"""
Security regression tests: cross-tenant task binding in workflows (Round 18).

Validates that workflow nodes cannot reference tasks belonging to other tenants.
An attacker in tenant A must not be able to bind tenant B's task UUID into a
workflow node, which would leak proprietary Cy scripts and data at execution time.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from analysi.repositories.workflow import WorkflowRepository


@pytest.mark.unit
class TestCrossTenantWorkflowTask:
    """Verify _validate_task_ownership blocks cross-tenant task references."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.execute = AsyncMock()
        session.rollback = AsyncMock()
        session.add = MagicMock()
        return session

    @pytest.fixture
    def repo(self, mock_session):
        return WorkflowRepository(mock_session)

    def _mock_task_lookup(self, mock_session, found: bool):
        """Configure mock session to simulate task ownership lookup."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = uuid4() if found else None
        mock_session.execute.return_value = mock_result

    # ---- create_workflow ----

    @pytest.mark.asyncio
    async def test_create_workflow_rejects_cross_tenant_task(self, repo, mock_session):
        """create_workflow must reject a node whose task_id belongs to another tenant."""
        foreign_task_id = uuid4()
        workflow_data = MagicMock()
        workflow_data.name = "evil-wf"
        workflow_data.description = "x"
        workflow_data.is_dynamic = False
        workflow_data.io_schema = {}
        workflow_data.data_samples = []

        node = MagicMock()
        node.node_id = "n1"
        node.node_template_id = None
        node.task_id = foreign_task_id
        node.kind.value = "task"
        node.name = "steal"
        node.schemas = {}
        node.is_start_node = True
        node.foreach_config = None
        workflow_data.nodes = [node]
        workflow_data.edges = []

        # First execute call: flush for workflow creation (returns workflow id)
        # Second execute call: _validate_task_ownership (returns None = not found)
        workflow_mock = MagicMock()
        workflow_mock.id = uuid4()

        task_lookup_result = MagicMock()
        task_lookup_result.scalar_one_or_none.return_value = None  # cross-tenant

        mock_session.execute.return_value = task_lookup_result

        with pytest.raises(ValueError, match="not found or not accessible"):
            await repo.create_workflow("tenant-a", workflow_data)

    @pytest.mark.asyncio
    async def test_create_workflow_allows_same_tenant_task(self, repo, mock_session):
        """create_workflow must allow a node whose task_id belongs to the same tenant."""
        same_tenant_task_id = uuid4()
        workflow_data = MagicMock()
        workflow_data.name = "good-wf"
        workflow_data.description = "x"
        workflow_data.is_dynamic = False
        workflow_data.io_schema = {}
        workflow_data.data_samples = []

        node = MagicMock()
        node.node_id = "n1"
        node.node_template_id = None
        node.task_id = same_tenant_task_id
        node.kind.value = "task"
        node.name = "legit"
        node.schemas = {}
        node.is_start_node = True
        node.foreach_config = None
        workflow_data.nodes = [node]
        workflow_data.edges = []

        # Mock: task ownership check returns the task id (found)
        task_lookup_result = MagicMock()
        task_lookup_result.scalar_one_or_none.return_value = same_tenant_task_id
        mock_session.execute.return_value = task_lookup_result

        # Mock get_workflow_by_id for the return value after commit
        created_wf = MagicMock()
        created_wf.id = uuid4()
        repo.get_workflow_by_id = AsyncMock(return_value=created_wf)

        result = await repo.create_workflow("tenant-a", workflow_data)
        assert result is not None

    # ---- add_node ----

    @pytest.mark.asyncio
    async def test_add_node_rejects_cross_tenant_task(self, repo, mock_session):
        """add_node must reject a task_id belonging to another tenant."""
        foreign_task_id = uuid4()
        workflow = MagicMock()
        workflow.id = uuid4()
        workflow.nodes = []
        repo.get_workflow_by_id = AsyncMock(return_value=workflow)

        # Task ownership lookup returns None
        self._mock_task_lookup(mock_session, found=False)

        node_data = {
            "node_id": "n-evil",
            "kind": "task",
            "name": "Steal Node",
            "task_id": foreign_task_id,
            "schemas": {},
        }

        with pytest.raises(ValueError, match="not found or not accessible"):
            await repo.add_node("tenant-a", workflow.id, node_data)

    # ---- update_node ----

    @pytest.mark.asyncio
    async def test_update_node_rejects_cross_tenant_task(self, repo, mock_session):
        """update_node must reject updating task_id to one from another tenant."""
        from analysi.models.workflow import WorkflowNode

        foreign_task_id = uuid4()

        node = MagicMock(spec=WorkflowNode)
        node.node_id = "n1"
        node.task_id = uuid4()  # current (valid) task

        workflow = MagicMock()
        workflow.id = uuid4()
        workflow.nodes = [node]
        repo.get_workflow_by_id = AsyncMock(return_value=workflow)

        # Task ownership lookup returns None
        self._mock_task_lookup(mock_session, found=False)

        with pytest.raises(ValueError, match="not found or not accessible"):
            await repo.update_node(
                "tenant-a", workflow.id, "n1", {"task_id": foreign_task_id}
            )

    # ---- skip validation when no task_id ----

    @pytest.mark.asyncio
    async def test_node_without_task_id_skips_validation(self, repo, mock_session):
        """Nodes with only a template (no task_id) must not trigger task validation."""
        workflow = MagicMock()
        workflow.id = uuid4()
        workflow.nodes = []
        repo.get_workflow_by_id = AsyncMock(return_value=workflow)

        node_data = {
            "node_id": "n-tmpl",
            "kind": "transformation",
            "name": "Template Node",
            "schemas": {},
        }

        # Should not call _validate_task_ownership at all
        repo._validate_task_ownership = AsyncMock()

        result = await repo.add_node("tenant-a", workflow.id, node_data)
        assert result is not None
        repo._validate_task_ownership.assert_not_called()
