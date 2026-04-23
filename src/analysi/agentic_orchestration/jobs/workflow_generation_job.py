"""ARQ job for workflow generation with database tracking."""

from datetime import UTC, datetime
from typing import Any

import httpx
from httpx import HTTPStatusError, TimeoutException
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from analysi.agentic_orchestration import (
    StageExecutionMetrics,
    TaskGenerationApiClient,
    WorkflowGenerationStage,
    create_executor,
)
from analysi.agentic_orchestration.orchestrator import run_orchestration_with_stages
from analysi.agentic_orchestration.skills_sync import TenantSkillsSyncer
from analysi.agentic_orchestration.stages import StageStrategyProvider
from analysi.alert_analysis.config import AlertAnalysisConfig
from analysi.common.internal_auth import internal_auth_headers
from analysi.common.internal_client import InternalAsyncClient
from analysi.common.job_tracking import tracked_job
from analysi.config.logging import get_logger
from analysi.db.session import AsyncSessionLocal
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.kea_coordination import WorkflowGeneration
from analysi.repositories.integration_repository import IntegrationRepository
from analysi.schemas.alert import AlertBase
from analysi.schemas.kea_coordination import WorkflowGenerationStatus
from analysi.services.agent_credential_factory import AgentCredentialFactory
from analysi.services.integration_service import IntegrationService

logger = get_logger(__name__)


class DatabaseProgressCallback:
    """Callback that updates workflow_generation.current_phase via REST API.

    Implements ProgressCallback protocol to track orchestration progress.
    Updates are best-effort - failures are logged but don't fail the job.
    """

    def __init__(self, api_base_url: str, tenant_id: str, generation_id: str):
        """Initialize callback with database connection info.

        Args:
            api_base_url: Base URL for REST API (e.g., "http://api:8000")
            tenant_id: Tenant identifier
            generation_id: WorkflowGeneration UUID being tracked
        """
        self.api_base_url = api_base_url
        self.tenant_id = tenant_id
        self.generation_id = generation_id

    async def on_stage_start(
        self, stage: WorkflowGenerationStage, metadata: dict[str, Any]
    ) -> None:
        """Update database when stage starts."""
        try:
            await _update_progress(
                api_base_url=self.api_base_url,
                tenant_id=self.tenant_id,
                generation_id=self.generation_id,
                stage=stage.value,
                tasks_count=metadata.get("tasks_count"),
            )
        except Exception as e:
            # Best-effort logging - don't fail job on progress update errors
            logger.warning(
                "progress_update_failed",
                stage=stage.value,
                error=str(e),
                exc_info=True,
            )

    async def on_stage_complete(
        self,
        stage: WorkflowGenerationStage,
        result: Any,
        metrics: StageExecutionMetrics,
    ) -> None:
        """Stage completed - no action needed.

        Stage completion is implicit: when the next stage starts via on_stage_start(),
        all previous stages are automatically marked as completed by the /progress API.
        Final status is set via the /results API when the job finishes.
        """
        # No-op: completion is handled implicitly by /progress when next stage starts
        logger.debug(
            "stage_completed_implicitly",
            stage=stage.value,
        )

    async def on_stage_error(
        self,
        stage: WorkflowGenerationStage,
        error: Exception,
        partial_result: Any = None,
    ) -> None:
        """Stage failed - error will be captured by job exception handler."""
        # Errors are handled by execute_workflow_generation's try/except
        # which updates orchestration_results with error details
        logger.error("stage_failed", value=stage.value, error=str(error), exc_info=True)

    async def on_tool_call(
        self, stage: WorkflowGenerationStage, tool_name: str, tool_input: dict[str, Any]
    ) -> None:
        """Tool call tracking - not needed for phase updates."""
        pass

    async def on_tool_result(
        self,
        stage: WorkflowGenerationStage,
        tool_name: str,
        tool_result: Any,
        is_error: bool,
    ) -> None:
        """Tool result tracking - not needed for phase updates."""
        pass

    async def on_workspace_created(self, workspace_path: str) -> None:
        """Update database when workspace is created.

        This enables early tracking of workspace location for debugging
        failed/timed-out workflow generations.
        """
        try:
            await _update_workspace_path(
                api_base_url=self.api_base_url,
                tenant_id=self.tenant_id,
                generation_id=self.generation_id,
                workspace_path=workspace_path,
            )
        except Exception as e:
            # Best-effort logging - don't fail job on workspace path update errors
            logger.warning(
                "workspace_path_update_failed",
                error=str(e),
                exc_info=True,
            )


