"""
Async Execution Engine Tests

Tests for task execution engine and async processing.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from analysi.models.task_run import TaskRun  # Will be created
from analysi.services.task_execution import (  # Will be created
    DefaultTaskExecutor,
    DurationCalculator,
    ExecutorConfigManager,
    TaskExecutionService,
)
from tests.utils.cy_boundary import apply_cy_adapter

MOCK_TASK_RUN_ID = uuid4()


class TestDefaultTaskExecutor:
    """Test DefaultTaskExecutor can execute simple Cy scripts."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_simple_cy_script(self):
        """Test that DefaultTaskExecutor can execute basic Cy scripts."""
        executor = DefaultTaskExecutor()

        # Test simple return statement
        cy_script = """return \"Hello World\""""
        input_data = {}

        result = await executor.execute(cy_script, input_data)

        assert result is not None
        if result["status"] != "completed":
            print(f"Error: {result}")
        assert result["status"] == "completed"
        assert result["output"] == "Hello World"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_cy_script_with_variables(self):
        """Test Cy script execution with variable manipulation."""
        executor = DefaultTaskExecutor()

        cy_script = """message = "Hello"
name = "World"
return message + " " + name
        """
        input_data = {}

        result = await executor.execute(cy_script, input_data)

        assert result["status"] == "completed"
        assert result["output"] == "Hello World"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_cy_script_with_input_data(self):
        """Test Cy script execution with input data access."""
        executor = DefaultTaskExecutor()

        cy_script = """user_name = input.name
return "Hello from Cy with data: " + user_name
        """
        input_data = {"name": "Alice"}

        result = await executor.execute(cy_script, input_data)

        assert result["status"] == "completed"
        assert result["output"] == "Hello from Cy with data: Alice"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_cy_script_error_handling(self):
        """Test Cy script execution error handling."""
        executor = DefaultTaskExecutor()

        # Script that causes an exception - invalid syntax
        cy_script = """invalid syntax here [broken
        """
        input_data = {}

        result = await executor.execute(cy_script, input_data)

        assert result["status"] == "failed"
        assert "error" in result
        assert result["output"] is None


