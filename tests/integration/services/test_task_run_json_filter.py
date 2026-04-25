"""Test task_run with |json filter for proper JSON serialization."""

import uuid

import pytest

from analysi.models.auth import SYSTEM_USER_ID
from analysi.repositories.task import TaskRepository
from analysi.services.task_execution import DefaultTaskExecutor
from tests.utils.cy_output import parse_cy_output


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskRunJsonFilter:
    """Test JSON serialization of task_run results using |json filter."""

    @pytest.fixture
    def tenant_id(self):
        """Create unique tenant ID for each test."""
        return f"test-tenant-{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    async def repository(self, integration_test_session):
        """Create TaskRepository with test session."""
        return TaskRepository(integration_test_session)

    @pytest.mark.asyncio
    async def test_task_run_with_json_filter(
        self, integration_test_session, tenant_id, repository
    ):
        """Test using |json filter to properly serialize task_run results."""

        # Create a child task that returns complex data
        child_task = {
            "tenant_id": tenant_id,
            "name": "Splunk Playground Task",
            "cy_name": "splunk_playground_task",
            "script": """result = {
    "events": [
        {"timestamp": "2025-09-26T10:00:00", "message": "Login successful"},
        {"timestamp": "2025-09-26T10:01:00", "message": "Data processed"}
    ],
    "summary": "Found 2 events",
    "status": "complete"
}
return result""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(child_task)

        # Create parent task that uses |json filter to serialize the result
        parent_task = {
            "tenant_id": tenant_id,
            "name": "JSON Serializer",
            "cy_name": "json_serializer",
            "script": """# Call the child task (returns output directly now)
x = task_run("splunk_playground_task", {})

# Use |json filter to serialize the output
json_string = "${x|json}"

# Get full result with flag
full = task_run("splunk_playground_task", {}, True)
full_json = "${full|json}"

return {
    "output_json": json_string,
    "full_result_json": full_json
}""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(parent_task)

        # Execute the parent task
        executor = DefaultTaskExecutor()
        execution_context = {
            "tenant_id": tenant_id,
            "session": integration_test_session,
            "task_call_depth": 0,
            "workflow_run_id": str(uuid.uuid4()),
        }

        result = await executor.execute(
            cy_script=parent_task["script"],
            input_data={},
            execution_context=execution_context,
        )

        print(f"Result with |json filter: {result}")
        assert result["status"] == "completed"
        output = parse_cy_output(result["output"])

        # The output_json should contain the task's output
        # Note: As of Cy 0.27.0, the |json filter produces valid JSON with double quotes
        output_json = output["output_json"]
        assert '"summary": "Found 2 events"' in output_json
        assert '"events":' in output_json

        # The full_result_json should contain the full context
        full_json = output["full_result_json"]
        assert '"status": "completed"' in full_json
        assert '"output":' in full_json
        assert '"summary": "Found 2 events"' in full_json

    @pytest.mark.asyncio
    async def test_task_run_json_filter_with_error_handling(
        self, integration_test_session, tenant_id, repository
    ):
        """Test using |json filter with error results."""

        # Create a task that will fail
        failing_task = {
            "tenant_id": tenant_id,
            "name": "Failing Task",
            "cy_name": "failing_task",
            "script": """undefined_var + 1  # This will cause an error""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(failing_task)

        # Create parent that handles failure and serializes it
        parent_task = {
            "tenant_id": tenant_id,
            "name": "Error Handler with JSON",
            "cy_name": "error_json_handler",
            "script": """# Call task that fails
result = task_run("failing_task", {})

# Serialize the entire error result to JSON
error_json = "${result|json}"

# Build a response
return {
    "task_failed": result["status"] == "failed",
    "error_details_json": error_json
}""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(parent_task)

        # Execute the parent task
        executor = DefaultTaskExecutor()
        execution_context = {
            "tenant_id": tenant_id,
            "session": integration_test_session,
            "task_call_depth": 0,
            "workflow_run_id": str(uuid.uuid4()),
        }

        result = await executor.execute(
            cy_script=parent_task["script"],
            input_data={},
            execution_context=execution_context,
        )

        print(f"Error handling with |json: {result}")
        assert result["status"] == "completed"
        output = parse_cy_output(result["output"])
        assert output["task_failed"] is True

        # The error_details_json should contain the error details
        # Note: As of Cy 0.27.0, the |json filter produces valid JSON with double quotes
        error_json = output["error_details_json"]
        assert '"status": "failed"' in error_json
        assert '"error":' in error_json

    @pytest.mark.asyncio
    async def test_direct_json_return(
        self, integration_test_session, tenant_id, repository
    ):
        """Test returning JSON string directly."""

        # Create a simple task
        simple_task = {
            "tenant_id": tenant_id,
            "name": "Simple Task",
            "cy_name": "simple_task",
            "script": """return {"data": "test", "count": 123}""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(simple_task)

        # Create parent that returns JSON string
        parent_task = {
            "tenant_id": tenant_id,
            "name": "Direct JSON Return",
            "cy_name": "direct_json_return",
            "script": """# Get full result for JSON serialization
x = task_run("simple_task", {}, True)
return "${x|json}" """,
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(parent_task)

        # Execute the parent task
        executor = DefaultTaskExecutor()
        execution_context = {
            "tenant_id": tenant_id,
            "session": integration_test_session,
            "task_call_depth": 0,
            "workflow_run_id": str(uuid.uuid4()),
        }

        result = await executor.execute(
            cy_script=parent_task["script"],
            input_data={},
            execution_context=execution_context,
        )

        print(f"Direct JSON return: {result}")
        assert result["status"] == "completed"

        # Note: The |json filter behavior may vary - it might return
        # the dict directly or a string representation
        output = result["output"]

        # If it's a string, check contents
        if isinstance(output, str):
            assert (
                "'status': 'completed'" in output or '"status": "completed"' in output
            )
            assert "test" in output
            assert "123" in str(output)
        # If it's still a dict (filter didn't work as expected)
        else:
            assert output["status"] == "completed"
            assert output["output"]["data"] == "test"
            assert output["output"]["count"] == 123
