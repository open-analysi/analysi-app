"""Adversarial edge case tests for Kea Coordination services."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from analysi.services.kea_coordination_service import (
    AlertRoutingRuleService,
    AnalysisGroupService,
    WorkflowGenerationService,
)


class TestAnalysisGroupServiceEdgeCases:
    """Adversarial tests for AnalysisGroupService."""

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
    async def test_create_group_with_empty_title(self, service, mock_repos):
        """Test behavior with empty string title."""
        group_repo, _ = mock_repos
        tenant_id = "test-tenant"
        title = ""  # Empty title

        mock_group = MagicMock()
        mock_group.title = ""
        group_repo.create.return_value = mock_group

        # Should pass through - validation is at repo/DB level
        result = await service.create_group(tenant_id=tenant_id, title=title)

        assert result == mock_group
        group_repo.create.assert_called_once_with(tenant_id=tenant_id, title=title)

    @pytest.mark.asyncio
    async def test_create_group_with_very_long_title(self, service, mock_repos):
        """Test behavior with extremely long title (potential DB truncation)."""
        group_repo, _ = mock_repos
        tenant_id = "test-tenant"
        title = "A" * 10000  # Very long title

        mock_group = MagicMock()
        group_repo.create.return_value = mock_group

        await service.create_group(tenant_id=tenant_id, title=title)

        group_repo.create.assert_called_once_with(tenant_id=tenant_id, title=title)

    @pytest.mark.asyncio
    async def test_create_group_with_special_characters_in_title(
        self, service, mock_repos
    ):
        """Test behavior with SQL injection-like characters in title."""
        group_repo, _ = mock_repos
        tenant_id = "test-tenant"
        title = "'; DROP TABLE analysis_groups; --"

        mock_group = MagicMock()
        mock_group.title = title
        group_repo.create.return_value = mock_group

        await service.create_group(tenant_id=tenant_id, title=title)

        # Should pass through safely - SQLAlchemy handles parameterization
        group_repo.create.assert_called_once_with(tenant_id=tenant_id, title=title)

    @pytest.mark.asyncio
    async def test_get_group_by_id_with_string_uuid(self, service, mock_repos):
        """Test that string UUIDs are handled correctly."""
        group_repo, _ = mock_repos
        tenant_id = "test-tenant"
        group_id = str(uuid4())  # String, not UUID object

        mock_group = MagicMock()
        group_repo.get_by_id.return_value = mock_group

        result = await service.get_group_by_id(tenant_id=tenant_id, group_id=group_id)

        assert result == mock_group

    @pytest.mark.asyncio
    async def test_get_group_by_id_with_uuid_object(self, service, mock_repos):
        """Test that UUID objects are handled correctly."""
        group_repo, _ = mock_repos
        tenant_id = "test-tenant"
        group_id = uuid4()  # UUID object, not string

        mock_group = MagicMock()
        group_repo.get_by_id.return_value = mock_group

        result = await service.get_group_by_id(tenant_id=tenant_id, group_id=group_id)

        assert result == mock_group

    @pytest.mark.asyncio
    async def test_create_group_with_generation_db_connection_error(
        self, service, mock_repos
    ):
        """Test behavior when DB connection fails during creation."""
        group_repo, generation_repo = mock_repos
        tenant_id = "test-tenant"
        title = "Test Group"

        group_repo.get_by_title.side_effect = OperationalError(
            "connection refused", None, None
        )

        with pytest.raises(OperationalError):
            await service.create_group_with_generation(tenant_id=tenant_id, title=title)

    @pytest.mark.asyncio
    async def test_create_group_with_generation_generation_creation_fails(
        self, service, mock_repos
    ):
        """Test behavior when group created but generation creation fails."""
        group_repo, generation_repo = mock_repos
        tenant_id = "test-tenant"
        title = "Test Group"

        mock_group = MagicMock()
        mock_group.id = str(uuid4())

        group_repo.get_by_title.return_value = None
        group_repo.create.return_value = mock_group
        generation_repo.get_active_for_group.return_value = None
        generation_repo.get_latest_for_group.return_value = (
            None  # No completed gen with workflow
        )
        generation_repo.get_generation_with_workflow_for_group.return_value = None
        generation_repo.create.side_effect = OperationalError("disk full", None, None)

        # Should propagate the error - partial state (group without generation)
        with pytest.raises(OperationalError):
            await service.create_group_with_generation(tenant_id=tenant_id, title=title)

    @pytest.mark.asyncio
    async def test_create_group_with_generation_concurrent_generation_creation(
        self, service, mock_repos
    ):
        """Test race condition: generation created by another worker after our check."""
        group_repo, generation_repo = mock_repos
        tenant_id = "test-tenant"
        title = "Concurrent Test"

        existing_group = MagicMock()
        existing_group.id = str(uuid4())

        # Group exists
        group_repo.get_by_title.return_value = existing_group

        # First check: no active generation
        # Also no completed generation with workflow
        # But when we try to create, another worker already did
        MagicMock()
        generation_repo.get_active_for_group.return_value = None
        generation_repo.get_latest_for_group.return_value = (
            None  # No completed gen with workflow
        )
        generation_repo.get_generation_with_workflow_for_group.return_value = None
        generation_repo.create.side_effect = IntegrityError("duplicate", None, None)

        # Current code doesn't handle this race condition!
        # This test documents the bug
        with pytest.raises(IntegrityError):
            await service.create_group_with_generation(tenant_id=tenant_id, title=title)

    @pytest.mark.asyncio
    async def test_delete_group_with_none_group_id(self, service, mock_repos):
        """Test behavior when group_id is None."""
        group_repo, _ = mock_repos
        tenant_id = "test-tenant"

        # Pass None - should it raise or return False?
        group_repo.delete.return_value = False

        await service.delete_group(tenant_id=tenant_id, group_id=None)

        # Currently passes through to repo
        group_repo.delete.assert_called_once_with(tenant_id=tenant_id, group_id=None)


class TestWorkflowGenerationServiceEdgeCases:
    """Adversarial tests for WorkflowGenerationService."""

    @pytest.fixture
    def mock_repo(self):
        """Create mock repository."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_repo):
        """Create WorkflowGenerationService instance."""
        return WorkflowGenerationService(mock_repo)

    @pytest.mark.asyncio
    async def test_update_progress_with_negative_tasks_count(self, service, mock_repo):
        """Test behavior with negative tasks_count."""
        tenant_id = "test-tenant"
        gen_id = str(uuid4())

        mock_generation = MagicMock()
        mock_repo.update_progress.return_value = mock_generation

        # Negative tasks_count - should this be validated?
        await service.update_generation_progress(
            tenant_id=tenant_id,
            generation_id=gen_id,
            tasks_count=-5,  # Invalid!
        )

        # Currently passes through without validation
        mock_repo.update_progress.assert_called_once()
        call_kwargs = mock_repo.update_progress.call_args.kwargs
        assert call_kwargs["tasks_count"] == -5

    @pytest.mark.asyncio
    async def test_update_progress_with_zero_tasks_count(self, service, mock_repo):
        """Test behavior with zero tasks_count."""
        tenant_id = "test-tenant"
        gen_id = str(uuid4())

        mock_generation = MagicMock()
        mock_repo.update_progress.return_value = mock_generation

        await service.update_generation_progress(
            tenant_id=tenant_id,
            generation_id=gen_id,
            tasks_count=0,
        )

        mock_repo.update_progress.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_results_with_invalid_status(self, service, mock_repo):
        """Test behavior with invalid status value."""
        tenant_id = "test-tenant"
        gen_id = str(uuid4())

        mock_generation = MagicMock()
        mock_repo.update_with_results.return_value = mock_generation

        # Invalid status - no enum validation at service level
        await service.update_generation_results(
            tenant_id=tenant_id,
            generation_id=gen_id,
            workflow_id=None,
            status="invalid_status_xyz",  # Not a valid status
        )

        # Passes through without validation - DB might reject
        mock_repo.update_with_results.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_results_with_huge_orchestration_results(
        self, service, mock_repo
    ):
        """Test behavior with very large orchestration_results dict."""
        tenant_id = "test-tenant"
        gen_id = str(uuid4())

        # Create a huge dict (potential JSONB size issues)
        huge_results = {f"key_{i}": "x" * 1000 for i in range(1000)}

        mock_generation = MagicMock()
        mock_repo.update_with_results.return_value = mock_generation

        await service.update_generation_results(
            tenant_id=tenant_id,
            generation_id=gen_id,
            workflow_id=None,
            status="completed",
            orchestration_results=huge_results,
        )

        # Passes through - DB handles size limits
        mock_repo.update_with_results.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_regeneration_deactivate_fails(self, service, mock_repo):
        """Test behavior when deactivating previous generations fails."""
        tenant_id = "test-tenant"
        group_id = str(uuid4())

        mock_repo.deactivate_previous_generations.side_effect = OperationalError(
            "deadlock", None, None
        )

        with pytest.raises(OperationalError):
            await service.trigger_regeneration(
                tenant_id=tenant_id, analysis_group_id=group_id
            )

        # Should not have tried to create new generation
        mock_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_mark_stage_completed_with_invalid_stage(self, service, mock_repo):
        """Test marking completion with invalid stage name."""
        tenant_id = "test-tenant"
        gen_id = str(uuid4())

        mock_generation = MagicMock()
        mock_repo.mark_stage_completed.return_value = mock_generation

        # Invalid stage name - no validation at service level
        await service.mark_stage_completed(
            tenant_id=tenant_id,
            generation_id=gen_id,
            stage="nonexistent_stage",
        )

        # Passes through - repo/DB handles validation
        mock_repo.mark_stage_completed.assert_called_once()


