"""
Unit tests for task execution error propagation.

Tests that errors from integration actions are properly propagated
through the execution pipeline and result in failed task runs.

This test suite reproduces the bug where integration action errors
are marked as "completed" instead of "failed".
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.services.task_execution import DefaultTaskExecutor
from tests.utils.cy_boundary import apply_cy_adapter


class TestErrorPropagation:
    """Test error propagation from integration actions to task run status."""

    @pytest.mark.asyncio
    async def test_integration_action_error_dict_causes_task_failure(self):
        """
        Test that when an integration action returns {"status": "error"},
        the task execution fails (not succeeds).

        This reproduces the bug where error dicts are treated as successful outputs.
        """
        # Create executor
        executor = DefaultTaskExecutor()

        # Mock an integration action that returns an error dict (simulates API key failure)
        async def mock_integration_action(**kwargs):
            return {
                "status": "error",
                "error": "Invalid API key",
                "error_type": "HTTPError",
                "integration_type": "virustotal",
                "action_id": "ip_reputation",
            }

        # Create a wrapper that mimics the app tool wrapper behavior
        async def wrapped_tool(**kwargs):
            result = await mock_integration_action(**kwargs)
            # This is the error-checking logic from task_execution.py:718-721
            if isinstance(result, dict) and result.get("status") == "error":
                error_msg = result.get("error", "Unknown error")
                error_type = result.get("error_type", "IntegrationError")
                raise RuntimeError(f"{error_type}: {error_msg}")
            return result

        # Cy script that calls the failing tool
        cy_script = """
ip = "8.8.8.8"
result = app::virustotal::ip_reputation(ip=ip)
return {"result": result}
"""

        # Mock execution context
        execution_context = {
            "tenant_id": "test-tenant",
            "task_run_id": "test-run-id",
        }

        # Mock _load_app_tools to return our wrapped tool
        with patch.object(
            executor,
            "_load_app_tools",
            return_value={"app::virustotal::ip_reputation": wrapped_tool},
        ):
            # Execute the script
            result = await executor.execute(cy_script, {}, execution_context)

            # BUG: Currently returns status="completed" with error in output
            # EXPECTED: Should return status="failed" with error message
            assert result["status"] == "failed", (
                f"Expected status='failed' for integration error, "
                f"got status='{result['status']}' with output={result.get('output')}"
            )
            assert "error" in result
            assert "Invalid API key" in str(result["error"])

            # Verify error message is descriptive
            error_msg = result["error"]
            # Should include line/column info from Cy interpreter
            assert (
                "Line" in error_msg or "Column" in error_msg or "HTTPError" in error_msg
            ), f"Error should include location or error type info, got: {error_msg}"

    @pytest.mark.asyncio
    async def test_integration_action_exception_causes_task_failure(self):
        """
        Test that when an integration action raises an exception,
        the task execution fails.
        """
        executor = DefaultTaskExecutor()

        # Mock an app tool that raises an exception
        async def raising_tool(**kwargs):
            raise RuntimeError("Integration service unavailable")

        cy_script = """
result = app::test::action()
return {"result": result}
"""

        execution_context = {
            "tenant_id": "test-tenant",
            "task_run_id": "test-run-id",
        }

        with patch.object(
            executor,
            "_load_app_tools",
            return_value={"app::test::action": raising_tool},
        ):
            result = await executor.execute(cy_script, {}, execution_context)

            # Should fail, not succeed
            assert result["status"] == "failed"
            assert "error" in result
            assert "Integration service unavailable" in str(result["error"])

    @pytest.mark.asyncio
    async def test_cy_syntax_error_causes_task_failure(self):
        """
        Test that Cy syntax errors result in failed task execution.
        """
        executor = DefaultTaskExecutor()

        # Invalid Cy syntax (unclosed bracket)
        cy_script = "x = ["

        execution_context = {
            "tenant_id": "test-tenant",
            "task_run_id": "test-run-id",
        }

        result = await executor.execute(cy_script, {}, execution_context)

        # Syntax errors should fail
        assert result["status"] == "failed"
        assert "error" in result

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure_results_in_failure(self):
        """
        Test that a script with successful tool calls followed by
        a failure still results in overall task failure.
        """
        executor = DefaultTaskExecutor()

        # Mock integration actions
        async def mock_success_action(**kwargs):
            return {"status": "success", "data": "OK"}

        async def mock_failing_action(**kwargs):
            return {
                "status": "error",
                "error": "Failed operation",
                "error_type": "OperationError",
            }

        # Wrap with the canonical Cy-boundary adapter (see tests/utils/cy_boundary.py)
        async def wrapped_success(**kwargs):
            return apply_cy_adapter(await mock_success_action(**kwargs))

        async def wrapped_failure(**kwargs):
            return apply_cy_adapter(await mock_failing_action(**kwargs))

        cy_script = """
