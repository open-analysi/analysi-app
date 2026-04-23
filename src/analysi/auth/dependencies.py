"""FastAPI dependency functions for authentication and RBAC.

Usage:

    # Protect a route and enforce tenant isolation + permission:
    @router.post("/v1/{tenant_id}/tasks")
    async def create_task(
        current_user: CurrentUser = Depends(require_permission("tasks", "create")),
    ):
        ...

    # Protect admin routes (platform_admin only):
    router = APIRouter(dependencies=[Depends(require_platform_admin)])
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.auth.api_key import validate_api_key
from analysi.auth.jwks import is_jwks_configured
from analysi.auth.jwt import validate_jwt_token
from analysi.auth.messages import INSUFFICIENT_PERMISSIONS
from analysi.auth.models import CurrentUser
from analysi.auth.permissions import has_permission
from analysi.config.logging import get_logger
from analysi.config.settings import settings
from analysi.db.session import get_db

logger = get_logger(__name__)

# auto_error=False so a missing token doesn't raise immediately;
# the function returns None instead and the caller decides to enforce or not.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

_API_KEY_HEADER = "X-API-Key"


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    request: Request = None,  # type: ignore[assignment]
    db: AsyncSession = Depends(get_db),
) -> CurrentUser | None:
    """Try Bearer JWT first, then X-API-Key header.

    Returns None when no credential is present or validation fails.
    Never raises — callers use ``require_current_user`` to enforce auth.
    """
    # 1. Try Bearer JWT
    if token:
        if not is_jwks_configured():
            # JWKS not set up (dev mode without Keycloak) → no JWT auth
            return None
        try:
            current_user = validate_jwt_token(
                token=token,
                audience=settings.ANALYSI_AUTH_AUDIENCE,
                issuer=settings.ANALYSI_AUTH_ISSUER,
            )
            # JIT provisioning: auto-create User + Membership on first login
            try:
                from analysi.services.member_service import MemberService

                svc = MemberService(db)
                db_user = await svc.provision_user_jit(current_user)
                if db_user is not None:
                    current_user.db_user_id = db_user.id
                await db.flush()
            except Exception as exc:
                # Never fail auth due to JIT errors
                logger.warning("jit_provision_failed", error=str(exc))

            # Override JWT roles with local membership roles.
            # Runs independently of JIT so that even when JIT fails,
            # stale JWT roles are replaced by local membership state.
            # Fail closed: if the user exists locally but has no
            # membership, roles are cleared to [].
            try:
                await _resolve_local_roles(current_user, db)
            except Exception as exc:
                logger.warning("local_role_resolution_failed", error=str(exc))
                current_user.roles = []  # Fail closed

            return current_user
        except HTTPException:
            return None

    # 2. Try X-API-Key header
    if request is not None:
        api_key = request.headers.get(_API_KEY_HEADER)
        if api_key:
            return await validate_api_key(api_key, db)

    return None


async def require_current_user(
    current_user: CurrentUser | None = Depends(get_current_user),
) -> CurrentUser:
    """Enforce authentication — raises HTTP 401 if no valid credential.

    Use this as a dependency on any route that must be protected.
    """
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return current_user


async def check_tenant_access(
    tenant: str,  # FastAPI injects from URL path parameter {tenant}
    current_user: CurrentUser = Depends(require_current_user),
) -> str:
    """Enforce tenant isolation.

    platform_admin bypasses tenant check entirely.
    All other users must have a non-None tenant_id that matches the URL.

    Returns the validated tenant_id for use by downstream dependencies.
    """
    if current_user.is_platform_admin:
        return tenant

    if current_user.tenant_id is None:
        raise HTTPException(
            status_code=403,
            detail="No tenant assigned to this user",
        )

    if current_user.tenant_id != tenant:
        raise HTTPException(
            status_code=403,
            detail="Access denied: tenant mismatch",
        )

    return tenant


def require_permission(resource: str, action: str) -> Callable:
    """Return a FastAPI dependency that enforces a specific permission.

    Includes tenant isolation check (check_tenant_access) so callers
    only need this single dependency on protected routes.

    Args:
        resource: Resource name, e.g. "tasks", "workflows", "members".
        action:   Action name, e.g. "read", "create", "delete", "execute".

    Returns:
        An async dependency function injectable via Depends().

    Example:
        router = APIRouter(
            prefix="/{tenant_id}/tasks",
            dependencies=[Depends(require_permission("tasks", "read"))],
        )
    """

    async def _check(
        tenant: str,  # FastAPI injects from URL path parameter {tenant}
        current_user: CurrentUser = Depends(require_current_user),
    ) -> CurrentUser:
        # platform_admin bypasses all checks
        if current_user.is_platform_admin:
            return current_user

        # Tenant isolation
        if current_user.tenant_id is None:
            raise HTTPException(
                status_code=403,
                detail="No tenant assigned to this user",
            )
        if current_user.tenant_id != tenant:
            raise HTTPException(
                status_code=403,
                detail="Access denied: tenant mismatch",
            )

        # Role-based permission
        if not has_permission(current_user.roles, resource, action):
            raise HTTPException(
                status_code=403,
                detail=INSUFFICIENT_PERMISSIONS,
            )

        return current_user

    # Give the inner function a unique name so FastAPI dependency caching
    # works correctly when multiple require_permission calls are used.
    _check.__name__ = f"require_{resource}_{action}"
    return _check


async def require_platform_admin(
    current_user: CurrentUser = Depends(require_current_user),
) -> CurrentUser:
    """Enforce platform_admin role — used exclusively on /admin/v1/ routes.

    Raises HTTP 403 if the user is not a platform_admin.
    """
    if not current_user.is_platform_admin:
        raise HTTPException(
            status_code=403,
            detail="Platform admin access required",
        )
    return current_user


async def _resolve_local_roles(user: CurrentUser, db: AsyncSession) -> None:
    """Override JWT-sourced roles with the local membership role.

    The local memberships table is the source of truth for authorization.
    JWT claims may be stale after an admin changes a user's role via the
    members API — this function ensures the local role takes precedence.

    Fail-closed: when a user exists locally but has no membership in the
    tenant, roles are cleared to [] (denying access) rather than keeping
    potentially stale JWT claims.

    Skips platform_admin users (no tenant-scoped membership).
    """
    if user.is_platform_admin:
        return
    if not user.tenant_id:
        return

    from sqlalchemy import select

    from analysi.models.auth import Membership, User

    # Resolve db_user_id from keycloak_id if not already set (e.g., JIT failed)
    if not user.db_user_id:
        if not user.user_id:
            # Empty keycloak_id — can't resolve. Fail closed.
            user.roles = []
            return
        result = await db.execute(
            select(User.id).where(User.keycloak_id == user.user_id)
        )
        db_user_id = result.scalar_one_or_none()
        if db_user_id is None:
            # User not provisioned locally — fail closed.
            # JIT provisioning runs before this function; if it succeeded,
            # the user row exists. If it failed, stale JWT roles must not
            # survive — local membership is the source of truth.
            user.roles = []
            return
        user.db_user_id = db_user_id

    result = await db.execute(
        select(Membership.role).where(
            Membership.user_id == user.db_user_id,
            Membership.tenant_id == user.tenant_id,
        )
    )
    local_role = result.scalar_one_or_none()
    if local_role is not None:
        user.roles = [str(local_role)]
    else:
        # User exists locally but has no membership in this tenant.
        # Fail closed — clear roles to deny access with stale JWT claims.
        user.roles = []
