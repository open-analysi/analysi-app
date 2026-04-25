"""
Unit tests for HITL analysis pipeline resume — Project Kalymnos.

Tests the fix for the gap where pipeline step 4 (final disposition update)
never ran after HITL resume because the original ARQ job returned early.

Three key behaviors:
  1. Pipeline checkpoints step 3 with workflow_run_id on HITL pause.
  2. handle_human_responded re-queues the pipeline after workflow completes.
  3. Re-queued pipeline skips steps 1-3 and runs step 4.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.schemas.alert import AnalysisStatus

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_pipeline_http_clients():
    """Mock HTTP clients to prevent real network calls in unit tests."""
    mock_api_client = AsyncMock()
    mock_api_client.update_analysis_status = AsyncMock(return_value=True)
    mock_api_client.update_alert_analysis_status = AsyncMock(return_value=True)
    with (
        patch(
            "analysi.alert_analysis.clients.BackendAPIClient",
            return_value=mock_api_client,
        ),
        patch("analysi.alert_analysis.pipeline.InternalAsyncClient") as mock_internal,
    ):
        mock_ctx = AsyncMock()
        mock_internal.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_internal.return_value.__aexit__ = AsyncMock(return_value=False)
        yield


# ---------------------------------------------------------------------------
# 1. Pipeline checkpoints step 3 on HITL pause
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPipelineCheckpointsStep3OnHITLPause:
    """When the workflow pauses for HITL, the pipeline must checkpoint step 3
    with the workflow_run_id so the re-queued pipeline skips to step 4."""

    @pytest.mark.asyncio
    async def test_step3_checkpointed_with_workflow_run_id(self):
        """Pipeline calls db.update_step_progress to checkpoint step 3."""
        from analysi.alert_analysis.pipeline import AlertAnalysisPipeline
        from analysi.common.retry_config import WorkflowPausedForHumanInput

        pipeline = AlertAnalysisPipeline(
            tenant_id="t1",
            alert_id=str(uuid4()),
            analysis_id=str(uuid4()),
        )

        # Mock DB with step completion tracking
        mock_db = AsyncMock()
        mock_db.get_step_progress = AsyncMock(return_value={})
        mock_db.initialize_steps_progress = AsyncMock()
        mock_db.get_alert = AsyncMock(return_value={"alert_id": "a1", "title": "Test"})
        mock_db.update_step_progress = AsyncMock()
        pipeline.db = mock_db

        wf_run_id = str(uuid4())

        # Mock steps: pre_triage and workflow_builder complete, workflow_execution pauses
        mock_pre_triage = AsyncMock()
        mock_pre_triage.execute = AsyncMock(return_value=None)
        mock_wf_builder = AsyncMock()
        mock_wf_builder.execute = AsyncMock(return_value="test-workflow-id")
        mock_wf_execution = AsyncMock()
        mock_wf_execution.execute = AsyncMock(
            side_effect=WorkflowPausedForHumanInput(wf_run_id)
        )

        pipeline.steps = {
            "pre_triage": mock_pre_triage,
            "workflow_builder": mock_wf_builder,
            "workflow_execution": mock_wf_execution,
            "final_disposition_update": AsyncMock(),
        }

        result = await pipeline.execute()

        # Step 3 should be checkpointed
        mock_db.update_step_progress.assert_awaited_once_with(
            pipeline.analysis_id,
            "workflow_execution",
            completed=True,
            result={"workflow_run_id": wf_run_id},
        )

        # Pipeline returns paused_human_review
        assert result["status"] == AnalysisStatus.PAUSED_HUMAN_REVIEW.value
        assert result["workflow_run_id"] == wf_run_id

        # current_step must be set so the UI progress display highlights the right step
        mock_db.update_current_step.assert_awaited_with(
            pipeline.analysis_id, "workflow_execution"
        )

    @pytest.mark.asyncio
    async def test_step4_not_executed_on_hitl_pause(self):
        """Step 4 must NOT run when the workflow pauses for HITL."""
        from analysi.alert_analysis.pipeline import AlertAnalysisPipeline
        from analysi.common.retry_config import WorkflowPausedForHumanInput

        pipeline = AlertAnalysisPipeline(
            tenant_id="t1",
            alert_id=str(uuid4()),
            analysis_id=str(uuid4()),
        )

        mock_db = AsyncMock()
        mock_db.get_step_progress = AsyncMock(return_value={})
        mock_db.initialize_steps_progress = AsyncMock()
        mock_db.get_alert = AsyncMock(return_value={"alert_id": "a1"})
        mock_db.update_step_progress = AsyncMock()
        pipeline.db = mock_db

        mock_disposition = AsyncMock()
        mock_disposition.execute = AsyncMock()

        pipeline.steps = {
            "pre_triage": AsyncMock(execute=AsyncMock(return_value=None)),
            "workflow_builder": AsyncMock(execute=AsyncMock(return_value="wf-id")),
            "workflow_execution": AsyncMock(
                execute=AsyncMock(side_effect=WorkflowPausedForHumanInput(str(uuid4())))
            ),
            "final_disposition_update": mock_disposition,
        }

        await pipeline.execute()

        # Step 4 should NOT have been called
        mock_disposition.execute.assert_not_awaited()


# ---------------------------------------------------------------------------
# 2. handle_human_responded re-queues pipeline after workflow completes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHandleHumanRespondedRequeuesPipeline:
    """After HITL resume completes the workflow, the pipeline must be
    re-queued so step 4 (final disposition update) can run."""

    @pytest.mark.asyncio
    async def test_pipeline_requeued_on_workflow_completion(self):
        """handle_human_responded enqueues process_alert_analysis after
        continue_after_hitl succeeds."""
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        question_id = uuid4()
        task_run_id = uuid4()
        workflow_run_id = uuid4()
        node_instance_id = uuid4()
        analysis_id = uuid4()
        alert_id = uuid4()

        # Mock question with workflow + analysis context
        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.task_run_id = task_run_id
        mock_question.workflow_run_id = workflow_run_id
        mock_question.node_instance_id = node_instance_id
        mock_question.analysis_id = analysis_id
        mock_question.status = "answered"

        # Mock event
        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answer": "Approve",
            "answered_by": "U123",
        }

        # Mock task result: COMPLETED (workflow finished)
        mock_task_result = MagicMock()
        mock_task_result.status = "completed"
        mock_task_result.task_run_id = task_run_id
        mock_task_result.output_data = {"result": "done"}
        mock_task_result.llm_usage = None
        mock_task_result.error_message = None

        # Mock analysis (for re-queue to get alert_id)
        mock_analysis = MagicMock()
        mock_analysis.alert_id = alert_id

        with (
            patch("analysi.db.session.AsyncSessionLocal") as MockSession,
            patch(
                "analysi.services.task_execution.TaskExecutionService"
            ) as MockTaskExec,
            patch(
                "analysi.repositories.hitl_repository.HITLQuestionRepository"
            ) as MockRepo,
            patch(
                "analysi.repositories.activity_audit_repository.ActivityAuditRepository"
            ) as MockAuditRepo,
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor"
            ) as MockWFExecutor,
            patch(
                "analysi.repositories.alert_repository.AlertAnalysisRepository"
            ) as MockAnalysisRepo,
            patch(
                "analysi.common.arq_enqueue.enqueue_arq_job",
                new_callable=AsyncMock,
            ) as mock_enqueue,
        ):
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            # Mock HITL repo
            mock_repo = AsyncMock()
            mock_repo.get_by_id = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo

            # Mock task execution
            mock_task_svc = AsyncMock()
            mock_task_svc.resume_paused_task = AsyncMock(return_value=mock_task_result)
            MockTaskExec.return_value = mock_task_svc

            # Mock workflow executor
            MockWFExecutor.continue_after_hitl = AsyncMock()

            # Mock audit repo
            MockAuditRepo.return_value = AsyncMock()

            # Mock analysis repo (for _update_analysis_after_hitl and _requeue)
            mock_analysis_repo = AsyncMock()
            mock_analysis_repo.mark_running = AsyncMock()
            mock_analysis_repo.get_by_id = AsyncMock(return_value=mock_analysis)
            MockAnalysisRepo.return_value = mock_analysis_repo

            await handle_human_responded(mock_event)

            # Pipeline should have been re-queued
            mock_enqueue.assert_awaited_once_with(
                "analysi.alert_analysis.worker.process_alert_analysis",
                "t1",
                str(alert_id),
                str(analysis_id),
            )

    @pytest.mark.asyncio
    async def test_pipeline_not_requeued_on_task_failure(self):
        """If the resumed task FAILED, the pipeline should NOT be re-queued."""
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        question_id = uuid4()
        task_run_id = uuid4()
        analysis_id = uuid4()

        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.task_run_id = task_run_id
        mock_question.workflow_run_id = uuid4()
        mock_question.node_instance_id = uuid4()
        mock_question.analysis_id = analysis_id
        mock_question.status = "answered"

        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answer": "Reject",
            "answered_by": "U456",
        }

        # Task FAILED after resume
        mock_task_result = MagicMock()
        mock_task_result.status = "failed"
        mock_task_result.task_run_id = task_run_id
        mock_task_result.output_data = None
        mock_task_result.llm_usage = None
        mock_task_result.error_message = "Script error"

        with (
            patch("analysi.db.session.AsyncSessionLocal") as MockSession,
            patch(
                "analysi.services.task_execution.TaskExecutionService"
            ) as MockTaskExec,
            patch(
                "analysi.repositories.hitl_repository.HITLQuestionRepository"
            ) as MockRepo,
            patch(
                "analysi.repositories.activity_audit_repository.ActivityAuditRepository"
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor"
            ) as MockWFExecutor,
            patch(
                "analysi.repositories.alert_repository.AlertAnalysisRepository"
            ) as MockAnalysisRepo,
            patch(
                "analysi.common.arq_enqueue.enqueue_arq_job",
                new_callable=AsyncMock,
            ) as mock_enqueue,
        ):
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            MockRepo.return_value = AsyncMock(
                get_by_id=AsyncMock(return_value=mock_question)
            )
            mock_task_svc = AsyncMock()
            mock_task_svc.resume_paused_task = AsyncMock(return_value=mock_task_result)
            MockTaskExec.return_value = mock_task_svc
            MockWFExecutor.continue_after_hitl = AsyncMock()

            mock_analysis_repo = AsyncMock()
            mock_analysis_repo.mark_failed = AsyncMock()
            MockAnalysisRepo.return_value = mock_analysis_repo

            await handle_human_responded(mock_event)

            # Pipeline should NOT be re-queued on failure
            mock_enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pipeline_not_requeued_on_task_repaused(self):
        """If the resumed task paused AGAIN (another HITL), no re-queue."""
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        question_id = uuid4()
        task_run_id = uuid4()

        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.task_run_id = task_run_id
        mock_question.workflow_run_id = uuid4()
        mock_question.node_instance_id = uuid4()
        mock_question.analysis_id = uuid4()
        mock_question.status = "answered"

        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answer": "Escalate",
            "answered_by": "U789",
        }

        # Task PAUSED again (another HITL tool)
        mock_task_result = MagicMock()
        mock_task_result.status = "paused"
        mock_task_result.task_run_id = task_run_id
        mock_task_result.output_data = {"_hitl_checkpoint": {}}
        mock_task_result.llm_usage = None
        mock_task_result.error_message = None

        with (
            patch("analysi.db.session.AsyncSessionLocal") as MockSession,
            patch(
                "analysi.services.task_execution.TaskExecutionService"
            ) as MockTaskExec,
            patch(
                "analysi.repositories.hitl_repository.HITLQuestionRepository"
            ) as MockRepo,
            patch(
                "analysi.repositories.activity_audit_repository.ActivityAuditRepository"
            ),
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor"
            ) as MockWFExecutor,
            patch(
                "analysi.common.arq_enqueue.enqueue_arq_job",
                new_callable=AsyncMock,
            ) as mock_enqueue,
        ):
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            MockRepo.return_value = AsyncMock(
                get_by_id=AsyncMock(return_value=mock_question)
            )
            mock_task_svc = AsyncMock()
            mock_task_svc.resume_paused_task = AsyncMock(return_value=mock_task_result)
            MockTaskExec.return_value = mock_task_svc
            MockWFExecutor.continue_after_hitl = AsyncMock()

            await handle_human_responded(mock_event)

            # Pipeline should NOT be re-queued on re-pause
            mock_enqueue.assert_not_awaited()


# ---------------------------------------------------------------------------
# 3. Re-queued pipeline skips to step 4
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRequeuedPipelineSkipsToStep4:
    """When the pipeline is re-queued after HITL resume, it should skip
    steps 1-3 (already completed) and only run step 4."""

    @pytest.mark.asyncio
    async def test_requeued_pipeline_runs_step4_only(self):
        """Pipeline with steps 1-3 completed runs only step 4."""
        from analysi.alert_analysis.pipeline import AlertAnalysisPipeline

        pipeline = AlertAnalysisPipeline(
            tenant_id="t1",
            alert_id=str(uuid4()),
            analysis_id=str(uuid4()),
        )

        wf_run_id = str(uuid4())

        # Mock DB: steps 1-3 all completed, step 4 not completed
        mock_db = AsyncMock()
        mock_db.initialize_steps_progress = AsyncMock()
        mock_db.get_alert = AsyncMock(return_value={"alert_id": "a1"})

        # Step progress: pre_triage, workflow_builder, workflow_execution completed
        completed_progress = {
            "pre_triage": {"completed": True, "status": "completed"},
            "workflow_builder": {
                "completed": True,
                "status": "completed",
                "result": {"selected_workflow": "wf-123"},
            },
            "workflow_execution": {
                "completed": True,
                "status": "completed",
                "result": {"workflow_run_id": wf_run_id},
            },
        }
        mock_db.get_step_progress = AsyncMock(return_value=completed_progress)
        mock_db.update_step_progress = AsyncMock()
        mock_db.update_current_step = AsyncMock()
        pipeline.db = mock_db

        # Track which steps execute
        mock_disposition = AsyncMock()
        mock_disposition.execute = AsyncMock(return_value="disposition-result")

        pipeline.steps = {
            "pre_triage": AsyncMock(execute=AsyncMock()),
            "workflow_builder": AsyncMock(execute=AsyncMock()),
            "workflow_execution": AsyncMock(execute=AsyncMock()),
            "final_disposition_update": mock_disposition,
        }

        result = await pipeline.execute()

        # Steps 1-3 should NOT have been called (already completed)
        pipeline.steps["pre_triage"].execute.assert_not_awaited()
        pipeline.steps["workflow_builder"].execute.assert_not_awaited()
        pipeline.steps["workflow_execution"].execute.assert_not_awaited()

        # Step 4 SHOULD have been called with the checkpointed workflow_run_id
        mock_disposition.execute.assert_awaited_once()
        call_kwargs = mock_disposition.execute.call_args.kwargs
        assert call_kwargs["workflow_run_id"] == wf_run_id

        # Pipeline should complete
        assert result["status"] == "completed"
