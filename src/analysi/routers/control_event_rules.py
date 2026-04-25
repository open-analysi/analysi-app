"""CRUD REST API for control event rules (Project Tilos).

TODO (access control): When role-based access control is added, restrict which
channels a non-admin user can manually trigger. System channels like
"disposition:ready" and "analysis:failed" should only be triggerable by admins
or internal services — not regular users. Regular users should only be able to
trigger custom/user-defined channels.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api import ApiListResponse, ApiResponse, api_list_response, api_response
from analysi.auth.dependencies import require_permission
from analysi.db.session import get_db
from analysi.dependencies.tenant import get_tenant_id
from analysi.repositories.control_event_repository import ControlEventRuleRepository
from analysi.schemas.control_event_rule import (
    ControlEventRuleCreate,
    ControlEventRuleResponse,
    ControlEventRuleUpdate,
)

router = APIRouter(
    prefix="/{tenant}/control-event-rules",
    tags=["control-event-rules"],
    dependencies=[Depends(require_permission("control_events", "read"))],
)


async def _get_repo(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ControlEventRuleRepository:
    return ControlEventRuleRepository(session)


@router.post(
    "",
    response_model=ApiResponse[ControlEventRuleResponse],
    status_code=201,
    dependencies=[Depends(require_permission("control_events", "create"))],
)
async def create_control_event_rule(
    request: Request,
    body: ControlEventRuleCreate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    repo: Annotated[ControlEventRuleRepository, Depends(_get_repo)],
) -> ApiResponse[ControlEventRuleResponse]:
    """Create a control event rule binding a channel to a task or workflow."""
    rule = await repo.create(
        tenant_id=tenant_id,
        channel=body.channel,
        target_type=body.target_type,
        target_id=body.target_id,
        name=body.name,
        enabled=body.enabled,
        config=body.config,
    )
    return api_response(ControlEventRuleResponse.model_validate(rule), request=request)


@router.get("", response_model=ApiListResponse[ControlEventRuleResponse])
async def list_control_event_rules(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    repo: Annotated[ControlEventRuleRepository, Depends(_get_repo)],
    channel: str | None = Query(None, description="Filter by channel"),
    enabled_only: bool = Query(False, description="Return only enabled rules"),
) -> ApiListResponse[ControlEventRuleResponse]:
    """List all control event rules for the tenant."""
    rules = await repo.list_by_tenant(
        tenant_id, channel=channel, enabled_only=enabled_only
    )
    items = [ControlEventRuleResponse.model_validate(r) for r in rules]
    return api_list_response(items, total=len(items), request=request)


@router.get("/{rule_id}", response_model=ApiResponse[ControlEventRuleResponse])
async def get_control_event_rule(
    request: Request,
    rule_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    repo: Annotated[ControlEventRuleRepository, Depends(_get_repo)],
) -> ApiResponse[ControlEventRuleResponse]:
    """Get a single control event rule by ID."""
    rule = await repo.get_by_id(tenant_id, rule_id)
    if rule is None:
        raise HTTPException(
            status_code=404, detail=f"Control event rule {rule_id} not found"
        )
    return api_response(ControlEventRuleResponse.model_validate(rule), request=request)


@router.patch(
    "/{rule_id}",
    response_model=ApiResponse[ControlEventRuleResponse],
    dependencies=[Depends(require_permission("control_events", "update"))],
)
async def update_control_event_rule(
    request: Request,
    rule_id: UUID,
    body: ControlEventRuleUpdate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    repo: Annotated[ControlEventRuleRepository, Depends(_get_repo)],
) -> ApiResponse[ControlEventRuleResponse]:
    """Partially update a control event rule."""
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields provided for update")
    rule = await repo.update(tenant_id, rule_id, **fields)
    if rule is None:
        raise HTTPException(
            status_code=404, detail=f"Control event rule {rule_id} not found"
        )
    return api_response(ControlEventRuleResponse.model_validate(rule), request=request)


@router.delete(
    "/{rule_id}",
    status_code=204,
    dependencies=[Depends(require_permission("control_events", "delete"))],
)
async def delete_control_event_rule(
    rule_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    repo: Annotated[ControlEventRuleRepository, Depends(_get_repo)],
) -> None:
    """Delete a control event rule."""
    deleted = await repo.delete(tenant_id, rule_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Control event rule {rule_id} not found"
        )
