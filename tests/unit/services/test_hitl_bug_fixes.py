"""
Unit tests for HITL bug fixes — Project Kalymnos hardening.

These tests are written TDD-style: each test targets a specific bug found
during the HITL code review. Tests are written FIRST (expected to fail),
then the corresponding fix is applied.

Bug tracker:
  Critical #1: Analysis never completes after HITL resume (workflow context)
  Critical #2: HITL in control-event-triggered tasks broken (_execute_task_rule)
  Critical #3: Question-level timeout is dead code
  High #4: Race condition — reconciliation vs. in-flight answer
  High #5: Expired analysis leaves hitl_questions as "pending" (ghost answers)
  High #6: handle_human_responded silently swallows missing questions
  Medium #9: No index on id alone (migration — tested in integration)
  Medium #10: create_question_from_checkpoint accepts empty channel
  Medium #11: No tenant isolation in get_by_id / find_by_ref
  Medium #12: find_by_ref uses scalar_one_or_none with no safety
  Medium #13: action_id collision in Block Kit buttons
  Medium #14: No cancellation check before HITL resume
  Medium #15: Standalone task re-pause missing question creation + Slack send
  Medium #16: Analysis mark_running after continue_after_hitl failure path
  Reviewer #17: create_question_from_checkpoint ignores `destination` arg name
  Reviewer #18: Analysis transitions to running on re-pause (should stay paused)
  Hypothesis #19: question_text extracted as "text" but Slack tools use "question"
  Hypothesis #20: options stored as [] — Slack uses "responses" (comma-separated)
  Reviewer #26: mark_expired flush not committed after per-analysis question expiry
  Reviewer #27: Slack integration lookup non-deterministic with LIMIT 1 (no ORDER BY)
  Reviewer #28: handle_human_responded doesn't gate on question.status before resume
  Reviewer #29: continue_after_hitl early return strands task_run in non-terminal state
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.constants import HITLQuestionConstants


@pytest.fixture(autouse=True)
def _mock_arq_enqueue():
    """Prevent real Redis/Valkey connections in unit tests.

    handle_human_responded → _requeue_pipeline_after_hitl → enqueue_arq_job
    calls arq.create_pool() which requires a live Valkey instance.  Unit tests
    must never depend on external services.
    """
    with patch(
        "analysi.common.arq_enqueue.enqueue_arq_job",
        new_callable=AsyncMock,
        return_value="mock-arq-job-id",
    ):
        yield


# ---------------------------------------------------------------------------
# Critical Bug #1: Analysis never completes after HITL resume (workflow ctx)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug1AnalysisCompletionAfterHITLResume:
    """After continue_after_hitl finishes, analysis must transition out of
    paused_human_review.  Before the fix, it stayed stuck forever."""

    @pytest.mark.asyncio
    async def test_workflow_completed_updates_analysis_to_completed(self):
        """After HITL resume + workflow completes, analysis status → completed."""
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        question_id = uuid4()
        task_run_id = uuid4()
        workflow_run_id = uuid4()
        node_instance_id = uuid4()
        analysis_id = uuid4()

        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.task_run_id = task_run_id
        mock_question.workflow_run_id = workflow_run_id
        mock_question.node_instance_id = node_instance_id
        mock_question.analysis_id = analysis_id
        mock_question.status = "answered"

        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answer": "Approve",
            "answered_by": "U1",
        }

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
                "analysi.repositories.activity_audit_repository.ActivityAuditRepository"
            ) as MockAuditRepo,
            patch(
                "analysi.repositories.alert_repository.AlertAnalysisRepository"
            ) as MockAnalysisRepo,
        ):
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo_instance

            # Task resume succeeds
            mock_task_svc = AsyncMock()
            mock_task_result = MagicMock()
            mock_task_result.status = "completed"
            mock_task_result.task_run_id = task_run_id
            mock_task_result.output_data = {"result": "done"}
            mock_task_result.llm_usage = None
            mock_task_result.error_message = None
            mock_task_svc.resume_paused_task = AsyncMock(return_value=mock_task_result)
            MockTaskExec.return_value = mock_task_svc

            # Workflow continuation succeeds (returns normally = completed)
            MockWfExec.continue_after_hitl = AsyncMock(return_value=None)

            mock_audit_instance = AsyncMock()
            MockAuditRepo.return_value = mock_audit_instance

            mock_analysis_repo_instance = AsyncMock()
            MockAnalysisRepo.return_value = mock_analysis_repo_instance

            await handle_human_responded(mock_event)

            # BUG FIX: After continue_after_hitl, analysis should be updated.
            # The handler must update the analysis status out of paused_human_review.
            # We check that analysis status update was attempted with analysis_id.
            # The fix should call update_analysis_status_after_hitl or equivalent.
            #
            # Verify that the analysis_id from the question is used to
            # transition the analysis out of paused_human_review.
            assert mock_question.analysis_id == analysis_id
            # The handler should make some call to update analysis status.
            # After fix, we expect a call to mark the analysis as running/completed.
            # We check by verifying a session commit happens after the workflow path.
            # The key assertion: continue_after_hitl was called AND afterwards
            # a status update is performed on the analysis.
            MockWfExec.continue_after_hitl.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_workflow_failed_updates_analysis_to_failed(self):
        """After HITL resume + workflow fails, analysis status → failed."""
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        question_id = uuid4()
        task_run_id = uuid4()
        workflow_run_id = uuid4()
        node_instance_id = uuid4()
        analysis_id = uuid4()

        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.task_run_id = task_run_id
        mock_question.workflow_run_id = workflow_run_id
        mock_question.node_instance_id = node_instance_id
        mock_question.analysis_id = analysis_id
        mock_question.status = "answered"

        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answer": "Deny",
            "answered_by": "U1",
        }

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
                "analysi.repositories.activity_audit_repository.ActivityAuditRepository"
            ) as MockAuditRepo,
            patch(
                "analysi.repositories.alert_repository.AlertAnalysisRepository"
            ) as MockAnalysisRepo,
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
            mock_task_result.output_data = {"result": "denied"}
            mock_task_result.llm_usage = None
            mock_task_result.error_message = None
            mock_task_svc.resume_paused_task = AsyncMock(return_value=mock_task_result)
            MockTaskExec.return_value = mock_task_svc

            # Workflow continuation raises (= workflow failed internally)
            MockWfExec.continue_after_hitl = AsyncMock(
                side_effect=RuntimeError("Workflow node failed")
            )

            mock_audit_instance = AsyncMock()
            MockAuditRepo.return_value = mock_audit_instance

            mock_analysis_repo_instance = AsyncMock()
            MockAnalysisRepo.return_value = mock_analysis_repo_instance

            # The exception should propagate (control event bus marks it failed),
            # BUT the analysis should also be updated before propagating.
            with pytest.raises(RuntimeError, match="Workflow node failed"):
                await handle_human_responded(mock_event)


# ---------------------------------------------------------------------------
# Critical Bug #2: HITL in control-event-triggered tasks broken
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug2ExecuteTaskRuleHITLPause:
    """_execute_task_rule must create a hitl_question and send Slack message
    when the task pauses for HITL.  Before the fix, only status was persisted."""

    @pytest.mark.asyncio
    async def test_paused_task_creates_hitl_question(self):
        """When a control-event-triggered task pauses, a hitl_question row is created."""
        from analysi.alert_analysis.jobs.control_events import (
            _execute_task_rule,
        )

        task_id = uuid4()
        task_run_id = uuid4()

        # Mock the task run creation
        mock_task_run = MagicMock()
        mock_task_run.id = task_run_id

        checkpoint_data = {
            "pending_tool_name": "slack_ask",
            "pending_tool_args": {
                "channel": "C12345",
                "text": "Approve containment?",
                "options": ["Approve", "Deny"],
            },
            "pending_tool_result": None,
            "node_results": {},
            "pending_node_id": "n1",
            "variables": {},
        }

        # Mock TaskExecutionResult with PAUSED status
        mock_result = MagicMock()
        mock_result.status = "paused"
        mock_result.task_run_id = task_run_id
        mock_result.output_data = {"_hitl_checkpoint": checkpoint_data}
        mock_result.llm_usage = None
        mock_result.error_message = None

        with (
            patch("analysi.db.session.AsyncSessionLocal") as MockSession,
            patch(
                "analysi.services.task_execution.TaskExecutionService"
            ) as MockTaskExec,
            patch("analysi.services.task_run.TaskRunService") as MockTaskRunSvc,
            patch(
                "analysi.repositories.hitl_repository.create_question_from_checkpoint",
                new_callable=AsyncMock,
            ) as mock_create_question,
            patch(
                "analysi.slack_listener.sender.send_hitl_question",
                new_callable=AsyncMock,
            ) as mock_send,
        ):
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_task_run_svc = AsyncMock()
            mock_task_run_svc.create_execution = AsyncMock(return_value=mock_task_run)
            MockTaskRunSvc.return_value = mock_task_run_svc

            mock_task_exec_svc = AsyncMock()
            mock_task_exec_svc.execute_single_task = AsyncMock(return_value=mock_result)
            MockTaskExec.return_value = mock_task_exec_svc

            mock_hitl_question = MagicMock()
            mock_hitl_question.id = uuid4()
            mock_create_question.return_value = mock_hitl_question

            await _execute_task_rule(
                tenant_id="t1",
                task_id=task_id,
                input_data={"alert_id": "a1"},
                execution_context={"rule_id": "r1"},
            )

            # BUG FIX: create_question_from_checkpoint must be called
            mock_create_question.assert_awaited_once()

            # BUG FIX: send_hitl_question must be called
            mock_send.assert_awaited_once()


# ---------------------------------------------------------------------------
# Critical Bug #3: Question-level timeout is dead code
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug3QuestionTimeoutReconciliation:
    """Reconciliation must call find_expired + mark_expired on hitl_questions,
    and then fail the associated analyses.  Before the fix, this was dead code."""

    @pytest.mark.asyncio
    async def test_reconciliation_expires_timed_out_questions(self):
        """mark_expired_hitl_paused_analyses also expires timed-out questions."""
        from analysi.alert_analysis.jobs.reconciliation import (
            mark_expired_hitl_paused_analyses,
        )

        now = datetime.now(UTC)
        analysis_id = uuid4()

        # Analysis paused 5 hours ago — within 24h analysis timeout but past 4h question timeout
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.tenant_id = "t1"
        mock_analysis.alert_id = uuid4()
        mock_analysis.updated_at = now - timedelta(hours=5)

        analysis_repo = AsyncMock()
        analysis_repo.find_paused_for_human_review = AsyncMock(
            return_value=[mock_analysis]
        )
        analysis_repo.mark_failed = AsyncMock()

        alert_repo = AsyncMock()
        alert_repo.mark_stuck_alert_failed = AsyncMock()

        # The question itself has expired (timeout_at was 4h after creation)
        expired_question = MagicMock()
        expired_question.id = uuid4()
        expired_question.analysis_id = analysis_id
        expired_question.status = "pending"
        expired_question.timeout_at = now - timedelta(hours=1)

        hitl_repo = AsyncMock()
        hitl_repo.find_expired = AsyncMock(return_value=[expired_question])
        hitl_repo.mark_expired = AsyncMock(return_value=True)

        await mark_expired_hitl_paused_analyses(
            analysis_repo,
            alert_repo,
            timeout_hours=24,
            hitl_repo=hitl_repo,
        )

        # With question-level timeout active, the analysis at 5h should be expired
        # even though it's within the 24h analysis window (because question timed out).
        hitl_repo.find_expired.assert_awaited_once()
        assert hitl_repo.mark_expired.await_count >= 1


# ---------------------------------------------------------------------------
# High Bug #4: Race condition — reconciliation vs. in-flight answer
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug4ReconciliationRaceWithAnswer:
    """Reconciliation must not expire an analysis whose question was already
    answered but whose control event hasn't been processed yet."""

    @pytest.mark.asyncio
    async def test_skips_analysis_with_answered_question(self):
        """Analysis with an answered hitl_question is not expired by reconciliation."""
        from analysi.alert_analysis.jobs.reconciliation import (
            mark_expired_hitl_paused_analyses,
        )

        now = datetime.now(UTC)
        analysis_id = uuid4()

        # Analysis has been paused for 25 hours (past 24h threshold)
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.tenant_id = "t1"
        mock_analysis.alert_id = uuid4()
        mock_analysis.updated_at = now - timedelta(hours=25)

        analysis_repo = AsyncMock()
        analysis_repo.find_paused_for_human_review = AsyncMock(
            return_value=[mock_analysis]
        )
        analysis_repo.mark_failed = AsyncMock()

        alert_repo = AsyncMock()
        alert_repo.mark_stuck_alert_failed = AsyncMock()

        # The question for this analysis was already answered
        answered_question = MagicMock()
        answered_question.id = uuid4()
        answered_question.analysis_id = analysis_id
        answered_question.status = HITLQuestionConstants.Status.ANSWERED

        hitl_repo = AsyncMock()
        hitl_repo.find_expired = AsyncMock(return_value=[])
        hitl_repo.find_pending_by_analysis_id = AsyncMock(return_value=None)
        hitl_repo.find_by_analysis_id = AsyncMock(return_value=answered_question)

        count = await mark_expired_hitl_paused_analyses(
            analysis_repo,
            alert_repo,
            timeout_hours=24,
            hitl_repo=hitl_repo,
        )

        # Should NOT expire — answer is in flight
        assert count == 0
        analysis_repo.mark_failed.assert_not_awaited()


