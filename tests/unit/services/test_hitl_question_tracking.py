"""
Unit tests for HITL Question Tracking.

Tests R19-R20, R26-R29: hitl_questions table, question creation on task pause,
human:responded control event handler, internal channel dispatch.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.constants import HITLQuestionConstants

# ---------------------------------------------------------------------------
# R19 — HITLQuestionConstants
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHITLQuestionConstants:
    """R19: HITL question status constants and channel name."""

    def test_status_values(self):
        assert HITLQuestionConstants.Status.PENDING == "pending"
        assert HITLQuestionConstants.Status.ANSWERED == "answered"
        assert HITLQuestionConstants.Status.EXPIRED == "expired"

    def test_channel_name(self):
        assert HITLQuestionConstants.CHANNEL_HUMAN_RESPONDED == "human:responded"

    def test_default_timeout(self):
        assert HITLQuestionConstants.DEFAULT_TIMEOUT_HOURS == 4


# ---------------------------------------------------------------------------
# R19 — HITLQuestionRepository
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHITLQuestionRepository:
    """R19: Repository CRUD operations for HITL questions."""

    @pytest.mark.asyncio
    async def test_create_question(self):
        """create() stores all fields and returns the question."""
        from analysi.repositories.hitl_repository import HITLQuestionRepository

        mock_session = AsyncMock()
        repo = HITLQuestionRepository(mock_session)

        task_run_id = uuid4()
        timeout = datetime.now(UTC) + timedelta(hours=4)

        question = await repo.create(
            tenant_id="t1",
            question_ref="1234567890.123456",
            channel="C12345",
            question_text="Should we escalate?",
            options=[{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}],
            timeout_at=timeout,
            task_run_id=task_run_id,
        )

        assert question.tenant_id == "t1"
        assert question.question_ref == "1234567890.123456"
        assert question.channel == "C12345"
        assert question.question_text == "Should we escalate?"
        assert len(question.options) == 2
        assert question.task_run_id == task_run_id
        assert question.status == "pending"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_with_workflow_context(self):
        """create() with workflow/analysis context stores all references."""
        from analysi.repositories.hitl_repository import HITLQuestionRepository

        mock_session = AsyncMock()
        repo = HITLQuestionRepository(mock_session)

        task_run_id = uuid4()
        workflow_run_id = uuid4()
        node_instance_id = uuid4()
        analysis_id = uuid4()

        question = await repo.create(
            tenant_id="t1",
            question_ref="ts-1",
            channel="C1",
            question_text="Approve?",
            options=[{"value": "approve"}],
            timeout_at=datetime.now(UTC) + timedelta(hours=4),
            task_run_id=task_run_id,
            workflow_run_id=workflow_run_id,
            node_instance_id=node_instance_id,
            analysis_id=analysis_id,
        )

        assert question.workflow_run_id == workflow_run_id
        assert question.node_instance_id == node_instance_id
        assert question.analysis_id == analysis_id

    @pytest.mark.asyncio
    async def test_record_answer_pending_question(self):
        """record_answer() updates status to answered when question is pending."""
        from analysi.repositories.hitl_repository import HITLQuestionRepository

        mock_session = AsyncMock()
        # Mock the execute result to indicate 1 row updated
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = HITLQuestionRepository(mock_session)
        question_id = uuid4()

        result = await repo.record_answer(question_id, "Escalate", "U123")
        assert result is True

    @pytest.mark.asyncio
    async def test_record_answer_already_answered(self):
        """record_answer() returns False for already-answered questions."""
        from analysi.repositories.hitl_repository import HITLQuestionRepository

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0  # No rows updated — question not pending
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = HITLQuestionRepository(mock_session)
        result = await repo.record_answer(uuid4(), "Escalate", "U123")
        assert result is False


# ---------------------------------------------------------------------------
# R26 — Internal channel dispatch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInternalChannelDispatch:
    """R26: Internal channels are dispatched to handlers, not fan-out rules."""

    def test_human_responded_is_internal(self):
        """human:responded channel exists in INTERNAL_HANDLERS."""
        from analysi.alert_analysis.jobs.control_events import INTERNAL_HANDLERS

        assert "human:responded" in INTERNAL_HANDLERS

    def test_internal_handler_is_callable(self):
        """Internal handler is an async callable."""
        from analysi.alert_analysis.jobs.control_events import INTERNAL_HANDLERS

        handler = INTERNAL_HANDLERS["human:responded"]
        assert callable(handler)


# ---------------------------------------------------------------------------
# R28 — handle_human_responded with workflow context
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHandleHumanRespondedWorkflow:
    """R28: Handler resumes task and continues workflow when human answers."""

    @pytest.mark.asyncio
    async def test_handler_resumes_workflow_task(self):
        """Handler resumes task, then calls continue_after_hitl for workflow."""
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        question_id = uuid4()
        task_run_id = uuid4()
        workflow_run_id = uuid4()
        node_instance_id = uuid4()
        analysis_id = uuid4()

        # Mock the question
        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.task_run_id = task_run_id
        mock_question.workflow_run_id = workflow_run_id
        mock_question.node_instance_id = node_instance_id
        mock_question.analysis_id = analysis_id
        mock_question.answer = "Escalate"
        mock_question.status = "answered"

        # Mock event
        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answer": "Escalate",
            "answered_by": "U123",
        }

        # Patch at source — handler lazily imports these
        with (
            patch("analysi.db.session.AsyncSessionLocal") as MockSession,
            patch(
                "analysi.services.task_execution.TaskExecutionService"
            ) as MockTaskExec,
            patch("analysi.services.workflow_execution.WorkflowExecutor") as MockWfExec,
            patch(
                "analysi.repositories.hitl_repository.HITLQuestionRepository"
            ) as MockRepo,
            patch(
                "analysi.alert_analysis.jobs.control_events._update_analysis_after_hitl",
                new_callable=AsyncMock,
            ),
            patch(
                "analysi.alert_analysis.jobs.control_events._requeue_pipeline_after_hitl",
                new_callable=AsyncMock,
            ),
        ):
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            # Mock repo to return question
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo_instance

            # Mock TaskExecutionService.resume_paused_task
            mock_task_svc = AsyncMock()
            mock_task_result = MagicMock()
            mock_task_result.status = "completed"
            mock_task_svc.resume_paused_task = AsyncMock(return_value=mock_task_result)
            MockTaskExec.return_value = mock_task_svc

            # Mock continue_after_hitl (replaces _execute_workflow_synchronously)
            MockWfExec.continue_after_hitl = AsyncMock()

            await handle_human_responded(mock_event)

            # Task resume should have been called
            mock_task_svc.resume_paused_task.assert_awaited_once()

            # Workflow should continue via continue_after_hitl
            MockWfExec.continue_after_hitl.assert_awaited_once_with(
                workflow_run_id=workflow_run_id,
                node_instance_id=node_instance_id,
                task_result=mock_task_result,
            )


# ---------------------------------------------------------------------------
# R29 — handle_human_responded standalone task (no workflow)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHandleHumanRespondedStandalone:
    """R29: Handler resumes standalone task and persists result (no workflow)."""

    @pytest.mark.asyncio
    async def test_handler_resumes_standalone_task_and_persists_result(self):
        """Handler resumes task and persists COMPLETED status for standalone task."""
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        question_id = uuid4()
        task_run_id = uuid4()

        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.task_run_id = task_run_id
        mock_question.workflow_run_id = None  # Standalone task
        mock_question.node_instance_id = None
        mock_question.analysis_id = None
        mock_question.answer = "Approve"
        mock_question.status = "answered"

        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answer": "Approve",
            "answered_by": "U456",
        }

        # Patch at source — handler lazily imports these
        with (
            patch("analysi.db.session.AsyncSessionLocal") as MockSession,
            patch(
                "analysi.services.task_execution.TaskExecutionService"
            ) as MockTaskExec,
            patch(
                "analysi.repositories.hitl_repository.HITLQuestionRepository"
            ) as MockRepo,
            patch("analysi.services.task_run.TaskRunService") as MockTaskRunSvc,
        ):
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo_instance

            mock_task_svc = AsyncMock()
            mock_task_result = MagicMock()
            mock_task_result.status = "completed"
            mock_task_result.task_run_id = task_run_id
            mock_task_result.output_data = {"result": "Approved"}
            mock_task_result.llm_usage = None
            mock_task_result.error_message = None
            mock_task_svc.resume_paused_task = AsyncMock(return_value=mock_task_result)
            MockTaskExec.return_value = mock_task_svc

            mock_task_run_svc = AsyncMock()
            MockTaskRunSvc.return_value = mock_task_run_svc

            await handle_human_responded(mock_event)

            # Task resume should have been called
            mock_task_svc.resume_paused_task.assert_awaited_once()

            # Task result should be persisted
            mock_task_run_svc.update_status.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handler_raises_on_missing_question(self):
        """Handler raises ValueError when question not found (Bug #6 fix)."""
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(uuid4()),
            "answer": "Approve",
        }

        # Patch at source — handler lazily imports these
        with (
            patch("analysi.db.session.AsyncSessionLocal") as MockSession,
            patch(
                "analysi.repositories.hitl_repository.HITLQuestionRepository"
            ) as MockRepo,
        ):
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_id = AsyncMock(return_value=None)
            MockRepo.return_value = mock_repo_instance

            # Bug #6 fix: Must raise ValueError so control event is marked failed
            with pytest.raises(ValueError, match="not found"):
                await handle_human_responded(mock_event)


