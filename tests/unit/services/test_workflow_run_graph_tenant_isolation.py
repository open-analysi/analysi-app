"""Regression tests for cross-tenant isolation in get_workflow_run_graph().

Without the tenant guard, get_workflow_run_graph() proceeds to load node/edge
instances by workflow_run_id alone even when the tenant-scoped run lookup
returns None. A caller who knows a run UUID from another tenant can read
the full execution graph.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


class TestWorkflowRunGraphTenantIsolation:
    """Verify get_workflow_run_graph() enforces tenant isolation."""

    @pytest.mark.asyncio
    async def test_returns_none_for_wrong_tenant(self):
        """get_workflow_run_graph() must return None when run belongs to another tenant."""
        from analysi.services.workflow_execution import WorkflowExecutionService

        service = WorkflowExecutionService()
        session = AsyncMock()
        run_id = uuid4()

        # Mock the run repo to return None (wrong tenant)
        mock_run = MagicMock()
        mock_run.get_workflow_run = AsyncMock(return_value=None)

        # Patch the repository constructors used inside get_workflow_run_graph
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "analysi.services.workflow_execution.WorkflowRunRepository",
                lambda s: mock_run,
            )
            # Node repo should NOT be called if tenant check fails
            mock_node_repo = MagicMock()
            mock_node_repo.list_node_instances = AsyncMock(
                side_effect=AssertionError(
                    "Node repo should not be called for wrong tenant"
                )
            )
            mp.setattr(
                "analysi.services.workflow_execution.WorkflowNodeInstanceRepository",
                lambda s: mock_node_repo,
            )
            mock_edge_repo = MagicMock()
            mock_edge_repo.get_outgoing_edges = AsyncMock(
                side_effect=AssertionError(
                    "Edge repo should not be called for wrong tenant"
                )
            )
            mp.setattr(
                "analysi.services.workflow_execution.WorkflowEdgeInstanceRepository",
                lambda s: mock_edge_repo,
            )

            result = await service.get_workflow_run_graph(
                session, "wrong-tenant", run_id
            )

        assert result is None, (
            "get_workflow_run_graph must return None when tenant-scoped run "
            "lookup fails, not proceed to load node/edge instances."
        )

    @pytest.mark.asyncio
    async def test_does_not_load_nodes_for_wrong_tenant(self):
        """Node instances must NOT be loaded when tenant lookup returns None."""
        from analysi.services.workflow_execution import WorkflowExecutionService

        service = WorkflowExecutionService()
        session = AsyncMock()
        run_id = uuid4()

        mock_run = MagicMock()
        mock_run.get_workflow_run = AsyncMock(return_value=None)

        node_called = False

        async def track_node_call(*args, **kwargs):
            nonlocal node_called
            node_called = True
            return []

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "analysi.services.workflow_execution.WorkflowRunRepository",
                lambda s: mock_run,
            )
            mock_node_repo = MagicMock()
            mock_node_repo.list_node_instances = track_node_call
            mp.setattr(
                "analysi.services.workflow_execution.WorkflowNodeInstanceRepository",
                lambda s: mock_node_repo,
            )
            mp.setattr(
                "analysi.services.workflow_execution.WorkflowEdgeInstanceRepository",
                lambda s: MagicMock(),
            )

            await service.get_workflow_run_graph(session, "wrong-tenant", run_id)

        assert not node_called, (
            "list_node_instances was called even though tenant-scoped run "
            "lookup returned None — cross-tenant data leak."
        )