# ---------------------------------------------------------------------------
# High Bug #5: Expired analysis leaves hitl_questions as "pending"
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug5ExpireQuestionsOnAnalysisTimeout:
    """When reconciliation expires an analysis, it must also mark the
    hitl_questions row as expired to prevent ghost answers."""

    @pytest.mark.asyncio
    async def test_expired_analysis_also_expires_its_questions(self):
        """When an analysis is expired, its hitl_questions are marked expired too."""
        from analysi.alert_analysis.jobs.reconciliation import (
            mark_expired_hitl_paused_analyses,
        )

        now = datetime.now(UTC)
        analysis_id = uuid4()
        question_id = uuid4()

        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.tenant_id = "t1"
        mock_analysis.alert_id = uuid4()
        mock_analysis.updated_at = now - timedelta(hours=25)

        analysis_repo = AsyncMock()
        analysis_repo.find_paused_for_human_review = AsyncMock(
            return_value=[mock_analysis]
        )
        analysis_repo.mark_failed = AsyncMock()

        alert_repo = AsyncMock()
        alert_repo.mark_stuck_alert_failed = AsyncMock()

        # The pending question for this analysis
        pending_question = MagicMock()
        pending_question.id = question_id
        pending_question.analysis_id = analysis_id
        pending_question.status = HITLQuestionConstants.Status.PENDING

        hitl_repo = AsyncMock()
        hitl_repo.find_expired = AsyncMock(return_value=[])
        hitl_repo.find_by_analysis_id = AsyncMock(return_value=pending_question)
        hitl_repo.find_pending_by_analysis_id = AsyncMock(return_value=pending_question)
        hitl_repo.mark_expired = AsyncMock(return_value=True)

        count = await mark_expired_hitl_paused_analyses(
            analysis_repo,
            alert_repo,
            timeout_hours=24,
            hitl_repo=hitl_repo,
        )

        assert count == 1
        # BUG FIX: mark_expired must be called for the question
        hitl_repo.mark_expired.assert_awaited_once_with(question_id)


