"""Integration tests for MCP HTTP transport layer.

Unlike other MCP tests that call tool functions directly, these tests go through
the full HTTP stack. This catches transport-level bugs that function-level tests
cannot see:

- HTTP 307 Redirect: Missing trailing slash on MCP URLs; the Claude Agent SDK
  does not follow redirects, so all MCP tools silently fail.
- HTTP 421 Misdirected Request: MCP 1.26.0 introduced DNS rebinding protection
  that auto-enables for localhost, rejecting Docker host headers like
  'api:8000' with HTTP 421.

Both bugs were triggered by the mcp 1.21.1 → 1.26.0 upgrade.
"""

import json
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.routing import Router as StarletteRouter

from analysi.auth.models import CurrentUser

TENANT = "default"
MCP_URL = f"/v1/{TENANT}/mcp/"

# Host header that Docker container-to-container calls use.
# MCP 1.26.0 DNS rebinding protection (HTTP 421) blocked this.
DOCKER_HOST = "api:8000"

# Fake API key for auth — validate_api_key is patched to accept this
_TEST_API_KEY = "test-transport-key"

MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "X-API-Key": _TEST_API_KEY,
}

_TEST_USER = CurrentUser(
    user_id="test-transport-user",
    email="transport@test.local",
    tenant_id=None,
    roles=["platform_admin"],
    actor_type="user",
)

MCP_INIT_PAYLOAD = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test-client", "version": "1.0"},
    },
}

MCP_LIST_TOOLS_PAYLOAD = {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {},
}


def _build_test_mcp_app():
    """Build a minimal Starlette app with a fresh MCP server instance.

    We create a fresh server instance (not the production module-level singleton)
    so each test fixture gets its own StreamableHTTPSessionManager.
    StreamableHTTPSessionManager.run() can only be called once per instance,
    so reusing the singleton across multiple tests would fail.

    The initialize and tools/list protocol operations don't require database
    access, so no DB override is needed for these transport-layer tests.
    """
    from analysi.mcp.analysi_server import create_analysi_mcp_server
    from analysi.mcp.middleware import wrap_mcp_app_with_tenant

    server = create_analysi_mcp_server()
    asgi_app = wrap_mcp_app_with_tenant(server.streamable_http_app())

    inner = StarletteRouter(
        routes=[
            Mount(f"/{TENANT}/mcp", app=asgi_app),
        ]
    )
    outer = Starlette(routes=[Mount("/v1", app=inner)])

    return outer, server


@pytest_asyncio.fixture
async def mcp_client() -> AsyncGenerator[AsyncClient]:
    """HTTP client with fresh MCP server, simulating Docker host headers.

    Creates a new FastMCP server instance per test so each test gets a
    pristine StreamableHTTPSessionManager that can be started cleanly.
    Patches validate_api_key so the auth middleware accepts the test API key.

    Note on anyio/asyncio teardown: the session_manager uses anyio task groups
    internally. Under pytest-asyncio (asyncio backend), cleanup can raise
    "Attempted to exit cancel scope in a different task than it was entered in".
    This is harmless (requests already completed) and is caught here, mirroring
    the pattern used in sdk_wrapper.py.
    """
    test_app, server = _build_test_mcp_app()

    cm = server.session_manager.run()
    await cm.__aenter__()

    # Patch validate_api_key to accept the test key
    async def _mock_validate(key, session):
        if key == _TEST_API_KEY:
            return _TEST_USER
        return None

    transport = ASGITransport(app=test_app)
    with patch(
        "analysi.mcp.middleware.validate_api_key",
        new=_mock_validate,
    ):
        async with AsyncClient(
            transport=transport, base_url=f"http://{DOCKER_HOST}"
        ) as client:
            yield client

    # Teardown: catch anyio cancel scope errors from anyio/asyncio mismatch
    try:
        await cm.__aexit__(None, None, None)
    except RuntimeError as e:
        if "cancel scope" not in str(e).lower():
            raise


