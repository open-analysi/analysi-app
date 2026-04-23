"""
Integration tests for Task Type Inference with database dependencies.

Tests Cy integration for task output schema inference with real database access.
"""

from uuid import uuid4

import pytest

from analysi.models.component import Component
from analysi.models.knowledge_unit import KnowledgeUnit, KUTool, KUType
from analysi.models.task import Task, TaskFunction
from analysi.services.type_propagation.errors import TypePropagationError
from analysi.services.type_propagation.task_inference import (
    infer_task_output_schema,
)


@pytest.mark.integration
class TestIntegrationToolTypeValidation:
    """Test type validation for integration tools (app:: namespace).

    Integration tools have schemas stored in KUTool table.
    These schemas should be passed to Cy for type validation.
    """

    @pytest.mark.asyncio
    async def test_integration_tool_wrong_parameter_type(self, test_session):
        """
        Test that tool parameter type validation detects type mismatches.

        Cy 0.19.0+ validates tool parameter types against the schemas in tool_registry.
        This test verifies that passing a number to a string parameter is caught.
        """
        # 1. Create a mock integration tool (use unique name to avoid framework conflicts)
        tool_component = Component(
            id=uuid4(),
            tenant_id="test-tenant",
            kind="ku",
            name="test_threat_intel::ip_check",
            ku_type=KUType.TOOL,
            status="enabled",
        )
        test_session.add(tool_component)
        test_session.flush()

        # Create KU
        ku = KnowledgeUnit(
            component_id=tool_component.id,
            ku_type=KUType.TOOL,
        )
        test_session.add(ku)
        test_session.flush()

        # Create tool with schemas from manifest
        tool = KUTool(
            component_id=tool_component.id,
            tool_type="app",
            integration_id=uuid4(),
            input_schema={
                "type": "object",
                "properties": {
                    "ip": {"type": "string"}  # Expects STRING
                },
                "required": ["ip"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "malicious": {"type": "boolean"},
                    "score": {"type": "number"},
                },
            },
        )
        test_session.add(tool)
        test_session.flush()

        # 2. Create task that calls the tool with WRONG type (number instead of string)
        task_component_id = uuid4()
        task = Task(
            component_id=task_component_id,
            directive="Check IP reputation",
            script="""
# Call integration tool with WRONG type - should fail type validation
result = app::test_threat_intel::ip_check(ip=123)  # ❌ number, not string!
return result
""",
            function=TaskFunction.REASONING,
        )

        # 3. Call type inference with session context
        input_schema = {"type": "object", "properties": {}}

        output = await infer_task_output_schema(
            task, input_schema, session=test_session, tenant_id="test-tenant"
        )

        # 4. Should return TypePropagationError for type mismatch
        assert isinstance(output, TypePropagationError), (
            f"Expected TypePropagationError for wrong parameter type, but got: {output}"
        )

        # Verify error message mentions the parameter name and type issue
        assert (
            "ip" in output.message.lower() or "parameter" in output.message.lower()
        ), (
            f"Error message should mention parameter name or 'parameter': {output.message}"
        )
        assert (
            "type" in output.message.lower()
            or "string" in output.message.lower()
            or "number" in output.message.lower()
        ), f"Error message should mention type issue: {output.message}"

    @pytest.mark.asyncio
    async def test_integration_tool_correct_parameter_type(self, test_session):
        """
        Test that calling an integration tool with correct parameter type succeeds.

        Positive test: Correct types should pass validation and return inferred output schema.
        """
        # 1. Create a mock integration tool (use unique name to avoid framework conflicts)
        tool_component = Component(
            id=uuid4(),
            tenant_id="test-tenant",
            kind="ku",
            name="test_threat_intel::ip_check",
            ku_type=KUType.TOOL,
            status="enabled",
        )
        test_session.add(tool_component)
        test_session.flush()

        ku = KnowledgeUnit(
            component_id=tool_component.id,
            ku_type=KUType.TOOL,
        )
        test_session.add(ku)
        test_session.flush()

        tool = KUTool(
            component_id=tool_component.id,
            tool_type="app",
            integration_id=uuid4(),
            input_schema={
                "type": "object",
                "properties": {
                    "ip": {"type": "string"}  # Expects STRING
                },
                "required": ["ip"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "malicious": {"type": "boolean"},
                    "score": {"type": "number"},
                },
            },
        )
        test_session.add(tool)
        test_session.flush()

        # 2. Create task with CORRECT type
        task_component_id = uuid4()
        task = Task(
            component_id=task_component_id,
            directive="Check IP reputation",
            script="""
# Call integration tool with CORRECT type
ip_address = "8.8.8.8"
result = app::test_threat_intel::ip_check(ip=ip_address)  # ✅ string!
return result
""",
            function=TaskFunction.REASONING,
        )

        # 3. Call type inference
        input_schema = {"type": "object", "properties": {}}

        output = await infer_task_output_schema(
            task, input_schema, session=test_session, tenant_id="test-tenant"
        )

        # 4. Should NOT be an error
        assert not isinstance(output, TypePropagationError), (
            f"Expected successful validation, but got error: {output.message if isinstance(output, TypePropagationError) else output}"
        )

        # 5. Should return the tool's output schema (object type)
        assert output.get("type") == "object", (
            f"Expected output schema type 'object', got: {output}"
        )