class TestAlertRoutingRuleServiceEdgeCases:
    """Adversarial tests for AlertRoutingRuleService."""

    @pytest.fixture
    def mock_repo(self):
        """Create mock repository."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_repo):
        """Create AlertRoutingRuleService instance."""
        return AlertRoutingRuleService(mock_repo)

    @pytest.mark.asyncio
    async def test_create_rule_with_same_group_different_workflow(
        self, service, mock_repo
    ):
        """Test creating rule for group that already has a rule (different workflow)."""
        tenant_id = "test-tenant"
        group_id = str(uuid4())
        workflow_id_1 = str(uuid4())
        workflow_id_2 = str(uuid4())

        # First rule creates successfully
        mock_rule_1 = MagicMock()
        mock_repo.create.return_value = mock_rule_1

        await service.create_rule(
            tenant_id=tenant_id,
            analysis_group_id=group_id,
            workflow_id=workflow_id_1,
        )

        # If we try to create another rule for same group with different workflow,
        # the DB should reject (unique constraint) but service doesn't validate
        mock_repo.create.side_effect = IntegrityError("duplicate", None, None)

        with pytest.raises(IntegrityError):
            await service.create_rule(
                tenant_id=tenant_id,
                analysis_group_id=group_id,
                workflow_id=workflow_id_2,
            )

    @pytest.mark.asyncio
    async def test_get_rule_by_group_returns_none_vs_raises(self, service, mock_repo):
        """Test that missing rule returns None, not raises."""
        tenant_id = "test-tenant"
        group_id = str(uuid4())

        mock_repo.get_by_group_id.return_value = None

        result = await service.get_rule_by_group(
            tenant_id=tenant_id, analysis_group_id=group_id
        )

        assert result is None  # Should return None, not raise

    @pytest.mark.asyncio
    async def test_list_rules_with_empty_tenant(self, service, mock_repo):
        """Test listing rules with empty tenant_id."""
        mock_repo.list_all.return_value = []

        await service.list_rules(tenant_id="")

        # Empty tenant passes through - DB handles validation
        mock_repo.list_all.assert_called_once_with(tenant_id="")
