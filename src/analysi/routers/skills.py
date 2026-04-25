"""Skills (Knowledge Modules) management endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api import (
    ApiListResponse,
    ApiResponse,
    PaginationParams,
    api_list_response,
    api_response,
)
from analysi.auth.dependencies import require_current_user, require_permission
from analysi.auth.models import CurrentUser
from analysi.config.logging import get_logger
from analysi.db.session import get_db
from analysi.dependencies.audit import get_audit_context
from analysi.dependencies.tenant import get_tenant_id
from analysi.models.content_review import ContentReviewStatus
from analysi.schemas.audit_context import AuditContext
from analysi.schemas.skill import (
    RepairEdgesResponse,
    SkillCreate,
    SkillDeleteCheck,
    SkillDocumentLink,
    SkillDocumentLinkResponse,
    SkillFileContent,
    SkillResponse,
    SkillTreeEntry,
    SkillTreeResponse,
    SkillUpdate,
    StagedDocumentEntry,
    StagedDocumentRequest,
    StagedDocumentResponse,
    is_extraction_eligible,
)
from analysi.schemas.skill_import import SkillImportResponse
from analysi.services.content_review import (
    ContentReviewGateError,
    ContentReviewService,
)
from analysi.services.knowledge_module import (
    DocumentNotFoundError,
    KnowledgeModuleService,
    repair_missing_skill_edges,
)
from analysi.services.knowledge_unit import KnowledgeUnitService

logger = get_logger(__name__)

router = APIRouter(
    prefix="/{tenant}/skills",
    tags=["skills"],
    dependencies=[Depends(require_permission("skills", "read"))],
)


async def get_skill_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> KnowledgeModuleService:
    """Dependency injection for KnowledgeModuleService."""
    return KnowledgeModuleService(session)


def _build_skill_response(module, review_counts: dict | None = None) -> dict:
    """Build response dict from KnowledgeModule.

    Args:
        module: KnowledgeModule with loaded component relationship.
        review_counts: Optional {skill_id: {pending: N, flagged: N}} from
            _fetch_review_counts. When None, counts default to 0.
    """
    counts = (review_counts or {}).get(module.component.id, {})
    return {
        "id": module.component.id,
        "tenant_id": module.component.tenant_id,
        "module_type": module.module_type,
        "name": module.component.name,
        "description": module.component.description,
        "version": module.component.version,
        "status": module.component.status,
        "visible": module.component.visible,
        "system_only": module.component.system_only,
        "app": module.component.app,
        "categories": module.component.categories,
        "created_by": module.component.created_by,
        "cy_name": module.component.cy_name,
        "namespace": module.component.namespace,
        "root_document_path": module.root_document_path,
        "config": module.config or {},
        "created_at": module.created_at,
        "updated_at": module.updated_at,
        "last_used_at": module.component.last_used_at,
        "extraction_eligible": is_extraction_eligible(module.component.cy_name),
        "pending_reviews_count": counts.get("pending", 0),
        "flagged_reviews_count": counts.get("flagged", 0),
    }


async def _fetch_review_counts(
    session: AsyncSession, tenant_id: str, skill_ids: list[UUID]
) -> dict[UUID, dict[str, int]]:
    """Fetch pending and flagged review counts for a batch of skills in one query.

    Returns:
        {skill_id: {"pending": N, "flagged": N}}
    """
    if not skill_ids:
        return {}

    from sqlalchemy import case, func, select

    from analysi.models.content_review import ContentReview

    stmt = (
        select(
            ContentReview.skill_id,
            func.count(
                case((ContentReview.status == ContentReviewStatus.PENDING, 1))
            ).label("pending"),
            func.count(case((ContentReview.status == "flagged", 1))).label("flagged"),
        )
        .where(
            ContentReview.tenant_id == tenant_id,
            ContentReview.skill_id.in_(skill_ids),
            ContentReview.status.in_(
                [ContentReviewStatus.PENDING, ContentReviewStatus.FLAGGED]
            ),
        )
        .group_by(ContentReview.skill_id)
    )

    result = await session.execute(stmt)
    return {
        row.skill_id: {"pending": row.pending, "flagged": row.flagged} for row in result
    }


async def _submit_validation_review(
    session: AsyncSession,
    document_id: UUID,
    skill_id: UUID,
    tenant_id: str,
    trigger_source: str,
    current_user: CurrentUser,
) -> None:
    """Read document content and submit for skill_validation review.

    Raises ContentReviewGateError if content gates fail (propagated for 422).
    """
    ku_service = KnowledgeUnitService(session)
    doc = await ku_service.get_document(document_id, tenant_id)
    if not doc:
        raise DocumentNotFoundError(f"Document {document_id} not found")

    content = doc.content or doc.markdown_content or ""
    if not content.strip():
        return  # Empty docs will fail empty_content_check anyway

    filename = doc.component.name or "unknown.md"

    review_service = ContentReviewService(session)
    await review_service.submit_for_review(
        content=content,
        filename=filename,
        skill_id=skill_id,
        tenant_id=tenant_id,
        pipeline_name="skill_validation",
        trigger_source=trigger_source,
        actor_user_id=current_user.db_user_id,
        actor_roles=current_user.roles,
        document_id=document_id,
    )


# --- CRUD Endpoints ---


@router.post(
    "",
    response_model=ApiResponse[SkillResponse],
    status_code=201,
    dependencies=[Depends(require_permission("skills", "create"))],
)
async def create_skill(
    request: Request,
    skill_data: SkillCreate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeModuleService, Depends(get_skill_service)],
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
) -> ApiResponse[SkillResponse]:
    """Create a new skill module."""
    module = await service.create_skill(
        tenant_id, skill_data, created_by=audit_context.actor_user_id
    )
    return api_response(
        SkillResponse.model_validate(_build_skill_response(module)), request=request
    )


@router.get("", response_model=ApiListResponse[SkillResponse])
async def list_skills(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeModuleService, Depends(get_skill_service)],
    pagination: PaginationParams = Depends(),
    q: str | None = Query(
        None, min_length=1, description="Search query for name, description, categories"
    ),
    status: str | None = Query(None, description="Filter by status (enabled/disabled)"),
    categories: list[str] | None = Query(
        None, description="Filter by categories (AND semantics)"
    ),
    app: str | None = Query(None, description="Filter by content pack name"),
) -> ApiListResponse[SkillResponse]:
    """List skills with optional search and pagination."""
    if status and status not in ["enabled", "disabled"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid status value. Must be 'enabled' or 'disabled'",
        )

    modules, meta = await service.list_skills(
        tenant_id=tenant_id,
        status=status,
        search=q,
        skip=pagination.offset,
        limit=pagination.limit,
        categories=categories,
        app=app,
    )

    skill_ids = [m.component.id for m in modules]
    review_counts = await _fetch_review_counts(service.session, tenant_id, skill_ids)

    skill_responses = [
        SkillResponse.model_validate(_build_skill_response(m, review_counts))
        for m in modules
    ]

    return api_list_response(
        skill_responses, total=meta["total"], request=request, pagination=pagination
    )


@router.get("/{id}", response_model=ApiResponse[SkillResponse])
async def get_skill(
    request: Request,
    id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeModuleService, Depends(get_skill_service)],
) -> ApiResponse[SkillResponse]:
    """Get a skill by ID."""
    module = await service.get_skill(id, tenant_id)
    if not module:
        raise HTTPException(status_code=404, detail="Skill not found")

    review_counts = await _fetch_review_counts(service.session, tenant_id, [id])

    return api_response(
        SkillResponse.model_validate(_build_skill_response(module, review_counts)),
        request=request,
    )


@router.put(
    "/{id}",
    response_model=ApiResponse[SkillResponse],
    dependencies=[Depends(require_permission("skills", "update"))],
)
async def update_skill(
    request: Request,
    id: UUID,
    update_data: SkillUpdate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeModuleService, Depends(get_skill_service)],
) -> ApiResponse[SkillResponse]:
    """Update an existing skill."""
    module = await service.update_skill(id, tenant_id, update_data)
    if not module:
        raise HTTPException(status_code=404, detail="Skill not found")

    return api_response(
        SkillResponse.model_validate(_build_skill_response(module)), request=request
    )


@router.delete(
    "/{id}",
    status_code=204,
    dependencies=[Depends(require_permission("skills", "delete"))],
)
async def delete_skill(
    id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeModuleService, Depends(get_skill_service)],
) -> None:
    """Delete a skill."""
    success = await service.delete_skill(id, tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Skill not found")


@router.get("/{id}/check-delete", response_model=ApiResponse[SkillDeleteCheck])
async def check_skill_delete(
    request: Request,
    id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeModuleService, Depends(get_skill_service)],
) -> ApiResponse[SkillDeleteCheck]:
    """Check what would be affected by deleting a skill."""
    module = await service.get_skill(id, tenant_id)
    if not module:
        raise HTTPException(status_code=404, detail="Skill not found")

    check_result = await service.check_skill_delete(id, tenant_id)
    return api_response(SkillDeleteCheck.model_validate(check_result), request=request)


# --- Document Management Endpoints ---


@router.post(
    "/{id}/documents",
    response_model=ApiResponse[SkillDocumentLinkResponse],
    status_code=201,
    dependencies=[Depends(require_permission("skills", "update"))],
)
async def link_document_to_skill(
    request: Request,
    id: UUID,
    link_data: SkillDocumentLink,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeModuleService, Depends(get_skill_service)],
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse[SkillDocumentLinkResponse]:
    """Link a document to a skill with a namespace path.

    Also submits document for skill_validation content review.
    Sync check failures return 422 (document not linked).
    """
    module = await service.get_skill(id, tenant_id)
    if not module:
        raise HTTPException(status_code=404, detail="Skill not found")

    # Submit for validation BEFORE linking (sync gate is fail-fast)
    try:
        await _submit_validation_review(
            session=session,
            document_id=link_data.document_id,
            skill_id=id,
            tenant_id=tenant_id,
            trigger_source="link_document",
            current_user=current_user,
        )
    except DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")
    except ContentReviewGateError:
        raise HTTPException(
            status_code=422,
            detail="Content validation failed: document did not pass safety checks",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("validation_review_unexpected_error")
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )

    try:
        result = await service.add_document(
            tenant_id=tenant_id,
            skill_id=id,
            document_id=link_data.document_id,
            namespace_path=link_data.namespace_path,
        )
        return api_response(
            SkillDocumentLinkResponse.model_validate(result), request=request
        )
    except ValueError:
        raise HTTPException(status_code=409, detail="Document link conflict")


@router.delete(
    "/{id}/documents/{document_id}",
    status_code=204,
    dependencies=[Depends(require_permission("skills", "update"))],
)
async def unlink_document_from_skill(
    id: UUID,
    document_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeModuleService, Depends(get_skill_service)],
) -> None:
    """Unlink a document from a skill."""
    module = await service.get_skill(id, tenant_id)
    if not module:
        raise HTTPException(status_code=404, detail="Skill not found")

    success = await service.remove_document(tenant_id, id, document_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not linked to this skill")


@router.get("/{id}/tree", response_model=ApiResponse[SkillTreeResponse])
async def get_skill_tree(
    request: Request,
    id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeModuleService, Depends(get_skill_service)],
) -> ApiResponse[SkillTreeResponse]:
    """Get the file tree for a skill (list of namespace paths)."""
    module = await service.get_skill(id, tenant_id)
    if not module:
        raise HTTPException(status_code=404, detail="Skill not found")

    tree = await service.get_skill_tree(tenant_id, id)
    tree_entries = [SkillTreeEntry.model_validate(entry) for entry in tree]

    return api_response(
        SkillTreeResponse(
            skill_id=str(id),
            files=tree_entries,
            total=len(tree_entries),
        ),
        request=request,
    )


@router.get("/{id}/files/{path:path}", response_model=ApiResponse[SkillFileContent])
async def read_skill_file(
    request: Request,
    id: UUID,
    path: str,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeModuleService, Depends(get_skill_service)],
) -> ApiResponse[SkillFileContent]:
    """Read a document's content by its namespace path within a skill."""
    module = await service.get_skill(id, tenant_id)
    if not module:
        raise HTTPException(status_code=404, detail="Skill not found")

    file_content = await service.read_skill_file(tenant_id, id, path)
    if not file_content:
        raise HTTPException(status_code=404, detail="File not found in skill")

    return api_response(SkillFileContent.model_validate(file_content), request=request)