# ---------------------------------------------------------------------------
# R20 — create_question_from_checkpoint helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateQuestionFromCheckpoint:
    """R20: Extracting HITL question from checkpoint data."""

    @pytest.mark.asyncio
    async def test_extracts_tool_args_and_creates_question(self):
        """create_question_from_checkpoint extracts pending_tool_args fields."""
        from analysi.repositories.hitl_repository import (
            create_question_from_checkpoint,
        )

        mock_session = AsyncMock()
        task_run_id = uuid4()

        checkpoint_data = {
            "pending_tool_name": "slack_ask",
            "pending_tool_args": {
                "channel": "C12345",
                "text": "Should we escalate?",
                "options": [
                    {"value": "yes", "label": "Yes"},
                    {"value": "no", "label": "No"},
                ],
                "question_ref": "1234567890.123456",
            },
            "pending_tool_result": None,
            "node_results": {},
            "pending_node_id": "node_3",
            "variables": {},
            "plan_version": "1",
        }

        question = await create_question_from_checkpoint(
            session=mock_session,
            tenant_id="t1",
            task_run_id=task_run_id,
            checkpoint_data=checkpoint_data,
        )

        assert question is not None
        assert question.channel == "C12345"
        assert question.question_text == "Should we escalate?"
        assert len(question.options) == 2
        assert question.question_ref == "1234567890.123456"
        assert question.task_run_id == task_run_id
        assert question.workflow_run_id is None
        assert question.status == "pending"
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_tool_args(self):
        """Returns None when pending_tool_args is empty or missing."""
        from analysi.repositories.hitl_repository import (
            create_question_from_checkpoint,
        )

        mock_session = AsyncMock()

        result = await create_question_from_checkpoint(
            session=mock_session,
            tenant_id="t1",
            task_run_id=uuid4(),
            checkpoint_data={"pending_tool_args": {}, "pending_node_id": "n1"},
        )

        assert result is None
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_includes_workflow_and_analysis_context(self):
        """Creates question with full workflow/analysis context when provided."""
        from analysi.repositories.hitl_repository import (
            create_question_from_checkpoint,
        )

        mock_session = AsyncMock()
        task_run_id = uuid4()
        workflow_run_id = uuid4()
        node_instance_id = uuid4()
        analysis_id = uuid4()

        checkpoint_data = {
            "pending_tool_name": "slack_ask",
            "pending_tool_args": {
                "channel": "C999",
                "text": "Approve containment?",
                "options": [{"value": "approve"}, {"value": "deny"}],
            },
        }

        question = await create_question_from_checkpoint(
            session=mock_session,
            tenant_id="t1",
            task_run_id=task_run_id,
            checkpoint_data=checkpoint_data,
            workflow_run_id=workflow_run_id,
            node_instance_id=node_instance_id,
            analysis_id=analysis_id,
        )

        assert question.workflow_run_id == workflow_run_id
        assert question.node_instance_id == node_instance_id
        assert question.analysis_id == analysis_id
        assert question.question_ref == ""  # No question_ref in args

    @pytest.mark.asyncio
    async def test_uses_question_text_field_fallback(self):
        """Handles 'question_text' key in addition to 'text'."""
        from analysi.repositories.hitl_repository import (
            create_question_from_checkpoint,
        )

        mock_session = AsyncMock()

        checkpoint_data = {
            "pending_tool_name": "slack_ask",
            "pending_tool_args": {
                "channel": "C1",
                "question_text": "Escalate to Tier 2?",
                "options": [{"value": "yes"}],
            },
        }

        question = await create_question_from_checkpoint(
            session=mock_session,
            tenant_id="t1",
            task_run_id=uuid4(),
            checkpoint_data=checkpoint_data,
        )

        assert question.question_text == "Escalate to Tier 2?"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_pending_tool_args_key(self):
        """Returns None when checkpoint_data has no pending_tool_args key at all."""
        from analysi.repositories.hitl_repository import (
            create_question_from_checkpoint,
        )

        mock_session = AsyncMock()

        result = await create_question_from_checkpoint(
            session=mock_session,
            tenant_id="t1",
            task_run_id=uuid4(),
            checkpoint_data={"pending_node_id": "n1", "node_results": {}},
        )

        assert result is None
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_with_missing_channel(self):
        """Returns None when tool args have no channel (Bug #10 fix)."""
        from analysi.repositories.hitl_repository import (
            create_question_from_checkpoint,
        )

        mock_session = AsyncMock()

        # pending_tool_args has content (so it's truthy) but no channel
        checkpoint_data = {
            "pending_tool_name": "custom_ask",
            "pending_tool_args": {"custom_field": "value"},
        }

        question = await create_question_from_checkpoint(
            session=mock_session,
            tenant_id="t1",
            task_run_id=uuid4(),
            checkpoint_data=checkpoint_data,
        )

        # Bug #10: Must return None when channel is missing
        assert question is None
        mock_session.add.assert_not_called()


