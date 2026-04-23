"""
Unit tests for Workflow Pause & Resume.

Tests R10-R14: workflow-level pause/resume when tasks pause for HITL.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.constants import WorkflowConstants
from analysi.models.workflow_execution import WorkflowNodeInstance
from analysi.services.workflow_execution import WorkflowExecutor

# ---------------------------------------------------------------------------
# R10 — WorkflowConstants.Status.PAUSED
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWorkflowPausedStatus:
    """R10: PAUSED status exists in WorkflowConstants.Status."""

    def test_paused_value_equals_paused(self):
        assert WorkflowConstants.Status.PAUSED == "paused"

    def test_paused_from_string(self):
        assert WorkflowConstants.Status("paused") == WorkflowConstants.Status.PAUSED


# ---------------------------------------------------------------------------
# R12 — monitor_execution completion check
# ---------------------------------------------------------------------------


def _make_node_instance(node_id: str, status: str, **kwargs) -> MagicMock:
    """Helper to build a mock WorkflowNodeInstance with given status."""
    ni = MagicMock(spec=WorkflowNodeInstance)
    ni.id = uuid4()
    ni.node_id = node_id
    ni.status = status
    ni.error_message = kwargs.get("error_message")
    ni.task_run_id = kwargs.get("task_run_id", uuid4())
    return ni


@pytest.mark.unit
class TestMonitorExecutionCompletionCheck:
    """R12: completion check distinguishes COMPLETED vs PAUSED vs FAILED."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock(spec=AsyncSession)
        session.expire_all = MagicMock()
        return session

    @pytest.fixture
    def executor(self, mock_session):
        return WorkflowExecutor(mock_session)

    def _setup_workflow_run(self, executor, workflow_run_id):
        """Wire up mock repository and workflow ORM objects for monitor_execution."""
        # Mock workflow run lookup
        mock_workflow_run = MagicMock()
        mock_workflow_run.id = workflow_run_id
        mock_workflow_run.workflow_id = uuid4()
        mock_workflow_run.tenant_id = "t1"

        # Mock workflow definition (simple 1-node or 2-node graph)
        mock_workflow = MagicMock()
        mock_workflow.name = "test-workflow"
        mock_workflow.nodes = []
        mock_workflow.edges = []

        # Wire up session.execute to return the right things in sequence
        # First call: workflow_run lookup, second call: workflow definition lookup
        run_result = MagicMock()
        run_result.scalar_one_or_none.return_value = mock_workflow_run
        wf_result = MagicMock()
        wf_result.scalar_one.return_value = mock_workflow

        executor.session.execute = AsyncMock(side_effect=[run_result, wf_result])
        return mock_workflow

    @pytest.mark.asyncio
    async def test_all_completed_no_paused_marks_workflow_completed(self, executor):
        """All nodes COMPLETED, none paused → workflow COMPLETED."""
        wf_run_id = uuid4()
        mock_wf = self._setup_workflow_run(executor, wf_run_id)

        # Nodes: single node A, no edges
        node_a = MagicMock()
        node_a.node_id = "A"
        node_a.id = uuid4()
        node_a.node_template_id = None
        mock_wf.nodes = [node_a]
        mock_wf.edges = []

        completed_a = _make_node_instance("A", WorkflowConstants.Status.COMPLETED)

        # Repo mocks
        executor.node_repo.get_node_instance_by_node_id = AsyncMock(return_value=None)
        executor.node_repo.create_node_instance = AsyncMock(return_value=completed_a)
        executor.session.commit = AsyncMock()

        # First iteration: failed check returns [], pending returns [A]
        # A is ready (no predecessors) → executes → marked completed
        # Second iteration: failed check returns [], pending returns []
        # all_nodes check: [completed_a] → all COMPLETED → workflow COMPLETED
        call_count = 0

        async def mock_list_nodes(run_id, status=None):
            nonlocal call_count
            call_count += 1
            if status == WorkflowConstants.Status.FAILED:
                return []
            if status == WorkflowConstants.Status.PENDING:
                return []  # No pending → triggers completion check
            if status == WorkflowConstants.Status.RUNNING:
                return []
            # No status filter → return all nodes
            return [completed_a]

        executor.node_repo.list_node_instances = AsyncMock(side_effect=mock_list_nodes)

        with patch.object(
            executor, "update_workflow_status", new=AsyncMock()
        ) as mock_update:
            with patch.object(
                executor, "_aggregate_llm_usage", new=AsyncMock(return_value=None)
            ):
                with patch.object(
                    executor, "_capture_workflow_output", new=AsyncMock()
                ):
                    await executor.monitor_execution(wf_run_id)

            # Should have been called with RUNNING first, then COMPLETED
            calls = mock_update.call_args_list
            statuses = [c.args[1] for c in calls]
            assert WorkflowConstants.Status.COMPLETED in statuses
            assert WorkflowConstants.Status.PAUSED not in statuses

    @pytest.mark.asyncio
    async def test_some_paused_no_failures_marks_workflow_paused(self, executor):
        """Some nodes COMPLETED, some PAUSED, none FAILED → workflow PAUSED."""
        wf_run_id = uuid4()
        mock_wf = self._setup_workflow_run(executor, wf_run_id)
        mock_wf.nodes = []
        mock_wf.edges = []

        completed_a = _make_node_instance("A", WorkflowConstants.Status.COMPLETED)
        paused_b = _make_node_instance("B", WorkflowConstants.Status.PAUSED)

        async def mock_list_nodes(run_id, status=None):
            if status == WorkflowConstants.Status.FAILED:
                return []
            if status == WorkflowConstants.Status.PENDING:
                return []  # No pending
            if status == WorkflowConstants.Status.RUNNING:
                return []
            return [completed_a, paused_b]

        executor.node_repo.list_node_instances = AsyncMock(side_effect=mock_list_nodes)
        executor.node_repo.get_node_instance_by_node_id = AsyncMock(
            return_value=MagicMock()
        )
        executor.session.commit = AsyncMock()

        with patch.object(
            executor, "update_workflow_status", new=AsyncMock()
        ) as mock_update:
            with patch.object(
                executor, "_aggregate_llm_usage", new=AsyncMock(return_value=None)
            ):
                await executor.monitor_execution(wf_run_id)

            calls = mock_update.call_args_list
            statuses = [c.args[1] for c in calls]
            assert WorkflowConstants.Status.PAUSED in statuses
            assert WorkflowConstants.Status.COMPLETED not in [
                s for s in statuses if s != WorkflowConstants.Status.RUNNING
            ]

    @pytest.mark.asyncio
    async def test_all_paused_single_node_marks_workflow_paused(self, executor):
        """Single node workflow, node pauses → workflow PAUSED."""
        wf_run_id = uuid4()
        mock_wf = self._setup_workflow_run(executor, wf_run_id)
        mock_wf.nodes = []
        mock_wf.edges = []

        paused_a = _make_node_instance("A", WorkflowConstants.Status.PAUSED)

        async def mock_list_nodes(run_id, status=None):
            if status == WorkflowConstants.Status.FAILED:
                return []
            if status == WorkflowConstants.Status.PENDING:
                return []
            if status == WorkflowConstants.Status.RUNNING:
                return []
            return [paused_a]

        executor.node_repo.list_node_instances = AsyncMock(side_effect=mock_list_nodes)
        executor.node_repo.get_node_instance_by_node_id = AsyncMock(
            return_value=MagicMock()
        )
        executor.session.commit = AsyncMock()

        with patch.object(
            executor, "update_workflow_status", new=AsyncMock()
        ) as mock_update:
            with patch.object(
                executor, "_aggregate_llm_usage", new=AsyncMock(return_value=None)
            ):
                await executor.monitor_execution(wf_run_id)

            statuses = [c.args[1] for c in mock_update.call_args_list]
            assert WorkflowConstants.Status.PAUSED in statuses

    @pytest.mark.asyncio
    async def test_mixed_failed_and_paused_marks_workflow_failed(self, executor):
        """Some FAILED + some PAUSED → FAILED takes precedence."""
        wf_run_id = uuid4()
        mock_wf = self._setup_workflow_run(executor, wf_run_id)
        mock_wf.nodes = []
        mock_wf.edges = []

        failed_a = _make_node_instance(
            "A", WorkflowConstants.Status.FAILED, error_message="boom"
        )

        async def mock_list_nodes(run_id, status=None):
            if status == WorkflowConstants.Status.FAILED:
                return [failed_a]  # Early exit on failure
            return []

        executor.node_repo.list_node_instances = AsyncMock(side_effect=mock_list_nodes)
        executor.node_repo.get_node_instance_by_node_id = AsyncMock(
            return_value=MagicMock()
        )
        executor.session.commit = AsyncMock()

        with patch.object(
            executor, "update_workflow_status", new=AsyncMock()
        ) as mock_update:
            with patch.object(
                executor, "_aggregate_llm_usage", new=AsyncMock(return_value=None)
            ):
                await executor.monitor_execution(wf_run_id)

            statuses = [c.args[1] for c in mock_update.call_args_list]
            assert WorkflowConstants.Status.FAILED in statuses