# --- Staged Documents Endpoints ---


@router.post(
    "/{id}/staged-documents",
    response_model=ApiResponse[StagedDocumentResponse],
    status_code=201,
    dependencies=[Depends(require_permission("skills", "update"))],
)
async def stage_document(
    request: Request,
    id: UUID,
    stage_request: StagedDocumentRequest,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeModuleService, Depends(get_skill_service)],
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse[StagedDocumentResponse]:
    """Stage a document for future extraction into a skill.

    Also submits document for skill_validation content review.
    Sync check failures return 422 (document not staged).
    """
    module = await service.get_skill(id, tenant_id)
    if not module:
        raise HTTPException(status_code=404, detail="Skill not found")

    # Submit for validation BEFORE staging
    try:
        await _submit_validation_review(
            session=session,
            document_id=stage_request.document_id,
            skill_id=id,
            tenant_id=tenant_id,
            trigger_source="stage_document",
            current_user=current_user,
        )
    except DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")
    except ContentReviewGateError:
        raise HTTPException(
            status_code=422,
            detail="Content validation failed: document did not pass safety checks",
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("validation_review_unexpected_error")
        raise HTTPException(
            status_code=500,
            detail="Internal server error",
        )

    try:
        result = await service.stage_document(
            tenant_id=tenant_id,
            skill_id=id,
            document_id=stage_request.document_id,
            namespace_path=stage_request.namespace_path,
        )
        return api_response(
            StagedDocumentResponse(
                document_id=result["document_id"],
                skill_id=result["skill_id"],
                path=result["path"],
                edge_id=result["edge_id"],
            ),
            request=request,
        )
    except DocumentNotFoundError:
        raise HTTPException(status_code=404, detail="Document not found")
    except ValueError:
        raise HTTPException(status_code=409, detail="Staged document conflict")


@router.get(
    "/{id}/staged-documents", response_model=ApiListResponse[StagedDocumentEntry]
)
async def list_staged_documents(
    request: Request,
    id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeModuleService, Depends(get_skill_service)],
) -> ApiListResponse[StagedDocumentEntry]:
    """List staged documents for a skill."""
    module = await service.get_skill(id, tenant_id)
    if not module:
        raise HTTPException(status_code=404, detail="Skill not found")

    staged = await service.get_staged_documents(tenant_id, id)
    entries = [StagedDocumentEntry.model_validate(s) for s in staged]

    return api_list_response(entries, total=len(entries), request=request)


