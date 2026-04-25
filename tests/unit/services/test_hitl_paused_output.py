"""
Tests for HITL paused task output — clean status object, no checkpoint blob.

When a task pauses for HITL, output_location should contain a readable
status object (question, channel), not the raw _hitl_checkpoint blob.
The checkpoint lives only in execution_context.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.mark.unit
class TestPausedTaskOutputFormat:
    """Paused tasks store a clean status object as output, not the checkpoint."""

    @pytest.mark.asyncio
    async def test_paused_output_contains_status_and_question(self):
        """execute_and_persist stores readable paused output with question text."""
        from analysi.services.task_execution import TaskExecutionService

        svc = TaskExecutionService()
        task_run_id = uuid4()

        # Mock execute_single_task to return a paused result
        mock_result = MagicMock()
        mock_result.status = "paused"
        mock_result.task_run_id = task_run_id
        mock_result.output_data = {
            "_hitl_checkpoint": {
                "node_results": {"node_10": {"ts": "123"}},
                "pending_node_id": "node_14",
                "pending_tool_name": "app::slack::ask_question_channel",
                "pending_tool_args": {
                    "destination": "C09KDTJF6JZ",
                    "question": "Should we escalate?",
                    "responses": "Yes,No",
                },
                "pending_tool_result": None,
                "variables": {},
                "plan_version": "2.0",
            }
        }
        mock_result.llm_usage = None
        mock_result.log_entries = []

        with (
            patch.object(svc, "execute_single_task", return_value=mock_result),
            patch("analysi.db.session.AsyncSessionLocal") as MockSession,
            patch("analysi.services.task_run.TaskRunService") as MockTaskRunSvc,
        ):
            mock_session = AsyncMock()
            MockSession.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            MockSession.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_task_run_svc = AsyncMock()
            MockTaskRunSvc.return_value = mock_task_run_svc

            await svc.execute_and_persist(task_run_id, "default")

            # Check what output_data was passed to update_status
            call_args = mock_task_run_svc.update_status.call_args
            output_data = call_args.kwargs.get("output_data") or call_args[1].get(
                "output_data"
            )

            # Must have clean status fields
            assert output_data["status"] == "paused"
            assert output_data["reason"] == "waiting_for_human_response"
            assert output_data["question"] == "Should we escalate?"
            assert output_data["channel"] == "C09KDTJF6JZ"

            # Must still include _hitl_checkpoint for execution_context extraction
            assert "_hitl_checkpoint" in output_data

    @pytest.mark.asyncio
    async def test_update_status_strips_checkpoint_from_output_location(self):
        """update_status stores checkpoint in execution_context, not output_location."""
        from analysi.services.task_run import TaskRunService

        svc = TaskRunService()

        mock_task_run = MagicMock()
        mock_task_run.id = uuid4()
        mock_task_run.execution_context = {}
        mock_task_run.started_at = None

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task_run
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Mock store_output_data to capture what gets stored
        stored_output = {}

        async def capture_store(task_run, output_data):
            stored_output.update(output_data)

        svc.store_output_data = capture_store

        # Mock repository update
        svc.repository = AsyncMock()

        output_data = {
            "status": "paused",
            "reason": "waiting_for_human_response",
            "question": "Escalate?",
            "channel": "C123",
            "_hitl_checkpoint": {
                "node_results": {},
                "pending_tool_result": None,
            },
        }

        await svc.update_status(
            mock_session, mock_task_run.id, "paused", output_data=output_data
        )

        # output_location should NOT contain _hitl_checkpoint
        assert "_hitl_checkpoint" not in stored_output
        assert stored_output["status"] == "paused"
        assert stored_output["question"] == "Escalate?"

        # execution_context SHOULD contain _hitl_checkpoint
        assert "_hitl_checkpoint" in mock_task_run.execution_context

    @pytest.mark.asyncio
    async def test_completed_output_unchanged(self):
        """Completed tasks still store full output as-is (no stripping)."""
        from analysi.services.task_run import TaskRunService

        svc = TaskRunService()

        mock_task_run = MagicMock()
        mock_task_run.id = uuid4()
        mock_task_run.execution_context = {}
        from datetime import UTC, datetime

        mock_task_run.started_at = datetime.now(UTC)
        mock_task_run.completed_at = None

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task_run
        mock_session.execute = AsyncMock(return_value=mock_result)

        stored_output = {}

        async def capture_store(task_run, output_data):
            stored_output.update(output_data)

        svc.store_output_data = capture_store
        svc.repository = AsyncMock()

        output_data = {
            "analyst_decision": "Escalate",
            "action_taken": "escalated",
        }

        await svc.update_status(
            mock_session, mock_task_run.id, "completed", output_data=output_data
        )

        # Full output preserved for completed tasks
        assert stored_output["analyst_decision"] == "Escalate"
        assert stored_output["action_taken"] == "escalated"
