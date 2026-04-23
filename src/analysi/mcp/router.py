"""FastAPI router for MCP Streamable HTTP endpoints.

Unified analysi MCP server replacing cy-script-assistant + workflow-builder.
Single mount at /v1/{tenant}/mcp/.
"""

from starlette.applications import Starlette
from starlette.routing import Mount

from analysi.mcp.analysi_server import create_analysi_mcp_server
from analysi.mcp.middleware import wrap_mcp_app_with_tenant

# Create the unified MCP server instance
_mcp_server = create_analysi_mcp_server()

# Get the streamable HTTP ASGI app from FastMCP and wrap with tenant middleware
# This provides the /mcp endpoint for streamable HTTP transport
_base_mcp_app = wrap_mcp_app_with_tenant(_mcp_server.streamable_http_app())


def get_mcp_router() -> Starlette:
    """
    Get MCP router with dynamic tenant path support.

    Handles paths: /v1/{tenant}/mcp/*

    Returns:
        Starlette app with tenant-aware routing
    """
    return Starlette(
        routes=[
            Mount("/{tenant}/mcp", app=_base_mcp_app),
        ]
    )
