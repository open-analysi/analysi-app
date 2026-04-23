"""Test task composition - tasks calling other tasks."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.repositories.task import TaskRepository
from analysi.services.task_execution import DefaultTaskExecutor
from tests.utils.cy_output import parse_cy_output


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskComposition:
    """Test tasks calling other tasks via task_run()."""

    @pytest.fixture
    def tenant_id(self):
        """Create unique tenant ID for each test."""
        return f"test-tenant-{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    async def setup_simple_tasks(
        self, integration_test_session: AsyncSession, tenant_id: str
    ):
        """Create three simple tasks for composition testing."""
        task_repo = TaskRepository(integration_test_session)

        # Task 1: Returns 1
        task1_data = {
            "tenant_id": tenant_id,
            "name": "Return One Task",
            "cy_name": "return_one",
            "script": "return 1",
            "description": "Simple task that returns 1",
            "app": "test_app",
        }
        task1 = await task_repo.create(task1_data)

        # Task 2: Returns 2
        task2_data = {
            "tenant_id": tenant_id,
            "name": "Return Two Task",
            "cy_name": "return_two",
            "script": "return 2",
            "description": "Simple task that returns 2",
            "app": "test_app",
        }
        task2 = await task_repo.create(task2_data)

        # Task 3: Calls task1 and task2, adds results
        task3_data = {
            "tenant_id": tenant_id,
            "name": "Add Tasks Task",
            "cy_name": "add_tasks",
            "script": """
# Call the first task
result1 = task_run("return_one", {})

# Call the second task
result2 = task_run("return_two", {})

# Add the results
total = result1 + result2

return total
""",
            "description": "Task that calls two other tasks and adds their results",
            "app": "test_app",
        }
        task3 = await task_repo.create(task3_data)

        await integration_test_session.commit()
        return task1, task2, task3

    @pytest.mark.asyncio
    async def test_simple_task_composition(
        self, integration_test_session: AsyncSession, tenant_id: str, setup_simple_tasks
    ):
        """Test that a task can call two other tasks and combine their results."""
        task1, task2, task3 = setup_simple_tasks

        # Create execution context for the main task
        execution_context = {
            "task_id": str(task3.component_id),
            "tenant_id": tenant_id,
            "app": "test_app",
            "session": integration_test_session,
        }

        # Execute the main task (which calls the other two)
        executor = DefaultTaskExecutor()
        result = await executor.execute(task3.script, {}, execution_context)

        # Verify the result
        assert result["status"] == "completed"
        assert result["output"] == 3  # 1 + 2 = 3

    @pytest.mark.asyncio
    async def test_task_composition_with_parameters(
        self, integration_test_session: AsyncSession, tenant_id: str
    ):
        """Test task composition with input parameters."""
        task_repo = TaskRepository(integration_test_session)

        # Task 1: Multiplies input by 2
        task1_data = {
            "tenant_id": tenant_id,
            "name": "Multiply By Two",
            "cy_name": "multiply_by_two",
            "script": """
value = input["value"]
return value * 2
""",
            "description": "Multiplies input by 2",
            "app": "math_app",
        }
        await task_repo.create(task1_data)

        # Task 2: Adds 10 to input
        task2_data = {
            "tenant_id": tenant_id,
            "name": "Add Ten",
            "cy_name": "add_ten",
            "script": """
value = input["value"]
return value + 10
""",
            "description": "Adds 10 to input",
            "app": "math_app",
        }
        await task_repo.create(task2_data)

        # Task 3: Orchestrates the other tasks
        task3_data = {
            "tenant_id": tenant_id,
            "name": "Process Number",
            "cy_name": "process_number",
            "script": """
# Get initial value from input
initial_value = input["number"]

# First, multiply by 2
doubled = task_run("multiply_by_two", {"value": initial_value})

# Then add 10 to the doubled value
final = task_run("add_ten", {"value": doubled})

# Return both intermediate and final results
return {
    "initial": initial_value,
    "doubled": doubled,
    "final": final
}
""",
            "description": "Processes a number through multiple tasks",
            "app": "math_app",
        }
        task3 = await task_repo.create(task3_data)

        await integration_test_session.commit()

        # Execute the orchestrator task with input
        execution_context = {
            "task_id": str(task3.component_id),
            "tenant_id": tenant_id,
            "app": "math_app",
            "session": integration_test_session,
        }

        executor = DefaultTaskExecutor()
        result = await executor.execute(task3.script, {"number": 5}, execution_context)

        # Verify the results
        if result["status"] != "completed":
            print(f"Task failed with error: {result.get('error', 'Unknown error')}")
            print(f"Full result: {result}")
        assert result["status"] == "completed"
        output = parse_cy_output(result["output"])
        assert output["initial"] == 5
        assert output["doubled"] == 10  # 5 * 2
        assert output["final"] == 20  # 10 + 10

    @pytest.mark.asyncio
    async def test_cross_app_task_composition(
        self, integration_test_session: AsyncSession, tenant_id: str
    ):
        """Test that tasks can call tasks from different apps."""
        task_repo = TaskRepository(integration_test_session)

        # Task in app1
        task1_data = {
            "tenant_id": tenant_id,
            "name": "App1 Task",
            "cy_name": "app1_task",
            "script": 'return "Hello from App1"',
            "description": "Task in App1",
            "app": "app1",
        }
        await task_repo.create(task1_data)

        # Task in app2
        task2_data = {
            "tenant_id": tenant_id,
            "name": "App2 Task",
            "cy_name": "app2_task",
            "script": 'return "Hello from App2"',
            "description": "Task in App2",
            "app": "app2",
        }
        await task_repo.create(task2_data)

        # Task in app3 that calls tasks from app1 and app2
        task3_data = {
            "tenant_id": tenant_id,
            "name": "Cross App Orchestrator",
            "cy_name": "cross_app_orchestrator",
            "script": """
