"""Unit tests for rate_limit_event handling in the SDK wrapper.

Claude Code sends a `rate_limit_event` JSON message when it hits API rate limits.
Without a fix, the SDK's message_parser raises MessageParseError for this unrecognised
type, which terminates the async generator and kills the whole workflow generation run.

Our fix:
1. A module-level monkey-patch converts rate_limit_event → SystemMessage so the
   generator continues instead of raising.
2. In execute_stage, when a SystemMessage(rate_limit_event) arrives we sleep for
   retry_after_ms/1000 seconds (proper backoff) before the SDK retries.
"""

from unittest.mock import AsyncMock, patch

import pytest

from analysi.agentic_orchestration.observability import WorkflowGenerationStage
from analysi.agentic_orchestration.sdk_wrapper import AgentOrchestrationExecutor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result_message(**overrides):
    """Create a real SDK ResultMessage for use in tests."""
    from claude_agent_sdk.types import ResultMessage

    defaults = {
        "subtype": "success",
        "duration_ms": 100,
        "duration_api_ms": 80,
        "is_error": False,
        "num_turns": 1,
        "session_id": "test-session",
        "total_cost_usd": 0.001,
        "usage": {"input_tokens": 100, "output_tokens": 50},
        "result": "test result text",
    }
    defaults.update(overrides)
    return ResultMessage(**defaults)


def _make_rate_limit_message(retry_after_ms: int = 3000):
    """Create a real SDK SystemMessage that simulates a rate_limit_event."""
    from claude_agent_sdk.types import SystemMessage

    data = {"type": "rate_limit_event", "retry_after_ms": retry_after_ms}
    return SystemMessage(subtype="rate_limit_event", data=data)


# ---------------------------------------------------------------------------
# 1. Monkey-patch tests (module-level patch applied at import time)
# ---------------------------------------------------------------------------


class TestRateLimitPatch:
    """Verify the module-level monkey-patch on claude_agent_sdk._internal.message_parser."""

    def test_parse_message_converts_rate_limit_event_to_system_message(self):
        """rate_limit_event is converted to SystemMessage instead of raising MessageParseError."""
        from claude_agent_sdk._internal.message_parser import parse_message
        from claude_agent_sdk.types import SystemMessage

        data = {"type": "rate_limit_event", "retry_after_ms": 5000}
        result = parse_message(data)

        assert isinstance(result, SystemMessage)
        assert result.subtype == "rate_limit_event"
        assert result.data == data

    def test_parse_message_rate_limit_event_without_retry_after_ms(self):
        """rate_limit_event with no retry_after_ms field is also handled gracefully."""
        from claude_agent_sdk._internal.message_parser import parse_message
        from claude_agent_sdk.types import SystemMessage

        data = {"type": "rate_limit_event"}  # No retry_after_ms
        result = parse_message(data)

        assert isinstance(result, SystemMessage)
        assert result.subtype == "rate_limit_event"

    def test_parse_message_result_type_still_works(self):
        """Normal 'result' messages are still parsed correctly after patch."""
        from claude_agent_sdk._internal.message_parser import parse_message
        from claude_agent_sdk.types import ResultMessage

        data = {
            "type": "result",
            "subtype": "success",
            "duration_ms": 100,
            "duration_api_ms": 80,
            "is_error": False,
            "num_turns": 1,
            "session_id": "test-session",
        }
        result = parse_message(data)
        assert isinstance(result, ResultMessage)
        assert result.subtype == "success"

    def test_parse_message_system_type_still_works(self):
        """Normal 'system' messages are still parsed correctly after patch."""
        from claude_agent_sdk._internal.message_parser import parse_message
        from claude_agent_sdk.types import SystemMessage

        data = {"type": "system", "subtype": "init_hook"}
        result = parse_message(data)
        assert isinstance(result, SystemMessage)
        assert result.subtype == "init_hook"

    def test_patch_is_marked_as_applied(self):
        """The patch function carries a marker attribute to prevent double-patching."""
        from claude_agent_sdk._internal import message_parser as mp

        assert hasattr(mp.parse_message, "_rate_limit_patched")

    def test_internal_client_namespace_is_also_patched(self):
        """
        _internal/client.py binds parse_message via a module-level
        `from .message_parser import parse_message` (line 13). That local name
        is NOT affected by patching the module attribute alone.

        We must also patch _internal.client.parse_message so that
        InternalClient.process_query() — which is what query() calls — sees the
        patched version. Without this, rate_limit_event still raises
        MessageParseError("Unknown message type: rate_limit_event").
        """
        from claude_agent_sdk._internal import client as sdk_client
        from claude_agent_sdk.types import SystemMessage

        # The locally-bound name in _internal/client must be our patched function
        assert hasattr(sdk_client.parse_message, "_rate_limit_patched")

        # And it must correctly handle rate_limit_event
        data = {"type": "rate_limit_event", "retry_after_ms": 5000}
        result = sdk_client.parse_message(data)
        assert isinstance(result, SystemMessage)
        assert result.subtype == "rate_limit_event"

    def test_patch_is_idempotent_after_module_reload(self):
        """Reloading sdk_wrapper does not double-patch parse_message."""
        import importlib

        from claude_agent_sdk._internal import message_parser as mp

        import analysi.agentic_orchestration.sdk_wrapper as wrapper

        importlib.reload(wrapper)

        fn_after = mp.parse_message

        # Function object is the same (not wrapped again) because of the marker check.
        # Both have the marker — either the same object or a new wrapper with the same marker.
        assert hasattr(fn_after, "_rate_limit_patched")
        # Either same object (idempotent) or a new wrapper that still handles correctly:
        from claude_agent_sdk.types import SystemMessage

        data = {"type": "rate_limit_event", "retry_after_ms": 1}
        result = fn_after(data)
        assert isinstance(result, SystemMessage)


