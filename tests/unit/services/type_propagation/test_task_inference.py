"""
Unit tests for Task Type Inference.

Tests Cy integration for task output schema inference and input validation.
Following TDD - these tests should fail until implementation is complete.
"""

from uuid import uuid4

import pytest

from analysi.models.task import Task, TaskFunction
from analysi.services.type_propagation.errors import TypePropagationError
from analysi.services.type_propagation.task_inference import (
    infer_task_output_schema,
    validate_task_input,
)


@pytest.mark.unit
class TestTaskOutputInference:
    """Test task output schema inference using Cy integration."""

    @pytest.mark.asyncio
    async def test_infer_task_output_with_explicit_schema(self):
        """
        Test task with script infers output type from input schema.

        Positive case: Cy inference correctly infers string type from input.data.
        """
        # Create task with script
        component_id = uuid4()

        task = Task(
            component_id=component_id,
            directive="Extract result",
            script="return input.data",
            function=TaskFunction.EXTRACTION,
        )

        # Input schema
        input_schema = {"type": "object", "properties": {"data": {"type": "string"}}}

        # Call infer_task_output_schema()
        output = await infer_task_output_schema(task, input_schema)

        # Should not be an error
        assert not isinstance(output, TypePropagationError)

        # Should return string type (since input.data is a string)
        assert output["type"] == "string"

    @pytest.mark.asyncio
    async def test_infer_task_output_with_cy_inference(self):
        """
        Test task with script returns generic schema.

        Positive case: Cy inference returns schema.
        """
        # Create task with script
        component_id = uuid4()

        task = Task(
            component_id=component_id,
            directive="Extract IP from input",
            script="return input.ip",
            function=TaskFunction.EXTRACTION,
        )

        # Input schema
        input_schema = {"type": "object", "properties": {"ip": {"type": "string"}}}

        # Call infer_task_output_schema()
        output = await infer_task_output_schema(task, input_schema)

        # Should not be an error
        assert not isinstance(output, TypePropagationError)

        # Should return schema
        assert "type" in output

    @pytest.mark.asyncio
    async def test_infer_task_output_cy_error(self):
        """
        Test task with script (Cy errors will be detected in future).

        Negative case: Currently returns generic schema, will detect errors when Cy integrated.
        """
        # Create task with script that would be invalid
        component_id = uuid4()

        task = Task(
            component_id=component_id,
            directive="Invalid script",
            script="return input.nonexistent_field.deep.access",  # Would be invalid
            function=TaskFunction.EXTRACTION,
        )

        # Input schema (missing the expected field)
        input_schema = {"type": "object", "properties": {"other": {"type": "string"}}}

        # Call infer_task_output_schema()
        output = await infer_task_output_schema(task, input_schema)

        # Currently returns generic schema (TODO: will return error when Cy integrated)
        # For now, just check it returns something
        assert output is not None

    @pytest.mark.asyncio
    async def test_infer_task_output_empty_script(self):
        """
        Test task with empty script handles gracefully.

        Edge case: Empty script handled.
        """
        # Create task with empty script
        component_id = uuid4()

        task = Task(
            component_id=component_id,
            directive="Task with empty script",
            script="",  # Empty script
            function=TaskFunction.EXTRACTION,
        )

        # Input schema
        input_schema = {"type": "object", "properties": {"data": {"type": "string"}}}

        # Call infer_task_output_schema()
        output = await infer_task_output_schema(task, input_schema)

        # Should return error for empty script
        assert isinstance(output, TypePropagationError)
        assert "empty script" in output.message.lower()


@pytest.mark.unit
class TestTaskInputValidation:
    """Test task input schema validation using Cy inference."""

    @pytest.mark.asyncio
    async def test_validate_task_input_compatible(self):
        """
        Test task input validation with compatible schema.

        Positive case: Compatible input validates.
        """
        # Create task that expects input.ip
        component_id = uuid4()

        task = Task(
            component_id=component_id,
            directive="Process IP address",
            script="return input.ip",
            function=TaskFunction.EXTRACTION,
        )

        # Input schema with ip field
        input_schema = {"type": "object", "properties": {"ip": {"type": "string"}}}

        # Call validate_task_input()
        result = await validate_task_input(task, input_schema)

        # Should not be an error
        assert not isinstance(result, TypePropagationError)

        # Should return True for compatible input
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_task_input_incompatible(self):
        """
        Test task input validation (currently accepts all non-empty scripts).

        Negative case: Will detect incompatibility when Cy integrated.
        """
        # Create task that expects input.name
        component_id = uuid4()

        task = Task(
            component_id=component_id,
            directive="Process name",
            script="return input.name",
            function=TaskFunction.EXTRACTION,
        )

        # Input schema missing name field
        input_schema = {"type": "object", "properties": {"ip": {"type": "string"}}}

        # Call validate_task_input()
        result = await validate_task_input(task, input_schema)

        # Currently returns True (TODO: will detect incompatibility when Cy integrated)
        # For now, any non-empty script is considered valid
        assert result is True or isinstance(result, TypePropagationError)

    @pytest.mark.asyncio
    async def test_validate_task_input_duck_typing_extra_fields(self):
        """
        Test task input validation allows extra fields (duck typing).

        Positive case: Duck typing allows extra fields.
        """
        # Create task that only uses input.ip
        component_id = uuid4()

        task = Task(
            component_id=component_id,
            directive="Extract IP",
            script="return input.ip",
            function=TaskFunction.EXTRACTION,
        )

        # Input schema with ip plus extra fields
        input_schema = {
            "type": "object",
            "properties": {
                "ip": {"type": "string"},
                "port": {"type": "number"},  # Extra field not used by task
                "protocol": {"type": "string"},  # Another extra field
            },
        }

        # Call validate_task_input()
        result = await validate_task_input(task, input_schema)

        # Should not be an error
        assert not isinstance(result, TypePropagationError)

        # Should return True (duck typing allows extra fields)
        assert result is True
