"""
Integration test for execute_integration_tool MCP tool.

Tests that execute_integration_tool successfully executes tools for properly
configured integrations.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.mcp import integration_tools
from analysi.mcp.context import set_tenant
from analysi.models.integration import Integration


@pytest.mark.asyncio
@pytest.mark.integration
class TestExecuteIntegrationTool:
    """Test execute_integration_tool MCP tool with real integrations."""

    @pytest.fixture
    def unique_id(self):
        """Generate unique ID suffix for test isolation."""
        return uuid4().hex[:8]

    @pytest.mark.asyncio
    async def test_execute_tool_with_configured_integration(
        self, integration_test_session: AsyncSession, unique_id: str
    ):
        """
        Test that execute_integration_tool works with a properly configured integration.

        This reproduces the bug where execute_integration_tool returns
        "Integration not found" even though the integration exists and is configured.
        """
        tenant_id = f"default-{unique_id}"
        integration_id = f"test-echo-edr-{unique_id}"

        # Create a test integration in database
        # Using echo_edr as it's available in the framework
        integration = Integration(
            integration_id=integration_id,  # User-facing ID
            tenant_id=tenant_id,
            integration_type="echo_edr",  # Framework integration type
            name="Test Echo EDR",
            description="Test integration for execute_integration_tool",
            enabled=True,
            settings={},
        )
        integration_test_session.add(integration)
        await integration_test_session.commit()

        # Set tenant context
        set_tenant(tenant_id)

        # Act: Execute a tool action
        # Using echo_edr's health_check action (should exist)
        result = await integration_tools.execute_integration_tool(
            integration_id=integration_id,  # Pass the integration_id (not integration_type)
            action_id="health_check",
            arguments={},
            capture_schema=False,
            timeout_seconds=30,
        )

        # Assert: Should execute successfully
        print("\n=== Execute Integration Tool Result ===")
        print(f"Status: {result.get('status')}")
        print(f"Error: {result.get('error')}")
        print(f"Output: {result.get('output')}")

        # BUG REPRODUCTION: With the current code, this fails with:
        # "Integration 'test-echo-edr' not found for tenant 'default'"
        #
        # Expected behavior: Should execute successfully since integration exists
        # and is enabled in the database.
        assert result["status"] in [
            "success",
            "error",
        ], f"Should execute (not fail with not found). Got: {result}"

        # Should NOT have "not found" error
        error = result.get("error", "")
        assert "not found" not in error.lower(), (
            f"Should not get 'not found' error for existing integration. Error: {error}"
        )

    @pytest.mark.asyncio
    async def test_execute_tool_with_nonexistent_integration(
        self, integration_test_session: AsyncSession, unique_id: str
    ):
        """Test that execute_integration_tool correctly reports nonexistent integrations."""
        tenant_id = f"default-{unique_id}"

        # Set tenant context
        set_tenant(tenant_id)

        # Act: Try to execute tool for nonexistent integration
        result = await integration_tools.execute_integration_tool(
            integration_id=f"nonexistent-integration-{unique_id}",
            action_id="some_action",
            arguments={},
        )

        # Assert: Should return error status
        assert result["status"] == "error"
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_execute_tool_with_disabled_integration(
        self, integration_test_session: AsyncSession, unique_id: str
    ):
        """Test that execute_integration_tool rejects disabled integrations."""
        tenant_id = f"test-tenant-{unique_id}"
        integration_id = f"test-disabled-{unique_id}"

        # Create a disabled integration
        integration = Integration(
            integration_id=integration_id,
            tenant_id=tenant_id,
            integration_type="echo_edr",
            name="Disabled Integration",
            enabled=False,  # Disabled
            settings={},
        )
        integration_test_session.add(integration)
        await integration_test_session.commit()

        # Set tenant context
        set_tenant(tenant_id)

        # Act: Try to execute tool
        result = await integration_tools.execute_integration_tool(
            integration_id=integration_id,
            action_id="health_check",
            arguments={},
        )

        # Assert: Should return error about disabled integration
        assert result["status"] == "error"
        assert "disabled" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_execute_tool_with_invalid_action(
        self, integration_test_session: AsyncSession, unique_id: str
    ):
        """Test that execute_integration_tool rejects invalid action IDs."""
        tenant_id = f"test-tenant-{unique_id}"
        integration_id = f"test-echo-edr-2-{unique_id}"

        # Create a valid integration
        integration = Integration(
            integration_id=integration_id,
            tenant_id=tenant_id,
            integration_type="echo_edr",
            name="Test Echo EDR 2",
            enabled=True,
            settings={},
        )
        integration_test_session.add(integration)
        await integration_test_session.commit()

        # Set tenant context
        set_tenant(tenant_id)

        # Act: Try to execute nonexistent action
        result = await integration_tools.execute_integration_tool(
            integration_id=integration_id,
            action_id="nonexistent_action",
            arguments={},
        )

        # Assert: Should return error about action not found
        assert result["status"] == "error"
        assert "action" in result["error"].lower()
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_execute_tool_with_schema_capture(
        self, integration_test_session: AsyncSession, unique_id: str
    ):
        """Test that execute_integration_tool can capture output schema."""
        tenant_id = f"test-tenant-{unique_id}"
        integration_id = f"test-echo-edr-3-{unique_id}"

        # Create integration
        integration = Integration(
            integration_id=integration_id,
            tenant_id=tenant_id,
            integration_type="echo_edr",
            name="Test Echo EDR 3",
            enabled=True,
            settings={},
        )
        integration_test_session.add(integration)
        await integration_test_session.commit()

        # Set tenant context
        set_tenant(tenant_id)

        # Act: Execute with schema capture
        result = await integration_tools.execute_integration_tool(
            integration_id=integration_id,
            action_id="health_check",
            arguments={},
            capture_schema=True,  # Request schema capture
        )

        # Assert: Should include output_schema if successful
        if result["status"] == "success":
            assert "output_schema" in result
            # Schema should be a dict (JSON Schema format)
            if result["output_schema"]:
                assert isinstance(result["output_schema"], dict)

    @pytest.mark.asyncio
    async def test_list_integrations_shows_configured_only(
        self, integration_test_session: AsyncSession, unique_id: str
    ):
        """
        Test that list_integrations correctly filters by configured integrations.

        This is related to execute_integration_tool since both need to work
        with the same integration_id values.
        """
        tenant_id = f"test-tenant-{unique_id}"
        splunk_integration_id = f"test-splunk-{unique_id}"
        echo_integration_id = f"test-echo-{unique_id}"

        # Create two integrations with different integration_types
        integration1 = Integration(
            integration_id=splunk_integration_id,
            tenant_id=tenant_id,
            integration_type="splunk",  # Type
            name="Test Splunk",
            enabled=True,
            settings={},
        )
        integration2 = Integration(
            integration_id=echo_integration_id,
            tenant_id=tenant_id,
            integration_type="echo_edr",  # Different type
            name="Test Echo",
            enabled=True,
            settings={},
        )
        integration_test_session.add(integration1)
        integration_test_session.add(integration2)
        await integration_test_session.commit()

        # Set tenant context
        set_tenant(tenant_id)

        # Act: List configured integrations
        result = await integration_tools.list_integrations(configured_only=True)

        # Assert: Should show both database integration instances
        integration_ids = [i["integration_id"] for i in result["integrations"]]
        integration_types = [i["integration_type"] for i in result["integrations"]]

        # After fix: list_integrations returns database integration_ids
        assert splunk_integration_id in integration_ids
        assert echo_integration_id in integration_ids

        # Integration types should also be included
        assert "splunk" in integration_types
        assert "echo_edr" in integration_types
