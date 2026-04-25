"""
Integration tests for tool registration with Cy 0.19.0+

Tests that app tools maintain correct FQN format and native tools are accessible.
Covers the fix for the native::tools::app::splunk::spl_run error.

These are integration tests because they test the integration between:
- Database (PostgreSQL with real Component/KU/KUTool records)
- Cy language type inference (analyze_types)
- Tool registry loading (framework manifest scanning)
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
class TestToolFQNPreservation:
    """Test that app tool FQNs are preserved correctly."""

    @pytest.mark.asyncio
    async def test_app_tool_fqn_preserved_in_type_inference(self, test_session):
        """
        Verify app:: tools maintain 3-part FQN (not 5-part with native::tools:: prefix).

        This is the regression test for the bug where tools became:
        native::tools::app::test_integration::query_tool (5 parts - INVALID)
        instead of:
        app::test_integration::query_tool (3 parts - VALID)

        Note: Uses a mock tool name to avoid conflicts with real framework tools.
        """
        # Create mock integration tool (use unique name to avoid framework conflicts)
        tool_component = Component(
            id=uuid4(),
            tenant_id="test-tenant",
            kind="ku",
            name="test_integration::query_tool",  # Will become app::test_integration::query_tool
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
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "results": {"type": "array"},
                    "count": {"type": "number"},
                },
            },
        )
        test_session.add(tool)
        test_session.flush()

        # Create task that calls the mock tool
        task = Task(
            component_id=uuid4(),
            directive="Run test query",
            script="""
# Should work with app:: prefix (3 parts - VALID)
results = app::test_integration::query_tool(query="test query")
return results
""",
            function=TaskFunction.REASONING,
        )

        # Call type inference - should succeed (not fail with 5-part FQN error)
        output = await infer_task_output_schema(
            task,
            input_schema={"type": "object", "properties": {}},
            session=test_session,
            tenant_id="test-tenant",
        )

        # Should NOT be an error
        assert not isinstance(output, TypePropagationError), (
            f"Expected successful inference, got error: {output.message if isinstance(output, TypePropagationError) else output}"
        )

        # Should return Splunk tool's output schema
        assert output.get("type") == "object"
        assert "results" in output.get("properties", {})

    @pytest.mark.asyncio
    async def test_native_tools_available_without_passing(self, test_session):
        """
        Verify native tools (len, str, etc.) are automatically available.

        Per Cy team: analyze_types() calls ToolResolver.from_native_tools() internally,
        so native tools are always available even if not in tool_registry parameter.
        """
        # Create task that uses BOTH native and app tools
        task = Task(
            component_id=uuid4(),
            directive="Use native tools",
            script="""
# Native tools should work without being in tool_registry
items = [1, 2, 3]
count = len(items)  # Native tool
text = str(count)   # Native tool
return text
""",
            function=TaskFunction.REASONING,
        )

        # Call type inference WITHOUT any tool_registry (no session/tenant_id)
        output = await infer_task_output_schema(
            task,
            input_schema={"type": "object", "properties": {}},
            session=None,  # No app tools
            tenant_id=None,
        )

        # Should succeed - native tools are automatic
        assert not isinstance(output, TypePropagationError), (
            f"Native tools should be available automatically, got error: {output}"
        )

        # str() returns string
        assert output.get("type") == "string"

    @pytest.mark.asyncio
    async def test_mixed_native_and_app_tools(self, test_session):
        """
        Verify scripts can use both native and app tools together.

        This ensures the tool_registry parameter (app tools only) doesn't
        interfere with native tools being available.
        """
        # Create mock integration tool (use unique name to avoid framework conflicts)
        tool_component = Component(
            id=uuid4(),
            tenant_id="test-tenant",
            kind="ku",
            name="test_intel::check_reputation",
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
                "properties": {"ip": {"type": "string"}},
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

        # Create task that uses BOTH native and app tools
        task = Task(
            component_id=uuid4(),
            directive="Mix native and app tools",
            script="""
# Use app tool
intel_data = app::test_intel::check_reputation(ip="8.8.8.8")

# Use native tool on app tool result
score = intel_data.score
score_text = str(score)  # Native tool: str()

# Use another native tool
message = "Intel Score: " + score_text
msg_length = len(message)  # Native tool: len()

return msg_length
""",
            function=TaskFunction.REASONING,
        )

        # Call type inference with app tools
        output = await infer_task_output_schema(
            task,
            input_schema={"type": "object", "properties": {}},
            session=test_session,
            tenant_id="test-tenant",
        )

        # Should succeed - both tool types work together
        assert not isinstance(output, TypePropagationError), (
            f"Expected mixed tool usage to work, got error: {output}"
        )

        # len() returns number
        assert output.get("type") == "number"


@pytest.mark.integration
class TestToolRegistryConversion:
    """Test ToolRegistry.from_dict() conversion."""

    @pytest.mark.asyncio
    async def test_tool_registry_dict_to_object_conversion(self, test_session):
        """
        Verify dict format is correctly converted to ToolRegistry object.

        The _load_tool_registry_async() returns a dict, which we convert
        to ToolRegistry using ToolRegistry.from_dict() before passing to analyze_types().
        """
        # Create test tool
        tool_component = Component(
            id=uuid4(),
            tenant_id="test-tenant",
            kind="ku",
            name="test::my_tool",
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
                "properties": {"param1": {"type": "string"}},
            },
            output_schema={"type": "string"},
        )
        test_session.add(tool)
        test_session.flush()

        # Create task that uses the tool
        task = Task(
            component_id=uuid4(),
            directive="Test ToolRegistry conversion",
            script='result = app::test::my_tool(param1="test")\nreturn result',
            function=TaskFunction.REASONING,
        )

        # This should internally convert dict → ToolRegistry → analyze_types
        output = await infer_task_output_schema(
            task,
            input_schema={"type": "object", "properties": {}},
            session=test_session,
            tenant_id="test-tenant",
        )

        # Should succeed with correct output type
        assert not isinstance(output, TypePropagationError)
        assert output.get("type") == "string"

    @pytest.mark.asyncio
    async def test_empty_tool_registry_handled(self, test_session):
        """
        Verify empty tool_registry (no app tools) is handled gracefully.

        When no integration tools exist, tool_registry should be None,
        and only native tools should be available.
        """
        # No app tools in database for this tenant
        task = Task(
            component_id=uuid4(),
            directive="Use native tools only",
            script="items = [1, 2]\ncount = len(items)\nreturn count",
            function=TaskFunction.REASONING,
        )

        # Call with session but no tools will be found
        output = await infer_task_output_schema(
            task,
            input_schema={"type": "object", "properties": {}},
            session=test_session,
            tenant_id="empty-tenant-no-tools",
        )

        # Should still work with native tools
        assert not isinstance(output, TypePropagationError)
        assert output.get("type") == "number"
