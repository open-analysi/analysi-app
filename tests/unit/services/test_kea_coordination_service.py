"""Unit tests for Kea Coordination services."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from analysi.services.kea_coordination_service import (
    AlertRoutingRuleService,
    AnalysisGroupService,
    WorkflowGenerationService,
)


class TestRoutingRulePriority:
    """
    Tests for routing rule priority over workflow_generations.

    BUG REPRODUCTION: When a user updates an alert_routing_rule to point to a
    different workflow, re-analyzing alerts should use the routing rule's workflow,
    not the cached workflow_id in workflow_generations.

    The routing rule is the authoritative source for workflow mapping.
    """

    @pytest.fixture
    def mock_repos(self):
        """Create mock repositories including rule_repo."""
        group_repo = AsyncMock()
        generation_repo = AsyncMock()
        rule_repo = AsyncMock()
        return group_repo, generation_repo, rule_repo

    @pytest.fixture
    def service(self, mock_repos):
        """Create AnalysisGroupService with all repositories."""
        group_repo, generation_repo, rule_repo = mock_repos
        return AnalysisGroupService(group_repo, generation_repo, rule_repo)

    @pytest.mark.asyncio
    async def test_routing_rule_takes_priority_over_workflow_generation(
        self, service, mock_repos
    ):
        """
        Test that routing rule workflow_id takes priority over workflow_generations.

        Scenario:
        - workflow_generations.workflow_id = "old-workflow-123"
        - alert_routing_rules.workflow_id = "new-workflow-456"
        - Expected: Return "new-workflow-456" (routing rule wins)
        """
        group_repo, generation_repo, rule_repo = mock_repos
        tenant_id = "test-tenant"
        title = "ProxyNotShell CVE-2022-41082"
        group_id = str(uuid4())
        old_workflow_id = str(uuid4())  # In workflow_generations
        new_workflow_id = str(uuid4())  # In routing rule (user updated)

        # Setup: existing group
        existing_group = MagicMock()
        existing_group.id = group_id
        existing_group.title = title
        group_repo.get_by_title.return_value = existing_group

        # Setup: no active generation (completed)
        generation_repo.get_active_for_group.return_value = None

        # Setup: completed generation with OLD workflow
        old_generation = MagicMock()
        old_generation.id = str(uuid4())
        old_generation.workflow_id = old_workflow_id
        old_generation.status = "completed"
        generation_repo.get_latest_for_group.return_value = old_generation

        # Setup: routing rule points to NEW workflow (user updated it)
        routing_rule = MagicMock()
        routing_rule.workflow_id = new_workflow_id
        routing_rule.analysis_group_id = group_id
        rule_repo.get_by_group_id.return_value = routing_rule

        # Act
        result_group, result_gen = await service.create_group_with_generation(
            tenant_id=tenant_id, title=title
        )

        # Assert: routing rule workflow should be used
        assert result_group == existing_group
        assert result_gen.workflow_id == new_workflow_id, (
            f"Expected routing rule workflow {new_workflow_id}, "
            f"got {result_gen.workflow_id}"
        )

    @pytest.mark.asyncio
    async def test_falls_back_to_generation_when_no_routing_rule(
        self, service, mock_repos
    ):
        """
        Test fallback to workflow_generations when no routing rule exists.

        This maintains backward compatibility for groups that have a completed
        generation but haven't had a routing rule created yet (edge case).
        """
        group_repo, generation_repo, rule_repo = mock_repos
        tenant_id = "test-tenant"
        title = "Legacy Alert Type"
        group_id = str(uuid4())
        workflow_id = str(uuid4())

        # Setup: existing group
        existing_group = MagicMock()
        existing_group.id = group_id
        group_repo.get_by_title.return_value = existing_group

        # Setup: no active generation
        generation_repo.get_active_for_group.return_value = None

        # Setup: completed generation with workflow
        completed_generation = MagicMock()
        completed_generation.id = str(uuid4())
        completed_generation.workflow_id = workflow_id
        generation_repo.get_latest_for_group.return_value = completed_generation

        # Setup: NO routing rule (legacy case)
        rule_repo.get_by_group_id.return_value = None

        # Act
        result_group, result_gen = await service.create_group_with_generation(
            tenant_id=tenant_id, title=title
        )

        # Assert: should fall back to workflow_generations
        assert result_group == existing_group
        assert result_gen.workflow_id == workflow_id

    @pytest.mark.asyncio
    async def test_creates_new_generation_when_no_routing_rule_and_no_completed_generation(
        self, service, mock_repos
    ):
        """
        Test that new generation is created when neither routing rule nor
        completed generation exists.
        """
        group_repo, generation_repo, rule_repo = mock_repos
        tenant_id = "test-tenant"
        title = "Brand New Alert Type"
        group_id = str(uuid4())

        # Setup: existing group
        existing_group = MagicMock()
        existing_group.id = group_id
        group_repo.get_by_title.return_value = existing_group

        # Setup: no active generation
        generation_repo.get_active_for_group.return_value = None

        # Setup: no completed generation
        generation_repo.get_latest_for_group.return_value = None

        # Setup: no routing rule
        rule_repo.get_by_group_id.return_value = None

        # Setup: no generation has a workflow
        generation_repo.get_generation_with_workflow_for_group.return_value = None

        # Setup: new generation will be created
        new_generation = MagicMock()
        new_generation.id = str(uuid4())
        new_generation.workflow_id = None  # Not yet completed
        generation_repo.create.return_value = new_generation

        # Act
        result_group, result_gen = await service.create_group_with_generation(
            tenant_id=tenant_id, title=title
        )

        # Assert: new generation should be created
        assert result_group == existing_group
        assert result_gen == new_generation
        generation_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_routing_rule_checked_before_fallback_to_generation_workflow(
        self, service, mock_repos
    ):
        """
        Test that routing rule is checked and its workflow_id is used.

        The implementation still fetches the generation object (as a container),
        but overrides its workflow_id with the routing rule's value.
        """
        group_repo, generation_repo, rule_repo = mock_repos
        tenant_id = "test-tenant"
        title = "Priority Check"
        group_id = str(uuid4())
        old_workflow_id = str(uuid4())
        routing_workflow_id = str(uuid4())

        # Setup: existing group
        existing_group = MagicMock()
        existing_group.id = group_id
        group_repo.get_by_title.return_value = existing_group

        # Setup: no active generation
        generation_repo.get_active_for_group.return_value = None

        # Setup: routing rule exists with different workflow
        routing_rule = MagicMock()
        routing_rule.workflow_id = routing_workflow_id
        rule_repo.get_by_group_id.return_value = routing_rule

        # Setup: latest generation has old workflow
        old_generation = MagicMock()
        old_generation.id = str(uuid4())
        old_generation.workflow_id = old_workflow_id
        generation_repo.get_latest_for_group.return_value = old_generation

        # Act
        result_group, result_gen = await service.create_group_with_generation(
            tenant_id=tenant_id, title=title
        )

        # Assert: routing rule was checked
        rule_repo.get_by_group_id.assert_called_once_with(
            tenant_id=tenant_id, analysis_group_id=group_id
        )
        # Assert: routing rule's workflow_id is used (not the generation's old value)
        assert result_gen.workflow_id == routing_workflow_id


class TestAnalysisGroupService:
    """Test AnalysisGroupService methods."""

    @pytest.fixture
    def mock_repos(self):
        """Create mock repositories."""
        group_repo = AsyncMock()
        generation_repo = AsyncMock()
        return group_repo, generation_repo

    @pytest.fixture
    def service(self, mock_repos):
        """Create AnalysisGroupService instance."""
        group_repo, generation_repo = mock_repos
        return AnalysisGroupService(group_repo, generation_repo)

    @pytest.mark.asyncio
    async def test_create_group_success(self, service, mock_repos):
        """Test successful analysis group creation."""
        # Arrange
        group_repo, _ = mock_repos
        tenant_id = "test-tenant"
        title = "Suspicious Login Attempts"

        mock_group = MagicMock()
        mock_group.id = str(uuid4())
        mock_group.tenant_id = tenant_id
        mock_group.title = title

        group_repo.create.return_value = mock_group

        # Act
        result = await service.create_group(tenant_id=tenant_id, title=title)

        # Assert
        assert result == mock_group
        group_repo.create.assert_called_once_with(tenant_id=tenant_id, title=title)

    @pytest.mark.asyncio
    async def test_create_group_duplicate_raises_conflict(self, service, mock_repos):
        """Test that duplicate group title raises IntegrityError."""
        # Arrange
        group_repo, _ = mock_repos
        tenant_id = "test-tenant"
        title = "Malware Detection"

        group_repo.create.side_effect = IntegrityError("duplicate", None, None)

        # Act & Assert
        with pytest.raises(IntegrityError):
            await service.create_group(tenant_id=tenant_id, title=title)

    @pytest.mark.asyncio
    async def test_get_group_by_id(self, service, mock_repos):
        """Test getting group by ID."""
        # Arrange
        group_repo, _ = mock_repos
        tenant_id = "test-tenant"
        group_id = str(uuid4())

        mock_group = MagicMock()
        group_repo.get_by_id.return_value = mock_group

        # Act
        result = await service.get_group_by_id(tenant_id=tenant_id, group_id=group_id)

        # Assert
        assert result == mock_group
        group_repo.get_by_id.assert_called_once_with(
            tenant_id=tenant_id, group_id=group_id
        )

    @pytest.mark.asyncio
    async def test_get_group_by_title(self, service, mock_repos):
        """Test getting group by title."""
        # Arrange
        group_repo, _ = mock_repos
        tenant_id = "test-tenant"
        title = "Suspicious Login Attempts"

        mock_group = MagicMock()
        mock_group.title = title
        group_repo.get_by_title.return_value = mock_group

        # Act
        result = await service.get_group_by_title(tenant_id=tenant_id, title=title)

        # Assert
        assert result == mock_group
        group_repo.get_by_title.assert_called_once_with(
            tenant_id=tenant_id, title=title
        )

    @pytest.mark.asyncio
    async def test_get_group_by_title_not_found(self, service, mock_repos):
        """Test getting group by title when not found returns None."""
        # Arrange
        group_repo, _ = mock_repos
        tenant_id = "test-tenant"
        title = "Non-existent Group"

        group_repo.get_by_title.return_value = None

        # Act
        result = await service.get_group_by_title(tenant_id=tenant_id, title=title)

        # Assert
        assert result is None
        group_repo.get_by_title.assert_called_once_with(
            tenant_id=tenant_id, title=title
        )

    @pytest.mark.asyncio
    async def test_list_groups(self, service, mock_repos):
        """Test listing all groups for tenant."""
        # Arrange
        group_repo, _ = mock_repos
        tenant_id = "test-tenant"

        mock_groups = [MagicMock(), MagicMock()]
        group_repo.list_all.return_value = mock_groups

        # Act
        result = await service.list_groups(tenant_id=tenant_id)

        # Assert
        assert result == mock_groups
        group_repo.list_all.assert_called_once_with(tenant_id=tenant_id)

    @pytest.mark.asyncio
    async def test_delete_group_success(self, service, mock_repos):
        """Test successful deletion of analysis group."""
        # Arrange
        group_repo, _ = mock_repos
        tenant_id = "test-tenant"
        group_id = str(uuid4())

        group_repo.delete.return_value = True

        # Act
        result = await service.delete_group(tenant_id=tenant_id, group_id=group_id)

        # Assert
        assert result is True
        group_repo.delete.assert_called_once_with(
            tenant_id=tenant_id, group_id=group_id
        )

    @pytest.mark.asyncio
    async def test_delete_group_not_found(self, service, mock_repos):
        """Test deleting non-existent analysis group returns False."""
        # Arrange
        group_repo, _ = mock_repos
        tenant_id = "test-tenant"
        group_id = str(uuid4())

        group_repo.delete.return_value = False

        # Act
        result = await service.delete_group(tenant_id=tenant_id, group_id=group_id)

        # Assert
        assert result is False
        group_repo.delete.assert_called_once_with(
            tenant_id=tenant_id, group_id=group_id
        )

    @pytest.mark.asyncio
    async def test_create_group_with_generation_success(self, service, mock_repos):
        """Test atomic creation of group + generation (happy path)."""
        # Arrange
        group_repo, generation_repo = mock_repos
        tenant_id = "test-tenant"
        title = "Lateral Movement Detection"

        mock_group = MagicMock()
        mock_group.id = str(uuid4())
        mock_generation = MagicMock()

        group_repo.get_by_title.return_value = None  # Not found
        group_repo.create.return_value = mock_group
        generation_repo.get_active_for_group.return_value = None  # No active gen
        generation_repo.get_latest_for_group.return_value = (
            None  # No completed gen with workflow
        )
        generation_repo.get_generation_with_workflow_for_group.return_value = None
        generation_repo.create.return_value = mock_generation

        # Act
        result_group, result_gen = await service.create_group_with_generation(
            tenant_id=tenant_id, title=title
        )

        # Assert
        assert result_group == mock_group
        assert result_gen == mock_generation
        group_repo.create.assert_called_once()
        generation_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_group_with_generation_race_condition(
        self, service, mock_repos
    ):
        """Test atomic creation handles race condition (another worker created first)."""
        # Arrange
        group_repo, generation_repo = mock_repos
        tenant_id = "test-tenant"
        title = "Brute Force Attempts"

        # First check: not found
        # Second check (after IntegrityError): found
        existing_group = MagicMock()
        existing_group.id = str(uuid4())
        existing_generation = MagicMock()

        group_repo.get_by_title.side_effect = [None, existing_group]
        group_repo.create.side_effect = IntegrityError("duplicate", None, None)
        generation_repo.get_active_for_group.return_value = existing_generation

        # Act
        result_group, result_gen = await service.create_group_with_generation(
            tenant_id=tenant_id, title=title
        )

        # Assert - should return existing group+generation
        assert result_group == existing_group
        assert result_gen == existing_generation
        # Verify fallback lookup was called
        assert group_repo.get_by_title.call_count == 2

    @pytest.mark.asyncio
    async def test_create_group_with_generation_existing_group_no_generation(
        self, service, mock_repos
    ):
        """Test creating generation for existing group."""
        # Arrange
        group_repo, generation_repo = mock_repos
        tenant_id = "test-tenant"
        title = "Existing Group"

        existing_group = MagicMock()
        existing_group.id = str(uuid4())
        mock_generation = MagicMock()

        group_repo.get_by_title.return_value = existing_group  # Already exists
        generation_repo.get_active_for_group.return_value = None  # No active gen
        generation_repo.get_latest_for_group.return_value = (
            None  # No completed gen with workflow
        )
        generation_repo.get_generation_with_workflow_for_group.return_value = None
        generation_repo.create.return_value = mock_generation

        # Act
        result_group, result_gen = await service.create_group_with_generation(
            tenant_id=tenant_id, title=title
        )

        # Assert
        assert result_group == existing_group
        assert result_gen == mock_generation
        group_repo.create.assert_not_called()  # Should not create new group
        generation_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_group_with_generation_both_exist(self, service, mock_repos):
        """Test when both group and generation already exist."""
        # Arrange
        group_repo, generation_repo = mock_repos
        tenant_id = "test-tenant"
        title = "Fully Configured"

        existing_group = MagicMock()
        existing_group.id = str(uuid4())
        existing_generation = MagicMock()

        group_repo.get_by_title.return_value = existing_group
        generation_repo.get_active_for_group.return_value = existing_generation

        # Act
        result_group, result_gen = await service.create_group_with_generation(
            tenant_id=tenant_id, title=title
        )

        # Assert - should return existing
        assert result_group == existing_group
        assert result_gen == existing_generation
        group_repo.create.assert_not_called()
        generation_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_group_reuses_workflow_from_previous_generation(
        self, service, mock_repos
    ):
        """Test that a previous generation's workflow is reused when latest has none.

        Scenario: G1 created workflow W1 then G2 failed (no workflow_id).
        get_latest_for_group returns G2 (no workflow), but
        get_generation_with_workflow_for_group returns G1 (has workflow).
        Should return G1 instead of creating G3.
        """
        group_repo, generation_repo = mock_repos
        tenant_id = "test-tenant"
        title = "LFI Attack Analysis"
        group_id = str(uuid4())
        workflow_id = str(uuid4())

        # Setup: existing group
        existing_group = MagicMock()
        existing_group.id = group_id
        group_repo.get_by_title.return_value = existing_group

        # No active generation
        generation_repo.get_active_for_group.return_value = None

        # Latest generation is a failed retry with no workflow_id
        failed_gen = MagicMock()
        failed_gen.id = str(uuid4())
        failed_gen.workflow_id = None
        failed_gen.status = "failed"
        generation_repo.get_latest_for_group.return_value = failed_gen

        # But a previous generation has a workflow_id
        gen_with_workflow = MagicMock()
        gen_with_workflow.id = str(uuid4())
        gen_with_workflow.workflow_id = workflow_id
        gen_with_workflow.status = "completed"
        generation_repo.get_generation_with_workflow_for_group.return_value = (
            gen_with_workflow
        )

        # Act
        result_group, result_gen = await service.create_group_with_generation(
            tenant_id=tenant_id, title=title
        )

        # Assert: reuses previous generation with workflow, no new creation
        assert result_group == existing_group
        assert result_gen == gen_with_workflow
        assert result_gen.workflow_id == workflow_id
        generation_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_group_creates_new_when_no_generation_has_workflow(
        self, service, mock_repos
    ):
        """Test new generation is created when no generation has a workflow_id.

        Scenario: G1 and G2 both failed without creating a workflow.
        get_latest_for_group returns G2 (no workflow),
        get_generation_with_workflow_for_group returns None.
        Should create G3.
        """
        group_repo, generation_repo = mock_repos
        tenant_id = "test-tenant"
        title = "LFI Attack Analysis"
        group_id = str(uuid4())

        # Setup: existing group
        existing_group = MagicMock()
        existing_group.id = group_id
        group_repo.get_by_title.return_value = existing_group

        # No active generation
        generation_repo.get_active_for_group.return_value = None

        # Latest generation failed, no workflow
        failed_gen = MagicMock()
        failed_gen.id = str(uuid4())
        failed_gen.workflow_id = None
        failed_gen.status = "failed"
        generation_repo.get_latest_for_group.return_value = failed_gen

        # No generation has a workflow
        generation_repo.get_generation_with_workflow_for_group.return_value = None

        # New generation will be created
        new_gen = MagicMock()
        new_gen.id = str(uuid4())
        new_gen.workflow_id = None
        generation_repo.create.return_value = new_gen

        # Act
        result_group, result_gen = await service.create_group_with_generation(
            tenant_id=tenant_id, title=title
        )

        # Assert: creates new generation
        assert result_group == existing_group
        assert result_gen == new_gen
        generation_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_group_with_generation_race_condition_failure(
        self, service, mock_repos
    ):
        """Test race condition where fallback lookup also fails (edge case)."""
        # Arrange
        group_repo, generation_repo = mock_repos
        tenant_id = "test-tenant"
        title = "Impossible Race"

        # First check: not found
        # Creation fails with IntegrityError
        # Second check: still not found (impossible in practice but tests error path)
        group_repo.get_by_title.side_effect = [None, None]
        group_repo.create.side_effect = IntegrityError("duplicate", None, None)

        # Act & Assert
        with pytest.raises(RuntimeError) as exc_info:
            await service.create_group_with_generation(tenant_id=tenant_id, title=title)

        assert "Failed to find or create analysis group" in str(exc_info.value)
        assert title in str(exc_info.value)
        assert tenant_id in str(exc_info.value)


class TestWorkflowGenerationService:
    """Test WorkflowGenerationService methods."""

    @pytest.fixture
    def mock_repos(self):
        """Create mock repositories."""
        generation_repo = AsyncMock()
        return generation_repo

    @pytest.fixture
    def service(self, mock_repos):
        """Create WorkflowGenerationService instance."""
        return WorkflowGenerationService(mock_repos)

    @pytest.mark.asyncio
    async def test_get_generation_by_id(self, service, mock_repos):
        """Test getting generation by ID."""
        # Arrange
        tenant_id = "test-tenant"
        gen_id = str(uuid4())

        mock_generation = MagicMock()
        mock_repos.get_by_id.return_value = mock_generation

        # Act
        result = await service.get_generation_by_id(
            tenant_id=tenant_id, generation_id=gen_id
        )

        # Assert
        assert result == mock_generation
        mock_repos.get_by_id.assert_called_once_with(
            tenant_id=tenant_id, generation_id=gen_id
        )

    @pytest.mark.asyncio
    async def test_get_latest_generation_for_group(self, service, mock_repos):
        """Test getting latest generation for a group (used by reconciliation)."""
        # Arrange
        tenant_id = "test-tenant"
        group_id = str(uuid4())

        mock_generation = MagicMock()
        mock_generation.status = "failed"
        mock_generation.is_active = False
        mock_repos.get_latest_for_group.return_value = mock_generation

        # Act
        result = await service.get_latest_generation_for_group(
            tenant_id=tenant_id, analysis_group_id=group_id
        )

        # Assert
        assert result == mock_generation
        mock_repos.get_latest_for_group.assert_called_once_with(
            tenant_id=tenant_id, analysis_group_id=group_id
        )

    @pytest.mark.asyncio
    async def test_get_latest_generation_for_group_not_found(self, service, mock_repos):
        """Test getting latest generation when none exist."""
        # Arrange
        tenant_id = "test-tenant"
        group_id = str(uuid4())

        mock_repos.get_latest_for_group.return_value = None

        # Act
        result = await service.get_latest_generation_for_group(
            tenant_id=tenant_id, analysis_group_id=group_id
        )

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_list_generations(self, service, mock_repos):
        """Test listing all generations for tenant."""
        # Arrange
        tenant_id = "test-tenant"

        mock_generations = [MagicMock(), MagicMock()]
        mock_repos.list_all.return_value = mock_generations

        # Act
        result = await service.list_generations(tenant_id=tenant_id)

        # Assert
        assert result == mock_generations
        mock_repos.list_all.assert_called_once_with(
            tenant_id=tenant_id, triggering_alert_analysis_id=None
        )

    @pytest.mark.asyncio
    async def test_list_generations_with_alert_filter(self, service, mock_repos):
        """Test listing generations filtered by triggering alert analysis."""
        # Arrange
        tenant_id = "test-tenant"
        alert_analysis_id = str(uuid4())

        mock_generations = [MagicMock()]
        mock_repos.list_all.return_value = mock_generations

        # Act
        result = await service.list_generations(
            tenant_id=tenant_id, triggering_alert_analysis_id=alert_analysis_id
        )

        # Assert
        assert result == mock_generations
        mock_repos.list_all.assert_called_once_with(
            tenant_id=tenant_id, triggering_alert_analysis_id=alert_analysis_id
        )

    @pytest.mark.asyncio
    async def test_mark_stage_completed(self, service, mock_repos):
        """Test marking a specific stage as completed."""
        # Arrange
        tenant_id = "test-tenant"
        gen_id = str(uuid4())
        stage = "runbook_generation"

        mock_generation = MagicMock()
        mock_repos.mark_stage_completed.return_value = mock_generation

        # Act
        result = await service.mark_stage_completed(
            tenant_id=tenant_id, generation_id=gen_id, stage=stage
        )

        # Assert
        assert result == mock_generation
        mock_repos.mark_stage_completed.assert_called_once_with(
            tenant_id=tenant_id, generation_id=gen_id, stage=stage
        )

    @pytest.mark.asyncio
    async def test_mark_stage_completed_not_found(self, service, mock_repos):
        """Test marking stage on non-existent generation returns None."""
        # Arrange
        tenant_id = "test-tenant"
        gen_id = str(uuid4())
        stage = "task_building"

        mock_repos.mark_stage_completed.return_value = None

        # Act
        result = await service.mark_stage_completed(
            tenant_id=tenant_id, generation_id=gen_id, stage=stage
        )

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_update_generation_progress(self, service, mock_repos):
        """Test updating generation progress with stage name."""
        # Arrange
        tenant_id = "test-tenant"
        gen_id = str(uuid4())
        stage = "workflow_assembly"

        mock_generation = MagicMock()
        mock_repos.update_progress.return_value = mock_generation

        # Act
        result = await service.update_generation_progress(
            tenant_id=tenant_id,
            generation_id=gen_id,
            stage=stage,
        )

        # Assert
        assert result == mock_generation
        mock_repos.update_progress.assert_called_once_with(
            tenant_id=tenant_id,
            generation_id=gen_id,
            stage=stage,
            tasks_count=None,
            workspace_path=None,
        )

    @pytest.mark.asyncio
    async def test_update_generation_progress_with_tasks_count(
        self, service, mock_repos
    ):
        """Test updating progress with tasks_count for task_building stage."""
        # Arrange
        tenant_id = "test-tenant"
        gen_id = str(uuid4())
        stage = "task_building"
        tasks_count = 5

        mock_generation = MagicMock()
        mock_repos.update_progress.return_value = mock_generation

        # Act
        result = await service.update_generation_progress(
            tenant_id=tenant_id,
            generation_id=gen_id,
            stage=stage,
            tasks_count=tasks_count,
        )

        # Assert
        assert result == mock_generation
        mock_repos.update_progress.assert_called_once_with(
            tenant_id=tenant_id,
            generation_id=gen_id,
            stage=stage,
            tasks_count=tasks_count,
            workspace_path=None,
        )

    @pytest.mark.asyncio
    async def test_update_generation_progress_workspace_only(self, service, mock_repos):
        """Test updating progress with only workspace_path (no stage)."""
        # Arrange
        tenant_id = "test-tenant"
        gen_id = str(uuid4())
        workspace_path = "/tmp/kea-test-123"

        mock_generation = MagicMock()
        mock_repos.update_progress.return_value = mock_generation

        # Act
        result = await service.update_generation_progress(
            tenant_id=tenant_id,
            generation_id=gen_id,
            stage=None,  # No stage
            workspace_path=workspace_path,
        )

        # Assert
        assert result == mock_generation
        mock_repos.update_progress.assert_called_once_with(
            tenant_id=tenant_id,
            generation_id=gen_id,
            stage=None,
            tasks_count=None,
            workspace_path=workspace_path,
        )

    @pytest.mark.asyncio
    async def test_update_generation_progress_workspace_and_stage(
        self, service, mock_repos
    ):
        """Test updating progress with both workspace_path and stage."""
        # Arrange
        tenant_id = "test-tenant"
        gen_id = str(uuid4())
        workspace_path = "/tmp/kea-test-456"
        stage = "task_building"
        tasks_count = 3

        mock_generation = MagicMock()
        mock_repos.update_progress.return_value = mock_generation

        # Act
        result = await service.update_generation_progress(
            tenant_id=tenant_id,
            generation_id=gen_id,
            stage=stage,
            tasks_count=tasks_count,
            workspace_path=workspace_path,
        )

        # Assert
        assert result == mock_generation
        mock_repos.update_progress.assert_called_once_with(
            tenant_id=tenant_id,
            generation_id=gen_id,
            stage=stage,
            tasks_count=tasks_count,
            workspace_path=workspace_path,
        )

    @pytest.mark.asyncio
    async def test_update_generation_results_success(self, service, mock_repos):
        """Test updating generation with orchestration results (consolidated JSONB)."""
        # Arrange
        tenant_id = "test-tenant"
        gen_id = str(uuid4())
        workflow_id = str(uuid4())

        orchestration_results = {
            "runbook": "# Test Runbook",
            "task_proposals": [{"name": "Task 1"}],
            "tasks_built": [{"success": True, "cy_name": "task1"}],
            "workflow_composition": ["task1", "task2"],
            "metrics": {"duration_ms": 5000},
        }

        mock_updated = MagicMock()
        mock_repos.update_with_results.return_value = mock_updated

        # Act
        result = await service.update_generation_results(
            tenant_id=tenant_id,
            generation_id=gen_id,
            workflow_id=workflow_id,
            status="completed",
            orchestration_results=orchestration_results,
        )

        # Assert
        assert result == mock_updated
        mock_repos.update_with_results.assert_called_once_with(
            tenant_id=tenant_id,
            generation_id=gen_id,
            workflow_id=workflow_id,
            status="completed",
            orchestration_results=orchestration_results,
            workspace_path=None,
        )

    @pytest.mark.asyncio
    async def test_update_generation_results_with_error(self, service, mock_repos):
        """Test updating generation with error status (error in orchestration_results)."""
        # Arrange
        tenant_id = "test-tenant"
        gen_id = str(uuid4())

        orchestration_results = {
            "error": {
                "message": "Failed to generate runbook",
                "type": "RuntimeError",
                "timestamp": "2025-12-01T12:00:00Z",
            },
            "metrics": {"duration_ms": 1000},
        }

        mock_updated = MagicMock()
        mock_repos.update_with_results.return_value = mock_updated

        # Act
        result = await service.update_generation_results(
            tenant_id=tenant_id,
            generation_id=gen_id,
            workflow_id=None,
            status="failed",
            orchestration_results=orchestration_results,
        )

        # Assert
        assert result == mock_updated
        mock_repos.update_with_results.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_regeneration(self, service, mock_repos):
        """Test triggering workflow regeneration."""
        # Arrange
        tenant_id = "test-tenant"
        group_id = str(uuid4())

        mock_new_generation = MagicMock()
        mock_repos.deactivate_previous_generations = AsyncMock()
        mock_repos.create.return_value = mock_new_generation

        # Act
        result = await service.trigger_regeneration(
            tenant_id=tenant_id, analysis_group_id=group_id
        )

        # Assert
        assert result == mock_new_generation
        mock_repos.deactivate_previous_generations.assert_called_once_with(
            tenant_id=tenant_id, analysis_group_id=group_id
        )
        mock_repos.create.assert_called_once_with(
            tenant_id=tenant_id, analysis_group_id=group_id
        )

    @pytest.mark.asyncio
    async def test_delete_generation_success(self, service, mock_repos):
        """Test successful deletion of workflow generation."""
        # Arrange
        tenant_id = "test-tenant"
        gen_id = str(uuid4())

        mock_repos.delete.return_value = True

        # Act
        result = await service.delete_generation(
            tenant_id=tenant_id, generation_id=gen_id
        )

        # Assert
        assert result is True
        mock_repos.delete.assert_called_once_with(
            tenant_id=tenant_id, generation_id=gen_id
        )

    @pytest.mark.asyncio
    async def test_delete_generation_not_found(self, service, mock_repos):
        """Test deleting non-existent workflow generation returns False."""
        # Arrange
        tenant_id = "test-tenant"
        gen_id = str(uuid4())

        mock_repos.delete.return_value = False

        # Act
        result = await service.delete_generation(
            tenant_id=tenant_id, generation_id=gen_id
        )

        # Assert
        assert result is False
        mock_repos.delete.assert_called_once_with(
            tenant_id=tenant_id, generation_id=gen_id
        )


class TestAlertRoutingRuleService:
    """Test AlertRoutingRuleService methods."""

    @pytest.fixture
    def mock_repos(self):
        """Create mock repository."""
        rule_repo = AsyncMock()
        return rule_repo

    @pytest.fixture
    def service(self, mock_repos):
        """Create AlertRoutingRuleService instance."""
        return AlertRoutingRuleService(mock_repos)

    @pytest.mark.asyncio
    async def test_create_rule_success(self, service, mock_repos):
        """Test successful alert routing rule creation."""
        # Arrange
        tenant_id = "test-tenant"
        group_id = str(uuid4())
        workflow_id = str(uuid4())

        mock_rule = MagicMock()
        mock_rule.id = str(uuid4())
        mock_rule.tenant_id = tenant_id
        mock_rule.analysis_group_id = group_id
        mock_rule.workflow_id = workflow_id

        mock_repos.create.return_value = mock_rule

        # Act
        result = await service.create_rule(
            tenant_id=tenant_id,
            analysis_group_id=group_id,
            workflow_id=workflow_id,
        )

        # Assert
        assert result == mock_rule
        mock_repos.create.assert_called_once_with(
            tenant_id=tenant_id,
            analysis_group_id=group_id,
            workflow_id=workflow_id,
        )

    @pytest.mark.asyncio
    async def test_get_rule_by_id(self, service, mock_repos):
        """Test getting rule by ID."""
        # Arrange
        tenant_id = "test-tenant"
        rule_id = str(uuid4())

        mock_rule = MagicMock()
        mock_repos.get_by_id.return_value = mock_rule

        # Act
        result = await service.get_rule_by_id(tenant_id=tenant_id, rule_id=rule_id)

        # Assert
        assert result == mock_rule
        mock_repos.get_by_id.assert_called_once_with(
            tenant_id=tenant_id, rule_id=rule_id
        )

    @pytest.mark.asyncio
    async def test_get_rule_by_group(self, service, mock_repos):
        """Test getting rule by analysis group ID."""
        # Arrange
        tenant_id = "test-tenant"
        group_id = str(uuid4())

        mock_rule = MagicMock()
        mock_repos.get_by_group_id.return_value = mock_rule

        # Act
        result = await service.get_rule_by_group(
            tenant_id=tenant_id, analysis_group_id=group_id
        )

        # Assert
        assert result == mock_rule
        mock_repos.get_by_group_id.assert_called_once_with(
            tenant_id=tenant_id, analysis_group_id=group_id
        )

    @pytest.mark.asyncio
    async def test_list_rules(self, service, mock_repos):
        """Test listing all alert routing rules for tenant."""
        # Arrange
        tenant_id = "test-tenant"

        mock_rules = [MagicMock(), MagicMock(), MagicMock()]
        mock_repos.list_all.return_value = mock_rules

        # Act
        result = await service.list_rules(tenant_id=tenant_id)

        # Assert
        assert result == mock_rules
        assert len(result) == 3
        mock_repos.list_all.assert_called_once_with(tenant_id=tenant_id)

    @pytest.mark.asyncio
    async def test_list_rules_empty(self, service, mock_repos):
        """Test listing rules when none exist returns empty list."""
        # Arrange
        tenant_id = "test-tenant"

        mock_repos.list_all.return_value = []

        # Act
        result = await service.list_rules(tenant_id=tenant_id)

        # Assert
        assert result == []
        mock_repos.list_all.assert_called_once_with(tenant_id=tenant_id)

    @pytest.mark.asyncio
    async def test_delete_rule_success(self, service, mock_repos):
        """Test successful deletion of alert routing rule."""
        # Arrange
        tenant_id = "test-tenant"
        rule_id = str(uuid4())

        mock_repos.delete.return_value = True

        # Act
        result = await service.delete_rule(tenant_id=tenant_id, rule_id=rule_id)

        # Assert
        assert result is True
        mock_repos.delete.assert_called_once_with(tenant_id=tenant_id, rule_id=rule_id)

    @pytest.mark.asyncio
    async def test_delete_rule_not_found(self, service, mock_repos):
        """Test deleting non-existent alert routing rule returns False."""
        # Arrange
        tenant_id = "test-tenant"
        rule_id = str(uuid4())

        mock_repos.delete.return_value = False

        # Act
        result = await service.delete_rule(tenant_id=tenant_id, rule_id=rule_id)

        # Assert
        assert result is False
        mock_repos.delete.assert_called_once_with(tenant_id=tenant_id, rule_id=rule_id)