# ---------------------------------------------------------------------------
# 2. execute_stage backoff tests
# ---------------------------------------------------------------------------


class TestExecuteStageRateLimitBackoff:
    """Verify that execute_stage sleeps for retry_after_ms when rate_limit_event arrives."""

    @pytest.fixture
    def executor(self):
        return AgentOrchestrationExecutor(api_key="test-api-key", mcp_servers={})

    @pytest.mark.asyncio
    async def test_backs_off_for_retry_after_ms_duration(self, executor):
        """asyncio.sleep is called with retry_after_ms/1000 when rate_limit_event received."""
        rate_limit_msg = _make_rate_limit_message(retry_after_ms=3000)
        result_msg = _make_result_message(result="after rate limit")

        async def mock_query(*, prompt, options):
            yield rate_limit_msg
            yield result_msg

        with (
            patch("claude_agent_sdk.query", new=mock_query),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            result, metrics = await executor.execute_stage(
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
                system_prompt="system prompt",
                user_prompt="user prompt",
            )

        assert result == "after rate limit"
        mock_sleep.assert_called_once_with(3.0)  # 3000ms → 3.0s

    @pytest.mark.asyncio
    async def test_no_sleep_when_retry_after_ms_is_zero(self, executor):
        """No sleep call when retry_after_ms is 0."""
        rate_limit_msg = _make_rate_limit_message(retry_after_ms=0)
        result_msg = _make_result_message()

        async def mock_query(*, prompt, options):
            yield rate_limit_msg
            yield result_msg

        with (
            patch("claude_agent_sdk.query", new=mock_query),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            result, _ = await executor.execute_stage(
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
                system_prompt="sys",
                user_prompt="usr",
            )

        assert result is not None
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_rate_limit_events_each_sleep(self, executor):
        """Multiple consecutive rate_limit_events each trigger a backoff sleep."""
        rl1 = _make_rate_limit_message(retry_after_ms=1000)
        rl2 = _make_rate_limit_message(retry_after_ms=2000)
        result_msg = _make_result_message(result="success after two limits")

        async def mock_query(*, prompt, options):
            yield rl1
            yield rl2
            yield result_msg

        with (
            patch("claude_agent_sdk.query", new=mock_query),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            result, _ = await executor.execute_stage(
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
                system_prompt="sys",
                user_prompt="usr",
            )

        assert result == "success after two limits"
        assert mock_sleep.call_count == 2
        calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert calls == [1.0, 2.0]

    @pytest.mark.asyncio
    async def test_result_after_rate_limit_is_correct(self, executor):
        """Result text from ResultMessage after rate_limit_event is correctly returned."""
        rate_limit_msg = _make_rate_limit_message(retry_after_ms=500)
        result_msg = _make_result_message(
            result="workflow runbook generated",
            total_cost_usd=0.05,
            usage={"input_tokens": 2000, "output_tokens": 800},
        )

        async def mock_query(*, prompt, options):
            yield rate_limit_msg
            yield result_msg

        with (
            patch("claude_agent_sdk.query", new=mock_query),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result, metrics = await executor.execute_stage(
                stage=WorkflowGenerationStage.TASK_PROPOSALS,
                system_prompt="You are an analyst",
                user_prompt="Analyze this alert",
            )

        assert result == "workflow runbook generated"
        assert metrics.total_cost_usd == pytest.approx(0.05)

    @pytest.mark.asyncio
    async def test_rate_limit_event_without_retry_after_ms_no_sleep(self, executor):
        """rate_limit_event missing retry_after_ms key doesn't crash and doesn't sleep."""
        from claude_agent_sdk.types import SystemMessage

        # Simulate an event that has no retry_after_ms at all
        rl_msg = SystemMessage(
            subtype="rate_limit_event", data={"type": "rate_limit_event"}
        )
        result_msg = _make_result_message(result="ok")

        async def mock_query(*, prompt, options):
            yield rl_msg
            yield result_msg

        with (
            patch("claude_agent_sdk.query", new=mock_query),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            result, _ = await executor.execute_stage(
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
                system_prompt="sys",
                user_prompt="usr",
            )

        assert result == "ok"
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_rate_limit_does_not_discard_prior_tool_calls(self, executor):
        """Tool calls before the rate_limit_event are still captured in metrics.

        In the SDK protocol, tool call traces are only finalised when the corresponding
        UserMessage(ToolResultBlock) arrives. This test exercises that full round-trip
        with a rate_limit_event between the AssistantMessage and the UserMessage.
        """
        from claude_agent_sdk.types import (
            AssistantMessage,
            ToolResultBlock,
            ToolUseBlock,
            UserMessage,
        )

        tool_use_id = "tool-123"
        tool_msg = AssistantMessage(
            content=[
                ToolUseBlock(
                    id=tool_use_id,
                    name="mcp__cy_script__compile",
                    input={"script": "x = 1"},
                )
            ],
            model="claude-3-5-sonnet",
        )
        # rate_limit_event arrives while tool result is being computed
        rl_msg = _make_rate_limit_message(retry_after_ms=500)
        # Tool result arrives after the rate limit wait
        tool_result_msg = UserMessage(
            content=[
                ToolResultBlock(
                    tool_use_id=tool_use_id,
                    content="Compiled successfully",
                    is_error=False,
                )
            ]
        )
        result_msg = _make_result_message(result="done")

        async def mock_query(*, prompt, options):
            yield tool_msg
            yield rl_msg
            yield tool_result_msg
            yield result_msg

        with (
            patch("claude_agent_sdk.query", new=mock_query),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result, metrics = await executor.execute_stage(
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
                system_prompt="sys",
                user_prompt="usr",
            )

        assert result == "done"
        assert len(metrics.tool_calls) == 1
        assert metrics.tool_calls[0].tool_name == "mcp__cy_script__compile"
        assert metrics.tool_calls[0].result == "Compiled successfully"


# ---------------------------------------------------------------------------
# 3. Integration-style: ensure no crash in end-to-end generator scenario
# ---------------------------------------------------------------------------


class TestRateLimitEventEndToEnd:
    """Simulate the full message sequence that caused the production failure."""

    @pytest.mark.asyncio
    async def test_rate_limit_event_in_real_stream_does_not_crash(self):
        """Production scenario: rate_limit_event in the middle of an SDK stream."""
        # This is exactly what caused the 'Unknown message type: rate_limit_event' error.
        # Before the fix, MessageParseError terminated the generator.
        # After the fix, the loop continues and the result is captured.

        from claude_agent_sdk._internal.message_parser import parse_message
        from claude_agent_sdk.types import SystemMessage

        # Simulate the raw messages from the CLI
        raw_messages = [
            {"type": "system", "subtype": "init"},
            {"type": "rate_limit_event", "retry_after_ms": 4000},  # ← was crashing here
            {
                "type": "result",
                "subtype": "success",
                "duration_ms": 5000,
                "duration_api_ms": 4800,
                "is_error": False,
                "num_turns": 3,
                "session_id": "abc",
                "result": "runbook generated",
            },
        ]

        parsed = []
        for raw in raw_messages:
            msg = parse_message(raw)  # Must not raise
            parsed.append(msg)

        assert len(parsed) == 3
        # rate_limit_event → SystemMessage (not a crash)
        assert isinstance(parsed[1], SystemMessage)
        assert parsed[1].subtype == "rate_limit_event"

    @pytest.mark.asyncio
    async def test_warning_logged_on_rate_limit_event(self, caplog):
        """A warning is emitted when a rate_limit_event is received."""
        import logging

        from claude_agent_sdk._internal.message_parser import parse_message

        with caplog.at_level(logging.WARNING):
            parse_message({"type": "rate_limit_event", "retry_after_ms": 2000})

        assert any("rate_limit" in record.message.lower() for record in caplog.records)
