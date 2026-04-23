"""Repository for Kea Coordination database operations."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.models.kea_coordination import (
    AlertRoutingRule,
    AnalysisGroup,
    WorkflowGeneration,
)
from analysi.schemas.kea_coordination import WorkflowGenerationStatus


class AnalysisGroupRepository:
    """Repository for analysis group database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, tenant_id: str, title: str) -> AnalysisGroup:
        """Create a new analysis group."""
        group = AnalysisGroup(tenant_id=tenant_id, title=title)
        self.session.add(group)
        await self.session.flush()
        return group

    async def get_by_id(
        self, tenant_id: str, group_id: str | UUID
    ) -> AnalysisGroup | None:
        """Get analysis group by ID with tenant isolation."""
        stmt = select(AnalysisGroup).where(
            and_(
                AnalysisGroup.tenant_id == tenant_id,
                AnalysisGroup.id == group_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_title(self, tenant_id: str, title: str) -> AnalysisGroup | None:
        """Get analysis group by title with tenant isolation."""
        stmt = select(AnalysisGroup).where(
            and_(
                AnalysisGroup.tenant_id == tenant_id,
                AnalysisGroup.title == title,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, tenant_id: str) -> list[AnalysisGroup]:
        """List all analysis groups for a tenant."""
        stmt = select(AnalysisGroup).where(AnalysisGroup.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, tenant_id: str, group_id: str | UUID) -> bool:
        """
        Delete an analysis group by ID with tenant isolation.

        Returns True if deleted, False if not found.
        """
        group = await self.get_by_id(tenant_id, group_id)
        if not group:
            return False

        await self.session.delete(group)
        await self.session.flush()
        return True


class WorkflowGenerationRepository:
    """Repository for workflow generation database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        tenant_id: str,
        analysis_group_id: str | UUID,
        triggering_alert_analysis_id: str | UUID | None = None,
    ) -> WorkflowGeneration:
        """Create a new workflow generation."""
        generation = WorkflowGeneration(
            tenant_id=tenant_id,
            analysis_group_id=analysis_group_id,
            triggering_alert_analysis_id=triggering_alert_analysis_id,
            status=WorkflowGenerationStatus.RUNNING,
            is_active=True,
        )
        self.session.add(generation)
        await self.session.flush()
        return generation

    async def get_by_id(
        self, tenant_id: str, generation_id: str | UUID
    ) -> WorkflowGeneration | None:
        """Get workflow generation by ID with tenant isolation."""
        stmt = select(WorkflowGeneration).where(
            and_(
                WorkflowGeneration.tenant_id == tenant_id,
                WorkflowGeneration.id == generation_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_for_group(
        self, tenant_id: str, analysis_group_id: str | UUID
    ) -> WorkflowGeneration | None:
        """Get active workflow generation for an analysis group.

        Uses .limit(1) as safety net against duplicate is_active=True rows
        (e.g., if mark_as_failed didn't deactivate properly).
        """
        stmt = (
            select(WorkflowGeneration)
            .where(
                and_(
                    WorkflowGeneration.tenant_id == tenant_id,
                    WorkflowGeneration.analysis_group_id == analysis_group_id,
                    WorkflowGeneration.is_active == True,  # noqa: E712
                )
            )
            .order_by(WorkflowGeneration.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_for_group(
        self, tenant_id: str, analysis_group_id: str | UUID
    ) -> WorkflowGeneration | None:
        """Get the most recent workflow generation for an analysis group.

        Returns the latest generation regardless of is_active status.
        Used by reconciliation to detect failed generations.
        """
        stmt = (
            select(WorkflowGeneration)
            .where(
                and_(
                    WorkflowGeneration.tenant_id == tenant_id,
                    WorkflowGeneration.analysis_group_id == analysis_group_id,
                )
            )
            .order_by(WorkflowGeneration.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_generation_with_workflow_for_group(
        self, tenant_id: str, analysis_group_id: str | UUID
    ) -> WorkflowGeneration | None:
        """Get the most recent generation that has a workflow_id for this group.

        Unlike get_latest_for_group, this specifically looks for any generation
        with workflow_id IS NOT NULL. Handles the case where the latest generation
        is a failed retry (no workflow_id) but a previous generation already
        created a workflow.
        """
        stmt = (
            select(WorkflowGeneration)
            .where(
                and_(
                    WorkflowGeneration.tenant_id == tenant_id,
                    WorkflowGeneration.analysis_group_id == analysis_group_id,
                    WorkflowGeneration.workflow_id.isnot(None),
                )
            )
            .order_by(WorkflowGeneration.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        tenant_id: str,
        triggering_alert_analysis_id: str | UUID | None = None,
    ) -> list[WorkflowGeneration]:
        """List workflow generations for a tenant, optionally filtered by triggering alert."""
        conditions = [WorkflowGeneration.tenant_id == tenant_id]
        if triggering_alert_analysis_id is not None:
            conditions.append(
                WorkflowGeneration.triggering_alert_analysis_id
                == triggering_alert_analysis_id
            )
        stmt = select(WorkflowGeneration).where(and_(*conditions))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_progress(
        self,
        tenant_id: str,
        generation_id: str | UUID,
        stage: str | None = None,
        tasks_count: int | None = None,
        workspace_path: str | None = None,
    ) -> WorkflowGeneration | None:
        """Update workflow generation progress with pre-populated phases.

        All 4 phases are initialized upfront on first call. When a stage is marked
        as in_progress, all previous stages are automatically marked as completed.

        Args:
            stage: Stage name to mark as in_progress (e.g., "task_proposals")
            tasks_count: Optional task count (for task_building stage)
            workspace_path: Optional workspace path update

        Returns:
            Updated WorkflowGeneration or None if not found
        """
        from analysi.schemas.kea_coordination import (
            WORKFLOW_STAGES,
            PhaseStatus,
            WorkflowGenerationPhase,
            WorkflowGenerationProgress,
            WorkflowGenerationStage,
        )

        generation = await self.get_by_id(tenant_id, generation_id)
        if not generation:
            return None

        now = datetime.now(UTC)

        if stage is not None:
            # Parse existing progress or initialize with all 4 phases
            if generation.current_phase:
                progress = WorkflowGenerationProgress.model_validate(
                    generation.current_phase
                )
            else:
                progress = WorkflowGenerationProgress(phases=[])

            # Initialize all phases if empty (first progress update)
            if not progress.phases:
                progress.phases = [
                    WorkflowGenerationPhase(
                        stage=s,
                        status=PhaseStatus.NOT_STARTED,
                    )
                    for s in WORKFLOW_STAGES
                ]

            # Find the target stage index
            target_stage = WorkflowGenerationStage(stage)
            target_idx = WORKFLOW_STAGES.index(target_stage)

            # Update all phases based on target stage
            for i, phase in enumerate(progress.phases):
                if i < target_idx:
                    # Previous stages should be completed
                    if phase.status != PhaseStatus.COMPLETED:
                        phase.status = PhaseStatus.COMPLETED
                        if not phase.started_at:
                            phase.started_at = now
                        if not phase.completed_at:
                            phase.completed_at = now
                elif i == target_idx:
                    # Target stage becomes in_progress
                    phase.status = PhaseStatus.IN_PROGRESS
                    # Preserve started_at if already set (idempotent for retries)
                    if not phase.started_at:
                        phase.started_at = now
                    # Clear completed_at when transitioning to in_progress (defensive)
                    # Prevents stale completed_at from previous runs
                    phase.completed_at = None
                    if tasks_count is not None:
                        phase.tasks_count = tasks_count
                # Stages after target remain as-is (not_started)

            # Serialize to dict for JSONB storage (triggers SQLAlchemy change tracking)
            generation.current_phase = progress.model_dump(mode="json")

        if workspace_path is not None:
            generation.workspace_path = workspace_path

        await self.session.commit()
        return generation

    async def mark_stage_completed(
        self,
        tenant_id: str,
        generation_id: str | UUID,
        stage: str,
    ) -> WorkflowGeneration | None:
        """Mark a specific stage as completed.

        This provides explicit completion tracking (vs implicit tracking when next stage starts).
        Used by on_stage_complete callback to ensure stages are properly marked done.

        Args:
            stage: Stage name to mark as completed (e.g., "task_building")

        Returns:
            Updated WorkflowGeneration or None if not found
        """
        from analysi.schemas.kea_coordination import (
            PhaseStatus,
            WorkflowGenerationProgress,
            WorkflowGenerationStage,
        )

        generation = await self.get_by_id(tenant_id, generation_id)
        if not generation:
            return None

        if not generation.current_phase:
            return generation  # No phases to update

        now = datetime.now(UTC)
        target_stage = WorkflowGenerationStage(stage)
        progress = WorkflowGenerationProgress.model_validate(generation.current_phase)

        for phase in progress.phases:
            if phase.stage == target_stage:
                phase.status = PhaseStatus.COMPLETED
                if not phase.completed_at:
                    phase.completed_at = now
                break

        generation.current_phase = progress.model_dump(mode="json")
        await self.session.commit()
        return generation

    async def update_with_results(
        self,
        tenant_id: str,
        generation_id: str | UUID,
        workflow_id: str | UUID | None,
        status: str,
        orchestration_results: dict[str, Any] | None = None,
        workspace_path: str | None = None,
    ) -> WorkflowGeneration | None:
        """
        Update workflow generation with orchestration results.

        Called by the generation job after orchestration completes. If reconciliation
        has already marked this generation as failed (race condition), a completed
        status with a workflow_id overrides the reconciliation's failed status — the
        job has the authoritative result.

        Args:
            orchestration_results: Single JSONB field containing all results:
                {
                    "runbook": str,
                    "task_proposals": [...],
                    "tasks_built": [...],
                    "workflow_composition": [...],
                    "metrics": {...},
                    "error": {...}  // if status == "failed"
                }
            workspace_path: Path to workspace directory for cleanup
        """

        from analysi.schemas.kea_coordination import (
            PhaseStatus,
            WorkflowGenerationProgress,
        )

        logger = get_logger(__name__)

        generation = await self.get_by_id(tenant_id, generation_id)
        if not generation:
            return None

        # Detect race: reconciliation marked as failed, but job actually completed
        if (
            generation.status == WorkflowGenerationStatus.FAILED
            and status == WorkflowGenerationStatus.COMPLETED
            and workflow_id is not None
        ):
            logger.warning(
                "generation_overriding_failed_to_completed",
                generation_id=str(generation_id),
                workflow_id=str(workflow_id),
            )

        generation.workflow_id = workflow_id
        generation.status = status
        generation.orchestration_results = orchestration_results

        # Update workspace_path if provided
        if workspace_path is not None:
            generation.workspace_path = workspace_path

        if status in (
            WorkflowGenerationStatus.COMPLETED,
            WorkflowGenerationStatus.FAILED,
        ):
            generation.completed_at = datetime.now(UTC)
            generation.is_active = (
                False  # Deactivate so new alerts create new generations
            )

            # Mark all phases as completed when workflow generation finishes
            if generation.current_phase:
                now = datetime.now(UTC)
                progress = WorkflowGenerationProgress.model_validate(
                    generation.current_phase
                )
                for phase in progress.phases:
                    if phase.status != PhaseStatus.COMPLETED:
                        phase.status = PhaseStatus.COMPLETED
                        if not phase.started_at:
                            phase.started_at = now
                        if not phase.completed_at:
                            phase.completed_at = now
                generation.current_phase = progress.model_dump(mode="json")

        await self.session.commit()
        return generation

    async def deactivate_previous_generations(
        self, tenant_id: str, analysis_group_id: str | UUID
    ) -> None:
        """Deactivate all previous generations for an analysis group."""
        stmt = (
            update(WorkflowGeneration)
            .where(
                and_(
                    WorkflowGeneration.tenant_id == tenant_id,
                    WorkflowGeneration.analysis_group_id == analysis_group_id,
                    WorkflowGeneration.is_active == True,  # noqa: E712
                )
            )
            .values(is_active=False)
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def count_running(self, tenant_id: str | None = None) -> int:
        """
        Count workflow generations with status='running'.

        Args:
            tenant_id: Optional tenant filter. If None, counts across all tenants.

        Returns:
            int: Number of running workflow generations
        """
        stmt = select(func.count(WorkflowGeneration.id)).where(
            WorkflowGeneration.status == WorkflowGenerationStatus.RUNNING
        )

        if tenant_id:
            stmt = stmt.where(WorkflowGeneration.tenant_id == tenant_id)

        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def find_stuck_generations(
        self, timeout_seconds: int = 3600
    ) -> list[WorkflowGeneration]:
        """
        Find workflow generations stuck in 'running' status beyond timeout threshold.

        Args:
            timeout_seconds: Timeout threshold in seconds (default: 3600 = 60 minutes)
                            Should match ARQ job timeout (AlertAnalysisConfig.JOB_TIMEOUT)

        Returns:
            list[WorkflowGeneration]: Stuck generations across all tenants
        """
        from datetime import timedelta

        cutoff_time = datetime.now(UTC) - timedelta(seconds=timeout_seconds)

        stmt = select(WorkflowGeneration).where(
            and_(
                WorkflowGeneration.status == WorkflowGenerationStatus.RUNNING,
                WorkflowGeneration.created_at < cutoff_time,
            )
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_as_failed(
        self, generation: WorkflowGeneration, error_message: str
    ) -> bool:
        """
        Atomically mark a workflow generation as failed, ONLY if still running.

        Uses SQL UPDATE ... WHERE status='running' to prevent overwriting a
        generation that was concurrently completed by the job. This fixes the
        race condition where reconciliation marks a just-completed generation
        as failed.

        Args:
            generation: WorkflowGeneration instance to update
            error_message: Error message to store

        Returns:
            True if the generation was marked as failed, False if it was
            already in a terminal state (completed/failed).
        """
        now = datetime.now(UTC)

        # Build error payload for orchestration_results
        if generation.orchestration_results is None:
            results = {}
        else:
            results = dict(generation.orchestration_results)

        results["error"] = {
            "message": error_message,
            "type": "timeout",
            "timestamp": now.isoformat(),
        }

        # Atomic UPDATE only if still running — prevents race with job completion
        stmt = (
            update(WorkflowGeneration)
            .where(
                and_(
                    WorkflowGeneration.id == generation.id,
                    WorkflowGeneration.status == WorkflowGenerationStatus.RUNNING,
                )
            )
            .values(
                status=WorkflowGenerationStatus.FAILED,
                completed_at=now,
                is_active=False,
                orchestration_results=results,
            )
        )

        result = await self.session.execute(stmt)
        await self.session.commit()

        rows_affected = result.rowcount
        # Generation was already completed or failed — not a problem
        return rows_affected != 0

    async def find_generations_for_cleanup(
        self,
        status_filter: list[str] | None = None,
    ) -> list[WorkflowGeneration]:
        """
        Get terminal generations for workspace cleanup.

        Args:
            status_filter: List of statuses to filter by (default: ["completed", "failed"])

        Returns:
            list[WorkflowGeneration]: Terminal generations ready for cleanup
        """
        if status_filter is None:
            status_filter = [
                WorkflowGenerationStatus.COMPLETED,
                WorkflowGenerationStatus.FAILED,
            ]

        stmt = select(WorkflowGeneration).where(
            WorkflowGeneration.status.in_(status_filter)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, tenant_id: str, generation_id: str | UUID) -> bool:
        """
        Delete a workflow generation by ID with tenant isolation.

        Returns True if deleted, False if not found.
        """
        generation = await self.get_by_id(tenant_id, generation_id)
        if not generation:
            return False

        await self.session.delete(generation)
        await self.session.flush()
        return True


class AlertRoutingRuleRepository:
    """Repository for alert routing rule database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        tenant_id: str,
        analysis_group_id: str | UUID,
        workflow_id: str | UUID,
    ) -> AlertRoutingRule:
        """Create a new alert routing rule."""
        rule = AlertRoutingRule(
            tenant_id=tenant_id,
            analysis_group_id=analysis_group_id,
            workflow_id=workflow_id,
        )
        self.session.add(rule)
        await self.session.flush()
        return rule

    async def get_by_id(
        self, tenant_id: str, rule_id: str | UUID
    ) -> AlertRoutingRule | None:
        """Get alert routing rule by ID with tenant isolation."""
        stmt = select(AlertRoutingRule).where(
            and_(
                AlertRoutingRule.tenant_id == tenant_id,
                AlertRoutingRule.id == rule_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_group_id(
        self, tenant_id: str, analysis_group_id: str | UUID
    ) -> AlertRoutingRule | None:
        """Get alert routing rule by analysis group ID.

        If duplicates exist (bug: orchestration creates multiple rules),
        returns the most recently created rule.
        """
        stmt = (
            select(AlertRoutingRule)
            .where(
                and_(
                    AlertRoutingRule.tenant_id == tenant_id,
                    AlertRoutingRule.analysis_group_id == analysis_group_id,
                )
            )
            .order_by(AlertRoutingRule.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, tenant_id: str) -> list[AlertRoutingRule]:
        """List all alert routing rules for a tenant."""
        stmt = select(AlertRoutingRule).where(AlertRoutingRule.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, tenant_id: str, rule_id: str | UUID) -> bool:
        """
        Delete an alert routing rule by ID with tenant isolation.

        Returns True if deleted, False if not found.
        """
        rule = await self.get_by_id(tenant_id, rule_id)
        if not rule:
            return False

        await self.session.delete(rule)
        await self.session.flush()
        return True
