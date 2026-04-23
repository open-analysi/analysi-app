"""Integration tests for stuck workflow generation cleanup (Fix #3).

Tests that generations stuck in 'running' status beyond timeout threshold
are automatically marked as failed by the reconciliation job.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.kea_coordination import AnalysisGroup, WorkflowGeneration
from analysi.repositories.kea_coordination_repository import (
    WorkflowGenerationRepository,
)


@pytest.mark.asyncio
@pytest.mark.integration
class TestStuckGenerationCleanup:
    """Test stuck workflow generation cleanup."""

    @pytest.fixture
    async def test_analysis_group(
        self, integration_test_session: AsyncSession
    ) -> AnalysisGroup:
        """Create a test analysis group."""
        group = AnalysisGroup(
            tenant_id="test-tenant",
            title="Test Analysis Group",
        )
        integration_test_session.add(group)
        await integration_test_session.flush()
        await integration_test_session.commit()
        await integration_test_session.refresh(group)
        return group

    @pytest.fixture
    async def generation_repo(
        self, integration_test_session: AsyncSession
    ) -> WorkflowGenerationRepository:
        """Create workflow generation repository."""
        return WorkflowGenerationRepository(integration_test_session)

    @pytest.mark.asyncio
    async def test_find_stuck_generations_empty(
        self, generation_repo: WorkflowGenerationRepository
    ):
        """Test finding stuck generations when none exist."""
        stuck = await generation_repo.find_stuck_generations()
        assert stuck == []

    @pytest.mark.asyncio
    async def test_find_stuck_generations_recent_not_stuck(
        self,
        integration_test_session: AsyncSession,
        generation_repo: WorkflowGenerationRepository,
        test_analysis_group: AnalysisGroup,
    ):
        """Test that recent running generations are not considered stuck."""
        # Create a recent generation (1 minute ago)
        generation = WorkflowGeneration(
            tenant_id="test-tenant",
            analysis_group_id=test_analysis_group.id,
            status="running",
            is_active=True,
        )
        # Manually set created_at to 1 minute ago
        generation.created_at = datetime.now(UTC) - timedelta(minutes=1)

        integration_test_session.add(generation)
        await integration_test_session.commit()

        # Should not find it (default threshold is 35 minutes)
        stuck = await generation_repo.find_stuck_generations()
        assert len(stuck) == 0

    @pytest.mark.asyncio
    async def test_find_stuck_generations_old_is_stuck(
        self,
        integration_test_session: AsyncSession,
        generation_repo: WorkflowGenerationRepository,
        test_analysis_group: AnalysisGroup,
    ):
        """Test that old running generations are found as stuck."""
        # Create an old generation (70 minutes ago — exceeds 60-minute default threshold)
        generation = WorkflowGeneration(
            tenant_id="test-tenant",
            analysis_group_id=test_analysis_group.id,
            status="running",
            is_active=True,
        )
        generation.created_at = datetime.now(UTC) - timedelta(minutes=70)

        integration_test_session.add(generation)
        await integration_test_session.commit()

        # Should find it (default threshold is 60 minutes = 3600s)
        stuck = await generation_repo.find_stuck_generations()
        assert len(stuck) == 1
        assert stuck[0].id == generation.id

    @pytest.mark.asyncio
    async def test_find_stuck_generations_custom_threshold(
        self,
        integration_test_session: AsyncSession,
        generation_repo: WorkflowGenerationRepository,
        test_analysis_group: AnalysisGroup,
    ):
        """Test finding stuck generations with custom timeout threshold."""
        # Create a generation 10 minutes ago
        generation = WorkflowGeneration(
            tenant_id="test-tenant",
            analysis_group_id=test_analysis_group.id,
            status="running",
            is_active=True,
        )
        generation.created_at = datetime.now(UTC) - timedelta(minutes=10)

        integration_test_session.add(generation)
        await integration_test_session.commit()

        # Should not find it with default threshold (60 minutes)
        stuck = await generation_repo.find_stuck_generations()
        assert len(stuck) == 0

        # Should find it with custom threshold (5 minutes = 300 seconds)
        stuck = await generation_repo.find_stuck_generations(timeout_seconds=300)
        assert len(stuck) == 1
        assert stuck[0].id == generation.id

    @pytest.mark.asyncio
    async def test_find_stuck_generations_completed_not_stuck(
        self,
        integration_test_session: AsyncSession,
        generation_repo: WorkflowGenerationRepository,
        test_analysis_group: AnalysisGroup,
    ):
        """Test that completed generations are not considered stuck."""
        # Create an old completed generation
        generation = WorkflowGeneration(
            tenant_id="test-tenant",
            analysis_group_id=test_analysis_group.id,
            status="completed",  # Not running
            is_active=True,
        )
        generation.created_at = datetime.now(UTC) - timedelta(minutes=40)

        integration_test_session.add(generation)
        await integration_test_session.commit()

        # Should not find it (only finds status='running')
        stuck = await generation_repo.find_stuck_generations()
        assert len(stuck) == 0

    @pytest.mark.asyncio
    async def test_mark_as_failed_updates_status(
        self,
        integration_test_session: AsyncSession,
        generation_repo: WorkflowGenerationRepository,
        test_analysis_group: AnalysisGroup,
    ):
        """Test that mark_as_failed updates generation status and error details."""
        # Create a running generation
        generation = WorkflowGeneration(
            tenant_id="test-tenant",
            analysis_group_id=test_analysis_group.id,
            status="running",
            is_active=True,
        )
        integration_test_session.add(generation)
        await integration_test_session.commit()
        await integration_test_session.refresh(generation)

        assert generation.status == "running"
        assert generation.completed_at is None
        assert generation.orchestration_results is None

        # Mark as failed (atomic SQL UPDATE)
        error_message = "Test timeout error"
        was_marked = await generation_repo.mark_as_failed(generation, error_message)

        assert was_marked is True, (
            "Should return True when transitioning from running to failed"
        )

        # Verify updates (need to expire ORM cache since we used raw SQL UPDATE)
        await integration_test_session.refresh(generation)
        assert generation.status == "failed"
        assert generation.is_active is False, (
            "mark_as_failed must set is_active=False to prevent duplicate active "
            "generations when a new generation is created for the same group"
        )
        assert generation.completed_at is not None
        assert generation.orchestration_results is not None
        assert generation.orchestration_results["error"]["message"] == error_message
        assert generation.orchestration_results["error"]["type"] == "timeout"
        assert "timestamp" in generation.orchestration_results["error"]

    @pytest.mark.asyncio
    async def test_mark_as_failed_skips_already_completed_generation(
        self,
        integration_test_session: AsyncSession,
        generation_repo: WorkflowGenerationRepository,
        test_analysis_group: AnalysisGroup,
    ):
        """Test that mark_as_failed returns False for already-completed generations.

        This is the key race condition fix: if the job completed the generation
        between find_stuck_generations and mark_as_failed, the atomic WHERE
        status='running' clause prevents overwriting the completed status.
        """
        # Create a generation that's already completed
        generation = WorkflowGeneration(
            tenant_id="test-tenant",
            analysis_group_id=test_analysis_group.id,
            status="completed",
            is_active=False,
            completed_at=datetime.now(UTC),
            orchestration_results={"workflow_id": "wf-123"},
        )
        integration_test_session.add(generation)
        await integration_test_session.commit()
        await integration_test_session.refresh(generation)

        # Try to mark as failed — should be a no-op
        was_marked = await generation_repo.mark_as_failed(generation, "Timeout error")

        assert was_marked is False, (
            "Should return False when generation is already completed"
        )

        # Verify status was NOT changed
        await integration_test_session.refresh(generation)
        assert generation.status == "completed"
        assert generation.orchestration_results == {"workflow_id": "wf-123"}

    @pytest.mark.asyncio
    async def test_mark_as_failed_preserves_existing_results(
        self,
        integration_test_session: AsyncSession,
        generation_repo: WorkflowGenerationRepository,
        test_analysis_group: AnalysisGroup,
    ):
        """Test that mark_as_failed includes existing orchestration_results in error payload."""
        # Create a running generation with some results
        generation = WorkflowGeneration(
            tenant_id="test-tenant",
            analysis_group_id=test_analysis_group.id,
            status="running",
            is_active=True,
            orchestration_results={
                "runbook": "existing runbook content",
                "metrics": {"cost": 0.05},
            },
        )
        integration_test_session.add(generation)
        await integration_test_session.commit()
        await integration_test_session.refresh(generation)

        # Mark as failed
        was_marked = await generation_repo.mark_as_failed(generation, "Timeout error")
        assert was_marked is True

        # Verify error added while preserving existing data
        await integration_test_session.refresh(generation)
        assert generation.orchestration_results["runbook"] == "existing runbook content"
        assert generation.orchestration_results["metrics"]["cost"] == 0.05
        assert generation.orchestration_results["error"]["message"] == "Timeout error"

    @pytest.mark.asyncio
    async def test_find_stuck_across_multiple_tenants(
        self,
        integration_test_session: AsyncSession,
        generation_repo: WorkflowGenerationRepository,
        test_analysis_group: AnalysisGroup,
    ):
        """Test that find_stuck_generations finds generations across all tenants."""
        # Create stuck generations for different tenants (both exceed 60-minute threshold)
        generation1 = WorkflowGeneration(
            tenant_id="tenant-1",
            analysis_group_id=test_analysis_group.id,
            status="running",
        )
        generation1.created_at = datetime.now(UTC) - timedelta(minutes=70)

        generation2 = WorkflowGeneration(
            tenant_id="tenant-2",
            analysis_group_id=test_analysis_group.id,
            status="running",
        )
        generation2.created_at = datetime.now(UTC) - timedelta(minutes=90)

        integration_test_session.add_all([generation1, generation2])
        await integration_test_session.commit()

        # Should find both
        stuck = await generation_repo.find_stuck_generations()
        assert len(stuck) == 2
        tenant_ids = {g.tenant_id for g in stuck}
        assert tenant_ids == {"tenant-1", "tenant-2"}