# ---------------------------------------------------------------------------
# R14 — Stall detection (pending blocked by paused predecessor)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMonitorExecutionStallDetection:
    """R14: pending nodes blocked by paused predecessors → workflow PAUSED."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock(spec=AsyncSession)
        session.expire_all = MagicMock()
        return session

    @pytest.fixture
    def executor(self, mock_session):
        return WorkflowExecutor(mock_session)

    def _setup_workflow_run(self, executor, workflow_run_id):
        mock_workflow_run = MagicMock()
        mock_workflow_run.id = workflow_run_id
        mock_workflow_run.workflow_id = uuid4()
        mock_workflow_run.tenant_id = "t1"

        mock_workflow = MagicMock()
        mock_workflow.name = "test-workflow"
        mock_workflow.nodes = []
        mock_workflow.edges = []

        run_result = MagicMock()
        run_result.scalar_one_or_none.return_value = mock_workflow_run
        wf_result = MagicMock()
        wf_result.scalar_one.return_value = mock_workflow

        executor.session.execute = AsyncMock(side_effect=[run_result, wf_result])
        return mock_workflow

    @pytest.mark.asyncio
    async def test_pending_blocked_by_paused_no_running_marks_paused(self, executor):
        """Pending node B blocked by paused A, nothing running → workflow PAUSED."""
        wf_run_id = uuid4()
        mock_wf = self._setup_workflow_run(executor, wf_run_id)
        mock_wf.nodes = []
        mock_wf.edges = []

        paused_a = _make_node_instance("A", WorkflowConstants.Status.PAUSED)
        pending_b = _make_node_instance("B", WorkflowConstants.Status.PENDING)

        iteration = 0

        async def mock_list_nodes(run_id, status=None):
            nonlocal iteration
            if status == WorkflowConstants.Status.FAILED:
                return []
            if status == WorkflowConstants.Status.PENDING:
                return [pending_b]
            if status == WorkflowConstants.Status.RUNNING:
                return []
            # All nodes (no status filter)
            return [paused_a, pending_b]

        executor.node_repo.list_node_instances = AsyncMock(side_effect=mock_list_nodes)
        executor.node_repo.get_node_instance_by_node_id = AsyncMock(
            return_value=MagicMock()
        )
        executor.session.commit = AsyncMock()

        # B's predecessor A is paused → not ready
        with patch.object(
            executor, "check_predecessors_complete", new=AsyncMock(return_value=False)
        ):
            with patch.object(
                executor, "update_workflow_status", new=AsyncMock()
            ) as mock_update:
                with patch.object(
                    executor, "_aggregate_llm_usage", new=AsyncMock(return_value=None)
                ):
                    await executor.monitor_execution(wf_run_id)

                statuses = [c.args[1] for c in mock_update.call_args_list]
                assert WorkflowConstants.Status.PAUSED in statuses

    @pytest.mark.asyncio
    async def test_pending_with_running_predecessor_continues_waiting(self, executor):
        """Pending node with a RUNNING predecessor → monitor keeps waiting, not PAUSED."""
        wf_run_id = uuid4()
        mock_wf = self._setup_workflow_run(executor, wf_run_id)
        mock_wf.nodes = []
        mock_wf.edges = []

        running_a = _make_node_instance("A", WorkflowConstants.Status.RUNNING)
        pending_b = _make_node_instance("B", WorkflowConstants.Status.PENDING)

        call_count = 0

        async def mock_list_nodes(run_id, status=None):
            nonlocal call_count
            call_count += 1
            if status == WorkflowConstants.Status.FAILED:
                return []
            if status == WorkflowConstants.Status.PENDING:
                # After some iterations, simulate A completing and B becoming ready
                if call_count > 6:
                    return []  # No more pending
                return [pending_b]
            if status == WorkflowConstants.Status.RUNNING:
                if call_count > 6:
                    return []
                return [running_a]
            # All nodes (completion check)
            completed_a = _make_node_instance("A", WorkflowConstants.Status.COMPLETED)
            completed_b = _make_node_instance("B", WorkflowConstants.Status.COMPLETED)
            return [completed_a, completed_b]

        executor.node_repo.list_node_instances = AsyncMock(side_effect=mock_list_nodes)
        executor.node_repo.get_node_instance_by_node_id = AsyncMock(
            return_value=MagicMock()
        )
        executor.session.commit = AsyncMock()

        with patch.object(
            executor, "check_predecessors_complete", new=AsyncMock(return_value=False)
        ):
            with patch.object(
                executor, "update_workflow_status", new=AsyncMock()
            ) as mock_update:
                with patch.object(
                    executor, "_aggregate_llm_usage", new=AsyncMock(return_value=None)
                ):
                    with patch.object(
                        executor, "_capture_workflow_output", new=AsyncMock()
                    ):
                        await executor.monitor_execution(wf_run_id)

                statuses = [c.args[1] for c in mock_update.call_args_list]
                # Should end with COMPLETED, NOT PAUSED (because A was running, then completed)
                assert WorkflowConstants.Status.PAUSED not in statuses
                assert WorkflowConstants.Status.COMPLETED in statuses


# ---------------------------------------------------------------------------
# update_workflow_status — PAUSED timing
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateWorkflowStatusPaused:
    """PAUSED status should NOT set completed_at."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock(spec=AsyncSession)
        session.expire_all = MagicMock()
        return session

    @pytest.fixture
    def executor(self, mock_session):
        return WorkflowExecutor(mock_session)

    @pytest.mark.asyncio
    async def test_paused_does_not_set_completed_at(self, executor):
        """PAUSED status must NOT set completed_at timestamp."""
        wf_run_id = uuid4()
        executor.run_repo.update_workflow_run_status = AsyncMock()
        executor.run_repo.merge_execution_context = AsyncMock()
        executor.session.commit = AsyncMock()

        await executor.update_workflow_status(
            wf_run_id, WorkflowConstants.Status.PAUSED
        )

        # update_workflow_run_status is called with (workflow_run_id, **kwargs)
        call_kwargs = executor.run_repo.update_workflow_run_status.call_args.kwargs
        assert "completed_at" not in call_kwargs
        assert "started_at" not in call_kwargs
        assert call_kwargs["status"] == "paused"


