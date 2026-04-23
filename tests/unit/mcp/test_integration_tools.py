"""Unit tests for integration discovery tools."""

import pytest

from analysi.auth.models import CurrentUser
from analysi.mcp import integration_tools
from analysi.mcp.context import mcp_current_user_context


@pytest.mark.asyncio
class TestIntegrationDiscoveryTools:
    """Test integration discovery tools for MCP."""

    @pytest.fixture(autouse=True)
    def _set_mcp_user(self):
        """Set an authenticated MCP user for all tests."""
        user = CurrentUser(
            user_id="kc-test",
            email="user@test.com",
            tenant_id="test-tenant",
            roles=["analyst"],
            actor_type="user",
        )
        mcp_current_user_context.set(user)
        yield
        mcp_current_user_context.set(None)

    @pytest.mark.asyncio
    async def test_list_integrations(self):
        """Verify that list_integrations returns all available integrations."""
        # Pass configured_only=False to get all integrations (not just configured ones)
        result = await integration_tools.list_integrations(configured_only=False)

        assert "integrations" in result
        assert "count" in result
        assert isinstance(result["integrations"], list)
        assert result["count"] == len(result["integrations"])

        # Should have at least virustotal integration
        integration_ids = [i["integration_id"] for i in result["integrations"]]
        assert "virustotal" in integration_ids

        # Each integration should have required fields
        for integration in result["integrations"]:
            assert "integration_id" in integration
            assert "name" in integration
            assert "description" in integration
            assert "archetypes" in integration
            assert isinstance(integration["archetypes"], list)
            assert "action_count" in integration

    @pytest.mark.asyncio
    async def test_get_integration_tools_virustotal(self):
        """Verify that get_integration_tools returns VirusTotal tools."""
        result = await integration_tools.get_integration_tools("virustotal")

        assert "integration_id" in result
        assert result["integration_id"] == "virustotal"
        assert "name" in result
        assert result["name"] == "VirusTotal"
        assert "tools" in result
        assert isinstance(result["tools"], list)

        # VirusTotal should have tool actions
        assert len(result["tools"]) > 0

        # Check ip_reputation tool exists
        tool_ids = [t["action_id"] for t in result["tools"]]
        assert "ip_reputation" in tool_ids

        # Verify tool structure
        ip_tool = next(t for t in result["tools"] if t["action_id"] == "ip_reputation")
        assert "name" in ip_tool
        assert "description" in ip_tool
        assert "parameters" in ip_tool
        assert "cy_usage" in ip_tool

        # Verify parameters have required fields
        if ip_tool["parameters"]:
            for _param_name, param_info in ip_tool["parameters"].items():
                assert "type" in param_info
                assert "description" in param_info
                assert "required" in param_info

        # Verify Cy usage example uses correct app:: namespace syntax
        assert "app::virustotal::ip_reputation" in ip_tool["cy_usage"]
        assert ip_tool["cy_usage"].startswith("result = app::")

    @pytest.mark.asyncio
    async def test_get_integration_tools_not_found(self):
        """Verify that requesting non-existent integration returns error."""
        result = await integration_tools.get_integration_tools(
            "nonexistent_integration"
        )

        assert "error" in result
        assert "nonexistent_integration" in result["error"]
        assert "available_types" in result
        assert isinstance(result["available_types"], list)

    @pytest.mark.asyncio
    async def test_search_integration_tools_by_query(self):
        """Verify that search finds tools by query string."""
        result = await integration_tools.search_integration_tools(query="reputation")

        assert "tools" in result
        assert "count" in result
        assert "filters_applied" in result

        # Should find VirusTotal reputation tools
        assert result["count"] > 0

        # All results should match query
        for tool in result["tools"]:
            text = f"{tool['name']} {tool['description']}".lower()
            assert "reputation" in text

    @pytest.mark.asyncio
    async def test_search_integration_tools_by_archetype(self):
        """Verify that search filters by archetype."""
        result = await integration_tools.search_integration_tools(
            archetype="ThreatIntel"
        )

        assert "tools" in result
        assert "count" in result

        # Should find tools from ThreatIntel integrations (like VirusTotal)
        # At least verify the structure is correct
        for tool in result["tools"]:
            assert "integration_type" in tool
            assert "integration_name" in tool
            assert "categories" in tool

    @pytest.mark.asyncio
    async def test_search_integration_tools_by_category(self):
        """Verify that search filters by category."""
        result = await integration_tools.search_integration_tools(
            category="threat_intel"
        )

        assert "tools" in result
        assert "count" in result

        # All results should have the category
        for tool in result["tools"]:
            assert "threat_intel" in tool.get("categories", [])

    @pytest.mark.asyncio
    async def test_search_integration_tools_no_matches(self):
        """Verify that search with no matches returns empty list."""
        result = await integration_tools.search_integration_tools(
            query="nonexistent_search_term_xyz"
        )

        assert "tools" in result
        assert result["count"] == 0
        assert len(result["tools"]) == 0

    @pytest.mark.asyncio
    async def test_search_integration_tools_multiple_filters(self):
        """Verify that search applies multiple filters correctly."""
        result = await integration_tools.search_integration_tools(
            query="reputation", archetype="ThreatIntel", category="threat_intel"
        )

        assert "tools" in result
        assert "filters_applied" in result

        # Verify filters were recorded
        assert result["filters_applied"]["query"] == "reputation"
        assert result["filters_applied"]["archetype"] == "ThreatIntel"
        assert result["filters_applied"]["category"] == "threat_intel"

    @pytest.mark.asyncio
    async def test_cy_usage_example_format(self):
        """Verify that Cy usage examples are properly formatted."""
        result = await integration_tools.get_integration_tools("virustotal")

        for tool in result["tools"]:
            cy_usage = tool["cy_usage"]

            # Should be valid Cy syntax using app:: namespace
            assert cy_usage.startswith("result = app::")
            assert f"app::virustotal::{tool['action_id']}" in cy_usage

            # Should have proper function call syntax with parentheses
            assert "(" in cy_usage
            assert ")" in cy_usage

    @pytest.mark.asyncio
    async def test_integration_tools_singleton(self):
        """Verify that integration tools use singleton pattern."""
        # Pass configured_only=False to get all integrations
        result1 = await integration_tools.list_integrations(configured_only=False)
        result2 = await integration_tools.list_integrations(configured_only=False)

        # Should return consistent results
        assert result1["count"] == result2["count"]
        assert len(result1["integrations"]) == len(result2["integrations"])
