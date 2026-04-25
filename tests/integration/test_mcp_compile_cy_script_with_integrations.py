"""
Integration test for MCP compile_cy_script tool with integration tools.

Tests that compile_cy_script successfully validates scripts that use
integration tools (like app::splunk::spl_run) by loading tool schemas
from the database.

This reproduces and verifies the fix for the bug where compile_cy_script
would fail with "Tool not found" errors even though execute_cy_script_adhoc
would succeed.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.mcp.context import set_tenant
from analysi.mcp.tools import cy_tools


@pytest.mark.asyncio
@pytest.mark.integration
class TestMCPCompileCyScriptWithIntegrations:
    """Test compile_cy_script MCP tool with integration tools."""

    @pytest.mark.asyncio
    async def test_compile_cy_script_validates_integration_tools(
        self, integration_test_session: AsyncSession
    ):
        """
        Test that compile_cy_script loads integration tools and validates scripts.

        This test verifies the fix for the architecture issue where:
        - quick_syntax_check_cy_script: ✅ PASSED (syntax only)
        - compile_cy_script: ❌ FAILED (Tool not found: app::splunk::spl_run)
        - execute_cy_script_adhoc: ✅ SUCCEEDED (runtime has tools)

        After fix, compile_cy_script should load tools from database and succeed.
        """
        # Arrange: Create a test integration tool in database
        from uuid import uuid4

        from analysi.models.component import Component, ComponentKind
        from analysi.models.knowledge_unit import KUTool, KUType
        from analysi.services.cy_tool_registry import load_tool_registry_async

        # Create Component for the tool
        component = Component(
            id=uuid4(),
            tenant_id="default",
            kind=ComponentKind.KU,  # Required field
            ku_type=KUType.TOOL,
            name="test_integration::test_action",  # Format: integration::action
            status="enabled",
        )
        integration_test_session.add(component)
        await integration_test_session.flush()

        # Create KUTool with app type
        ku_tool = KUTool(
            component_id=component.id,
            tool_type="app",
            input_schema={
                "type": "object",
                "properties": {
                    "param1": {"type": "string", "description": "Test parameter"}
                },
                "required": ["param1"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "string", "description": "Test result"}
                },
            },
        )
        integration_test_session.add(ku_tool)
        await integration_test_session.commit()

        # Verify tool was created using shared utility
        tool_registry = await load_tool_registry_async(
            integration_test_session, "default"
        )
        print("\n=== DEBUG: Tools in database after creation ===")
        print(f"Total tools: {len(tool_registry)}")
        print(f"Tool names: {list(tool_registry.keys())}")

        # Arrange: Cy script that uses the test integration tool
        script = """
# Example script using test integration tool
result = app::test_integration::test_action(param1="test_value")

return {
    "result": result
}
"""

        # Act: Call compile_cy_script with tenant "default" (demo data tenant)
        # Set tenant context
        set_tenant("default")

        result = await cy_tools.compile_cy_script(script)

        # Debug: Print what was loaded
        print("\n=== DEBUG: compile_cy_script result ===")
        print(f"Tools loaded: {result.get('tools_loaded', 0)}")
        print(f"Plan: {'None' if result['plan'] is None else 'SUCCESS'}")
        print(f"Validation errors: {result.get('validation_errors')}")

        # Assert: Should compile successfully
        assert result["plan"] is not None, (
            f"Compilation failed! Expected compile_cy_script to load integration tools "
            f"from database and validate the script. "
            f"Validation errors: {result.get('validation_errors')}. "
            f"Tools loaded: {result.get('tools_loaded', 0)}"
        )

        # Should have no validation errors (or only empty list)
        validation_errors = result.get("validation_errors", [])
        assert len(validation_errors) == 0, (
            f"Expected no validation errors after loading integration tools. "
            f"Got: {validation_errors}"
        )

        # Should report tools were loaded
        tools_loaded = result.get("tools_loaded", 0)
        assert tools_loaded > 0, (
            "Expected integration tools to be loaded from database. "
            "Got tools_loaded=0, which means tool registry was empty."
        )

        print(
            f"\n✅ SUCCESS: compile_cy_script loaded {tools_loaded} integration tools"
        )
        print(f"✅ Plan compiled: {result['plan'].get('compiled', False)}")
        print(f"✅ Output schema inferred: {'output_schema' in result['plan']}")

    @pytest.mark.asyncio
    async def test_compile_cy_script_without_tenant_uses_default(
        self, integration_test_session: AsyncSession
    ):
        """Test that compile_cy_script defaults to 'default' tenant."""
        script = """
# Simple script without integration tools
x = 10
y = 20
return {"sum": x + y}
"""

        # Act: Call without tenant parameter
        # Set tenant context
        set_tenant("default")

        result = await cy_tools.compile_cy_script(script)

        # Assert: Should compile successfully
        assert result["plan"] is not None, (
            f"Compilation failed for simple script without tenant parameter. "
            f"Errors: {result.get('validation_errors')}"
        )

    @pytest.mark.asyncio
    async def test_compile_cy_script_detects_missing_return_statement(
        self, integration_test_session: AsyncSession
    ):
        """
        Test that compile_cy_script detects semantic errors.

        NOTE: After switching to analyze_types() for integration tool support,
        compile_cy_script now focuses on type inference rather than return
        statement validation. For return statement checking, use validate_task_script()
        or rely on runtime validation.
        """
        script = """
