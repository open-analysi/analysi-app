"""
Unit tests for Analysis Pause & Resume.

Tests R15-R18: analysis-level pause/resume when workflow pauses for HITL.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.schemas.alert import AnalysisStatus

# ---------------------------------------------------------------------------
# R15 — AnalysisStatus.PAUSED_HUMAN_REVIEW
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnalysisStatusPausedHumanReview:
    """R15: PAUSED_HUMAN_REVIEW status exists in AnalysisStatus."""

    def test_paused_human_review_value(self):
        assert AnalysisStatus.PAUSED_HUMAN_REVIEW == "paused_human_review"

    def test_paused_human_review_from_string(self):
        assert (
            AnalysisStatus("paused_human_review") == AnalysisStatus.PAUSED_HUMAN_REVIEW
        )


# ---------------------------------------------------------------------------
# R16 — WorkflowPausedForHumanInput exception
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWorkflowPausedForHumanInput:
    """R16: WorkflowPausedForHumanInput exception exists and carries context."""

    def test_exception_exists_and_carries_workflow_run_id(self):
        from analysi.common.retry_config import WorkflowPausedForHumanInput

        wf_run_id = uuid4()
        exc = WorkflowPausedForHumanInput(str(wf_run_id))
        assert exc.workflow_run_id == str(wf_run_id)
        assert "paused" in str(exc).lower()


# ---------------------------------------------------------------------------
# R16 — WorkflowExecutionStep detects paused workflow
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWorkflowExecutionStepDetectsPaused:
    """R16: WorkflowExecutionStep raises WorkflowPausedForHumanInput on paused workflow."""

    @pytest.mark.asyncio
    async def test_paused_workflow_raises_exception(self):
        """When workflow status is 'paused', step raises WorkflowPausedForHumanInput."""
        from analysi.alert_analysis.steps.workflow_execution import (
            WorkflowExecutionStep,
        )
        from analysi.common.retry_config import WorkflowPausedForHumanInput

        step = WorkflowExecutionStep()
        wf_run_id = uuid4()

        # Patch at the source — execute() lazily imports from analysi.db.session
        with (
            patch.object(
                step, "_prepare_workflow_input", new=AsyncMock(return_value={})
            ),
            patch("analysi.db.session.AsyncSessionLocal") as MockSession,
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor",
            ) as MockExecutor,
        ):
            # Mock session context manager
            mock_session_instance = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            # Mock create_workflow_run
            mock_executor_instance = MagicMock()
            mock_executor_instance.create_workflow_run = AsyncMock(
                return_value=wf_run_id
            )
            MockExecutor.return_value = mock_executor_instance
            mock_session_instance.commit = AsyncMock()

            # Mock _execute_workflow_synchronously (classmethod-style call on the class mock)
            MockExecutor._execute_workflow_synchronously = AsyncMock()

            # Mock the status check — return "paused"
            mock_row = MagicMock()
            mock_row.status = "paused"
            mock_row.error_message = None
            mock_result = MagicMock()
            mock_result.fetchone.return_value = mock_row
            mock_session_instance.execute = AsyncMock(return_value=mock_result)

            with pytest.raises(WorkflowPausedForHumanInput) as exc_info:
                await step.execute("t1", "alert-1", "analysis-1", str(uuid4()))

            assert exc_info.value.workflow_run_id == str(wf_run_id)

    @pytest.mark.asyncio
    async def test_completed_workflow_returns_normally(self):
        """When workflow status is 'completed', step returns workflow_run_id."""
        from analysi.alert_analysis.steps.workflow_execution import (
            WorkflowExecutionStep,
        )

        step = WorkflowExecutionStep()
        wf_run_id = uuid4()

        # Patch at the source — execute() lazily imports from analysi.db.session
        with (
            patch.object(
                step, "_prepare_workflow_input", new=AsyncMock(return_value={})
            ),
            patch("analysi.db.session.AsyncSessionLocal") as MockSession,
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor",
            ) as MockExecutor,
        ):
            mock_session_instance = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(
                return_value=mock_session_instance
            )
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_executor_instance = MagicMock()
            mock_executor_instance.create_workflow_run = AsyncMock(
                return_value=wf_run_id
            )
            MockExecutor.return_value = mock_executor_instance
            mock_session_instance.commit = AsyncMock()

            # Mock _execute_workflow_synchronously (classmethod-style call on the class mock)
            MockExecutor._execute_workflow_synchronously = AsyncMock()

            # Status check returns "completed"
            mock_row = MagicMock()
            mock_row.status = "completed"
            mock_result = MagicMock()
            mock_result.fetchone.return_value = mock_row
            mock_session_instance.execute = AsyncMock(return_value=mock_result)

            result = await step.execute("t1", "alert-1", "analysis-1", str(uuid4()))
            assert result == str(wf_run_id)


# ---------------------------------------------------------------------------
# R16 — Pipeline catches WorkflowPausedForHumanInput
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPipelineCatchesPausedWorkflow:
    """R16: Pipeline catches WorkflowPausedForHumanInput and pauses analysis."""

    @pytest.mark.asyncio
    async def test_pipeline_pauses_on_hitl(self):
        """When workflow pauses for HITL, pipeline sets PAUSED_HUMAN_REVIEW and returns."""
        from analysi.alert_analysis.pipeline import AlertAnalysisPipeline
        from analysi.common.retry_config import WorkflowPausedForHumanInput

        pipeline = AlertAnalysisPipeline(
            tenant_id="t1",
            alert_id="alert-1",
            analysis_id="analysis-1",
        )

        # Mock DB and steps
        pipeline.db = AsyncMock()
        pipeline.db.initialize_steps_progress = AsyncMock()
        pipeline.db.get_alert = AsyncMock(return_value={"alert_id": "alert-1"})

        # Pretriage already done, workflow_builder done
        async def mock_is_step_completed(step_name):
            return step_name in ("pre_triage", "workflow_builder")

        pipeline._is_step_completed = mock_is_step_completed
        pipeline._get_step_result = AsyncMock(return_value="wf-123")
        pipeline._update_status = AsyncMock()

        # Workflow execution raises WorkflowPausedForHumanInput
        wf_run_id = str(uuid4())

        async def mock_execute_workflow_with_retry(workflow_id, alert_data):
            raise WorkflowPausedForHumanInput(wf_run_id)

        pipeline._execute_workflow_with_retry = mock_execute_workflow_with_retry

        result = await pipeline.execute()

        assert result["status"] == "paused_human_review"
        assert "workflow_run_id" in result

        # Should have called _update_status with PAUSED_HUMAN_REVIEW
        pipeline._update_status.assert_any_call(
            AnalysisStatus.PAUSED_HUMAN_REVIEW.value
        )


# ---------------------------------------------------------------------------
# R17 — Worker frees ARQ slot on HITL pause
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWorkerHandlesPausedHumanReview:
    """R17: Worker properly handles paused_human_review result from pipeline."""

    @pytest.mark.asyncio
    async def test_worker_returns_paused_human_review_status(self):
        """Worker returns normally (freeing ARQ slot) when pipeline pauses for HITL."""
        from analysi.alert_analysis.worker import process_alert_analysis

        wf_run_id = str(uuid4())
        pipeline_result = {
            "status": AnalysisStatus.PAUSED_HUMAN_REVIEW.value,
            "workflow_run_id": wf_run_id,
            "message": "Workflow paused waiting for human input",
            "paused_at": datetime.now(UTC).isoformat(),
        }

        with (
            patch("analysi.alert_analysis.worker.AlertAnalysisDB") as MockDB,
            patch("analysi.alert_analysis.worker.BackendAPIClient") as MockAPI,
            patch(
                "analysi.alert_analysis.worker.AlertAnalysisPipeline"
            ) as MockPipeline,
        ):
            # Mock DB
            mock_db = AsyncMock()
            MockDB.return_value = mock_db

            # Mock API client
            mock_api = AsyncMock()
            mock_api.update_analysis_status = AsyncMock(return_value=True)
            mock_api.update_alert_analysis_status = AsyncMock()
            MockAPI.return_value = mock_api

            # Mock pipeline
            mock_pipeline = AsyncMock()
            mock_pipeline.execute = AsyncMock(return_value=pipeline_result)
            MockPipeline.return_value = mock_pipeline

            ctx = {"redis": AsyncMock()}
            result = await process_alert_analysis(ctx, "t1", "alert-1", "analysis-1")

            # Worker should return normally with paused status
            assert result["status"] == "paused_human_review"

            # Should NOT update alert status to completed
            mock_api.update_alert_analysis_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_worker_does_not_mark_alert_completed_on_hitl_pause(self):
        """Worker must not set alert.analysis_status to 'completed' on HITL pause."""
        from analysi.alert_analysis.worker import process_alert_analysis

        pipeline_result = {
            "status": AnalysisStatus.PAUSED_HUMAN_REVIEW.value,
            "workflow_run_id": str(uuid4()),
        }

        with (
            patch("analysi.alert_analysis.worker.AlertAnalysisDB") as MockDB,
            patch("analysi.alert_analysis.worker.BackendAPIClient") as MockAPI,
            patch(
                "analysi.alert_analysis.worker.AlertAnalysisPipeline"
            ) as MockPipeline,
        ):
            mock_db = AsyncMock()
            MockDB.return_value = mock_db

            mock_api = AsyncMock()
            mock_api.update_analysis_status = AsyncMock(return_value=True)
            mock_api.update_alert_analysis_status = AsyncMock()
            MockAPI.return_value = mock_api

            mock_pipeline = AsyncMock()
            mock_pipeline.execute = AsyncMock(return_value=pipeline_result)
            MockPipeline.return_value = mock_pipeline

            ctx = {"redis": AsyncMock()}
            await process_alert_analysis(ctx, "t1", "alert-1", "analysis-1")

            # Verify: update_alert_analysis_status is never called
            # (alert stays as in_progress, not marked completed or failed)
            mock_api.update_alert_analysis_status.assert_not_called()


# ---------------------------------------------------------------------------
# R18 — Reconciliation detects stuck HITL-paused analyses
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReconciliationHandlesPausedHumanReview:
    """R18: Reconciliation detects and fails expired HITL-paused analyses."""

    @pytest.mark.asyncio
    async def test_expired_hitl_pause_is_marked_failed(self):
        """Analysis paused for HITL beyond timeout is marked as failed."""
        from analysi.alert_analysis.jobs.reconciliation import (
            mark_expired_hitl_paused_analyses,
        )

        # Create a mock analysis that's been paused for >24 hours
        mock_analysis = MagicMock()
        mock_analysis.id = uuid4()
        mock_analysis.alert_id = uuid4()
        mock_analysis.tenant_id = "t1"
        mock_analysis.status = "paused_human_review"
        mock_analysis.updated_at = datetime.now(UTC) - timedelta(hours=25)

        mock_analysis_repo = AsyncMock()
        mock_analysis_repo.find_paused_for_human_review.return_value = [mock_analysis]
        mock_analysis_repo.mark_failed = AsyncMock()

        mock_alert_repo = AsyncMock()
        mock_alert_repo.mark_stuck_alert_failed = AsyncMock(return_value=True)

        count = await mark_expired_hitl_paused_analyses(
            mock_analysis_repo, mock_alert_repo, timeout_hours=24
        )

        assert count == 1
        mock_analysis_repo.mark_failed.assert_called_once()
        # Verify the error message mentions HITL timeout
        call_kwargs = mock_analysis_repo.mark_failed.call_args.kwargs
        assert (
            "human" in call_kwargs["error_message"].lower()
            or "HITL" in call_kwargs["error_message"]
        )

    @pytest.mark.asyncio
    async def test_recent_hitl_pause_is_not_marked_failed(self):
        """Analysis paused for HITL within timeout is left alone."""
        from analysi.alert_analysis.jobs.reconciliation import (
            mark_expired_hitl_paused_analyses,
        )

        # Create a mock analysis that's been paused for only 1 hour
        mock_analysis = MagicMock()
        mock_analysis.id = uuid4()
        mock_analysis.alert_id = uuid4()
        mock_analysis.tenant_id = "t1"
        mock_analysis.status = "paused_human_review"
        mock_analysis.updated_at = datetime.now(UTC) - timedelta(hours=1)

        mock_analysis_repo = AsyncMock()
        mock_analysis_repo.find_paused_for_human_review.return_value = [mock_analysis]

        mock_alert_repo = AsyncMock()

        count = await mark_expired_hitl_paused_analyses(
            mock_analysis_repo, mock_alert_repo, timeout_hours=24
        )

        assert count == 0
        mock_analysis_repo.mark_failed.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_hitl_paused_analyses(self):
        """When no HITL-paused analyses exist, returns zero."""
        from analysi.alert_analysis.jobs.reconciliation import (
            mark_expired_hitl_paused_analyses,
        )

        mock_analysis_repo = AsyncMock()
        mock_analysis_repo.find_paused_for_human_review.return_value = []

        mock_alert_repo = AsyncMock()

        count = await mark_expired_hitl_paused_analyses(
            mock_analysis_repo, mock_alert_repo, timeout_hours=24
        )

        assert count == 0