# Call task from app1
msg1 = task_run("app1_task", {})

# Call task from app2
msg2 = task_run("app2_task", {})

# Combine messages with string concatenation (use + not ++)
return msg1 + " | " + msg2
""",
            "description": "Orchestrates tasks from different apps",
            "app": "app3",
        }
        task3 = await task_repo.create(task3_data)

        await integration_test_session.commit()

        # Execute the orchestrator task
        execution_context = {
            "task_id": str(task3.component_id),
            "tenant_id": tenant_id,
            "app": "app3",
            "session": integration_test_session,
        }

        executor = DefaultTaskExecutor()
        result = await executor.execute(task3.script, {}, execution_context)

        # Verify cross-app calls worked
        if result["status"] != "completed":
            print("\nCross-app task failed!")
            print(f"Status: {result.get('status')}")
            print(f"Error: {result.get('error')}")
            print(f"Output: {result.get('output')}")
            print(f"Full result: {result}")
        assert result["status"] == "completed", (
            f"Task failed with: {result.get('error') or result.get('output')}"
        )
        assert result["output"] == "Hello from App1 | Hello from App2"

    @pytest.mark.asyncio
    async def test_nested_task_composition(
        self, integration_test_session: AsyncSession, tenant_id: str
    ):
        """Test deeply nested task calls (A calls B, B calls C)."""
        task_repo = TaskRepository(integration_test_session)

        # Level 3: Base task
        task_c_data = {
            "tenant_id": tenant_id,
            "name": "Level C Task",
            "cy_name": "level_c",
            "script": 'return "C"',
            "description": "Deepest level task",
            "app": "nested_app",
        }
        await task_repo.create(task_c_data)

        # Level 2: Calls Level 3
        task_b_data = {
            "tenant_id": tenant_id,
            "name": "Level B Task",
            "cy_name": "level_b",
            "script": """
c_result = task_run("level_c", {})
return "B-" + c_result
""",
            "description": "Middle level task",
            "app": "nested_app",
        }
        await task_repo.create(task_b_data)

        # Level 1: Calls Level 2
        task_a_data = {
            "tenant_id": tenant_id,
            "name": "Level A Task",
            "cy_name": "level_a",
            "script": """
b_result = task_run("level_b", {})
return "A-" + b_result
""",
            "description": "Top level task",
            "app": "nested_app",
        }
        task_a = await task_repo.create(task_a_data)

        await integration_test_session.commit()

        # Execute the top-level task
        execution_context = {
            "task_id": str(task_a.component_id),
            "tenant_id": tenant_id,
            "app": "nested_app",
            "session": integration_test_session,
        }

        executor = DefaultTaskExecutor()
        result = await executor.execute(task_a.script, {}, execution_context)

        # Verify nested calls worked
        if result["status"] != "completed":
            print(f"Nested task failed: {result.get('error', 'Unknown error')}")
        assert result["status"] == "completed"
        assert result["output"] == "A-B-C"

    @pytest.mark.asyncio
    async def test_task_composition_with_full_result(
        self, integration_test_session: AsyncSession, tenant_id: str
    ):
        """Test task composition using full_result parameter."""
        task_repo = TaskRepository(integration_test_session)

        # Task that might fail
        task1_data = {
            "tenant_id": tenant_id,
            "name": "May Fail Task",
            "cy_name": "may_fail",
            "script": """
fail = input["fail"]
if (fail) {
    # Cause an intentional error by dividing by zero
    error = 1 / 0
}
return "Success"
""",
            "description": "Task that may fail based on input",
            "app": "test_app",
        }
        await task_repo.create(task1_data)

        # Task that handles potential failures
        task2_data = {
            "tenant_id": tenant_id,
            "name": "Safe Orchestrator",
            "cy_name": "safe_orchestrator",
            "script": """
# Call with full_result to get status and error info
result = task_run("may_fail", {"fail": False}, True)

# Get the output value from success case
success_output = result["output"]

# Also try one that fails
failed_result = task_run("may_fail", {"fail": True}, True)

return {
    "success_output": success_output,
    "success_status": result["status"],
    "failed_status": failed_result["status"],
    "failed_error": failed_result["error"]
}
""",
            "description": "Orchestrator that handles task failures",
            "app": "test_app",
        }
        task2 = await task_repo.create(task2_data)

        await integration_test_session.commit()

        # Execute the orchestrator
        execution_context = {
            "task_id": str(task2.component_id),
            "tenant_id": tenant_id,
            "app": "test_app",
            "session": integration_test_session,
        }

        executor = DefaultTaskExecutor()
        result = await executor.execute(task2.script, {}, execution_context)

        # Verify error handling worked
        if result["status"] != "completed":
            print(f"Full result task failed: {result.get('error', 'Unknown error')}")
        assert result["status"] == "completed"
        output = parse_cy_output(result["output"])
        assert output["success_output"] == "Success"
        assert output["success_status"] == "completed"
        assert output["failed_status"] == "failed"
        # Check for division by zero error
        assert (
            "division" in output["failed_error"].lower()
            or "zero" in output["failed_error"].lower()
        )