class TestTaskExecutionService:
    """Test TaskExecutionService queues and processes tasks asynchronously."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_queue_task_for_execution(self):
        """Test that tasks can be queued for async execution."""
        execution_service = TaskExecutionService()

        # Mock TaskRun
        task_run = Mock(spec=TaskRun)
        task_run.id = MOCK_TASK_RUN_ID
        task_run.cy_script = "return 'test'"
        task_run.status = "running"

        # Queue the task
        await execution_service.queue_task(task_run)

        # Verify task was added to queue
        assert execution_service.has_queued_tasks()
        assert execution_service.queue_size() == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_single_task_calls_executor(self):
        """Test that _execute_task_with_session calls the executor and returns result."""
        execution_service = TaskExecutionService()

        # Mock TaskRun
        task_run = Mock(spec=TaskRun)
        task_run.id = MOCK_TASK_RUN_ID
        task_run.cy_script = "return 'async test'"
        task_run.status = "running"
        task_run.task_id = None  # For ad-hoc execution
        task_run.tenant_id = "test-tenant"
        task_run.execution_context = None  # No workflow context
        task_run.workflow_run_id = None

        # Mock the executor
        mock_executor = AsyncMock()
        mock_executor.execute.return_value = {
            "status": "completed",
            "output": "async test",
        }

        mock_session = AsyncMock()

        # Mock the TaskRunService and its methods
        with (
            patch.object(execution_service, "executor", mock_executor),
            patch(
                "analysi.services.task_run.TaskRunService"
            ) as mock_task_service_class,
        ):
            mock_task_service = mock_task_service_class.return_value
            mock_task_service.retrieve_input_data = AsyncMock(return_value={})

            # Test via _execute_task_with_session (the core logic method)
            result = await execution_service._execute_task_with_session(
                task_run, mock_session
            )

            # Verify executor was called with execution context
            mock_executor.execute.assert_called_once()
            call_args = mock_executor.execute.call_args[0]
            assert call_args[0] == "return 'async test'"  # cy_script
            assert call_args[1] == {}  # input_data
            assert isinstance(call_args[2], dict)  # execution_context
            assert "task_run_id" in call_args[2]
            assert "tenant_id" in call_args[2]

            # Verify result is a TaskExecutionResult
            from analysi.schemas.task_execution import TaskExecutionStatus

            assert result.status == TaskExecutionStatus.COMPLETED
            assert result.output_data == "async test"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_task_processing(self):
        """Test that multiple tasks can be processed concurrently."""
        execution_service = TaskExecutionService()

        # Create multiple mock task runs
        task_runs = []
        for i in range(3):
            task_run = Mock(spec=TaskRun)
            task_run.id = uuid4()
            task_run.cy_script = f"return 'task-{i}'"
            task_run.status = "running"
            task_runs.append(task_run)

        # Queue all tasks
        for task_run in task_runs:
            await execution_service.queue_task(task_run)

        assert execution_service.queue_size() == 3

        # Process all tasks concurrently
        start_time = datetime.now(UTC)
        await execution_service.process_queue()
        end_time = datetime.now(UTC)

        # Verify all tasks were processed
        assert execution_service.queue_size() == 0

        # Processing should be relatively fast due to concurrency
        processing_time = (end_time - start_time).total_seconds()
        assert processing_time < 5.0  # Should complete quickly


class TestTaskStatusTransitions:
    """Verify task status transitions: running -> completed/failed."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_status_transition_running_to_succeeded(self):
        """_execute_task_with_session returns COMPLETED result on success."""
        execution_service = TaskExecutionService()

        task_run = Mock(spec=TaskRun)
        task_run.id = MOCK_TASK_RUN_ID
        task_run.cy_script = "return 'success'"
        task_run.status = "running"
        task_run.task_id = None
        task_run.tenant_id = "test-tenant"
        task_run.execution_context = None
        task_run.workflow_run_id = None

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = {
            "status": "completed",
            "output": "success result",
        }

        mock_session = AsyncMock()

        with (
            patch.object(execution_service, "executor", mock_executor),
            patch(
                "analysi.services.task_run.TaskRunService"
            ) as mock_task_service_class,
        ):
            mock_task_service = mock_task_service_class.return_value
            mock_task_service.retrieve_input_data = AsyncMock(return_value={})

            result = await execution_service._execute_task_with_session(
                task_run, mock_session
            )

            from analysi.schemas.task_execution import TaskExecutionStatus

            assert result.status == TaskExecutionStatus.COMPLETED
            assert result.output_data == "success result"
            assert result.error_message is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_status_transition_running_to_failed(self):
        """_execute_task_with_session returns FAILED result on executor failure."""
        execution_service = TaskExecutionService()

        task_run = Mock(spec=TaskRun)
        task_run.id = MOCK_TASK_RUN_ID
        task_run.cy_script = "return 'failure'"
        task_run.status = "running"
        task_run.task_id = None
        task_run.tenant_id = "test-tenant"
        task_run.execution_context = None
        task_run.workflow_run_id = None

        mock_executor = AsyncMock()
        mock_executor.execute.return_value = {
            "status": "failed",
            "error": "Execution error",
        }

        mock_session = AsyncMock()

        with (
            patch.object(execution_service, "executor", mock_executor),
            patch(
                "analysi.services.task_run.TaskRunService"
            ) as mock_task_service_class,
        ):
            mock_task_service = mock_task_service_class.return_value
            mock_task_service.retrieve_input_data = AsyncMock(return_value={})

            result = await execution_service._execute_task_with_session(
                task_run, mock_session
            )

            from analysi.schemas.task_execution import TaskExecutionStatus

            assert result.status == TaskExecutionStatus.FAILED
            assert result.error_message == "Execution error"
            assert result.output_data is None


