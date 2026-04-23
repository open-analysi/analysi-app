"""
Integration tests for HITL analysis pipeline resume.

Exercises the real DB path for the fix where pipeline step 4 never ran
after HITL resume.  Tests use PostgreSQL to verify:

  1. Step 3 checkpoint survives a DB round-trip (JSONB → read back → correct).
  2. Pipeline._is_step_completed reads the checkpoint and skips step 3.
  3. Pipeline._get_step_result returns the checkpointed workflow_run_id.
  4. Full pipeline re-entry: steps 1-3 skipped, step 4 executes.
  5. Corner case: checkpoint written during HITL pause is not lost if
     the pipeline also set step 3 as "failed" (exception path).
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from analysi.alert_analysis.db import AlertAnalysisDB
from analysi.models.alert import Alert, AlertAnalysis
from analysi.schemas.alert import (
    PipelineStep,
    PipelineStepsProgress,
    StepStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT_ID = f"hitl-resume-intg-{uuid.uuid4().hex[:8]}"


async def _create_alert_and_analysis(
    session,
    *,
    status: str = "running",
    steps_progress: dict | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create an Alert + AlertAnalysis in the test DB, return (alert_id, analysis_id)."""
    alert_id = uuid.uuid4()
    now = datetime.now(UTC)
    alert = Alert(
        id=alert_id,
        tenant_id=TENANT_ID,
        human_readable_id=f"HITL-{uuid.uuid4().hex[:8]}",
        title="HITL Resume Test Alert",
        severity="high",
        analysis_status="in_progress",
        rule_name="test-rule",
        triggering_event_time=now - timedelta(minutes=10),
        raw_data='{"test": true}',
        raw_data_hash=f"hash-{uuid.uuid4().hex[:8]}",
        raw_data_hash_algorithm="SHA-256",
        finding_info={},
        ocsf_metadata={},
        severity_id=4,
        status_id=1,
        created_at=now - timedelta(minutes=5),
        updated_at=now,
    )
    session.add(alert)
    await session.flush()

    analysis_id = uuid.uuid4()
    analysis = AlertAnalysis(
        id=analysis_id,
        alert_id=alert.id,
        tenant_id=TENANT_ID,
        status=status,
        steps_progress=steps_progress or {},
        started_at=now - timedelta(minutes=4),
        created_at=now - timedelta(minutes=4),
        updated_at=now,
    )
    session.add(analysis)
    await session.commit()
    return alert_id, analysis_id


# ---------------------------------------------------------------------------
# 1. Checkpoint round-trip through PostgreSQL JSONB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
class TestStep3CheckpointDBRoundTrip:
    """Step 3 checkpoint written by pipeline survives JSONB round-trip."""

    async def test_checkpoint_written_and_read_back(self, integration_test_session):
        """update_step_progress(completed=True, result={workflow_run_id: X})
        persists to JSONB and is readable via get_step_progress."""
        session = integration_test_session
        _, analysis_id = await _create_alert_and_analysis(session)

        # Initialize steps (as the pipeline does)
        db = AlertAnalysisDB(session=session)
        await db.initialize_steps_progress(str(analysis_id))

        # Write checkpoint — same call the pipeline makes on HITL pause
        wf_run_id = str(uuid.uuid4())
        await db.update_step_progress(
            str(analysis_id),
            "workflow_execution",
            completed=True,
            result={"workflow_run_id": wf_run_id},
        )

        # Read back
        session.expire_all()
        progress = await db.get_step_progress(str(analysis_id))

        # Verify via PipelineStepsProgress (same path as pipeline._is_step_completed)
        parsed = PipelineStepsProgress.from_dict(progress)
        step = parsed.get_step(PipelineStep("workflow_execution"))
        assert step is not None
        assert step.status == StepStatus.COMPLETED
        assert step.result == {"workflow_run_id": wf_run_id}

    async def test_checkpoint_overrides_prior_failed_status(
        self, integration_test_session
    ):
        """When _execute_step marks step 3 as failed (exception path) and then
        the pipeline's HITL handler overwrites with completed, the final
        state in DB must be completed with the workflow_run_id."""
        session = integration_test_session
        _, analysis_id = await _create_alert_and_analysis(session)

        db = AlertAnalysisDB(session=session)
        await db.initialize_steps_progress(str(analysis_id))

        # Simulate _execute_step marking the step as failed
        await db.update_step_progress(
            str(analysis_id),
            "workflow_execution",
            completed=False,
            error="WorkflowPausedForHumanInput",
        )

        # Now the HITL handler overwrites with completed + result
        wf_run_id = str(uuid.uuid4())
        await db.update_step_progress(
            str(analysis_id),
            "workflow_execution",
            completed=True,
            result={"workflow_run_id": wf_run_id},
        )

        # Verify final state is completed (not failed)
        session.expire_all()
        progress = await db.get_step_progress(str(analysis_id))
        parsed = PipelineStepsProgress.from_dict(progress)
        step = parsed.get_step(PipelineStep("workflow_execution"))
        assert step.status == StepStatus.COMPLETED
        assert step.result == {"workflow_run_id": wf_run_id}


