"""Artifacts REST API endpoints.

Complete REST API implementation following existing router patterns.
"""

import io
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api import (
    ApiListResponse,
    ApiResponse,
    PaginationParams,
    api_list_response,
    api_response,
)
from analysi.auth.dependencies import require_permission
from analysi.auth.messages import INTERNAL_ERROR
from analysi.config.logging import get_logger
from analysi.db.session import get_db
from analysi.dependencies.tenant import get_tenant_id
from analysi.schemas.artifact import ArtifactCreate, ArtifactResponse
from analysi.services.artifact_service import ArtifactService

logger = get_logger(__name__)


def _safe_content_disposition(filename: str) -> str:
    """Build a Content-Disposition header value that is safe against
    header injection and correctly represents non-ASCII filenames.

    - Strips CR/LF to prevent response-splitting attacks.
    - Emits both an ASCII ``filename="..."`` parameter (for legacy clients)
      and an RFC 5987 ``filename*=UTF-8''...`` parameter (for full Unicode).
    - Escapes quotes and backslashes inside the ASCII parameter so a
      malicious filename cannot break out of the quoted-string.
    """
    # Strip header-breaking characters
    safe = filename.replace("\r", "").replace("\n", "")

    # ASCII fallback: replace non-ASCII with "_", strip quotes/backslashes
    ascii_fallback = (
        safe.encode("ascii", "replace")
        .decode("ascii")
        .replace("?", "_")
        .replace('"', "")
        .replace("\\", "")
    )

    # RFC 5987 encoded form — percent-encode everything outside attr-char set
    rfc5987 = quote(safe, safe="")

    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{rfc5987}"


router = APIRouter(
    prefix="/{tenant}/artifacts",
    tags=["artifacts"],
    dependencies=[Depends(require_permission("tasks", "read"))],
)


async def get_artifact_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ArtifactService:
    """Dependency injection for ArtifactService."""
    return ArtifactService(session)


@router.post(
    "",
    response_model=ApiResponse[ArtifactResponse],
    status_code=201,
    dependencies=[Depends(require_permission("tasks", "create"))],
)
async def create_artifact(
    request: Request,
    artifact_data: ArtifactCreate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
) -> ApiResponse[ArtifactResponse]:
    """Create a new artifact.

    Raises:
        HTTPException 400: Invalid data
        HTTPException 413: Content too large
        HTTPException 500: Storage error
    """
    try:
        response = await service.create_artifact(tenant_id, artifact_data)
        return api_response(response, request=request)

    except ValueError as e:
        logger.error("create_artifact_validation_error", error=str(e))
        raise HTTPException(status_code=400, detail="Invalid artifact data")
    except RuntimeError:
        logger.exception("create_artifact: storage error")
        raise HTTPException(status_code=500, detail="Storage error")
    except Exception:
        logger.exception("create_artifact: unexpected error")
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR)


@router.get("", response_model=ApiListResponse[ArtifactResponse])
async def list_artifacts(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
    pagination: PaginationParams = Depends(),
    name: str | None = Query(None, description="Filter by name (partial match)"),
    artifact_type: str | None = Query(None, description="Filter by artifact type"),
    task_run_id: UUID | None = Query(None, description="Filter by task run ID"),
    workflow_run_id: UUID | None = Query(None, description="Filter by workflow run ID"),
    analysis_id: UUID | None = Query(None, description="Filter by analysis ID"),
    alert_id: UUID | None = Query(None, description="Filter by alert ID"),
    mime_type: str | None = Query(None, description="Filter by MIME type"),
    storage_class: str | None = Query(
        None, pattern="^(inline|object)$", description="Filter by storage class"
    ),
    integration_id: str | None = Query(
        None, description="Filter by integration instance ID"
    ),
    source: str | None = Query(None, description="Filter by provenance source"),
    sort: str = Query("created_at", description="Sort field"),
    order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
) -> ApiListResponse[ArtifactResponse]:
    """List artifacts with filtering and pagination."""
    # Build filters dictionary
    filters = {}
    if name:
        filters["name"] = name
    if artifact_type:
        filters["artifact_type"] = artifact_type
    if task_run_id:
        filters["task_run_id"] = task_run_id
    if workflow_run_id:
        filters["workflow_run_id"] = workflow_run_id
    if analysis_id:
        filters["analysis_id"] = analysis_id
    if alert_id:
        filters["alert_id"] = alert_id
    if mime_type:
        filters["mime_type"] = mime_type
    if storage_class:
        filters["storage_class"] = storage_class
    if integration_id:
        filters["integration_id"] = integration_id
    if source:
        filters["source"] = source

    items, total = await service.list_artifacts(
        tenant_id, filters, pagination.limit, pagination.offset, sort, order
    )

    return api_list_response(items, total=total, request=request, pagination=pagination)


@router.get("/{artifact_id}", response_model=ApiResponse[ArtifactResponse])
async def get_artifact(
    request: Request,
    artifact_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
) -> ApiResponse[ArtifactResponse]:
    """Get artifact metadata by ID.

    Raises:
        HTTPException 404: Artifact not found
        HTTPException 403: Tenant mismatch
    """
    response = await service.get_artifact(tenant_id, artifact_id)

    if not response:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return api_response(response, request=request)


@router.get("/{artifact_id}/download")
async def download_artifact(
    artifact_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
) -> StreamingResponse:
    """Download artifact raw content.

    Returns:
        Streaming response with raw content

    Raises:
        HTTPException 404: Artifact not found
    """
    result = await service.get_artifact_content(tenant_id, artifact_id)

    if not result:
        raise HTTPException(status_code=404, detail="Artifact not found")

    content_bytes, mime_type, filename, sha256_hex = result

    return StreamingResponse(
        io.BytesIO(content_bytes),
        media_type=mime_type,
        headers={
            "Content-Disposition": _safe_content_disposition(filename),
            "Content-Length": str(len(content_bytes)),
            "ETag": f'"{sha256_hex}"',
        },
    )


@router.delete(
    "/{artifact_id}",
    status_code=204,
    dependencies=[Depends(require_permission("tasks", "delete"))],
)
async def delete_artifact(
    artifact_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[ArtifactService, Depends(get_artifact_service)],
) -> None:
    """Soft delete artifact (mark as deleted, preserve data)."""
    deleted = await service.delete_artifact(tenant_id, artifact_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Artifact not found")
