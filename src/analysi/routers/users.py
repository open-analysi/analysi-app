"""User resolution endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api import ApiListResponse, ApiResponse, api_list_response, api_response
from analysi.auth.dependencies import require_current_user, require_permission
from analysi.auth.models import CurrentUser
from analysi.db.session import get_db
from analysi.repositories.user_repository import UserRepository

router = APIRouter(
    prefix="/{tenant}/users",
    tags=["users"],
    dependencies=[Depends(require_permission("users", "read"))],
)


class UserProfileResponse(BaseModel):
    id: UUID
    email: str
    display_name: str | None = None


@router.get("/me", response_model=ApiResponse[UserProfileResponse])
async def get_current_user_profile(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse[UserProfileResponse]:
    """Get current user's profile (any authenticated user)."""
    repo = UserRepository(session)
    db_user = await repo.get_by_keycloak_id(current_user.user_id)
    if db_user is None:
        # JIT provisioning should have created the user, but handle edge case
        profile = UserProfileResponse(
            id=current_user.db_user_id or UUID("00000000-0000-0000-0000-000000000002"),
            email=current_user.email,
            display_name=None,
        )
    else:
        profile = UserProfileResponse(
            id=db_user.id,
            email=db_user.email,
            display_name=db_user.display_name,
        )
    return api_response(profile, request=request)


@router.get("/resolve", response_model=ApiListResponse[UserProfileResponse])
async def resolve_users(
    request: Request,
    tenant: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    ids: list[UUID] = Query(..., description="User UUIDs to resolve (max 50)"),
) -> ApiListResponse[UserProfileResponse]:
    """Batch resolve user UUIDs to profiles.

    Tenant-scoped: only returns users who are members of the requesting
    tenant, plus well-known sentinel users (SYSTEM_USER_ID, UNKNOWN_USER_ID).
    """
    # Cap at 50 to prevent abuse
    capped_ids = ids[:50]
    repo = UserRepository(session)
    db_users = await repo.get_by_ids_in_tenant(capped_ids, tenant)
    profiles = [
        UserProfileResponse(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
        )
        for u in db_users
    ]
    return api_list_response(profiles, total=len(profiles), request=request)