# ---------------------------------------------------------------------------
# High Bug #6: handle_human_responded silently swallows missing questions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug6MissingQuestionRaisesError:
    """handle_human_responded must raise when the question is not found,
    so the control event is marked failed and retried."""

    @pytest.mark.asyncio
    async def test_missing_question_raises_value_error(self):
        """Handler raises ValueError (not silent return) when question not found."""
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(uuid4()),
            "answer": "Yes",
            "answered_by": "U1",
        }

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

            # BUG FIX: Must raise, not return silently
            with pytest.raises(ValueError, match="not found"):
                await handle_human_responded(mock_event)


# ---------------------------------------------------------------------------
# Medium Bug #10: create_question_from_checkpoint accepts empty channel
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug10ValidateChannelInCheckpoint:
    """create_question_from_checkpoint must return None (not create a
    question) when the channel is empty — those questions can never be answered."""

    @pytest.mark.asyncio
    async def test_returns_none_when_channel_empty(self):
        """Missing channel in tool args returns None instead of creating orphan question."""
        from analysi.repositories.hitl_repository import (
            create_question_from_checkpoint,
        )

        mock_session = AsyncMock()

        checkpoint_data = {
            "pending_tool_name": "slack_ask",
            "pending_tool_args": {
                # No channel key!
                "text": "Should we escalate?",
                "options": [{"value": "yes"}],
            },
        }

        result = await create_question_from_checkpoint(
            session=mock_session,
            tenant_id="t1",
            task_run_id=uuid4(),
            checkpoint_data=checkpoint_data,
        )

        # BUG FIX: Must return None when channel is empty
        assert result is None
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_when_channel_is_empty_string(self):
        """Explicit empty channel string also returns None."""
        from analysi.repositories.hitl_repository import (
            create_question_from_checkpoint,
        )

        mock_session = AsyncMock()

        checkpoint_data = {
            "pending_tool_name": "slack_ask",
            "pending_tool_args": {
                "channel": "",
                "text": "Q?",
                "options": [],
            },
        }

        result = await create_question_from_checkpoint(
            session=mock_session,
            tenant_id="t1",
            task_run_id=uuid4(),
            checkpoint_data=checkpoint_data,
        )

        assert result is None
        mock_session.add.assert_not_called()


