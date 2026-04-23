"""
Integration tests for rate_limit_event handling.

Production failure: Claude Code sends rate_limit_event JSON messages when the
Anthropic API rate-limits it. The SDK's _internal/client.py calls parse_message()
via a module-level binding:

    # claude_agent_sdk/_internal/client.py, line 13
    from .message_parser import parse_message   # <-- local binding

    # line 141 (in process_query)
    yield parse_message(data)   # <-- calls the local name, NOT the module attribute

Our fix patches BOTH:
  1. message_parser.parse_message       (module attribute, for future `from ... import` calls)
  2. _internal/client.parse_message     (the local name that InternalClient actually calls)

Without patching both, the rate_limit_event still crashes with:
    MessageParseError("Unknown message type: rate_limit_event")

These integration tests verify the complete fix, including the exact call path.
"""

from unittest.mock import AsyncMock, patch

import pytest

from analysi.agentic_orchestration.observability import WorkflowGenerationStage
from analysi.agentic_orchestration.sdk_wrapper import AgentOrchestrationExecutor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result_message(**overrides):
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


def _make_system_message(subtype: str = "init", data: dict | None = None):
    from claude_agent_sdk.types import SystemMessage

    return SystemMessage(subtype=subtype, data=data or {})


@pytest.fixture
def executor():
    return AgentOrchestrationExecutor(api_key="test-api-key", mcp_servers={})


# ---------------------------------------------------------------------------
# 1. Patch correctness — both namespaces must be patched
# ---------------------------------------------------------------------------


class TestPatchIsAppliedToCorrectNamespaces:
    """
    The patch must be applied to _internal/client.parse_message, NOT just
    message_parser.parse_message.

    InternalClient.process_query() (called by query()) uses a module-level
    local binding created at import time. Patching only the module attribute
    has no effect on that local binding.
    """

    def test_message_parser_module_attribute_is_patched(self):
        """message_parser.parse_message (module attribute) is patched."""
        from claude_agent_sdk._internal import message_parser as mp

        assert hasattr(mp.parse_message, "_rate_limit_patched"), (
            "message_parser.parse_message must have _rate_limit_patched marker"
        )

    def test_internal_client_local_binding_is_patched(self):
        """
        _internal/client.parse_message (the local binding used by InternalClient)
        is patched. This is the critical one — without it the fix does nothing.
        """
        from claude_agent_sdk._internal import client as sdk_client

        assert hasattr(sdk_client.parse_message, "_rate_limit_patched"), (
            "_internal/client.parse_message must be patched. "
            "InternalClient.process_query() calls this local binding at line 141."
        )

    def test_both_bindings_are_the_same_patched_function(self):
        """Both patched names must point to the same function object."""
        from claude_agent_sdk._internal import client as sdk_client
        from claude_agent_sdk._internal import message_parser as mp

        assert mp.parse_message is sdk_client.parse_message, (
            "Both bindings must point to the same patched function"
        )

    def test_internal_client_binding_converts_rate_limit_event(self):
        """
        Calling _internal/client.parse_message with rate_limit_event data
        returns SystemMessage, not raises MessageParseError.

        This is the exact call that was crashing in production.
        """
        from claude_agent_sdk._internal import client as sdk_client
        from claude_agent_sdk.types import SystemMessage

        data = {"type": "rate_limit_event", "retry_after_ms": 5000}
        result = sdk_client.parse_message(data)

        assert isinstance(result, SystemMessage)
        assert result.subtype == "rate_limit_event"
        assert result.data == data

    def test_internal_client_binding_passes_normal_messages_through(self):
        """Normal messages still work through the patched _internal/client binding."""
        from claude_agent_sdk._internal import client as sdk_client
        from claude_agent_sdk.types import ResultMessage, SystemMessage

        # system message
        result = sdk_client.parse_message({"type": "system", "subtype": "init"})
        assert isinstance(result, SystemMessage)
        assert result.subtype == "init"

        # result message
        result = sdk_client.parse_message(
            {
                "type": "result",
                "subtype": "success",
                "duration_ms": 100,
                "duration_api_ms": 80,
                "is_error": False,
                "num_turns": 1,
                "session_id": "abc",
            }
        )
        assert isinstance(result, ResultMessage)

    def test_patch_survives_reimport_of_message_parser(self):
        """
        Importing parse_message from message_parser after the patch is applied
        still returns the patched version via the module attribute.
        """
        from claude_agent_sdk._internal.message_parser import parse_message
        from claude_agent_sdk.types import SystemMessage

        data = {"type": "rate_limit_event", "retry_after_ms": 1000}
        result = parse_message(data)
        assert isinstance(result, SystemMessage)

    def test_patch_marker_prevents_double_wrapping(self):
        """
        Importing sdk_wrapper a second time does not wrap parse_message again.
        The _rate_limit_patched marker prevents double-patching.
        """
        import importlib

        from claude_agent_sdk._internal import client as sdk_client
        from claude_agent_sdk._internal import message_parser as mp

        import analysi.agentic_orchestration.sdk_wrapper as wrapper

        fn_before_mp = mp.parse_message
        fn_before_client = sdk_client.parse_message

        importlib.reload(wrapper)

        # After reload, the marker is seen and the patch is skipped
        assert mp.parse_message is fn_before_mp
        assert sdk_client.parse_message is fn_before_client