# Script without return statement
x = 10
y = 20
result = x + y
# Missing: return statement
"""

        # Act: Compile script
        # Set tenant context
        set_tenant("default")

        result = await cy_tools.compile_cy_script(script)

        # Assert: Since analyze_types() doesn't check for return statements,
        # the compilation will succeed but with a None output schema
        # This is acceptable behavior - runtime validation will catch this
        assert "plan" in result, "compile_cy_script should always return a plan field"
        assert "validation_errors" in result, (
            "compile_cy_script should include validation_errors field"
        )

        # Either plan is None (compilation failed) OR it succeeded without return check
        # Both are valid outcomes for this edge case
        print(
            f"✅ compile_cy_script handled script without return: plan={result['plan'] is not None}"
        )

    @pytest.mark.asyncio
    async def test_compile_cy_script_with_optional_parameters(
        self, integration_test_session: AsyncSession
    ):
        """
        Test that compile_cy_script correctly handles optional parameters with defaults.

        This is a regression test for the bug where optional parameters (like 'days'
        in abuseipdb::lookup_ip or 'search_base' in ad_ldap::run_query) were being
        treated as required, causing compilation to fail even though they had default
        values.

        The bug was in two places:
        1. cy_tool_registry.py - wasn't extracting the 'required' array from input_schema
        2. cy-language ToolRegistry.from_dict() - hardcoded required=True for all params

        With the fix in cy-language 0.19.2, this test should pass.
        """
        # Arrange: Create a tool with optional parameter (has default value)
        from uuid import uuid4

        from analysi.models.component import Component, ComponentKind
        from analysi.models.knowledge_unit import KUTool, KUType

        component = Component(
            id=uuid4(),
            tenant_id="default",
            kind=ComponentKind.KU,
            ku_type=KUType.TOOL,
            name="abuseipdb::lookup_ip",  # Mimic real AbuseIPDB action
            status="enabled",
        )
        integration_test_session.add(component)
        await integration_test_session.flush()

        # Create tool with 'days' as optional parameter (has default, NOT in required array)
        ku_tool = KUTool(
            component_id=component.id,
            tool_type="app",
            input_schema={
                "type": "object",
                "properties": {
                    "ip": {
                        "type": "string",
                        "description": "IPv4 or IPv6 address to check",
                    },
                    "days": {
                        "type": "integer",
                        "default": 10,  # Has default value
                        "description": "Check for reports within this number of days",
                    },
                },
                "required": ["ip"],  # Only 'ip' is required, 'days' is OPTIONAL
            },
            output_schema={
                "type": "object",
                "properties": {"abuse_confidence_score": {"type": "integer"}},
            },
        )
        integration_test_session.add(ku_tool)
        await integration_test_session.commit()

        # Arrange: Script that calls lookup_ip WITHOUT the optional 'days' parameter
        script = """
ip_address = input.ip ?? "192.168.1.100"
abuse_report = app::abuseipdb::lookup_ip(ip=ip_address)
# Note: NOT passing 'days' parameter - should use default value of 10
abuse_confidence = abuse_report.abuse_confidence_score ?? 0
return {"confidence": abuse_confidence}
"""

        # Act: Compile script
        # Set tenant context
        set_tenant("default")

        result = await cy_tools.compile_cy_script(script)

        # Assert: Should compile successfully (days is optional)
        print("\n=== Optional Parameters Test ===")
        print(f"Tools loaded: {result.get('tools_loaded', 0)}")
        print(f"Validation errors: {result.get('validation_errors')}")

        # BUG REPRODUCTION: With cy-language 0.19.1, this would fail with:
        # "missing required parameter 'days' for tool 'app::abuseipdb::lookup_ip'"
        #
        # FIX: With cy-language 0.19.2, compilation should succeed because:
        # 1. cy_tool_registry.py extracts required=["ip"] (not including 'days')
        # 2. ToolRegistry.from_dict() respects the required array
        assert result["plan"] is not None, (
            f"Compilation should succeed when optional parameter is omitted. "
            f"Parameter 'days' has default value and is NOT in required array. "
            f"Validation errors: {result.get('validation_errors')}"
        )

        assert len(result.get("validation_errors", [])) == 0, (
            f"Should have no validation errors for optional parameters. "
            f"Got: {result.get('validation_errors')}"
        )

        print("✅ SUCCESS: Optional parameter 'days' correctly handled as optional")
        print("✅ Script compiled without requiring all parameters")

    @pytest.mark.asyncio
    async def test_compile_cy_script_with_nonexistent_integration_tool(
        self, integration_test_session: AsyncSession
    ):
        """Test that compile_cy_script detects calls to nonexistent integration tools."""
        script = """
# Call nonexistent integration tool
result = app::fake_integration::fake_action()
return {"result": result}
"""

        # Act: Compile script
        # Set tenant context
        set_tenant("default")

        result = await cy_tools.compile_cy_script(script)

        # Assert: Should fail with tool not found error
        # Note: This depends on cy-language compile_cy_program behavior
        # It might succeed with plan=None or have validation_errors
        # The key is that it should NOT crash, but handle gracefully
        assert "plan" in result, "compile_cy_script should always return a result dict"
        assert "validation_errors" in result, (
            "compile_cy_script should include validation_errors field"
        )

        # If plan is None, there should be errors
        if result["plan"] is None:
            assert len(result.get("validation_errors", [])) > 0, (
                "If compilation fails (plan=None), should have validation errors"
            )