def _parse_mcp_sse_response(text: str) -> dict | None:
    """Parse MCP SSE response to extract the JSON-RPC result.

    MCP Streamable HTTP uses Server-Sent Events format:
        data: {"jsonrpc":"2.0","id":1,"result":{...}}
    """
    for line in text.splitlines():
        if line.startswith("data: "):
            try:
                return json.loads(line[6:])
            except json.JSONDecodeError:
                continue
    return None


@pytest.mark.asyncio
@pytest.mark.integration
class TestMCPHttpTransport:
    """Test MCP HTTP transport with real HTTP requests through the full stack."""

    # -------------------------------------------------------------------------
    # Connectivity: catching 421 and 307
    # -------------------------------------------------------------------------

    async def test_mcp_reachable_with_docker_host(self, mcp_client):
        """Analysi MCP endpoint must respond 200 with a Docker host header.

        Regression test for MCP 1.26.0 DNS rebinding protection that rejected
        requests with Host: api:8000 with HTTP 421.
        """
        response = await mcp_client.post(
            MCP_URL, headers=MCP_HEADERS, json=MCP_INIT_PAYLOAD
        )
        assert response.status_code == 200, (
            f"Got {response.status_code}. "
            "421 = DNS rebinding protection blocking Docker host. "
            "307 = missing trailing slash on MCP URL."
        )

    async def test_mcp_url_without_trailing_slash_redirects(self, mcp_client):
        """URL without trailing slash redirects — callers must use the trailing slash.

        Documents that get_mcp_servers() in config.py must include trailing slashes.
        The Claude Agent SDK does not follow 307 redirects, so without this the
        agent SDK cannot discover any MCP tools.
        """
        response = await mcp_client.post(
            MCP_URL.rstrip("/"),
            headers=MCP_HEADERS,
            json=MCP_INIT_PAYLOAD,
            follow_redirects=False,
        )
        assert response.status_code in (307, 308), (
            f"Expected 307/308 redirect, got {response.status_code}. "
            "URL without trailing slash should redirect to the canonical URL with slash."
        )

    # -------------------------------------------------------------------------
    # MCP protocol handshake
    # -------------------------------------------------------------------------

    async def test_mcp_initialize_returns_server_info(self, mcp_client):
        """MCP initialize must return the analysi server name."""
        response = await mcp_client.post(
            MCP_URL, headers=MCP_HEADERS, json=MCP_INIT_PAYLOAD
        )
        assert response.status_code == 200

        result = _parse_mcp_sse_response(response.text)
        assert result is not None, (
            f"Could not parse SSE response: {response.text[:200]}"
        )
        assert result["result"]["serverInfo"]["name"] == "analysi"

    async def test_mcp_tools_list_contains_expected_tools(self, mcp_client):
        """tools/list must return the registered analysi tools (25 total)."""
        response = await mcp_client.post(
            MCP_URL, headers=MCP_HEADERS, json=MCP_LIST_TOOLS_PAYLOAD
        )
        assert response.status_code == 200

        result = _parse_mcp_sse_response(response.text)
        assert result is not None
        tool_names = [t["name"] for t in result["result"]["tools"]]

        # Script tools (unified names)
        assert "compile_script" in tool_names
        assert "run_script" in tool_names
        assert "list_tools" in tool_names

        # Task tools
        assert "list_tasks" in tool_names
        assert "get_task" in tool_names
        assert "create_task" in tool_names

        # Workflow tools
        assert "compose_workflow" in tool_names
        assert "get_workflow" in tool_names
        assert "list_workflows" in tool_names
        assert "run_workflow" in tool_names

        # Total count: 25 tools (validate_alert replaces validate_nas_alert, OCSF)
        assert len(tool_names) == 25, (
            f"Expected 25 tools, got {len(tool_names)}: {sorted(tool_names)}"
        )
