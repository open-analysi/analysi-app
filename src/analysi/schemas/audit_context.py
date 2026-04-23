"""Audit context for passing actor information through the service layer."""

from dataclasses import dataclass
from uuid import UUID


@dataclass
class AuditContext:
    """Context for audit logging, passed from routers/MCP tools to services.

    Attributes:
        actor_id: User identifier (email, username, "system", or API key name)
        actor_type: Type of actor ("user", "system", "api_key", "workflow")
        source: Subsystem generating the log ("rest_api", "mcp", "ui", "internal")
        actor_user_id: UUID FK to users table (for created_by/updated_by columns)
        ip_address: Client IP address (optional)
        user_agent: Client user agent string (optional)
        request_id: Request correlation ID for tracing (optional)
    """

    actor_id: str
    actor_type: str  # "user", "system", "api_key", "workflow"
    source: str = "unknown"  # "rest_api", "mcp", "ui", "internal"
    actor_user_id: UUID | None = None  # FK-ready UUID from users table
    ip_address: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
