"""Unit tests for Kea Coordination repositories."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from analysi.repositories.kea_coordination_repository import (
    AlertRoutingRuleRepository,
    AnalysisGroupRepository,
    WorkflowGenerationRepository,
)


class TestAnalysisGroupRepository:
    """Test AnalysisGroupRepository methods."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def repo(self, mock_session):
        """Create AnalysisGroupRepository instance."""
        return AnalysisGroupRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_success(self, repo, mock_session):
        """Test successful analysis group creation."""
        # Arrange
        tenant_id = "test-tenant"
        title = "Suspicious Login Attempts"

        # Act
        group = await repo.create(tenant_id=tenant_id, title=title)

        # Assert
        assert group is not None
        assert group.tenant_id == tenant_id
        assert group.title == title
        # created_at is set by SQLAlchemy default, not tested in unit tests
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, repo, mock_session):
        """Test getting analysis group by ID when it exists."""
        # Arrange
        group_id = str(uuid4())
        tenant_id = "test-tenant"
        mock_group = MagicMock()
        mock_group.id = group_id
        mock_group.tenant_id = tenant_id

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_group)
        mock_session.execute.return_value = mock_result

        # Act
        result = await repo.get_by_id(tenant_id=tenant_id, group_id=group_id)

        # Assert
        assert result == mock_group
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, repo, mock_session):
        """Test getting analysis group by ID when it doesn't exist."""
        # Arrange
        group_id = str(uuid4())
        tenant_id = "test-tenant"

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        # Act
        result = await repo.get_by_id(tenant_id=tenant_id, group_id=group_id)

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_id_tenant_isolation(self, repo, mock_session):
        """Test that get_by_id respects tenant isolation."""
        # Arrange
        group_id = str(uuid4())
        tenant_id = "tenant-a"

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        # Act
        result = await repo.get_by_id(tenant_id=tenant_id, group_id=group_id)

        # Assert
        assert result is None
        # Verify SQL includes tenant_id filter
        call_args = mock_session.execute.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_get_by_title_found(self, repo, mock_session):
        """Test getting analysis group by title when it exists."""
        # Arrange
        tenant_id = "test-tenant"
        title = "Malware Detection"
        mock_group = MagicMock()
        mock_group.title = title

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_group)
        mock_session.execute.return_value = mock_result

        # Act
        result = await repo.get_by_title(tenant_id=tenant_id, title=title)

        # Assert
        assert result == mock_group

    @pytest.mark.asyncio
    async def test_get_by_title_not_found(self, repo, mock_session):
        """Test getting analysis group by title when it doesn't exist."""
        # Arrange
        tenant_id = "test-tenant"
        title = "Nonexistent Group"

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        # Act
        result = await repo.get_by_title(tenant_id=tenant_id, title=title)

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_list_all(self, repo, mock_session):
        """Test listing all analysis groups for a tenant."""
        # Arrange
        tenant_id = "test-tenant"
        mock_groups = [MagicMock(), MagicMock()]

        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=mock_groups))
        )
        mock_session.execute.return_value = mock_result

        # Act
        result = await repo.list_all(tenant_id=tenant_id)

        # Assert
        assert result == mock_groups
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_success(self, repo, mock_session):
        """Test successful deletion of analysis group."""
        # Arrange
        group_id = str(uuid4())
        tenant_id = "test-tenant"
        mock_group = MagicMock()

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_group)
        mock_session.execute.return_value = mock_result
        mock_session.delete = AsyncMock()

        # Act
        result = await repo.delete(tenant_id=tenant_id, group_id=group_id)

        # Assert
        assert result is True
        mock_session.delete.assert_called_once_with(mock_group)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, repo, mock_session):
        """Test deleting non-existent analysis group returns False."""
        # Arrange
        group_id = str(uuid4())
        tenant_id = "test-tenant"

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result
        mock_session.delete = AsyncMock()

        # Act
        result = await repo.delete(tenant_id=tenant_id, group_id=group_id)

        # Assert
        assert result is False
        mock_session.delete.assert_not_called()
        mock_session.flush.assert_not_called()


class TestWorkflowGenerationRepository:
    """Test WorkflowGenerationRepository methods."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def repo(self, mock_session):
        """Create WorkflowGenerationRepository instance."""
        return WorkflowGenerationRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_success(self, repo, mock_session):
        """Test successful workflow generation creation."""
        # Arrange
        tenant_id = "test-tenant"
        analysis_group_id = str(uuid4())

        # Act
        generation = await repo.create(
            tenant_id=tenant_id,
            analysis_group_id=analysis_group_id,
        )

        # Assert
        assert generation is not None
        assert generation.tenant_id == tenant_id
        assert generation.analysis_group_id == analysis_group_id
        assert generation.status == "running"
        assert generation.is_active is True
        assert generation.workflow_id is None
        assert generation.triggering_alert_analysis_id is None
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_with_triggering_alert(self, repo, mock_session):
        """Test workflow generation creation with triggering alert ID."""
        # Arrange
        tenant_id = "test-tenant"
        analysis_group_id = str(uuid4())
        triggering_alert_id = str(uuid4())

        # Act
        generation = await repo.create(
            tenant_id=tenant_id,
            analysis_group_id=analysis_group_id,
            triggering_alert_analysis_id=triggering_alert_id,
        )

        # Assert
        assert generation.triggering_alert_analysis_id == triggering_alert_id
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, repo, mock_session):
        """Test getting workflow generation by ID when it exists."""
        # Arrange
        gen_id = str(uuid4())
        tenant_id = "test-tenant"
        mock_generation = MagicMock()
        mock_generation.id = gen_id

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_generation)
        mock_session.execute.return_value = mock_result

        # Act
        result = await repo.get_by_id(tenant_id=tenant_id, generation_id=gen_id)

        # Assert
        assert result == mock_generation

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, repo, mock_session):
        """Test getting workflow generation by ID when it doesn't exist."""
        # Arrange
        gen_id = str(uuid4())
        tenant_id = "test-tenant"

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        # Act
        result = await repo.get_by_id(tenant_id=tenant_id, generation_id=gen_id)

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_get_active_for_group_found(self, repo, mock_session):
        """Test getting active generation for a group."""
        # Arrange
        tenant_id = "test-tenant"
        group_id = str(uuid4())
        mock_generation = MagicMock()
        mock_generation.is_active = True

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_generation)
        mock_session.execute.return_value = mock_result

        # Act
        result = await repo.get_active_for_group(
            tenant_id=tenant_id, analysis_group_id=group_id
        )

        # Assert
        assert result == mock_generation

    @pytest.mark.asyncio
    async def test_get_active_for_group_not_found(self, repo, mock_session):
        """Test getting active generation when none exists."""
        # Arrange
        tenant_id = "test-tenant"
        group_id = str(uuid4())

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        # Act
        result = await repo.get_active_for_group(
            tenant_id=tenant_id, analysis_group_id=group_id
        )

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_update_progress_initializes_all_phases(self, repo, mock_session):
        """Test that first progress update initializes all 4 phases."""
        # Arrange
        generation_id = str(uuid4())
        tenant_id = "test-tenant"

        mock_generation = MagicMock()
        mock_generation.current_phase = None  # Empty progress
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_generation)
        mock_session.execute.return_value = mock_result

        # Act
        updated = await repo.update_progress(
            tenant_id=tenant_id,
            generation_id=generation_id,
            stage="runbook_generation",
        )

        # Assert
        assert updated == mock_generation
        assert mock_generation.current_phase is not None
        phases = mock_generation.current_phase["phases"]
        assert len(phases) == 4  # All 4 phases initialized

        # First phase should be in_progress
        assert phases[0]["stage"] == "runbook_generation"
        assert phases[0]["status"] == "in_progress"
        assert phases[0]["started_at"] is not None

        # Other phases should be not_started
        assert phases[1]["stage"] == "task_proposals"
        assert phases[1]["status"] == "not_started"
        assert phases[2]["stage"] == "task_building"
        assert phases[2]["status"] == "not_started"
        assert phases[3]["stage"] == "workflow_assembly"
        assert phases[3]["status"] == "not_started"

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_progress_auto_completes_previous_stages(
        self, repo, mock_session
    ):
        """Test that marking a stage in_progress auto-completes previous stages."""
        # Arrange
        generation_id = str(uuid4())
        tenant_id = "test-tenant"

        # Existing progress with first phase in_progress
        mock_generation = MagicMock()
        mock_generation.current_phase = {
            "phases": [
                {
                    "stage": "runbook_generation",
                    "status": "in_progress",
                    "started_at": "2024-01-01T10:00:00+00:00",
                },
                {"stage": "task_proposals", "status": "not_started"},
                {"stage": "task_building", "status": "not_started"},
                {"stage": "workflow_assembly", "status": "not_started"},
            ]
        }

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_generation)
        mock_session.execute.return_value = mock_result

        # Act - mark task_proposals as in_progress
        updated = await repo.update_progress(
            tenant_id=tenant_id,
            generation_id=generation_id,
            stage="task_proposals",
        )

        # Assert
        assert updated == mock_generation
        phases = mock_generation.current_phase["phases"]

        # First phase should be auto-completed
        assert phases[0]["stage"] == "runbook_generation"
        assert phases[0]["status"] == "completed"
        assert phases[0]["completed_at"] is not None

        # Second phase should be in_progress
        assert phases[1]["stage"] == "task_proposals"
        assert phases[1]["status"] == "in_progress"
        assert phases[1]["started_at"] is not None

        # Later phases should still be not_started
        assert phases[2]["status"] == "not_started"
        assert phases[3]["status"] == "not_started"

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_progress_with_tasks_count(self, repo, mock_session):
        """Test updating progress with tasks_count for task_building stage."""
        # Arrange
        generation_id = str(uuid4())
        tenant_id = "test-tenant"

        mock_generation = MagicMock()
        mock_generation.current_phase = None
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_generation)
        mock_session.execute.return_value = mock_result

        # Act
        updated = await repo.update_progress(
            tenant_id=tenant_id,
            generation_id=generation_id,
            stage="task_building",
            tasks_count=5,
        )

        # Assert
        assert updated == mock_generation
        phases = mock_generation.current_phase["phases"]
        # task_building is at index 2
        assert phases[2]["stage"] == "task_building"
        assert phases[2]["tasks_count"] == 5
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_progress_not_found(self, repo, mock_session):
        """Test updating progress when generation doesn't exist."""
        # Arrange
        generation_id = str(uuid4())
        tenant_id = "test-tenant"

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        # Act
        updated = await repo.update_progress(
            tenant_id=tenant_id,
            generation_id=generation_id,
            stage="runbook_generation",
        )

        # Assert
        assert updated is None
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_progress_preserves_already_completed(
        self, repo, mock_session
    ):
        """Test that already-completed stages keep their timestamps."""
        # Arrange
        generation_id = str(uuid4())
        tenant_id = "test-tenant"
        # Use Z format since Pydantic serializes UTC as Z
        original_completed_at = "2024-01-01T11:00:00Z"

        mock_generation = MagicMock()
        mock_generation.current_phase = {
            "phases": [
                {
                    "stage": "runbook_generation",
                    "status": "completed",
                    "started_at": "2024-01-01T10:00:00Z",
                    "completed_at": original_completed_at,
                },
                {
                    "stage": "task_proposals",
                    "status": "in_progress",
                    "started_at": "2024-01-01T11:00:00Z",
                },
                {"stage": "task_building", "status": "not_started"},
                {"stage": "workflow_assembly", "status": "not_started"},
            ]
        }

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_generation)
        mock_session.execute.return_value = mock_result

        # Act - mark task_building as in_progress
        await repo.update_progress(
            tenant_id=tenant_id,
            generation_id=generation_id,
            stage="task_building",
        )

        # Assert
        phases = mock_generation.current_phase["phases"]

        # First phase should keep original completed_at
        assert phases[0]["completed_at"] == original_completed_at

        # Second phase should be auto-completed
        assert phases[1]["status"] == "completed"

        # Third phase should be in_progress
        assert phases[2]["status"] == "in_progress"

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_progress_skip_stages(self, repo, mock_session):
        """Test that skipping stages auto-completes all previous stages.

        Edge case: Jump from stage 1 directly to stage 3.
        """
        # Arrange
        generation_id = str(uuid4())
        tenant_id = "test-tenant"

        # Existing progress with first phase in_progress
        mock_generation = MagicMock()
        mock_generation.current_phase = {
            "phases": [
                {
                    "stage": "runbook_generation",
                    "status": "in_progress",
                    "started_at": "2024-01-01T10:00:00Z",
                },
                {"stage": "task_proposals", "status": "not_started"},
                {"stage": "task_building", "status": "not_started"},
                {"stage": "workflow_assembly", "status": "not_started"},
            ]
        }

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_generation)
        mock_session.execute.return_value = mock_result

        # Act - jump directly to task_building (stage 3), skipping task_proposals
        await repo.update_progress(
            tenant_id=tenant_id,
            generation_id=generation_id,
            stage="task_building",
        )

        # Assert - all previous stages should be completed
        phases = mock_generation.current_phase["phases"]
        assert phases[0]["status"] == "completed"  # runbook_generation
        assert phases[0]["completed_at"] is not None
        assert (
            phases[1]["status"] == "completed"
        )  # task_proposals (skipped but completed)
        assert phases[1]["completed_at"] is not None
        assert phases[2]["status"] == "in_progress"  # task_building
        assert phases[3]["status"] == "not_started"  # workflow_assembly

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_progress_same_stage_twice_idempotent(
        self, repo, mock_session
    ):
        """Test that calling the same stage twice is idempotent.

        Edge case: UI might retry, job might re-signal same stage.
        """
        # Arrange
        generation_id = str(uuid4())
        tenant_id = "test-tenant"
        original_started_at = "2024-01-01T10:00:00Z"

        mock_generation = MagicMock()
        mock_generation.current_phase = {
            "phases": [
                {
                    "stage": "runbook_generation",
                    "status": "in_progress",
                    "started_at": original_started_at,
                },
                {"stage": "task_proposals", "status": "not_started"},
                {"stage": "task_building", "status": "not_started"},
                {"stage": "workflow_assembly", "status": "not_started"},
            ]
        }

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_generation)
        mock_session.execute.return_value = mock_result

        # Act - call same stage again
        await repo.update_progress(
            tenant_id=tenant_id,
            generation_id=generation_id,
            stage="runbook_generation",
        )

        # Assert - should preserve original started_at, still in_progress
        phases = mock_generation.current_phase["phases"]
        assert phases[0]["status"] == "in_progress"
        assert phases[0]["started_at"] == original_started_at  # Not overwritten
        assert phases[1]["status"] == "not_started"

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_progress_go_backwards(self, repo, mock_session):
        """Test behavior when going backwards (stage 2 -> stage 1).

        Edge case: Unusual but should be handled gracefully.
        Going backwards sets the earlier stage to in_progress.
        """
        # Arrange
        generation_id = str(uuid4())
        tenant_id = "test-tenant"

        mock_generation = MagicMock()
        mock_generation.current_phase = {
            "phases": [
                {
                    "stage": "runbook_generation",
                    "status": "completed",
                    "started_at": "2024-01-01T10:00:00Z",
                    "completed_at": "2024-01-01T10:30:00Z",
                },
                {
                    "stage": "task_proposals",
                    "status": "in_progress",
                    "started_at": "2024-01-01T10:30:00Z",
                },
                {"stage": "task_building", "status": "not_started"},
                {"stage": "workflow_assembly", "status": "not_started"},
            ]
        }

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_generation)
        mock_session.execute.return_value = mock_result

        # Act - go backwards to runbook_generation
        await repo.update_progress(
            tenant_id=tenant_id,
            generation_id=generation_id,
            stage="runbook_generation",
        )

        # Assert - runbook_generation should be in_progress
        # The completed_at should be preserved since it was already completed
        phases = mock_generation.current_phase["phases"]
        assert phases[0]["status"] == "in_progress"
        # Later phases are not affected by going backwards
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_progress_final_stage(self, repo, mock_session):
        """Test progressing to the final stage (workflow_assembly).

        Edge case: All previous stages should be completed.
        """
        # Arrange
        generation_id = str(uuid4())
        tenant_id = "test-tenant"

        mock_generation = MagicMock()
        mock_generation.current_phase = {
            "phases": [
                {
                    "stage": "runbook_generation",
                    "status": "completed",
                    "started_at": "2024-01-01T10:00:00Z",
                    "completed_at": "2024-01-01T10:30:00Z",
                },
                {
                    "stage": "task_proposals",
                    "status": "completed",
                    "started_at": "2024-01-01T10:30:00Z",
                    "completed_at": "2024-01-01T11:00:00Z",
                },
                {
                    "stage": "task_building",
                    "status": "in_progress",
                    "started_at": "2024-01-01T11:00:00Z",
                },
                {"stage": "workflow_assembly", "status": "not_started"},
            ]
        }

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_generation)
        mock_session.execute.return_value = mock_result

        # Act - progress to final stage
        await repo.update_progress(
            tenant_id=tenant_id,
            generation_id=generation_id,
            stage="workflow_assembly",
        )

        # Assert - all previous completed, final in_progress
        phases = mock_generation.current_phase["phases"]
        assert phases[0]["status"] == "completed"
        assert phases[1]["status"] == "completed"
        assert phases[2]["status"] == "completed"  # task_building now completed
        assert phases[2]["completed_at"] is not None
        assert phases[3]["status"] == "in_progress"  # workflow_assembly
        assert phases[3]["started_at"] is not None

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_progress_workspace_path_only(self, repo, mock_session):
        """Test updating only workspace_path without changing stage.

        Edge case: Early workspace path update before first stage starts.
        """
        # Arrange
        generation_id = str(uuid4())
        tenant_id = "test-tenant"

        mock_generation = MagicMock()
        mock_generation.current_phase = None  # No progress yet
        mock_generation.workspace_path = "/tmp/unknown"

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_generation)
        mock_session.execute.return_value = mock_result

        # Act - update only workspace_path (stage=None)
        await repo.update_progress(
            tenant_id=tenant_id,
            generation_id=generation_id,
            stage=None,
            workspace_path="/tmp/kea-test-123",
        )

        # Assert - workspace_path updated, no phase changes
        assert mock_generation.workspace_path == "/tmp/kea-test-123"
        # current_phase should still be None since no stage was provided
        assert mock_generation.current_phase is None

        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_with_results(self, repo, mock_session):
        """Test updating generation with orchestration results (consolidated JSONB)."""
        # Arrange
        generation_id = str(uuid4())
        tenant_id = "test-tenant"
        workflow_id = str(uuid4())
        orchestration_results = {
            "runbook": "# Test Runbook",
            "task_proposals": [{"name": "Task 1"}],
            "tasks_built": [{"success": True}],
            "workflow_composition": ["task1", "task2"],
            "metrics": {"duration_ms": 5000},
        }

        mock_generation = MagicMock()
        mock_generation.current_phase = None  # No progress tracked yet
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_generation)
        mock_session.execute.return_value = mock_result

        # Act
        updated = await repo.update_with_results(
            tenant_id=tenant_id,
            generation_id=generation_id,
            workflow_id=workflow_id,
            status="completed",
            orchestration_results=orchestration_results,
        )

        # Assert
        assert updated == mock_generation
        assert mock_generation.workflow_id == workflow_id
        assert mock_generation.status == "completed"
        assert mock_generation.orchestration_results == orchestration_results
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_with_results_deactivates_on_completion(
        self, repo, mock_session
    ):
        """Test that generation is deactivated when status is 'completed'.

        Bug fix test: Ensures completed generations are not reused by get_active_for_group().
        """
        # Arrange
        generation_id = str(uuid4())
        tenant_id = "test-tenant"
        workflow_id = str(uuid4())

        mock_generation = MagicMock()
        mock_generation.is_active = True  # Initially active
        mock_generation.completed_at = None
        mock_generation.current_phase = None  # No progress tracked

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_generation)
        mock_session.execute.return_value = mock_result

        # Act
        updated = await repo.update_with_results(
            tenant_id=tenant_id,
            generation_id=generation_id,
            workflow_id=workflow_id,
            status="completed",
            orchestration_results={"test": "data"},
        )

        # Assert
        assert updated == mock_generation
        assert mock_generation.status == "completed"
        assert mock_generation.is_active is False  # Should be deactivated
        assert mock_generation.completed_at is not None
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_with_results_marks_all_phases_completed(
        self, repo, mock_session
    ):
        """Test that all phases are marked completed when status is 'completed'.

        When workflow generation completes successfully, all phases should be marked
        as completed so the UI shows a complete progress bar.
        """
        # Arrange
        generation_id = str(uuid4())
        tenant_id = "test-tenant"
        workflow_id = str(uuid4())

        mock_generation = MagicMock()
        mock_generation.is_active = True
        mock_generation.completed_at = None
        # Simulate progress with final phase still in_progress
        mock_generation.current_phase = {
            "phases": [
                {
                    "stage": "runbook_generation",
                    "status": "completed",
                    "started_at": "2024-01-01T10:00:00Z",
                    "completed_at": "2024-01-01T10:30:00Z",
                },
                {
                    "stage": "task_proposals",
                    "status": "completed",
                    "started_at": "2024-01-01T10:30:00Z",
                    "completed_at": "2024-01-01T11:00:00Z",
                },
                {
                    "stage": "task_building",
                    "status": "completed",
                    "started_at": "2024-01-01T11:00:00Z",
                    "completed_at": "2024-01-01T11:30:00Z",
                },
                {
                    "stage": "workflow_assembly",
                    "status": "in_progress",
                    "started_at": "2024-01-01T11:30:00Z",
                },
            ]
        }

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_generation)
        mock_session.execute.return_value = mock_result

        # Act
        updated = await repo.update_with_results(
            tenant_id=tenant_id,
            generation_id=generation_id,
            workflow_id=workflow_id,
            status="completed",
            orchestration_results={"test": "data"},
        )

        # Assert
        assert updated == mock_generation
        # All phases should now be completed
        phases = mock_generation.current_phase["phases"]
        assert all(phase["status"] == "completed" for phase in phases)
        # Final phase should have completed_at set
        assert phases[3]["completed_at"] is not None
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_with_results_marks_all_phases_completed_on_failure(
        self, repo, mock_session
    ):
        """Test that all phases are marked completed when status is 'failed'.

        Even on failure, we mark all phases as completed to show the workflow
        generation process has ended.
        """
        # Arrange
        generation_id = str(uuid4())
        tenant_id = "test-tenant"

        mock_generation = MagicMock()
        mock_generation.is_active = True
        mock_generation.completed_at = None
        # Simulate progress with task_building in_progress (failed mid-build)
        mock_generation.current_phase = {
            "phases": [
                {
                    "stage": "runbook_generation",
                    "status": "completed",
                    "started_at": "2024-01-01T10:00:00Z",
                    "completed_at": "2024-01-01T10:30:00Z",
                },
                {
                    "stage": "task_proposals",
                    "status": "completed",
                    "started_at": "2024-01-01T10:30:00Z",
                    "completed_at": "2024-01-01T11:00:00Z",
                },
                {
                    "stage": "task_building",
                    "status": "in_progress",
                    "started_at": "2024-01-01T11:00:00Z",
                },
                {"stage": "workflow_assembly", "status": "not_started"},
            ]
        }

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_generation)
        mock_session.execute.return_value = mock_result

        # Act
        updated = await repo.update_with_results(
            tenant_id=tenant_id,
            generation_id=generation_id,
            workflow_id=None,
            status="failed",
            orchestration_results={"error": {"message": "Build failed"}},
        )

        # Assert
        assert updated == mock_generation
        # All phases should now be completed (even though job failed)
        phases = mock_generation.current_phase["phases"]
        assert all(phase["status"] == "completed" for phase in phases)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_with_results_deactivates_on_failure(self, repo, mock_session):
        """Test that generation is deactivated when status is 'failed'.

        Bug fix test: This was the root cause of Dec 3rd issue where failed
        generations from Dec 2nd were reused instead of creating new ones.
        """
        # Arrange
        generation_id = str(uuid4())
        tenant_id = "test-tenant"

        mock_generation = MagicMock()
        mock_generation.is_active = True  # Initially active
        mock_generation.completed_at = None
        mock_generation.current_phase = None  # No progress tracked

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_generation)
        mock_session.execute.return_value = mock_result

        # Act
        updated = await repo.update_with_results(
            tenant_id=tenant_id,
            generation_id=generation_id,
            workflow_id=None,
            status="failed",
            orchestration_results={"error": {"message": "Test failure"}},
        )

        # Assert
        assert updated == mock_generation
        assert mock_generation.status == "failed"
        assert mock_generation.is_active is False  # Should be deactivated
        assert mock_generation.completed_at is not None
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_with_results_stays_active_when_running(
        self, repo, mock_session
    ):
        """Test that generation stays active when status is 'running'.

        Ensures progress updates don't accidentally deactivate running generations.
        """
        # Arrange
        generation_id = str(uuid4())
        tenant_id = "test-tenant"

        mock_generation = MagicMock()
        mock_generation.is_active = True
        mock_generation.completed_at = None

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_generation)
        mock_session.execute.return_value = mock_result

        # Act - update with running status
        updated = await repo.update_with_results(
            tenant_id=tenant_id,
            generation_id=generation_id,
            workflow_id=None,
            status="running",
            orchestration_results={"partial": "results"},
        )

        # Assert
        assert updated == mock_generation
        assert mock_generation.status == "running"
        assert mock_generation.is_active is True  # Should stay active
        assert mock_generation.completed_at is None  # Should NOT be set
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_deactivate_previous_generations(self, repo, mock_session):
        """Test deactivating previous generations for a group."""
        # Arrange
        tenant_id = "test-tenant"
        group_id = str(uuid4())
        mock_result = AsyncMock()
        mock_session.execute.return_value = mock_result

        # Act
        await repo.deactivate_previous_generations(
            tenant_id=tenant_id, analysis_group_id=group_id
        )

        # Assert
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_running_all_tenants(self, repo, mock_session):
        """Test counting running generations across all tenants."""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalar = MagicMock(return_value=3)
        mock_session.execute.return_value = mock_result

        # Act
        count = await repo.count_running()

        # Assert
        assert count == 3
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_running_specific_tenant(self, repo, mock_session):
        """Test counting running generations for specific tenant."""
        # Arrange
        tenant_id = "test-tenant"
        mock_result = AsyncMock()
        mock_result.scalar = MagicMock(return_value=2)
        mock_session.execute.return_value = mock_result

        # Act
        count = await repo.count_running(tenant_id=tenant_id)

        # Assert
        assert count == 2
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_running_returns_zero_when_none(self, repo, mock_session):
        """Test counting running generations when none exist."""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalar = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        # Act
        count = await repo.count_running()

        # Assert
        assert count == 0
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_generations_for_cleanup_returns_terminal_only(
        self, repo, mock_session
    ):
        """Test find_generations_for_cleanup returns only completed/failed generations."""
        # Arrange
        mock_generation_1 = MagicMock()
        mock_generation_1.id = str(uuid4())
        mock_generation_1.status = "completed"
        mock_generation_1.workspace_path = "/tmp/kea-test-123"

        mock_generation_2 = MagicMock()
        mock_generation_2.id = str(uuid4())
        mock_generation_2.status = "failed"
        mock_generation_2.workspace_path = "/tmp/kea-test-456"

        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(
            return_value=MagicMock(
                all=MagicMock(return_value=[mock_generation_1, mock_generation_2])
            )
        )
        mock_session.execute.return_value = mock_result

        # Act
        generations = await repo.find_generations_for_cleanup()

        # Assert
        assert len(generations) == 2
        assert generations[0] == mock_generation_1
        assert generations[1] == mock_generation_2
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_generations_for_cleanup_respects_status_filter(
        self, repo, mock_session
    ):
        """Test find_generations_for_cleanup respects custom status_filter parameter."""
        # Arrange
        mock_generation = MagicMock()
        mock_generation.id = str(uuid4())
        mock_generation.status = "completed"

        mock_result = AsyncMock()
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[mock_generation]))
        )
        mock_session.execute.return_value = mock_result

        # Act - filter for completed only
        generations = await repo.find_generations_for_cleanup(
            status_filter=["completed"]
        )

        # Assert
        assert len(generations) == 1
        assert generations[0] == mock_generation
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_success(self, repo, mock_session):
        """Test successful deletion of workflow generation."""
        # Arrange
        generation_id = str(uuid4())
        tenant_id = "test-tenant"
        mock_generation = MagicMock()

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_generation)
        mock_session.execute.return_value = mock_result
        mock_session.delete = AsyncMock()

        # Act
        result = await repo.delete(tenant_id=tenant_id, generation_id=generation_id)

        # Assert
        assert result is True
        mock_session.delete.assert_called_once_with(mock_generation)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, repo, mock_session):
        """Test deleting non-existent workflow generation returns False."""
        # Arrange
        generation_id = str(uuid4())
        tenant_id = "test-tenant"

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result
        mock_session.delete = AsyncMock()

        # Act
        result = await repo.delete(tenant_id=tenant_id, generation_id=generation_id)

        # Assert
        assert result is False
        mock_session.delete.assert_not_called()
        mock_session.flush.assert_not_called()


