"""Service layer for Kea Coordination."""

from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from analysi.models.kea_coordination import (
    AlertRoutingRule,
    AnalysisGroup,
    WorkflowGeneration,
)
from analysi.repositories.kea_coordination_repository import (
    AlertRoutingRuleRepository,
    AnalysisGroupRepository,
    WorkflowGenerationRepository,
)


class AnalysisGroupService:
    """Service for analysis group business logic."""

    def __init__(
        self,
        group_repo: AnalysisGroupRepository,
        generation_repo: WorkflowGenerationRepository,
        rule_repo: AlertRoutingRuleRepository | None = None,
    ):
        self.group_repo = group_repo
        self.generation_repo = generation_repo
        self.rule_repo = rule_repo

    async def create_group(self, tenant_id: str, title: str) -> AnalysisGroup:
        """Create a new analysis group."""
        return await self.group_repo.create(tenant_id=tenant_id, title=title)

    async def get_group_by_id(
        self, tenant_id: str, group_id: str | UUID
    ) -> AnalysisGroup | None:
        """Get analysis group by ID."""
        return await self.group_repo.get_by_id(tenant_id=tenant_id, group_id=group_id)

    async def get_group_by_title(
        self, tenant_id: str, title: str
    ) -> AnalysisGroup | None:
        """Get analysis group by title."""
        return await self.group_repo.get_by_title(tenant_id=tenant_id, title=title)

    async def list_groups(self, tenant_id: str) -> list[AnalysisGroup]:
        """List all analysis groups for tenant."""
        return await self.group_repo.list_all(tenant_id=tenant_id)

    async def delete_group(self, tenant_id: str, group_id: str | UUID) -> bool:
        """Delete an analysis group by ID. Returns True if deleted, False if not found."""
        return await self.group_repo.delete(tenant_id=tenant_id, group_id=group_id)

    async def create_group_with_generation(
        self,
        tenant_id: str,
        title: str,
        triggering_alert_analysis_id: str | UUID | None = None,
    ) -> tuple[AnalysisGroup, WorkflowGeneration]:
        """
        Atomically create analysis group + workflow generation.

        Handles race conditions where multiple workers try to create the same group:
        1. Try to find existing group by title
        2. If not found, try to create it
        3. If creation fails (IntegrityError), another worker created it first
        4. Fall back to looking up the existing group
        5. Check routing rules first (authoritative source for workflow mapping)
        6. Fall back to workflow_generations if no routing rule
        7. Create new generation if neither exists

        Returns tuple of (AnalysisGroup, WorkflowGeneration).
        """
        # First attempt: check if group already exists
        existing_group = await self.group_repo.get_by_title(
            tenant_id=tenant_id, title=title
        )

        if not existing_group:
            try:
                # Try to create the group
                existing_group = await self.group_repo.create(
                    tenant_id=tenant_id, title=title
                )
            except IntegrityError:
                # Race condition: another worker created it first
                # Look it up again
                existing_group = await self.group_repo.get_by_title(
                    tenant_id=tenant_id, title=title
                )
                if not existing_group:
                    # Should never happen, but handle gracefully
                    raise RuntimeError(
                        f"Failed to find or create analysis group '{title}' for tenant '{tenant_id}'"
                    )

        # Now handle workflow generation
        # First check for active (in-progress) generation
        existing_generation = await self.generation_repo.get_active_for_group(
            tenant_id=tenant_id, analysis_group_id=existing_group.id
        )

        if existing_generation:
            # Active generation in progress - return it
            return existing_group, existing_generation

        # No active generation - check routing rules FIRST (authoritative source)
        # Routing rules represent explicit user configuration and take priority
        if self.rule_repo:
            routing_rule = await self.rule_repo.get_by_group_id(
                tenant_id=tenant_id, analysis_group_id=existing_group.id
            )
            if routing_rule and routing_rule.workflow_id:
                # Routing rule exists - use its workflow_id
                # Get latest generation as container, update workflow_id to match rule
                latest_generation = await self.generation_repo.get_latest_for_group(
                    tenant_id=tenant_id, analysis_group_id=existing_group.id
                )
                if latest_generation:
                    # Override workflow_id with routing rule's value
                    # This ensures users can update routing rules and have changes take effect
                    latest_generation.workflow_id = routing_rule.workflow_id
                    return existing_group, latest_generation
                # Routing rule exists but no generation record - create a placeholder
                # This is an edge case but we should handle it gracefully
                new_generation = await self.generation_repo.create(
                    tenant_id=tenant_id,
                    analysis_group_id=existing_group.id,
                    triggering_alert_analysis_id=triggering_alert_analysis_id,
                )
                new_generation.workflow_id = routing_rule.workflow_id
                return existing_group, new_generation

        # No routing rule - fall back to workflow_generations (legacy behavior)
        latest_generation = await self.generation_repo.get_latest_for_group(
            tenant_id=tenant_id, analysis_group_id=existing_group.id
        )
        if latest_generation and latest_generation.workflow_id:
            # A workflow already exists for this group - reuse the completed generation
            return existing_group, latest_generation

        # Check if any previous generation created a workflow.
        # Handles: latest is a failed retry (no workflow_id), but an earlier
        # generation already created a workflow successfully.
        gen_with_workflow = (
            await self.generation_repo.get_generation_with_workflow_for_group(
                tenant_id=tenant_id, analysis_group_id=existing_group.id
            )
        )
        if gen_with_workflow:
            return existing_group, gen_with_workflow

        # No usable generation exists, create a new one
        new_generation = await self.generation_repo.create(
            tenant_id=tenant_id,
            analysis_group_id=existing_group.id,
            triggering_alert_analysis_id=triggering_alert_analysis_id,
        )

        return existing_group, new_generation


