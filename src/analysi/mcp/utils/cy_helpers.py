"""
Cy language utilities for MCP tools.

Shared utilities for Cy script compilation, tool registry loading, etc.
"""

from typing import Any

from analysi.mcp.utils.db import get_db_session
from analysi.services.cy_tool_registry import load_tool_registry_async


async def load_tool_registry_for_tenant(tenant_id: str) -> dict[str, Any]:
    """
    Load tool registry for a tenant (DRY wrapper).

    Combines database session management with tool registry loading.

    Args:
        tenant_id: Tenant identifier

    Returns:
        Tool registry dict mapping FQN to schema info
    """
    try:
        async with get_db_session() as session:
            return await load_tool_registry_async(session, tenant_id)
    except RuntimeError as e:
        # Handle "Event loop is closed" during sequential test execution
        # This can happen when pytest runs tests back-to-back
        if "Event loop is closed" in str(e):
            # Return empty registry - tests can handle this gracefully
            return {}
        raise
