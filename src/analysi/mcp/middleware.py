"""Middleware for MCP apps to extract tenant from path and validate auth."""

from __future__ import annotations

import dataclasses
import json
import re
import time
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from analysi.auth.models import CurrentUser

from sqlalchemy import select
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from analysi.auth.api_key import validate_api_key
from analysi.auth.jwks import is_jwks_configured
from analysi.auth.jwt import validate_jwt_token
from analysi.config.logging import get_logger
from analysi.mcp.context import get_mcp_current_user, set_mcp_current_user, set_tenant
from analysi.models.auth import Membership

_API_KEY_HEADER = "X-API-Key"
_ACTOR_HEADER = "X-Actor-User-Id"

logger = get_logger(__name__)


class MCPTenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware for MCP sub-apps that:
    1. Extracts tenant from URL path and stores in ContextVar.
    2. Validates Bearer JWT tokens (when JWKS is configured) and API keys,
       storing the resolved CurrentUser in a ContextVar.
    3. Rejects unauthenticated requests with 401.

    Auth behaviour:
    - Bearer token present + JWKS configured → validate; 401 on invalid.
    - Bearer token present + JWKS not configured → 401 (cannot validate).
    - X-API-Key present → validate via DB lookup; 401 on invalid.
    - No auth header → 401.

    Actor impersonation (system API keys only):
    - X-Actor-User-Id header is trusted ONLY from system-authenticated requests.
    - The actor UUID must have a membership in the tenant from the URL path.
    - If validation fails, the header is ignored (system default kept).

    Tenant extraction:
    - Extracts tenant from paths like /v1/{tenant}/mcp/* and
      /v1/{tenant}/workflows-builder/mcp/*.
    """

    TENANT_PATTERN = re.compile(r"^/v1/([^/]+)/")

    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. Extract tenant from path
        tenant: str | None = None
        match = self.TENANT_PATTERN.match(request.url.path)
        if match:
            tenant = match.group(1)
            set_tenant(tenant)

        # 2. Validate auth and set CurrentUser ContextVar
        authenticated = False
        auth_header = request.headers.get("Authorization", "")

        user: CurrentUser | None = None
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if is_jwks_configured():
                from analysi.config.settings import settings

                try:
                    user = validate_jwt_token(
                        token=token,
                        audience=settings.ANALYSI_AUTH_AUDIENCE,
                        issuer=settings.ANALYSI_AUTH_ISSUER,
                    )
                    # Resolve local roles — JWT claims may be stale after
                    # admin role changes. Local membership is source of truth.
                    # Fail closed: on resolver error, clear roles rather than
                    # keeping potentially stale JWT claims.
                    if tenant and not user.is_platform_admin:
                        try:
                            await _resolve_jwt_local_roles(user, tenant)
                        except Exception:
                            logger.warning("mcp_local_role_resolution_failed")
                            user.roles = []  # Fail closed
                    set_mcp_current_user(user)
                    authenticated = True
                except Exception:
                    return Response("Unauthorized", status_code=401)
            # else: JWKS not configured — cannot validate JWT, reject below
        else:
            api_key = request.headers.get(_API_KEY_HEADER)
            if api_key:
                from analysi.db.session import AsyncSessionLocal

                async with AsyncSessionLocal() as session:
                    user = await validate_api_key(api_key, session)
                    if user is not None:
                        # Trust X-Actor-User-Id only from system-authenticated
                        # requests (not regular user JWTs or user API keys).
                        # This propagates the originating user's identity when
                        # ARQ jobs call MCP tools via the Agent SDK.
                        if user.actor_type == "system" and tenant:
                            actor_header = request.headers.get(_ACTOR_HEADER)
                            if actor_header:
                                user = await _resolve_actor(
                                    session, actor_header, tenant, user
                                )
                        set_mcp_current_user(user)
                        authenticated = True
                    else:
                        return Response(
                            "Unauthorized: invalid API key", status_code=401
                        )

        # 3. Reject unauthenticated requests
        if not authenticated:
            return Response("Unauthorized", status_code=401)

        # 4. Enforce tenant isolation — credential must belong to URL tenant.
        #    Platform admins and system actors (workers) bypass this check.
        if tenant:
            authed_user = get_mcp_current_user()
            if (
                authed_user
                and not authed_user.is_platform_admin
                and authed_user.actor_type != "system"
                and authed_user.tenant_id != tenant
            ):
                return Response("Access denied: tenant mismatch", status_code=403)

        # 5. Log request and response
        return await _log_mcp_request(request, call_next)


async def _log_mcp_request(request: Request, call_next) -> Response:
    """Log MCP request/response with JSON-RPC method and tool name."""
    rpc_method = None
    tool_name = None
    try:
        body_bytes = await request.body()
        request._body = body_bytes  # Store back for downstream
        if body_bytes:
            rpc = json.loads(body_bytes)
            rpc_method = rpc.get("method")
            if rpc_method == "tools/call":
                tool_name = (rpc.get("params") or {}).get("name")
    except Exception:
        pass  # Best-effort — don't block request on parse failure

    log_extra: dict[str, str] = {}
    if rpc_method:
        log_extra["rpc_method"] = rpc_method
    if tool_name:
        log_extra["tool"] = tool_name

    mcp_logger = logger.bind(api="mcp", **log_extra)
    mcp_logger.info("request_start")
    start_time = time.time()

    try:
        response = await call_next(request)
        execution_time = time.time() - start_time

        log_level = (
            "error"
            if response.status_code >= 500
            else "warning"
            if response.status_code >= 400
            else "info"
        )
        getattr(mcp_logger, log_level)(
            "request_complete",
            status_code=response.status_code,
            execution_time=round(execution_time, 4),
        )
        return response
    except Exception as e:
        execution_time = time.time() - start_time
        mcp_logger.error(
            "request_error",
            execution_time=round(execution_time, 4),
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


async def _resolve_jwt_local_roles(user, tenant: str) -> None:
    """Override JWT roles with the local membership role for MCP requests.

    The local memberships table is the source of truth for authorization.
    JWT claims may be stale after an admin changes a user's role.
    Mutates user.db_user_id and user.roles in place.

    Fail-closed: when a user exists locally but has no membership in the
    tenant, roles are cleared to [] rather than keeping stale JWT claims.
    """
    from analysi.db.session import AsyncSessionLocal
    from analysi.models.auth import User

    if not user.user_id:
        # Empty keycloak_id — can't resolve identity. Fail closed.
        user.roles = []
        return

    async with AsyncSessionLocal() as session:
        # Look up local user by keycloak_id
        result = await session.execute(
            select(User.id).where(User.keycloak_id == user.user_id)
        )
        db_user_id = result.scalar_one_or_none()
        if db_user_id is None:
            # User not provisioned locally — fail closed.
            # MCP has no JIT provisioning path, so a missing local user
            # must not retain stale JWT roles.
            user.roles = []
            return

        user.db_user_id = db_user_id

        result = await session.execute(
            select(Membership.role).where(
                Membership.user_id == db_user_id,
                Membership.tenant_id == tenant,
            )
        )
        local_role = result.scalar_one_or_none()
        if local_role is not None:
            user.roles = [local_role]
        else:
            # User exists locally but no membership — fail closed.
            user.roles = []


async def _resolve_actor(session, actor_header: str, tenant: str, user):
    """Validate X-Actor-User-Id against tenant membership.

    Returns a new CurrentUser with overridden db_user_id AND roles resolved
    from the actor's membership. This ensures RBAC checks reflect the actor's
    actual permissions, not the system API key's roles.

    Fail-closed: if the actor has no membership in the tenant, roles are
    cleared to [] (denying all RBAC-gated operations). An invalid UUID
    header returns the original system user unchanged.
    """
    try:
        actor_uuid = UUID(actor_header)
    except ValueError:
        logger.warning("invalid_actor_user_id_uuid", actor_header=actor_header)
        return user

    # Verify actor has a membership in this tenant and get their role
    stmt = select(Membership.role).where(
        Membership.user_id == actor_uuid,
        Membership.tenant_id == tenant,
    )
    result = await session.execute(stmt)
    actor_role = result.scalar_one_or_none()
    if actor_role is None:
        logger.warning(
            "X-Actor-User-Id %s has no membership in tenant %s — denying",
            actor_uuid,
            tenant,
        )
        # Fail closed: actor was explicitly requested but has no membership.
        # Clear roles rather than keeping the system key's admin privileges.
        return dataclasses.replace(user, roles=[], actor_type="user", tenant_id=tenant)

    return dataclasses.replace(
        user,
        db_user_id=actor_uuid,
        roles=[actor_role],
        actor_type="user",  # Actor is a real user, not system
        tenant_id=tenant,  # Actor belongs to this tenant
    )


def wrap_mcp_app_with_tenant(app: Starlette) -> Starlette:
    """
    Wrap an MCP app with tenant extraction and auth middleware.

    Args:
        app: Starlette app to wrap

    Returns:
        Wrapped Starlette app with tenant + auth middleware
    """
    app.add_middleware(MCPTenantMiddleware)
    return app
