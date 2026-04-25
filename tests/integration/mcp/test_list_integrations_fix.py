"""
Test that list_integrations returns correct integration_id values
that can be used with execute_integration_tool.
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.mcp import integration_tools
from analysi.mcp.context import set_tenant
from analysi.models.integration import Integration


@pytest.mark.asyncio
@pytest.mark.integration
class TestListIntegrationsReturnsCorrectIds:
    """Test that list_integrations returns database integration_ids."""

    @pytest.fixture
    def unique_id(self):
        """Generate unique ID suffix for test isolation."""
        return uuid4().hex[:8]

    @pytest.mark.asyncio
    async def test_list_integrations_returns_database_ids(
        self, integration_test_session: AsyncSession, unique_id: str
    ):
        """
        Test that list_integrations(configured_only=True) returns actual
        database integration_ids that can be used with execute_integration_tool.
        """
        tenant_id = f"test-tenant-{unique_id}"
        echo_id = f"echo-edr-prod-{unique_id}"
        splunk_id = f"splunk-main-{unique_id}"

        # Create test integrations in database with specific IDs
        integrations = [
            Integration(
                integration_id=echo_id,  # This is what should be returned
                tenant_id=tenant_id,
                integration_type="echo_edr",  # This is the framework type
                name="Echo EDR Production",
                enabled=True,
                settings={},
            ),
            Integration(
                integration_id=splunk_id,  # This is what should be returned
                tenant_id=tenant_id,
                integration_type="splunk",  # This is the framework type
                name="Splunk Main Instance",
                enabled=True,
                settings={},
            ),
        ]
        for integration in integrations:
            integration_test_session.add(integration)
        await integration_test_session.commit()

        # Set tenant context
        set_tenant(tenant_id)

        # Act: List configured integrations
        result = await integration_tools.list_integrations(configured_only=True)

        # Assert: Should return database integration_ids, not framework types
        assert result["count"] == 2
        assert result["filtered"] is True

        integration_ids = {i["integration_id"] for i in result["integrations"]}
        integration_types = {i["integration_type"] for i in result["integrations"]}

        # Database integration_ids should be returned
        assert echo_id in integration_ids
        assert splunk_id in integration_ids

        # Framework types should also be included separately
        assert "echo_edr" in integration_types
        assert "splunk" in integration_types

        # Should NOT return just framework types as integration_id
        assert (
            "echo_edr" not in integration_ids
        )  # Framework type shouldn't be integration_id
        assert (
            "splunk" not in integration_ids
        )  # Framework type shouldn't be integration_id

    @pytest.mark.asyncio
    async def test_list_integrations_ids_work_with_execute_tool(
        self, integration_test_session: AsyncSession, unique_id: str
    ):
        """
        Test that integration_ids from list_integrations can be used
        directly with execute_integration_tool.
        """
        tenant_id = f"test-tenant-{unique_id}"
        integration_id = f"test-echo-edr-instance-{unique_id}"

        # Create a test integration
        integration = Integration(
            integration_id=integration_id,
            tenant_id=tenant_id,
            integration_type="echo_edr",
            name="Test Echo EDR",
            enabled=True,
            settings={},
        )
        integration_test_session.add(integration)
        await integration_test_session.commit()

        # Set tenant context
        set_tenant(tenant_id)

        # Step 1: List integrations
        list_result = await integration_tools.list_integrations(configured_only=True)

        # Step 2: Get the integration_id from list result
        assert list_result["count"] == 1
        returned_integration_id = list_result["integrations"][0]["integration_id"]

        # Should return the database integration_id
        assert returned_integration_id == integration_id

        # Step 3: Use that integration_id with execute_integration_tool
        execute_result = await integration_tools.execute_integration_tool(
            integration_id=returned_integration_id,  # Use ID from list_integrations
            action_id="get_host_details",
            arguments={"hostname": "test-host"},
        )

        # Should NOT get "integration not found" error
        error_msg = execute_result.get("error") or ""
        assert "not found" not in error_msg.lower()

        # Should either succeed or fail with connection error (not configuration error)
        assert execute_result["status"] in ["success", "error"]

    @pytest.mark.asyncio
    async def test_list_integrations_with_configured_only_false(
        self, integration_test_session: AsyncSession, unique_id: str
    ):
        """
        Test that list_integrations(configured_only=False) returns
        framework integration types.
        """
        tenant_id = f"default-{unique_id}"
        set_tenant(tenant_id)

        # Act: List all framework integrations
        result = await integration_tools.list_integrations(configured_only=False)

        # Assert: Should return many framework integrations
        assert result["count"] > 10  # We have 36 framework integrations
        assert result["filtered"] is False

        # Should include framework types
        integration_ids = {i["integration_id"] for i in result["integrations"]}
        assert "splunk" in integration_ids
        assert "echo_edr" in integration_ids
        assert "virustotal" in integration_ids

    @pytest.mark.asyncio
    async def test_list_integrations_includes_integration_type(
        self, integration_test_session: AsyncSession, unique_id: str
    ):
        """
        Test that list_integrations includes both integration_id and
        integration_type for configured integrations.
        """
        tenant_id = f"test-tenant-{unique_id}"
        integration_id = f"my-custom-splunk-{unique_id}"

        # Create integration with specific ID and type
        integration = Integration(
            integration_id=integration_id,
            tenant_id=tenant_id,
            integration_type="splunk",
            name="My Custom Splunk",
            enabled=True,
            settings={},
        )
        integration_test_session.add(integration)
        await integration_test_session.commit()

        set_tenant(tenant_id)

        # Act
        result = await integration_tools.list_integrations(configured_only=True)

        # Assert
        assert result["count"] == 1
        integration_data = result["integrations"][0]

        # Should have both fields
        assert "integration_id" in integration_data
        assert "integration_type" in integration_data

        # Values should be correct
        assert integration_data["integration_id"] == integration_id
        assert integration_data["integration_type"] == "splunk"

        # Should also include metadata from framework
        assert "archetypes" in integration_data
        assert "SIEM" in integration_data["archetypes"]