class WorkflowGenerationService:
    """Service for workflow generation business logic."""

    def __init__(self, generation_repo: WorkflowGenerationRepository):
        self.generation_repo = generation_repo

    async def get_generation_by_id(
        self, tenant_id: str, generation_id: str | UUID
    ) -> WorkflowGeneration | None:
        """Get workflow generation by ID."""
        return await self.generation_repo.get_by_id(
            tenant_id=tenant_id, generation_id=generation_id
        )

    async def get_latest_generation_for_group(
        self, tenant_id: str, analysis_group_id: str | UUID
    ) -> WorkflowGeneration | None:
        """Get the most recent workflow generation for an analysis group.

        Used by reconciliation to detect failed generations (even if is_active=False).
        """
        return await self.generation_repo.get_latest_for_group(
            tenant_id=tenant_id, analysis_group_id=analysis_group_id
        )

    async def list_generations(
        self,
        tenant_id: str,
        triggering_alert_analysis_id: str | UUID | None = None,
    ) -> list[WorkflowGeneration]:
        """List workflow generations for tenant, optionally filtered by triggering alert."""
        return await self.generation_repo.list_all(
            tenant_id=tenant_id,
            triggering_alert_analysis_id=triggering_alert_analysis_id,
        )

    async def update_generation_progress(
        self,
        tenant_id: str,
        generation_id: str | UUID,
        stage: str | None = None,
        tasks_count: int | None = None,
        workspace_path: str | None = None,
    ) -> WorkflowGeneration | None:
        """Update workflow generation progress with pre-populated phases.

        All 4 phases are initialized upfront. When a stage is marked as in_progress,
        all previous stages are automatically marked as completed.
        """
        return await self.generation_repo.update_progress(
            tenant_id=tenant_id,
            generation_id=generation_id,
            stage=stage,
            tasks_count=tasks_count,
            workspace_path=workspace_path,
        )

    async def mark_stage_completed(
        self,
        tenant_id: str,
        generation_id: str | UUID,
        stage: str,
    ) -> WorkflowGeneration | None:
        """Mark a specific stage as completed.

        Provides explicit completion tracking for workflow generation phases.
        """
        return await self.generation_repo.mark_stage_completed(
            tenant_id=tenant_id,
            generation_id=generation_id,
            stage=stage,
        )

    async def update_generation_results(
        self,
        tenant_id: str,
        generation_id: str | UUID,
        workflow_id: str | UUID | None,
        status: str,
        orchestration_results: dict[str, Any] | None = None,
        workspace_path: str | None = None,
    ) -> WorkflowGeneration | None:
        """Update workflow generation with orchestration results (single JSONB field)."""
        return await self.generation_repo.update_with_results(
            tenant_id=tenant_id,
            generation_id=generation_id,
            workflow_id=workflow_id,
            status=status,
            orchestration_results=orchestration_results,
            workspace_path=workspace_path,
        )

    async def trigger_regeneration(
        self, tenant_id: str, analysis_group_id: str | UUID
    ) -> WorkflowGeneration:
        """
        Trigger workflow regeneration for an analysis group.

        Deactivates previous generations and creates a new active one.
        """
        # Deactivate all previous generations
        await self.generation_repo.deactivate_previous_generations(
            tenant_id=tenant_id, analysis_group_id=analysis_group_id
        )

        # Create new active generation
        return await self.generation_repo.create(
            tenant_id=tenant_id, analysis_group_id=analysis_group_id
        )

    async def delete_generation(
        self, tenant_id: str, generation_id: str | UUID
    ) -> bool:
        """Delete a workflow generation by ID. Returns True if deleted, False if not found."""
        return await self.generation_repo.delete(
            tenant_id=tenant_id, generation_id=generation_id
        )


class AlertRoutingRuleService:
    """Service for alert routing rule business logic."""

    def __init__(self, rule_repo: AlertRoutingRuleRepository):
        self.rule_repo = rule_repo

    async def create_rule(
        self,
        tenant_id: str,
        analysis_group_id: str | UUID,
        workflow_id: str | UUID,
    ) -> AlertRoutingRule:
        """Create a new alert routing rule."""
        return await self.rule_repo.create(
            tenant_id=tenant_id,
            analysis_group_id=analysis_group_id,
            workflow_id=workflow_id,
        )

    async def get_rule_by_id(
        self, tenant_id: str, rule_id: str | UUID
    ) -> AlertRoutingRule | None:
        """Get alert routing rule by ID."""
        return await self.rule_repo.get_by_id(tenant_id=tenant_id, rule_id=rule_id)

    async def get_rule_by_group(
        self, tenant_id: str, analysis_group_id: str | UUID
    ) -> AlertRoutingRule | None:
        """Get alert routing rule by analysis group ID."""
        return await self.rule_repo.get_by_group_id(
            tenant_id=tenant_id, analysis_group_id=analysis_group_id
        )

    async def list_rules(self, tenant_id: str) -> list[AlertRoutingRule]:
        """List all alert routing rules for tenant."""
        return await self.rule_repo.list_all(tenant_id=tenant_id)

    async def delete_rule(self, tenant_id: str, rule_id: str | UUID) -> bool:
        """Delete an alert routing rule by ID. Returns True if deleted, False if not found."""
        return await self.rule_repo.delete(tenant_id=tenant_id, rule_id=rule_id)