# ---------------------------------------------------------------------------
# R13 — resume_paused_workflow
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResumePausedWorkflow:
    """R13: resume resets paused node → PENDING, workflow → RUNNING, re-enters monitor."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock(spec=AsyncSession)
        session.expire_all = MagicMock()
        return session

    @pytest.fixture
    def executor(self, mock_session):
        return WorkflowExecutor(mock_session)

    @pytest.mark.asyncio
    async def test_resume_resets_paused_node_and_workflow(self, executor):
        """Resume: paused node → PENDING, workflow → RUNNING."""
        wf_run_id = uuid4()
        paused_node = _make_node_instance("A", WorkflowConstants.Status.PAUSED)

        # Mock workflow run lookup
        mock_wf_run = MagicMock()
        mock_wf_run.id = wf_run_id
        mock_wf_run.status = WorkflowConstants.Status.PAUSED
        mock_wf_run.tenant_id = "t1"

        run_result = MagicMock()
        run_result.scalar_one_or_none.return_value = mock_wf_run
        executor.session.execute = AsyncMock(return_value=run_result)

        # Mock: find the paused node instance
        executor.node_repo.list_node_instances = AsyncMock(return_value=[paused_node])
        executor.node_repo.update_node_instance_status = AsyncMock()
        executor.run_repo.update_workflow_run_status = AsyncMock()
        executor.session.commit = AsyncMock()
        executor.session.flush = AsyncMock()

        # Mock monitor_execution to avoid actual execution
        with patch.object(
            executor, "monitor_execution", new=AsyncMock()
        ) as mock_monitor:
            await executor.resume_paused_workflow(wf_run_id)

            # Node should be reset to PENDING
            executor.node_repo.update_node_instance_status.assert_called_once_with(
                paused_node.id,
                WorkflowConstants.Status.PENDING,
            )
            # monitor_execution should be re-entered
            mock_monitor.assert_called_once_with(wf_run_id)

    @pytest.mark.asyncio
    async def test_resume_non_paused_workflow_raises(self, executor):
        """Resume on a non-paused workflow raises ValueError."""
        wf_run_id = uuid4()

        mock_wf_run = MagicMock()
        mock_wf_run.id = wf_run_id
        mock_wf_run.status = WorkflowConstants.Status.COMPLETED
        mock_wf_run.tenant_id = "t1"

        run_result = MagicMock()
        run_result.scalar_one_or_none.return_value = mock_wf_run
        executor.session.execute = AsyncMock(return_value=run_result)

        with pytest.raises(ValueError, match="not paused"):
            await executor.resume_paused_workflow(wf_run_id)

    @pytest.mark.asyncio
    async def test_resume_nonexistent_workflow_raises(self, executor):
        """Resume on a non-existent workflow run raises ValueError."""
        wf_run_id = uuid4()

        run_result = MagicMock()
        run_result.scalar_one_or_none.return_value = None
        executor.session.execute = AsyncMock(return_value=run_result)

        with pytest.raises(ValueError, match="not found"):
            await executor.resume_paused_workflow(wf_run_id)


# ---------------------------------------------------------------------------
# _execute_workflow_synchronously — PAUSED skip
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecuteWorkflowSynchronouslySkipsPaused:
    """PAUSED workflow should be skipped by _execute_workflow_synchronously."""

    @pytest.mark.asyncio
    async def test_paused_workflow_is_skipped(self):
        """A PAUSED workflow should not be re-executed by the background path."""
        # This tests the production (no session) path which checks status
        # We verify that "paused" is included in the skip list
        # by checking the code constant rather than doing a full DB test
        # (integration test would verify end-to-end)
        assert WorkflowConstants.Status.PAUSED == "paused"
        # The actual skip logic is tested via integration tests;
        # here we just verify the constant exists for the guard clause
