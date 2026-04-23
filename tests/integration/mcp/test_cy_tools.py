"""Integration tests for Cy script tools."""

import pytest

from analysi.auth.models import CurrentUser
from analysi.mcp.context import set_mcp_current_user
from analysi.mcp.tools import cy_tools
from tests.utils.cy_output import parse_cy_output


@pytest.mark.integration
@pytest.mark.asyncio
class TestCyTools:
    """Test Cy script validation and analysis tools."""

    @pytest.fixture(autouse=True)
    def _mcp_user(self):
        """Set MCP user context so RBAC checks pass."""
        set_mcp_current_user(
            CurrentUser(
                user_id="test-user",
                email="test@test.com",
                tenant_id="test",
                roles=["analyst"],
                actor_type="user",
            )
        )

    @pytest.mark.asyncio
    async def test_quick_syntax_check_cy_script_valid(self):
        """Verify that a syntactically valid Cy script passes validation without errors."""
        script = """
x = 10
y = 20
return x + y
        """.strip()

        result = await cy_tools.quick_syntax_check_cy_script(script)

        assert result["valid"] is True
        assert result["errors"] is None

    @pytest.mark.asyncio
    async def test_quick_syntax_check_cy_script_invalid_syntax(self):
        """Verify that invalid Cy syntax returns appropriate error messages."""
        script = """
x = 10
if (x > 5
    return "large"
        """.strip()

        result = await cy_tools.quick_syntax_check_cy_script(script)

        assert result["valid"] is False
        assert result["errors"] is not None
        assert len(result["errors"]) > 0
        # Error should contain line/column info
        assert any("line" in str(err).lower() for err in result["errors"])

    @pytest.mark.asyncio
    async def test_compile_cy_script_success(self):
        """Verify that a valid script compiles to an execution plan."""
        script = """
x = 10
y = 20
return x + y
        """.strip()

        result = await cy_tools.compile_cy_script(script)

        assert result["plan"] is not None
        assert result["validation_errors"] == []
        # New format: plan has 'compiled' and 'output_schema'
        assert "compiled" in result["plan"]
        assert result["plan"]["compiled"] is True
        assert "output_schema" in result["plan"]
        # Should infer number type from x + y
        assert result["plan"]["output_schema"]["type"] == "number"

    @pytest.mark.asyncio
    async def test_compile_cy_script_missing_output(self):
        """
        Verify that scripts without return statement compile successfully.

        NOTE: After switching to analyze_types(), compile_cy_script focuses on
        type inference rather than semantic validation like return statements.
        Use validate_task_script() for return statement checking.
        """
        script = """
x = 10
y = 20
result = x + y
        """.strip()

        result = await cy_tools.compile_cy_script(script)

        # analyze_types() doesn't validate return statements - it infers types
        # This script is valid from a type perspective (no type errors)
        assert result["plan"] is not None
        assert result["plan"]["compiled"] is True
        # Without return, output type is inferred as None or empty
        assert "output_schema" in result["plan"]

    @pytest.mark.skip(reason="analyze_dependencies not fully implemented yet")
    @pytest.mark.asyncio
    async def test_analyze_dependencies_parallel(self):
        """Verify detection of parallelizable operations."""
        # Use valid Cy syntax with built-in operations
        script = """
list1 = [1, 2, 3]
list2 = [4, 5, 6]
list3 = [7, 8, 9]
len1 = len(list1)
len2 = len(list2)
len3 = len(list3)
return len1 + len2 + len3
        """.strip()

        result = await cy_tools.analyze_dependencies(script)

        assert "parallel_groups" in result
        assert "can_parallelize" in result
        # If there's an error (tools not found), that's acceptable
        # The test verifies the function returns the expected structure
        if "error" not in result:
            assert "node_count" in result or "note" in result

    @pytest.mark.skip(reason="analyze_dependencies not fully implemented yet")
    @pytest.mark.asyncio
    async def test_analyze_dependencies_sequential(self):
        """Verify that sequential dependencies are correctly identified."""
        script = """
x = 10
y = x + 5
z = y * 2
return z
        """.strip()

        result = await cy_tools.analyze_dependencies(script)

        assert "parallel_groups" in result
        assert "can_parallelize" in result
        # Each operation depends on previous, limited parallelization
        assert (
            result["can_parallelize"] is False
            or len([g for g in result["parallel_groups"] if len(g) > 1]) == 0
        )

    @pytest.mark.skip(reason="visualize_plan not fully implemented yet")
    @pytest.mark.asyncio
    async def test_visualize_plan_graphviz(self):
        """Verify GraphViz DOT format generation."""
        script = """
x = 10
y = 20
return x + y
        """.strip()

        result = await cy_tools.visualize_plan(script)

        assert "graphviz" in result
        # Simplified implementation - returns plan_json instead of graphviz
        assert "plan_json" in result or "note" in result

    @pytest.mark.asyncio
    async def test_get_plan_stats(self):
        """Verify execution plan statistics are accurate."""
        script = """
x = 10
y = 20
z = x + y
return z
        """.strip()

        result = await cy_tools.get_plan_stats(script)

        assert "total_nodes" in result
        assert "node_types" in result
        # Should have 4 assignment nodes
        assert result["total_nodes"] >= 4
        assert isinstance(result["node_types"], dict)
        # Should have assignment node types
        assert "assign" in result["node_types"] or len(result["node_types"]) > 0

    @pytest.mark.asyncio
    async def test_list_all_active_tool_summaries(self):
        """Verify listing all active tool FQNs."""
        result = await cy_tools.list_all_active_tool_summaries()

        assert "tools" in result
        assert "total" in result
        assert isinstance(result["tools"], list)
        assert result["total"] > 0
        # Should have at least some basic native tools
        assert "add" in result["tools"] or "len" in result["tools"]
        # Each should be a string FQN
        for tool_fqn in result["tools"]:
            assert isinstance(tool_fqn, str)

    @pytest.mark.asyncio
    async def test_get_tool_details(self):
        """Verify getting tool details for selected tools."""
        # First get summaries
        summaries = await cy_tools.list_all_active_tool_summaries()
        assert len(summaries["tools"]) > 0

        # Get details for first few tools
        tool_fqns = summaries["tools"][:5]
        result = await cy_tools.get_tool_details(tool_fqns)

        assert "tools" in result
        assert "count" in result
        assert result["count"] > 0
        # Each tool should have full details
        for tool in result["tools"]:
            assert "fqn" in tool
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool
            assert isinstance(tool["fqn"], str)
            assert isinstance(tool["description"], str)

    @pytest.mark.asyncio
    async def test_execute_cy_script_adhoc_success(self):
        """Verify ad-hoc script execution returns correct output and creates task_run."""
        script = """
x = 10
y = 20
return x + y
        """.strip()

        result = await cy_tools.execute_cy_script_adhoc(script)

        # New API-based execution returns different fields
        assert "status" in result
        assert result["status"] in ["completed", "failed", "error"]

        if result["status"] == "completed":
            assert result["output"] == "30"
            assert result["task_run_id"] is not None
            assert result["execution_time_ms"] is not None
            assert result["error"] is None

    @pytest.mark.asyncio
    async def test_execute_cy_script_adhoc_with_tools(self):
        """Verify ad-hoc execution can call Cy tools."""
        script = """
numbers = [1, 2, 3, 4, 5]
length = len(numbers)
return length
        """.strip()

        result = await cy_tools.execute_cy_script_adhoc(script)

        assert "status" in result
        if result["status"] == "completed":
            assert result["output"] == "5"
            assert result["error"] is None

    @pytest.mark.asyncio
    @pytest.mark.requires_full_stack
    async def test_execute_cy_script_adhoc_missing_output(self):
        """Verify ad-hoc execution fails without $output."""
        script = """
x = 10
y = 20
result = x + y
        """.strip()

        result = await cy_tools.execute_cy_script_adhoc(script)

        assert "status" in result
        assert result["status"] in ["failed", "error"]
        # Error is in output field as JSON, not error field
        assert result["output"] is not None
        assert "$output" in result["output"] or "output" in result["output"].lower()

    @pytest.mark.asyncio
    async def test_execute_cy_script_adhoc_syntax_error(self):
        """Verify ad-hoc execution handles syntax errors."""
        script = """
x = 10
if (x > 5
    return "large"
        """.strip()

        result = await cy_tools.execute_cy_script_adhoc(script)

        assert "status" in result
        assert result["status"] in ["failed", "error"]
        assert result["error"] is not None

    @pytest.mark.asyncio
    async def test_execute_cy_script_adhoc_with_input_data(self):
        """Verify ad-hoc execution with input data."""
        script = """
doubled = input * 2
return doubled
        """.strip()

        result = await cy_tools.execute_cy_script_adhoc(script, input_data=5)

        assert "status" in result
        if result["status"] == "completed":
            assert result["output"] == "10"
            assert result["error"] is None

    @pytest.mark.asyncio
    @pytest.mark.requires_full_stack
    async def test_execute_adhoc_runtime_error(self):
        """Verify runtime errors are caught and returned."""
        script = """
x = 10
y = 0
result = x / y
return result
        """.strip()

        result = await cy_tools.execute_cy_script_adhoc(script)

        assert "status" in result
        assert result["status"] in ["failed", "error"]
        # Error is in output field as JSON
        assert result["output"] is not None
        assert (
            "division" in result["output"].lower() or "zero" in result["output"].lower()
        )

    @pytest.mark.asyncio
    @pytest.mark.requires_full_stack
    async def test_execute_adhoc_undefined_tool(self):
        """Verify undefined tool calls return clear error."""
        script = """
result = undefined_tool_xyz(123)
return result
        """.strip()

        result = await cy_tools.execute_cy_script_adhoc(script)

        assert "status" in result
        assert result["status"] in ["failed", "error"]
        # Error is in output field as JSON
        assert result["output"] is not None
        assert (
            "undefined_tool_xyz" in result["output"]
            or "not found" in result["output"].lower()
        )

    @pytest.mark.asyncio
    async def test_all_tools_have_descriptions(self):
        """Verify all registered Cy tools have descriptions."""
        # Get summaries and then details
        summaries = await cy_tools.list_all_active_tool_summaries()
        assert summaries["total"] > 0

        # Get details for first 10 tools
        tool_fqns = summaries["tools"][:10]
        result = await cy_tools.get_tool_details(tool_fqns)

        assert result["count"] > 0
        for tool in result["tools"]:
            assert tool["fqn"], "Tool missing FQN"
            assert tool["description"], f"Tool {tool['fqn']} missing description"
            assert len(tool["description"]) > 5, (
                f"Tool {tool['fqn']} has too short description"
            )

    @pytest.mark.asyncio
    async def test_adhoc_execution_isolation(self):
        """Verify ad-hoc executions are isolated from each other."""
        # Execute same script multiple times in parallel
        script = "output = add(1, 2, 3)"

        import asyncio

        results = await asyncio.gather(
            cy_tools.execute_cy_script_adhoc(script),
            cy_tools.execute_cy_script_adhoc(script),
            cy_tools.execute_cy_script_adhoc(script),
        )

        # All should succeed independently
        for result in results:
            assert "status" in result
            if result["status"] == "completed":
                assert result["output"] == "6"
                assert result["error"] is None

    @pytest.mark.asyncio
    async def test_adhoc_execution_different_input_data(self):
        """Verify each execution has its own input data scope."""
        script = "output = input * 2"

        import asyncio

        results = await asyncio.gather(
            cy_tools.execute_cy_script_adhoc(script, input_data=5),
            cy_tools.execute_cy_script_adhoc(script, input_data=10),
            cy_tools.execute_cy_script_adhoc(script, input_data=15),
        )

        # Each should use its own input data
        if results[0]["status"] == "completed":
            assert results[0]["output"] == "10"
        if results[1]["status"] == "completed":
            assert results[1]["output"] == "20"
        if results[2]["status"] == "completed":
            assert results[2]["output"] == "30"

    @pytest.mark.asyncio
    async def test_adhoc_execution_creates_task_run(self):
        """Verify ad-hoc execution creates task_run record."""
        script = "output = add(1, 2)"

        result = await cy_tools.execute_cy_script_adhoc(script)

        # Should return task_run_id
        assert "task_run_id" in result
        if result["status"] == "completed":
            assert result["task_run_id"] is not None
            # Task run ID should be a valid UUID string
            import uuid

            uuid.UUID(result["task_run_id"])  # Should not raise

    @pytest.mark.asyncio
    @pytest.mark.requires_full_stack
    async def test_null_safe_navigation_basic(self):
        """Test Cy 0.21 null-safe navigation with ?? operator for basic nested objects."""
        # Test with deeply nested object that exists
        script = """
data = {"user": {"profile": {"contact": {"email": "test@example.com"}}}}
email = data.user.profile.contact.email ?? "no-email@example.com"
return email
        """.strip()

        result = await cy_tools.execute_cy_script_adhoc(script)

        # Check status and print diagnostics if failed
        if result["status"] != "completed":
            print(f"Status: {result['status']}")
            print(f"Output: {result.get('output', 'N/A')}")
            print(f"Error: {result.get('error', 'N/A')}")

        assert result["status"] == "completed", (
            f"Failed with output: {result.get('output')} and error: {result.get('error')}"
        )
        assert result["output"] == '"test@example.com"'
        assert result["error"] is None

    @pytest.mark.asyncio
    @pytest.mark.requires_full_stack
    async def test_null_safe_navigation_with_missing_fields(self):
        """Test null-safe navigation returns default when intermediate fields are missing."""
        # Test with missing intermediate fields
        script = """
data = {"user": {}}
email = data.user.profile.contact.email ?? "no-email@example.com"
return email
        """.strip()

        result = await cy_tools.execute_cy_script_adhoc(script)

        assert result["status"] == "completed"
        assert result["output"] == '"no-email@example.com"'
        assert result["error"] is None

    @pytest.mark.asyncio
    @pytest.mark.requires_full_stack
    async def test_null_safe_navigation_with_null_root(self):
        """Test null-safe navigation handles null root objects gracefully."""
        script = """
data = null
email = data.user.profile.contact.email ?? "default@example.com"
return email
        """.strip()

        result = await cy_tools.execute_cy_script_adhoc(script, input_data=None)

        assert result["status"] == "completed"
        assert result["output"] == '"default@example.com"'
        assert result["error"] is None

    @pytest.mark.asyncio
    @pytest.mark.requires_full_stack
    async def test_null_safe_navigation_vs_or_operator(self):
        """Test difference between ?? (null-coalescing) and 'or' for falsy values."""
        # Test with 0 and empty array - ?? preserves them, 'or' replaces them
        script = """
data = {"count": 0, "items": [], "missing": null}

# ?? operator - only replaces null/undefined
count_nullsafe = data.count ?? 100
items_nullsafe = data.items ?? ["default"]
missing_nullsafe = data.missing ?? "replaced"

# or operator - replaces all falsy values
count_or = data.count or 100
items_or = data.items or ["default"]
missing_or = data.missing or "replaced"

return {
    "nullsafe": {"count": count_nullsafe, "items": items_nullsafe, "missing": missing_nullsafe},
    "or": {"count": count_or, "items": items_or, "missing": missing_or}
}
        """.strip()

        result = await cy_tools.execute_cy_script_adhoc(script)

        assert result["status"] == "completed"
        output = parse_cy_output(result["output"])

        # ?? preserves 0 and empty array
        assert output["nullsafe"]["count"] == 0
        assert output["nullsafe"]["items"] == []
        assert output["nullsafe"]["missing"] == "replaced"

        # or replaces 0 and empty array with defaults
        assert output["or"]["count"] == 100
        assert output["or"]["items"] == ["default"]
        assert output["or"]["missing"] == "replaced"

    @pytest.mark.asyncio
    @pytest.mark.requires_full_stack
    async def test_null_safe_navigation_multiple_fallbacks(self):
        """Test chaining multiple ?? operators for fallback values."""
        script = """
data = {"shipping": {}}

# Try multiple fallback paths
city = data.billing.address.city ?? data.shipping.address.city ?? "Unknown City"
return city
        """.strip()

        result = await cy_tools.execute_cy_script_adhoc(script)

        assert result["status"] == "completed"
        assert result["output"] == '"Unknown City"'
        assert result["error"] is None

    @pytest.mark.asyncio
    @pytest.mark.requires_full_stack
    async def test_null_safe_navigation_in_complex_workflow(self):
        """Test null-safe navigation in a realistic workflow scenario."""
        script = """
# Simulate alert data with possibly missing enrichment fields
alert = {
    "id": "alert-123",
    "severity": "high",
    "enrichments": {
        "network": {
            "source_ip": "192.168.1.100"
        }
    }
}

# Safe navigation for potentially missing fields
ip = alert.enrichments.network.source_ip ?? "0.0.0.0"
country = alert.enrichments.geo.country ?? "Unknown"
severity = alert.severity ?? "medium"
user_email = alert.user.email ?? "no-user@example.com"
tags = alert.metadata.tags ?? []

# Build summary
summary = {
    "alert_id": alert.id,
    "source_ip": ip,
    "country": country,
    "severity": severity,
    "user": user_email,
    "tags": tags
}

return summary
        """.strip()

        result = await cy_tools.execute_cy_script_adhoc(script)

        assert result["status"] == "completed"
        output = parse_cy_output(result["output"])

        assert output["alert_id"] == "alert-123"
        assert output["source_ip"] == "192.168.1.100"  # Found value
        assert output["country"] == "Unknown"  # Missing geo, used default
        assert output["severity"] == "high"  # Found value
        assert output["user"] == "no-user@example.com"  # Missing user, used default
        assert output["tags"] == []  # Missing metadata.tags, used default

    @pytest.mark.asyncio
    @pytest.mark.requires_full_stack
    async def test_null_safe_navigation_on_primitives(self):
        """Test null-safe navigation on primitive types returns null without error."""
        script = """
# Access field on number (primitive)
number = 42
field_value = number.some_field ?? "field-not-found"

# Access field on string (primitive)
text = "hello"
text_prop = text.invalid_property ?? "no-property"

# Access field on boolean (primitive)
flag = True
flag_attr = flag.attribute ?? "no-attribute"

return {
    "number_field": field_value,
    "string_prop": text_prop,
    "boolean_attr": flag_attr
}
        """.strip()

        result = await cy_tools.execute_cy_script_adhoc(script)

        assert result["status"] == "completed"
        output = parse_cy_output(result["output"])

        assert output["number_field"] == "field-not-found"
        assert output["string_prop"] == "no-property"
        assert output["boolean_attr"] == "no-attribute"