class TestExecutorConfiguration:
    """Test executor configuration comes from environment variables."""

    @pytest.mark.unit
    def test_load_executor_config_from_environment(self):
        """Test that executor configuration is loaded from environment variables."""
        # Mock environment variables
        env_vars = {
            "TASK_EXECUTOR_WORKERS": "4",
            "TASK_EXECUTOR_TIMEOUT": "120",
            "ENABLED_EXECUTORS": "default,parallel",
        }

        with patch.dict("os.environ", env_vars):
            config = ExecutorConfigManager.load_from_env()

            assert config["threads"] == 4
            assert config["timeout"] == 120
            assert config["enabled_executors"] == ["default", "parallel"]

    @pytest.mark.unit
    def test_executor_config_defaults(self):
        """Test that executor configuration has sensible defaults."""
        # Clear environment variables
        with patch.dict("os.environ", {}, clear=True):
            config = ExecutorConfigManager.load_from_env()

            # Should have defaults
            assert config["threads"] >= 1
            assert config["timeout"] > 0
            assert "default" in config["enabled_executors"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execution_service_respects_thread_limit(self):
        """Test that execution service respects thread limit configuration."""
        # Mock environment with thread limit
        with patch.dict("os.environ", {"TASK_EXECUTOR_WORKERS": "2"}):
            execution_service = TaskExecutionService()

            # Verify thread pool size matches configuration
            assert execution_service.max_workers == 2


class TestDurationCalculation:
    """Test duration field calculation (started_at to completed_at interval)."""

    @pytest.mark.unit
    def test_calculate_duration_from_timestamps(self):
        """Test duration calculation from start and end timestamps."""
        start_time = datetime(2025, 8, 14, 10, 0, 0, tzinfo=UTC)
        end_time = datetime(
            2025, 8, 14, 10, 2, 30, tzinfo=UTC
        )  # 2 minutes 30 seconds later

        duration = DurationCalculator.calculate(start_time, end_time)

        # Duration should be a timedelta or interval representation
        assert duration is not None

        # Should represent 2 minutes 30 seconds
        if isinstance(duration, timedelta):
            assert duration.total_seconds() == 150.0
        else:
            # If it's a PostgreSQL interval string
            assert "00:02:30" in str(duration)

    @pytest.mark.unit
    def test_calculate_duration_handles_none_values(self):
        """Test duration calculation handles None values gracefully."""
        start_time = datetime(2025, 8, 14, 10, 0, 0, tzinfo=UTC)

        # End time is None (task still running)
        duration = DurationCalculator.calculate(start_time, None)
        assert duration is None

        # Start time is None (invalid state)
        duration = DurationCalculator.calculate(None, datetime.now(UTC))
        assert duration is None

    @pytest.mark.unit
    def test_calculate_duration_negative_intervals(self):
        """Test duration calculation handles negative intervals."""
        start_time = datetime(2025, 8, 14, 10, 2, 0, tzinfo=UTC)
        end_time = datetime(2025, 8, 14, 10, 0, 0, tzinfo=UTC)  # End before start

        duration = DurationCalculator.calculate(start_time, end_time)

        # Should handle invalid intervals gracefully
        assert duration is None or duration.total_seconds() == 0


class TestAppToolWrapper:
    """Test app tool wrapper handles both positional and keyword arguments."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_tool_wrapper_accepts_keyword_arguments(self):
        """Test that tool wrapper accepts keyword arguments."""
        from analysi.integrations.framework.models import ActionDefinition

        # Mock action definition with params_schema
        action_def = ActionDefinition(
            id="test_action",
            type="tool",
            categories=["testing"],
            params_schema={
                "type": "object",
                "properties": {
                    "param1": {"type": "string"},
                    "param2": {"type": "integer"},
                },
                "required": ["param1"],
            },
        )

        # Mock integration service
        mock_integration_service = AsyncMock()
        mock_integration_service.execute_action = AsyncMock(
            return_value={"status": "success", "result": "test"}
        )

        mock_integration_repo = Mock()
        mock_credential_repo = Mock()

        # Simulate creating the tool wrapper
        from analysi.services.task_execution import DefaultTaskExecutor

        DefaultTaskExecutor()

        # Create wrapper using the same pattern as _load_app_tools
        async def create_tool_wrapper(
            int_type: str,
            act_id: str,
            act_def: ActionDefinition,
            int_id: str,
            ten_id: str,
            int_svc,
            int_repo,
            cred_repo,
            cred_id,
        ):
            cached_int_id = int_id
            cached_cred_id = cred_id

            async def tool_wrapper(*args, **kwargs):
                nonlocal cached_int_id, cached_cred_id

                # Map positional args to params
                params = kwargs.copy()
                if args and act_def.metadata and "params_schema" in act_def.metadata:
                    schema = act_def.metadata["params_schema"]
                    if "properties" in schema:
                        param_names = list(schema["properties"].keys())
                        for i, arg in enumerate(args):
                            if i < len(param_names):
                                params[param_names[i]] = arg

                result = await int_svc.execute_action(
                    tenant_id=ten_id,
                    integration_id=cached_int_id,
                    integration_type=int_type,
                    action_id=act_id,
                    credential_id=cached_cred_id,
                    params=params,
                )
                return result

            return tool_wrapper

        wrapper = await create_tool_wrapper(
            "test_integration",
            "test_action",
            action_def,
            "test-int-123",
            "test-tenant",
            mock_integration_service,
            mock_integration_repo,
            mock_credential_repo,
            "cred-123",
        )

        # Call with keyword arguments
        result = await wrapper(param1="value1", param2=42)

        assert result["status"] == "success"
        mock_integration_service.execute_action.assert_called_once()
        call_kwargs = mock_integration_service.execute_action.call_args.kwargs
        assert call_kwargs["params"]["param1"] == "value1"
        assert call_kwargs["params"]["param2"] == 42

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_tool_wrapper_accepts_positional_arguments(self):
        """Test that tool wrapper accepts positional arguments and maps them correctly."""
        from analysi.integrations.framework.models import ActionDefinition

        # Mock action definition with params_schema
        action_def = ActionDefinition(
            id="generate_spl",
            type="tool",
            categories=["query"],
            params_schema={
                "type": "object",
                "properties": {
                    "alert": {"type": "object"},
                    "lookback_seconds": {"type": "integer"},
                },
                "required": ["alert"],
            },
        )

        # Mock integration service
        mock_integration_service = AsyncMock()
        mock_integration_service.execute_action = AsyncMock(
            return_value={"status": "success", "spl": "search index=main"}
        )

        mock_integration_repo = Mock()
        mock_credential_repo = Mock()

        # Create wrapper using the same pattern as _load_app_tools
        async def create_tool_wrapper(
            int_type: str,
            act_id: str,
            act_def: ActionDefinition,
            int_id: str,
            ten_id: str,
            int_svc,
            int_repo,
            cred_repo,
            cred_id,
        ):
            cached_int_id = int_id
            cached_cred_id = cred_id

            async def tool_wrapper(*args, **kwargs):
                nonlocal cached_int_id, cached_cred_id

                # Map positional args to params
                params = kwargs.copy()
                if args and act_def.metadata and "params_schema" in act_def.metadata:
                    schema = act_def.metadata["params_schema"]
                    if "properties" in schema:
                        param_names = list(schema["properties"].keys())
                        for i, arg in enumerate(args):
                            if i < len(param_names):
                                params[param_names[i]] = arg

                result = await int_svc.execute_action(
                    tenant_id=ten_id,
                    integration_id=cached_int_id,
                    integration_type=int_type,
                    action_id=act_id,
                    credential_id=cached_cred_id,
                    params=params,
                )
                return result

            return tool_wrapper

        wrapper = await create_tool_wrapper(
            "splunk",
            "generate_spl",
            action_def,
            "splunk-main",
            "test-tenant",
            mock_integration_service,
            mock_integration_repo,
            mock_credential_repo,
            "cred-123",
        )

        # Call with positional argument (like Cy script: generate_triggering_events_spl($alert))
        alert_data = {"id": "alert-123", "severity": "high"}
        result = await wrapper(alert_data)

        assert result["status"] == "success"
        mock_integration_service.execute_action.assert_called_once()
        call_kwargs = mock_integration_service.execute_action.call_args.kwargs
        assert call_kwargs["params"]["alert"] == alert_data

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_tool_wrapper_accepts_mixed_arguments(self):
        """Test that tool wrapper accepts both positional and keyword arguments."""
        from analysi.integrations.framework.models import ActionDefinition

        # Mock action definition with params_schema
        action_def = ActionDefinition(
            id="test_action",
            type="tool",
            categories=["testing"],
            params_schema={
                "type": "object",
                "properties": {
                    "param1": {"type": "string"},
                    "param2": {"type": "integer"},
                    "param3": {"type": "boolean"},
                },
                "required": ["param1"],
            },
        )

        # Mock integration service
        mock_integration_service = AsyncMock()
        mock_integration_service.execute_action = AsyncMock(
            return_value={"status": "success"}
        )

        mock_integration_repo = Mock()
        mock_credential_repo = Mock()

        # Create wrapper
        async def create_tool_wrapper(
            int_type: str,
            act_id: str,
            act_def: ActionDefinition,
            int_id: str,
            ten_id: str,
            int_svc,
            int_repo,
            cred_repo,
            cred_id,
        ):
            cached_int_id = int_id
            cached_cred_id = cred_id

            async def tool_wrapper(*args, **kwargs):
                nonlocal cached_int_id, cached_cred_id

                # Map positional args to params
                params = kwargs.copy()
                if args and act_def.metadata and "params_schema" in act_def.metadata:
                    schema = act_def.metadata["params_schema"]
                    if "properties" in schema:
                        param_names = list(schema["properties"].keys())
                        for i, arg in enumerate(args):
                            if i < len(param_names):
                                params[param_names[i]] = arg

                result = await int_svc.execute_action(
                    tenant_id=ten_id,
                    integration_id=cached_int_id,
                    integration_type=int_type,
                    action_id=act_id,
                    credential_id=cached_cred_id,
                    params=params,
                )
                return result

            return tool_wrapper

        wrapper = await create_tool_wrapper(
            "test_integration",
            "test_action",
            action_def,
            "test-int-123",
            "test-tenant",
            mock_integration_service,
            mock_integration_repo,
            mock_credential_repo,
            "cred-123",
        )

        # Call with mixed positional and keyword arguments
        result = await wrapper("value1", param3=True)

        assert result["status"] == "success"
        mock_integration_service.execute_action.assert_called_once()
        call_kwargs = mock_integration_service.execute_action.call_args.kwargs
        assert call_kwargs["params"]["param1"] == "value1"
        assert call_kwargs["params"]["param3"] is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_tool_wrapper_unwraps_successful_results_with_single_field(self):
        """Test that tool wrapper unwraps successful results to maintain Cy function compatibility."""
        from analysi.integrations.framework.models import ActionDefinition

        # Mock action definition
        action_def = ActionDefinition(
            id="generate_spl",
            type="tool",
            categories=["query"],
            params_schema={
                "type": "object",
                "properties": {"alert": {"type": "object"}},
                "required": ["alert"],
            },
        )

        # Mock integration service returns framework-style dict
        mock_integration_service = AsyncMock()
        mock_integration_service.execute_action = AsyncMock(
            return_value={
                "status": "success",
                "timestamp": "2026-04-26T00:00:00Z",
                "spl_query": "search index=main",  # Single data field
            }
        )

        mock_integration_repo = Mock()
        mock_credential_repo = Mock()

        # Create wrapper
        async def create_tool_wrapper(
            int_type: str,
            act_id: str,
            act_def: ActionDefinition,
            int_id: str,
            ten_id: str,
            int_svc,
            int_repo,
            cred_repo,
            cred_id,
            sess,
        ):
            cached_int_id = int_id
            cached_cred_id = cred_id

            async def tool_wrapper(*args, **kwargs):
                nonlocal cached_int_id, cached_cred_id

                params = kwargs.copy()
                if args and act_def.metadata and "params_schema" in act_def.metadata:
                    schema = act_def.metadata["params_schema"]
                    if "properties" in schema:
                        param_names = list(schema["properties"].keys())
                        for i, arg in enumerate(args):
                            if i < len(param_names):
                                params[param_names[i]] = arg

                result = await int_svc.execute_action(
                    tenant_id=ten_id,
                    integration_id=cached_int_id,
                    integration_type=int_type,
                    action_id=act_id,
                    credential_id=cached_cred_id,
                    params=params,
                    session=sess,
                )

                return apply_cy_adapter(result)

            return tool_wrapper

        wrapper = await create_tool_wrapper(
            "splunk",
            "generate_spl",
            action_def,
            "splunk-main",
            "test-tenant",
            mock_integration_service,
            mock_integration_repo,
            mock_credential_repo,
            "cred-123",
            None,
        )

        # Call wrapper - should return unwrapped string, not dict
        alert_data = {"id": "alert-123"}
        result = await wrapper(alert_data)

        # Should return just the spl_query string (like original Cy function)
        assert result == "search index=main"
        assert not isinstance(result, dict)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_tool_wrapper_raises_exception_for_error_results(self):
        """Test that tool wrapper raises exceptions for error results (backward compatibility).

        Original Cy functions raised exceptions on errors. Integration actions return error dicts.
        Tool wrapper must convert error dicts to exceptions to maintain backward compatibility.
        """
        from analysi.integrations.framework.models import ActionDefinition

        action_def = ActionDefinition(
            id="test_action",
            type="tool",
            categories=["testing"],
            params_schema={
                "type": "object",
                "properties": {"param1": {"type": "string"}},
                "required": ["param1"],
            },
        )

        # Mock integration service returns error dict
        mock_integration_service = AsyncMock()
        mock_integration_service.execute_action = AsyncMock(
            return_value={
                "status": "error",
                "error": "Something went wrong",
                "error_type": "ValidationError",
            }
        )

        mock_integration_repo = Mock()
        mock_credential_repo = Mock()

        # Create wrapper with same logic as production code
        async def create_tool_wrapper(
            int_type: str,
            act_id: str,
            act_def: ActionDefinition,
            int_id: str,
            ten_id: str,
            int_svc,
            int_repo,
            cred_repo,
            cred_id,
            sess,
        ):
            cached_int_id = int_id
            cached_cred_id = cred_id

            async def tool_wrapper(*args, **kwargs):
                nonlocal cached_int_id, cached_cred_id

                params = kwargs.copy()
                if args and act_def.metadata and "params_schema" in act_def.metadata:
                    schema = act_def.metadata["params_schema"]
                    if "properties" in schema:
                        param_names = list(schema["properties"].keys())
                        for i, arg in enumerate(args):
                            if i < len(param_names):
                                params[param_names[i]] = arg

                result = await int_svc.execute_action(
                    tenant_id=ten_id,
                    integration_id=cached_int_id,
                    integration_type=int_type,
                    action_id=act_id,
                    credential_id=cached_cred_id,
                    params=params,
                    session=sess,
                )

                return apply_cy_adapter(result)

            return tool_wrapper

        wrapper = await create_tool_wrapper(
            "test_integration",
            "test_action",
            action_def,
            "test-int-123",
            "test-tenant",
            mock_integration_service,
            mock_integration_repo,
            mock_credential_repo,
            "cred-123",
            None,
        )

        # Call wrapper - should raise RuntimeError (like original Cy functions)
        with pytest.raises(RuntimeError) as exc_info:
            await wrapper(param1="test")

        # Verify exception message includes error type and message
        assert "ValidationError" in str(exc_info.value)
        assert "Something went wrong" in str(exc_info.value)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_tool_wrapper_unwraps_multi_field_success_results(self):
        """Test that tool wrapper unwraps successful results with multiple data fields."""
        from analysi.integrations.framework.models import ActionDefinition

        action_def = ActionDefinition(
            id="ip_reputation",
            type="tool",
            categories=["threat_intel"],
            params_schema={
                "type": "object",
                "properties": {"ip_address": {"type": "string"}},
                "required": ["ip_address"],
            },
        )

        # Mock integration service returns success dict with multiple data fields
        mock_integration_service = AsyncMock()
        mock_integration_service.execute_action = AsyncMock(
            return_value={
                "status": "success",
                "timestamp": "2026-04-26T00:00:00Z",
                "ip_address": "8.8.8.8",
                "reputation_summary": {
                    "malicious": 0,
                    "suspicious": 0,
                    "harmless": 80,
                    "undetected": 0,
                },
                "network_info": {"country": "US", "asn": "AS15169"},
            }
        )

        mock_integration_repo = Mock()
        mock_credential_repo = Mock()

        # Create wrapper
        async def create_tool_wrapper(
            int_type: str,
            act_id: str,
            act_def: ActionDefinition,
            int_id: str,
            ten_id: str,
            int_svc,
            int_repo,
            cred_repo,
            cred_id,
            sess,
        ):
            cached_int_id = int_id
            cached_cred_id = cred_id

            async def tool_wrapper(*args, **kwargs):
                nonlocal cached_int_id, cached_cred_id

                params = kwargs.copy()
                if args and act_def.metadata and "params_schema" in act_def.metadata:
                    schema = act_def.metadata["params_schema"]
                    if "properties" in schema:
                        param_names = list(schema["properties"].keys())
                        for i, arg in enumerate(args):
                            if i < len(param_names):
                                params[param_names[i]] = arg

                result = await int_svc.execute_action(
                    tenant_id=ten_id,
                    integration_id=cached_int_id,
                    integration_type=int_type,
                    action_id=act_id,
                    credential_id=cached_cred_id,
                    params=params,
                    session=sess,
                )

                # Backward compatibility logic
                if isinstance(result, dict):
                    if result.get("status") == "error":
                        error_msg = result.get("error", "Unknown error")
                        error_type = result.get("error_type", "IntegrationError")
                        raise RuntimeError(f"{error_type}: {error_msg}")

                    if result.get("status") == "success":
                        unwrapped = {
                            k: v
                            for k, v in result.items()
                            if k not in ["status", "timestamp"]
                        }
                        if len(unwrapped) == 1:
                            return next(iter(unwrapped.values()))
                        return unwrapped if unwrapped else result

                return result

            return tool_wrapper

        wrapper = await create_tool_wrapper(
            "virustotal",
            "ip_reputation",
            action_def,
            "virustotal-main",
            "test-tenant",
            mock_integration_service,
            mock_integration_repo,
            mock_credential_repo,
            "cred-123",
            None,
        )

        # Call wrapper
        result = await wrapper(ip_address="8.8.8.8")

        # Should return dict without status/timestamp (multiple fields remain)
        assert isinstance(result, dict)
        assert "status" not in result
        assert "timestamp" not in result
        assert result["ip_address"] == "8.8.8.8"
        assert "reputation_summary" in result
        assert "network_info" in result
        assert result["reputation_summary"]["harmless"] == 80

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_tool_wrapper_merges_siblings_into_unwrapped_data(self):
        """When an action returns {status, data, ...siblings}, Cy sees `data` flattened
        with its siblings merged in.

        This preserves idioms like `success_result(not_found=True, data={...})` — the
        `not_found` flag reaches Cy as a top-level field.
        """
        # Mock ad_ldap::run_query shape: {status, data, total_objects}
        mock_integration_service = AsyncMock()
        mock_integration_service.execute_action = AsyncMock(
            return_value={
                "status": "success",
                "data": {"entries": [{"dn": "cn=alice", "attributes": {}}]},
                "total_objects": 1,
            }
        )

        async def tool_wrapper(*args, **kwargs):
            result = await mock_integration_service.execute_action(
                tenant_id="t",
                integration_id="i",
                integration_type="ad_ldap",
                action_id="run_query",
                credential_id="c",
                params=kwargs,
                session=None,
            )
            return apply_cy_adapter(result)

        result = await tool_wrapper()

        # Cy sees data fields AND siblings flattened at the top level
        assert isinstance(result, dict)
        assert "entries" in result
        assert result["entries"][0]["dn"] == "cn=alice"
        assert result["total_objects"] == 1  # sibling preserved via merge
        assert "status" not in result
        assert "data" not in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_tool_wrapper_preserves_not_found_flag(self):
        """The `not_found=True` idiom (success_result(not_found=True, data=X)) must
        reach Cy as a top-level flag.

        196 call sites across 53 integrations rely on this pattern for read actions
        (lookup, get, search, query) when the resource doesn't exist.
        """
        # Shape produced by success_result(not_found=True, data={"ip": ip})
        mock_integration_service = AsyncMock()
        mock_integration_service.execute_action = AsyncMock(
            return_value={
                "status": "success",
                "timestamp": "2026-04-26T00:00:00Z",
                "integration_id": "virustotal-main",
                "action_id": "ip_reputation",
                "data": {"ip": "192.168.1.1"},
                "not_found": True,
            }
        )

        async def tool_wrapper(*args, **kwargs):
            result = await mock_integration_service.execute_action(
                tenant_id="t",
                integration_id="i",
                integration_type="virustotal",
                action_id="ip_reputation",
                credential_id="c",
                params=kwargs,
                session=None,
            )
            return apply_cy_adapter(result)

        result = await tool_wrapper()

        # Cy can branch on result.not_found — a core idiom for read actions
        assert result["not_found"] is True
        assert result["ip"] == "192.168.1.1"
        assert "status" not in result
        assert "integration_id" not in result
        assert "data" not in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_tool_wrapper_returns_list_payload_directly(self):
        """When `data` is a list (not a dict), return it as-is. Siblings are rare
        in this shape and cannot be merged — callers expect the list.
        """
        mock_integration_service = AsyncMock()
        mock_integration_service.execute_action = AsyncMock(
            return_value={
                "status": "success",
                "data": [{"id": 1}, {"id": 2}, {"id": 3}],
            }
        )

        async def tool_wrapper(*args, **kwargs):
            result = await mock_integration_service.execute_action(
                tenant_id="t",
                integration_id="i",
                integration_type="x",
                action_id="list_items",
                credential_id="c",
                params=kwargs,
                session=None,
            )
            return apply_cy_adapter(result)

        result = await tool_wrapper()

        assert result == [{"id": 1}, {"id": 2}, {"id": 3}]
