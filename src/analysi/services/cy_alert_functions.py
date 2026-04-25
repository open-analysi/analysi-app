"""
Cy Native Functions for Alert Access.

Provides alert retrieval for Cy scripts. Returns OCSF-shaped dicts
that work with the Cy OCSF helpers (get_primary_user, get_src_ip, etc.).

Project Skaros: OCSF-only.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.models.alert import Alert

logger = get_logger(__name__)


class CyAlertFunctions:
    """Native functions for alert access in Cy scripts."""

    def __init__(
        self, session: AsyncSession, tenant_id: str, execution_context: dict[str, Any]
    ):
        self.session = session
        self.tenant_id = tenant_id
        self.execution_context = execution_context

    async def alert_read(self, alert_id: str) -> dict[str, Any]:
        """
        Get an alert by ID and return it in OCSF format.

        Returns a dict with OCSF fields that work with Cy helpers:
        get_primary_user(alert), get_src_ip(alert), get_observables(alert), etc.

        Args:
            alert_id: UUID string of the alert to retrieve

        Returns:
            Alert data as OCSF-shaped dict

        Raises:
            ValueError: If alert_id is invalid or alert not found
        """
        try:
            alert_uuid = UUID(alert_id)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid alert_id format: {alert_id}") from e

        stmt = select(Alert).where(
            Alert.tenant_id == self.tenant_id, Alert.id == alert_uuid
        )
        result = await self.session.execute(stmt)
        alert = result.scalar_one_or_none()

        if not alert:
            raise ValueError(f"Alert {alert_id} not found for tenant {self.tenant_id}")

        # Build OCSF-shaped dict from model columns
        alert_dict: dict[str, Any] = {
            # Analysi identifiers
            "alert_id": str(alert.id),
            "human_readable_id": alert.human_readable_id,
            "tenant_id": alert.tenant_id,
            # OCSF core fields
            "title": alert.title,
            "severity": alert.severity,
            "severity_id": alert.severity_id,
            "finding_info": alert.finding_info or {},
            "metadata": alert.ocsf_metadata or {},
            # OCSF structured fields (used by Cy helpers)
            "observables": alert.observables,
            "evidences": alert.evidences,
            "osint": alert.osint,
            "actor": alert.actor,
            "device": alert.device,
            "cloud": alert.cloud,
            "vulnerabilities": alert.vulnerabilities,
            "unmapped": alert.unmapped,
            # OCSF scalar enums
            "disposition_id": alert.disposition_id,
            "verdict_id": alert.verdict_id,
            "action_id": alert.action_id,
            "status_id": alert.status_id,
            "confidence_id": alert.confidence_id,
            "risk_level_id": alert.risk_level_id,
            # Source identification
            "source_vendor": alert.source_vendor,
            "source_product": alert.source_product,
            "rule_name": alert.rule_name,
            "source_event_id": alert.source_event_id,
            # Timestamps
            "triggering_event_time": (
                alert.triggering_event_time.isoformat()
                if alert.triggering_event_time
                else None
            ),
            "detected_at": (
                alert.detected_at.isoformat() if alert.detected_at else None
            ),
            "created_at": (alert.created_at.isoformat() if alert.created_at else None),
            "updated_at": (alert.updated_at.isoformat() if alert.updated_at else None),
            # Raw data
            "raw_data": alert.raw_data,
            "raw_data_hash": alert.raw_data_hash,
            # Analysis state
            "analysis_status": alert.analysis_status,
            "current_analysis_id": (
                str(alert.current_analysis_id) if alert.current_analysis_id else None
            ),
            "current_disposition_category": alert.current_disposition_category,
            "current_disposition_subcategory": alert.current_disposition_subcategory,
            "current_disposition_display_name": alert.current_disposition_display_name,
            "current_disposition_confidence": alert.current_disposition_confidence,
        }

        logger.debug(
            "alert_retrieved_for_cy_script",
            alert_id=alert_id,
            tenant_id=self.tenant_id,
            task_id=self.execution_context.get("task_id"),
            workflow_id=self.execution_context.get("workflow_id"),
        )

        return alert_dict

    async def cleanup(self):
        """Clean up resources."""
        pass


def create_cy_alert_functions(
    session: AsyncSession, tenant_id: str, execution_context: dict[str, Any]
) -> dict[str, Any]:
    """Create dictionary of alert functions for Cy interpreter."""
    alert_functions = CyAlertFunctions(session, tenant_id, execution_context)

    async def alert_read_wrapper(alert_id: str) -> dict[str, Any]:
        """Cy-compatible wrapper for retrieving alerts in OCSF format."""
        return await alert_functions.alert_read(alert_id)

    return {
        "alert_read": alert_read_wrapper,
    }