# ---------------------------------------------------------------------------
# resume_paused_workflow — Project Kalymnos
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResumePausedWorkflow:
    """WorkflowExecutor.resume_paused_workflow guard clauses and happy path."""

    @pytest.mark.asyncio
    async def test_resume_workflow_not_found_raises(self):
        """ValueError when workflow_run_id does not exist."""
        from analysi.services.workflow_execution import WorkflowExecutor

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        executor = WorkflowExecutor(mock_session)
        executor.node_repo = AsyncMock()

        with pytest.raises(ValueError, match="not found"):
            await executor.resume_paused_workflow(uuid4())

    @pytest.mark.asyncio
    async def test_resume_workflow_not_paused_raises(self):
        """ValueError when workflow is running instead of paused."""
        from analysi.services.workflow_execution import WorkflowExecutor

        wf_run = MagicMock()
        wf_run.status = "running"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = wf_run
        mock_session.execute = AsyncMock(return_value=mock_result)

        executor = WorkflowExecutor(mock_session)
        executor.node_repo = AsyncMock()

        with pytest.raises(ValueError, match="not paused"):
            await executor.resume_paused_workflow(uuid4())

    @pytest.mark.asyncio
    async def test_resume_resets_paused_nodes_to_pending(self):
        """All paused nodes are reset to PENDING before re-entering monitor."""
        from analysi.constants import WorkflowConstants
        from analysi.services.workflow_execution import WorkflowExecutor

        wf_run_id = uuid4()
        wf_run = MagicMock()
        wf_run.id = wf_run_id
        wf_run.status = WorkflowConstants.Status.PAUSED

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = wf_run
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Two paused nodes
        node_a = MagicMock()
        node_a.id = uuid4()
        node_a.node_id = "enrich_ip"
        node_b = MagicMock()
        node_b.id = uuid4()
        node_b.node_id = "ask_analyst"

        executor = WorkflowExecutor(mock_session)
        executor.node_repo = AsyncMock()
        executor.node_repo.list_node_instances = AsyncMock(
            return_value=[node_a, node_b]
        )
        executor.monitor_execution = AsyncMock()  # Prevent real execution

        await executor.resume_paused_workflow(wf_run_id)

        # Both nodes should be reset to PENDING
        calls = executor.node_repo.update_node_instance_status.call_args_list
        assert len(calls) == 2
        assert calls[0][0] == (node_a.id, WorkflowConstants.Status.PENDING)
        assert calls[1][0] == (node_b.id, WorkflowConstants.Status.PENDING)

        # monitor_execution should be re-entered
        executor.monitor_execution.assert_awaited_once_with(wf_run_id)


