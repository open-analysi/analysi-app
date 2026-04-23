"""
Bug #30: Executor does not pass HITL checkpoint to Cy interpreter on resume.

When resume_paused_task injects the human's answer into the checkpoint and
stores it in execution_context["_hitl_checkpoint"], the DefaultTaskExecutor
must extract it and pass it to run_native_async(checkpoint=...) so memoized
replay works. Without this, the script re-executes from scratch and pauses
again at the same hi-latency tool.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


def _make_execution_context(**overrides):
    """Build a minimal execution_context for testing."""
    ctx = {
        "task_id": str(uuid4()),
        "task_run_id": str(uuid4()),
        "tenant_id": "default",
        "app": "default",
        "cy_name": None,
        "workflow_run_id": None,
        "session": AsyncMock(),
        "directive": None,
    }
    ctx.update(overrides)
    return ctx


def _patch_tool_loaders(executor):
    """Patch all tool-loading methods to return empty dicts (no DB needed)."""
    for method_name in (
        "_load_tools",
        "_load_time_functions",
        "_load_artifact_functions",
        "_load_llm_functions",
        "_load_ku_functions",
        "_load_task_functions",
        "_load_alert_functions",
        "_load_enrichment_functions",
        "_load_app_tools",
    ):
        method = getattr(executor, method_name, None)
        if method is None:
            continue
        import asyncio

        if asyncio.iscoroutinefunction(method):
            setattr(executor, method_name, AsyncMock(return_value={}))
        else:
            from unittest.mock import MagicMock

            setattr(executor, method_name, MagicMock(return_value={}))


@pytest.mark.unit
class TestCheckpointPassthrough:
    """DefaultTaskExecutor must pass checkpoint to Cy interpreter."""

    @pytest.mark.asyncio
    async def test_checkpoint_from_execution_context_passed_to_interpreter(self):
        """When execution_context has _hitl_checkpoint, run_native_async receives it."""
        from analysi.services.task_execution import DefaultTaskExecutor

        executor = DefaultTaskExecutor()
        _patch_tool_loaders(executor)

        checkpoint_data = {
            "node_results": {"node_10": {"ts": "123"}},
            "pending_node_id": "node_14",
            "pending_tool_name": "app::slack::ask_question_channel",
            "pending_tool_args": {
                "destination": "C123",
                "question": "Escalate?",
                "responses": "Yes,No",
            },
            "pending_tool_result": "Yes",
            "variables": {"alert": {"title": "Test"}},
            "plan_version": "0.40.0",
        }

        execution_context = _make_execution_context(_hitl_checkpoint=checkpoint_data)

        mock_interpreter = AsyncMock()
        mock_interpreter.run_native_async = AsyncMock(return_value="done")

        with patch("analysi.services.task_execution.Cy") as MockCy:
            MockCy.create_async = AsyncMock(return_value=mock_interpreter)

            await executor.execute(
                'return "done"', {"title": "Test"}, execution_context
            )

        mock_interpreter.run_native_async.assert_awaited_once()
        call_kwargs = mock_interpreter.run_native_async.call_args
        assert call_kwargs.kwargs.get("checkpoint") is not None, (
            "Checkpoint must be passed to run_native_async for memoized replay"
        )

    @pytest.mark.asyncio
    async def test_no_checkpoint_when_execution_context_lacks_it(self):
        """Normal execution (no HITL) should not pass checkpoint."""
        from analysi.services.task_execution import DefaultTaskExecutor

        executor = DefaultTaskExecutor()
        _patch_tool_loaders(executor)

        execution_context = _make_execution_context()

        mock_interpreter = AsyncMock()
        mock_interpreter.run_native_async = AsyncMock(return_value="hello")

        with patch("analysi.services.task_execution.Cy") as MockCy:
            MockCy.create_async = AsyncMock(return_value=mock_interpreter)

            await executor.execute('return "hello"', {}, execution_context)

        call_kwargs = mock_interpreter.run_native_async.call_args
        checkpoint_arg = call_kwargs.kwargs.get("checkpoint")
        assert checkpoint_arg is None, "Normal execution should not pass a checkpoint"

    @pytest.mark.asyncio
    async def test_checkpoint_has_correct_pending_tool_result(self):
        """The checkpoint passed to the interpreter contains the injected answer."""
        from analysi.services.task_execution import DefaultTaskExecutor

        executor = DefaultTaskExecutor()
        _patch_tool_loaders(executor)

        checkpoint_data = {
            "node_results": {},
            "pending_node_id": "node_5",
            "pending_tool_name": "app::slack::ask_question_channel",
            "pending_tool_args": {"question": "OK?", "responses": "Yes,No"},
            "pending_tool_result": "No",
            "variables": {},
            "plan_version": "0.40.0",
        }

        execution_context = _make_execution_context(_hitl_checkpoint=checkpoint_data)

        mock_interpreter = AsyncMock()
        mock_interpreter.run_native_async = AsyncMock(return_value="result")

        with patch("analysi.services.task_execution.Cy") as MockCy:
            MockCy.create_async = AsyncMock(return_value=mock_interpreter)

            await executor.execute('return "x"', {}, execution_context)

        call_kwargs = mock_interpreter.run_native_async.call_args
        checkpoint = call_kwargs.kwargs["checkpoint"]
        assert checkpoint.pending_tool_result == "No"
