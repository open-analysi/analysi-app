"""
Integration test for KU Tool auto-registration from framework manifests.

Tests that tool actions from integration manifests are automatically registered
as KU Tools, making them discoverable by Cy scripts.
"""

import pytest

from analysi.repositories.knowledge_unit import KnowledgeUnitRepository
from analysi.services.integration_registry_service import IntegrationRegistryService


@pytest.mark.integration
class TestKUToolRegistration:
    """Test framework tool registration in KU API."""

    @pytest.mark.asyncio
    async def test_register_echo_edr_tools(self, integration_test_session):
        """Test that framework tool actions are registered as KU Tools."""
        registry = IntegrationRegistryService()
        ku_repo = KnowledgeUnitRepository(integration_test_session)

        # Register tools
        tenant_id = "test-tenant"
        registered_count = await registry.register_tools_in_ku_api(
            integration_test_session, tenant_id
        )

        # Should register at least 27 tools (increases as we add more integrations)
        # Core integrations: Echo EDR (8) + Splunk (8) + VirusTotal (6) + AbuseIPDB (5) = 27
        # Note: sourcetype_discovery is now a connector, not a tool
        assert registered_count >= 27, (
            f"Expected at least 27 tools, got {registered_count}"
        )

        # Verify tools were created
        isolate_tool = await ku_repo.get_tool_by_name(
            tenant_id, "echo_edr::isolate_host"
        )
        assert isolate_tool is not None
        assert isolate_tool.tool_type == "app"
        assert isolate_tool.component.name == "echo_edr::isolate_host"
        assert (
            "response" in isolate_tool.component.categories
            or "containment" in isolate_tool.component.categories
        )

        release_tool = await ku_repo.get_tool_by_name(
            tenant_id, "echo_edr::release_host"
        )
        assert release_tool is not None

        scan_tool = await ku_repo.get_tool_by_name(tenant_id, "echo_edr::scan_host")
        assert scan_tool is not None

        details_tool = await ku_repo.get_tool_by_name(
            tenant_id, "echo_edr::get_host_details"
        )
        assert details_tool is not None

    @pytest.mark.asyncio
    async def test_tool_registration_idempotent(self, integration_test_session):
        """Test that registering tools multiple times doesn't create duplicates."""
        registry = IntegrationRegistryService()

        tenant_id = "test-tenant"

        # Register tools first time
        first_count = await registry.register_tools_in_ku_api(
            integration_test_session, tenant_id
        )
        assert first_count >= 27, (
            f"Expected at least 27 tools, got {first_count}"
        )  # Echo EDR (8) + Splunk (8) + VirusTotal (6) + AbuseIPDB (5)

        # Register tools second time (should skip existing)
        second_count = await registry.register_tools_in_ku_api(
            integration_test_session, tenant_id
        )
        assert second_count == 0  # No new tools registered

    @pytest.mark.asyncio
    async def test_tool_naming_convention(self, integration_test_session):
        """Test that tools follow integration_type::action_id naming convention."""
        registry = IntegrationRegistryService()
        ku_repo = KnowledgeUnitRepository(integration_test_session)

        tenant_id = "test-tenant"
        await registry.register_tools_in_ku_api(integration_test_session, tenant_id)

        # Verify naming convention: {integration_type}::{action_id}
        tool = await ku_repo.get_tool_by_name(tenant_id, "echo_edr::isolate_host")
        assert tool is not None
        assert "::" in tool.component.name
        parts = tool.component.name.split("::")
        assert len(parts) == 2
        assert parts[0] == "echo_edr"  # integration_type
        assert parts[1] == "isolate_host"  # action_id

    @pytest.mark.asyncio
    async def test_tool_has_cy_name(self, integration_test_session):
        """Test that registered tools have Cy-callable names."""
        registry = IntegrationRegistryService()
        ku_repo = KnowledgeUnitRepository(integration_test_session)

        tenant_id = "test-tenant"
        await registry.register_tools_in_ku_api(integration_test_session, tenant_id)

        tool = await ku_repo.get_tool_by_name(tenant_id, "echo_edr::isolate_host")
        assert tool is not None
        assert tool.component.cy_name is not None
        assert len(tool.component.cy_name) > 0
        # cy_name should be a valid Cy identifier (sanitized from name)
        assert tool.component.cy_name == "echo_edr_isolate_host"
