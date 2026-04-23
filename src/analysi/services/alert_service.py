"""Service layer for alert business logic."""

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from analysi.config.logging import get_logger
from analysi.models.alert import Alert, AlertAnalysis, Disposition
from analysi.repositories.alert_repository import (
    AlertAnalysisRepository,
    AlertRepository,
    DispositionRepository,
)
from analysi.schemas.alert import (
    AlertAnalysisResponse,
    AlertCreate,
    AlertList,
    AlertResponse,
    AlertStatus,
    AlertUpdate,
    DispositionResponse,
    StepProgress,
)

logger = get_logger(__name__)


class AlertService:
    """Service for alert management."""

    def __init__(
        self,
        alert_repo: AlertRepository,
        analysis_repo: AlertAnalysisRepository,
        disposition_repo: DispositionRepository,
        session: AsyncSession,
    ):
        self.alert_repo = alert_repo
        self.analysis_repo = analysis_repo
        self.disposition_repo = disposition_repo
        self.session = session

    async def create_alert(
        self, tenant_id: str, alert_data: AlertCreate
    ) -> AlertResponse:
        """Create new alert with deduplication."""
        # Calculate raw_data_hash for deduplication
        raw_data_hash = self._calculate_raw_data_hash(alert_data.raw_data)

        # Generate human readable ID if not provided
        # The database function handles atomicity, so no retry needed
        if not alert_data.human_readable_id:
            human_readable_id = await self.alert_repo.get_next_human_readable_id(
                tenant_id
            )
        else:
            human_readable_id = alert_data.human_readable_id

        # Create alert with deduplication
        alert_dict = alert_data.model_dump(exclude={"human_readable_id"})
        alert = await self.alert_repo.create_with_deduplication(
            tenant_id=tenant_id,
            raw_data_hash=raw_data_hash,
            human_readable_id=human_readable_id,
            **alert_dict,
        )

        if not alert:
            # Duplicate found, raise exception for 409 response
            logger.info(
                "Duplicate alert detected during creation",
                tenant_id=tenant_id,
                raw_data_hash=raw_data_hash,
                source_event_id=alert_data.source_event_id,
                title=alert_data.title,
                triggering_event_time=str(alert_data.triggering_event_time),
                source_product=alert_data.source_product,
            )
            raise ValueError(
                f"Duplicate alert detected with raw_data_hash: {raw_data_hash}"
            )

        return AlertResponse.model_validate(alert)

    async def get_alert(
        self,
        tenant_id: str,
        alert_id: UUID,
        include_analysis: bool = True,
    ) -> AlertResponse | None:
        """Get alert with optional expanded relationships."""
        stmt = select(Alert).where(Alert.id == alert_id, Alert.tenant_id == tenant_id)

        if include_analysis:
            stmt = stmt.options(selectinload(Alert.analyses))

        result = await self.session.execute(stmt)
        alert = result.scalar_one_or_none()

        if not alert:
            return None

        response = AlertResponse.model_validate(alert)

        # Add current analysis if requested
        if include_analysis and alert.current_analysis_id:
            current_analysis = await self.analysis_repo.get_current_analysis(
                alert_id, tenant_id
            )
            if current_analysis:
                response.current_analysis = AlertAnalysisResponse.model_validate(
                    current_analysis
                )

        return response

    async def list_alerts(
        self,
        tenant_id: str,
        filters: dict[str, Any],
        limit: int = 20,
        offset: int = 0,
        include_short_summary: bool = False,
        sort_by: str = "triggering_event_time",
        sort_order: str = "desc",
    ) -> AlertList:
        """List alerts with filtering and pagination."""
        alerts, total = await self.alert_repo.find_by_filters(
            tenant_id=tenant_id,
            severity=filters.get("severity"),
            status=filters.get("status"),
            source_vendor=filters.get("source_vendor"),
            source_product=filters.get("source_product"),
            time_from=filters.get("time_from"),
            time_to=filters.get("time_to"),
            disposition_category=filters.get("disposition_category"),
            disposition_subcategory=filters.get("disposition_subcategory"),
            min_confidence=filters.get("min_confidence"),
            max_confidence=filters.get("max_confidence"),
            title_filter=filters.get("title_filter"),
            ioc_filter=filters.get("ioc_filter"),
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        alert_responses = []
        for alert in alerts:
            response = AlertResponse.model_validate(alert)

            # Optionally add short summary from current analysis
            if include_short_summary and alert.current_analysis_id:
                analysis = await self.analysis_repo.get_by_id(
                    alert.current_analysis_id, tenant_id
                )
                if analysis and analysis.short_summary:
                    response.short_summary = analysis.short_summary

            alert_responses.append(response)

        return AlertList(
            alerts=alert_responses, total=total, limit=limit, offset=offset
        )

    async def update_alert(
        self, tenant_id: str, alert_id: UUID, update_data: AlertUpdate
    ) -> AlertResponse:
        """Update alert (only mutable fields)."""
        stmt = select(Alert).where(Alert.id == alert_id, Alert.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        alert = result.scalar_one_or_none()

        if not alert:
            raise ValueError(f"Alert {alert_id} not found")

        # Update only allowed fields
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(alert, field, value)

        alert.updated_at = datetime.now(UTC)
        await self.session.flush()

        return AlertResponse.model_validate(alert)

    async def delete_alert(self, tenant_id: str, alert_id: UUID) -> bool:
        """Hard delete alert."""
        return await self.alert_repo.delete(alert_id, tenant_id)

    async def search_similar_alerts(
        self, tenant_id: str, alert_id: UUID, threshold: float = 0.7, limit: int = 10
    ) -> list[AlertResponse]:
        """Find similar alerts."""
        similar_alerts = await self.alert_repo.search_similar(
            alert_id=alert_id, tenant_id=tenant_id, threshold=threshold, limit=limit
        )

        return [AlertResponse.model_validate(alert) for alert in similar_alerts]

    async def search_alerts(
        self, tenant_id: str, query: str, limit: int = 20
    ) -> list[AlertResponse]:
        """Search alerts using text search."""
        alerts = await self.alert_repo.search_text(tenant_id, query, limit)
        return [AlertResponse.model_validate(alert) for alert in alerts]

    async def get_alerts_by_entity(
        self,
        tenant_id: str,
        entity_value: str,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[AlertResponse]:
        """Get alerts by entity value and optional type."""
        alerts = await self.alert_repo.get_by_entity(
            tenant_id, entity_value, entity_type, limit
        )
        return [AlertResponse.model_validate(alert) for alert in alerts]

    async def get_alerts_by_ioc(
        self,
        tenant_id: str,
        ioc_value: str,
        ioc_type: str | None = None,
        limit: int = 20,
    ) -> list[AlertResponse]:
        """Get alerts by IOC value and optional type."""
        alerts = await self.alert_repo.get_by_ioc(tenant_id, ioc_value, ioc_type, limit)
        return [AlertResponse.model_validate(alert) for alert in alerts]

    def _calculate_raw_data_hash(self, raw_data: str) -> str:
        """Calculate SHA-256 hash of raw_data for deduplication.

        The hash is computed over the full raw alert payload so that
        byte-identical ingestions are caught regardless of field mapping.
        """
        return hashlib.sha256(raw_data.encode()).hexdigest()


class AlertAnalysisService:
    """Service for alert analysis operations."""

    def __init__(
        self,
        analysis_repo: AlertAnalysisRepository,
        alert_repo: AlertRepository,
        session: AsyncSession,
    ):
        self.analysis_repo = analysis_repo
        self.alert_repo = alert_repo
        self.session = session

    async def start_analysis(
        self, tenant_id: str, alert_id: UUID
    ) -> AlertAnalysisResponse:
        """Start new analysis for an alert."""
        # Create new analysis
        analysis = await self.analysis_repo.create_analysis(
            alert_id=alert_id, tenant_id=tenant_id
        )

        # Update alert to reference this analysis and reset disposition fields
        stmt = select(Alert).where(Alert.id == alert_id, Alert.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        alert = result.scalar_one_or_none()

        if alert:
            alert.current_analysis_id = analysis.id
            alert.analysis_status = AlertStatus.IN_PROGRESS

            # Reset denormalized disposition fields for re-analysis
            alert.current_disposition_category = None
            alert.current_disposition_subcategory = None
            alert.current_disposition_display_name = None
            alert.current_disposition_confidence = None

            await self.session.flush()

        return AlertAnalysisResponse.model_validate(analysis)

    async def get_analysis_progress(
        self, tenant_id: str, alert_id: UUID
    ) -> dict[str, Any]:
        """Get current analysis progress."""
        analysis = await self.analysis_repo.get_current_analysis(
            alert_id=alert_id, tenant_id=tenant_id
        )

        if not analysis:
            return {}

        # Parse steps progress (handles both old and new formats)
        from analysi.schemas.alert import PipelineStepsProgress, StepStatus

        steps_progress_dict = analysis.steps_progress or {}
        progress = PipelineStepsProgress.from_dict(steps_progress_dict)

        # Count completed steps
        completed_steps = sum(
            1 for step in progress.steps if step.status == StepStatus.COMPLETED
        )

        # Convert to StepProgress objects for backward compatibility
        steps_detail = {}
        for step_progress in progress.steps:
            steps_detail[step_progress.step.value] = StepProgress(
                completed=(step_progress.status == StepStatus.COMPLETED),
                started_at=step_progress.started_at,
                completed_at=step_progress.completed_at,
                retries=step_progress.retries,
                error=step_progress.error,
            )

        return {
            "analysis_id": analysis.id,
            "current_step": analysis.current_step or "not_started",
            "completed_steps": completed_steps,
            "total_steps": 4,  # All 4 steps are now pre-populated
            "status": analysis.status,
            "error_message": (
                analysis.error_message if hasattr(analysis, "error_message") else None
            ),
            "steps_detail": steps_detail,
        }

    async def get_analysis_history(
        self, tenant_id: str, alert_id: UUID
    ) -> list[AlertAnalysisResponse]:
        """Get all analyses for an alert."""
        analyses = await self.analysis_repo.get_analysis_history(
            alert_id=alert_id, tenant_id=tenant_id
        )

        return [AlertAnalysisResponse.model_validate(analysis) for analysis in analyses]

    async def update_analysis_step(
        self, analysis_id: UUID, step: str, completed: bool, error: str | None = None
    ) -> None:
        """Update analysis step progress."""
        await self.analysis_repo.update_step_progress(
            analysis_id=analysis_id, step=step, completed=completed, error=error
        )

    async def complete_analysis(
        self,
        analysis_id: UUID,
        disposition_id: UUID,
        confidence: int,
        short_summary: str,
        long_summary: str,
    ) -> None:
        """Mark analysis as completed with results."""
        await self.analysis_repo.mark_completed(
            analysis_id=analysis_id,
            disposition_id=disposition_id,
            confidence=confidence,
            short_summary=short_summary,
            long_summary=long_summary,
        )

        # Update associated alert status
        stmt = select(AlertAnalysis).where(AlertAnalysis.id == analysis_id)
        result = await self.session.execute(stmt)
        analysis = result.scalar_one_or_none()

        if analysis:
            alert_stmt = select(Alert).where(
                Alert.id == analysis.alert_id,
                Alert.tenant_id == analysis.tenant_id,
            )
            alert_result = await self.session.execute(alert_stmt)
            alert = alert_result.scalar_one_or_none()

            if alert:
                alert.analysis_status = AlertStatus.COMPLETED
                await self.session.flush()


class DispositionService:
    """Service for disposition management."""

    def __init__(self, disposition_repo: DispositionRepository, session: AsyncSession):
        self.disposition_repo = disposition_repo
        self.session = session

    async def list_dispositions(
        self, category: str | None = None, requires_escalation: bool | None = None
    ) -> list[DispositionResponse]:
        """List dispositions with optional filters."""
        conditions = []
        if category:
            conditions.append(Disposition.category == category)
        if requires_escalation is not None:
            conditions.append(Disposition.requires_escalation == requires_escalation)

        stmt = select(Disposition)
        if conditions:
            from sqlalchemy import and_

            stmt = stmt.where(and_(*conditions))

        stmt = stmt.order_by(Disposition.priority_score)

        result = await self.session.execute(stmt)
        dispositions = result.scalars().all()

        return [DispositionResponse.model_validate(disp) for disp in dispositions]

    async def get_disposition(self, disposition_id: UUID) -> DispositionResponse | None:
        """Get specific disposition."""
        stmt = select(Disposition).where(Disposition.id == disposition_id)
        result = await self.session.execute(stmt)
        disposition = result.scalar_one_or_none()

        if not disposition:
            return None

        return DispositionResponse.model_validate(disposition)

    async def get_by_category(self) -> dict[str, list[DispositionResponse]]:
        """Get dispositions grouped by category."""
        grouped = await self.disposition_repo.get_by_category()

        # Convert to response schemas
        result = {}
        for category, dispositions in grouped.items():
            result[category] = [
                DispositionResponse.model_validate(disp) for disp in dispositions
            ]

        return result

    async def create_custom_disposition(
        self,
        category: str,
        subcategory: str,
        display_name: str,
        color_hex: str,
        color_name: str,
        priority_score: int,
        description: str | None = None,
        requires_escalation: bool = False,
    ) -> DispositionResponse:
        """Create custom disposition (admin only)."""
        disposition = await self.disposition_repo.create_custom_disposition(
            category=category,
            subcategory=subcategory,
            display_name=display_name,
            color_hex=color_hex,
            color_name=color_name,
            priority_score=priority_score,
            description=description,
            requires_escalation=requires_escalation,
        )

        return DispositionResponse.model_validate(disposition)