result1 = app::test::success()
result2 = app::test::failure()
return {"r1": result1, "r2": result2}
"""

        execution_context = {
            "tenant_id": "test-tenant",
            "task_run_id": "test-run-id",
        }

        with patch.object(
            executor,
            "_load_app_tools",
            return_value={
                "app::test::success": wrapped_success,
                "app::test::failure": wrapped_failure,
            },
        ):
            result = await executor.execute(cy_script, {}, execution_context)

            # Overall result should be failed due to the error
            assert result["status"] == "failed"
            assert "error" in result

    @pytest.mark.asyncio
    async def test_cy_runtime_error_output_causes_task_failure(self):
        """
        Test that when Cy successfully executes but returns {"error": "..."}
        as its output, the task should be marked as failed.

        This reproduces the actual bug found in production where tasks
        succeed but return error dicts, which then get passed downstream
        and cause merge conflicts.

        Real example from database:
        Task output: {"error": "Line 11, Col 17: Key 'device_action' not found"}
        Task status: succeeded (WRONG - should be failed!)
        """
        executor = DefaultTaskExecutor()

        # Mock the Cy interpreter to return an error dict as output
        # (simulating what happens when Cy catches an error internally)
        with patch("analysi.services.task_execution.Cy") as MockCy:
            # Mock the async context manager and run_native_async method (Cy 0.38+)
            mock_interpreter = AsyncMock()
            mock_interpreter.run_native_async = AsyncMock(
                return_value={
                    "error": "Line 11: Key 'device_action' not found in dictionary"
                }
            )

            # Mock both create_async and regular constructor
            MockCy.create_async = AsyncMock(return_value=mock_interpreter)
            MockCy.return_value = mock_interpreter
            mock_interpreter.run_native = MagicMock(
                return_value={
                    "error": "Line 11: Key 'device_action' not found in dictionary"
                }
            )

            cy_script = "# Script doesn't matter, we're mocking the output"
            input_data = {"title": "Test"}
            execution_context = {"tenant_id": "test", "task_run_id": "test"}

            result = await executor.execute(cy_script, input_data, execution_context)

            # BUG: Currently returns status="completed" with {"error": ...} in output
            # EXPECTED: Should return status="failed" with error message
            assert result["status"] == "failed", (
                f"Expected status='failed' when Cy returns error dict, "
                f"got status='{result['status']}' with output={result.get('output')}"
            )
            assert "error" in result
            assert "device_action" in str(result["error"]) or "Key" in str(
                result["error"]
            )

    @pytest.mark.asyncio
    async def test_successful_integration_action_succeeds(self):
        """
        Test that successful integration actions result in successful task execution.

        This is a sanity check to ensure we don't break the success path.
        """
        executor = DefaultTaskExecutor()

        # Mock a successful integration action
        async def mock_success_action(**kwargs):
            return {
                "status": "success",
                "ip_address": "8.8.8.8",
                "reputation_summary": {"malicious": 0, "harmless": 50},
            }

        # Wrap with the canonical Cy-boundary adapter (see tests/utils/cy_boundary.py)
        async def wrapped_success(**kwargs):
            return apply_cy_adapter(await mock_success_action(**kwargs))

        cy_script = """
ip = "8.8.8.8"
result = app::test::success_action(ip=ip)
return {"result": result}
"""

        execution_context = {
            "tenant_id": "test-tenant",
            "task_run_id": "test-run-id",
        }

        with patch.object(
            executor,
            "_load_app_tools",
            return_value={"app::test::success_action": wrapped_success},
        ):
            result = await executor.execute(cy_script, {}, execution_context)

            # Success case should still work
            assert result["status"] == "completed", (
                f"Expected status='completed' for successful integration action, "
                f"got status='{result['status']}' with error={result.get('error')}"
            )
            assert result["output"] is not None
            assert "result" in result["output"]
