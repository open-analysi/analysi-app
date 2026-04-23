"""Alert Analysis Pipeline Implementation"""

from datetime import UTC, datetime
from typing import Any

from httpx import ConnectError, HTTPStatusError, TimeoutException
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from analysi.agentic_orchestration.logging_context import get_pipeline_logger
from analysi.alert_analysis.steps import (
    DispositionMatchingStep,
    PreTriageStep,
    WorkflowBuilderStep,
    WorkflowExecutionStep,
)
from analysi.common.internal_auth import internal_auth_headers
from analysi.common.internal_client import InternalAsyncClient
from analysi.common.retry_config import (
    WorkflowNotFoundError,
    WorkflowPausedForHumanInput,
)
from analysi.config.logging import get_logger
from analysi.schemas.alert import AnalysisStatus

logger = get_logger(__name__)


class AlertAnalysisPipeline:
    """
    Orchestrates the 4-step alert analysis pipeline.
    Each step is idempotent and can be resumed from failure.
    """

    def __init__(
        self,
        tenant_id: str,
        alert_id: str,
        analysis_id: str,
        actor_user_id: str | None = None,
    ):
        self.tenant_id = tenant_id
        self.alert_id = alert_id
        self.analysis_id = analysis_id
        self.actor_user_id = actor_user_id  # For audit attribution
        self.db = None  # Will be injected by worker

        # Create contextual logger with tenant and alert context
        self.logger = get_pipeline_logger(tenant_id, alert_id)

        # Initialize all steps
        from analysi.alert_analysis.clients import KeaCoordinationClient
        from analysi.alert_analysis.config import AlertAnalysisConfig

        kea_client = KeaCoordinationClient(base_url=AlertAnalysisConfig.API_BASE_URL)

        self.steps = {
            "pre_triage": PreTriageStep(),
            "workflow_builder": WorkflowBuilderStep(
                kea_client=kea_client,
                actor_user_id=self.actor_user_id,
            ),
            "workflow_execution": WorkflowExecutionStep(),
            "final_disposition_update": DispositionMatchingStep(tenant_id=tenant_id),
        }

    async def execute(self) -> dict[str, Any]:
        """
        Execute the complete 4-step pipeline.
        Each step checks if it's already completed (idempotency).

        Returns:
            Dict with execution results
        """
        self.logger.info("pipeline_execution_started", analysis_id=self.analysis_id)

        # Update status to running
        await self._update_status(AnalysisStatus.RUNNING)

        # This ensures the UI knows all expected steps upfront
        if self.db:
            await self.db.initialize_steps_progress(self.analysis_id)

        try:
            # Step 1: Pre-triage
            if not await self._is_step_completed("pre_triage"):
                await self._execute_step("pre_triage")

            # Fetch alert data - needed for workflow_builder and workflow_execution retry
            alert_data = await self.db.get_alert(self.alert_id)
            if not alert_data:
                raise ValueError(f"Alert {self.alert_id} not found")

            # Step 2: Workflow Builder
            if not await self._is_step_completed("workflow_builder"):
                workflow_name = await self._execute_step(
                    "workflow_builder", alert_data=alert_data
                )
            else:
                workflow_name = await self._get_step_result(
                    "workflow_builder", "selected_workflow"
                )

            # Check if workflow is ready (None = paused for generation)
            if workflow_name is None:
                self.logger.info(
                    "alert_paused_for_workflow_generation",
                    alert_id=self.alert_id,
                )
                # Update AlertAnalysis.status to paused_workflow_building
                # NOTE: Alert.analysis_status stays as "in_progress" (user-facing simplified status)
                # Reconciliation job queries AlertAnalysis.status, not Alert.analysis_status
                await self._update_status(AnalysisStatus.PAUSED_WORKFLOW_BUILDING.value)
                return {
                    "status": AnalysisStatus.PAUSED_WORKFLOW_BUILDING.value,
                    "message": "Workflow generation in progress",
                    "paused_at": datetime.now(UTC).isoformat(),
                }

            # Step 3: Workflow Execution (with retry on stale cache)
            if not await self._is_step_completed("workflow_execution"):
                workflow_run_id = await self._execute_workflow_with_retry(
                    workflow_name, alert_data
                )
                # Link workflow to analysis so the UI can show it during execution.
                if workflow_run_id and self.db:
                    await self._link_workflow_to_analysis(
                        workflow_name, workflow_run_id
                    )
                # Handle case where retry triggered new workflow generation
                if workflow_run_id is None:
                    self.logger.info(
                        "alert_paused_stale_workflow_retry",
                        alert_id=self.alert_id,
                    )
                    await self._update_status(
                        AnalysisStatus.PAUSED_WORKFLOW_BUILDING.value
                    )
                    return {
                        "status": AnalysisStatus.PAUSED_WORKFLOW_BUILDING.value,
                        "message": "Workflow was stale, new generation in progress",
                        "paused_at": datetime.now(UTC).isoformat(),
                    }
            else:
                workflow_run_id = await self._get_step_result(
                    "workflow_execution", "workflow_run_id"
                )

            # Step 4: Final Disposition Update
            # If this fails, the analysis fails. We want the disposition to come
            # from the actual analysis, not from an arbitrary fallback code path.
            if not await self._is_step_completed("final_disposition_update"):
                await self._execute_step(
                    "final_disposition_update",
                    workflow_run_id=workflow_run_id,
                    workflow_id=workflow_name,
                )

            # If this status update fails, the analysis was already completed
            # by Step 4's /complete API call. Reconciliation will sync later.
            try:
                await self._update_status(AnalysisStatus.COMPLETED)
            except Exception as status_err:
                self.logger.error(
                    "status_update_to_completed_failed",
                    error=str(status_err),
                    note="Analysis was already completed by Step 4. Reconciliation will sync status later.",
                )

            return {
                "status": "completed",
                "workflow_run_id": workflow_run_id,
                "completed_at": datetime.now(UTC).isoformat(),
            }

        except WorkflowPausedForHumanInput as hitl:
            # HITL — Project Kalymnos: workflow paused for human input.
            # Mark analysis as PAUSED_HUMAN_REVIEW and return — freeing the ARQ worker.
            #
            # Checkpoint step 3 with the workflow_run_id so that when the pipeline
            # is re-queued after the human responds, _is_step_completed returns True
            # and _get_step_result returns the workflow_run_id — skipping straight
            # to step 4 (final disposition update).
            #
            # Without this checkpoint, re-queue would try to create a NEW workflow
            # run instead of using the one that already completed after HITL resume.
            self.logger.info(
                "alert_paused_for_human_review",
                alert_id=self.alert_id,
                workflow_run_id=hitl.workflow_run_id,
            )
            if self.db:
                await self.db.update_step_progress(
                    self.analysis_id,
                    "workflow_execution",
                    completed=True,
                    result={"workflow_run_id": hitl.workflow_run_id},
                )
                await self.db.update_current_step(
                    self.analysis_id, "workflow_execution"
                )
                await self._link_workflow_to_analysis(None, hitl.workflow_run_id)
            await self._update_status(AnalysisStatus.PAUSED_HUMAN_REVIEW.value)
            return {
                "status": AnalysisStatus.PAUSED_HUMAN_REVIEW.value,
                "workflow_run_id": hitl.workflow_run_id,
                "message": "Workflow paused waiting for human input",
                "paused_at": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            self.logger.error("pipeline_execution_failed", error=str(e))
            await self._update_status(AnalysisStatus.FAILED, error=str(e))
            raise

    async def _execute_workflow_with_retry(
        self, workflow_id: str, alert_data: dict[str, Any]
    ) -> str | None:
        """
        Execute workflow with retry on WorkflowNotFoundError.

        If the workflow is not found (404), this indicates a stale cache.
        We invalidate the cache, re-run workflow_builder to get a fresh
        workflow_id, and retry the execution once.

        Args:
            workflow_id: Initial workflow ID from workflow_builder step
            alert_data: Alert data needed for re-running workflow_builder

        Returns:
            Workflow run ID if execution succeeded
            None if workflow generation was triggered (alert should pause)

        Raises:
            WorkflowNotFoundError: If workflow still not found after retry
        """
        try:
            return await self._execute_step(
                "workflow_execution", workflow_id=workflow_id, alert_data=alert_data
            )
        except WorkflowNotFoundError as e:
            self.logger.warning(
                "workflow_not_found_cache_stale",
                workflow_id=e.workflow_id,
            )

            # Invalidate the workflow_builder cache
            workflow_builder_step = self.steps["workflow_builder"]
            workflow_builder_step.invalidate_cache()

            # Clear the workflow_builder step completion so it runs again
            await self._clear_step_completion("workflow_builder")

            # Re-run workflow_builder to get fresh workflow_id
            new_workflow_id = await self._execute_step(
                "workflow_builder", alert_data=alert_data
            )

            if new_workflow_id is None:
                # Workflow was deleted and a new generation started.
                # Return None to let caller handle pause (same as initial flow).
                self.logger.info(
                    "stale_workflow_deleted_new_generation_triggered",
                    stale_workflow_id=e.workflow_id,
                )
                return None

            self.logger.info(
                "fresh_workflow_id_after_cache_invalidation",
                workflow_id=new_workflow_id,
            )

            # Retry workflow execution with new ID
            return await self._execute_step(
                "workflow_execution", workflow_id=new_workflow_id, alert_data=alert_data
            )

    async def _clear_step_completion(self, step_name: str):
        """
        Clear a step's completion status to allow re-execution.

        Used when we need to re-run a step (e.g., after cache invalidation).
        """
        self.logger.info("clearing_step_completion", step_name=step_name)

        if self.db:
            try:
                await self.db.clear_step_completion(self.analysis_id, step_name)
            except Exception as e:
                self.logger.warning("clear_step_completion_failed", error=str(e))
                # Continue anyway - the step will re-execute

    async def _is_step_completed(self, step_name: str) -> bool:
        """
        Check if a step has already been completed.

        Uses new PipelineStepsProgress schema format with backward compatibility.
        """
        self.logger.debug("checking_step_completion", step_name=step_name)

        if not self.db:
            return False

        try:
            from analysi.schemas.alert import (
                PipelineStep,
                PipelineStepsProgress,
                StepStatus,
            )

            progress_dict = await self.db.get_step_progress(self.analysis_id)
            progress = PipelineStepsProgress.from_dict(progress_dict)

            try:
                pipeline_step = PipelineStep(step_name)
                step_progress = progress.get_step(pipeline_step)
                if step_progress:
                    return step_progress.status == StepStatus.COMPLETED
            except ValueError:
                # Unknown step name, fall back to old format check
                if progress_dict and step_name in progress_dict:
                    return progress_dict[step_name].get("completed", False)

        except Exception as e:
            self.logger.error("step_completion_check_error", error=str(e))

        return False

    async def _execute_step(self, step_name: str, **kwargs) -> Any:
        """
        Execute a single step and update progress.

        STUBBED: Needs full implementation
        """
        self.logger.info("executing_step", step_name=step_name)

        # Mark step as started
        await self._update_step_progress(step_name, "started")

        try:
            # Execute the step
            step = self.steps[step_name]
            result = await step.execute(
                tenant_id=self.tenant_id,
                alert_id=self.alert_id,
                analysis_id=self.analysis_id,
                **kwargs,
            )

            # Mark step as completed
            await self._update_step_progress(step_name, "completed", result=result)

            # Update current_step
            await self._update_current_step(self._get_next_step(step_name))

            return result

        except Exception as e:
            # Mark step as failed
            await self._update_step_progress(step_name, "failed", error=str(e))
            raise

    async def _update_status(self, status: str, error: str | None = None):
        """
        Update the overall analysis status via REST API.

        No DB fallback - REST API is the authoritative source for status updates.
        """
        self.logger.info("updating_analysis_status", status=status)

        from analysi.alert_analysis.clients import BackendAPIClient

        api_client = BackendAPIClient()
        await api_client.update_analysis_status(
            self.tenant_id, self.analysis_id, status, error=error
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(
            (HTTPStatusError, ConnectError, TimeoutException)
        ),
    )
    async def _update_step_progress_api(
        self, step_name: str, completed: bool, error: str | None = None
    ):
        """
        Update step progress via REST API with retry logic.
        """
        import httpx

        from analysi.alert_analysis.config import AlertAnalysisConfig

        base_url = AlertAnalysisConfig.API_BASE_URL
        timeout = httpx.Timeout(30.0, connect=5.0)

        async with InternalAsyncClient(
            base_url=base_url, timeout=timeout, headers=internal_auth_headers()
        ) as client:
            response = await client.put(
                f"/v1/{self.tenant_id}/analyses/{self.analysis_id}/step",
                params={"step_name": step_name, "completed": completed, "error": error},
            )
            response.raise_for_status()

    async def _update_step_progress(
        self, step_name: str, status: str, result: Any = None, error: str | None = None
    ):
        """
        Update progress for a specific step via REST API.

        No DB fallback - REST API is the authoritative source for step progress.
        Uses retry logic via _update_step_progress_api.
        """
        self.logger.info("updating_step_progress", step_name=step_name, status=status)

        completed = status == AnalysisStatus.COMPLETED
        await self._update_step_progress_api(step_name, completed, error)
        self.logger.info("step_progress_updated", step_name=step_name)

    async def _update_current_step(self, step_name: str | None):
        """
        Update the current_step field.
        """
        if step_name:
            self.logger.info("setting_current_step", step_name=step_name)

        if self.db and step_name:
            await self.db.update_current_step(self.analysis_id, step_name)

    async def _link_workflow_to_analysis(
        self, workflow_id: str | None, workflow_run_id: str
    ) -> None:
        """Link workflow run to analysis so the UI shows it during execution."""
        try:
            from uuid import UUID

            from sqlalchemy import update as sql_update

            from analysi.models.alert import AlertAnalysis

            values: dict = {"workflow_run_id": UUID(workflow_run_id)}
            if workflow_id:
                values["workflow_id"] = UUID(workflow_id)
            await self.db.session.execute(
                sql_update(AlertAnalysis)
                .where(AlertAnalysis.id == UUID(self.analysis_id))
                .values(**values)
            )
            await self.db.session.commit()
        except Exception:
            self.logger.warning("link_workflow_to_analysis_failed", exc_info=True)

    async def _get_step_result(self, step_name: str, field: str) -> Any:
        """
        Get a stored result from a completed step.

        Handles both old format (dict of step dicts) and new format
        (PipelineStepsProgress with "steps" array).
        """
        if not self.db:
            return None

        try:
            progress_dict = await self.db.get_step_progress(self.analysis_id)
            if not progress_dict:
                return None

            # New format: {"steps": [{...}, ...]}
            if "steps" in progress_dict:
                from analysi.schemas.alert import (
                    PipelineStep,
                    PipelineStepsProgress,
                )

                parsed = PipelineStepsProgress.from_dict(progress_dict)
                try:
                    step = parsed.get_step(PipelineStep(step_name))
                    if step and step.result and isinstance(step.result, dict):
                        return step.result.get(field)
                except ValueError:
                    pass
                return None

            # Old format: {"step_name": {"result": ..., "completed": true}}
            if step_name in progress_dict:
                step_data = progress_dict[step_name]
                result = step_data.get("result", {})
                if isinstance(result, dict):
                    return result.get(field)
                return result

        except Exception as e:
            self.logger.error("step_result_error", error=str(e))

        return None

    def _get_next_step(self, current_step: str) -> str | None:
        """Get the next step in the pipeline."""
        step_order = [
            "pre_triage",
            "workflow_builder",
            "workflow_execution",
            "final_disposition_update",
        ]
        try:
            current_index = step_order.index(current_step)
            if current_index < len(step_order) - 1:
                return step_order[current_index + 1]
        except ValueError:
            pass
        return None