# ---------------------------------------------------------------------------
# Many HITL — concurrency and batch scenarios
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestManyHITLExpiry:
    """mark_expired_hitl_paused_analyses with mixed expired/recent batch."""

    @pytest.mark.asyncio
    async def test_mixed_expired_and_recent_batch(self):
        """5 analyses: 3 expired, 2 recent → exactly 3 marked failed."""
        from analysi.alert_analysis.jobs.reconciliation import (
            mark_expired_hitl_paused_analyses,
        )

        now = datetime.now(UTC)
        expired_time = now - timedelta(hours=30)
        recent_time = now - timedelta(hours=1)

        # Build 5 analyses: 3 expired, 2 recent
        analyses = []
        for i in range(5):
            a = MagicMock()
            a.id = uuid4()
            a.tenant_id = f"tenant-{i}"
            a.alert_id = uuid4()
            a.updated_at = expired_time if i < 3 else recent_time
            analyses.append(a)

        analysis_repo = AsyncMock()
        analysis_repo.find_paused_for_human_review = AsyncMock(return_value=analyses)
        analysis_repo.mark_failed = AsyncMock()

        alert_repo = AsyncMock()

        count = await mark_expired_hitl_paused_analyses(
            analysis_repo, alert_repo, timeout_hours=24
        )

        assert count == 3
        assert analysis_repo.mark_failed.await_count == 3
        # Bug #24: direct Alert UPDATE via session.execute (replaces mark_stuck_alert_failed)
        assert analysis_repo.session.execute.await_count >= 3
        assert analysis_repo.session.commit.await_count >= 3

    @pytest.mark.asyncio
    async def test_partial_failure_in_large_batch(self):
        """In a batch of 4 expired, one mark_failed raises → still processes the rest."""
        from analysi.alert_analysis.jobs.reconciliation import (
            mark_expired_hitl_paused_analyses,
        )

        now = datetime.now(UTC)
        expired_time = now - timedelta(hours=30)

        analyses = []
        for i in range(4):
            a = MagicMock()
            a.id = uuid4()
            a.tenant_id = f"tenant-{i}"
            a.alert_id = uuid4()
            a.updated_at = expired_time
            analyses.append(a)

        analysis_repo = AsyncMock()
        analysis_repo.find_paused_for_human_review = AsyncMock(return_value=analyses)
        # Second call raises, others succeed
        analysis_repo.mark_failed = AsyncMock(
            side_effect=[None, RuntimeError("DB error"), None, None]
        )

        alert_repo = AsyncMock()

        count = await mark_expired_hitl_paused_analyses(
            analysis_repo, alert_repo, timeout_hours=24
        )

        # 3 succeeded, 1 failed — count should be 3
        assert count == 3
        assert analysis_repo.mark_failed.await_count == 4  # All 4 attempted


