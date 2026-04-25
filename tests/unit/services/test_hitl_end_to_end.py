"""
Unit tests for HITL End-to-End & Hardening.

Tests the full HITL flow, multi-tenant routing, audit trail logging,
and timeout/expiry handling.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.constants import HITLQuestionConstants

# ---------------------------------------------------------------------------
# E2E: Full HITL flow (mocked) — pause → question → answer → resume
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHITLEndToEndFlow:
    """Full HITL flow from task pause to resume via human:responded event."""

    @pytest.mark.asyncio
    async def test_full_flow_standalone_task(self):
        """Task pauses → question created → sender called → human responds → task resumes."""
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        question_id = uuid4()
        task_run_id = uuid4()

        # Mock question with standalone context (no workflow)
        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.task_run_id = task_run_id
        mock_question.workflow_run_id = None
        mock_question.node_instance_id = None
        mock_question.analysis_id = None
        mock_question.answer = "Escalate"
        mock_question.status = "answered"

        # Build event
        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answer": "Escalate",
            "answered_by": "U123",
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
                "analysi.repositories.activity_audit_repository.ActivityAuditRepository"
            ) as MockAuditRepo,
            patch("analysi.services.task_run.TaskRunService") as MockTaskRunSvc,
        ):
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            # Mock repo
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo_instance

            # Mock task execution
            mock_task_svc = AsyncMock()
            mock_task_result = MagicMock()
            mock_task_result.status = "completed"
            mock_task_result.task_run_id = task_run_id
            mock_task_result.output_data = {"result": "done"}
            mock_task_result.llm_usage = None
            mock_task_result.error_message = None
            mock_task_svc.resume_paused_task = AsyncMock(return_value=mock_task_result)
            MockTaskExec.return_value = mock_task_svc

            # Mock TaskRunService for standalone result persistence
            mock_task_run_svc = AsyncMock()
            MockTaskRunSvc.return_value = mock_task_run_svc

            # Mock audit repo
            mock_audit_instance = AsyncMock()
            MockAuditRepo.return_value = mock_audit_instance

            await handle_human_responded(mock_event)

            # Task should have been resumed with the answer
            mock_task_svc.resume_paused_task.assert_awaited_once()
            call_kwargs = mock_task_svc.resume_paused_task.call_args.kwargs
            assert call_kwargs["human_response"] == "Escalate"
            assert call_kwargs["task_run_id"] == task_run_id

    @pytest.mark.asyncio
    async def test_full_flow_workflow_task(self):
        """Task pauses → question created → human responds → task + workflow resume."""
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
        mock_question.answer = "Approve"
        mock_question.status = "answered"

        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answer": "Approve",
            "answered_by": "U789",
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

            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo_instance

            mock_task_svc = AsyncMock()
            mock_task_result = MagicMock()
            mock_task_result.status = "completed"
            mock_task_result.task_run_id = task_run_id
            mock_task_result.output_data = {"result": "approved"}
            mock_task_result.llm_usage = None
            mock_task_result.error_message = None
            mock_task_svc.resume_paused_task = AsyncMock(return_value=mock_task_result)
            MockTaskExec.return_value = mock_task_svc

            # Mock continue_after_hitl (replaces _execute_workflow_synchronously)
            MockWfExec.continue_after_hitl = AsyncMock()

            mock_audit_instance = AsyncMock()
            MockAuditRepo.return_value = mock_audit_instance

            await handle_human_responded(mock_event)

            # Task resumed
            mock_task_svc.resume_paused_task.assert_awaited_once()

            # Workflow continued via continue_after_hitl
            MockWfExec.continue_after_hitl.assert_awaited_once_with(
                workflow_run_id=workflow_run_id,
                node_instance_id=node_instance_id,
                task_result=mock_task_result,
            )


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHITLAuditTrail:
    """Audit trail: HITL response is logged as an activity event."""

    @pytest.mark.asyncio
    async def test_audit_event_created_on_answer(self):
        """handle_human_responded logs hitl.question_answered audit event."""
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
        mock_question.answer = "Escalate"
        mock_question.status = "answered"

        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answer": "Escalate",
            "answered_by": "U999",
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

            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo_instance

            mock_task_svc = AsyncMock()
            mock_task_result = MagicMock()
            mock_task_result.status = "completed"
            mock_task_result.task_run_id = task_run_id
            mock_task_result.output_data = {"result": "done"}
            mock_task_result.llm_usage = None
            mock_task_result.error_message = None
            mock_task_svc.resume_paused_task = AsyncMock(return_value=mock_task_result)
            MockTaskExec.return_value = mock_task_svc
            MockWfExec.continue_after_hitl = AsyncMock()

            mock_audit_instance = AsyncMock()
            MockAuditRepo.return_value = mock_audit_instance

            await handle_human_responded(mock_event)

            # Verify audit repo.create was called with correct fields
            mock_audit_instance.create.assert_awaited_once()
            call_kwargs = mock_audit_instance.create.call_args.kwargs
            assert call_kwargs["tenant_id"] == "t1"
            assert call_kwargs["actor_id"] is not None, (
                "actor_id must not be None — DB has NOT NULL constraint"
            )
            assert call_kwargs["actor_type"] == "external_user"
            assert call_kwargs["source"] == "internal"
            assert call_kwargs["action"] == "hitl.question_answered"
            assert call_kwargs["resource_type"] == "hitl_question"
            assert call_kwargs["resource_id"] == str(question_id)
            assert call_kwargs["details"]["answer"] == "Escalate"
            assert call_kwargs["details"]["answered_by"] == "U999"
            assert call_kwargs["details"]["task_run_id"] == str(task_run_id)
            assert call_kwargs["details"]["workflow_run_id"] == str(workflow_run_id)
            assert call_kwargs["details"]["analysis_id"] == str(analysis_id)

    @pytest.mark.asyncio
    async def test_audit_failure_does_not_break_handler(self):
        """If audit logging fails, the handler still completes successfully."""
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
            patch(
                "analysi.repositories.activity_audit_repository.ActivityAuditRepository"
            ) as MockAuditRepo,
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
            mock_task_result.output_data = {"result": "yes"}
            mock_task_result.llm_usage = None
            mock_task_result.error_message = None
            mock_task_svc.resume_paused_task = AsyncMock(return_value=mock_task_result)
            MockTaskExec.return_value = mock_task_svc

            # Mock TaskRunService for standalone result persistence
            mock_task_run_svc = AsyncMock()
            MockTaskRunSvc.return_value = mock_task_run_svc

            # Make audit repo raise an exception
            mock_audit_instance = AsyncMock()
            mock_audit_instance.create = AsyncMock(side_effect=RuntimeError("DB error"))
            MockAuditRepo.return_value = mock_audit_instance

            # Should NOT raise — audit failure is swallowed
            await handle_human_responded(mock_event)

            # Task resume still happened
            mock_task_svc.resume_paused_task.assert_awaited_once()


# ---------------------------------------------------------------------------
# Multi-tenant routing
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHITLMultiTenantRouting:
    """Multi-tenant: two tenants share workspace, correct routing by tenant_id."""

    @pytest.mark.asyncio
    async def test_handler_routes_by_tenant_from_question(self):
        """Button click routes to correct tenant based on hitl_question's tenant_id."""
        from analysi.slack_listener.handler import InteractivePayloadHandler

        handler = InteractivePayloadHandler()

        # Question belongs to tenant-2
        mock_question = MagicMock()
        mock_question.id = uuid4()
        mock_question.tenant_id = "tenant-2"
        mock_question.task_run_id = uuid4()
        mock_question.workflow_run_id = uuid4()
        mock_question.node_instance_id = uuid4()
        mock_question.analysis_id = uuid4()
        mock_question.status = HITLQuestionConstants.Status.PENDING
        mock_question.question_text = "Approve?"
        mock_question.channel = "C-shared"
        mock_question.question_ref = "ts-shared"

        payload = {
            "type": "block_actions",
            "actions": [{"value": "Approve"}],
            "channel": {"id": "C-shared"},
            "container": {"message_ts": "ts-shared"},
            "user": {"id": "U-analyst", "username": "analyst"},
        }

        with patch("analysi.slack_listener.handler.AsyncSessionLocal") as MockSession:
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "analysi.slack_listener.handler.HITLQuestionRepository"
            ) as MockRepo:
                mock_repo = AsyncMock()
                mock_repo.find_by_ref = AsyncMock(return_value=mock_question)
                mock_repo.record_answer = AsyncMock(return_value=True)
                MockRepo.return_value = mock_repo

                with patch.object(
                    handler, "_update_slack_message", new_callable=AsyncMock
                ):
                    await handler.handle(payload)

                    # Control event should use the question's tenant_id, not any other
                    added_event = mock_session.add.call_args[0][0]
                    assert added_event.tenant_id == "tenant-2"
                    assert added_event.channel == "human:responded"

    @pytest.mark.asyncio
    async def test_two_tenants_same_channel_different_questions(self):
        """Two questions in same channel, different tenants — find_by_ref disambiguates."""
        from analysi.slack_listener.handler import InteractivePayloadHandler

        handler = InteractivePayloadHandler()

        # Question for tenant-1 with unique message_ts
        mock_question_t1 = MagicMock()
        mock_question_t1.id = uuid4()
        mock_question_t1.tenant_id = "tenant-1"
        mock_question_t1.task_run_id = uuid4()
        mock_question_t1.workflow_run_id = None
        mock_question_t1.node_instance_id = None
        mock_question_t1.analysis_id = None
        mock_question_t1.status = HITLQuestionConstants.Status.PENDING
        mock_question_t1.question_text = "Q for T1?"
        mock_question_t1.channel = "C-shared"
        mock_question_t1.question_ref = "ts-t1-unique"

        payload_t1 = {
            "type": "block_actions",
            "actions": [{"value": "Yes"}],
            "channel": {"id": "C-shared"},
            "container": {"message_ts": "ts-t1-unique"},
            "user": {"id": "U1", "username": "user1"},
        }

        with patch("analysi.slack_listener.handler.AsyncSessionLocal") as MockSession:
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            with patch(
                "analysi.slack_listener.handler.HITLQuestionRepository"
            ) as MockRepo:
                mock_repo = AsyncMock()
                # find_by_ref returns tenant-1's question
                mock_repo.find_by_ref = AsyncMock(return_value=mock_question_t1)
                mock_repo.record_answer = AsyncMock(return_value=True)
                MockRepo.return_value = mock_repo

                with patch.object(
                    handler, "_update_slack_message", new_callable=AsyncMock
                ):
                    await handler.handle(payload_t1)

                    # Control event uses tenant-1
                    added_event = mock_session.add.call_args[0][0]
                    assert added_event.tenant_id == "tenant-1"