@router.delete(
    "/{id}/staged-documents/{document_id}",
    status_code=204,
    dependencies=[Depends(require_permission("skills", "update"))],
)
async def remove_staged_document(
    id: UUID,
    document_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[KnowledgeModuleService, Depends(get_skill_service)],
) -> None:
    """Remove a staged document from a skill."""
    module = await service.get_skill(id, tenant_id)
    if not module:
        raise HTTPException(status_code=404, detail="Skill not found")

    success = await service.remove_staged_document(tenant_id, id, document_id)
    if not success:
        raise HTTPException(
            status_code=404, detail="Staged document not found for this skill"
        )


# --- Import Endpoint ---


@router.post(
    "/import",
    response_model=ApiResponse[SkillImportResponse],
    status_code=202,
    dependencies=[Depends(require_permission("skills", "create"))],
)
async def import_skill(
    request: Request,
    file: UploadFile,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
    app: str = Query("default", description="Content pack name"),
) -> ApiResponse[SkillImportResponse]:
    """Import a skill from a .skill zip file.

    The zip must contain manifest.json and SKILL.md at root.
    Returns 202 -- documents are submitted for async content review.
    """
    from analysi.services.skill_import import SkillImportError, SkillImportService

    file_content = await file.read()
    import_service = SkillImportService(session)

    try:
        result = await import_service.import_from_zip(
            file_content=file_content,
            tenant_id=tenant_id,
            actor_user_id=current_user.db_user_id,
            actor_roles=current_user.roles,
            app=app,
        )
        return api_response(result, request=request)
    except SkillImportError as exc:
        logger.warning(
            "skill_import_failed",
            extra={"error_code": exc.error_code, "error": str(exc)},
        )
        from fastapi_problem_details import ProblemResponse

        return ProblemResponse(
            status=422,
            title=exc.title,
            detail=exc.message,
            request_id=getattr(request.state, "request_id", "unknown"),
            error_code=exc.error_code,
            hint=exc.hint,
            **exc.details,
        )
    except Exception:
        logger.exception("skill_import_unexpected_error")
        raise HTTPException(status_code=500, detail="Internal server error")


# --- Maintenance Endpoints ---


@router.post(
    "/repair-edges",
    response_model=ApiResponse[RepairEdgesResponse],
    status_code=200,
    dependencies=[Depends(require_permission("skills", "update"))],
)
async def repair_skill_edges(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApiResponse[RepairEdgesResponse]:
    """
    Repair missing CONTAINS edges between Skills and their documents.

    Finds documents in skill namespaces that don't have proper edges
    and creates the missing connections.
    """
    results = await repair_missing_skill_edges(session, tenant_id)
    return api_response(RepairEdgesResponse(**results), request=request)
