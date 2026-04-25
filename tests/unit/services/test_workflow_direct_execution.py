"""Unit tests for direct workflow execution in the worker (no REST, no polling).

Tests the new `create_workflow_run()` method on WorkflowExecutor and the updated
`_execute_workflow_rule()` that runs workflows synchronously in the worker
instead of using asyncio.create_task + polling.

Part of the initiative to move scheduled task/workflow execution out of
the API containers and into the analysis worker.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.services.workflow_execution import WorkflowExecutor


class TestCreateWorkflowRun:
    """Tests for WorkflowExecutor.create_workflow_run() — the split-out method
    that creates the DB record without starting execution."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def executor(self, mock_session):
        return WorkflowExecutor(mock_session)

    @pytest.mark.asyncio
    async def test_creates_workflow_run_record(self, executor):
        """create_workflow_run creates a WorkflowRun record and returns the ID."""
        tenant_id = "test-tenant"
        workflow_id = uuid4()
        input_data = {"alert_id": "123", "severity": "high"}
        run_id = uuid4()

        mock_run = MagicMock(id=run_id)
        executor.run_repo.create_workflow_run = AsyncMock(return_value=mock_run)
        executor.storage.store = AsyncMock(return_value={"location": "inline://data"})
        executor.storage.select_storage_type = MagicMock(return_value="inline")

        result = await executor.create_workflow_run(tenant_id, workflow_id, input_data)

        assert result == run_id
        executor.run_repo.create_workflow_run.assert_called_once()
        executor.storage.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_does_not_start_background_execution(self, executor):
        """create_workflow_run must NOT fire asyncio.create_task.

        This is the key difference from execute_workflow() — the caller
        is responsible for starting execution.
        """
        tenant_id = "test-tenant"
        workflow_id = uuid4()
        input_data = {"alert_id": "123"}
        mock_run = MagicMock(id=uuid4())

        executor.run_repo.create_workflow_run = AsyncMock(return_value=mock_run)
        executor.storage.store = AsyncMock(return_value={"location": "loc"})
        executor.storage.select_storage_type = MagicMock(return_value="inline")

        with patch("asyncio.create_task") as mock_create_task:
            await executor.create_workflow_run(tenant_id, workflow_id, input_data)
            mock_create_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_passes_execution_context(self, executor):
        """create_workflow_run forwards execution_context to the repo."""
        tenant_id = "test-tenant"
        workflow_id = uuid4()
        input_data = {"alert_id": "123"}
        execution_context = {"control_event_id": "evt-1", "rule_id": "rule-1"}
        mock_run = MagicMock(id=uuid4())

        executor.run_repo.create_workflow_run = AsyncMock(return_value=mock_run)
        executor.storage.store = AsyncMock(return_value={"location": "loc"})
        executor.storage.select_storage_type = MagicMock(return_value="inline")

        await executor.create_workflow_run(
            tenant_id, workflow_id, input_data, execution_context=execution_context
        )

        call_kwargs = executor.run_repo.create_workflow_run.call_args
        assert call_kwargs.kwargs.get("execution_context") == execution_context

    @pytest.mark.asyncio
    async def test_sets_tenant_id_on_executor(self, executor):
        """create_workflow_run sets self.tenant_id for downstream use."""
        tenant_id = "my-tenant"
        workflow_id = uuid4()
        mock_run = MagicMock(id=uuid4())

        executor.run_repo.create_workflow_run = AsyncMock(return_value=mock_run)
        executor.storage.store = AsyncMock(return_value={"location": "loc"})
        executor.storage.select_storage_type = MagicMock(return_value="inline")

        await executor.create_workflow_run(tenant_id, workflow_id, {"k": "v"})

        assert executor.tenant_id == tenant_id

    @pytest.mark.asyncio
    async def test_execute_workflow_delegates_to_create_workflow_run(self, executor):
        """execute_workflow() should call create_workflow_run() internally,
        then fire asyncio.create_task for the delayed execution."""
        tenant_id = "test-tenant"
        workflow_id = uuid4()
        input_data = {"alert_id": "123"}
        run_id = uuid4()

        executor.create_workflow_run = AsyncMock(return_value=run_id)

        with patch("analysi.services.workflow_execution.asyncio.create_task"):
            result = await executor.execute_workflow(tenant_id, workflow_id, input_data)

        assert result == run_id
        executor.create_workflow_run.assert_called_once_with(
            tenant_id, workflow_id, input_data, execution_context=None
        )


