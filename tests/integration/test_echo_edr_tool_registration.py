"""
Integration test to reproduce echo_edr tool loading issue.

This test verifies that echo_edr::pull_browser_history tool is correctly
registered in the database with its 'ip' parameter schema.

Reproduces bug where compile_cy_script reports:
"tool 'app::echo_edr::pull_browser_history' has no parameter 'ip'"
even though the manifest clearly defines 'ip' as a required parameter.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.mcp.context import set_tenant
from analysi.models.component import Component
from analysi.models.knowledge_unit import KUTool, KUType
from analysi.services.cy_tool_registry import load_tool_registry_async


@pytest.mark.asyncio
@pytest.mark.integration
class TestEchoEDRToolRegistration:
    """Test echo_edr tool registration and schema loading."""

    @pytest.mark.asyncio
    async def test_echo_edr_tools_not_in_database_come_from_manifests(
        self, integration_test_session: AsyncSession
    ):
        """
        Test that echo_edr tools are NOT in database (they come from manifests).

        This test documents the architecture decision that framework tools
        (like echo_edr) are loaded from manifests at runtime, not stored in
        the database as KUTool records.

        This is by design - framework tools are ephemeral and always loaded
        fresh from manifest files.
        """
        # Query database for echo_edr::pull_browser_history tool
        stmt = (
            select(KUTool)
            .join(Component, KUTool.component_id == Component.id)
            .where(
                Component.tenant_id == "default",
                Component.name == "echo_edr::pull_browser_history",
                Component.ku_type == KUType.TOOL,
            )
        )
        result = await integration_test_session.execute(stmt)
        tool = result.scalars().first()

        # Assert: Tool should NOT be in database (comes from manifests)
        assert tool is None, (
            "echo_edr::pull_browser_history should NOT be in database. "
            "Framework tools are loaded from manifests, not stored as KUTool records."
        )

        print("\n✅ Confirmed: echo_edr tools come from manifests, not database")
        print("✅ This is the correct architecture for framework tools")

    @pytest.mark.asyncio
    async def test_echo_edr_tool_appears_in_tool_registry(
        self, integration_test_session: AsyncSession
    ):
        """
        Test that echo_edr::pull_browser_history appears in tool registry with 'ip' parameter.

        This verifies that load_tool_registry_async correctly loads the tool and its schema.
        """
        # Load tool registry (same as compile_cy_script does)
        tool_registry = await load_tool_registry_async(
            integration_test_session, "default"
        )

        # Check if echo_edr tool is in registry
        tool_fqn = "app::echo_edr::pull_browser_history"

        print("\n=== DEBUG: Tool Registry ===")
        print(f"Total tools: {len(tool_registry)}")
        echo_tools = [k for k in tool_registry if "echo_edr" in k]
        print(f"Echo EDR tools: {echo_tools}")

        assert tool_fqn in tool_registry, (
            f"Tool {tool_fqn} not found in tool registry! "
            f"Expected load_tool_registry_async to load it from database. "
            f"Echo EDR tools found: {echo_tools}"
        )

        # Verify tool schema has 'ip' parameter
        tool_schema = tool_registry[tool_fqn]
        parameters = tool_schema.get("parameters", {})

        print("\n=== DEBUG: Tool Schema ===")
        print(f"Parameters: {list(parameters.keys())}")
        print(f"Required: {tool_schema.get('required', [])}")

        assert "ip" in parameters, (
            f"Tool registry missing 'ip' parameter for {tool_fqn}! "
            f"Expected it to be extracted from input_schema. "
            f"Got parameters: {list(parameters.keys())}"
        )

        # Verify 'ip' parameter schema details
        ip_param = parameters["ip"]
        print("\n=== DEBUG: IP Parameter Schema ===")
        print(f"Full schema: {ip_param}")

        assert "type" in ip_param, (
            f"Parameter 'ip' should have 'type' field. Got: {ip_param}"
        )
        assert ip_param["type"] == "string", (
            f"Parameter 'ip' should be type 'string', got: {ip_param['type']}"
        )
        assert "description" in ip_param, (
            f"Parameter 'ip' should have 'description' field. Got: {ip_param}"
        )

        # Verify 'ip' is required
        required = tool_schema.get("required", [])
        assert "ip" in required, (
            f"Parameter 'ip' should be required in tool registry. "
            f"Got required: {required}"
        )

        print(f"\n✅ Tool registry has correct schema for {tool_fqn}")
        print(
            "✅ Parameter 'ip' is present, required, and has correct type/description"
        )

    @pytest.mark.asyncio
    async def test_compile_cy_script_with_echo_edr_tool(
        self, integration_test_session: AsyncSession
    ):
        """
        Test that compile_cy_script successfully validates scripts using echo_edr tools.

        This is the end-to-end test that reproduces the original bug report.
        """
        from analysi.mcp.tools import cy_tools

        # Script that uses echo_edr::pull_browser_history with 'ip' parameter
        script = """
endpoint_ip = input.ip ?? "192.168.1.100"
browser_data = app::echo_edr::pull_browser_history(
    ip=endpoint_ip,
    start_time="2024-01-01T00:00:00Z",
    end_time="2024-01-02T00:00:00Z"
)

return {
    "browser_history": browser_data
}
"""

        # Set tenant context
        set_tenant("default")

        # Compile script (should load echo_edr tools from database)
        result = await cy_tools.compile_cy_script(script)

        print("\n=== DEBUG: Compilation Result ===")
        print(f"Tools loaded: {result.get('tools_loaded', 0)}")
        print(f"Validation errors: {result.get('validation_errors')}")
        print(f"Plan: {'SUCCESS' if result['plan'] is not None else 'FAILED'}")

        # BUG REPRODUCTION: With the current implementation, this should fail with:
        # "tool 'app::echo_edr::pull_browser_history' has no parameter 'ip'"
        #
        # If the test passes, the bug is fixed. If it fails, we need to investigate why.
        assert result["plan"] is not None, (
            f"Compilation failed! Expected compile_cy_script to load echo_edr tools "
            f"from database and validate the script successfully. "
            f"Validation errors: {result.get('validation_errors')}. "
            f"Tools loaded: {result.get('tools_loaded', 0)}"
        )

        assert len(result.get("validation_errors", [])) == 0, (
            f"Should have no validation errors. Got: {result.get('validation_errors')}"
        )

        print("\n✅ SUCCESS: echo_edr::pull_browser_history compiled successfully")
        print("✅ Parameter 'ip' was recognized by compiler")
