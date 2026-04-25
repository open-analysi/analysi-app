"""Kea Coordination API endpoints."""

from typing import Annotated
from uuid import UUID

from arq import create_pool
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api.responses import (
    ApiListResponse,
    ApiResponse,
    api_list_response,
    api_response,
)
from analysi.auth.dependencies import require_permission
from analysi.config.logging import get_logger
from analysi.config.valkey_db import ValkeyDBConfig
from analysi.db.session import get_db
from analysi.dependencies.tenant import get_tenant_id
from analysi.repositories.alert_repository import AlertRepository
from analysi.repositories.kea_coordination_repository import (
    AlertRoutingRuleRepository,
    AnalysisGroupRepository,
    WorkflowGenerationRepository,
)
from analysi.schemas.kea_coordination import (
    ActiveWorkflowResponse,
    AlertRoutingRuleCreate,
    AlertRoutingRuleResponse,
    AnalysisGroupCreate,
    AnalysisGroupResponse,
    AnalysisGroupWithGenerationResponse,
    GenerationSummary,
    ResumePausedAlertsResponse,
    WorkflowGenerationProgressUpdate,
    WorkflowGenerationResponse,
    WorkflowGenerationUpdateResults,
)
from analysi.services.kea_coordination_service import (
    AlertRoutingRuleService,
    AnalysisGroupService,
    WorkflowGenerationService,
)

logger = get_logger(__name__)

router = APIRouter(
    prefix="/{tenant}",
    tags=["alert-routing"],
    dependencies=[Depends(require_permission("workflows", "read"))],
)


# Dependency injection functions
async def get_analysis_group_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AnalysisGroupService:
    """Dependency injection for AnalysisGroupService."""
    group_repo = AnalysisGroupRepository(session)
    generation_repo = WorkflowGenerationRepository(session)
    rule_repo = AlertRoutingRuleRepository(session)
    return AnalysisGroupService(group_repo, generation_repo, rule_repo)


async def get_workflow_generation_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> WorkflowGenerationService:
    """Dependency injection for WorkflowGenerationService."""
    generation_repo = WorkflowGenerationRepository(session)
    return WorkflowGenerationService(generation_repo)


async def get_alert_routing_rule_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AlertRoutingRuleService:
    """Dependency injection for AlertRoutingRuleService."""
    rule_repo = AlertRoutingRuleRepository(session)
    return AlertRoutingRuleService(rule_repo)


# Analysis Group Endpoints
@router.post(
    "/analysis-groups",
    response_model=ApiResponse[AnalysisGroupResponse],
    status_code=201,
    dependencies=[Depends(require_permission("workflows", "create"))],
)
async def create_analysis_group(
    group_data: AnalysisGroupCreate,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[AnalysisGroupService, Depends(get_analysis_group_service)],
) -> ApiResponse[AnalysisGroupResponse]:
    """Create a new analysis group."""
    try:
        group = await service.create_group(tenant_id=tenant_id, title=group_data.title)
        return api_response(
            AnalysisGroupResponse.model_validate(group), request=request
        )
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail=f"Analysis group with title '{group_data.title}' already exists for this tenant",
        )


@router.get(
    "/analysis-groups/active-workflow",
    response_model=ApiResponse[ActiveWorkflowResponse],
)
async def get_active_workflow_by_title(
    title: str,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    group_service: Annotated[AnalysisGroupService, Depends(get_analysis_group_service)],
    routing_service: Annotated[
        AlertRoutingRuleService, Depends(get_alert_routing_rule_service)
    ],
    generation_service: Annotated[
        WorkflowGenerationService, Depends(get_workflow_generation_service)
    ],
) -> ApiResponse[ActiveWorkflowResponse]:
    """
    Get active workflow for an analysis group by title.

    Used by reconciliation job to check if workflows are ready for paused alerts.
    Looks up the analysis group by title first, then returns workflow status.

    Returns empty response (no routing_rule, no generation) if group doesn't exist.
    """
    # Look up group by title first
    group = await group_service.get_group_by_title(tenant_id=tenant_id, title=title)
    if not group:
        # Group doesn't exist yet - return empty response
        return api_response(
            ActiveWorkflowResponse(routing_rule=None, generation=None),
            request=request,
        )

    # Now get workflow status using the group ID
    routing_rule = await routing_service.get_rule_by_group(
        tenant_id=tenant_id, analysis_group_id=group.id
    )

    latest_generation = await generation_service.get_latest_generation_for_group(
        tenant_id=tenant_id, analysis_group_id=group.id
    )

    generation_summary = None
    if latest_generation:
        generation_summary = GenerationSummary(
            id=latest_generation.id,
            analysis_group_id=latest_generation.analysis_group_id,
            status=latest_generation.status,
            workflow_id=latest_generation.workflow_id,
        )

    return api_response(
        ActiveWorkflowResponse(
            routing_rule=AlertRoutingRuleResponse.model_validate(routing_rule)
            if routing_rule
            else None,
            generation=generation_summary,
        ),
        request=request,
    )


