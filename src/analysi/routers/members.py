"""Member management endpoints.

Project Mikonos — Auth & RBAC (Spec: version_7/AuthAndRBAC_v1.md)
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api import ApiListResponse, ApiResponse, api_list_response, api_response
from analysi.auth.dependencies import require_current_user, require_permission
from analysi.auth.models import CurrentUser
from analysi.db.session import get_db
from analysi.models.auth import SYSTEM_USER_ID
from analysi.repositories.activity_audit_repository import ActivityAuditRepository
from analysi.repositories.user_repository import UserRepository
from analysi.schemas.auth import (
    ChangeRoleRequest,
    InvitationResponse,
    InvitationWithTokenResponse,
    InviteRequest,
    MemberResponse,
)
from analysi.services.member_service import MemberService

router = APIRouter(
    prefix="/{tenant}/members",
    tags=["members"],
    dependencies=[Depends(require_permission("members", "read"))],
)


async def get_member_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MemberService:
    return MemberService(session)


async def _log_member_audit(
    session: AsyncSession,
    tenant: str,
    current_user: CurrentUser,
    action: str,
    resource_id: str,
    request: Request,
    details: dict | None = None,
) -> None:
    """Record an audit event for a member lifecycle action."""
    repo = ActivityAuditRepository(session)
    await repo.create(
        tenant_id=tenant,
        actor_id=current_user.db_user_id or SYSTEM_USER_ID,
        actor_type=current_user.actor_type,
        source="rest_api",
        action=action,
        resource_type="member",
        resource_id=resource_id,
        details=details,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=None,
    )


@router.get("", response_model=ApiListResponse[MemberResponse])
async def list_members(
    request: Request,
    tenant: str,
    service: Annotated[MemberService, Depends(get_member_service)],
) -> ApiListResponse[MemberResponse]:
    """List all members of a tenant with their roles."""
    members = await service.list_members(tenant)
    return api_list_response(members, total=len(members), request=request)


@router.post(
    "/invite",
    response_model=ApiResponse[InvitationResponse],
    status_code=201,
    dependencies=[Depends(require_permission("members", "invite"))],
)
async def invite_member(
    request: Request,
    tenant: str,
    body: InviteRequest,
    service: Annotated[MemberService, Depends(get_member_service)],
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse[InvitationResponse]:
    """Send a member invitation (single-use, 7-day expiry).

    The invitation token is included in the response for testing purposes.
    In production, this would be sent via email only.
    """
    # Resolve the inviter's User record by their Keycloak ID
    user_repo = UserRepository(session)
    inviter_db_user = await user_repo.get_by_keycloak_id(current_user.user_id)
    inviter_user_id = inviter_db_user.id if inviter_db_user else None

    invitation_response, _token = await service.invite_member(
        tenant_id=tenant,
        email=body.email,
        role=body.role,
        inviter_user_id=inviter_user_id,
    )
    return api_response(invitation_response, request=request)


@router.post(
    "/invite-with-token",
    response_model=ApiResponse[InvitationWithTokenResponse],
    status_code=201,
    dependencies=[Depends(require_permission("members", "invite"))],
    include_in_schema=False,  # Dev/test endpoint only — not in public docs
)
async def invite_member_with_token(
    request: Request,
    tenant: str,
    body: InviteRequest,
    service: Annotated[MemberService, Depends(get_member_service)],
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse[InvitationWithTokenResponse]:
    """Invite endpoint that returns the plaintext token (for testing only).

    In production, the token would be sent via email and never exposed in the API.
    """
    user_repo = UserRepository(session)
    inviter_db_user = await user_repo.get_by_keycloak_id(current_user.user_id)
    inviter_user_id = inviter_db_user.id if inviter_db_user else None

    invitation_response, token = await service.invite_member(
        tenant_id=tenant,
        email=body.email,
        role=body.role,
        inviter_user_id=inviter_user_id,
    )
    return api_response(
        InvitationWithTokenResponse(**invitation_response.model_dump(), token=token),
        request=request,
    )


@router.patch(
    "/{user_id}",
    response_model=ApiResponse[MemberResponse],
    dependencies=[Depends(require_permission("members", "update"))],
)
async def change_role(
    tenant: str,
    user_id: UUID,
    body: ChangeRoleRequest,
    service: Annotated[MemberService, Depends(get_member_service)],
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> ApiResponse[MemberResponse]:
    """Change a member's role. Prevents removing the last owner."""
    result = await service.change_role(
        tenant_id=tenant,
        user_id=user_id,
        new_role=body.role,
    )

    await _log_member_audit(
        session=session,
        tenant=tenant,
        current_user=current_user,
        action="member.role_changed",
        resource_id=str(user_id),
        request=request,
        details={"new_role": body.role},
    )

    return api_response(result, request=request)


@router.delete(
    "/{user_id}",
    status_code=204,
    dependencies=[Depends(require_permission("members", "delete"))],
)
async def remove_member(
    tenant: str,
    user_id: UUID,
    service: Annotated[MemberService, Depends(get_member_service)],
) -> None:
    """Remove a member and revoke all their API keys for this tenant."""
    await service.remove_member(tenant_id=tenant, user_id=user_id)