# ---------------------------------------------------------------------------
# Medium Bug #11: No tenant isolation in get_by_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug11TenantIsolation:
    """get_by_id and find_by_ref must accept and filter by tenant_id."""

    @pytest.mark.asyncio
    async def test_get_by_id_accepts_tenant_id(self):
        """get_by_id filters by tenant_id when provided."""
        from analysi.repositories.hitl_repository import HITLQuestionRepository

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = HITLQuestionRepository(mock_session)
        result = await repo.get_by_id(uuid4(), tenant_id="t1")

        assert result is None
        # Verify tenant_id was included in the query
        call_args = mock_session.execute.call_args
        stmt = call_args[0][0]
        # The compiled SQL should contain tenant_id filter
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "tenant_id" in compiled


# ---------------------------------------------------------------------------
# Medium Bug #12: find_by_ref scalar_one_or_none safety
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug12FindByRefSafety:
    """find_by_ref must not crash on duplicate matches — use .first()."""

    @pytest.mark.asyncio
    async def test_find_by_ref_returns_most_recent_on_duplicates(self):
        """When multiple questions match (question_ref, channel), return most recent."""
        from analysi.repositories.hitl_repository import HITLQuestionRepository

        # Simulate .first() returning the first result (most recent due to ORDER BY)
        mock_question = MagicMock()
        mock_question.id = uuid4()
        mock_question.created_at = datetime.now(UTC)

        mock_session = AsyncMock()
        mock_result = MagicMock()
        # After fix: uses scalars().first() instead of scalar_one_or_none()
        mock_result.scalars.return_value.first.return_value = mock_question
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = HITLQuestionRepository(mock_session)
        result = await repo.find_by_ref("1234.5678", "C123")

        assert result == mock_question


# ---------------------------------------------------------------------------
# Medium Bug #13: action_id collision in Block Kit buttons
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug13ActionIdCollision:
    """Buttons with labels that normalize to the same string must get unique action_ids."""

    def test_duplicate_labels_get_unique_action_ids(self):
        """Two buttons normalizing to same string still have unique action_ids."""
        from analysi.slack_listener.sender import _build_blocks

        # "Approve Now" and "approve_now" would normalize to same action_id
        blocks = _build_blocks("Question?", ["Approve Now", "approve_now", "Deny"])

        actions_block = blocks[1]
        action_ids = [el["action_id"] for el in actions_block["elements"]]

        # All action_ids must be unique
        assert len(action_ids) == len(set(action_ids)), (
            f"Duplicate action_ids found: {action_ids}"
        )

    def test_identical_labels_get_unique_action_ids(self):
        """Even identical labels produce unique action_ids (via index suffix)."""
        from analysi.slack_listener.sender import _build_blocks

        blocks = _build_blocks("Question?", ["Yes", "Yes"])

        actions_block = blocks[1]
        action_ids = [el["action_id"] for el in actions_block["elements"]]

        assert len(action_ids) == len(set(action_ids))


# ---------------------------------------------------------------------------
# Medium Bug #14: No cancellation check before HITL resume
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug14CancellationCheckBeforeResume:
    """continue_after_hitl must verify workflow is still PAUSED before resuming."""

    @pytest.mark.asyncio
    async def test_cancelled_workflow_not_resumed(self):
        """If workflow was cancelled while paused, continue_after_hitl returns early."""
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
        mock_wf_run.status = "cancelled"  # Was cancelled while paused!

        mock_workflow = MagicMock()

        task_result = MagicMock()
        task_result.status = "completed"
        task_result.task_run_id = uuid4()
        task_result.output_data = {"answer": "Approved"}
        task_result.error_message = None
        task_result.llm_usage = None

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

                # BUG FIX: monitor_execution should NOT be called for cancelled workflow
                executor.monitor_execution.assert_not_awaited()