# ---------------------------------------------------------------------------
# 2. InternalClient call path simulation
# ---------------------------------------------------------------------------


class TestInternalClientCallPath:
    """
    Simulate the actual call path: query() → InternalClient → process_query()
    → parse_message(raw_data) at line 141.

    We mock InternalClient.process_query to yield raw dicts (as the transport
    would), then call parse_message on them — exactly as the real code does.
    """

    @pytest.mark.asyncio
    async def test_rate_limit_event_does_not_crash_when_parsed_by_client_binding(self):
        """
        The exact call that was crashing: _internal/client.parse_message called
        with rate_limit_event raw data returns SystemMessage, not raises.
        """
        from claude_agent_sdk._internal import client as sdk_client
        from claude_agent_sdk.types import SystemMessage

        # This is the data the transport sends; parse_message is called per message
        raw_messages = [
            {"type": "system", "subtype": "init"},
            {"type": "rate_limit_event", "retry_after_ms": 4000},
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
            msg = sdk_client.parse_message(raw)  # Must not raise
            parsed.append(msg)

        assert len(parsed) == 3
        assert isinstance(parsed[1], SystemMessage)
        assert parsed[1].subtype == "rate_limit_event"
        assert parsed[1].data["retry_after_ms"] == 4000

    @pytest.mark.asyncio
    async def test_rate_limit_event_without_retry_after_ms_does_not_crash(self):
        """Malformed rate_limit_event (no retry_after_ms) is handled gracefully."""
        from claude_agent_sdk._internal import client as sdk_client
        from claude_agent_sdk.types import SystemMessage

        result = sdk_client.parse_message({"type": "rate_limit_event"})
        assert isinstance(result, SystemMessage)
        assert result.subtype == "rate_limit_event"

    @pytest.mark.asyncio
    async def test_multiple_rate_limit_events_all_parsed_correctly(self):
        """Multiple consecutive rate_limit_events are all parsed as SystemMessage."""
        from claude_agent_sdk._internal import client as sdk_client
        from claude_agent_sdk.types import SystemMessage

        events = [
            {"type": "rate_limit_event", "retry_after_ms": 1000},
            {"type": "rate_limit_event", "retry_after_ms": 2000},
            {"type": "rate_limit_event", "retry_after_ms": 5000},
        ]

        for raw in events:
            result = sdk_client.parse_message(raw)
            assert isinstance(result, SystemMessage)
            assert result.subtype == "rate_limit_event"
            assert result.data["retry_after_ms"] == raw["retry_after_ms"]

    def test_warning_logged_when_parsing_rate_limit_event(self, caplog):
        """A WARNING is emitted each time a rate_limit_event is parsed."""
        import logging

        from claude_agent_sdk._internal import client as sdk_client

        with caplog.at_level(logging.WARNING):
            sdk_client.parse_message(
                {"type": "rate_limit_event", "retry_after_ms": 3000}
            )

        assert any("rate_limit" in r.message.lower() for r in caplog.records), (
            f"Expected rate limit warning. Got: {[r.message for r in caplog.records]}"
        )


# ---------------------------------------------------------------------------
# 3. execute_stage backoff behaviour
# ---------------------------------------------------------------------------


class TestExecuteStageBackoff:
    """
    execute_stage must sleep for retry_after_ms/1000 seconds when it receives
    a SystemMessage(rate_limit_event), so the ARQ job respects the server's
    requested backoff before the SDK retries.
    """

    @pytest.mark.asyncio
    async def test_sleeps_for_retry_after_ms(self, executor):
        """asyncio.sleep is called with retry_after_ms/1000 seconds."""
        from claude_agent_sdk.types import SystemMessage

        rl_msg = SystemMessage(
            subtype="rate_limit_event",
            data={"type": "rate_limit_event", "retry_after_ms": 6000},
        )
        result_msg = _make_result_message(result="done after backoff")

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

        assert result == "done after backoff"
        mock_sleep.assert_called_once_with(6.0)

    @pytest.mark.asyncio
    async def test_no_sleep_for_zero_retry_after_ms(self, executor):
        """retry_after_ms=0 means no sleep."""
        from claude_agent_sdk.types import SystemMessage

        rl_msg = SystemMessage(
            subtype="rate_limit_event",
            data={"type": "rate_limit_event", "retry_after_ms": 0},
        )

        async def mock_query(*, prompt, options):
            yield rl_msg
            yield _make_result_message()

        with (
            patch("claude_agent_sdk.query", new=mock_query),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await executor.execute_stage(
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
                system_prompt="sys",
                user_prompt="usr",
            )

        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_sleep_when_retry_after_ms_absent(self, executor):
        """Missing retry_after_ms field defaults to 0 — no sleep."""
        from claude_agent_sdk.types import SystemMessage

        rl_msg = SystemMessage(
            subtype="rate_limit_event",
            data={"type": "rate_limit_event"},  # no retry_after_ms
        )

        async def mock_query(*, prompt, options):
            yield rl_msg
            yield _make_result_message()

        with (
            patch("claude_agent_sdk.query", new=mock_query),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await executor.execute_stage(
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
                system_prompt="sys",
                user_prompt="usr",
            )

        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_rate_limits_each_get_own_sleep(self, executor):
        """Each rate_limit_event triggers its own sleep call with the right duration."""
        from claude_agent_sdk.types import SystemMessage

        def rl(ms: int):
            return SystemMessage(
                subtype="rate_limit_event",
                data={"type": "rate_limit_event", "retry_after_ms": ms},
            )

        async def mock_query(*, prompt, options):
            yield rl(1000)
            yield rl(3000)
            yield rl(500)
            yield _make_result_message(result="ok")

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
        assert mock_sleep.call_count == 3
        sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_args == [1.0, 3.0, 0.5]

    @pytest.mark.asyncio
    async def test_tool_calls_before_rate_limit_are_preserved(self, executor):
        """
        Tool call traces captured before a rate_limit_event are not lost.
        The rate limit event must not reset or corrupt the in-flight tool tracking.
        """
        from claude_agent_sdk.types import (
            AssistantMessage,
            SystemMessage,
            ToolResultBlock,
            ToolUseBlock,
            UserMessage,
        )

        tool_id = "tid-001"

        async def mock_query(*, prompt, options):
            # 1. Agent calls a tool
            yield AssistantMessage(
                content=[ToolUseBlock(id=tool_id, name="mcp__compile", input={"x": 1})],
                model="claude-3-5-sonnet",
            )
            # 2. Rate limit hits while tool result is being computed
            yield SystemMessage(
                subtype="rate_limit_event",
                data={"type": "rate_limit_event", "retry_after_ms": 500},
            )
            # 3. Tool result arrives after backoff
            yield UserMessage(
                content=[
                    ToolResultBlock(
                        tool_use_id=tool_id,
                        content="ok",
                        is_error=False,
                    )
                ]
            )
            yield _make_result_message(result="final")

        with (
            patch("claude_agent_sdk.query", new=mock_query),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result, metrics = await executor.execute_stage(
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
                system_prompt="sys",
                user_prompt="usr",
            )

        assert result == "final"
        assert len(metrics.tool_calls) == 1
        assert metrics.tool_calls[0].tool_name == "mcp__compile"
        assert metrics.tool_calls[0].result == "ok"
        assert not metrics.tool_calls[0].is_error

    @pytest.mark.asyncio
    async def test_metrics_cost_correct_after_rate_limit(self, executor):
        """Cost and usage metrics from the ResultMessage are correct even after backoff."""
        from claude_agent_sdk.types import SystemMessage

        rl = SystemMessage(
            subtype="rate_limit_event",
            data={"type": "rate_limit_event", "retry_after_ms": 2000},
        )
        result_msg = _make_result_message(
            result="runbook text",
            total_cost_usd=0.123,
            usage={"input_tokens": 5000, "output_tokens": 2000},
        )

        async def mock_query(*, prompt, options):
            yield rl
            yield result_msg

        with (
            patch("claude_agent_sdk.query", new=mock_query),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result, metrics = await executor.execute_stage(
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
                system_prompt="You are an expert analyst",
                user_prompt="Analyze this alert",
            )

        assert result == "runbook text"
        assert metrics.total_cost_usd == pytest.approx(0.123)
        assert metrics.usage["input_tokens"] == 5000
        assert metrics.usage["output_tokens"] == 2000

    @pytest.mark.asyncio
    async def test_rate_limit_warning_logged_in_execute_stage(self, executor, caplog):
        """A WARNING is logged by execute_stage when it handles a rate_limit_event."""
        import logging

        from claude_agent_sdk.types import SystemMessage

        rl = SystemMessage(
            subtype="rate_limit_event",
            data={"type": "rate_limit_event", "retry_after_ms": 3000},
        )

        async def mock_query(*, prompt, options):
            yield rl
            yield _make_result_message()

        with (
            caplog.at_level(logging.WARNING),
            patch("claude_agent_sdk.query", new=mock_query),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await executor.execute_stage(
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
                system_prompt="sys",
                user_prompt="usr",
            )

        assert any(
            "rate_limit" in r.message.lower() and "3.0" in r.message
            for r in caplog.records
        ), (
            f"Expected backoff warning with 3.0s. Got: {[r.message for r in caplog.records]}"
        )

    @pytest.mark.asyncio
    async def test_non_rate_limit_system_messages_are_ignored(self, executor):
        """Non-rate-limit SystemMessages (e.g., init) pass through without sleeping."""
        from claude_agent_sdk.types import SystemMessage

        async def mock_query(*, prompt, options):
            yield SystemMessage(subtype="init", data={})
            yield SystemMessage(subtype="some_other_event", data={})
            yield _make_result_message(result="done")

        with (
            patch("claude_agent_sdk.query", new=mock_query),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            result, _ = await executor.execute_stage(
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
                system_prompt="sys",
                user_prompt="usr",
            )

        assert result == "done"
        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# 4. End-to-end production scenario
# ---------------------------------------------------------------------------


class TestProductionScenario:
    """
    Reproduce the exact sequence that caused the production failure:
    workflow generation stream containing a rate_limit_event in the middle.
    """

    @pytest.mark.asyncio
    async def test_full_stream_with_rate_limit_does_not_crash(self, executor):
        """
        Before the fix: stream terminates at rate_limit_event with
        MessageParseError("Unknown message type: rate_limit_event").

        After the fix: stream continues, result is captured correctly.
        """
        from claude_agent_sdk.types import SystemMessage

        async def mock_query(*, prompt, options):
            yield _make_system_message("init")
            yield SystemMessage(
                subtype="rate_limit_event",
                data={"type": "rate_limit_event", "retry_after_ms": 1000},
            )
            yield _make_result_message(result="workflow runbook generated successfully")

        with (
            patch("claude_agent_sdk.query", new=mock_query),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result, metrics = await executor.execute_stage(
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
                system_prompt="Expert security analyst",
                user_prompt="Analyze this alert and generate runbook",
            )

        # Must not raise — and must return the result after the rate limit
        assert result == "workflow runbook generated successfully"
        assert metrics.total_cost_usd == pytest.approx(0.001)

    @pytest.mark.asyncio
    async def test_rate_limit_at_start_of_stream(self, executor):
        """rate_limit_event as the very first message (before any tool calls)."""
        from claude_agent_sdk.types import SystemMessage

        async def mock_query(*, prompt, options):
            yield SystemMessage(
                subtype="rate_limit_event",
                data={"type": "rate_limit_event", "retry_after_ms": 500},
            )
            yield _make_result_message(result="immediate result")

        with (
            patch("claude_agent_sdk.query", new=mock_query),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            result, _ = await executor.execute_stage(
                stage=WorkflowGenerationStage.TASK_PROPOSALS,
                system_prompt="sys",
                user_prompt="usr",
            )

        assert result == "immediate result"
        mock_sleep.assert_called_once_with(0.5)

    @pytest.mark.asyncio
    async def test_rate_limit_between_tool_calls(self, executor):
        """
        Rate limit arrives between two separate tool calls — both tool call
        traces are correctly captured in metrics.
        """
        from claude_agent_sdk.types import (
            AssistantMessage,
            SystemMessage,
            ToolResultBlock,
            ToolUseBlock,
            UserMessage,
        )

        async def mock_query(*, prompt, options):
            # First tool call
            yield AssistantMessage(
                content=[
                    ToolUseBlock(id="t1", name="mcp__search", input={"q": "alert"})
                ],
                model="claude-sonnet",
            )
            yield UserMessage(
                content=[
                    ToolResultBlock(tool_use_id="t1", content="results", is_error=False)
                ]
            )

            # Rate limit hits between tool calls
            yield SystemMessage(
                subtype="rate_limit_event",
                data={"type": "rate_limit_event", "retry_after_ms": 2000},
            )

            # Second tool call after backoff
            yield AssistantMessage(
                content=[
                    ToolUseBlock(
                        id="t2", name="mcp__analyze", input={"data": "results"}
                    )
                ],
                model="claude-sonnet",
            )
            yield UserMessage(
                content=[
                    ToolResultBlock(
                        tool_use_id="t2", content="analysis done", is_error=False
                    )
                ]
            )

            yield _make_result_message(result="complete")

        with (
            patch("claude_agent_sdk.query", new=mock_query),
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            result, metrics = await executor.execute_stage(
                stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
                system_prompt="sys",
                user_prompt="usr",
            )

        assert result == "complete"
        assert mock_sleep.call_count == 1
        assert mock_sleep.call_args.args[0] == pytest.approx(2.0)
        assert len(metrics.tool_calls) == 2
        tool_names = {tc.tool_name for tc in metrics.tool_calls}
        assert tool_names == {"mcp__search", "mcp__analyze"}
