"""Test task_run() with the new full_result flag."""

import uuid

import pytest

from analysi.models.auth import SYSTEM_USER_ID
from analysi.repositories.task import TaskRepository
from analysi.services.task_execution import DefaultTaskExecutor
from tests.utils.cy_output import parse_cy_output


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskRunFullResultFlag:
    """Test the full_result flag in task_run()."""

    @pytest.fixture
    def tenant_id(self):
        """Create unique tenant ID for each test."""
        return f"test-tenant-{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    async def repository(self, integration_test_session):
        """Create TaskRepository with test session."""
        return TaskRepository(integration_test_session)

    @pytest.mark.asyncio
    async def test_default_behavior_returns_output_only(
        self, integration_test_session, tenant_id, repository
    ):
        """Test that default behavior (full_result=False) returns just the output."""

        # Create a child task
        child_task = {
            "tenant_id": tenant_id,
            "name": "Data Provider",
            "cy_name": "data_provider",
            "script": """data = {
    "message": "Hello World",
    "value": 42,
    "items": ["a", "b", "c"]
}
return data""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(child_task)

        # Parent task using default behavior (no full_result flag)
        parent_default = {
            "tenant_id": tenant_id,
            "name": "Parent Default",
            "cy_name": "parent_default",
            "script": """# Call without full_result flag - should get just the output
result = task_run("data_provider", {})

# Now $result should be the actual data, not wrapped
return result""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(parent_default)

        # Execute the parent task
        executor = DefaultTaskExecutor()
        execution_context = {
            "tenant_id": tenant_id,
            "session": integration_test_session,
            "task_call_depth": 0,
            "workflow_run_id": str(uuid.uuid4()),
        }

        result = await executor.execute(
            cy_script=parent_default["script"],
            input_data={},
            execution_context=execution_context,
        )

        print(f"Default behavior result: {result}")
        assert result["status"] == "completed"

        # The output should be the data directly, not wrapped
        output = parse_cy_output(result["output"])
        assert output["message"] == "Hello World"
        assert output["value"] == 42
        assert output["items"] == ["a", "b", "c"]
        # Should NOT have status/execution_time at this level
        assert "status" not in output
        assert "execution_time" not in output

    @pytest.mark.asyncio
    async def test_full_result_flag_returns_complete_context(
        self, integration_test_session, tenant_id, repository
    ):
        """Test that full_result=True returns the complete execution context."""

        # Create a child task
        child_task = {
            "tenant_id": tenant_id,
            "name": "Timer Task",
            "cy_name": "timer_task",
            "script": """result = {"processed": True, "count": 100}
return result""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(child_task)

        # Parent task using full_result=True
        parent_full = {
            "tenant_id": tenant_id,
            "name": "Parent Full Result",
            "cy_name": "parent_full",
            "script": """# Call with full_result=True to get everything
full = task_run("timer_task", {}, True)

# Now we have access to status, execution_time, etc.
response = {
    "task_succeeded": full["status"] == "completed",
    "task_output": full["output"],
    "task_time": full["execution_time"]
}

return response""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(parent_full)

        # Execute the parent task
        executor = DefaultTaskExecutor()
        execution_context = {
            "tenant_id": tenant_id,
            "session": integration_test_session,
            "task_call_depth": 0,
            "workflow_run_id": str(uuid.uuid4()),
        }

        result = await executor.execute(
            cy_script=parent_full["script"],
            input_data={},
            execution_context=execution_context,
        )

        print(f"Full result flag test: {result}")
        assert result["status"] == "completed"

        output = parse_cy_output(result["output"])
        assert output["task_succeeded"] is True
        task_output = parse_cy_output(output["task_output"])
        assert task_output["processed"] is True
        assert task_output["count"] == 100
        assert "task_time" in output
        assert isinstance(output["task_time"], int | float)

    @pytest.mark.asyncio
    async def test_error_handling_with_default_behavior(
        self, integration_test_session, tenant_id, repository
    ):
        """Test that errors are still visible with default behavior."""

        # Create a child task that fails
        failing_task = {
            "tenant_id": tenant_id,
            "name": "Failing Task",
            "cy_name": "failing_task",
            "script": """result = 1 / 0  # This will fail
return result""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(failing_task)

        # Parent task using default behavior
        parent_error = {
            "tenant_id": tenant_id,
            "name": "Parent Error Handler",
            "cy_name": "parent_error",
            "script": """# Call task that fails - default behavior
result = task_run("failing_task", {})

# When task fails, we should still get the full error context
if (result["status"] == "failed") {
    return {
        "error_detected": True,
        "error_message": result["error"]
    }
} else {
    return {
        "error_detected": False,
        "data": result
    }
}""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(parent_error)

        # Execute the parent task
        executor = DefaultTaskExecutor()
        execution_context = {
            "tenant_id": tenant_id,
            "session": integration_test_session,
            "task_call_depth": 0,
            "workflow_run_id": str(uuid.uuid4()),
        }

        result = await executor.execute(
            cy_script=parent_error["script"],
            input_data={},
            execution_context=execution_context,
        )

        print(f"Error handling result: {result}")
        assert result["status"] == "completed"  # Parent succeeds even if child fails

        output = parse_cy_output(result["output"])
        assert output["error_detected"] is True
        assert "error_message" in output
        assert (
            "division" in output["error_message"].lower()
            or "zero" in output["error_message"].lower()
        )

    @pytest.mark.asyncio
    async def test_backwards_compatibility(
        self, integration_test_session, tenant_id, repository
    ):
        """Test that old code without the flag still works."""

        # Create tasks
        simple_task = {
            "tenant_id": tenant_id,
            "name": "Simple Task",
            "cy_name": "simple_task",
            "script": """return {"data": "test"}""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(simple_task)

        # Old-style parent task (before the flag was added)
        old_parent = {
            "tenant_id": tenant_id,
            "name": "Old Style Parent",
            "cy_name": "old_parent",
            "script": """# Old code that expects the full result
result = task_run("simple_task", {}, True)  # Explicitly request full result
data = result["output"]
return data""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(old_parent)

        # Execute the parent task
        executor = DefaultTaskExecutor()
        execution_context = {
            "tenant_id": tenant_id,
            "session": integration_test_session,
            "task_call_depth": 0,
            "workflow_run_id": str(uuid.uuid4()),
        }

        result = await executor.execute(
            cy_script=old_parent["script"],
            input_data={},
            execution_context=execution_context,
        )

        print(f"Backwards compatibility result: {result}")
        assert result["status"] == "completed"
        assert parse_cy_output(result["output"])["data"] == "test"

    @pytest.mark.asyncio
    async def test_direct_return_now_works(
        self, integration_test_session, tenant_id, repository
    ):
        """Test that direct return of task_run now works without [object Object]."""

        # Create a child task
        child_task = {
            "tenant_id": tenant_id,
            "name": "Splunk-like Task",
            "cy_name": "splunk_playground_task",
            "script": """result = {
    "spl_query": "index=main | head 10",
    "events": [{"id": 1}, {"id": 2}],
    "summary": "Found 2 events"
}
return result""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(child_task)

        # Parent that directly returns task_run result
        parent_direct = {
            "tenant_id": tenant_id,
            "name": "Direct Return Parent",
            "cy_name": "direct_parent",
            "script": """# This should now work and return the actual data
return task_run("splunk_playground_task", {})""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(parent_direct)

        # Execute the parent task
        executor = DefaultTaskExecutor()
        execution_context = {
            "tenant_id": tenant_id,
            "session": integration_test_session,
            "task_call_depth": 0,
            "workflow_run_id": str(uuid.uuid4()),
        }

        result = await executor.execute(
            cy_script=parent_direct["script"],
            input_data={},
            execution_context=execution_context,
        )

        print(f"Direct return result: {result}")
        assert result["status"] == "completed"

        # Should get the actual task data, not wrapped
        output = parse_cy_output(result["output"])
        assert output["spl_query"] == "index=main | head 10"
        assert output["summary"] == "Found 2 events"
        assert len(output["events"]) == 2
        # Should NOT have execution context at this level
        assert "status" not in output
        assert "execution_time" not in output