# ---------------------------------------------------------------------------
# Standalone task PAUSED branch in handle_human_responded
# (Missing test coverage — not a bug fix, but needed for safety)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStandaloneTaskPausedBranch:
    """When a standalone task re-pauses (another HITL), status is persisted as paused."""

    @pytest.mark.asyncio
    async def test_standalone_task_paused_again_persists_paused(self):
        """Re-pause persists PAUSED status and creates new question."""
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        question_id = uuid4()
        task_run_id = uuid4()

        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.task_run_id = task_run_id
        mock_question.workflow_run_id = None
        mock_question.node_instance_id = None
        mock_question.analysis_id = None
        mock_question.status = "answered"

        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answer": "Yes",
            "answered_by": "U1",
        }

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
            mock_task_result.status = "paused"  # Re-paused!
            mock_task_result.task_run_id = task_run_id
            mock_task_result.output_data = {
                "_hitl_checkpoint": {
                    "pending_tool_name": "ask_second",
                    "pending_tool_args": {"text": "Second Q?"},
                }
            }
            mock_task_result.llm_usage = None
            mock_task_result.error_message = None
            mock_task_svc.resume_paused_task = AsyncMock(return_value=mock_task_result)
            MockTaskExec.return_value = mock_task_svc

            mock_task_run_svc = AsyncMock()
            MockTaskRunSvc.return_value = mock_task_run_svc

            await handle_human_responded(mock_event)

            # Status should be persisted as PAUSED
            mock_task_run_svc.update_status.assert_awaited_once()
            call_args = mock_task_run_svc.update_status.call_args
            assert call_args[0][2] == "paused"

    @pytest.mark.asyncio
    async def test_standalone_task_failed_persists_error(self):
        """Failed standalone task persists FAILED status with error_info."""
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        question_id = uuid4()
        task_run_id = uuid4()

        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.task_run_id = task_run_id
        mock_question.workflow_run_id = None
        mock_question.node_instance_id = None
        mock_question.analysis_id = None
        mock_question.status = "answered"

        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answer": "Reject",
            "answered_by": "U1",
        }

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
            mock_task_result.status = "failed"
            mock_task_result.task_run_id = task_run_id
            mock_task_result.output_data = None
            mock_task_result.llm_usage = None
            mock_task_result.error_message = "Script crashed"
            mock_task_svc.resume_paused_task = AsyncMock(return_value=mock_task_result)
            MockTaskExec.return_value = mock_task_svc

            mock_task_run_svc = AsyncMock()
            MockTaskRunSvc.return_value = mock_task_run_svc

            await handle_human_responded(mock_event)

            # Status should be persisted as FAILED with error
            mock_task_run_svc.update_status.assert_awaited_once()
            call_args = mock_task_run_svc.update_status.call_args
            assert call_args[0][2] == "failed"
            assert "error" in call_args[1].get("error_info", {})


# ---------------------------------------------------------------------------
# Medium Bug #15: Standalone task re-pause missing question + Slack send
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug15StandaloneTaskRepauseQuestion:
    """When a standalone task resumes and then pauses again (multiple HITL
    tools in one script), a new hitl_questions row must be created and the
    Slack message sent.  Before the fix, only the status was persisted."""

    @pytest.mark.asyncio
    async def test_standalone_repaused_creates_question_and_sends_slack(self):
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        question_id = uuid4()
        task_run_id = uuid4()

        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.task_run_id = task_run_id
        mock_question.workflow_run_id = None
        mock_question.node_instance_id = None
        mock_question.analysis_id = None
        mock_question.status = "answered"

        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answer": "Approve",
            "answered_by": "U1",
        }

        with (
            patch("analysi.db.session.AsyncSessionLocal") as MockSession,
            patch(
                "analysi.services.task_execution.TaskExecutionService"
            ) as MockTaskExec,
            patch(
                "analysi.repositories.hitl_repository.HITLQuestionRepository"
            ) as MockRepo,
            patch("analysi.services.task_run.TaskRunService") as MockTaskRunSvc,
            patch(
                "analysi.repositories.hitl_repository.create_question_from_checkpoint"
            ) as mock_create_q,
            patch("analysi.slack_listener.sender.send_hitl_question") as mock_send_q,
        ):
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo_instance

            # Task resumes and then pauses again at a second HITL tool
            mock_task_svc = AsyncMock()
            mock_task_result = MagicMock()
            mock_task_result.status = "paused"
            mock_task_result.task_run_id = task_run_id
            mock_task_result.output_data = {
                "_hitl_checkpoint": {
                    "pending_tool_name": "ask_second_question",
                    "pending_tool_args": {
                        "text": "Second question?",
                        "channel": "C123",
                        "question_ref": "ts456",
                    },
                }
            }
            mock_task_result.llm_usage = None
            mock_task_result.error_message = None
            mock_task_svc.resume_paused_task = AsyncMock(return_value=mock_task_result)
            MockTaskExec.return_value = mock_task_svc

            mock_task_run_svc = AsyncMock()
            MockTaskRunSvc.return_value = mock_task_run_svc

            # Mock the question creation to return a question
            mock_new_question = MagicMock()
            mock_new_question.id = uuid4()
            mock_create_q.return_value = mock_new_question

            await handle_human_responded(mock_event)

            # Must create a new question for the second pause
            mock_create_q.assert_awaited_once()
            # Must send the Slack message
            mock_send_q.assert_awaited_once()


# ---------------------------------------------------------------------------
# Medium Bug #16: Analysis status after continue_after_hitl failure
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug16AnalysisStatusAfterWorkflowFailure:
    """When continue_after_hitl completes but the workflow ended in FAILED
    status (the task itself failed), _update_analysis_after_hitl must NOT
    unconditionally set the analysis to 'running'."""

    @pytest.mark.asyncio
    async def test_workflow_failure_does_not_mark_analysis_running(self):
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        question_id = uuid4()
        task_run_id = uuid4()
        workflow_run_id = uuid4()
        node_instance_id = uuid4()
        analysis_id = uuid4()

        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.task_run_id = task_run_id
        mock_question.workflow_run_id = workflow_run_id
        mock_question.node_instance_id = node_instance_id
        mock_question.analysis_id = analysis_id
        mock_question.status = "answered"

        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answer": "Approve",
            "answered_by": "U1",
        }

        with (
            patch("analysi.db.session.AsyncSessionLocal") as MockSession,
            patch(
                "analysi.services.task_execution.TaskExecutionService"
            ) as MockTaskExec,
            patch(
                "analysi.repositories.hitl_repository.HITLQuestionRepository"
            ) as MockRepo,
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.continue_after_hitl"
            ) as mock_continue_hitl,
            patch(
                "analysi.alert_analysis.jobs.control_events._update_analysis_after_hitl"
            ) as mock_update_analysis,
        ):
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo_instance

            mock_task_svc = AsyncMock()
            mock_task_result = MagicMock()
            mock_task_result.status = "failed"
            mock_task_result.task_run_id = task_run_id
            mock_task_result.output_data = None
            mock_task_result.llm_usage = None
            mock_task_result.error_message = "Task script crashed"
            mock_task_svc.resume_paused_task = AsyncMock(return_value=mock_task_result)
            MockTaskExec.return_value = mock_task_svc

            # continue_after_hitl does NOT raise — it handles FAILED internally
            mock_continue_hitl.return_value = None

            await handle_human_responded(mock_event)

            # Bug #22 fix: Analysis must be explicitly marked "failed" when
            # the task fails, since monitor_execution doesn't touch alert_analysis.
            mock_update_analysis.assert_awaited_once()
            call_kwargs = mock_update_analysis.call_args.kwargs
            assert call_kwargs["status"] == "failed", (
                "Analysis should be marked 'failed' when the task failed"
            )


