"""
Alert ingestion service for Naxos framework connectors.

This service provides generalized alert persistence that can be used by any
connector with purpose="alert_ingestion". It handles:
- Converting raw source events to AlertCreate schema (via source-specific normalizers)
- Persisting alerts to the database
- Triggering alert analysis
- Deduplication

Note: Resilience is handled by tenacity retry decorators on API client methods.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.repositories.alert_repository import (
    AlertAnalysisRepository,
    AlertRepository,
    DispositionRepository,
)
from analysi.services.alert_service import AlertService

logger = get_logger(__name__)


class AlertIngestionService:
    """Service for ingesting alerts from integration connectors."""

    def __init__(self, session: AsyncSession):
        """Initialize with database session.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

        # Create required repositories for AlertService
        alert_repo = AlertRepository(session)
        analysis_repo = AlertAnalysisRepository(session)
        disposition_repo = DispositionRepository(session)

        self.alert_service = AlertService(
            alert_repo=alert_repo,
            analysis_repo=analysis_repo,
            disposition_repo=disposition_repo,
            session=session,
        )

    async def ingest_alerts(
        self,
        tenant_id: str,
        integration_type: str,
        raw_alerts: list[dict[str, Any]],
        normalizer_class=None,
    ) -> dict[str, Any]:
        """
        Ingest alerts from a connector into the database.

        Args:
            tenant_id: Tenant identifier
            integration_type: Type of integration (e.g., "splunk", "echo_edr")
            raw_alerts: List of raw alert dictionaries from the source
            normalizer_class: Optional normalizer class to use (auto-detected if not provided)

        Returns:
            Result dict with created/duplicate counts
        """
        if not raw_alerts:
            return {"created": 0, "duplicates": 0, "errors": 0}

        # Get normalizer for this integration type
        normalizer = self._get_normalizer(integration_type, normalizer_class)
        if not normalizer:
            logger.error(
                "no_normalizer_available_for_integration_type",
                integration_type=integration_type,
            )
            return {"created": 0, "duplicates": 0, "errors": len(raw_alerts)}

        created = 0
        duplicates = 0
        errors = 0

        # Process each alert
        for raw_alert in raw_alerts:
            try:
                # Normalize to OCSF, then create AlertCreate from shared fields
                ocsf_dict = normalizer.to_ocsf(raw_alert)
                alert_create = self._ocsf_to_alert_create(ocsf_dict)

                # Persist to database
                try:
                    alert = await self.alert_service.create_alert(
                        tenant_id, alert_create
                    )
                    created += 1

                    # Commit the alert to database BEFORE triggering analysis
                    # This ensures the analysis worker can access the complete alert data
                    await self.session.commit()

                    # Trigger analysis for the newly created alert
                    try:
                        await self._trigger_analysis(tenant_id, alert.alert_id)
                    except Exception as e:
                        logger.warning(
                            "failed_to_trigger_analysis_for_ingested_alert",
                            alert_id=str(alert.alert_id),
                            error=str(e),
                        )
                except ValueError as e:
                    # Duplicate alert detected (raises ValueError with "Duplicate alert detected")
                    if "Duplicate alert detected" in str(e):
                        duplicates += 1
                    else:
                        # Other ValueError - treat as error
                        logger.error("failed_to_ingest_alert", error=str(e))
                        errors += 1

            except Exception as e:
                logger.error("failed_to_ingest_alert", error=str(e))
                errors += 1
                continue

        logger.info(
            "alert_ingestion_complete",
            integration_type=integration_type,
            created=created,
            duplicates=duplicates,
            errors=errors,
        )

        return {
            "created": created,
            "duplicates": duplicates,
            "errors": errors,
        }

    @staticmethod
    def _ocsf_to_alert_create(ocsf: dict[str, Any]) -> Any:
        """Convert an OCSF Detection Finding dict to AlertCreate.

        Maps OCSF fields to the AlertCreate schema which shares columns
        with the Alert DB model (title, severity, source_vendor, etc.).
        """
        from analysi.schemas.alert import AlertCreate

        # Map severity_id back to string caption
        severity_map = {
            0: "unknown",
            1: "info",
            2: "low",
            3: "medium",
            4: "high",
            5: "critical",
            6: "fatal",
        }
        severity_id = ocsf.get("severity_id", 3)
        severity = ocsf.get("severity", severity_map.get(severity_id, "medium")).lower()

        return AlertCreate(
            title=ocsf.get("message")
            or ocsf.get("finding_info", {}).get("title", "Unknown Alert"),
            triggering_event_time=ocsf.get("time_dt")
            or ocsf.get("triggering_event_time"),
            severity=severity,
            raw_data=ocsf.get("raw_data", "{}"),
            source_vendor=ocsf.get("metadata", {})
            .get("product", {})
            .get("vendor_name"),
            source_product=ocsf.get("metadata", {}).get("product", {}).get("name"),
            rule_name=ocsf.get("finding_info", {}).get("analytic", {}).get("name")
            if isinstance(ocsf.get("finding_info", {}).get("analytic"), dict)
            else None,
            source_event_id=ocsf.get("metadata", {}).get("event_code"),
            # OCSF structured fields pass through directly
            finding_info=ocsf.get("finding_info"),
            ocsf_metadata=ocsf.get("metadata"),
            evidences=ocsf.get("evidences"),
            observables=ocsf.get("observables"),
            osint=ocsf.get("osint"),
            actor=ocsf.get("actor"),
            device=ocsf.get("device"),
            cloud=ocsf.get("cloud"),
            vulnerabilities=ocsf.get("vulnerabilities"),
            unmapped=ocsf.get("unmapped"),
            severity_id=severity_id,
            disposition_id=ocsf.get("disposition_id"),
            action_id=ocsf.get("action_id"),
            ocsf_time=ocsf.get("time"),
            detected_at=ocsf.get("finding_info", {}).get("created_time_dt"),
        )

    def _get_normalizer(self, integration_type: str, normalizer_class=None):
        """
        Get the appropriate normalizer for an integration type.

        Args:
            integration_type: Type of integration
            normalizer_class: Optional explicit normalizer class

        Returns:
            Normalizer instance or None
        """
        if normalizer_class:
            return normalizer_class()

        # Auto-detect normalizer based on integration type.
        # Project Skaros: OCSF normalizers are preferred; they produce OCSF
        # Detection Finding as canonical output and derive AlertCreate
        # for backward compat.
        normalizer_map = {
            "splunk": "alert_normalizer.splunk_ocsf.SplunkOCSFNormalizer",
            # Add more as needed:
            # "echo_edr": "alert_normalizer.echo_edr.EchoEDRNormalizer",
        }

        normalizer_path = normalizer_map.get(integration_type)
        if not normalizer_path:
            logger.warning(
                "no_normalizer_configured_for_integration_type",
                integration_type=integration_type,
            )
            return None

        try:
            # Dynamic import
            module_path, class_name = normalizer_path.rsplit(".", 1)
            module = __import__(module_path, fromlist=[class_name])
            normalizer_class = getattr(module, class_name)
            return normalizer_class()
        except Exception as e:
            logger.error(
                "failed_to_load_normalizer",
                normalizer_path=normalizer_path,
                error=str(e),
            )
            return None

    async def _trigger_analysis(self, tenant_id: str, alert_id: str) -> None:
        """
        Trigger alert analysis workflow.

        Args:
            tenant_id: Tenant identifier
            alert_id: Alert identifier
        """
        try:
            # Import here to avoid circular dependency
            from analysi.integrations.api_client import IntegrationAPIClient

            api_client = IntegrationAPIClient()
            await api_client.trigger_alert_analysis(tenant_id, alert_id)
            await api_client.close()

            logger.info("triggered_analysis_for_alert", alert_id=alert_id)
        except Exception as e:
            # Log but don't fail - analysis can happen later
            logger.warning(
                "failed_to_trigger_analysis_for_alert", alert_id=alert_id, error=str(e)
            )
