"""Unit tests for MCP server setup and tool registration.

Tests the unified analysi server (replaces cy-script-assistant + workflow-builder).
See test_analysi_server.py for comprehensive tool name and naming convention tests.
"""

import pytest
from mcp.server.fastmcp import FastMCP

from analysi.mcp.analysi_server import create_analysi_mcp_server


class TestMCPServer:
    """Test MCP server creation and tool registration."""

    @pytest.mark.asyncio
    async def test_create_mcp_server(self):
        """Verify unified analysi MCP server is created with all tools registered."""
        mcp_server = create_analysi_mcp_server()

        assert mcp_server is not None
        assert isinstance(mcp_server, FastMCP)
        assert mcp_server.name == "analysi"

        # FastMCP has a tool manager that handles tools
        assert hasattr(mcp_server, "_tool_manager")

        # Server should have the decorator method for tools
        assert hasattr(mcp_server, "tool")

    @pytest.mark.asyncio
    async def test_all_tools_registered_in_create_mcp_server(self):
        """Verify create_analysi_mcp_server registers all 25 tools."""
        mcp_server = create_analysi_mcp_server()

        # Count total tools registered
        total_tools = len(mcp_server._tool_manager._tools)

        # Unified server has 25 tools total (validate_alert now calls OCSF)
        assert total_tools == 25

    @pytest.mark.asyncio
    async def test_task_tools_available(self):
        """Verify task tools are available in the unified server."""
        mcp_server = create_analysi_mcp_server()
        tool_names = list(mcp_server._tool_manager._tools.keys())

        assert "list_tasks" in tool_names
        assert "get_task" in tool_names
        assert "create_task" in tool_names
        assert "update_task" in tool_names

    @pytest.mark.asyncio
    async def test_script_tools_available(self):
        """Verify script/Cy tools are available in the unified server."""
        mcp_server = create_analysi_mcp_server()
        tool_names = list(mcp_server._tool_manager._tools.keys())

        assert "compile_script" in tool_names
        assert "run_script" in tool_names
        assert "list_tools" in tool_names
        assert "get_tool" in tool_names

    @pytest.mark.asyncio
    async def test_integration_tools_available(self):
        """Verify integration discovery tools are available in server."""
        mcp_server = create_analysi_mcp_server()
        tool_names = list(mcp_server._tool_manager._tools.keys())

        assert "list_integrations" in tool_names
        assert "list_integration_tools" in tool_names
        assert "run_integration_tool" in tool_names

    @pytest.mark.asyncio
    async def test_workflow_tools_available(self):
        """Verify workflow tools are available in the unified server."""
        mcp_server = create_analysi_mcp_server()
        tool_names = list(mcp_server._tool_manager._tools.keys())

        assert "compose_workflow" in tool_names
        assert "get_workflow" in tool_names
        assert "list_workflows" in tool_names
        assert "run_workflow" in tool_names

    def test_mcp_server_dns_rebinding_protection_disabled(self):
        """Verify DNS rebinding protection is disabled for embedded server.

        MCP 1.26.0 introduced DNS rebinding protection that auto-enables for
        localhost host, rejecting requests with non-localhost Host headers
        (e.g. Docker's 'api:8000') with HTTP 421.
        Since our MCP servers are embedded in FastAPI (not standalone), we must
        disable this protection to allow Docker container-to-container communication.
        """
        mcp_server = create_analysi_mcp_server()
        security = mcp_server.settings.transport_security
        # Must be explicitly disabled (not None which defaults to True for localhost)
        assert security is not None, (
            "transport_security must be explicitly set to disable DNS rebinding protection"
        )
        assert not security.enable_dns_rebinding_protection, (
            "DNS rebinding protection must be disabled for embedded MCP servers. "
            "MCP 1.26.0 auto-enables it for localhost, blocking Docker host headers."
        )