class TestExecuteWorkflowRuleDirect:
    """Tests for _execute_workflow_rule — verifies it runs synchronously
    in the worker (no polling, no asyncio.create_task).

    Note: _execute_workflow_rule uses deferred imports, so we patch the
    source modules (analysi.services.workflow_execution.WorkflowExecutor
    and analysi.db.session.AsyncSessionLocal).
    """

    @staticmethod
    def _setup_status_check(mock_session, status="completed"):
        """Configure mock session for post-execution status check."""
        mock_status_row = MagicMock()
        mock_status_row.status = status
        mock_status_row.error_message = None
        mock_status_result = MagicMock()
        mock_status_result.fetchone = MagicMock(return_value=mock_status_row)
        mock_session.execute = AsyncMock(return_value=mock_status_result)

    @pytest.mark.asyncio
    async def test_executes_synchronously_no_polling(self):
        """_execute_workflow_rule should run _execute_workflow_synchronously
        directly instead of polling."""
        from analysi.alert_analysis.jobs.control_events import (
            _execute_workflow_rule,
        )

        tenant_id = "tenant-a"
        workflow_id = uuid4()
        input_data = {"alert_id": "123", "event_id": "evt-1", "config": {}}
        execution_context = {"control_event_id": "evt-1", "rule_id": "rule-1"}
        run_id = uuid4()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        self._setup_status_check(mock_session)

        mock_executor = MagicMock()
        mock_executor.create_workflow_run = AsyncMock(return_value=run_id)

        with (
            patch(
                "analysi.alert_analysis.jobs.control_events.AsyncSessionLocal",
                return_value=mock_session,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.__init__",
                return_value=None,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.create_workflow_run",
                new_callable=AsyncMock,
                return_value=run_id,
            ) as mock_create,
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
                new_callable=AsyncMock,
            ) as mock_exec_sync,
        ):
            await _execute_workflow_rule(
                tenant_id=tenant_id,
                workflow_id=workflow_id,
                input_data=input_data,
                execution_context=execution_context,
            )

        # Verify: create_workflow_run called with correct args
        mock_create.assert_called_once_with(
            tenant_id, workflow_id, input_data, execution_context=execution_context
        )

        # Verify: synchronous execution called with the run ID
        mock_exec_sync.assert_called_once_with(run_id)

    @pytest.mark.asyncio
    async def test_does_not_use_polling_loop(self):
        """_execute_workflow_rule must NOT have a polling loop (asyncio.sleep)."""
        from analysi.alert_analysis.jobs.control_events import (
            _execute_workflow_rule,
        )

        tenant_id = "tenant-a"
        workflow_id = uuid4()
        input_data = {"alert_id": "123", "event_id": "evt-1", "config": {}}
        execution_context = {}
        run_id = uuid4()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        self._setup_status_check(mock_session)

        with (
            patch(
                "analysi.alert_analysis.jobs.control_events.AsyncSessionLocal",
                return_value=mock_session,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.__init__",
                return_value=None,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.create_workflow_run",
                new_callable=AsyncMock,
                return_value=run_id,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
                new_callable=AsyncMock,
            ),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await _execute_workflow_rule(
                tenant_id=tenant_id,
                workflow_id=workflow_id,
                input_data=input_data,
                execution_context=execution_context,
            )

        # Verify: no polling (asyncio.sleep should NOT be called)
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_on_failed_workflow_run_status(self):
        """_execute_workflow_rule raises when workflow ends in FAILED status
        (monitor_execution marks it failed but doesn't raise)."""
        from analysi.alert_analysis.jobs.control_events import (
            _execute_workflow_rule,
        )

        tenant_id = "tenant-a"
        workflow_id = uuid4()
        input_data = {"alert_id": "123", "event_id": "evt-1", "config": {}}
        execution_context = {}
        run_id = uuid4()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        # Status check returns FAILED
        self._setup_status_check(mock_session, status="failed")
        # Override error_message
        mock_session.execute.return_value.fetchone.return_value.error_message = (
            "Failed nodes: ['n-task-1']"
        )

        with (
            patch(
                "analysi.alert_analysis.jobs.control_events.AsyncSessionLocal",
                return_value=mock_session,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.__init__",
                return_value=None,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.create_workflow_run",
                new_callable=AsyncMock,
                return_value=run_id,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
                new_callable=AsyncMock,
                # Returns normally — the bug scenario
            ),
        ):
            with pytest.raises(RuntimeError, match="Workflow rule execution failed"):
                await _execute_workflow_rule(
                    tenant_id=tenant_id,
                    workflow_id=workflow_id,
                    input_data=input_data,
                    execution_context=execution_context,
                )

    @pytest.mark.asyncio
    async def test_raises_on_execution_failure(self):
        """_execute_workflow_rule propagates exceptions from synchronous execution."""
        from analysi.alert_analysis.jobs.control_events import (
            _execute_workflow_rule,
        )

        tenant_id = "tenant-a"
        workflow_id = uuid4()
        input_data = {"alert_id": "123", "event_id": "evt-1", "config": {}}
        execution_context = {}
        run_id = uuid4()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "analysi.alert_analysis.jobs.control_events.AsyncSessionLocal",
                return_value=mock_session,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.__init__",
                return_value=None,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.create_workflow_run",
                new_callable=AsyncMock,
                return_value=run_id,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Node n-task-1 failed"),
            ),
        ):
            with pytest.raises(RuntimeError, match="Node n-task-1 failed"):
                await _execute_workflow_rule(
                    tenant_id=tenant_id,
                    workflow_id=workflow_id,
                    input_data=input_data,
                    execution_context=execution_context,
                )

    @pytest.mark.asyncio
    async def test_commits_before_execution(self):
        """The WorkflowRun record must be committed before execution starts,
        so monitor_execution can find it without the asyncio.sleep(1.0) hack."""
        from analysi.alert_analysis.jobs.control_events import (
            _execute_workflow_rule,
        )

        tenant_id = "tenant-a"
        workflow_id = uuid4()
        input_data = {"alert_id": "123", "event_id": "evt-1", "config": {}}
        execution_context = {}
        run_id = uuid4()

        call_order = []

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        self._setup_status_check(mock_session)

        original_commit = mock_session.commit

        async def track_commit():
            call_order.append("commit")
            return await original_commit()

        mock_session.commit = track_commit

        async def track_create(self_arg, *args, **kwargs):
            call_order.append("create")
            return run_id

        async def track_execute(*args, **kwargs):
            call_order.append("execute")

        with (
            patch(
                "analysi.alert_analysis.jobs.control_events.AsyncSessionLocal",
                return_value=mock_session,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.__init__",
                return_value=None,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.create_workflow_run",
                side_effect=track_create,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
                side_effect=track_execute,
            ),
        ):
            await _execute_workflow_rule(
                tenant_id=tenant_id,
                workflow_id=workflow_id,
                input_data=input_data,
                execution_context=execution_context,
            )

        # Verify ordering: create → commit → execute
        assert call_order == ["create", "commit", "execute"]