async def _mark_triggering_analysis_failed(
    api_base_url: str,
    tenant_id: str,
    generation_id: str,
    error_message: str,
) -> None:
    """Mark the alert analysis that triggered this generation as failed.

    Fetches the generation record to find triggering_alert_analysis_id,
    then marks both the analysis and alert as failed via direct DB access
    (same pattern as reconciliation job).

    Best-effort: failures are logged but don't propagate.
    """
    try:
        # 1. Fetch generation to get triggering_alert_analysis_id
        url = f"{api_base_url}/v1/{tenant_id}/workflow-generations/{generation_id}"
        timeout = httpx.Timeout(10.0, connect=5.0)

        async with InternalAsyncClient(
            timeout=timeout, headers=internal_auth_headers()
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            generation = response.json()

        analysis_id = generation.get("triggering_alert_analysis_id")
        if not analysis_id:
            logger.info(
                "no_triggering_analysis_to_mark_failed",
                generation_id=generation_id,
            )
            return

        # 2. Mark analysis and alert as failed via direct DB
        from analysi.alert_analysis.db import AlertAnalysisDB

        db = AlertAnalysisDB()
        try:
            await db.initialize()

            # Get the alert_id from the analysis record
            analysis_data = await db.get_analysis(analysis_id)
            if not analysis_data:
                logger.warning(
                    "triggering_analysis_not_found",
                    analysis_id=analysis_id,
                    generation_id=generation_id,
                )
                return

            alert_id = analysis_data.get("alert_id")

            # Mark analysis as failed
            await db.update_analysis_status(
                analysis_id=analysis_id,
                status=WorkflowGenerationStatus.FAILED,
                error=f"Workflow generation failed: {error_message}",
            )

            # Only mark alert as failed if this analysis is still the current one.
            # A newer analysis (from retry) may already be in progress — don't overwrite it.
            if alert_id:
                await db.update_alert_status_if_current(alert_id, "failed", analysis_id)

            logger.info(
                "marked_triggering_analysis_failed",
                analysis_id=analysis_id,
                alert_id=alert_id,
                generation_id=generation_id,
            )
        finally:
            await db.close()

    except Exception as e:
        # Best-effort — reconciliation will catch it eventually
        logger.warning(
            "failed_to_mark_triggering_analysis_failed",
            generation_id=generation_id,
            error=str(e),
        )


@tracked_job(
    job_type="execute_workflow_generation",
    timeout_seconds=AlertAnalysisConfig.JOB_TIMEOUT,
    model_class=WorkflowGeneration,
    extract_row_id=lambda ctx, generation_id, tenant_id, alert_data, max_tasks_to_build=None, actor_user_id=None: (
        generation_id
    ),
)
async def execute_workflow_generation(
    ctx: dict[str, Any],
    generation_id: str,
    tenant_id: str,
    alert_data: dict,
    max_tasks_to_build: int | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """
    Execute workflow generation and track progress in database.

    Wrapper around run_full_orchestration() that:
    1. Calls pure orchestration logic
    2. Updates database via REST API
    3. Creates alert routing rule on success

    Args:
        ctx: ARQ context
        generation_id: WorkflowGeneration UUID
        tenant_id: Tenant identifier
        alert_data: alert data (dict format)
        max_tasks_to_build: Optional limit on parallel task building (for cost control)
        actor_user_id: UUID of the originating user. Propagated from the
            user who triggered analysis. None for system-initiated triggers
            (reconciliation, control events). When provided, MCP middleware
            resolves the actor's membership and applies their RBAC roles
            instead of the system key's roles.

    Returns:
        {
            "status": "completed" | "failed",
            "workflow_id": str | None,
            "error": str | None
        }
    """
    # Correlation + tenant context set by @tracked_job (Project Leros)

    logger.info("starting_workflow_generation_for_tenant", generation_id=generation_id)

    try:
        # 1. Setup executor with credentials from anthropic_agent integration
        async with AsyncSessionLocal() as credential_session:
            integration_repo = IntegrationRepository(credential_session)
            integration_service = IntegrationService(
                integration_repo=integration_repo,
            )
            credential_factory = AgentCredentialFactory(integration_service)

            try:
                credentials = await credential_factory.get_agent_credentials(tenant_id)
                oauth_token = credentials["oauth_token"]
                logger.info(
                    "oauth_token_retrieved",
                    tenant_id=tenant_id,
                    integration="anthropic_agent",
                )
            except ValueError as e:
                logger.error(
                    "anthropic_agent_integration_missing",
                    tenant_id=tenant_id,
                    error=str(e),
                )
                raise

        executor = create_executor(
            tenant_id=tenant_id,
            oauth_token=oauth_token,
            actor_user_id=actor_user_id,
        )
        logger.info(
            "executor_created",
            generation_id=generation_id,
        )

        # 2. Convert alert dict to AlertBase
        alert = AlertBase(**alert_data)

        # 3. Setup progress callback for database tracking
        api_base_url = AlertAnalysisConfig.API_BASE_URL
        progress_callback = DatabaseProgressCallback(
            api_base_url=api_base_url,
            tenant_id=tenant_id,
            generation_id=generation_id,
        )

        # 4. Run orchestration with pluggable stages
        # If max_tasks_to_build not provided, use config value
        if max_tasks_to_build is None:
            max_tasks_to_build = AlertAnalysisConfig.MAX_TASKS_TO_BUILD
            if max_tasks_to_build:
                logger.info(
                    "max_tasks_to_build_from_config",
                    max_tasks_to_build=max_tasks_to_build,
                )

        # Create TaskGenerationApiClient for tracking parallel task building
        task_generation_client = TaskGenerationApiClient(
            api_base_url=api_base_url,
            tenant_id=tenant_id,
            generation_id=generation_id,
        )

        # Create database session for skills sync
        # Skills are now always DB-backed
        async with AsyncSessionLocal() as session:
            skills_syncer = TenantSkillsSyncer(
                tenant_id=tenant_id,
                session_factory=AsyncSessionLocal,
            )
            logger.info(
                "db_skills_syncer_created_for_generation", generation_id=generation_id
            )

            # Create strategy provider
            provider = StageStrategyProvider(
                executor=executor,
                max_tasks_to_build=max_tasks_to_build,
                task_generation_client=task_generation_client,
                skills_syncer=skills_syncer,
                session=session,
            )
            stages = provider.get_stages()

            logger.info(
                "running_orchestration",
                generation_id=generation_id,
                stage_count=len(stages),
            )

            # Build initial state
            initial_state = {
                "alert": alert.model_dump(mode="json"),
                "tenant_id": tenant_id,
                "run_id": generation_id,
                "created_by": actor_user_id or str(SYSTEM_USER_ID),
            }

            try:
                # Execute with pluggable stages
                result = await run_orchestration_with_stages(
                    stages=stages,
                    initial_state=initial_state,
                    callback=progress_callback,
                )

                # Commit any Hydra changes if orchestration succeeded
                if not result.get("error"):
                    await session.commit()
                    logger.info(
                        "hydra_changes_committed",
                        generation_id=generation_id,
                    )
                else:
                    await session.rollback()
                    logger.warning(
                        "hydra_changes_rolled_back",
                        generation_id=generation_id,
                    )
            except Exception:
                await session.rollback()
                raise

        # 5. Update database with final results via REST API
        # Build orchestration_results JSONB structure
        orchestration_results = {
            "runbook": result.get("runbook"),
            "task_proposals": None,  # Not returned by orchestrator (internal)
            "tasks_built": result.get("tasks_built"),
            "workflow_composition": result.get("workflow_composition"),
            "metrics": _serialize_metrics(result.get("metrics", [])),
        }

        # Add error details if present (now in proper place, not in metrics)
        if result.get("error"):
            orchestration_results["error"] = {
                "message": str(result["error"]),
                "timestamp": datetime.now(UTC).isoformat(),
            }

        update_payload = {
            "workflow_id": result.get("workflow_id"),
            "workspace_path": result.get("workspace_path"),
            "status": "failed" if result.get("error") else "completed",
            "orchestration_results": orchestration_results,
        }

        logger.info("updating_generation_via_rest_api", generation_id=generation_id)
        await _update_workflow_generation(
            api_base_url=api_base_url,
            tenant_id=tenant_id,
            generation_id=generation_id,
            update_data=update_payload,
        )

        # 6. Create alert routing rule if successful
        # Wrapped in try/except so routing rule failure doesn't overwrite the
        # completed generation status (Issue #10)
        routing_rule_error = None
        if result.get("workflow_id") and not result.get("error"):
            try:
                logger.info(
                    "creating_routing_rule",
                    generation_id=generation_id,
                    workflow_id=result["workflow_id"],
                )
                analysis_group_id = await _create_routing_rule(
                    api_base_url=api_base_url,
                    tenant_id=tenant_id,
                    generation_id=generation_id,
                    workflow_id=result["workflow_id"],
                )

                # 7. Push-based resume: Immediately resume paused alerts waiting for this workflow
                # This eliminates the 10-second delay from reconciliation polling
                if analysis_group_id:
                    await _resume_paused_alerts(
                        api_base_url=api_base_url,
                        tenant_id=tenant_id,
                        analysis_group_id=analysis_group_id,
                    )
            except Exception as routing_err:
                # Routing rule failure is non-fatal — the workflow was built successfully.
                # Reconciliation job will recover by creating the rule later.
                routing_rule_error = str(routing_err)
                logger.error(
                    "routing_rule_creation_failed",
                    generation_id=generation_id,
                    error=str(routing_err),
                    exc_info=True,
                )

        # If orchestration returned an error, mark the triggering analysis as failed
        if result.get("error"):
            await _mark_triggering_analysis_failed(
                api_base_url=api_base_url,
                tenant_id=tenant_id,
                generation_id=generation_id,
                error_message=str(result["error"]),
            )

        logger.info(
            "workflow_generation_completed_successfully", generation_id=generation_id
        )
        return_dict = {
            "status": "completed" if not result.get("error") else "failed",
            "workflow_id": result.get("workflow_id"),
            "error": result.get("error"),
        }
        if routing_rule_error:
            return_dict["routing_rule_error"] = routing_rule_error
        return return_dict

    except Exception as e:
        logger.error(
            "workflow_generation_failed",
            generation_id=generation_id,
            error=str(e),
            exc_info=True,
        )

        # Update database with failure status
        api_base_url = AlertAnalysisConfig.API_BASE_URL
        try:
            await _update_workflow_generation(
                api_base_url=api_base_url,
                tenant_id=tenant_id,
                generation_id=generation_id,
                update_data={
                    "workflow_id": None,
                    "workspace_path": None,
                    "status": "failed",
                    "orchestration_results": {
                        "error": {
                            "message": str(e),
                            "type": type(e).__name__,
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    },
                },
            )
        except Exception as update_error:
            logger.error("failed_to_update_generation_status", error=str(update_error))

        # Mark the triggering alert analysis as failed immediately
        await _mark_triggering_analysis_failed(
            api_base_url=api_base_url,
            tenant_id=tenant_id,
            generation_id=generation_id,
            error_message=str(e),
        )

        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((HTTPStatusError, TimeoutException)),
)
async def _update_workflow_generation(
    api_base_url: str,
    tenant_id: str,
    generation_id: str,
    update_data: dict[str, Any],
) -> None:
    """Update workflow generation via REST API with retry logic."""
    url = f"{api_base_url}/v1/{tenant_id}/workflow-generations/{generation_id}/results"
    timeout = httpx.Timeout(30.0, connect=5.0)

    async with InternalAsyncClient(
        timeout=timeout, headers=internal_auth_headers()
    ) as client:
        response = await client.put(url, json=update_data)
        response.raise_for_status()
        logger.info(
            "successfully_updated_workflow_generation", generation_id=generation_id
        )


async def _create_routing_rule(
    api_base_url: str,
    tenant_id: str,
    generation_id: str,
    workflow_id: str,
) -> str | None:
    """Create alert routing rule via REST API.

    Returns:
        analysis_group_id if successful, None if failed
    """
    # First, get the generation to find analysis_group_id
    url = f"{api_base_url}/v1/{tenant_id}/workflow-generations/{generation_id}"
    timeout = httpx.Timeout(30.0, connect=5.0)

    async with InternalAsyncClient(
        timeout=timeout, headers=internal_auth_headers()
    ) as client:
        # Get generation
        response = await client.get(url)
        response.raise_for_status()
        generation = response.json()

        analysis_group_id = generation["analysis_group_id"]

        # Create routing rule
        rule_url = f"{api_base_url}/v1/{tenant_id}/alert-routing-rules"
        rule_data = {
            "analysis_group_id": analysis_group_id,
            "workflow_id": workflow_id,
        }
        response = await client.post(rule_url, json=rule_data)
        response.raise_for_status()
        logger.info(
            "routing_rule_created",
            analysis_group_id=analysis_group_id,
            workflow_id=workflow_id,
        )

        return analysis_group_id


async def _resume_paused_alerts(
    api_base_url: str,
    tenant_id: str,
    analysis_group_id: str,
) -> None:
    """Resume all paused alerts waiting for this analysis group's workflow.

    Push-based Resume: Called AFTER creating routing rule to immediately
    resume alerts without waiting for reconciliation polling.

    This is best-effort - failures are logged but don't fail the job.
    Reconciliation will catch any missed alerts.
    """
    url = f"{api_base_url}/v1/{tenant_id}/analysis-groups/{analysis_group_id}/resume-paused-alerts"
    timeout = httpx.Timeout(30.0, connect=5.0)

    try:
        async with InternalAsyncClient(
            timeout=timeout, headers=internal_auth_headers()
        ) as client:
            response = await client.post(url)
            response.raise_for_status()
            result = response.json()

            resumed = result.get("resumed_count", 0)
            skipped = result.get("skipped_count", 0)

            if resumed > 0:
                logger.info(
                    "paused_alerts_resumed",
                    resumed_count=resumed,
                    skipped_count=skipped,
                    analysis_group_id=analysis_group_id,
                )
            else:
                logger.debug(
                    "no_paused_alerts_to_resume",
                    analysis_group_id=analysis_group_id,
                )

    except Exception as e:
        # Best-effort - log and continue
        # Reconciliation will catch any missed alerts
        logger.warning(
            "resume_paused_alerts_failed",
            analysis_group_id=analysis_group_id,
            error=str(e),
        )


def _serialize_metrics(metrics: list) -> dict[str, Any]:
    """Serialize metrics list to dict for JSONB storage."""
    if not metrics:
        return {}

    return {
        "stages": [
            {
                "total_cost_usd": m.total_cost_usd,
                "total_input_tokens": m.usage.get("total_input_tokens", 0),
                "total_output_tokens": m.usage.get("total_output_tokens", 0),
            }
            for m in metrics
        ],
        "total_cost_usd": sum(m.total_cost_usd for m in metrics),
    }


def _should_retry_progress_update(retry_state: RetryCallState) -> bool:
    """
    Determine if progress update should be retried.

    Retry on:
    - 5xx server errors (transient)
    - Timeouts (transient)

    Don't retry on:
    - 4xx client errors like 404 (permanent - record doesn't exist)
    - 401/403 (auth issues - won't fix on retry)
    """
    if retry_state.outcome is None:
        return False
    exception = retry_state.outcome.exception()
    if exception is None:
        return False
    if isinstance(exception, TimeoutException):
        return True
    if isinstance(exception, HTTPStatusError):
        # Only retry on server errors (5xx), not client errors (4xx)
        return exception.response.status_code >= 500
    return False


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((TimeoutException, HTTPStatusError)),
)
async def _update_workspace_path(
    api_base_url: str,
    tenant_id: str,
    generation_id: str,
    workspace_path: str,
) -> None:
    """
    Update workflow generation workspace_path via REST API with retry logic.

    This enables early tracking of workspace location for debugging
    failed/timed-out workflow generations.

    Retries on transient errors (5xx, timeouts).
    """
    url = f"{api_base_url}/v1/{tenant_id}/workflow-generations/{generation_id}/progress"
    timeout = httpx.Timeout(30.0, connect=5.0)

    payload = {"workspace_path": workspace_path}

    async with InternalAsyncClient(
        timeout=timeout, headers=internal_auth_headers()
    ) as client:
        response = await client.patch(url, json=payload)
        response.raise_for_status()
        logger.info(
            "workspace_path_updated",
            generation_id=generation_id,
            workspace_path=workspace_path,
        )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=_should_retry_progress_update,
)
async def _update_progress(
    api_base_url: str,
    tenant_id: str,
    generation_id: str,
    stage: str,
    tasks_count: int | None = None,
) -> None:
    """
    Update workflow generation progress via REST API.

    All 4 phases are initialized on first call. When a stage is provided,
    it's marked as in_progress and all previous stages are auto-completed.

    Retries on transient errors (5xx, timeouts) but not permanent errors (4xx).
    Wrapped in try-except at call site for best-effort observability.
    """
    url = f"{api_base_url}/v1/{tenant_id}/workflow-generations/{generation_id}/progress"
    timeout = httpx.Timeout(30.0, connect=5.0)

    payload: dict[str, Any] = {"stage": stage}
    if tasks_count is not None:
        payload["tasks_count"] = tasks_count

    async with InternalAsyncClient(
        timeout=timeout, headers=internal_auth_headers()
    ) as client:
        response = await client.patch(url, json=payload)
        response.raise_for_status()
        logger.info(
            "workflow_generation_progress_updated",
            generation_id=generation_id,
            stage=stage,
        )


# NOTE: _mark_stage_completed was removed - stage completion is now implicit.
# When the next stage starts via /progress API, all previous stages are
# automatically marked as completed. Final status is set via /results API.