# ---------------------------------------------------------------------------
# Timeout / expiry
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHITLQuestionTimeout:
    """Question expiry → reconciliation marks analysis as failed."""

    @pytest.mark.asyncio
    async def test_expired_questions_found_by_repository(self):
        """find_expired returns questions past their timeout_at."""
        from analysi.repositories.hitl_repository import HITLQuestionRepository

        # Create mock questions — one expired, one not
        expired_q = MagicMock()
        expired_q.id = uuid4()
        expired_q.timeout_at = datetime.now(UTC) - timedelta(hours=5)
        expired_q.status = "pending"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [expired_q]
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = HITLQuestionRepository(mock_session)
        expired = await repo.find_expired()

        assert len(expired) == 1
        assert expired[0].id == expired_q.id

    @pytest.mark.asyncio
    async def test_mark_expired_updates_status(self):
        """mark_expired updates status from pending to expired."""
        from analysi.repositories.hitl_repository import HITLQuestionRepository

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = HITLQuestionRepository(mock_session)
        result = await repo.mark_expired(uuid4())

        assert result is True

    @pytest.mark.asyncio
    async def test_reconciliation_marks_hitl_paused_analyses_failed(self):
        """mark_expired_hitl_paused_analyses marks timed-out analyses as failed."""
        from analysi.alert_analysis.jobs.reconciliation import (
            mark_expired_hitl_paused_analyses,
        )

        analysis_id = uuid4()
        mock_analysis = MagicMock()
        mock_analysis.id = analysis_id
        mock_analysis.tenant_id = "t1"
        # Paused 25 hours ago — should be expired with default 24h timeout
        mock_analysis.updated_at = datetime.now(UTC) - timedelta(hours=25)

        mock_analysis_repo = AsyncMock()
        mock_analysis_repo.find_paused_for_human_review = AsyncMock(
            return_value=[mock_analysis]
        )
        mock_analysis_repo.mark_failed = AsyncMock()

        mock_alert_repo = AsyncMock()

        count = await mark_expired_hitl_paused_analyses(
            mock_analysis_repo,
            mock_alert_repo,
            timeout_hours=24,
        )

        assert count == 1
        mock_analysis_repo.mark_failed.assert_awaited_once()
        # Bug #24: mark_stuck_alert_failed replaced with direct Alert UPDATE
        # via analysis_repo.session.execute (it filters on RUNNING, unusable here)
        mock_analysis_repo.session.execute.assert_awaited()
        mock_analysis_repo.session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_reconciliation_skips_recently_paused(self):
        """mark_expired_hitl_paused_analyses skips analyses within timeout window."""
        from analysi.alert_analysis.jobs.reconciliation import (
            mark_expired_hitl_paused_analyses,
        )

        mock_analysis = MagicMock()
        mock_analysis.id = uuid4()
        mock_analysis.tenant_id = "t1"
        # Paused 1 hour ago — still within 24h window
        mock_analysis.updated_at = datetime.now(UTC) - timedelta(hours=1)

        mock_analysis_repo = AsyncMock()
        mock_analysis_repo.find_paused_for_human_review = AsyncMock(
            return_value=[mock_analysis]
        )

        mock_alert_repo = AsyncMock()

        count = await mark_expired_hitl_paused_analyses(
            mock_analysis_repo,
            mock_alert_repo,
            timeout_hours=24,
        )

        assert count == 0
        mock_analysis_repo.mark_failed.assert_not_awaited()