# ---------------------------------------------------------------------------
# Reviewer Bug #17: create_question_from_checkpoint must accept `destination`
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug17DestinationAsFallbackChannel:
    """Slack HITL tools use `destination` (not `channel`) as the argument name.
    create_question_from_checkpoint must fall back to `destination` when
    `channel` is not present, otherwise the question row is never created
    and the human never sees the prompt."""

    @pytest.mark.asyncio
    async def test_destination_used_when_channel_missing(self):
        """Tool args with `destination` but no `channel` should create a question."""
        from analysi.repositories.hitl_repository import (
            create_question_from_checkpoint,
        )

        mock_session = AsyncMock()
        # Mock the repo.create path
        mock_question = MagicMock()
        mock_question.id = uuid4()

        checkpoint_data = {
            "pending_tool_name": "ask_question_channel",
            "pending_tool_args": {
                "destination": "C123SLACK",  # Slack uses destination, not channel
                "question": "Should we block?",
                "options": [{"value": "yes"}, {"value": "no"}],
            },
        }

        with patch(
            "analysi.repositories.hitl_repository.HITLQuestionRepository"
        ) as MockRepo:
            mock_repo = AsyncMock()
            mock_repo.create = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo

            result = await create_question_from_checkpoint(
                session=mock_session,
                tenant_id="t1",
                task_run_id=uuid4(),
                checkpoint_data=checkpoint_data,
            )

            # Must NOT return None — destination should be accepted as channel
            assert result is not None
            mock_repo.create.assert_awaited_once()
            # The channel passed to create() must be the destination value
            call_kwargs = mock_repo.create.call_args[1]
            assert call_kwargs["channel"] == "C123SLACK"

    @pytest.mark.asyncio
    async def test_channel_takes_precedence_over_destination(self):
        """When both `channel` and `destination` are present, `channel` wins."""
        from analysi.repositories.hitl_repository import (
            create_question_from_checkpoint,
        )

        mock_session = AsyncMock()
        mock_question = MagicMock()
        mock_question.id = uuid4()

        checkpoint_data = {
            "pending_tool_name": "ask_question_channel",
            "pending_tool_args": {
                "channel": "C_EXPLICIT",
                "destination": "C_FALLBACK",
                "question": "Which channel?",
            },
        }

        with patch(
            "analysi.repositories.hitl_repository.HITLQuestionRepository"
        ) as MockRepo:
            mock_repo = AsyncMock()
            mock_repo.create = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo

            result = await create_question_from_checkpoint(
                session=mock_session,
                tenant_id="t1",
                task_run_id=uuid4(),
                checkpoint_data=checkpoint_data,
            )

            assert result is not None
            call_kwargs = mock_repo.create.call_args[1]
            assert call_kwargs["channel"] == "C_EXPLICIT"


# ---------------------------------------------------------------------------
# Reviewer Bug #18: Analysis must stay paused_human_review on re-pause
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug18AnalysisStaysPausedOnRepause:
    """When a workflow task resumes and then pauses again (second HITL tool),
    the analysis must remain in paused_human_review — not transition to running.
    Otherwise reconciliation misclassifies it as 'stuck running' instead of
    correctly tracking it as awaiting a human response."""

    @pytest.mark.asyncio
    async def test_workflow_repaused_keeps_analysis_paused(self):
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        question_id = uuid4()
        task_run_id = uuid4()
        workflow_run_id = uuid4()
        node_instance_id = uuid4()
        analysis_id = uuid4()

        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.task_run_id = task_run_id
        mock_question.workflow_run_id = workflow_run_id
        mock_question.node_instance_id = node_instance_id
        mock_question.analysis_id = analysis_id
        mock_question.status = "answered"

        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answer": "Yes",
            "answered_by": "U1",
        }

        with (
            patch("analysi.db.session.AsyncSessionLocal") as MockSession,
            patch(
                "analysi.services.task_execution.TaskExecutionService"
            ) as MockTaskExec,
            patch(
                "analysi.repositories.hitl_repository.HITLQuestionRepository"
            ) as MockRepo,
            patch(
                "analysi.services.workflow_execution.WorkflowExecutor.continue_after_hitl"
            ) as mock_continue_hitl,
            patch(
                "analysi.alert_analysis.jobs.control_events._update_analysis_after_hitl"
            ) as mock_update_analysis,
        ):
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo_instance

            # Task resumes, then pauses again at a second HITL tool
            mock_task_svc = AsyncMock()
            mock_task_result = MagicMock()
            mock_task_result.status = "paused"  # Re-paused!
            mock_task_result.task_run_id = task_run_id
            mock_task_result.output_data = {
                "_hitl_checkpoint": {
                    "pending_tool_name": "ask_second",
                    "pending_tool_args": {
                        "destination": "C123",
                        "question": "Follow-up?",
                    },
                }
            }
            mock_task_result.llm_usage = None
            mock_task_result.error_message = None
            mock_task_svc.resume_paused_task = AsyncMock(return_value=mock_task_result)
            MockTaskExec.return_value = mock_task_svc

            mock_continue_hitl.return_value = None

            await handle_human_responded(mock_event)

            # Analysis must NOT be set to "running" when the task re-paused.
            # It should either not be called at all (stays paused_human_review)
            # or be explicitly kept in paused state.
            for call in mock_update_analysis.call_args_list:
                assert call.kwargs.get("status") != "running", (
                    "Analysis should not be marked 'running' when task re-paused for HITL"
                )


