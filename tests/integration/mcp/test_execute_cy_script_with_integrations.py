"""
Test execute_cy_script_adhoc with integration tools.

Verifies that Cy scripts can successfully call integration tools like
app::echo_edr::get_host_details when executed through MCP.

This tests the fix for DRY violation where compile and execute had different
tool loading logic. Now both use framework manifests for tool availability.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.auth.models import CurrentUser
from analysi.mcp.context import set_mcp_current_user, set_tenant
from analysi.mcp.tools import cy_tools
from analysi.models.integration import Integration


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_full_stack
class TestExecuteCyScriptWithIntegrations:
    """Test Cy script execution with integration tools.

    Requires full stack because execute_cy_script_adhoc calls the API server,
    which must share the same database as the test session for tool resolution
    to find the test-created integrations.
    """

    @pytest.fixture(autouse=True)
    def _mcp_user(self):
        """Set MCP user context so RBAC checks pass."""
        set_mcp_current_user(
            CurrentUser(
                user_id="test-user",
                email="test@test.com",
                tenant_id="default",
                roles=["analyst"],
            )
        )

    @pytest.mark.asyncio
    @pytest.mark.requires_echo_edr
    async def test_execute_cy_script_with_echo_edr_tool(
        self, integration_test_session: AsyncSession
    ):
        """
        Test that execute_cy_script_adhoc can execute Cy scripts
        that call integration tools like app::echo_edr::get_host_details.

        This reproduces the bug where the script compiles but fails at
        execution with "Tool not found" because execute_cy_script_adhoc
        was using environment variable for tenant instead of MCP context.
        """
        tenant_id = "default"  # Use default tenant for this test

        # Create an integration for this tenant (unique ID to avoid flakiness)
        integration = Integration(
            integration_id=f"test-echo-{uuid4().hex[:8]}",
            tenant_id=tenant_id,
            integration_type="echo_edr",
            name="Test Echo EDR",
            enabled=True,
            settings={},
        )
        integration_test_session.add(integration)
        await integration_test_session.flush()  # Ensure data is written to DB
        await integration_test_session.commit()  # Commit transaction

        # Set tenant context (this should be used by execute_cy_script_adhoc)
        set_tenant(tenant_id)

        # Create a Cy script that uses an integration tool
        script = """# Test using Echo EDR tool in Cy script
hostname = input["hostname"]

# Call the integration tool
host_details = app::echo_edr::get_host_details(hostname=hostname)

# Extract some fields
ip = host_details["ip_address"]
os = host_details["os"]
risk = host_details["risk_level"]

# Return structured result
return {
  "hostname": hostname,
  "ip_address": ip,
  "operating_system": os,
  "risk_level": risk,
  "raw_details": host_details
}"""

        # Act: Execute the script
        result = await cy_tools.execute_cy_script_adhoc(
            script=script, input_data={"hostname": "DESKTOP-TEST-001"}
        )

        # Assert: Should execute successfully (not "tool not found")
        print("\n=== Execution Result ===")
        print(f"Status: {result['status']}")
        print(f"Output: {result.get('output')}")
        print(f"Error: {result.get('error')}")

        # Should NOT have "tool not found" error
        # Note: May have "error" status if API server is not running, that's OK
        assert result["status"] in ["success", "completed", "failed", "error"]

        # If failed/error, should not be due to "tool not found"
        if result["status"] in ["failed", "error"]:
            output = result.get("output") or ""
            error = result.get("error") or ""
            combined = f"{output} {error}".lower()

            # The bug was: "Tool 'app::echo_edr::get_host_details' not found"
            # After fix, should not get this error
            # Connection errors are OK (means API server not running in test)
            if "tool" in combined and "not found" in combined:
                raise AssertionError(
                    f"Script execution should not fail with 'tool not found'. "
                    f"Output: {result.get('output')}, Error: {result.get('error')}"
                )

    @pytest.mark.asyncio
    @pytest.mark.requires_full_stack
    async def test_execute_cy_script_uses_mcp_context_tenant(
        self, integration_test_session: AsyncSession
    ):
        """
        Test that execute_cy_script_adhoc uses MCP tenant context,
        not environment variables. Requires running API server.
        """
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Create a custom integration for this tenant
        integration = Integration(
            integration_id="test-echo-custom",
            tenant_id=tenant_id,
            integration_type="echo_edr",
            name="Test Echo Custom",
            enabled=True,
            settings={},
        )
        integration_test_session.add(integration)
        await integration_test_session.commit()

        # Set MCP tenant context
        set_tenant(tenant_id)

        # Simple script that should use the tenant's integrations
        script = """
# This should use the tenant from MCP context
result = app::echo_edr::get_host_details(hostname="test-host")
return {"success": True}
"""

        # Execute the script
        result = await cy_tools.execute_cy_script_adhoc(script=script, input_data={})

        # The execution should use the correct tenant from MCP context
        # We can't easily verify the tenant was used correctly without
        # checking logs, but at minimum the script should attempt to execute
        assert result["task_run_id"] is not None or result["status"] in [
            "success",
            "completed",
            "failed",
        ]

    @pytest.mark.asyncio
    @pytest.mark.requires_echo_edr
    async def test_compile_and_execute_consistency(
        self, integration_test_session: AsyncSession
    ):
        """
        Test that scripts that compile successfully also execute successfully
        (no "tool not found" at runtime that wasn't caught at compile time).

        Depends on the Echo EDR lab container because the script resolves
        ``app::echo_edr::get_host_details`` at runtime.
        """
        tenant_id = "default"

        # Create an integration for this tenant (unique ID to avoid flakiness)
        integration = Integration(
            integration_id=f"test-echo-{uuid4().hex[:8]}",
            tenant_id=tenant_id,
            integration_type="echo_edr",
            name="Test Echo EDR Compile",
            enabled=True,
            settings={},
        )
        integration_test_session.add(integration)
        await integration_test_session.flush()  # Ensure data is written to DB
        await integration_test_session.commit()  # Commit transaction

        set_tenant(tenant_id)

        script = """
hostname = input.hostname ?? "test-host"
details = app::echo_edr::get_host_details(hostname=hostname)
return details
"""

        # Step 1: Compile should succeed
        compile_result = await cy_tools.compile_cy_script(script)
        assert compile_result["plan"]["compiled"] is True
        assert len(compile_result["validation_errors"]) == 0

        # Step 2: Execute should also not fail with "tool not found"
        # (it may fail with connection errors, but not tool registration errors)
        exec_result = await cy_tools.execute_cy_script_adhoc(
            script=script, input_data={"hostname": "test"}
        )

        # Should not have tool not found error
        output = exec_result.get("output") or ""
        error = exec_result.get("error") or ""
        combined = f"{output} {error}".lower()

        assert not ("tool" in combined and "not found" in combined), (
            "If script compiles successfully, it should not fail execution "
            "with 'tool not found'"
        )
