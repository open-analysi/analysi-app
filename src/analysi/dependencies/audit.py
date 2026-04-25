"""Shared audit context dependency for REST API routers."""

from fastapi import Depends, Request

from analysi.auth.dependencies import require_current_user
from analysi.auth.models import CurrentUser
from analysi.models.auth import SYSTEM_USER_ID
from analysi.schemas.audit_context import AuditContext


def get_audit_context(
    request: Request,
    current_user: CurrentUser = Depends(require_current_user),
) -> AuditContext:
    """Build AuditContext from the authenticated user and request metadata."""
    ip_address: str | None
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    else:
        ip_address = request.client.host if request.client else None

    return AuditContext(
        actor_id=current_user.email or current_user.user_id,
        actor_type=current_user.actor_type,
        source="rest_api",
        actor_user_id=current_user.db_user_id or SYSTEM_USER_ID,
        ip_address=ip_address,
        user_agent=request.headers.get("user-agent"),
        request_id=request.headers.get("x-request-id"),
    )