# ---------------------------------------------------------------------------
# resume_paused_task — session commit fix (Bug 2)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResumePausedTaskCommit:
    """resume_paused_task commits (not just flushes) before re-executing."""

    @pytest.mark.asyncio
    async def test_resume_commits_session_before_execute(self):
        """Checkpoint with injected answer is committed so the inner session sees it."""
        from analysi.services.task_execution import TaskExecutionService

        service = TaskExecutionService()

        checkpoint_data = {
            "node_results": {},
            "pending_node_id": "n1",
            "pending_tool_name": "ask_human",
            "pending_tool_args": {"question": "Block?"},
            "pending_tool_result": None,
            "variables": {},
            "plan_version": "2.0",
        }

        mock_task_run = MagicMock()
        mock_task_run.id = uuid4()
        mock_task_run.status = "paused"
        mock_task_run.execution_context = {"_hitl_checkpoint": checkpoint_data}

        completed_result = MagicMock()
        completed_result.status = "completed"
        service.execute_single_task = AsyncMock(return_value=completed_result)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task_run
        mock_session.execute = AsyncMock(return_value=mock_result)

        await service.resume_paused_task(
            session=mock_session,
            task_run_id=mock_task_run.id,
            tenant_id="t1",
            human_response="Yes",
        )

        # session.commit() must be called (not just flush) before execute_single_task
        mock_session.commit.assert_awaited_once()
        # flush should NOT have been called (we use commit directly now)
        mock_session.flush.assert_not_awaited()