class TestWorkflowExecutionStepDirect:
    """Tests for WorkflowExecutionStep — verifies it uses direct DB calls
    instead of REST API for execution.

    Note: WorkflowExecutionStep uses deferred imports inside execute(),
    so we patch the source modules (analysi.db.session.AsyncSessionLocal
    and analysi.services.workflow_execution.WorkflowExecutor).
    """

    @staticmethod
    def _setup_status_check(mock_session, status="completed"):
        """Configure mock session to return workflow run status for
        the post-execution status check query."""
        mock_status_row = MagicMock()
        mock_status_row.status = status
        mock_status_row.error_message = None
        mock_status_result = MagicMock()
        mock_status_result.fetchone = MagicMock(return_value=mock_status_row)
        mock_session.execute = AsyncMock(return_value=mock_status_result)

    @pytest.mark.asyncio
    async def test_executes_via_direct_service_not_rest(self):
        """WorkflowExecutionStep should call the service directly,
        not BackendAPIClient.execute_workflow (REST)."""
        from analysi.alert_analysis.steps.workflow_execution import (
            WorkflowExecutionStep,
        )

        step = WorkflowExecutionStep()
        tenant_id = "test-tenant"
        alert_id = "alert-123"
        analysis_id = "analysis-456"
        workflow_id = str(uuid4())
        run_id = uuid4()

        alert_data = {"alert_id": alert_id, "severity": "high"}

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        self._setup_status_check(mock_session)

        with (
            patch(
                "analysi.db.session.AsyncSessionLocal",
                return_value=mock_session,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.__init__",
                return_value=None,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.create_workflow_run",
                new_callable=AsyncMock,
                return_value=run_id,
            ) as mock_create,
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
                new_callable=AsyncMock,
            ) as mock_exec_sync,
        ):
            result = await step.execute(
                tenant_id,
                alert_id,
                analysis_id,
                workflow_id,
                alert_data=alert_data,
            )

        assert result == str(run_id)
        mock_create.assert_called_once()
        mock_exec_sync.assert_called_once_with(run_id)

    @pytest.mark.asyncio
    async def test_does_not_call_rest_api(self):
        """WorkflowExecutionStep must NOT use BackendAPIClient for execution.

        Verifies that the module no longer imports or uses BackendAPIClient.
        """
        from analysi.alert_analysis.steps import workflow_execution as mod

        # The module should NOT import BackendAPIClient
        assert not hasattr(mod, "BackendAPIClient"), (
            "WorkflowExecutionStep should not import BackendAPIClient"
        )

    @pytest.mark.asyncio
    async def test_passes_execution_context_with_analysis_id(self):
        """WorkflowExecutionStep passes analysis_id in execution_context
        for artifact linking."""
        from analysi.alert_analysis.steps.workflow_execution import (
            WorkflowExecutionStep,
        )

        step = WorkflowExecutionStep()
        tenant_id = "test-tenant"
        alert_id = "alert-123"
        analysis_id = "analysis-456"
        workflow_id = str(uuid4())
        run_id = uuid4()

        alert_data = {"alert_id": alert_id, "severity": "high"}

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        self._setup_status_check(mock_session)

        with (
            patch(
                "analysi.db.session.AsyncSessionLocal",
                return_value=mock_session,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.__init__",
                return_value=None,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.create_workflow_run",
                new_callable=AsyncMock,
                return_value=run_id,
            ) as mock_create,
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
                new_callable=AsyncMock,
            ),
        ):
            await step.execute(
                tenant_id,
                alert_id,
                analysis_id,
                workflow_id,
                alert_data=alert_data,
            )

        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs.get("execution_context") == {
            "analysis_id": analysis_id
        }

    @pytest.mark.asyncio
    async def test_propagates_execution_failure(self):
        """WorkflowExecutionStep raises RuntimeError when workflow execution fails."""
        from analysi.alert_analysis.steps.workflow_execution import (
            WorkflowExecutionStep,
        )

        step = WorkflowExecutionStep()
        tenant_id = "test-tenant"
        alert_id = "alert-123"
        analysis_id = "analysis-456"
        workflow_id = str(uuid4())
        run_id = uuid4()

        alert_data = {"alert_id": alert_id, "severity": "high"}

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "analysi.db.session.AsyncSessionLocal",
                return_value=mock_session,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.__init__",
                return_value=None,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.create_workflow_run",
                new_callable=AsyncMock,
                return_value=run_id,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
                new_callable=AsyncMock,
                side_effect=RuntimeError("Task node failed"),
            ),
        ):
            with pytest.raises(RuntimeError, match="Task node failed"):
                await step.execute(
                    tenant_id,
                    alert_id,
                    analysis_id,
                    workflow_id,
                    alert_data=alert_data,
                )

    @pytest.mark.asyncio
    async def test_falls_back_to_prepare_input_when_no_alert_data(self):
        """When alert_data is not provided, _prepare_workflow_input is called."""
        from analysi.alert_analysis.steps.workflow_execution import (
            WorkflowExecutionStep,
        )

        step = WorkflowExecutionStep()
        tenant_id = "test-tenant"
        alert_id = "alert-123"
        analysis_id = "analysis-456"
        workflow_id = str(uuid4())
        run_id = uuid4()

        # Mock _prepare_workflow_input
        step._prepare_workflow_input = AsyncMock(
            return_value={"alert_id": alert_id, "severity": "medium"}
        )

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        self._setup_status_check(mock_session)

        with (
            patch(
                "analysi.db.session.AsyncSessionLocal",
                return_value=mock_session,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.__init__",
                return_value=None,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.create_workflow_run",
                new_callable=AsyncMock,
                return_value=run_id,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
                new_callable=AsyncMock,
            ),
        ):
            await step.execute(
                tenant_id,
                alert_id,
                analysis_id,
                workflow_id,
                # No alert_data passed
            )

        step._prepare_workflow_input.assert_called_once_with(tenant_id, alert_id)


