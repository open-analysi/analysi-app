"""REST API for control event history and manual triggering (Project Tilos).

TODO (access control): When role-based access control is added:
- POST (manual trigger) must be restricted to admin users only. Allowing
  arbitrary users to emit events on system channels like "disposition:ready"
  or "analysis:failed" would let them trigger unintended Task/Workflow
  executions (e.g. sending fake Slack notifications or JIRA tickets).
- GET (history) can be available to all authenticated users, but should be
  scoped to the tenant so cross-tenant data is never exposed.
- Consider a separate set of "user-triggerable" channels vs "system-only"
  channels, where only admins can emit on system channels.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api import ApiListResponse, ApiResponse, api_list_response, api_response
from analysi.auth.dependencies import require_permission
from analysi.db.session import get_db
from analysi.dependencies.tenant import get_tenant_id
from analysi.repositories.control_event_repository import ControlEventRepository
from analysi.schemas.control_event import (
    ControlEventCreate,
    ControlEventResponse,
)

router = APIRouter(
    prefix="/{tenant}/control-events",
    tags=["control-events"],
    dependencies=[Depends(require_permission("control_events", "read"))],
)


async def _get_repo(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ControlEventRepository:
    return ControlEventRepository(session)


@router.post(
    "",
    response_model=ApiResponse[ControlEventResponse],
    status_code=201,
    dependencies=[Depends(require_permission("control_events", "create"))],
)
async def create_control_event(
    request: Request,
    body: ControlEventCreate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    repo: Annotated[ControlEventRepository, Depends(_get_repo)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse[ControlEventResponse]:
    """Manually emit a control event on a channel.

    The event is inserted as 'pending' and picked up by the cron within 30s.
    Use this for testing rules without needing a real analysis to complete.
    """
    event = await repo.insert(
        tenant_id=tenant_id,
        channel=body.channel,
        payload=body.payload,
    )
    await session.commit()
    return api_response(ControlEventResponse.model_validate(event), request=request)


@router.get("", response_model=ApiListResponse[ControlEventResponse])
async def list_control_events(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    repo: Annotated[ControlEventRepository, Depends(_get_repo)],
    channel: str | None = Query(None, description="Filter by channel"),
    status: str | None = Query(
        None, description="Filter by status (pending, claimed, completed, failed)"
    ),
    limit: int = Query(
        50, ge=1, le=500, description="Maximum number of events to return"
    ),
    since_days: int = Query(30, ge=1, le=90, description="Look back this many days"),
) -> ApiListResponse[ControlEventResponse]:
    """List recent control events for the tenant, newest first.

    Useful for monitoring rule execution history and debugging failed events.
    """
    events = await repo.list_by_tenant(
        tenant_id=tenant_id,
        channel=channel,
        status=status,
        limit=limit,
        since_days=since_days,
    )
    items = [ControlEventResponse.model_validate(e) for e in events]
    return api_list_response(items, total=len(items), request=request)


@router.get("/{event_id}", response_model=ApiResponse[ControlEventResponse])
async def get_control_event(
    request: Request,
    event_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    repo: Annotated[ControlEventRepository, Depends(_get_repo)],
) -> ApiResponse[ControlEventResponse]:
    """Get a single control event by ID."""
    event = await repo.get_by_id(event_id)
    if event is None or event.tenant_id != tenant_id:
        raise HTTPException(
            status_code=404, detail=f"Control event {event_id} not found"
        )
    return api_response(ControlEventResponse.model_validate(event), request=request)
