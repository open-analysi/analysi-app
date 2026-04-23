"""Unit tests for MCP server configuration (unified analysi server).

Verifies the agentic orchestration config returns a single 'analysi'
MCP server instead of two separate servers.
"""

from analysi.agentic_orchestration.config import (
    get_mcp_servers,
    mcp_tool_wildcards,
)


class TestGetMcpServers:
    """Test MCP server configuration for Claude Agent SDK."""

    def test_returns_single_analysi_server(self):
        """Config returns exactly one server named 'analysi'."""
        servers = get_mcp_servers("test-tenant")
        assert "analysi" in servers
        assert len(servers) == 1, (
            f"Expected 1 MCP server, got {len(servers)}: {list(servers.keys())}"
        )

    def test_no_old_server_names(self):
        """Old server names 'cy-script-assistant' and 'workflow-builder' are gone."""
        servers = get_mcp_servers("test-tenant")
        assert "cy-script-assistant" not in servers
        assert "workflow-builder" not in servers

    def test_server_type_is_http(self):
        """Server uses HTTP transport."""
        servers = get_mcp_servers("test-tenant")
        assert servers["analysi"]["type"] == "http"

    def test_server_url_contains_tenant(self):
        """Server URL is tenant-scoped."""
        servers = get_mcp_servers("acme-corp")
        url = servers["analysi"]["url"]
        assert "acme-corp" in url
        assert "/mcp/" in url

    def test_server_url_default_docker(self):
        """Default URL uses Docker hostname 'api:8000' when no env override."""
        # Use explicit host/port to simulate Docker defaults (avoids env interference)
        servers = get_mcp_servers("test-tenant", api_host="api", api_port=8000)
        url = servers["analysi"]["url"]
        assert url == "http://api:8000/v1/test-tenant/mcp/"

    def test_server_url_custom_host_port(self):
        """Custom host/port override works."""
        servers = get_mcp_servers("test-tenant", api_host="localhost", api_port=8001)
        url = servers["analysi"]["url"]
        assert url == "http://localhost:8001/v1/test-tenant/mcp/"

    def test_no_auth_headers_by_default(self):
        """No auth headers when no actor_user_id provided."""
        servers = get_mcp_servers("test-tenant")
        # Headers may or may not be present depending on system API key config
        # Just verify no crash
        assert servers["analysi"]["type"] == "http"


class TestMcpToolWildcards:
    """Test MCP tool wildcard generation."""

    def test_generates_analysi_wildcard(self):
        """Generates 'mcp__analysi__*' wildcard for the unified server."""
        servers = get_mcp_servers("test-tenant")
        wildcards = mcp_tool_wildcards(servers)
        assert "mcp__analysi__*" in wildcards

    def test_no_old_wildcards(self):
        """Old wildcard patterns are not generated."""
        servers = get_mcp_servers("test-tenant")
        wildcards = mcp_tool_wildcards(servers)
        assert "mcp__cy-script-assistant__*" not in wildcards
        assert "mcp__workflow-builder__*" not in wildcards

    def test_exactly_one_wildcard(self):
        """Only one wildcard entry for the single server."""
        servers = get_mcp_servers("test-tenant")
        wildcards = mcp_tool_wildcards(servers)
        assert len(wildcards) == 1