# ---------------------------------------------------------------------------
# continue_after_hitl — COMPLETED, PAUSED, FAILED branches
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestContinueAfterHitl:
    """WorkflowExecutor.continue_after_hitl handles all task result branches."""

    def _make_task_result(self, status="completed", output_data=None, error=None):
        """Helper: create a mock TaskExecutionResult."""
        result = MagicMock()
        result.status = status
        result.task_run_id = uuid4()
        result.output_data = output_data or {"answer": "Approved"}
        result.error_message = error
        result.llm_usage = None
        return result

    @pytest.mark.asyncio
    async def test_completed_marks_node_and_creates_successors(self):
        """COMPLETED task → node marked COMPLETED, successor instances created."""
        from analysi.constants import WorkflowConstants
        from analysi.services.workflow_execution import WorkflowExecutor

        wf_run_id = uuid4()
        node_instance_id = uuid4()

        mock_node_instance = MagicMock()
        mock_node_instance.id = node_instance_id
        mock_node_instance.node_id = "analyze_threat"

        mock_wf_run = MagicMock()
        mock_wf_run.id = wf_run_id
        mock_wf_run.tenant_id = "t1"
        mock_wf_run.workflow_id = uuid4()
        mock_wf_run.execution_context = {}
        mock_wf_run.status = WorkflowConstants.Status.PAUSED  # Bug #14: must be set

        mock_workflow = MagicMock()
        mock_workflow.edges = []
        mock_workflow.nodes = []

        task_result = self._make_task_result("completed")

        with patch("analysi.db.session.AsyncSessionLocal") as MockSession:
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            # Mock the queries that continue_after_hitl executes
            mock_session.execute = AsyncMock()

            with patch.object(WorkflowExecutor, "__init__", lambda self, session: None):
                with patch.object(
                    WorkflowExecutor, "monitor_execution", new_callable=AsyncMock
                ):
                    executor = WorkflowExecutor.__new__(WorkflowExecutor)
                    executor.session = mock_session
                    executor.tenant_id = "t1"
                    executor.node_repo = AsyncMock()
                    executor.run_repo = AsyncMock()
                    executor.edge_repo = AsyncMock()
                    executor.storage = MagicMock()

                    # Setup return values
                    node_result = MagicMock()
                    node_result.scalar_one.return_value = mock_node_instance
                    wf_result = MagicMock()
                    wf_result.scalar_one.return_value = mock_workflow
                    mock_session.execute = AsyncMock(
                        side_effect=[node_result, wf_result]
                    )

                    executor.run_repo.get_workflow_run_by_id = AsyncMock(
                        return_value=mock_wf_run
                    )
                    executor.storage.select_storage_type = MagicMock(
                        return_value="inline"
                    )
                    executor.storage.store = AsyncMock(
                        return_value={"location": "inline://data"}
                    )
                    executor._create_successor_instances = AsyncMock()
                    executor.monitor_execution = AsyncMock()

                    # Patch the constructor to return our pre-built executor
                    with patch(
                        "analysi.services.workflow_execution.WorkflowExecutor",
                        return_value=executor,
                    ):
                        with patch(
                            "analysi.services.task_run.TaskRunService"
                        ) as MockTaskRunSvc:
                            mock_task_run_svc = AsyncMock()
                            MockTaskRunSvc.return_value = mock_task_run_svc

                            await WorkflowExecutor.continue_after_hitl(
                                workflow_run_id=wf_run_id,
                                node_instance_id=node_instance_id,
                                task_result=task_result,
                            )

                    # Node should be marked COMPLETED
                    executor.node_repo.update_node_instance_status.assert_awaited()
                    call_args = executor.node_repo.update_node_instance_status.call_args
                    assert call_args[0][0] == node_instance_id
                    assert call_args[0][1] == "completed"

                    # Successors should be created
                    executor._create_successor_instances.assert_awaited_once()

                    # monitor_execution should be re-entered
                    executor.monitor_execution.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_paused_stays_paused_and_returns_early(self):
        """PAUSED task (another HITL) → node stays paused, no monitor_execution."""
        from analysi.constants import WorkflowConstants
        from analysi.services.workflow_execution import WorkflowExecutor

        wf_run_id = uuid4()
        node_instance_id = uuid4()

        mock_node_instance = MagicMock()
        mock_node_instance.id = node_instance_id
        mock_node_instance.node_id = "ask_analyst"

        mock_wf_run = MagicMock()
        mock_wf_run.id = wf_run_id
        mock_wf_run.tenant_id = "t1"
        mock_wf_run.workflow_id = uuid4()
        mock_wf_run.execution_context = {}
        mock_wf_run.status = WorkflowConstants.Status.PAUSED  # Bug #14: must be set

        mock_workflow = MagicMock()

        # Task paused again with a new checkpoint
        task_result = self._make_task_result(
            "paused",
            output_data={
                "_hitl_checkpoint": {
                    "pending_tool_name": "ask_human",
                    "pending_tool_args": {"question": "Second question?"},
                }
            },
        )

        with patch("analysi.db.session.AsyncSessionLocal") as MockSession:
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.object(WorkflowExecutor, "__init__", lambda self, session: None):
                executor = WorkflowExecutor.__new__(WorkflowExecutor)
                executor.session = mock_session
                executor.tenant_id = "t1"
                executor.node_repo = AsyncMock()
                executor.run_repo = AsyncMock()
                executor.edge_repo = AsyncMock()
                executor.storage = MagicMock()

                node_result = MagicMock()
                node_result.scalar_one.return_value = mock_node_instance
                wf_result = MagicMock()
                wf_result.scalar_one.return_value = mock_workflow
                mock_session.execute = AsyncMock(side_effect=[node_result, wf_result])
                executor.run_repo.get_workflow_run_by_id = AsyncMock(
                    return_value=mock_wf_run
                )
                executor.monitor_execution = AsyncMock()

                with patch(
                    "analysi.services.workflow_execution.WorkflowExecutor",
                    return_value=executor,
                ):
                    with patch(
                        "analysi.services.task_run.TaskRunService"
                    ) as MockTaskRunSvc:
                        MockTaskRunSvc.return_value = AsyncMock()

                        with patch(
                            "analysi.repositories.hitl_repository.create_question_from_checkpoint",
                            new_callable=AsyncMock,
                            return_value=None,
                        ):
                            await WorkflowExecutor.continue_after_hitl(
                                workflow_run_id=wf_run_id,
                                node_instance_id=node_instance_id,
                                task_result=task_result,
                            )

                # monitor_execution should NOT be called (workflow stays paused)
                executor.monitor_execution.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_marks_node_failed_and_enters_monitor(self):
        """FAILED task → node marked FAILED, monitor_execution re-entered."""
        from analysi.constants import WorkflowConstants
        from analysi.services.workflow_execution import WorkflowExecutor

        wf_run_id = uuid4()
        node_instance_id = uuid4()

        mock_node_instance = MagicMock()
        mock_node_instance.id = node_instance_id
        mock_node_instance.node_id = "enrich_ip"

        mock_wf_run = MagicMock()
        mock_wf_run.id = wf_run_id
        mock_wf_run.tenant_id = "t1"
        mock_wf_run.workflow_id = uuid4()
        mock_wf_run.execution_context = {}
        mock_wf_run.status = WorkflowConstants.Status.PAUSED  # Bug #14: must be set

        mock_workflow = MagicMock()

        task_result = self._make_task_result("failed", error="Script timeout")

        with patch("analysi.db.session.AsyncSessionLocal") as MockSession:
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch.object(WorkflowExecutor, "__init__", lambda self, session: None):
                executor = WorkflowExecutor.__new__(WorkflowExecutor)
                executor.session = mock_session
                executor.tenant_id = "t1"
                executor.node_repo = AsyncMock()
                executor.run_repo = AsyncMock()
                executor.edge_repo = AsyncMock()
                executor.storage = MagicMock()

                node_result = MagicMock()
                node_result.scalar_one.return_value = mock_node_instance
                wf_result = MagicMock()
                wf_result.scalar_one.return_value = mock_workflow
                mock_session.execute = AsyncMock(side_effect=[node_result, wf_result])
                executor.run_repo.get_workflow_run_by_id = AsyncMock(
                    return_value=mock_wf_run
                )
                executor.monitor_execution = AsyncMock()

                with patch(
                    "analysi.services.workflow_execution.WorkflowExecutor",
                    return_value=executor,
                ):
                    with patch(
                        "analysi.services.task_run.TaskRunService"
                    ) as MockTaskRunSvc:
                        MockTaskRunSvc.return_value = AsyncMock()

                        await WorkflowExecutor.continue_after_hitl(
                            workflow_run_id=wf_run_id,
                            node_instance_id=node_instance_id,
                            task_result=task_result,
                        )

                # Node should be marked FAILED
                executor.node_repo.update_node_instance_status.assert_awaited()
                call_args = executor.node_repo.update_node_instance_status.call_args
                assert call_args[0][0] == node_instance_id
                assert call_args[0][1] == "failed"

                # monitor_execution should detect the failed node and stop workflow
                executor.monitor_execution.assert_awaited_once()
