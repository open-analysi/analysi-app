"""MCP audit logging utilities.

Provides helpers for logging MCP tool calls with argument capture.
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.auth import SYSTEM_USER_ID
from analysi.repositories.activity_audit_repository import ActivityAuditRepository
from analysi.schemas.audit_context import AuditContext

# Maximum length for string arguments before truncation
MAX_ARG_LENGTH = 1000
TRUNCATION_SUFFIX = "... [truncated]"


def _get_mcp_audit_context(actor_id: UUID = SYSTEM_USER_ID) -> AuditContext:
    """Create audit context for MCP tool calls."""
    return AuditContext(
        actor_id=str(actor_id),
        actor_type="system",
        source="mcp",
        actor_user_id=actor_id,
    )


def truncate_value(value: Any, max_length: int = MAX_ARG_LENGTH) -> Any:
    """Truncate string values that exceed max_length.

    Args:
        value: Value to potentially truncate
        max_length: Maximum length for string values

    Returns:
        Original value if not a string or under limit, truncated string otherwise
    """
    if isinstance(value, str) and len(value) > max_length:
        return value[: max_length - len(TRUNCATION_SUFFIX)] + TRUNCATION_SUFFIX
    return value


def prepare_mcp_audit_details(
    tool_name: str,
    arguments: dict[str, Any],
    max_arg_length: int = MAX_ARG_LENGTH,
) -> dict[str, Any]:
    """Prepare audit details from MCP tool arguments.

    Truncates string arguments that exceed max_arg_length.

    Args:
        tool_name: Name of the MCP tool being called
        arguments: Tool arguments dict
        max_arg_length: Maximum length for string arguments

    Returns:
        Details dict suitable for audit logging
    """
    truncated_args = {}
    for key, value in arguments.items():
        if value is None:
            continue  # Skip None values
        truncated_args[key] = truncate_value(value, max_arg_length)

    return {
        "mcp_tool": tool_name,
        "arguments": truncated_args,
    }


async def log_mcp_audit(
    session: AsyncSession,
    tenant_id: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    tool_name: str,
    arguments: dict[str, Any],
    actor_id: UUID = SYSTEM_USER_ID,
    max_arg_length: int = MAX_ARG_LENGTH,
) -> None:
    """Log an MCP tool call to the audit trail.

    Args:
        session: Database session
        tenant_id: Tenant identifier
        action: Action name (e.g., "task.create", "workflow.execute")
        resource_type: Type of resource (e.g., "task", "workflow")
        resource_id: ID of the resource (can be None for failed operations)
        tool_name: Name of the MCP tool
        arguments: Tool arguments (will be truncated if too long)
        actor_id: Actor performing the action
        max_arg_length: Maximum length for string arguments
    """
    audit_context = _get_mcp_audit_context(actor_id)
    details = prepare_mcp_audit_details(tool_name, arguments, max_arg_length)

    repo = ActivityAuditRepository(session)
    await repo.create(
        tenant_id=tenant_id,
        actor_id=audit_context.actor_user_id or SYSTEM_USER_ID,
        actor_type=audit_context.actor_type,
        source=audit_context.source,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )
