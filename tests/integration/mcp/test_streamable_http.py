"""Integration tests for MCP integration discovery tools.

Note: HTTP endpoint tests are not included here because they require
the MCP session manager to be running, which happens in the app lifespan
and not in pytest fixtures.
"""

import pytest


@pytest.mark.asyncio
@pytest.mark.integration
class TestIntegrationDiscoveryTools:
    """Test integration discovery MCP tools with real integration registry."""

    @pytest.mark.asyncio
    async def test_list_integrations_tool(self):
        """Verify list_integrations returns actual integrations."""
        from analysi.mcp import integration_tools

        # Pass configured_only=False to get all integrations (not just configured ones)
        result = await integration_tools.list_integrations(configured_only=False)

        # Should return structure
        assert "integrations" in result
        assert "count" in result
        assert isinstance(result["integrations"], list)

        # Should have at least VirusTotal integration
        integration_ids = [i["integration_id"] for i in result["integrations"]]
        assert "virustotal" in integration_ids, (
            "VirusTotal integration should be available"
        )

        # Verify structure of each integration
        for integration in result["integrations"]:
            assert "integration_id" in integration
            assert "name" in integration
            assert "description" in integration
            assert "archetypes" in integration
            assert isinstance(integration["archetypes"], list)

    @pytest.mark.asyncio
    async def test_get_integration_tools_virustotal(self):
        """Verify get_integration_tools returns VirusTotal tools with real data."""
        from analysi.mcp import integration_tools

        result = await integration_tools.get_integration_tools("virustotal")

        # Should return VirusTotal details
        assert result["integration_id"] == "virustotal"
        assert result["name"] == "VirusTotal"
        assert "ThreatIntel" in result["archetypes"]

        # Should have tools
        assert len(result["tools"]) > 0

        # Check ip_reputation tool
        tool_ids = [t["action_id"] for t in result["tools"]]
        assert "ip_reputation" in tool_ids

        ip_tool = next(t for t in result["tools"] if t["action_id"] == "ip_reputation")
        assert ip_tool["name"] == "IP Reputation"
        assert "parameters" in ip_tool
        assert "ip" in ip_tool["parameters"]
        assert ip_tool["parameters"]["ip"]["required"] is True
        assert "cy_usage" in ip_tool
        assert "app::virustotal::ip_reputation" in ip_tool["cy_usage"]

    @pytest.mark.asyncio
    async def test_get_integration_tools_nonexistent(self):
        """Verify get_integration_tools handles non-existent integration."""
        from analysi.mcp import integration_tools

        result = await integration_tools.get_integration_tools(
            "nonexistent_integration_xyz"
        )

        # Should return error
        assert "error" in result
        assert "nonexistent_integration_xyz" in result["error"]
        assert "available_types" in result

    @pytest.mark.asyncio
    async def test_search_integration_tools_by_category(self):
        """Verify search_integration_tools finds tools by category."""
        from analysi.mcp import integration_tools

        result = await integration_tools.search_integration_tools(
            category="threat_intel"
        )

        # Should find threat intel tools
        assert result["count"] > 0
        assert len(result["tools"]) > 0

        # All tools should have threat_intel category
        for tool in result["tools"]:
            assert "threat_intel" in tool["categories"]

        # Should include VirusTotal tools
        integration_types = [t["integration_type"] for t in result["tools"]]
        assert "virustotal" in integration_types

    @pytest.mark.asyncio
    async def test_search_integration_tools_by_archetype(self):
        """Verify search_integration_tools filters by archetype."""
        from analysi.mcp import integration_tools

        result = await integration_tools.search_integration_tools(
            archetype="ThreatIntel"
        )

        # Should find ThreatIntel tools
        assert result["count"] > 0

        # Filters should be recorded
        assert result["filters_applied"]["archetype"] == "ThreatIntel"

    @pytest.mark.asyncio
    async def test_search_integration_tools_by_query(self):
        """Verify search_integration_tools finds tools by text query."""
        from analysi.mcp import integration_tools

        result = await integration_tools.search_integration_tools(query="reputation")

        # Should find reputation-related tools
        assert result["count"] > 0

        # All results should match query
        for tool in result["tools"]:
            text = f"{tool['name']} {tool['description']}".lower()
            assert "reputation" in text

    @pytest.mark.asyncio
    async def test_integration_tools_cy_usage_format(self):
        """Verify Cy usage examples are properly formatted for all integrations."""
        from analysi.mcp import integration_tools

        # Get all integrations (pass configured_only=False to get all)
        integrations_result = await integration_tools.list_integrations(
            configured_only=False
        )

        for integration_summary in integrations_result["integrations"]:
            integration_id = integration_summary["integration_id"]

            # Get actions for each integration
            actions_result = await integration_tools.get_integration_tools(
                integration_id
            )

            # Skip if error or no tools
            if "error" in actions_result or not actions_result.get("tools"):
                continue

            # Check each tool's cy_usage
            for tool in actions_result["tools"]:
                cy_usage = tool["cy_usage"]

                # Should be valid Cy syntax using app:: namespace
                assert cy_usage.startswith("result = app::")
                assert f"app::{integration_id}::{tool['action_id']}" in cy_usage
                assert "(" in cy_usage
                assert ")" in cy_usage