@router.get(
    "/analysis-groups/{group_id}", response_model=ApiResponse[AnalysisGroupResponse]
)
async def get_analysis_group(
    group_id: UUID,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[AnalysisGroupService, Depends(get_analysis_group_service)],
) -> ApiResponse[AnalysisGroupResponse]:
    """Get an analysis group by ID."""
    group = await service.get_group_by_id(tenant_id=tenant_id, group_id=group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Analysis group not found")
    return api_response(AnalysisGroupResponse.model_validate(group), request=request)


@router.get("/analysis-groups", response_model=ApiListResponse[AnalysisGroupResponse])
async def list_analysis_groups(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[AnalysisGroupService, Depends(get_analysis_group_service)],
) -> ApiListResponse[AnalysisGroupResponse]:
    """List all analysis groups for a tenant."""
    groups = await service.list_groups(tenant_id=tenant_id)
    group_responses = [AnalysisGroupResponse.model_validate(g) for g in groups]

    total = len(group_responses)
    return api_list_response(
        group_responses,
        total=total,
        request=request,
    )


@router.delete(
    "/analysis-groups/{group_id}",
    status_code=204,
    dependencies=[Depends(require_permission("workflows", "delete"))],
)
async def delete_analysis_group(
    group_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[AnalysisGroupService, Depends(get_analysis_group_service)],
) -> None:
    """Delete an analysis group by ID."""
    deleted = await service.delete_group(tenant_id=tenant_id, group_id=group_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Analysis group not found")


# Atomic Group + Generation Creation
@router.post(
    "/analysis-groups/with-workflow-generation",
    response_model=ApiResponse[AnalysisGroupWithGenerationResponse],
    status_code=201,
    dependencies=[Depends(require_permission("workflows", "create"))],
)
async def create_group_with_generation(
    group_data: AnalysisGroupCreate,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[AnalysisGroupService, Depends(get_analysis_group_service)],
) -> ApiResponse[AnalysisGroupWithGenerationResponse]:
    """
    Atomically create analysis group + workflow generation.

    Handles race conditions where multiple workers try to create the same group.
    If group already exists, returns existing group and its active generation.
    """
    group, generation = await service.create_group_with_generation(
        tenant_id=tenant_id,
        title=group_data.title,
        triggering_alert_analysis_id=group_data.triggering_alert_analysis_id,
    )
    return api_response(
        AnalysisGroupWithGenerationResponse(
            analysis_group=AnalysisGroupResponse.model_validate(group),
            workflow_generation=WorkflowGenerationResponse.model_validate(generation),
        ),
        request=request,
    )


@router.post(
    "/analysis-groups/{group_id}/resume-paused-alerts",
    response_model=ApiResponse[ResumePausedAlertsResponse],
    dependencies=[Depends(require_permission("workflows", "execute"))],
)
async def resume_paused_alerts(
    group_id: UUID,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
    group_service: Annotated[AnalysisGroupService, Depends(get_analysis_group_service)],
) -> ApiResponse[ResumePausedAlertsResponse]:
    """
    Resume all paused alerts waiting for this analysis group's workflow.

    Push-based resume: Called by workflow_generation_job AFTER creating
    the routing rule. This eliminates the need to wait for reconciliation polling.

    Flow:
    1. Get analysis group to find its title (rule_name)
    2. Find all alerts paused at 'paused_workflow_building' with matching rule_name
    3. For each alert, atomically transition to 'running' and enqueue for processing
    4. Return count of resumed alerts

    Race Safety: Uses atomic try_resume_alert() - only one caller wins per alert.
    """
    # Get analysis group
    group = await group_service.get_group_by_id(tenant_id=tenant_id, group_id=group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Analysis group not found")

    # Create AlertRepository for this session
    alert_repo = AlertRepository(session)

    # Find paused alerts for this group's rule_name
    paused_alerts = await alert_repo.find_paused_alerts_by_rule_name(
        tenant_id=tenant_id,
        rule_name=group.title,
    )

    if not paused_alerts:
        logger.info(
            "no_paused_alerts_found_for_group_title",
            group_id=group_id,
            title=group.title,
        )
        return api_response(
            ResumePausedAlertsResponse(
                resumed_count=0,
                skipped_count=0,
                alert_ids=[],
            ),
            request=request,
        )

    logger.info(
        "found_paused_alerts_to_resume_for_group",
        paused_alerts_count=len(paused_alerts),
        group_id=group_id,
    )

    # Create Redis pool for enqueueing
    redis_settings = ValkeyDBConfig.get_redis_settings(
        database=ValkeyDBConfig.ALERT_PROCESSING_DB
    )
    redis = await create_pool(redis_settings)

    try:
        resumed_count = 0
        skipped_count = 0
        resumed_alert_ids = []

        for alert in paused_alerts:
            # Try to resume atomically (first-come-first-serve)
            success = await alert_repo.try_resume_alert(
                tenant_id=tenant_id,
                alert_id=str(alert.id),
            )

            if success:
                # Enqueue for processing
                await redis.enqueue_job(
                    "analysi.alert_analysis.worker.process_alert_analysis",
                    tenant_id,
                    str(alert.id),
                    str(alert.current_analysis_id),  # Resume existing analysis
                )
                resumed_count += 1
                resumed_alert_ids.append(str(alert.id))
                logger.info("resumed_alert_pushbased", alert_id=alert.id)
            else:
                # Another worker already resumed this alert
                skipped_count += 1
                logger.debug(
                    "alert_already_resumed_by_another_worker", alert_id=alert.id
                )

        logger.info(
            "push_based_resume_complete",
            group_id=str(group_id),
            resumed_count=resumed_count,
            skipped_count=skipped_count,
        )

        return api_response(
            ResumePausedAlertsResponse(
                resumed_count=resumed_count,
                skipped_count=skipped_count,
                alert_ids=resumed_alert_ids,
            ),
            request=request,
        )

    finally:
        await redis.aclose()


# Workflow Generation Endpoints
@router.get(
    "/workflow-generations", response_model=ApiListResponse[WorkflowGenerationResponse]
)
async def list_workflow_generations(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[
        WorkflowGenerationService, Depends(get_workflow_generation_service)
    ],
    triggering_alert_analysis_id: UUID | None = None,
) -> ApiListResponse[WorkflowGenerationResponse]:
    """List workflow generations for a tenant, optionally filtered by triggering alert."""
    generations = await service.list_generations(
        tenant_id=tenant_id,
        triggering_alert_analysis_id=triggering_alert_analysis_id,
    )
    generation_responses = [
        WorkflowGenerationResponse.model_validate(g) for g in generations
    ]

    total = len(generation_responses)
    return api_list_response(
        generation_responses,
        total=total,
        request=request,
    )


@router.get(
    "/workflow-generations/{generation_id}",
    response_model=ApiResponse[WorkflowGenerationResponse],
)
async def get_workflow_generation(
    generation_id: UUID,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[
        WorkflowGenerationService, Depends(get_workflow_generation_service)
    ],
) -> ApiResponse[WorkflowGenerationResponse]:
    """Get a workflow generation by ID."""
    generation = await service.get_generation_by_id(
        tenant_id=tenant_id, generation_id=generation_id
    )
    if not generation:
        raise HTTPException(status_code=404, detail="Workflow generation not found")
    return api_response(
        WorkflowGenerationResponse.model_validate(generation), request=request
    )


@router.patch(
    "/workflow-generations/{generation_id}/progress",
    response_model=ApiResponse[WorkflowGenerationResponse],
    dependencies=[Depends(require_permission("workflows", "update"))],
)
async def update_workflow_generation_progress(
    generation_id: UUID,
    progress_data: WorkflowGenerationProgressUpdate,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[
        WorkflowGenerationService, Depends(get_workflow_generation_service)
    ],
) -> ApiResponse[WorkflowGenerationResponse]:
    """
    Update workflow generation progress with pre-populated phases.

    All 4 phases are initialized upfront so the UI knows what to expect.
    When a stage is provided, it's marked as in_progress and all previous
    stages are automatically marked as completed.

    Example progression:
    - PATCH {stage: "runbook_generation"}
      → runbook_generation: in_progress, others: not_started
    - PATCH {stage: "task_proposals"}
      → runbook_generation: completed, task_proposals: in_progress, others: not_started
    """
    generation = await service.update_generation_progress(
        tenant_id=tenant_id,
        generation_id=generation_id,
        stage=progress_data.stage.value if progress_data.stage else None,
        tasks_count=progress_data.tasks_count,
        workspace_path=progress_data.workspace_path,
    )

    if not generation:
        raise HTTPException(status_code=404, detail="Workflow generation not found")

    return api_response(
        WorkflowGenerationResponse.model_validate(generation), request=request
    )


@router.put(
    "/workflow-generations/{generation_id}/results",
    response_model=ApiResponse[WorkflowGenerationResponse],
    dependencies=[Depends(require_permission("workflows", "update"))],
)
async def update_workflow_generation_results(
    generation_id: UUID,
    update_data: WorkflowGenerationUpdateResults,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[
        WorkflowGenerationService, Depends(get_workflow_generation_service)
    ],
) -> ApiResponse[WorkflowGenerationResponse]:
    """Update workflow generation with orchestration results (consolidated JSONB field)."""
    generation = await service.update_generation_results(
        tenant_id=tenant_id,
        generation_id=generation_id,
        workflow_id=update_data.workflow_id,
        status=update_data.status.value,
        orchestration_results=update_data.orchestration_results,
        workspace_path=update_data.workspace_path,
    )

    if not generation:
        raise HTTPException(status_code=404, detail="Workflow generation not found")

    return api_response(
        WorkflowGenerationResponse.model_validate(generation), request=request
    )


@router.delete(
    "/workflow-generations/{generation_id}",
    status_code=204,
    dependencies=[Depends(require_permission("workflows", "delete"))],
)
async def delete_workflow_generation(
    generation_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[
        WorkflowGenerationService, Depends(get_workflow_generation_service)
    ],
) -> None:
    """Delete a workflow generation by ID."""
    deleted = await service.delete_generation(
        tenant_id=tenant_id, generation_id=generation_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow generation not found")


# Alert Routing Rule Endpoints
@router.get(
    "/alert-routing-rules", response_model=ApiListResponse[AlertRoutingRuleResponse]
)
async def list_alert_routing_rules(
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[
        AlertRoutingRuleService, Depends(get_alert_routing_rule_service)
    ],
) -> ApiListResponse[AlertRoutingRuleResponse]:
    """List all alert routing rules for a tenant."""
    rules = await service.list_rules(tenant_id=tenant_id)
    rule_responses = [AlertRoutingRuleResponse.model_validate(r) for r in rules]

    total = len(rule_responses)
    return api_list_response(
        rule_responses,
        total=total,
        request=request,
    )


@router.post(
    "/alert-routing-rules",
    response_model=ApiResponse[AlertRoutingRuleResponse],
    status_code=201,
    dependencies=[Depends(require_permission("workflows", "create"))],
)
async def create_alert_routing_rule(
    rule_data: AlertRoutingRuleCreate,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[
        AlertRoutingRuleService, Depends(get_alert_routing_rule_service)
    ],
) -> ApiResponse[AlertRoutingRuleResponse]:
    """Create a new alert routing rule.

    Multiple rules can be created for the same analysis group to support
    A/B testing or multi-workflow scenarios.
    """
    rule = await service.create_rule(
        tenant_id=tenant_id,
        analysis_group_id=rule_data.analysis_group_id,
        workflow_id=rule_data.workflow_id,
    )
    return api_response(AlertRoutingRuleResponse.model_validate(rule), request=request)


@router.get(
    "/alert-routing-rules/{rule_id}",
    response_model=ApiResponse[AlertRoutingRuleResponse],
)
async def get_alert_routing_rule(
    rule_id: UUID,
    request: Request,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[
        AlertRoutingRuleService, Depends(get_alert_routing_rule_service)
    ],
) -> ApiResponse[AlertRoutingRuleResponse]:
    """Get an alert routing rule by ID."""
    rule = await service.get_rule_by_id(tenant_id=tenant_id, rule_id=rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Alert routing rule not found")
    return api_response(AlertRoutingRuleResponse.model_validate(rule), request=request)


@router.delete(
    "/alert-routing-rules/{rule_id}",
    status_code=204,
    dependencies=[Depends(require_permission("workflows", "delete"))],
)
async def delete_alert_routing_rule(
    rule_id: UUID,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    service: Annotated[
        AlertRoutingRuleService, Depends(get_alert_routing_rule_service)
    ],
) -> None:
    """Delete an alert routing rule by ID."""
    deleted = await service.delete_rule(tenant_id=tenant_id, rule_id=rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Alert routing rule not found")