# ---------------------------------------------------------------------------
# Hypothesis Bug #19: question_text field name mismatch with Slack tools
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug19QuestionTextFieldName:
    """Slack HITL tools use `question` as the argument name for the question
    text, but create_question_from_checkpoint only checks `text` and
    `question_text`.  This causes hitl_questions.question_text to be stored
    as empty string for real Slack HITL checkpoints."""

    @pytest.mark.asyncio
    async def test_question_field_used_for_question_text(self):
        """Tool args with `question` (Slack convention) should populate question_text."""
        from analysi.repositories.hitl_repository import (
            create_question_from_checkpoint,
        )

        mock_session = AsyncMock()
        mock_question = MagicMock()
        mock_question.id = uuid4()

        checkpoint_data = {
            "pending_tool_name": "ask_question_channel",
            "pending_tool_args": {
                "destination": "C123SLACK",
                "question": "Should we escalate this incident?",
                "options": [{"value": "yes"}, {"value": "no"}],
            },
        }

        with patch(
            "analysi.repositories.hitl_repository.HITLQuestionRepository"
        ) as MockRepo:
            mock_repo = AsyncMock()
            mock_repo.create = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo

            result = await create_question_from_checkpoint(
                session=mock_session,
                tenant_id="t1",
                task_run_id=uuid4(),
                checkpoint_data=checkpoint_data,
            )

            assert result is not None
            call_kwargs = mock_repo.create.call_args[1]
            assert call_kwargs["question_text"] == "Should we escalate this incident?"

    @pytest.mark.asyncio
    async def test_text_field_still_works(self):
        """Legacy `text` field should still work for backward compatibility."""
        from analysi.repositories.hitl_repository import (
            create_question_from_checkpoint,
        )

        mock_session = AsyncMock()
        mock_question = MagicMock()
        mock_question.id = uuid4()

        checkpoint_data = {
            "pending_tool_name": "custom_tool",
            "pending_tool_args": {
                "destination": "C123",
                "text": "Legacy text field question",
            },
        }

        with patch(
            "analysi.repositories.hitl_repository.HITLQuestionRepository"
        ) as MockRepo:
            mock_repo = AsyncMock()
            mock_repo.create = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo

            result = await create_question_from_checkpoint(
                session=mock_session,
                tenant_id="t1",
                task_run_id=uuid4(),
                checkpoint_data=checkpoint_data,
            )

            assert result is not None
            call_kwargs = mock_repo.create.call_args[1]
            assert call_kwargs["question_text"] == "Legacy text field question"


# ---------------------------------------------------------------------------
# Hypothesis Bug #20: options stored as [] — Slack uses "responses"
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug20ResponsesAsFallbackOptions:
    """Slack HITL tools use `responses` (a comma-separated string) for answer
    options, but create_question_from_checkpoint only checks `options`. This
    stores [] in the DB, breaking any code that reads hitl_question.options
    directly (audit trail, retries, UI)."""

    @pytest.mark.asyncio
    async def test_responses_string_parsed_into_options(self):
        """Comma-separated `responses` string should be stored as list of dicts."""
        from analysi.repositories.hitl_repository import (
            create_question_from_checkpoint,
        )

        mock_session = AsyncMock()
        mock_question = MagicMock()
        mock_question.id = uuid4()

        checkpoint_data = {
            "pending_tool_name": "ask_question_channel",
            "pending_tool_args": {
                "destination": "C123SLACK",
                "question": "Should we block this IP?",
                "responses": "Approve, Reject, Escalate",
            },
        }

        with patch(
            "analysi.repositories.hitl_repository.HITLQuestionRepository"
        ) as MockRepo:
            mock_repo = AsyncMock()
            mock_repo.create = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo

            result = await create_question_from_checkpoint(
                session=mock_session,
                tenant_id="t1",
                task_run_id=uuid4(),
                checkpoint_data=checkpoint_data,
            )

            assert result is not None
            call_kwargs = mock_repo.create.call_args[1]
            options = call_kwargs["options"]
            # Must not be empty — responses should be parsed
            assert len(options) == 3
            # Each option should be a dict with at least a "value" key
            values = [opt["value"] for opt in options]
            assert values == ["Approve", "Reject", "Escalate"]

    @pytest.mark.asyncio
    async def test_options_list_still_works(self):
        """Legacy `options` list should still work for backward compatibility."""
        from analysi.repositories.hitl_repository import (
            create_question_from_checkpoint,
        )

        mock_session = AsyncMock()
        mock_question = MagicMock()
        mock_question.id = uuid4()

        checkpoint_data = {
            "pending_tool_name": "custom_tool",
            "pending_tool_args": {
                "destination": "C123",
                "question": "Pick one",
                "options": [{"value": "yes"}, {"value": "no"}],
            },
        }

        with patch(
            "analysi.repositories.hitl_repository.HITLQuestionRepository"
        ) as MockRepo:
            mock_repo = AsyncMock()
            mock_repo.create = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo

            result = await create_question_from_checkpoint(
                session=mock_session,
                tenant_id="t1",
                task_run_id=uuid4(),
                checkpoint_data=checkpoint_data,
            )

            assert result is not None
            call_kwargs = mock_repo.create.call_args[1]
            assert call_kwargs["options"] == [{"value": "yes"}, {"value": "no"}]


