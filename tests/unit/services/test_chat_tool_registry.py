"""Unit tests for ``analysi.services.chat_tool_registry``.

This module wires 22 Pydantic-AI tools that the chat agent calls during
LLM-driven conversations. Integration tests stub the LLM agent, so none
of these wrappers are ever exercised end-to-end. Previous coverage:
**24 % across both unit and integration suites**.

Each wrapper does a small amount of work:

  1. ``_check_tool_call_limit`` cap (returns a polite "limit reached"
     string when a per-turn budget is exhausted).
  2. Optional permission check for action tools (returns a permission
     error when the user's role can't perform the action).
  3. Optional confirmation gate for action tools (two-phase: first call
     stages a ``PendingAction``; second call with matching args replays).
  4. Forwards to a service-layer ``*_impl`` function that does the real
     work.

We mock the underlying ``*_impl`` functions and the chat-skill loader at
the module boundary, then test (a) the happy path, (b) the rate-limit
boundary, (c) the permission/confirmation rejection paths, and (d) the
error / arg-parsing paths.

Coverage target: ≥ 95 % for ``chat_tool_registry.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from analysi.constants import ChatConstants
from analysi.services import chat_tool_registry as ctr
from analysi.services.chat_action_tools import PendingAction

# ── A minimal RunContext / ChatDeps stand-in ───────────────────────────────-
#
# The real Pydantic-AI ``RunContext`` is heavy; the tools only ever access
# ``ctx.deps``, so we wrap our deps in a tiny stub.


@dataclass
class _StubDeps:
    """Mirror of ``ChatDeps`` — only the fields the tools touch."""

    tenant_id: str = "tenant-x"
    user_roles: list[str] = field(default_factory=lambda: ["analyst"])
    user_id: object = field(default_factory=uuid4)
    conversation_id: object = field(default_factory=uuid4)
    session: object = "session-stub"  # not introspected by the tools
    page_context: dict[str, Any] | None = None
    pinned_skills: list[str] = field(default_factory=list)
    tool_call_count: int = 0
    skill_load_count: int = 0
    pending_action: PendingAction | None = None


@dataclass
class _StubCtx:
    deps: _StubDeps


@pytest.fixture
def deps() -> _StubDeps:
    return _StubDeps()


@pytest.fixture
def ctx(deps: _StubDeps) -> _StubCtx:
    return _StubCtx(deps=deps)


# ── _check_tool_call_limit (the helper most wrappers call) ─────────────────-


def test_check_tool_call_limit_increments_counter(deps: _StubDeps) -> None:
    """Each non-exempt tool call increments the counter and returns None."""
    assert deps.tool_call_count == 0
    assert ctr._check_tool_call_limit(deps) is None
    assert deps.tool_call_count == 1


def test_check_tool_call_limit_at_cap_returns_message(deps: _StubDeps) -> None:
    deps.tool_call_count = ChatConstants.MAX_TOOL_CALLS_PER_TURN
    msg = ctr._check_tool_call_limit(deps)
    assert msg is not None
    assert "Tool call limit reached" in msg
    # Counter NOT incremented when at the cap.
    assert deps.tool_call_count == ChatConstants.MAX_TOOL_CALLS_PER_TURN


# ── _load_product_skill (skill tool, exempt from cap, has own cap) ─────────-


@pytest.mark.asyncio
async def test_load_product_skill_happy(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    monkeypatch.setattr(
        ctr, "load_skill_content", lambda name: f"# Skill: {name}\nbody"
    )
    monkeypatch.setattr(
        ctr, "update_pinned_skills", lambda current, new: [*current, new]
    )

    result = await ctr._load_product_skill(ctx, "alerts")  # type: ignore[arg-type]

    assert "alerts" in result
    assert ctx.deps.skill_load_count == 1
    assert ctx.deps.pinned_skills == ["alerts"]


@pytest.mark.asyncio
async def test_load_product_skill_at_cap_returns_message(
    ctx: _StubCtx,
) -> None:
    ctx.deps.skill_load_count = ChatConstants.MAX_PINNED_SKILLS
    result = await ctr._load_product_skill(ctx, "alerts")  # type: ignore[arg-type]
    assert "Skill load limit reached" in result
    # Counter not incremented past the cap.
    assert ctx.deps.skill_load_count == ChatConstants.MAX_PINNED_SKILLS


@pytest.mark.asyncio
async def test_load_product_skill_unknown_skill_returns_value_error(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    """Unknown skill name surfaces the underlying ValueError text to the LLM."""
    def boom(name: str) -> str:
        raise ValueError(f"Unknown skill: {name}")

    monkeypatch.setattr(ctr, "load_skill_content", boom)
    result = await ctr._load_product_skill(ctx, "bogus")  # type: ignore[arg-type]
    assert "Unknown skill" in result
    # Counter incremented (we tried), but pinned list unchanged.
    assert ctx.deps.skill_load_count == 1
    assert ctx.deps.pinned_skills == []


# ── Knowledge tools ────────────────────────────────────────────────────────-


@pytest.mark.asyncio
async def test_search_tenant_knowledge_forwards(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    mock = AsyncMock(return_value="result")
    monkeypatch.setattr(ctr, "search_knowledge", mock)
    out = await ctr._search_tenant_knowledge(ctx, query="ip", ku_type="document")  # type: ignore[arg-type]
    assert out == "result"
    mock.assert_awaited_once()
    # Counter incremented (this tool is not exempt).
    assert ctx.deps.tool_call_count == 1


@pytest.mark.asyncio
async def test_search_tenant_knowledge_at_cap_short_circuits(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    mock = AsyncMock()
    monkeypatch.setattr(ctr, "search_knowledge", mock)
    ctx.deps.tool_call_count = ChatConstants.MAX_TOOL_CALLS_PER_TURN
    out = await ctr._search_tenant_knowledge(ctx, query="x")  # type: ignore[arg-type]
    assert "Tool call limit reached" in out
    mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_read_knowledge_document_forwards(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    mock = AsyncMock(return_value="doc-body")
    monkeypatch.setattr(ctr, "read_document", mock)
    assert (
        await ctr._read_knowledge_document(ctx, name="runbook")  # type: ignore[arg-type]
        == "doc-body"
    )


@pytest.mark.asyncio
async def test_read_knowledge_document_cap(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    ctx.deps.tool_call_count = ChatConstants.MAX_TOOL_CALLS_PER_TURN
    mock = AsyncMock()
    monkeypatch.setattr(ctr, "read_document", mock)
    out = await ctr._read_knowledge_document(ctx, name="x")  # type: ignore[arg-type]
    assert "limit reached" in out.lower()
    mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_read_knowledge_table_forwards(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    mock = AsyncMock(return_value="rows")
    monkeypatch.setattr(ctr, "read_table", mock)
    assert (
        await ctr._read_knowledge_table(ctx, name="users", max_rows=20)  # type: ignore[arg-type]
        == "rows"
    )


@pytest.mark.asyncio
async def test_read_knowledge_table_cap(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    ctx.deps.tool_call_count = ChatConstants.MAX_TOOL_CALLS_PER_TURN
    mock = AsyncMock()
    monkeypatch.setattr(ctr, "read_table", mock)
    out = await ctr._read_knowledge_table(ctx, name="x")  # type: ignore[arg-type]
    assert "limit reached" in out.lower()
    mock.assert_not_awaited()


# ── Read-only platform tools (parametrized to keep the file short) ─────────-


READ_ONLY_TOOLS = [
    # (wrapper, impl-attr-name, kwargs)
    ("_get_alert", "get_alert_impl", {"alert_id": "alert-1"}),
    ("_search_alerts", "search_alerts_impl", {"severity": "high"}),
    ("_get_workflow", "get_workflow_impl", {"workflow_id": "wf-1"}),
    ("_list_workflows", "list_workflows_impl", {}),
    ("_get_task", "get_task_impl", {"task_identifier": "task-1"}),
    ("_list_tasks", "list_tasks_impl", {}),
    ("_get_integration_health", "get_integration_health_impl", {"integration_id": "i-1"}),
    ("_list_integrations", "list_integrations_impl", {}),
    ("_get_workflow_run", "get_workflow_run_impl", {"workflow_run_id": "wfr-1"}),
    ("_get_task_run", "get_task_run_impl", {"task_run_id": "tr-1"}),
    ("_list_workflow_runs", "list_workflow_runs_impl", {}),
    ("_list_task_runs", "list_task_runs_impl", {}),
    ("_get_platform_summary", "get_platform_summary_impl", {}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("wrapper_name", "impl_name", "kwargs"), READ_ONLY_TOOLS)
async def test_read_only_tool_forwards_and_increments(
    monkeypatch: pytest.MonkeyPatch,
    ctx: _StubCtx,
    wrapper_name: str,
    impl_name: str,
    kwargs: dict,
) -> None:
    impl_mock = AsyncMock(return_value="ok")
    monkeypatch.setattr(ctr, impl_name, impl_mock)

    wrapper = getattr(ctr, wrapper_name)
    out = await wrapper(ctx, **kwargs)
    assert out == "ok"
    impl_mock.assert_awaited_once()
    assert ctx.deps.tool_call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("wrapper_name", "impl_name", "kwargs"), READ_ONLY_TOOLS)
async def test_read_only_tool_short_circuits_at_cap(
    monkeypatch: pytest.MonkeyPatch,
    ctx: _StubCtx,
    wrapper_name: str,
    impl_name: str,
    kwargs: dict,
) -> None:
    impl_mock = AsyncMock()
    monkeypatch.setattr(ctr, impl_name, impl_mock)
    ctx.deps.tool_call_count = ChatConstants.MAX_TOOL_CALLS_PER_TURN
    out = await getattr(ctr, wrapper_name)(ctx, **kwargs)
    assert "limit reached" in out.lower()
    impl_mock.assert_not_awaited()


# ── _search_audit_trail (admin-gated) ──────────────────────────────────────-


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "owner", "platform_admin"])
async def test_search_audit_trail_allowed_for_admin_roles(
    monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    deps = _StubDeps(user_roles=[role])
    ctx = _StubCtx(deps=deps)
    impl = AsyncMock(return_value="rows")
    monkeypatch.setattr(ctr, "search_audit_trail_impl", impl)

    assert await ctr._search_audit_trail(ctx, action="alert.create") == "rows"  # type: ignore[arg-type]
    impl.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_audit_trail_denied_for_non_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _StubDeps(user_roles=["analyst"])
    ctx = _StubCtx(deps=deps)
    impl = AsyncMock()
    monkeypatch.setattr(ctr, "search_audit_trail_impl", impl)

    out = await ctr._search_audit_trail(ctx)  # type: ignore[arg-type]
    assert "admin permissions" in out
    impl.assert_not_awaited()


# ── Action tools (two-phase confirmation, permission-gated) ────────────────-


@pytest.mark.asyncio
async def test_run_workflow_first_call_stages_pending_action(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    monkeypatch.setattr(
        ctr, "check_chat_action_permission", lambda roles, _a, _b: None
    )
    impl = AsyncMock()
    monkeypatch.setattr(ctr, "run_workflow_impl", impl)

    out = await ctr._run_workflow(ctx, workflow_id="wf-1", input_data='{"a":1}')  # type: ignore[arg-type]

    assert "confirmation" in out.lower()
    assert ctx.deps.pending_action is not None
    assert ctx.deps.pending_action.tool_name == "run_workflow"
    impl.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_workflow_second_call_replays_and_clears_pending(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    monkeypatch.setattr(
        ctr, "check_chat_action_permission", lambda roles, _a, _b: None
    )
    impl = AsyncMock(return_value="run-1")
    monkeypatch.setattr(ctr, "run_workflow_impl", impl)

    ctx.deps.pending_action = PendingAction(
        tool_name="run_workflow",
        description="...",
        kwargs={"workflow_id": "wf-1", "input_data": '{"a":1}'},
    )

    out = await ctr._run_workflow(ctx, workflow_id="wf-1", input_data='{"a":1}')  # type: ignore[arg-type]
    assert out == "run-1"
    impl.assert_awaited_once()
    assert ctx.deps.pending_action is None


@pytest.mark.asyncio
async def test_run_workflow_permission_denied(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    monkeypatch.setattr(
        ctr,
        "check_chat_action_permission",
        lambda roles, _a, _b: "forbidden",
    )
    impl = AsyncMock()
    monkeypatch.setattr(ctr, "run_workflow_impl", impl)
    out = await ctr._run_workflow(ctx, workflow_id="wf-1")  # type: ignore[arg-type]
    assert out == "forbidden"
    impl.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_workflow_invalid_json_input(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    monkeypatch.setattr(
        ctr, "check_chat_action_permission", lambda *args, **kw: None
    )
    impl = AsyncMock()
    monkeypatch.setattr(ctr, "run_workflow_impl", impl)
    out = await ctr._run_workflow(ctx, workflow_id="wf-1", input_data="{not json")  # type: ignore[arg-type]
    assert "Invalid JSON" in out
    impl.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_workflow_at_call_cap_short_circuits(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    monkeypatch.setattr(
        ctr, "check_chat_action_permission", lambda *args, **kw: None
    )
    impl = AsyncMock()
    monkeypatch.setattr(ctr, "run_workflow_impl", impl)
    ctx.deps.tool_call_count = ChatConstants.MAX_TOOL_CALLS_PER_TURN
    out = await ctr._run_workflow(ctx, workflow_id="wf-1")  # type: ignore[arg-type]
    assert "limit reached" in out.lower()
    impl.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_task_first_call_stages_then_replays(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    monkeypatch.setattr(
        ctr, "check_chat_action_permission", lambda *args, **kw: None
    )
    impl = AsyncMock(return_value="task-run-1")
    monkeypatch.setattr(ctr, "run_task_impl", impl)

    # First call: stages
    out1 = await ctr._run_task(ctx, task_identifier="t-1")  # type: ignore[arg-type]
    assert "confirmation" in out1.lower()
    assert ctx.deps.pending_action is not None
    impl.assert_not_awaited()

    # Second call with matching args: replays
    out2 = await ctr._run_task(ctx, task_identifier="t-1")  # type: ignore[arg-type]
    assert out2 == "task-run-1"
    impl.assert_awaited_once()
    assert ctx.deps.pending_action is None


@pytest.mark.asyncio
async def test_run_task_invalid_json(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    monkeypatch.setattr(
        ctr, "check_chat_action_permission", lambda *args, **kw: None
    )
    monkeypatch.setattr(ctr, "run_task_impl", AsyncMock())
    out = await ctr._run_task(ctx, task_identifier="t-1", input_data="not-json")  # type: ignore[arg-type]
    assert "Invalid JSON" in out


@pytest.mark.asyncio
async def test_run_task_permission_denied(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    monkeypatch.setattr(
        ctr, "check_chat_action_permission", lambda *args, **kw: "denied"
    )
    impl = AsyncMock()
    monkeypatch.setattr(ctr, "run_task_impl", impl)
    out = await ctr._run_task(ctx, task_identifier="t-1")  # type: ignore[arg-type]
    assert out == "denied"
    impl.assert_not_awaited()


@pytest.mark.asyncio
async def test_analyze_alert_first_call_then_replay(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    monkeypatch.setattr(
        ctr, "check_chat_action_permission", lambda *args, **kw: None
    )
    impl = AsyncMock(return_value="analysis-1")
    monkeypatch.setattr(ctr, "analyze_alert_impl", impl)

    out1 = await ctr._analyze_alert(ctx, alert_id="a-1")  # type: ignore[arg-type]
    assert "confirmation" in out1.lower()

    out2 = await ctr._analyze_alert(ctx, alert_id="a-1")  # type: ignore[arg-type]
    assert out2 == "analysis-1"
    impl.assert_awaited_once()


@pytest.mark.asyncio
async def test_analyze_alert_permission_denied(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    monkeypatch.setattr(
        ctr, "check_chat_action_permission", lambda *args, **kw: "no"
    )
    impl = AsyncMock()
    monkeypatch.setattr(ctr, "analyze_alert_impl", impl)
    out = await ctr._analyze_alert(ctx, alert_id="a-1")  # type: ignore[arg-type]
    assert out == "no"
    impl.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_alert_first_call_then_replay(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    monkeypatch.setattr(
        ctr, "check_chat_action_permission", lambda *args, **kw: None
    )
    impl = AsyncMock(return_value="alert-1")
    monkeypatch.setattr(ctr, "create_alert_impl", impl)

    out1 = await ctr._create_alert(
        ctx,  # type: ignore[arg-type]
        title="t",
        severity="high",
        description="long description " * 20,
    )
    assert "confirmation" in out1.lower()

    out2 = await ctr._create_alert(
        ctx,  # type: ignore[arg-type]
        title="t",
        severity="high",
        description="long description " * 20,
    )
    assert out2 == "alert-1"
    impl.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_alert_permission_denied(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    monkeypatch.setattr(
        ctr, "check_chat_action_permission", lambda *args, **kw: "no permission"
    )
    impl = AsyncMock()
    monkeypatch.setattr(ctr, "create_alert_impl", impl)
    out = await ctr._create_alert(ctx, title="t")  # type: ignore[arg-type]
    assert out == "no permission"
    impl.assert_not_awaited()


# ── Meta tools (no DB session, no tool-call cap) ────────────────────────────


@pytest.mark.asyncio
async def test_get_page_context_does_not_increment_counter(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    monkeypatch.setattr(ctr, "get_page_context_impl", lambda pc: "page=alerts")
    ctx.deps.page_context = {"page": "alerts"}
    assert await ctr._get_page_context(ctx) == "page=alerts"  # type: ignore[arg-type]
    # Meta tool — no cap.
    assert ctx.deps.tool_call_count == 0


@pytest.mark.asyncio
async def test_suggest_next_steps(
    monkeypatch: pytest.MonkeyPatch, ctx: _StubCtx
) -> None:
    monkeypatch.setattr(ctr, "suggest_next_steps_impl", lambda pc: "next: x")
    assert await ctr._suggest_next_steps(ctx) == "next: x"  # type: ignore[arg-type]
    assert ctx.deps.tool_call_count == 0


# ── build_tool_list — the registry entry point ──────────────────────────────


def test_build_tool_list_registers_every_tool_exactly_once() -> None:
    """Sanity: every wrapper appears as a Tool with a unique name. The
    module's docstring still says "22 tool wrappers" — that's stale
    (counted before the meta tools landed). Actual count is 24.

    If this drifts, adjust both the assertion and the
    ``chat_tool_registry`` docstring together."""
    tools = ctr.build_tool_list()
    names = [t.name for t in tools]

    expected = {
        "load_product_skill",
        "search_tenant_knowledge",
        "read_knowledge_document",
        "read_knowledge_table",
        "get_alert",
        "search_alerts",
        "get_workflow",
        "list_workflows",
        "get_task",
        "list_tasks",
        "get_integration_health",
        "list_integrations",
        "get_workflow_run",
        "list_workflow_runs",
        "get_task_run",
        "list_task_runs",
        "get_platform_summary",
        "search_audit_trail",
        "run_workflow",
        "run_task",
        "analyze_alert",
        "create_alert",
        "get_page_context",
        "suggest_next_steps",
    }

    assert set(names) == expected
    assert len(names) == len(expected)  # no duplicates


def test_build_tool_list_every_tool_has_description() -> None:
    """Pydantic-AI uses ``description`` to construct the JSON-schema for
    the LLM. An empty/None description is a regression that silently
    degrades agent performance."""
    for tool in ctr.build_tool_list():
        assert tool.description, f"Tool {tool.name} has empty description"
        assert len(tool.description) > 10, (
            f"Tool {tool.name} description suspiciously short"
        )
