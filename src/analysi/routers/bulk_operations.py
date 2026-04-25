"""Tenant-scoped bulk-delete endpoints.

Destructive operations for tenant data management, gated by owner role.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api.responses import ApiResponse, api_response
from analysi.auth.dependencies import require_permission
from analysi.config.logging import get_logger
from analysi.db.session import get_db
from analysi.models.activity_audit import ActivityAuditTrail
from analysi.models.alert import Alert, AlertAnalysis
from analysi.models.kea_coordination import (
    AlertRoutingRule,
    AnalysisGroup,
    WorkflowGeneration,
)
from analysi.models.task_run import TaskRun
from analysi.models.workflow_execution import WorkflowRun
from analysi.schemas.alert import AlertStatus, AnalysisStatus

logger = get_logger(__name__)

router = APIRouter(
    prefix="/{tenant}",
    tags=["bulk-operations"],
    dependencies=[Depends(require_permission("bulk_operations", "delete"))],
)


class BulkDeleteResponse(BaseModel):
    """Response model for bulk delete operations."""

    deleted_count: int = Field(description="Number of records deleted")
    message: str = Field(description="Operation result message")


@router.delete(
    "/task-runs",
    response_model=ApiResponse[BulkDeleteResponse],
    summary="Bulk delete task runs",
)
async def bulk_delete_task_runs(
    tenant: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    task_id: UUID | None = Query(None, description="Delete runs for specific task"),
    before: datetime | None = Query(
        None, description="Delete runs created before this date"
    ),
    after: datetime | None = Query(
        None, description="Delete runs created after this date"
    ),
    status: str | None = Query(
        None,
        description="Delete runs with specific status (e.g., 'failed', 'completed')",
    ),
) -> ApiResponse[BulkDeleteResponse]:
    """Bulk delete task runs based on filters."""
    query = delete(TaskRun).where(TaskRun.tenant_id == tenant)
    if task_id:
        query = query.where(TaskRun.task_id == task_id)
    if before:
        query = query.where(TaskRun.created_at < before)
    if after:
        query = query.where(TaskRun.created_at > after)
    if status:
        query = query.where(TaskRun.status == status)

    result = await db.execute(query)
    await db.commit()

    return api_response(
        BulkDeleteResponse(
            deleted_count=result.rowcount,
            message=f"Successfully deleted {result.rowcount} task runs",
        ),
        request=request,
    )


@router.delete(
    "/workflow-runs",
    response_model=ApiResponse[BulkDeleteResponse],
    summary="Bulk delete workflow runs",
)
async def bulk_delete_workflow_runs(
    tenant: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    workflow_id: UUID | None = Query(
        None, description="Delete runs for specific workflow"
    ),
    before: datetime | None = Query(
        None, description="Delete runs created before this date"
    ),
    after: datetime | None = Query(
        None, description="Delete runs created after this date"
    ),
    status: str | None = Query(
        None,
        description="Delete runs with specific status (e.g., 'completed', 'failed')",
    ),
) -> ApiResponse[BulkDeleteResponse]:
    """Bulk delete workflow runs based on filters."""
    query = delete(WorkflowRun).where(WorkflowRun.tenant_id == tenant)
    if workflow_id:
        query = query.where(WorkflowRun.workflow_id == workflow_id)
    if before:
        query = query.where(WorkflowRun.created_at < before)
    if after:
        query = query.where(WorkflowRun.created_at > after)
    if status:
        query = query.where(WorkflowRun.status == status)

    result = await db.execute(query)
    await db.commit()

    return api_response(
        BulkDeleteResponse(
            deleted_count=result.rowcount,
            message=f"Successfully deleted {result.rowcount} workflow runs",
        ),
        request=request,
    )


@router.delete(
    "/runs",
    response_model=ApiResponse[dict[str, BulkDeleteResponse]],
    summary="Delete all execution history",
)
async def delete_all_execution_history(
    tenant: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict[str, BulkDeleteResponse]]:
    """Delete all execution history (task runs and workflow runs) for a tenant."""
    task_result = await db.execute(delete(TaskRun).where(TaskRun.tenant_id == tenant))
    workflow_result = await db.execute(
        delete(WorkflowRun).where(WorkflowRun.tenant_id == tenant)
    )
    await db.commit()

    return api_response(
        {
            "task_runs": BulkDeleteResponse(
                deleted_count=task_result.rowcount,
                message=f"Deleted {task_result.rowcount} task runs",
            ),
            "workflow_runs": BulkDeleteResponse(
                deleted_count=workflow_result.rowcount,
                message=f"Deleted {workflow_result.rowcount} workflow runs",
            ),
        },
        request=request,
    )


@router.delete(
    "/analysis-groups",
    response_model=ApiResponse[BulkDeleteResponse],
    summary="Bulk delete analysis groups",
)
async def bulk_delete_analysis_groups(
    tenant: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    before: datetime | None = Query(
        None, description="Delete groups created before this date"
    ),
    after: datetime | None = Query(
        None, description="Delete groups created after this date"
    ),
) -> ApiResponse[BulkDeleteResponse]:
    """Bulk delete analysis groups (cascades to workflow_generations and routing rules)."""
    query = delete(AnalysisGroup).where(AnalysisGroup.tenant_id == tenant)
    if before:
        query = query.where(AnalysisGroup.created_at < before)
    if after:
        query = query.where(AnalysisGroup.created_at > after)

    result = await db.execute(query)
    await db.commit()

    return api_response(
        BulkDeleteResponse(
            deleted_count=result.rowcount,
            message=f"Successfully deleted {result.rowcount} analysis groups",
        ),
        request=request,
    )


@router.delete(
    "/workflow-generations",
    response_model=ApiResponse[BulkDeleteResponse],
    summary="Bulk delete workflow generations",
)
async def bulk_delete_workflow_generations(
    tenant: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    analysis_group_id: UUID | None = Query(
        None, description="Delete generations for specific analysis group"
    ),
    status: str | None = Query(None, description="Filter by status"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    before: datetime | None = Query(None, description="Delete before this date"),
    after: datetime | None = Query(None, description="Delete after this date"),
) -> ApiResponse[BulkDeleteResponse]:
    """Bulk delete workflow generations based on filters."""
    query = delete(WorkflowGeneration).where(WorkflowGeneration.tenant_id == tenant)
    if analysis_group_id:
        query = query.where(WorkflowGeneration.analysis_group_id == analysis_group_id)
    if status:
        query = query.where(WorkflowGeneration.status == status)
    if is_active is not None:
        query = query.where(WorkflowGeneration.is_active == is_active)
    if before:
        query = query.where(WorkflowGeneration.created_at < before)
    if after:
        query = query.where(WorkflowGeneration.created_at > after)

    result = await db.execute(query)
    await db.commit()

    return api_response(
        BulkDeleteResponse(
            deleted_count=result.rowcount,
            message=f"Successfully deleted {result.rowcount} workflow generations",
        ),
        request=request,
    )


@router.delete(
    "/alert-routing-rules",
    response_model=ApiResponse[BulkDeleteResponse],
    summary="Bulk delete alert routing rules",
)
async def bulk_delete_alert_routing_rules(
    tenant: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    analysis_group_id: UUID | None = Query(
        None, description="Filter by analysis group"
    ),
    workflow_id: UUID | None = Query(None, description="Filter by workflow"),
    before: datetime | None = Query(None, description="Delete before this date"),
    after: datetime | None = Query(None, description="Delete after this date"),
) -> ApiResponse[BulkDeleteResponse]:
    """Bulk delete alert routing rules based on filters."""
    query = delete(AlertRoutingRule).where(AlertRoutingRule.tenant_id == tenant)
    if analysis_group_id:
        query = query.where(AlertRoutingRule.analysis_group_id == analysis_group_id)
    if workflow_id:
        query = query.where(AlertRoutingRule.workflow_id == workflow_id)
    if before:
        query = query.where(AlertRoutingRule.created_at < before)
    if after:
        query = query.where(AlertRoutingRule.created_at > after)

    result = await db.execute(query)
    await db.commit()

    return api_response(
        BulkDeleteResponse(
            deleted_count=result.rowcount,
            message=f"Successfully deleted {result.rowcount} alert routing rules",
        ),
        request=request,
    )


@router.delete(
    "/alert-analyses",
    response_model=ApiResponse[BulkDeleteResponse],
    summary="Bulk delete alert analyses",
)
async def bulk_delete_alert_analyses(
    tenant: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    alert_id: UUID | None = Query(None, description="Filter by alert"),
    workflow_id: UUID | None = Query(None, description="Filter by workflow"),
    status: str | None = Query(None, description="Filter by status"),
    before: datetime | None = Query(None, description="Delete before this date"),
    after: datetime | None = Query(None, description="Delete after this date"),
) -> ApiResponse[BulkDeleteResponse]:
    """Bulk delete alert analyses based on filters."""
    query = delete(AlertAnalysis).where(AlertAnalysis.tenant_id == tenant)
    if alert_id:
        query = query.where(AlertAnalysis.alert_id == alert_id)
    if workflow_id:
        query = query.where(AlertAnalysis.workflow_id == workflow_id)
    if status:
        query = query.where(AlertAnalysis.status == status)
    if before:
        query = query.where(AlertAnalysis.created_at < before)
    if after:
        query = query.where(AlertAnalysis.created_at > after)

    result = await db.execute(query)
    await db.commit()

    return api_response(
        BulkDeleteResponse(
            deleted_count=result.rowcount,
            message=f"Successfully deleted {result.rowcount} alert analyses",
        ),
        request=request,
    )


@router.delete(
    "/audit-trail",
    response_model=ApiResponse[BulkDeleteResponse],
    summary="Bulk delete audit trail entries",
)
async def bulk_delete_audit_trail(
    tenant: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor_id: str | None = Query(None, description="Filter by actor"),
    source: str | None = Query(None, description="Filter by source"),
    action: str | None = Query(None, description="Filter by action"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    before: datetime | None = Query(None, description="Delete before this date"),
    after: datetime | None = Query(None, description="Delete after this date"),
) -> ApiResponse[BulkDeleteResponse]:
    """Bulk delete audit trail entries based on filters."""
    query = delete(ActivityAuditTrail).where(ActivityAuditTrail.tenant_id == tenant)
    if actor_id:
        query = query.where(ActivityAuditTrail.actor_id == actor_id)
    if source:
        query = query.where(ActivityAuditTrail.source == source)
    if action:
        query = query.where(ActivityAuditTrail.action == action)
    if resource_type:
        query = query.where(ActivityAuditTrail.resource_type == resource_type)
    if before:
        query = query.where(ActivityAuditTrail.created_at < before)
    if after:
        query = query.where(ActivityAuditTrail.created_at > after)

    result = await db.execute(query)
    await db.commit()

    return api_response(
        BulkDeleteResponse(
            deleted_count=result.rowcount,
            message=f"Successfully deleted {result.rowcount} audit trail entries",
        ),
        request=request,
    )


class QueueCleanupResponse(BaseModel):
    """Response model for queue cleanup operations."""

    queued_jobs_removed: int = Field(description="Number of queued jobs removed")
    in_progress_jobs_aborted: int = Field(
        description="Number of in-progress jobs aborted"
    )
    alerts_marked_failed: int = Field(description="Number of alerts marked as failed")
    analyses_marked_failed: int = Field(
        description="Number of analyses marked as failed"
    )
    workflow_generations_reset: int = Field(
        default=0, description="Number of workflow generations reset"
    )
    routing_rules_deleted: int = Field(
        default=0, description="Number of alert routing rules deleted"
    )
    errors: list[str] = Field(
        default_factory=list, description="Any errors encountered"
    )
    message: str = Field(description="Operation result message")


@router.delete(
    "/analysis-queue",
    response_model=ApiResponse[QueueCleanupResponse],
    summary="Purge analysis queue for tenant",
)
async def purge_tenant_analysis_queue(
    tenant: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    abort_in_progress: bool = Query(False, description="Also abort in-progress jobs"),
    mark_alerts_failed: bool = Query(
        True, description="Mark pending/running alerts and analyses as failed"
    ),
    reset_workflow_mappings: bool = Query(
        False,
        description="Reset workflow mappings (clears workflow_id, deletes routing rules)",
    ),
) -> ApiResponse[QueueCleanupResponse]:
    """Purge all queued alert analysis jobs for a tenant."""
    from analysi.alert_analysis.queue_cleanup import purge_tenant_queue
    from analysi.config.valkey_db import ValkeyDBConfig

    errors: list[str] = []
    alerts_failed = 0
    analyses_failed = 0

    # 1. Purge jobs from ARQ queue
    try:
        redis_settings = ValkeyDBConfig.get_redis_settings(
            database=ValkeyDBConfig.ALERT_PROCESSING_DB
        )
        cleanup_result = await purge_tenant_queue(
            redis_settings=redis_settings,
            tenant_id=tenant,
            abort_in_progress=abort_in_progress,
        )
        errors.extend(cleanup_result.errors)
    except Exception:
        logger.exception("Queue purge failed for tenant %s", tenant)
        raise HTTPException(status_code=500, detail="Queue purge failed")

    # 2. Mark pending/running alerts and analyses as failed
    if mark_alerts_failed:
        try:
            analysis_result = await db.execute(
                update(AlertAnalysis)
                .where(AlertAnalysis.tenant_id == tenant)
                .where(
                    AlertAnalysis.status.in_(
                        [
                            AnalysisStatus.RUNNING.value,
                            AnalysisStatus.PAUSED_WORKFLOW_BUILDING.value,
                        ]
                    )
                )
                .values(
                    status=AnalysisStatus.FAILED.value,
                    error_message="Analysis cancelled: queue purged by admin",
                )
            )
            analyses_failed = analysis_result.rowcount

            alert_result = await db.execute(
                update(Alert)
                .where(Alert.tenant_id == tenant)
                .where(
                    Alert.analysis_status.in_(
                        [AlertStatus.NEW.value, AlertStatus.IN_PROGRESS.value]
                    )
                )
                .values(analysis_status=AlertStatus.FAILED.value)
            )
            alerts_failed = alert_result.rowcount
            await db.commit()
        except Exception as e:
            logger.error("failed_to_mark_alerts_as_failed", tenant=tenant, error=str(e))
            errors.append(f"Database update failed: {e!s}")

    # 3. Reset workflow mappings if requested
    workflow_generations_reset = 0
    routing_rules_deleted = 0

    if reset_workflow_mappings:
        try:
            from analysi.alert_analysis.steps.workflow_builder import (
                invalidate_global_cache,
            )

            gen_result = await db.execute(
                update(WorkflowGeneration)
                .where(WorkflowGeneration.tenant_id == tenant)
                .where(WorkflowGeneration.workflow_id.isnot(None))
                .values(workflow_id=None, status="invalidated")
            )
            workflow_generations_reset = gen_result.rowcount

            rule_result = await db.execute(
                delete(AlertRoutingRule).where(AlertRoutingRule.tenant_id == tenant)
            )
            routing_rules_deleted = rule_result.rowcount
            await db.commit()
            invalidate_global_cache()
        except Exception as e:
            logger.error(
                "failed_to_reset_workflow_mappings", tenant=tenant, error=str(e)
            )
            errors.append(f"Workflow mapping reset failed: {e!s}")

    total_cleaned = (
        cleanup_result.queued_jobs_removed
        + cleanup_result.in_progress_jobs_aborted
        + alerts_failed
        + workflow_generations_reset
        + routing_rules_deleted
    )

    return api_response(
        QueueCleanupResponse(
            queued_jobs_removed=cleanup_result.queued_jobs_removed,
            in_progress_jobs_aborted=cleanup_result.in_progress_jobs_aborted,
            alerts_marked_failed=alerts_failed,
            analyses_marked_failed=analyses_failed,
            workflow_generations_reset=workflow_generations_reset,
            routing_rules_deleted=routing_rules_deleted,
            errors=errors,
            message=f"Purged {total_cleaned} items for tenant {tenant}",
        ),
        request=request,
    )