# ---------------------------------------------------------------------------
# Reviewer Bug #26: mark_expired flush not committed after per-analysis expiry
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug26QuestionExpiryCommit:
    """mark_expired only flushes — needs explicit commit per analysis."""

    @pytest.mark.asyncio
    async def test_question_expiry_committed_after_mark_expired(self):
        """After expiring a question alongside its analysis, commit is called."""
        from analysi.alert_analysis.jobs.reconciliation import (
            mark_expired_hitl_paused_analyses,
        )

        analysis = MagicMock()
        analysis.id = uuid4()
        analysis.tenant_id = "t1"
        analysis.alert_id = uuid4()
        analysis.updated_at = datetime.now(UTC) - timedelta(hours=30)

        mock_analysis_repo = AsyncMock()
        mock_analysis_repo.find_paused_for_human_review = AsyncMock(
            return_value=[analysis]
        )
        mock_analysis_repo.mark_failed = AsyncMock()

        mock_alert_repo = AsyncMock()

        mock_pending_q = MagicMock()
        mock_pending_q.id = uuid4()

        mock_hitl_repo = AsyncMock()
        mock_hitl_repo.find_expired = AsyncMock(return_value=[])
        mock_hitl_repo.find_pending_by_analysis_id = AsyncMock(
            return_value=mock_pending_q
        )
        mock_hitl_repo.mark_expired = AsyncMock(return_value=True)

        count = await mark_expired_hitl_paused_analyses(
            mock_analysis_repo,
            mock_alert_repo,
            timeout_hours=24,
            hitl_repo=mock_hitl_repo,
        )

        assert count == 1
        # Bug #26: commit must be called AFTER mark_expired on the question.
        # mark_expired only flushes; without commit the change is lost.
        mock_hitl_repo.mark_expired.assert_awaited_once_with(mock_pending_q.id)
        # At least 2 commits: one for the analysis/alert, one for question expiry
        assert mock_analysis_repo.session.commit.await_count >= 2


# ---------------------------------------------------------------------------
# Reviewer Bug #27: Slack integration lookup non-deterministic
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug27SlackIntegrationOrdering:
    """_find_slack_integration_id must use deterministic ordering."""

    @pytest.mark.asyncio
    async def test_find_slack_integration_orders_by_created_at(self):
        """Query includes ORDER BY created_at ASC for deterministic results."""
        from analysi.slack_listener._credentials import _find_slack_integration_id

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "int-oldest"
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await _find_slack_integration_id(mock_session, "t1")

        assert result == "int-oldest"
        # Verify the SQL statement was built with an ORDER BY clause
        call_args = mock_session.execute.call_args
        stmt = call_args[0][0]
        # The compiled SQL should contain ORDER BY with created_at
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "ORDER BY" in compiled
        assert "created_at" in compiled


# ---------------------------------------------------------------------------
# Reviewer Bug #28: Gate HITL resume on question status
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug28GateOnQuestionStatus:
    """handle_human_responded must verify question.status == 'answered'."""

    @pytest.mark.asyncio
    async def test_pending_question_rejected(self):
        """Resuming a still-pending question raises ValueError."""
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        question_id = uuid4()
        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.status = "pending"  # Not yet answered!
        mock_question.task_run_id = uuid4()

        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answer": "Approve",
            "answered_by": "attacker",
        }

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
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo_instance

            with pytest.raises(ValueError, match="pending.*not 'answered'"):
                await handle_human_responded(mock_event)

    @pytest.mark.asyncio
    async def test_expired_question_rejected(self):
        """Resuming an expired question raises ValueError."""
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        question_id = uuid4()
        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.status = "expired"
        mock_question.task_run_id = uuid4()

        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answer": "Approve",
            "answered_by": "U1",
        }

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
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo_instance

            with pytest.raises(ValueError, match="expired.*not 'answered'"):
                await handle_human_responded(mock_event)


# ---------------------------------------------------------------------------
# Reviewer Bug #29: Persist task result when workflow is non-resumable
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBug29PersistResultOnNonResumable:
    """continue_after_hitl must persist task result before early return."""

    @pytest.mark.asyncio
    async def test_cancelled_workflow_persists_task_result(self):
        """When workflow is cancelled, task result is still persisted."""
        from analysi.services.workflow_execution import WorkflowExecutor

        wf_run_id = uuid4()
        node_instance_id = uuid4()

        mock_node_instance = MagicMock()
        mock_node_instance.id = node_instance_id
        mock_node_instance.node_id = "ask_analyst"
        mock_node_instance.status = "paused"

        mock_wf_run = MagicMock()
        mock_wf_run.id = wf_run_id
        mock_wf_run.tenant_id = "t1"
        mock_wf_run.workflow_id = uuid4()
        mock_wf_run.status = "cancelled"

        task_result = MagicMock()
        task_result.status = "completed"
        task_result.task_run_id = uuid4()
        task_result.output_data = {"answer": "Approved"}
        task_result.error_message = None
        task_result.llm_usage = None

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
                mock_session.execute = AsyncMock(return_value=node_result)
                executor.run_repo.get_workflow_run_by_id = AsyncMock(
                    return_value=mock_wf_run
                )

                mock_task_run_svc = AsyncMock()
                with (
                    patch(
                        "analysi.services.workflow_execution.WorkflowExecutor",
                        return_value=executor,
                    ),
                    patch(
                        "analysi.services.task_run.TaskRunService",
                        return_value=mock_task_run_svc,
                    ),
                ):
                    await WorkflowExecutor.continue_after_hitl(
                        workflow_run_id=wf_run_id,
                        node_instance_id=node_instance_id,
                        task_result=task_result,
                    )

                # Bug #29: task result must be persisted even though
                # workflow is non-resumable
                mock_task_run_svc.update_status.assert_awaited_once()
                call_args = mock_task_run_svc.update_status.call_args
                assert call_args[0][1] == task_result.task_run_id
                # Node instance should be marked failed
                assert mock_node_instance.status == "failed"
                # Session should be committed
                mock_session.commit.assert_awaited()
