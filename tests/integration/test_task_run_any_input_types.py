"""
Integration tests for task run with Any type input support.

Tests that task execution properly handles dict, list, string, and other JSON types.
This validates the fix for supporting fan-in array inputs via the REST API.
"""

from typing import Any

import pytest

from analysi.services.task_execution import TaskExecutionService
from analysi.services.task_run import TaskRunService
from tests.utils.cy_output import parse_cy_output


@pytest.mark.integration
class TestTaskRunAnyInputTypes:
    """Test task runs with various input types (dict, list, string, etc.)"""

    async def _execute_task_with_input(
        self, session, cy_script: str, input_data
    ) -> Any:
        """Helper to execute a task with given input and return the result.

        Creates a real TaskRun in the DB via TaskRunService.create_execution(),
        then executes it via the new execute_single_task(task_run_id, tenant_id) API.
        """
        tenant_id = "test-tenant"

        task_run_service = TaskRunService()
        exec_service = TaskExecutionService()

        # Create task run with input data persisted to DB
        task_run = await task_run_service.create_execution(
            session=session,
            tenant_id=tenant_id,
            task_id=None,  # Ad-hoc execution
            cy_script=cy_script,
            input_data=input_data,
            executor_config=None,
        )
        await session.commit()

        # Execute (creates its own session internally)
        result = await exec_service.execute_single_task(task_run.id, tenant_id)

        if result.status == "failed":
            raise Exception(f"Task failed: {result.error_message}")

        return parse_cy_output(result.output_data)

    @pytest.mark.asyncio
    async def test_task_run_with_dict_input(self, integration_test_session):
        """Test task execution with traditional dict input (backward compatibility)."""
        cy_script = "return input"  # Simple echo script
        input_data = {"message": "test", "value": 42}

        result = await self._execute_task_with_input(
            integration_test_session, cy_script, input_data
        )

        assert result == {"message": "test", "value": 42}

    @pytest.mark.asyncio
    async def test_task_run_with_array_input(self, integration_test_session):
        """Test task execution with array input (fan-in scenario support)."""
        cy_script = "return input"  # Simple echo script
        input_data = [
            {"node_id": "node1", "result": {"data": "value1"}},
            {"node_id": "node2", "result": {"data": "value2"}},
        ]

        result = await self._execute_task_with_input(
            integration_test_session, cy_script, input_data
        )

        assert result == [
            {"node_id": "node1", "result": {"data": "value1"}},
            {"node_id": "node2", "result": {"data": "value2"}},
        ]

    @pytest.mark.asyncio
    async def test_task_run_with_string_input(self, integration_test_session):
        """Test task execution with string input."""
        cy_script = "return input"  # Simple echo script
        input_data = "Hello, this is a simple string"

        result = await self._execute_task_with_input(
            integration_test_session, cy_script, input_data
        )

        assert result == "Hello, this is a simple string"

    @pytest.mark.asyncio
    async def test_task_run_with_number_input(self, integration_test_session):
        """Test task execution with numeric input."""
        cy_script = "return input * 2"  # Double the input
        input_data = 21

        result = await self._execute_task_with_input(
            integration_test_session, cy_script, input_data
        )

        assert result == 42

    @pytest.mark.asyncio
    async def test_task_run_with_boolean_input(self, integration_test_session):
        """Test task execution with boolean input."""
        cy_script = 'return {"inverted": not input}'  # Invert boolean
        input_data = True

        result = await self._execute_task_with_input(
            integration_test_session, cy_script, input_data
        )

        assert result == {"inverted": False}

    @pytest.mark.asyncio
    async def test_task_run_with_null_input(self, integration_test_session):
        """Test task execution with null input."""
        # Skip null test - Cy doesn't have a way to check for None/null
        # Just verify it doesn't crash
        cy_script = 'return {"processed": True}'
        input_data = None

        result = await self._execute_task_with_input(
            integration_test_session, cy_script, input_data
        )

        assert result == {"processed": True}

    @pytest.mark.asyncio
    async def test_task_run_with_nested_array_input(self, integration_test_session):
        """Test task execution with nested array input (complex fan-in)."""
        cy_script = """
# Extract first element's result array
first_node_results = input[0]["result"]
# Get the first item from that array
first_item = first_node_results[0]
return {"extracted": first_item}
        """
        input_data = [
            {"node_id": "aggregator1", "result": ["item1", "item2", "item3"]},
            {"node_id": "aggregator2", "result": ["item4", "item5"]},
        ]

        result = await self._execute_task_with_input(
            integration_test_session, cy_script, input_data
        )

        assert result == {"extracted": "item1"}

    @pytest.mark.asyncio
    async def test_task_run_processes_fan_in_array(self, integration_test_session):
        """Test realistic fan-in processing with array of predecessor outputs."""
        # Simplified Cy script that just counts predecessors
        cy_script = """
# Process fan-in - just count predecessors and extract first values
first_count = input[0]["result"]["count"]
second_count = input[1]["result"]["count"]
third_count = input[2]["result"]["count"]

# Get first value from each
first_val = input[0]["result"]["values"][0]
second_val = input[1]["result"]["values"][0]
third_val = input[2]["result"]["values"][0]

return {
    "total_count": first_count + second_count + third_count,
    "sample_values": [first_val, second_val, third_val],
    "predecessor_count": len(input)
}
        """
        input_data = [
            {"node_id": "counter1", "result": {"count": 5, "values": [1, 2, 3]}},
            {"node_id": "counter2", "result": {"count": 3, "values": [4, 5]}},
            {"node_id": "counter3", "result": {"count": 7, "values": [6, 7, 8, 9]}},
        ]

        result = await self._execute_task_with_input(
            integration_test_session, cy_script, input_data
        )

        assert result == {
            "total_count": 15,  # 5 + 3 + 7
            "sample_values": [1, 4, 6],  # First value from each
            "predecessor_count": 3,
        }

    @pytest.mark.asyncio
    async def test_create_execution_accepts_any_type(self, integration_test_session):
        """Test that TaskRunService.create_execution accepts any JSON type."""
        service = TaskRunService()
        tenant_id = "test-tenant"

        # Test with array input (the main fix)
        array_task_run = await service.create_execution(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=None,
            cy_script="return input",
            input_data=[1, 2, 3],  # Array input
            executor_config=None,
        )
        assert array_task_run is not None
        assert array_task_run.input_type == "inline"

        # Test with string input
        string_task_run = await service.create_execution(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=None,
            cy_script="return input",
            input_data="test string",  # String input
            executor_config=None,
        )
        assert string_task_run is not None
        assert string_task_run.input_type == "inline"

        # Test with dict input (backward compatibility)
        dict_task_run = await service.create_execution(
            session=integration_test_session,
            tenant_id=tenant_id,
            task_id=None,
            cy_script="return input",
            input_data={"key": "value"},  # Dict input
            executor_config=None,
        )
        assert dict_task_run is not None
        assert dict_task_run.input_type == "inline"

        # Commit to persist
        await integration_test_session.commit()