# ---------------------------------------------------------------------------
# 2. Pipeline re-entry skips to step 4
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
class TestPipelineReentrySkipsToStep4:
    """When the pipeline is re-queued after HITL, it reads the checkpoint
    from the real DB and skips steps 1-3."""

    @pytest.fixture(autouse=True)
    def _mock_http_clients(self):
        """Mock HTTP clients — pipeline uses REST API for status updates."""
        mock_api = AsyncMock()
        mock_api.update_analysis_status = AsyncMock(return_value=True)
        mock_api.update_alert_analysis_status = AsyncMock(return_value=True)
        with (
            patch(
                "analysi.alert_analysis.clients.BackendAPIClient",
                return_value=mock_api,
            ),
            patch(
                "analysi.alert_analysis.pipeline.InternalAsyncClient",
            ) as mock_internal,
        ):
            mock_ctx = AsyncMock()
            mock_internal.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_internal.return_value.__aexit__ = AsyncMock(return_value=False)
            yield

    async def test_pipeline_skips_steps_123_runs_step4(self, integration_test_session):
        """Pipeline with checkpointed steps 1-3 only executes step 4."""
        from analysi.alert_analysis.pipeline import AlertAnalysisPipeline

        session = integration_test_session
        alert_id, analysis_id = await _create_alert_and_analysis(session)
        wf_run_id = str(uuid.uuid4())

        # Set up step progress: steps 1-3 completed (as checkpoint does)
        db = AlertAnalysisDB(session=session)
        await db.initialize_steps_progress(str(analysis_id))
        # Step 1
        await db.update_step_progress(str(analysis_id), "pre_triage", completed=True)
        # Step 2
        await db.update_step_progress(
            str(analysis_id),
            "workflow_builder",
            completed=True,
            result={"selected_workflow": "test-wf"},
        )
        # Step 3 (checkpointed on HITL pause)
        await db.update_step_progress(
            str(analysis_id),
            "workflow_execution",
            completed=True,
            result={"workflow_run_id": wf_run_id},
        )

        # Create pipeline with real DB
        pipeline = AlertAnalysisPipeline(
            tenant_id=TENANT_ID,
            alert_id=str(alert_id),
            analysis_id=str(analysis_id),
        )
        pipeline.db = db

        # Track which steps execute
        mock_disposition = AsyncMock()
        mock_disposition.execute = AsyncMock(return_value="disposition-done")
        mock_pre_triage = AsyncMock()
        mock_pre_triage.execute = AsyncMock()
        mock_wf_builder = AsyncMock()
        mock_wf_builder.execute = AsyncMock()
        mock_wf_execution = AsyncMock()
        mock_wf_execution.execute = AsyncMock()

        pipeline.steps = {
            "pre_triage": mock_pre_triage,
            "workflow_builder": mock_wf_builder,
            "workflow_execution": mock_wf_execution,
            "final_disposition_update": mock_disposition,
        }

        result = await pipeline.execute()

        # Steps 1-3 NOT called (completed in DB)
        mock_pre_triage.execute.assert_not_awaited()
        mock_wf_builder.execute.assert_not_awaited()
        mock_wf_execution.execute.assert_not_awaited()

        # Step 4 called with checkpointed workflow_run_id
        mock_disposition.execute.assert_awaited_once()
        call_kwargs = mock_disposition.execute.call_args.kwargs
        assert call_kwargs["workflow_run_id"] == wf_run_id

        assert result["status"] == "completed"

    async def test_pipeline_reentry_with_only_step3_checkpointed(
        self, integration_test_session
    ):
        """When only step 3 is checkpointed (steps 1-2 also completed from
        the original run), the pipeline correctly reads all three and skips
        to step 4."""
        from analysi.alert_analysis.pipeline import AlertAnalysisPipeline

        session = integration_test_session
        alert_id, analysis_id = await _create_alert_and_analysis(session)
        wf_run_id = str(uuid.uuid4())
        wf_name = "Investigation Workflow"

        # Simulate the state after original run + HITL pause:
        # Steps 1 & 2 completed by _execute_step, step 3 checkpointed by HITL handler
        db = AlertAnalysisDB(session=session)
        await db.initialize_steps_progress(str(analysis_id))
        await db.update_step_progress(str(analysis_id), "pre_triage", completed=True)
        await db.update_step_progress(
            str(analysis_id),
            "workflow_builder",
            completed=True,
            result={"selected_workflow": wf_name},
        )
        await db.update_step_progress(
            str(analysis_id),
            "workflow_execution",
            completed=True,
            result={"workflow_run_id": wf_run_id},
        )

        pipeline = AlertAnalysisPipeline(
            tenant_id=TENANT_ID,
            alert_id=str(alert_id),
            analysis_id=str(analysis_id),
        )
        pipeline.db = db

        mock_disposition = AsyncMock()
        mock_disposition.execute = AsyncMock(return_value="ok")

        pipeline.steps = {
            "pre_triage": AsyncMock(execute=AsyncMock()),
            "workflow_builder": AsyncMock(execute=AsyncMock()),
            "workflow_execution": AsyncMock(execute=AsyncMock()),
            "final_disposition_update": mock_disposition,
        }

        result = await pipeline.execute()

        # Step 4 receives both workflow_id (from step 2) and workflow_run_id (from step 3)
        call_kwargs = mock_disposition.execute.call_args.kwargs
        assert call_kwargs["workflow_run_id"] == wf_run_id
        assert call_kwargs["workflow_id"] == wf_name
        assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# 3. _requeue_pipeline_after_hitl loads analysis from DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