class TestAlertRoutingRuleRepository:
    """Test AlertRoutingRuleRepository methods."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def repo(self, mock_session):
        """Create AlertRoutingRuleRepository instance."""
        return AlertRoutingRuleRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_success(self, repo, mock_session):
        """Test successful alert routing rule creation."""
        # Arrange
        tenant_id = "test-tenant"
        group_id = str(uuid4())
        workflow_id = str(uuid4())

        # Act
        rule = await repo.create(
            tenant_id=tenant_id,
            analysis_group_id=group_id,
            workflow_id=workflow_id,
        )

        # Assert
        assert rule is not None
        assert rule.tenant_id == tenant_id
        assert rule.analysis_group_id == group_id
        assert rule.workflow_id == workflow_id
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_duplicate_raises_integrity_error(self, repo, mock_session):
        """Test that duplicate rules raise IntegrityError."""
        # Arrange
        tenant_id = "test-tenant"
        group_id = str(uuid4())
        workflow_id = str(uuid4())

        # Mock IntegrityError on flush
        mock_session.flush.side_effect = IntegrityError("duplicate", None, None)

        # Act & Assert
        with pytest.raises(IntegrityError):
            await repo.create(
                tenant_id=tenant_id,
                analysis_group_id=group_id,
                workflow_id=workflow_id,
            )

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, repo, mock_session):
        """Test getting alert routing rule by ID when it exists."""
        # Arrange
        rule_id = str(uuid4())
        tenant_id = "test-tenant"
        mock_rule = MagicMock()
        mock_rule.id = rule_id

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_rule)
        mock_session.execute.return_value = mock_result

        # Act
        result = await repo.get_by_id(tenant_id=tenant_id, rule_id=rule_id)

        # Assert
        assert result == mock_rule

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, repo, mock_session):
        """Test getting alert routing rule by ID when it doesn't exist."""
        # Arrange
        rule_id = str(uuid4())
        tenant_id = "test-tenant"

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        # Act
        result = await repo.get_by_id(tenant_id=tenant_id, rule_id=rule_id)

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_group_id_found(self, repo, mock_session):
        """Test getting rule by analysis group ID."""
        # Arrange
        tenant_id = "test-tenant"
        group_id = str(uuid4())
        mock_rule = MagicMock()

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_rule)
        mock_session.execute.return_value = mock_result

        # Act
        result = await repo.get_by_group_id(
            tenant_id=tenant_id, analysis_group_id=group_id
        )

        # Assert
        assert result == mock_rule

    @pytest.mark.asyncio
    async def test_get_by_group_id_not_found(self, repo, mock_session):
        """Test getting rule when none exists for group."""
        # Arrange
        tenant_id = "test-tenant"
        group_id = str(uuid4())

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        # Act
        result = await repo.get_by_group_id(
            tenant_id=tenant_id, analysis_group_id=group_id
        )

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_success(self, repo, mock_session):
        """Test successful deletion of alert routing rule."""
        # Arrange
        rule_id = str(uuid4())
        tenant_id = "test-tenant"
        mock_rule = MagicMock()

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_rule)
        mock_session.execute.return_value = mock_result
        mock_session.delete = AsyncMock()

        # Act
        result = await repo.delete(tenant_id=tenant_id, rule_id=rule_id)

        # Assert
        assert result is True
        mock_session.delete.assert_called_once_with(mock_rule)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, repo, mock_session):
        """Test deleting non-existent alert routing rule returns False."""
        # Arrange
        rule_id = str(uuid4())
        tenant_id = "test-tenant"

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result
        mock_session.delete = AsyncMock()

        # Act
        result = await repo.delete(tenant_id=tenant_id, rule_id=rule_id)

        # Assert
        assert result is False
        mock_session.delete.assert_not_called()
        mock_session.flush.assert_not_called()
