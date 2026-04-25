"""MCP request context management."""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING
from uuid import UUID

from analysi.auth.messages import INSUFFICIENT_PERMISSIONS, NO_AUTHENTICATED_USER
from analysi.models.auth import SYSTEM_USER_ID

if TYPE_CHECKING:
    from analysi.auth.models import CurrentUser

# Context variable to store tenant ID for MCP requests
mcp_tenant_context: ContextVar[str] = ContextVar("mcp_tenant", default="default")

# Context variable to store the authenticated user for MCP requests
mcp_current_user_context: ContextVar[CurrentUser | None] = ContextVar(
    "mcp_current_user", default=None
)


def get_tenant() -> str:
    """Get the current tenant ID from MCP request context."""
    return mcp_tenant_context.get()


def set_tenant(tenant: str) -> None:
    """Set the tenant ID in MCP request context."""
    mcp_tenant_context.set(tenant)


def get_mcp_current_user() -> CurrentUser | None:
    """Get the authenticated CurrentUser from MCP request context."""
    return mcp_current_user_context.get()


def set_mcp_current_user(user: CurrentUser | None) -> None:
    """Set the authenticated CurrentUser in MCP request context."""
    mcp_current_user_context.set(user)


def check_mcp_permission(resource: str, action: str) -> None:
    """Check that the current MCP user has permission for resource.action.

    Raises PermissionError if the user lacks the required permission.
    Platform admins bypass all checks.
    """
    from analysi.auth.permissions import has_permission

    user = mcp_current_user_context.get()
    if user is None:
        raise PermissionError(NO_AUTHENTICATED_USER)
    if user.is_platform_admin:
        return
    if not has_permission(user.roles, resource, action):
        raise PermissionError(INSUFFICIENT_PERMISSIONS)


def get_mcp_actor_user_id() -> UUID:
    """Derive actor_user_id from the authenticated MCP user.

    Returns db_user_id when available, otherwise SYSTEM_USER_ID for
    authenticated users without a db identity (e.g., system API keys).

    Raises RuntimeError if no authenticated user is present — the MCP
    middleware must enforce authentication before tools are invoked.
    """
    user = mcp_current_user_context.get()
    if user is None:
        raise RuntimeError(
            "No authenticated user in MCP context. "
            "MCP middleware must enforce authentication before tool invocation."
        )
    if user.db_user_id:
        return user.db_user_id
    return SYSTEM_USER_ID
