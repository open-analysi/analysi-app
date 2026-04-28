"""Unit tests for ``analysi.services.chat_action_tools``.

This module is the chat agent's "two-phase confirmation" backbone:
``PendingAction`` (the staged-action dataclass), ``check_confirmation``
(the matcher), ``build_confirmation_message`` (the LLM-facing string),
and the four ``*_impl`` functions that finally execute mutating
operations once a user confirms.

Combined unit + integration coverage was 43 % — the existing
``test_chat_tool_registry`` exercises the wrappers (and inadvertently
hits some of these helpers) but the impl functions and the
``PendingAction`` round-trip semantics are not directly tested anywhere.

We mock at the service-layer boundary so we never touch a real DB.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.services.chat_action_tools import (
    PendingAction,
    analyze_alert_impl,
    build_confirmation_message,
    check_confirmation,
    create_alert_impl,
    run_task_impl,
    run_workflow_impl,
)


# ── PendingAction round-trip ────────────────────────────────────────────────


def test_pending_action_to_dict_round_trip() -> None:
    pa = PendingAction(
        tool_name="run_workflow",
        description="run x",
        kwargs={"workflow_id": "wf-1", "input_data": {"a": 1}},
    )
    d = pa.to_dict()
    pa2 = PendingAction.from_dict(d)
    assert pa2 == pa


def test_pending_action_from_dict_missing_key_raises() -> None:
    """Documenting current behaviour: ``from_dict`` is not defensive — it
    raises KeyError on incomplete data. Callers (chat_service) currently
    swallow this; if that ever changes, this test will catch the contract
    drift."""
    with pytest.raises(KeyError):
        PendingAction.from_dict({"tool_name": "x", "description": "y"})


def test_pending_action_to_dict_after_json_round_trip() -> None:
    """The pending action survives JSON serialization (it's stored in
    conversation.metadata as JSON in Postgres)."""
    pa = PendingAction(
        tool_name="run_workflow",
        description="d",
        kwargs={"workflow_id": "wf-1", "input_data": '{"a":1}'},
    )
    serialized = json.dumps(pa.to_dict())
    pa2 = PendingAction.from_dict(json.loads(serialized))
    assert pa2 == pa


# ── check_confirmation ──────────────────────────────────────────────────────


def test_check_confirmation_no_pending_returns_false() -> None:
    assert check_confirmation(None, "run_workflow", {}) is False


def test_check_confirmation_matching_returns_true() -> None:
    pending = PendingAction(
        tool_name="run_workflow",
        description="d",
        kwargs={"workflow_id": "wf-1"},
    )
    assert check_confirmation(pending, "run_workflow", {"workflow_id": "wf-1"}) is True


def test_check_confirmation_different_tool_name_returns_false() -> None:
    pending = PendingAction(
        tool_name="run_workflow",
        description="d",
        kwargs={"workflow_id": "wf-1"},
    )
    assert check_confirmation(pending, "run_task", {"workflow_id": "wf-1"}) is False


def test_check_confirmation_different_kwargs_returns_false() -> None:
    pending = PendingAction(
        tool_name="run_workflow",
        description="d",
        kwargs={"workflow_id": "wf-1"},
    )
    assert (
        check_confirmation(pending, "run_workflow", {"workflow_id": "wf-2"}) is False
    )


def test_check_confirmation_extra_kwarg_returns_false() -> None:
    """User must replay with EXACT same args — extra kwargs invalidate."""
    pending = PendingAction(
        tool_name="run_workflow",
        description="d",
        kwargs={"workflow_id": "wf-1"},
    )
    assert (
        check_confirmation(
            pending, "run_workflow", {"workflow_id": "wf-1", "extra": "x"}
        )
        is False
    )


# ── build_confirmation_message ─────────────────────────────────────────────-


def test_build_confirmation_message_includes_description() -> None:
    msg = build_confirmation_message("execute workflow X")
    assert "execute workflow X" in msg
    assert "Action requires confirmation" in msg
    assert "call this tool again with the same arguments" in msg.lower()


# ── run_workflow_impl ──────────────────────────────────────────────────────-


@pytest.mark.asyncio
async def test_run_workflow_impl_invalid_uuid_returns_error_string() -> None:
    out = await run_workflow_impl(MagicMock(), "t", "not-a-uuid", {})
    assert "Invalid workflow ID format" in out


@pytest.mark.asyncio
async def test_run_workflow_impl_unknown_workflow_returns_not_found() -> None:
    fake_session = MagicMock()
    fake_session.flush = AsyncMock()
    workflow_id = str(uuid4())
    with patch(
        "analysi.services.workflow.WorkflowService"
    ) as wf_service_cls:
        wf_service = wf_service_cls.return_value
        wf_service.get_workflow = AsyncMock(return_value=None)
        out = await run_workflow_impl(fake_session, "t", workflow_id, {})
    assert "not found" in out


@pytest.mark.asyncio
async def test_run_workflow_impl_happy_path_returns_run_id() -> None:
    fake_session = MagicMock()
    fake_session.flush = AsyncMock()
    workflow_id = str(uuid4())

    workflow = MagicMock()
    workflow.name = "Test Workflow"

    with (
        patch("analysi.services.workflow.WorkflowService") as wf_cls,
        patch(
            "analysi.services.workflow_execution.WorkflowExecutor"
        ) as exec_cls,
    ):
        wf_cls.return_value.get_workflow = AsyncMock(return_value=workflow)
        run_id = uuid4()
        exec_cls.return_value.execute_workflow = AsyncMock(return_value=run_id)
        out = await run_workflow_impl(
            fake_session, "t", workflow_id, {"alert_id": "a-1"}
        )
    assert "Test Workflow" in out
    assert str(run_id) in out
    assert "running" in out.lower()


# ── run_task_impl ──────────────────────────────────────────────────────────-


@pytest.mark.asyncio
async def test_run_task_impl_unknown_task_returns_not_found() -> None:
    fake_session = MagicMock()
    fake_session.flush = AsyncMock()
    with patch("analysi.services.task.TaskService") as task_cls:
        # UUID-shaped ID — get_task path
        task_cls.return_value.get_task = AsyncMock(return_value=None)
        task_cls.return_value.get_task_by_cy_name = AsyncMock(return_value=None)
        out = await run_task_impl(fake_session, "t", str(uuid4()), {})
    assert "not found" in out


@pytest.mark.asyncio
async def test_run_task_impl_falls_back_to_cy_name() -> None:
    """A non-UUID identifier triggers the cy_name path."""
    fake_session = MagicMock()
    fake_session.flush = AsyncMock()
    task = MagicMock()
    task.component.name = "My Task"
    task_run = MagicMock(id=uuid4(), status="running")
    with (
        patch("analysi.services.task.TaskService") as task_cls,
        patch(
            "analysi.services.task_execution.DefaultTaskExecutor"
        ) as exec_cls,
    ):
        ts = task_cls.return_value
        ts.get_task = AsyncMock()
        ts.get_task_by_cy_name = AsyncMock(return_value=task)
        exec_cls.return_value.create_and_execute = AsyncMock(return_value=task_run)
        out = await run_task_impl(fake_session, "t", "my_task", {})
    # cy_name path was taken (no UUID parse)
    ts.get_task.assert_not_called()
    ts.get_task_by_cy_name.assert_awaited_once()
    assert "My Task" in out


# ── analyze_alert_impl ─────────────────────────────────────────────────────-


@pytest.mark.asyncio
async def test_analyze_alert_impl_invalid_uuid() -> None:
    out = await analyze_alert_impl(MagicMock(), "t", "not-a-uuid")
    assert "Invalid alert ID format" in out


@pytest.mark.asyncio
async def test_analyze_alert_impl_unknown_alert_returns_not_found() -> None:
    fake_session = MagicMock()
    fake_session.flush = AsyncMock()
    alert_id = str(uuid4())
    with patch("analysi.services.chat_tools._make_alert_service") as factory:
        svc = factory.return_value
        svc.get_alert = AsyncMock(return_value=None)
        out = await analyze_alert_impl(fake_session, "t", alert_id)
    assert "not found" in out


@pytest.mark.asyncio
async def test_analyze_alert_impl_dispatches_control_event() -> None:
    fake_session = MagicMock()
    fake_session.flush = AsyncMock()
    alert_id = str(uuid4())
    alert = MagicMock(title="Suspicious Login")
    with (
        patch("analysi.services.chat_tools._make_alert_service") as factory,
        patch(
            "analysi.repositories.control_event_repository.ControlEventRepository"
        ) as repo_cls,
    ):
        factory.return_value.get_alert = AsyncMock(return_value=alert)
        repo = repo_cls.return_value
        repo.insert = AsyncMock()
        out = await analyze_alert_impl(fake_session, "t", alert_id)

    repo.insert.assert_awaited_once()
    call_kwargs = repo.insert.await_args.kwargs
    assert call_kwargs["channel"] == "alert:analyze"
    assert call_kwargs["payload"] == {"alert_id": alert_id}
    assert "Suspicious Login" in out


# ── create_alert_impl — bug-hunt territory ─────────────────────────────────-
#
# The current implementation builds raw_data via an f-string:
#
#     raw_data=f'{{"title": "{title}", "severity": "{severity}", "source": "chatbot"}}'
#
# That is *string formatting*, not JSON encoding — so any double-quote,
# backslash, newline, or control character in ``title`` breaks the JSON.
# Bug ticket: this PR's first regression test below pinpoints it.


@pytest.mark.asyncio
async def test_create_alert_impl_happy_path_returns_id() -> None:
    fake_session = MagicMock()
    fake_session.flush = AsyncMock()
    alert = MagicMock(alert_id="ALR-001")
    with patch("analysi.services.chat_tools._make_alert_service") as factory:
        factory.return_value.create_alert = AsyncMock(return_value=alert)
        out = await create_alert_impl(
            fake_session, "t", title="A simple alert", severity="medium"
        )
    assert "ALR-001" in out


@pytest.mark.asyncio
async def test_create_alert_impl_raw_data_is_valid_json_for_simple_title() -> None:
    """Sanity baseline: a plain title round-trips through json.loads."""
    captured: dict = {}

    async def capture_create(_tenant, create_data):
        captured["raw_data"] = create_data.raw_data
        return MagicMock(alert_id="ALR-2")

    fake_session = MagicMock()
    fake_session.flush = AsyncMock()
    with patch("analysi.services.chat_tools._make_alert_service") as factory:
        factory.return_value.create_alert = AsyncMock(side_effect=capture_create)
        await create_alert_impl(fake_session, "t", title="Plain title")
    # Must be valid JSON.
    json.loads(captured["raw_data"])  # raises if broken


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "title",
    [
        'Title with "double quotes"',
        "Title with backslash \\path\\to\\thing",
        "Title with newline\nin it",
        "Title with carriage return\rmidway",
        "Title with tab\there",
        "Title with unicode escape \\u0041",
        # A title that itself looks like JSON — currently produces broken
        # nested JSON in the raw_data field.
        '{"injection": "hi"}',
    ],
)
async def test_create_alert_impl_raw_data_must_be_valid_json_for_any_title(
    title: str,
) -> None:
    """Regression test for raw_data construction.

    ``raw_data`` must be valid JSON: alert_service hashes it for
    deduplication, and downstream OCSF normalizers / exports parse it.
    Building it via ``f'{{"title": "{title}"}}'`` silently produces
    invalid JSON whenever the title contains a JSON-special character.
    Bug fix: use ``json.dumps`` instead.
    """
    captured: dict = {}

    async def capture_create(_tenant, create_data):
        captured["raw_data"] = create_data.raw_data
        return MagicMock(alert_id="ALR-3")

    fake_session = MagicMock()
    fake_session.flush = AsyncMock()
    with patch("analysi.services.chat_tools._make_alert_service") as factory:
        factory.return_value.create_alert = AsyncMock(side_effect=capture_create)
        await create_alert_impl(
            fake_session, "t", title=title, severity="medium"
        )

    # The whole point: raw_data must round-trip through the JSON parser.
    parsed = json.loads(captured["raw_data"])
    # And the title we put in is the title that comes out (i.e. no
    # accidental escaping/truncation).
    assert parsed["title"] == title
