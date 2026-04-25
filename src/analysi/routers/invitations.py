"""Invitation acceptance endpoint.

Project Mikonos — Auth & RBAC (Spec: version_7/AuthAndRBAC_v1.md)

This router is mounted DIRECTLY in main.py (outside the v1 router) because
accept-invite callers are not yet members of the tenant — they would fail
the check_tenant_access guard that the v1 router enforces.

The endpoint only requires authentication (require_current_user), not tenant
membership. The invitation token itself is the proof of authorization.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api import ApiResponse, api_response
from analysi.auth.dependencies import require_current_user
from analysi.auth.models import CurrentUser
from analysi.db.session import get_db
from analysi.schemas.auth import AcceptInviteRequest, MemberResponse
from analysi.services.member_service import MemberService

# Prefix mirrors the v1 member path so the URL is /v1/{tenant}/members/accept-invite.
# This router is registered in main.py with prefix="/v1".
router = APIRouter(
    prefix="/v1",
    tags=["members"],
)


async def get_member_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MemberService:
    return MemberService(session)


@router.post(
    "/{tenant}/members/accept-invite",
    response_model=ApiResponse[MemberResponse],
    status_code=201,
)
async def accept_invite(
    request: Request,
    tenant: str,
    body: AcceptInviteRequest,
    service: Annotated[MemberService, Depends(get_member_service)],
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
) -> ApiResponse[MemberResponse]:
    """Accept an invitation token and create a tenant membership.

    Single-use: rejects if the token has already been accepted.
    Rate-limited: 5 attempts per token per hour.
    """
    result = await service.accept_invite(
        tenant_id=tenant,
        token=body.token,
        current_user=current_user,
    )
    return api_response(result, request=request)
