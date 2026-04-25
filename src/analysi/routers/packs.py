"""Content Packs query and uninstall endpoints.

Lightweight endpoints for pack management:
- GET /v1/{tenant}/packs — list installed packs with component counts
- DELETE /v1/{tenant}/packs/{pack_name} — uninstall a pack
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api.responses import (
    ApiListResponse,
    ApiResponse,
    api_list_response,
    api_response,
)
from analysi.auth.dependencies import require_permission
from analysi.config.logging import get_logger
from analysi.constants import PackConstants
from analysi.db.session import get_db
from analysi.dependencies.tenant import get_tenant_id
from analysi.models.component import Component
from analysi.models.workflow import Workflow

logger = get_logger(__name__)

router = APIRouter(
    prefix="/{tenant}/packs",
    tags=["packs"],
)


class PackSummary(BaseModel):
    """Summary of an installed content pack."""

    name: str = Field(description="Pack name (app field value)")
    components: dict[str, int] = Field(
        description="Component counts by type (task, ku, module, workflows)"
    )


class PackUninstallResponse(BaseModel):
    """Response for pack uninstall."""

    pack_name: str
    components_deleted: int
    workflows_deleted: int
    message: str


@router.get(
    "",
    response_model=ApiListResponse[PackSummary],
    dependencies=[Depends(require_permission("tasks", "read"))],
    summary="List installed content packs",
)
async def list_packs(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[PackSummary]:
    """List installed content packs with component counts.

    Returns distinct app values (excluding 'default') across
    the component and workflow tables, with per-type counts.
    """
    # Component counts by app and kind
    comp_stmt = (
        select(Component.app, Component.kind, func.count())
        .where(
            Component.tenant_id == tenant_id, Component.app != PackConstants.DEFAULT_APP
        )
        .group_by(Component.app, Component.kind)
    )
    comp_result = await db.execute(comp_stmt)
    comp_rows = comp_result.all()

    # Workflow counts by app
    wf_stmt = (
        select(Workflow.app, func.count())
        .where(
            Workflow.tenant_id == tenant_id, Workflow.app != PackConstants.DEFAULT_APP
        )
        .group_by(Workflow.app)
    )
    wf_result = await db.execute(wf_stmt)
    wf_rows = wf_result.all()

    # Aggregate into pack summaries
    packs: dict[str, dict[str, int]] = {}

    for app_name, kind, count in comp_rows:
        if app_name not in packs:
            packs[app_name] = {}
        packs[app_name][kind] = count

    for app_name, count in wf_rows:
        if app_name not in packs:
            packs[app_name] = {}
        packs[app_name]["workflows"] = count

    summaries = [
        PackSummary(name=name, components=counts)
        for name, counts in sorted(packs.items())
    ]

    return api_list_response(summaries, total=len(summaries), request=request)


_MODIFICATION_THRESHOLD = timedelta(
    seconds=PackConstants.MODIFICATION_THRESHOLD_SECONDS
)


@router.delete(
    "/{pack_name}",
    response_model=ApiResponse[PackUninstallResponse],
    dependencies=[Depends(require_permission("tasks", "delete"))],
    summary="Uninstall a content pack",
)
async def uninstall_pack(
    pack_name: str,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    force: bool = Query(
        False,
        description="Force uninstall even if components were modified by users",
    ),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PackUninstallResponse]:
    """Uninstall a content pack by deleting all components and workflows
    tagged with the given app name.

    The implicit 'default' pack (user-created content) cannot be uninstalled.

    By default, refuses if any component has been modified by a user
    (updated_at significantly after created_at). Use ?force=true to override.
    """
    if pack_name == PackConstants.DEFAULT_APP:
        raise HTTPException(
            status_code=400,
            detail="Cannot uninstall the default pack",
        )

    # Modification check (unless force) — also serves as existence check
    if not force:
        threshold = _MODIFICATION_THRESHOLD
        modified_stmt = (
            select(func.count())
            .select_from(Component)
            .where(
                Component.tenant_id == tenant_id,
                Component.app == pack_name,
                Component.updated_at > Component.created_at + threshold,
            )
        )
        modified_result = await db.execute(modified_stmt)
        modified_count = modified_result.scalar() or 0

        if modified_count > 0:
            raise HTTPException(
                status_code=409,
                detail=f"Pack '{pack_name}' has {modified_count} user-modified component(s). "
                f"Use ?force=true to uninstall anyway.",
            )

    # Delete components
    comp_delete = await db.execute(
        delete(Component).where(
            Component.tenant_id == tenant_id, Component.app == pack_name
        )
    )
    components_deleted = comp_delete.rowcount

    # Delete workflows
    wf_delete = await db.execute(
        delete(Workflow).where(
            Workflow.tenant_id == tenant_id, Workflow.app == pack_name
        )
    )
    workflows_deleted = wf_delete.rowcount

    if components_deleted == 0 and workflows_deleted == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Pack '{pack_name}' not found in tenant",
        )

    await db.commit()

    logger.info(
        "pack_uninstalled",
        pack_name=pack_name,
        tenant_id=tenant_id,
        components_deleted=components_deleted,
        workflows_deleted=workflows_deleted,
    )

    return api_response(
        PackUninstallResponse(
            pack_name=pack_name,
            components_deleted=components_deleted,
            workflows_deleted=workflows_deleted,
            message=f"Uninstalled pack '{pack_name}': "
            f"{components_deleted} components, {workflows_deleted} workflows deleted",
        ),
        request=request,
    )
