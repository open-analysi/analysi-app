"""API key management endpoints.

Project Mikonos — Auth & RBAC (Spec: version_7/AuthAndRBAC_v1.md)
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api import ApiListResponse, ApiResponse, api_list_response, api_response
from analysi.auth.dependencies import require_current_user, require_permission
from analysi.auth.models import CurrentUser
from analysi.db.session import get_db
from analysi.models.auth import SYSTEM_USER_ID
from analysi.repositories.activity_audit_repository import ActivityAuditRepository
from analysi.repositories.user_repository import UserRepository
from analysi.schemas.auth import (
    ApiKeyCreatedResponse,
    ApiKeyResponse,
    CreateApiKeyRequest,
)
from analysi.services.api_key_service import ApiKeyService

router = APIRouter(
    prefix="/{tenant}/api-keys",
    tags=["api-keys"],
    dependencies=[Depends(require_permission("api_keys", "read"))],
)


async def get_api_key_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApiKeyService:
    return ApiKeyService(session)


async def _log_api_key_audit(
    session: AsyncSession,
    tenant: str,
    current_user: CurrentUser,
    action: str,
    resource_id: str,
    request: Request,
) -> None:
    """Record an audit event for an API key lifecycle action."""
    repo = ActivityAuditRepository(session)
    await repo.create(
        tenant_id=tenant,
        actor_id=current_user.db_user_id or SYSTEM_USER_ID,
        actor_type=current_user.actor_type,
        source="rest_api",
        action=action,
        resource_type="api_key",
        resource_id=resource_id,
        details=None,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=None,
    )


@router.get("", response_model=ApiListResponse[ApiKeyResponse])
async def list_api_keys(
    request: Request,
    tenant: str,
    service: Annotated[ApiKeyService, Depends(get_api_key_service)],
) -> ApiListResponse[ApiKeyResponse]:
    """List all API keys for a tenant (secrets never included)."""
    keys = await service.list_api_keys(tenant)
    return api_list_response(keys, total=len(keys), request=request)


@router.post(
    "",
    response_model=ApiResponse[ApiKeyCreatedResponse],
    status_code=201,
    dependencies=[Depends(require_permission("api_keys", "create"))],
)
async def create_api_key(
    tenant: str,
    body: CreateApiKeyRequest,
    service: Annotated[ApiKeyService, Depends(get_api_key_service)],
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> ApiResponse[ApiKeyCreatedResponse]:
    """Create an API key. The plaintext secret is returned once and not stored."""
    # Resolve the creating user's DB identity.
    # Non-system callers MUST bind to a real db_user_id — user_id=None would
    # create a system key with platform_admin privileges (P0 escalation risk).
    user_id: UUID | None = None
    if current_user.actor_type == "api_key":
        # API-key callers already have db_user_id resolved by validate_api_key()
        if current_user.db_user_id is None:
            raise HTTPException(
                status_code=403,
                detail="Cannot create API key: caller has no associated user identity.",
            )
        user_id = current_user.db_user_id
    elif current_user.actor_type == "user":
        # JWT callers: look up db user by keycloak ID
        if current_user.db_user_id is not None:
            user_id = current_user.db_user_id
        else:
            user_repo = UserRepository(session)
            db_user = await user_repo.get_by_keycloak_id(current_user.user_id)
            if db_user is not None:
                user_id = db_user.id
        if user_id is None:
            raise HTTPException(
                status_code=403,
                detail="Cannot create API key: user identity not found.",
            )

    result = await service.create_api_key(
        tenant_id=tenant,
        name=body.name,
        user_id=user_id,
        scopes=body.scopes,
        expires_at=body.expires_at,
    )

    await _log_api_key_audit(
        session=session,
        tenant=tenant,
        current_user=current_user,
        action="api_key.created",
        resource_id=str(result.id),
        request=request,
    )

    return api_response(result, request=request)


@router.delete(
    "/{key_id}",
    status_code=204,
    dependencies=[Depends(require_permission("api_keys", "delete"))],
)
async def revoke_api_key(
    tenant: str,
    key_id: UUID,
    service: Annotated[ApiKeyService, Depends(get_api_key_service)],
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> None:
    """Revoke an API key immediately. Next request using this key will get 401."""
    deleted = await service.revoke_api_key(tenant_id=tenant, key_id=key_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="API key not found.")

    await _log_api_key_audit(
        session=session,
        tenant=tenant,
        current_user=current_user,
        action="api_key.revoked",
        resource_id=str(key_id),
        request=request,
    )