class TestWorkflowExecutionStepFailedRunDetection:
    """Fix for bot review comment #1: _execute_workflow_synchronously returns
    normally even when monitor_execution marks the run as FAILED (no exception).

    The step must detect the failed terminal status and raise, so the pipeline
    treats step 3 as failed instead of continuing to disposition matching.
    """

    @pytest.mark.asyncio
    async def test_raises_on_failed_workflow_run(self):
        """When workflow execution ends in FAILED status (monitor_execution
        marks it failed but doesn't raise), the step must raise RuntimeError."""
        from analysi.alert_analysis.steps.workflow_execution import (
            WorkflowExecutionStep,
        )

        step = WorkflowExecutionStep()
        workflow_id = str(uuid4())
        run_id = uuid4()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        # Mock the status check query to return FAILED
        mock_status_row = MagicMock()
        mock_status_row.status = "failed"
        mock_status_row.error_message = (
            "Failed nodes: ['n-task-1']. Error: Task timeout"
        )
        mock_result = MagicMock()
        mock_result.fetchone = MagicMock(return_value=mock_status_row)

        # We need two separate sessions — one for create, one for status check
        mock_status_session = AsyncMock()
        mock_status_session.__aenter__ = AsyncMock(return_value=mock_status_session)
        mock_status_session.__aexit__ = AsyncMock(return_value=False)
        mock_status_session.execute = AsyncMock(return_value=mock_result)

        session_call_count = 0

        def session_factory():
            nonlocal session_call_count
            session_call_count += 1
            if session_call_count == 1:
                return mock_session  # For create_workflow_run
            return mock_status_session  # For post-execution status check

        with (
            patch(
                "analysi.db.session.AsyncSessionLocal",
                side_effect=session_factory,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.__init__",
                return_value=None,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.create_workflow_run",
                new_callable=AsyncMock,
                return_value=run_id,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
                new_callable=AsyncMock,
                # Returns normally — this is the bug scenario
            ),
        ):
            with pytest.raises(RuntimeError, match="Workflow execution failed"):
                await step.execute(
                    "test-tenant",
                    "alert-123",
                    "analysis-456",
                    workflow_id,
                    alert_data={"alert_id": "alert-123"},
                )

    @pytest.mark.asyncio
    async def test_succeeds_on_completed_workflow_run(self):
        """When workflow run ends in COMPLETED status, execute returns normally."""
        from analysi.alert_analysis.steps.workflow_execution import (
            WorkflowExecutionStep,
        )

        step = WorkflowExecutionStep()
        workflow_id = str(uuid4())
        run_id = uuid4()

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        # Mock status check returns COMPLETED
        mock_status_row = MagicMock()
        mock_status_row.status = "completed"
        mock_result = MagicMock()
        mock_result.fetchone = MagicMock(return_value=mock_status_row)

        mock_status_session = AsyncMock()
        mock_status_session.__aenter__ = AsyncMock(return_value=mock_status_session)
        mock_status_session.__aexit__ = AsyncMock(return_value=False)
        mock_status_session.execute = AsyncMock(return_value=mock_result)

        session_call_count = 0

        def session_factory():
            nonlocal session_call_count
            session_call_count += 1
            if session_call_count == 1:
                return mock_session
            return mock_status_session

        with (
            patch(
                "analysi.db.session.AsyncSessionLocal",
                side_effect=session_factory,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.__init__",
                return_value=None,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.create_workflow_run",
                new_callable=AsyncMock,
                return_value=run_id,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor._execute_workflow_synchronously",
                new_callable=AsyncMock,
            ),
        ):
            result = await step.execute(
                "test-tenant",
                "alert-123",
                "analysis-456",
                workflow_id,
                alert_data={"alert_id": "alert-123"},
            )

        assert result == str(run_id)


