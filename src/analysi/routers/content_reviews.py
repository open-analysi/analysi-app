"""Content reviews REST API.

Sub-resource of skills: /{tenant}/skills/{skill_id}/content-reviews
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api.responses import (
    ApiListResponse,
    ApiResponse,
    api_list_response,
    api_response,
)
from analysi.auth.dependencies import require_current_user, require_permission
from analysi.auth.models import CurrentUser
from analysi.config.logging import get_logger
from analysi.db.session import get_db
from analysi.dependencies.tenant import get_tenant_id
from analysi.schemas.content_review import (
    ContentReviewCreateRequest,
    ContentReviewRejectRequest,
    ContentReviewResponse,
)
from analysi.services.content_review import (
    ContentReviewGateError,
    ContentReviewService,
    ContentReviewStateError,
)

logger = get_logger(__name__)

router = APIRouter(
    prefix="/{tenant}/skills/{skill_id}/content-reviews",
    tags=["content-reviews"],
    dependencies=[Depends(require_permission("skills", "read"))],
)


@router.post(
    "",
    response_model=ApiResponse[ContentReviewResponse],
    status_code=201,
    dependencies=[Depends(require_permission("skills", "create"))],
)
async def create_content_review(
    skill_id: UUID,
    body: ContentReviewCreateRequest,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """Start a content review for a document (extraction pipeline).

    Runs content gates immediately; if passed, enqueues async LLM pipeline.
    Owner role bypasses LLM tier (content gates still run).
    """
    from analysi.repositories.knowledge_module import KnowledgeModuleRepository
    from analysi.repositories.knowledge_unit import KnowledgeUnitRepository

    km_repo = KnowledgeModuleRepository(db)
    skill = await km_repo.get_skill_by_id(skill_id, tenant_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    ku_repo = KnowledgeUnitRepository(db)
    doc = await ku_repo.get_document_by_id(body.document_id, tenant_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    content = doc.content or ""
    filename = doc.component.name if doc.component else "unknown"

    service = ContentReviewService(db)
    try:
        review = await service.submit_for_review(
            content=content,
            filename=filename,
            skill_id=skill_id,
            tenant_id=tenant_id,
            pipeline_name="extraction",
            trigger_source="content_review_api",
            actor_user_id=current_user.db_user_id,
            actor_roles=current_user.roles,
            document_id=body.document_id,
        )
    except ContentReviewGateError:
        raise HTTPException(status_code=422, detail="Content failed validation checks")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid extraction request")
    except Exception:
        logger.exception("create_content_review_error")
        raise HTTPException(status_code=500, detail="Internal server error")

    await db.commit()
    return api_response(ContentReviewResponse.model_validate(review), request=request)


@router.get(
    "",
    response_model=ApiListResponse[ContentReviewResponse],
)
async def list_content_reviews(
    skill_id: UUID,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    status: str | None = Query(None, description="Filter by status"),
    pipeline_name: str | None = Query(None, description="Filter by pipeline name"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List content reviews for a skill."""
    service = ContentReviewService(db)
    reviews, total = await service.list_reviews(
        tenant_id=tenant_id,
        skill_id=skill_id,
        status=status,
        pipeline_name=pipeline_name,
        limit=limit,
        offset=offset,
    )
    items = [ContentReviewResponse.model_validate(r) for r in reviews]
    return api_list_response(items, total=total, request=request)


@router.get(
    "/{review_id}",
    response_model=ApiResponse[ContentReviewResponse],
)
async def get_content_review(
    skill_id: UUID,
    review_id: UUID,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: AsyncSession = Depends(get_db),
):
    """Get a content review by ID."""
    service = ContentReviewService(db)
    review = await service.get_review(review_id, tenant_id)
    if review is None or review.skill_id != skill_id:
        raise HTTPException(status_code=404, detail="Content review not found")
    return api_response(ContentReviewResponse.model_validate(review), request=request)


@router.post(
    "/{review_id}/apply",
    response_model=ApiResponse[ContentReviewResponse],
    dependencies=[Depends(require_permission("skills", "update"))],
)
async def apply_content_review(
    skill_id: UUID,
    review_id: UUID,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: AsyncSession = Depends(get_db),
):
    """Apply an approved or flagged content review."""
    service = ContentReviewService(db)

    review = await service.get_review(review_id, tenant_id)
    if review is None or review.skill_id != skill_id:
        raise HTTPException(status_code=404, detail="Content review not found")

    try:
        review = await service.apply_review(review_id, tenant_id=tenant_id)
        await db.commit()
    except ContentReviewStateError:
        raise HTTPException(
            status_code=409, detail="Review cannot be applied in current state"
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("apply_content_review_error")
        raise HTTPException(status_code=500, detail="Internal server error")

    return api_response(ContentReviewResponse.model_validate(review), request=request)


@router.post(
    "/{review_id}/reject",
    response_model=ApiResponse[ContentReviewResponse],
    dependencies=[Depends(require_permission("skills", "update"))],
)
async def reject_content_review(
    skill_id: UUID,
    review_id: UUID,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    body: ContentReviewRejectRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Reject a content review."""
    service = ContentReviewService(db)

    review = await service.get_review(review_id, tenant_id)
    if review is None or review.skill_id != skill_id:
        raise HTTPException(status_code=404, detail="Content review not found")

    try:
        reason = body.reason if body else None
        review = await service.reject_review(
            review_id, reason=reason, tenant_id=tenant_id
        )
        await db.commit()
    except ContentReviewStateError:
        raise HTTPException(
            status_code=409,
            detail="Review cannot be rejected in current state",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("reject_content_review_error")
        raise HTTPException(status_code=500, detail="Internal server error")

    return api_response(ContentReviewResponse.model_validate(review), request=request)


@router.post(
    "/{review_id}/retry",
    response_model=ApiResponse[ContentReviewResponse],
    status_code=202,
    dependencies=[Depends(require_permission("skills", "update"))],
)
async def retry_content_review(
    skill_id: UUID,
    review_id: UUID,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    db: AsyncSession = Depends(get_db),
):
    """Retry a failed content review by re-enqueuing it for processing."""
    service = ContentReviewService(db)

    review = await service.get_review(review_id, tenant_id)
    if review is None or review.skill_id != skill_id:
        raise HTTPException(status_code=404, detail="Content review not found")

    try:
        review = await service.retry_review(review_id, tenant_id=tenant_id)
        await db.commit()
    except ContentReviewStateError:
        raise HTTPException(
            status_code=409,
            detail="Only failed reviews can be retried",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("retry_content_review_error")
        raise HTTPException(status_code=500, detail="Internal server error")

    return api_response(ContentReviewResponse.model_validate(review), request=request)
