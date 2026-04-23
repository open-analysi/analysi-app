"""Test to reproduce and fix the [object Object] issue when returning task_run directly."""

import uuid

import pytest

from analysi.models.auth import SYSTEM_USER_ID
from analysi.repositories.task import TaskRepository
from analysi.services.task_execution import DefaultTaskExecutor
from tests.utils.cy_output import parse_cy_output


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskRunReturnObject:
    """Test returning task_run results directly."""

    @pytest.fixture
    def tenant_id(self):
        """Create unique tenant ID for each test."""
        return f"test-tenant-{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    async def repository(self, integration_test_session):
        """Create TaskRepository with test session."""
        return TaskRepository(integration_test_session)

    @pytest.mark.asyncio
    async def test_direct_task_run_return(
        self, integration_test_session, tenant_id, repository
    ):
        """Reproduce the [object Object] issue when returning task_run directly."""

        # Create a child task similar to the user's splunk task
        child_task = {
            "tenant_id": tenant_id,
            "name": "Splunk Playground Task",
            "cy_name": "splunk_playground_triggering_event_retrieval",
            "script": """result = {
    "spl_query": "index=main | head 10",
    "events_found": 10,
    "summary": "Retrieved events successfully"
}
return result""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(child_task)

        # Test 1: Direct return of task_run (reproduces the issue)
        parent_direct = {
            "tenant_id": tenant_id,
            "name": "Direct Return",
            "cy_name": "direct_return",
            "script": """return task_run("splunk_playground_triggering_event_retrieval", {})""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(parent_direct)

        # Test 2: Return with |json filter
        parent_json = {
            "tenant_id": tenant_id,
            "name": "JSON Return",
            "cy_name": "json_return",
            "script": """x = task_run("splunk_playground_triggering_event_retrieval", {})
return "${x|json}" """,
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(parent_json)

        # Test 3: With new default behavior, result IS the output
        parent_output = {
            "tenant_id": tenant_id,
            "name": "Output Return",
            "cy_name": "output_return",
            "script": """# With new default behavior, task_run returns output directly
result = task_run("splunk_playground_triggering_event_retrieval", {})
return result""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(parent_output)

        # Execute all three approaches
        executor = DefaultTaskExecutor()
        execution_context = {
            "tenant_id": tenant_id,
            "session": integration_test_session,
            "task_call_depth": 0,
            "workflow_run_id": str(uuid.uuid4()),
        }

        # Test 1: Direct return
        result_direct = await executor.execute(
            cy_script=parent_direct["script"],
            input_data={},
            execution_context=execution_context,
        )
        print(f"\n1. Direct return: {result_direct}")
        print(f"   Output type: {type(result_direct['output'])}")
        print(f"   Output value: {result_direct['output']}")

        # Test 2: JSON filter return
        result_json = await executor.execute(
            cy_script=parent_json["script"],
            input_data={},
            execution_context=execution_context,
        )
        print(f"\n2. JSON filter return: {result_json}")
        print(f"   Output type: {type(result_json['output'])}")
        print(f"   Output value: {result_json['output']}")

        # Test 3: Output field return
        result_output = await executor.execute(
            cy_script=parent_output["script"],
            input_data={},
            execution_context=execution_context,
        )
        print(f"\n3. Output field return: {result_output}")
        print(f"   Output type: {type(result_output['output'])}")
        print(f"   Output value: {result_output['output']}")

        # Assertions
        assert result_direct["status"] == "completed"
        assert result_json["status"] == "completed"
        assert result_output["status"] == "completed"

        # With new default behavior, direct return should contain just the output
        direct_output = parse_cy_output(result_direct["output"])
        assert direct_output["summary"] == "Retrieved events successfully"
        assert direct_output["spl_query"] == "index=main | head 10"

        # The JSON filter return should also get just the output now
        # since task_run returns output by default
        json_output = parse_cy_output(result_json["output"])
        assert json_output["summary"] == "Retrieved events successfully"

        # The output return should contain the task's output directly
        output_output = parse_cy_output(result_output["output"])
        assert output_output["summary"] == "Retrieved events successfully"

    @pytest.mark.asyncio
    async def test_workaround_solutions(
        self, integration_test_session, tenant_id, repository
    ):
        """Provide workaround solutions for the [object Object] issue."""

        # Create a child task
        child_task = {
            "tenant_id": tenant_id,
            "name": "Data Provider",
            "cy_name": "data_provider",
            "script": """return {"message": "Hello World", "value": 42}""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(child_task)

        # Workaround 1: With new default, result IS already the output
        workaround1 = {
            "tenant_id": tenant_id,
            "name": "Workaround 1",
            "cy_name": "workaround1",
            "script": """# Call the task - now returns output directly by default
result = task_run("data_provider", {})

# Result is already the data, no extraction needed
return result""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(workaround1)

        # Workaround 2: If you need the full context, use full_result flag
        workaround2 = {
            "tenant_id": tenant_id,
            "name": "Workaround 2",
            "cy_name": "workaround2",
            "script": """# Call with full_result=True to get full context
full = task_run("data_provider", {}, True)

# Build a clean response
response = {
    "success": full["status"] == "completed",
    "data": full["output"],
    "execution_time": full["execution_time"]
}

return response""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(workaround2)

        # Workaround 3: Use |json filter on the output directly
        workaround3 = {
            "tenant_id": tenant_id,
            "name": "Workaround 3",
            "cy_name": "workaround3",
            "script": """# Call the task - returns output directly
result = task_run("data_provider", {})

# For logging/debugging, convert to JSON string
json_log = "${result|json}"

# Return the data with log entry
return {
    "data": result,
    "log_entry": json_log
}""",
            "created_by": str(SYSTEM_USER_ID),
        }
        await repository.create(workaround3)

        # Execute workarounds
        executor = DefaultTaskExecutor()
        execution_context = {
            "tenant_id": tenant_id,
            "session": integration_test_session,
            "task_call_depth": 0,
            "workflow_run_id": str(uuid.uuid4()),
        }

        # Test workaround 1
        result1 = await executor.execute(
            cy_script=workaround1["script"],
            input_data={},
            execution_context=execution_context,
        )
        print(f"\nWorkaround 1 (extract output): {result1}")
        assert result1["status"] == "completed"
        output1 = parse_cy_output(result1["output"])
        assert output1["message"] == "Hello World"
        assert output1["value"] == 42

        # Test workaround 2
        result2 = await executor.execute(
            cy_script=workaround2["script"],
            input_data={},
            execution_context=execution_context,
        )
        print(f"\nWorkaround 2 (build response): {result2}")
        assert result2["status"] == "completed"
        output2 = parse_cy_output(result2["output"])
        assert output2["success"] is True
        data2 = parse_cy_output(output2["data"])
        assert data2["message"] == "Hello World"

        # Test workaround 3
        result3 = await executor.execute(
            cy_script=workaround3["script"],
            input_data={},
            execution_context=execution_context,
        )
        print(f"\nWorkaround 3 (with logging): {result3}")
        assert result3["status"] == "completed"
        output3 = parse_cy_output(result3["output"])
        data3 = parse_cy_output(output3["data"])
        assert data3["message"] == "Hello World"
        assert "log_entry" in output3