class TestWorkflowExecutionStepStaleCache:
    """Fix for bot review comment #2: With direct DB calls, a stale cached
    workflow_id causes an IntegrityError (FK violation) instead of
    WorkflowNotFoundError, so _execute_workflow_with_retry's retry path
    is dead code.

    The step must translate FK violations on workflow_id into
    WorkflowNotFoundError so the pipeline's stale-cache retry works.
    """

    @pytest.mark.asyncio
    async def test_fk_violation_raises_workflow_not_found(self):
        """IntegrityError from create_workflow_run (stale workflow_id FK)
        should be translated to WorkflowNotFoundError."""
        from analysi.alert_analysis.steps.workflow_execution import (
            WorkflowExecutionStep,
        )
        from analysi.common.retry_config import WorkflowNotFoundError

        step = WorkflowExecutionStep()
        stale_workflow_id = str(uuid4())

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        # Simulate FK violation from create_workflow_run
        fk_error = IntegrityError(
            "INSERT INTO workflow_runs",
            params={},
            orig=Exception(
                'insert or update on table "workflow_runs" violates foreign key '
                'constraint "fk_workflow_runs_workflow_id_workflows"'
            ),
        )

        with (
            patch(
                "analysi.db.session.AsyncSessionLocal",
                return_value=mock_session,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.__init__",
                return_value=None,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.create_workflow_run",
                new_callable=AsyncMock,
                side_effect=fk_error,
            ),
        ):
            with pytest.raises(WorkflowNotFoundError) as exc_info:
                await step.execute(
                    "test-tenant",
                    "alert-123",
                    "analysis-456",
                    stale_workflow_id,
                    alert_data={"alert_id": "alert-123"},
                )

        assert exc_info.value.workflow_id == stale_workflow_id

    @pytest.mark.asyncio
    async def test_non_fk_integrity_error_propagates_as_is(self):
        """IntegrityError NOT related to workflow FK should propagate unchanged."""
        from analysi.alert_analysis.steps.workflow_execution import (
            WorkflowExecutionStep,
        )

        step = WorkflowExecutionStep()
        workflow_id = str(uuid4())

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        # Non-FK integrity error (e.g., unique constraint)
        unique_error = IntegrityError(
            "INSERT INTO workflow_runs",
            params={},
            orig=Exception(
                'duplicate key value violates unique constraint "workflow_runs_pkey"'
            ),
        )

        with (
            patch(
                "analysi.db.session.AsyncSessionLocal",
                return_value=mock_session,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.__init__",
                return_value=None,
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.create_workflow_run",
                new_callable=AsyncMock,
                side_effect=unique_error,
            ),
        ):
            with pytest.raises(IntegrityError):
                await step.execute(
                    "test-tenant",
                    "alert-123",
                    "analysis-456",
                    workflow_id,
                    alert_data={"alert_id": "alert-123"},
                )
