"""Integration tests for MCP resource endpoints."""

import pytest

from analysi.mcp.analysi_server import create_analysi_mcp_server


@pytest.mark.asyncio
@pytest.mark.integration
class TestMCPResources:
    """Test MCP resource endpoints."""

    @pytest.fixture
    def analysi_server(self):
        """Create unified analysi MCP server instance for testing."""
        return create_analysi_mcp_server()

    @pytest.mark.asyncio
    async def test_analysi_server_has_no_resources(self, analysi_server):
        """Verify unified analysi MCP server has no resources registered.

        Documentation is provided via skills (task-builder, workflow-builder,
        cy-language-programming) instead of MCP resources.
        """
        resources = await analysi_server.list_resources()
        assert len(resources) == 0, (
            "analysi server should not register resources - "
            "documentation is provided via skills instead"
        )