# ---------------------------------------------------------------------------
# Credential schema validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHITLDockerCompose:
    """Verify Docker Compose includes the notifications-worker service."""

    def test_docker_compose_has_notifications_worker(self):
        """core.yml includes the notifications-worker service definition."""
        from pathlib import Path

        compose_path = Path("deployments/compose/core.yml")
        content = compose_path.read_text()

        # Service definition and entrypoint — container_name is derived from
        # COMPOSE_PROJECT_NAME at runtime (worktree-safe parameterization).
        assert "notifications-worker:" in content
        assert "analysi.slack_listener" in content


# ---------------------------------------------------------------------------
# Unhappy paths: handle_human_responded
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHandleHumanRespondedUnhappyPaths:
    """Error handling in handle_human_responded for malformed payloads and failures."""

    @pytest.mark.asyncio
    async def test_missing_question_id_raises_key_error(self):
        """Payload without question_id raises KeyError (propagated to caller)."""
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {"answer": "Yes", "answered_by": "U1"}

        with pytest.raises(KeyError, match="question_id"):
            await handle_human_responded(mock_event)

    @pytest.mark.asyncio
    async def test_missing_answer_raises_key_error(self):
        """Payload without answer raises KeyError (propagated to caller)."""
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        question_id = uuid4()
        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answered_by": "U1",
        }

        with pytest.raises(KeyError, match="answer"):
            await handle_human_responded(mock_event)

    @pytest.mark.asyncio
    async def test_question_not_found_raises_value_error(self):
        """When question is not in DB, handler raises ValueError (Bug #6 fix)."""
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

            # Bug #6 fix: Must raise so control event is marked failed and retried
            with pytest.raises(ValueError, match="not found"):
                await handle_human_responded(mock_event)

    @pytest.mark.asyncio
    async def test_resume_paused_task_raises_propagates(self):
        """When resume_paused_task raises, the exception propagates to the caller."""
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        question_id = uuid4()
        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.task_run_id = uuid4()
        mock_question.workflow_run_id = None
        mock_question.node_instance_id = None
        mock_question.analysis_id = None
        mock_question.status = "answered"

        mock_event = MagicMock()
        mock_event.tenant_id = "t1"
        mock_event.payload = {
            "question_id": str(question_id),
            "answer": "Escalate",
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
        ):
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_question)
            MockRepo.return_value = mock_repo_instance

            mock_task_svc = AsyncMock()
            mock_task_svc.resume_paused_task = AsyncMock(
                side_effect=RuntimeError("Cy interpreter crashed")
            )
            MockTaskExec.return_value = mock_task_svc

            with pytest.raises(RuntimeError, match="Cy interpreter crashed"):
                await handle_human_responded(mock_event)

    @pytest.mark.asyncio
    async def test_workflow_resume_raises_propagates(self):
        """When continue_after_hitl raises, exception propagates."""
        from analysi.alert_analysis.jobs.control_events import (
            handle_human_responded,
        )

        question_id = uuid4()
        task_run_id = uuid4()
        workflow_run_id = uuid4()
        mock_question = MagicMock()
        mock_question.id = question_id
        mock_question.tenant_id = "t1"
        mock_question.task_run_id = task_run_id
        mock_question.workflow_run_id = workflow_run_id
        mock_question.node_instance_id = uuid4()
        mock_question.analysis_id = uuid4()
        mock_question.answer = "Approve"
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
            mock_task_result.output_data = {"result": "approved"}
            mock_task_result.llm_usage = None
            mock_task_result.error_message = None
            mock_task_svc.resume_paused_task = AsyncMock(return_value=mock_task_result)
            MockTaskExec.return_value = mock_task_svc

            # Workflow continuation fails
            MockWfExec.continue_after_hitl = AsyncMock(
                side_effect=RuntimeError("Workflow deadlock")
            )

            mock_audit_instance = AsyncMock()
            MockAuditRepo.return_value = mock_audit_instance

            with pytest.raises(RuntimeError, match="Workflow deadlock"):
                await handle_human_responded(mock_event)

            # Task was still resumed before workflow blew up
            mock_task_svc.resume_paused_task.assert_awaited_once()