class TestRequeuePipelineLoadsAnalysis:
    """_requeue_pipeline_after_hitl must load the analysis from DB to get
    the alert_id for the pipeline job signature."""

    async def test_requeue_reads_alert_id_from_analysis(self, integration_test_session):
        """Enqueue call receives the correct alert_id from the DB."""
        from analysi.alert_analysis.jobs.control_events import (
            _requeue_pipeline_after_hitl,
        )

        session = integration_test_session
        alert_id, analysis_id = await _create_alert_and_analysis(session)

        with (
            patch("analysi.db.session.AsyncSessionLocal") as MockSession,
            patch(
                "analysi.common.arq_enqueue.enqueue_arq_job",
                new_callable=AsyncMock,
            ) as mock_enqueue,
        ):
            # Use the real test session for the DB lookup
            MockSession.return_value.__aenter__ = AsyncMock(return_value=session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            await _requeue_pipeline_after_hitl(
                analysis_id=analysis_id,
                tenant_id=TENANT_ID,
            )

            mock_enqueue.assert_awaited_once_with(
                "analysi.alert_analysis.worker.process_alert_analysis",
                TENANT_ID,
                str(alert_id),
                str(analysis_id),
            )

    async def test_requeue_handles_missing_analysis_gracefully(
        self, integration_test_session
    ):
        """If analysis doesn't exist, log error but don't raise."""
        from analysi.alert_analysis.jobs.control_events import (
            _requeue_pipeline_after_hitl,
        )

        session = integration_test_session

        with (
            patch("analysi.db.session.AsyncSessionLocal") as MockSession,
            patch(
                "analysi.common.arq_enqueue.enqueue_arq_job",
                new_callable=AsyncMock,
            ) as mock_enqueue,
        ):
            MockSession.return_value.__aenter__ = AsyncMock(return_value=session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            # Non-existent analysis — should not raise
            await _requeue_pipeline_after_hitl(
                analysis_id=uuid.uuid4(),
                tenant_id=TENANT_ID,
            )

            # Should NOT have enqueued anything
            mock_enqueue.assert_not_awaited()

    async def test_enqueue_failure_propagates_as_exception(
        self, integration_test_session
    ):
        """If enqueue_arq_job raises (e.g., Valkey down), the exception must
        propagate so the control event can be retried.  The analysis status
        should NOT have been touched (still paused_human_review)."""
        from analysi.alert_analysis.jobs.control_events import (
            _requeue_pipeline_after_hitl,
        )

        session = integration_test_session
        _, analysis_id = await _create_alert_and_analysis(
            session, status="paused_human_review"
        )

        with (
            patch("analysi.db.session.AsyncSessionLocal") as MockSession,
            patch(
                "analysi.common.arq_enqueue.enqueue_arq_job",
                new_callable=AsyncMock,
                side_effect=ConnectionError("Valkey unavailable"),
            ),
        ):
            MockSession.return_value.__aenter__ = AsyncMock(return_value=session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(ConnectionError, match="Valkey unavailable"):
                await _requeue_pipeline_after_hitl(
                    analysis_id=analysis_id,
                    tenant_id=TENANT_ID,
                )

        # Analysis must still be paused_human_review (not "running")
        session.expire_all()
        from sqlalchemy import select

        from analysi.models.alert import AlertAnalysis

        result = await session.execute(
            select(AlertAnalysis.status).where(AlertAnalysis.id == analysis_id)
        )
        status = result.scalar_one()
        assert status == "paused_human_review", (
            f"Expected paused_human_review after enqueue failure, got {status}"
        )


# ---------------------------------------------------------------------------
# 4. Enqueue ordering: enqueue before mark-running
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.integration
class TestEnqueueOrderingSafety:
    """The re-queue must happen BEFORE marking analysis as 'running'.
    This ensures that if enqueue fails, the analysis stays in
    paused_human_review for safe retry."""

    async def test_successful_requeue_then_mark_running(self, integration_test_session):
        """After successful enqueue, analysis transitions to running."""
        from analysi.alert_analysis.jobs.control_events import (
            _requeue_pipeline_after_hitl,
            _update_analysis_after_hitl,
        )

        session = integration_test_session
        _, analysis_id = await _create_alert_and_analysis(
            session, status="paused_human_review"
        )

        with (
            patch("analysi.db.session.AsyncSessionLocal") as MockSession,
            patch(
                "analysi.common.arq_enqueue.enqueue_arq_job",
                new_callable=AsyncMock,
                return_value="job-123",
            ),
        ):
            MockSession.return_value.__aenter__ = AsyncMock(return_value=session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            # Step 1: enqueue (should succeed)
            await _requeue_pipeline_after_hitl(
                analysis_id=analysis_id,
                tenant_id=TENANT_ID,
            )

        # Step 2: mark running (same pattern as handle_human_responded)
        with patch("analysi.db.session.AsyncSessionLocal") as MockSession:
            MockSession.return_value.__aenter__ = AsyncMock(return_value=session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            await _update_analysis_after_hitl(
                analysis_id=analysis_id,
                tenant_id=TENANT_ID,
                status="running",
            )

        # Verify final state
        session.expire_all()
        from sqlalchemy import select

        from analysi.models.alert import AlertAnalysis

        result = await session.execute(
            select(AlertAnalysis.status).where(AlertAnalysis.id == analysis_id)
        )
        status = result.scalar_one()
        assert status == "running"
