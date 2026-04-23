"""REST API for task feedback management (Project Zakynthos).

Nested under tasks: /{tenant}/tasks/{task_component_id}/feedback
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api import ApiListResponse, ApiResponse, api_list_response, api_response
from analysi.auth.dependencies import require_current_user, require_permission
from analysi.auth.messages import INSUFFICIENT_PERMISSIONS
from analysi.auth.models import CurrentUser
from analysi.auth.permissions import has_permission
from analysi.config.logging import get_logger
from analysi.db.session import get_db
from analysi.dependencies.audit import get_audit_context
from analysi.dependencies.tenant import get_tenant_id
from analysi.models.knowledge_unit import KUDocument
from analysi.schemas.audit_context import AuditContext
from analysi.schemas.task_feedback import (
    TaskFeedbackCreate,
    TaskFeedbackResponse,
    TaskFeedbackUpdate,
)
from analysi.services.task_feedback import TaskFeedbackService

logger = get_logger(__name__)

SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

router = APIRouter(
    prefix="/{tenant}/tasks/{task_component_id}/feedback",
    tags=["task-feedback"],
    dependencies=[Depends(require_permission("tasks", "read"))],
)


async def _get_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TaskFeedbackService:
    return TaskFeedbackService(session)


def _check_feedback_ownership(
    doc: KUDocument,
    current_user: CurrentUser,
) -> None:
    """Raise 403 if user is not the feedback owner and not an admin.

    Ownership: Component.created_by == current_user.db_user_id.
    platform_admin and admin/owner roles bypass the ownership check.
    """
    if current_user.is_platform_admin:
        return

    is_owner = (
        current_user.db_user_id is not None
        and doc.component.created_by == current_user.db_user_id
    )
    is_admin = has_permission(current_user.roles, "tasks", "delete")
    if not is_owner and not is_admin:
        logger.warning(
            "task_feedback_ownership_denied",
            feedback_id=str(doc.component.id),
            actor_id=str(current_user.db_user_id),
            owner_id=str(doc.component.created_by),
        )
        raise HTTPException(status_code=403, detail=INSUFFICIENT_PERMISSIONS)


def _build_response(doc: KUDocument, task_component_id: UUID) -> TaskFeedbackResponse:
    """Build a flattened TaskFeedbackResponse from a KUDocument + Component."""
    return TaskFeedbackResponse(
        id=doc.component.id,
        tenant_id=doc.component.tenant_id,
        task_component_id=task_component_id,
        title=doc.component.name,
        feedback=doc.content,
        metadata=doc.doc_metadata or {},
        status=doc.component.status,
        created_by=doc.component.created_by,
        created_at=doc.component.created_at,
        updated_at=doc.component.updated_at,
    )


@router.post(
    "",
    response_model=ApiResponse[TaskFeedbackResponse],
    status_code=201,
    dependencies=[Depends(require_permission("tasks", "update"))],
)
async def create_task_feedback(
    request: Request,
    task_component_id: UUID,
    body: TaskFeedbackCreate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TaskFeedbackService, Depends(_get_service)],
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
) -> ApiResponse[TaskFeedbackResponse]:
    """Create a feedback entry for a task."""
    try:
        doc = await service.create_feedback(
            tenant_id=tenant_id,
            task_component_id=task_component_id,
            feedback_text=body.feedback,
            created_by=audit_context.actor_user_id or SYSTEM_USER_ID,
            metadata=body.metadata,
            audit_context=audit_context,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Task not found")

    await service.session.commit()
    return api_response(
        _build_response(doc, task_component_id),
        request=request,
    )


@router.get("", response_model=ApiListResponse[TaskFeedbackResponse])
async def list_task_feedback(
    request: Request,
    task_component_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TaskFeedbackService, Depends(_get_service)],
) -> ApiListResponse[TaskFeedbackResponse]:
    """List all active feedback entries for a task."""
    docs = await service.list_active_feedback(tenant_id, task_component_id)
    items = [_build_response(doc, task_component_id) for doc in docs]
    return api_list_response(items, total=len(items), request=request)


@router.get("/{feedback_id}", response_model=ApiResponse[TaskFeedbackResponse])
async def get_task_feedback(
    request: Request,
    task_component_id: UUID,
    feedback_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TaskFeedbackService, Depends(_get_service)],
) -> ApiResponse[TaskFeedbackResponse]:
    """Get a single feedback entry."""
    doc = await service.get_feedback(tenant_id, feedback_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return api_response(
        _build_response(doc, task_component_id),
        request=request,
    )


@router.patch(
    "/{feedback_id}",
    response_model=ApiResponse[TaskFeedbackResponse],
    dependencies=[Depends(require_permission("tasks", "update"))],
)
async def update_task_feedback(
    request: Request,
    task_component_id: UUID,
    feedback_id: UUID,
    body: TaskFeedbackUpdate,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TaskFeedbackService, Depends(_get_service)],
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
) -> ApiResponse[TaskFeedbackResponse]:
    """Update feedback text and/or metadata.

    Only the feedback owner or an admin can update feedback.
    """
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    # Ownership check: load feedback, verify caller is owner or admin
    existing = await service.get_feedback(tenant_id, feedback_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    _check_feedback_ownership(existing, current_user)

    doc = await service.update_feedback(
        tenant_id=tenant_id,
        feedback_component_id=feedback_id,
        feedback_text=body.feedback,
        metadata=body.metadata,
        audit_context=audit_context,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Feedback not found")

    await service.session.commit()
    return api_response(
        _build_response(doc, task_component_id),
        request=request,
    )


@router.delete(
    "/{feedback_id}",
    status_code=204,
    dependencies=[Depends(require_permission("tasks", "update"))],
)
async def delete_task_feedback(
    task_component_id: UUID,
    feedback_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[TaskFeedbackService, Depends(_get_service)],
    audit_context: Annotated[AuditContext, Depends(get_audit_context)],
    current_user: Annotated[CurrentUser, Depends(require_current_user)],
) -> None:
    """Soft-delete a feedback entry (sets status to disabled).

    Only the feedback owner or an admin can delete feedback.
    """
    # Ownership check: load feedback, verify caller is owner or admin
    existing = await service.get_feedback(tenant_id, feedback_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    _check_feedback_ownership(existing, current_user)

    deleted = await service.deactivate_feedback(
        tenant_id, feedback_id, audit_context=audit_context
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Feedback not found")
    await service.session.commit()