# ---------------------------------------------------------------------------
# Unhappy paths: mark_expired_hitl_paused_analyses
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMarkExpiredHITLPausedAnalysesUnhappyPaths:
    """Edge cases for the HITL pause timeout/expiry reconciliation."""

    @pytest.mark.asyncio
    async def test_none_updated_at_treated_as_expired(self):
        """Analysis with None updated_at is treated as expired and marked failed."""
        from analysi.alert_analysis.jobs.reconciliation import (
            mark_expired_hitl_paused_analyses,
        )

        analysis = MagicMock()
        analysis.id = uuid4()
        analysis.tenant_id = "t1"
        analysis.alert_id = uuid4()
        analysis.updated_at = None  # No timestamp → treated as expired

        mock_analysis_repo = AsyncMock()
        mock_analysis_repo.find_paused_for_human_review = AsyncMock(
            return_value=[analysis]
        )
        mock_analysis_repo.mark_failed = AsyncMock()

        mock_alert_repo = AsyncMock()

        count = await mark_expired_hitl_paused_analyses(
            mock_analysis_repo,
            mock_alert_repo,
            timeout_hours=24,
        )

        assert count == 1
        mock_analysis_repo.mark_failed.assert_awaited_once()
        # Bug #24: direct Alert UPDATE via session.execute
        mock_analysis_repo.session.execute.assert_awaited()
        mock_analysis_repo.session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_mark_failed_exception_continues_loop(self):
        """If mark_failed raises for one analysis, the loop continues for the rest."""
        from analysi.alert_analysis.jobs.reconciliation import (
            mark_expired_hitl_paused_analyses,
        )

        analysis_ok = MagicMock()
        analysis_ok.id = uuid4()
        analysis_ok.tenant_id = "t1"
        analysis_ok.alert_id = uuid4()
        analysis_ok.updated_at = datetime.now(UTC) - timedelta(hours=48)

        analysis_fail = MagicMock()
        analysis_fail.id = uuid4()
        analysis_fail.tenant_id = "t1"
        analysis_fail.alert_id = uuid4()
        analysis_fail.updated_at = datetime.now(UTC) - timedelta(hours=48)

        mock_analysis_repo = AsyncMock()
        mock_analysis_repo.find_paused_for_human_review = AsyncMock(
            return_value=[analysis_fail, analysis_ok]
        )
        # First call raises, second succeeds
        mock_analysis_repo.mark_failed = AsyncMock(
            side_effect=[RuntimeError("DB deadlock"), None]
        )

        mock_alert_repo = AsyncMock()

        count = await mark_expired_hitl_paused_analyses(
            mock_analysis_repo,
            mock_alert_repo,
            timeout_hours=24,
        )

        # Only the second one succeeded
        assert count == 1
        assert mock_analysis_repo.mark_failed.await_count == 2
        # Bug #24: direct Alert UPDATE via session.execute for the successful one
        assert mock_analysis_repo.session.execute.await_count >= 1
        assert mock_analysis_repo.session.commit.await_count >= 1

    @pytest.mark.asyncio
    async def test_naive_timestamp_gets_utc_treatment(self):
        """Analysis with naive (tz-unaware) updated_at is treated as UTC."""
        from analysi.alert_analysis.jobs.reconciliation import (
            mark_expired_hitl_paused_analyses,
        )

        analysis = MagicMock()
        analysis.id = uuid4()
        analysis.tenant_id = "t1"
        analysis.alert_id = uuid4()
        # Naive timestamp: 25 hours ago without tzinfo
        analysis.updated_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(
            hours=25
        )

        mock_analysis_repo = AsyncMock()
        mock_analysis_repo.find_paused_for_human_review = AsyncMock(
            return_value=[analysis]
        )
        mock_analysis_repo.mark_failed = AsyncMock()

        mock_alert_repo = AsyncMock()

        count = await mark_expired_hitl_paused_analyses(
            mock_analysis_repo,
            mock_alert_repo,
            timeout_hours=24,
        )

        # Should still be detected as expired despite naive timestamp
        assert count == 1
        mock_analysis_repo.mark_failed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_paused_list_returns_zero(self):
        """No paused analyses returns 0 without calling mark_failed."""
        from analysi.alert_analysis.jobs.reconciliation import (
            mark_expired_hitl_paused_analyses,
        )

        mock_analysis_repo = AsyncMock()
        mock_analysis_repo.find_paused_for_human_review = AsyncMock(return_value=[])

        mock_alert_repo = AsyncMock()

        count = await mark_expired_hitl_paused_analyses(
            mock_analysis_repo,
            mock_alert_repo,
            timeout_hours=24,
        )

        assert count == 0
