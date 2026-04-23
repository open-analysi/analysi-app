"""Test to demonstrate task_run JSON serialization issue and solution."""

import uuid

import pytest

from analysi.models.auth import SYSTEM_USER_ID
from analysi.repositories.task import TaskRepository
from analysi.services.task_execution import DefaultTaskExecutor
from tests.utils.cy_output import parse_cy_output


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskRunJsonOutput:
    """Test JSON serialization of task_run results."""

    @pytest.fixture
    def tenant_id(self):
        """Create unique tenant ID for each test."""
        return f"test-tenant-{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    async def repository(self, integration_test_session):
        """Create TaskRepository with test session."""
        return TaskRepository(integration_test_session)

    @pytest.mark.asyncio
    async def test_task_run_json_serialization_issue(
        self, integration_test_session, tenant_id, repository
    ):
        """Test that the JSON serialization issue is now fixed."""

        # Create a child task that returns some data
        child_task = {
            "tenant_id": tenant_id,
            "name": "Data Generator",
            "cy_name": "data_generator",
            "script": """result = {"message": "Hello", "value": 42}
return result""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(child_task)

        # Create parent task that stringifies the result
        parent_task = {
            "tenant_id": tenant_id,
            "name": "Parent Task",
            "cy_name": "parent_task",
            "script": """child_result = task_run("data_generator", {})
# With new default behavior, task_run returns just the output
# So string interpolation now works correctly
stringified = "Result: message=${child_result['message']}, value=${child_result['value']}"
return stringified""",
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

        print(f"Result: {result}")
        # With the fix, no more [object Object]
        assert result["status"] == "completed"
        assert "[object Object]" not in result["output"]
        assert "message=Hello" in result["output"]
        assert "value=42" in result["output"]

    @pytest.mark.asyncio
    async def test_task_run_correct_json_access(
        self, integration_test_session, tenant_id, repository
    ):
        """Show the correct way to access task_run results."""

        # Create a child task
        child_task = {
            "tenant_id": tenant_id,
            "name": "Data Provider",
            "cy_name": "data_provider",
            "script": """data = {"message": "Hello World", "count": 100, "items": ["a", "b", "c"]}
return data""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(child_task)

        # Create parent task that correctly accesses the output
        parent_task_correct = {
            "tenant_id": tenant_id,
            "name": "Parent Correct",
            "cy_name": "parent_correct",
            "script": """# Call the child task
child_result = task_run("data_provider", {})

# With new default behavior, task_run returns the output directly
# No need to access 'output' field anymore
actual_data = child_result

# Now we can work with the actual data
message = actual_data["message"]
count = actual_data["count"]
items = actual_data["items"]

# Build a proper response
response = {
    "child_message": message,
    "child_count": count,
    "first_item": items[0],
    "summary": "Processed child task output successfully"
}

return response""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(parent_task_correct)

        # Execute the parent task
        executor = DefaultTaskExecutor()
        execution_context = {
            "tenant_id": tenant_id,
            "session": integration_test_session,
            "task_call_depth": 0,
            "workflow_run_id": str(uuid.uuid4()),
        }

        result = await executor.execute(
            cy_script=parent_task_correct["script"],
            input_data={},
            execution_context=execution_context,
        )

        print(f"Correct approach result: {result}")
        assert result["status"] == "completed"
        output = parse_cy_output(result["output"])
        assert output["child_message"] == "Hello World"
        assert output["child_count"] == 100
        assert output["first_item"] == "a"

    @pytest.mark.asyncio
    async def test_task_run_with_json_stringify_helper(
        self, integration_test_session, tenant_id, repository
    ):
        """Show how to create a JSON string from task_run results."""

        # Create a child task
        child_task = {
            "tenant_id": tenant_id,
            "name": "API Response",
            "cy_name": "api_response",
            "script": """response = {
    "status": "ok",
    "data": {"user": "alice", "role": "admin"},
    "timestamp": "2025-09-26"
}
return response""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(child_task)

        # Create parent task that needs to create a JSON string
        parent_task_json = {
            "tenant_id": tenant_id,
            "name": "JSON Logger",
            "cy_name": "json_logger",
            "script": """# Call the API task
api_result = task_run("api_response", {})

# With new default behavior, task_run returns the output directly
api_data = api_result

# If you need to create a formatted string with the data:
log_entry = {
    "event": "api_call_completed",
    "api_response": api_data,
    "processed_at": "2025-09-26T10:00:00Z"
}

# For debugging or logging, you can create a formatted string
# Note: Cy doesn't have a built-in JSON.stringify, so we format manually
summary = "API returned status: ${api_data['status']} for user: ${api_data['data']['user']}"

return {
    "log_entry": log_entry,
    "summary": summary
}""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(parent_task_json)

        # Execute the parent task
        executor = DefaultTaskExecutor()
        execution_context = {
            "tenant_id": tenant_id,
            "session": integration_test_session,
            "task_call_depth": 0,
            "workflow_run_id": str(uuid.uuid4()),
        }

        result = await executor.execute(
            cy_script=parent_task_json["script"],
            input_data={},
            execution_context=execution_context,
        )

        print(f"JSON handling result: {result}")
        assert result["status"] == "completed"
        output = parse_cy_output(result["output"])
        assert "log_entry" in output
        assert output["summary"] == "API returned status: ok for user: alice"

    @pytest.mark.asyncio
    async def test_handling_failed_task_run(
        self, integration_test_session, tenant_id, repository
    ):
        """Show how to handle errors from task_run."""

        # Create a child task that will fail
        child_task = {
            "tenant_id": tenant_id,
            "name": "Failing Task",
            "cy_name": "failing_task",
            "script": """value = 1 / 0  # This will cause an error
return value""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(child_task)

        # Create parent task that handles the failure
        parent_task = {
            "tenant_id": tenant_id,
            "name": "Error Handler",
            "cy_name": "error_handler",
            "script": """# Call task that might fail
result = task_run("failing_task", {})

# Check if the task succeeded or failed
status = result["status"]

if (status == "failed") {
    error_msg = result["error"]
    response = {
        "success": False,
        "message": "Child task failed",
        "error": error_msg
    }
} else {
    response = {
        "success": True,
        "data": result["output"]
    }
}

return response""",
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

        print(f"Error handling result: {result}")
        assert (
            result["status"] == "completed"
        )  # Parent task succeeds even if child fails
        output = parse_cy_output(result["output"])
        assert output["success"] is False
        assert "Child task failed" in output["message"]
