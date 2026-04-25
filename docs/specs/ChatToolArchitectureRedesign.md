+++
version = "1.0"
status = "active"

[[changelog]]
version = "1.0"
summary = "Tool architecture redesign (Project Rhodes)"
+++

# Chat Tool Architecture Redesign — Project Rhodes

**Status**: Proposal
**Context**: QA testing of Rhodos uncovered 5 bugs — all caused by the same architectural patterns

## Problem Statement

During a 2-hour QA session, all 5 bugs found in the chatbot had the same root causes:

| Bug | Root Cause |
|-----|-----------|
| `alert.status` crash (500) | Manual field selection drifted from schema |
| Wrong status enum in docstring | Hand-written docstring drifted from model |
| No `name_filter` on tasks | Adding a filter requires touching 4-6 files |
| No `title_filter` on alerts | Same duplication problem |
| Wrong service class for workflow run | No type-safety between chat tools and service layer |

**One pattern causes all five bugs: the chat tool layer is a manual adapter that duplicates information from the service/schema layer, and every duplication point is a place where things silently drift.**

## Root Causes (5)

### RC-1: Parameter Duplication (4-6 files per filter)
Adding `name_filter` to `list_tasks` required editing:
1. `repositories/task.py` — add to `list_with_filters()`
2. `services/task.py` — pass through `list_tasks()`
3. `services/chat_tools.py` — add to `list_tasks_impl()`
4. `services/chat_service.py` — add to inner `list_tasks()` + docstring

Layers 1-2 often already support the filter. The friction is in layers 3-4.

### RC-2: Manual Output Formatting (12 tools, all hand-built)
Every tool manually picks fields and builds strings:
```python
# Current: fragile, drifts from schema
summary = {
    "alert_id": data.get("alert_id"),
    "status": data.get("status"),  # BUG: field doesn't exist
    ...
}
```
When `AlertResponse` changed from `status` to `analysis_status`, the chat tool wasn't updated.

### RC-3: Docstring Enum Drift
Tool docstrings hard-code enum values that drift from model definitions:
- Docstring says `severity: (critical, high, medium, low, informational)` — model has `info`
- Docstring says `function: (enrichment, ...)` — model has no `enrichment` value
- These wrong values get passed to the database and silently match zero rows

### RC-4: MagicMock Masks Attribute Bugs
Tests use unconstrained `MagicMock` that auto-creates any attribute. `mock_alert.status` and `mock_alert.analysis_status` both "work" — the test never catches the wrong one because it only asserts substring presence, not field correctness.

### RC-5: Monolithic `_build_agent` (561 lines, 19 tools)
All 19 tools are registered in one giant function with duplicated wrapper logic (tool call limit check, permission check, delegation to impl). Adding or modifying a tool means editing this massive function.

## Proposed Redesign

### Principle: Derive from source of truth, don't duplicate it

The schemas, models, and enums already exist. The chat layer should **derive** from them rather than restate them.

### Change 1: `ChatToolOutput` schemas — schema-driven output

Create slim Pydantic models specifically for chat tool output. These are **derived from** the existing API schemas but optimized for LLM consumption (fewer fields, shorter names).

```python
# src/analysi/schemas/chat_tool_output.py

class AlertChatSummary(BaseModel):
    """Slim alert representation for chat tool output."""
    alert_id: UUID
    title: str
    severity: AlertSeverity          # Reuses the actual enum
    analysis_status: AlertStatus     # Reuses the actual enum — can't drift
    source_vendor: str | None
    source_product: str | None
    short_summary: str | None = None

    @classmethod
    def from_alert_response(cls, alert: AlertResponse) -> "AlertChatSummary":
        return cls(
            alert_id=alert.alert_id,
            title=alert.title,
            severity=alert.severity,
            analysis_status=alert.analysis_status,
            source_vendor=alert.source_vendor,
            source_product=alert.source_product,
        )

    def to_chat_line(self) -> str:
        """Single-line summary for list output."""
        summary = f" — {self.short_summary[:100]}" if self.short_summary else ""
        return f"- **{self.title}** (ID: {self.alert_id}, {self.severity}/{self.analysis_status}){summary}"


class TaskChatSummary(BaseModel):
    """Slim task representation for chat tool output."""
    id: UUID
    name: str
    cy_name: str
    function: str | None              # From Task.function — uses the actual field
    status: str                       # From Component.status
    categories: list[str]             # From Component.categories
    description: str | None

    @classmethod
    def from_task(cls, task: Task) -> "TaskChatSummary":
        comp = task.component
        return cls(
            id=comp.id, name=comp.name, cy_name=comp.cy_name,
            function=task.function, status=comp.status,
            categories=comp.categories or [],
            description=comp.description,
        )

    def to_chat_line(self) -> str:
        cats = f" [{', '.join(self.categories[:5])}]" if self.categories else ""
        fn = f" ({self.function})" if self.function else ""
        desc = f" — {self.description[:80]}" if self.description else ""
        return f"- **{self.name}** (`{self.cy_name}`, ID: {self.id}){fn}{cats}{desc}"
```

**Why this helps:**
- `AlertChatSummary` uses `AlertSeverity` and `AlertStatus` — if the enum changes, the chat output changes. No drift.
- `from_alert_response()` validates at construction time — accessing a wrong attribute raises `AttributeError` immediately, not a silent MagicMock.
- `to_chat_line()` centralizes formatting — one place to update when output format changes.
- The schema is testable independently of the chat service.

### Change 2: Docstring generation from enums

Generate tool docstrings at module load time, pulling enum values from the actual models:

```python
# src/analysi/services/chat_tool_docs.py

from analysi.schemas.alert import AlertSeverity, AlertStatus

def _enum_values(enum_cls) -> str:
    """Comma-separated enum values for docstrings."""
    return ", ".join(e.value for e in enum_cls)

SEARCH_ALERTS_DOC = f"""\
Search and list alerts. Call with no arguments to get recent alerts.
Use title_filter to find alerts by name (e.g., "SQL Injection").

Args:
    severity: Filter by severity ({_enum_values(AlertSeverity)}).
    status: Filter by analysis status ({_enum_values(AlertStatus)}).
    source_vendor: Filter by source vendor name.
    title_filter: Text to search alert titles (case-insensitive).
    limit: Max results (default 10, max 20).
"""
```

**Why this helps:** Enum values in docstrings are generated from source of truth. When `AlertSeverity` adds a new value, every docstring that references it updates automatically.

### Change 3: Tool descriptor pattern — eliminate `_build_agent` duplication

Replace the 561-line `_build_agent` with a registry of tool descriptors:

```python
# src/analysi/services/chat_tool_registry.py

@dataclass
class ChatTool:
    """Self-contained tool descriptor."""
    name: str
    impl: Callable          # The *_impl function
    doc: str                # Generated docstring
    params: dict            # Parameter schema (for Pydantic AI)
    category: str           # "read" | "action" | "knowledge" | "meta"
    requires_permission: tuple[str, str] | None = None  # (resource, action)
    exempt_from_cap: bool = False

CHAT_TOOLS: list[ChatTool] = [
    ChatTool(
        name="search_alerts",
        impl=search_alerts_impl,
        doc=SEARCH_ALERTS_DOC,
        params={"severity": str | None, "status": str | None, ...},
        category="read",
    ),
    ChatTool(
        name="list_tasks",
        impl=list_tasks_impl,
        doc=LIST_TASKS_DOC,
        params={"function": str | None, "name_filter": str | None, ...},
        category="read",
    ),
    ...
]

def register_tools(agent: Agent, tools: list[ChatTool]):
    """Register all tools on the agent with standard wrappers."""
    for tool in tools:
        # Auto-generates the wrapper that handles:
        # - tool call limit check
        # - permission check (if configured)
        # - delegation to impl
        _register_single_tool(agent, tool)
```

**Why this helps:**
- Adding a new tool = adding one `ChatTool` entry. No 561-line function to edit.
- Parameters declared once (in the descriptor), not twice (wrapper + impl).
- Permission checks, tool call limits, and injection scanning are applied uniformly by the registration loop.

### Change 4: `spec_set=True` on all mocks + structural assertions

```python
# Before: MagicMock auto-creates any attribute
mock_alert = MagicMock()           # mock_alert.status silently works
mock_alert.status = "new"          # sets .status, but code reads .analysis_status

# After: spec_set prevents accessing undefined attributes
mock_alert = MagicMock(spec_set=AlertResponse)
mock_alert.analysis_status = "new" # OK — field exists on AlertResponse
mock_alert.status = "new"          # AttributeError — field doesn't exist
```

And output assertions check structure, not just substring:
```python
# Before:
assert "Phishing Attempt" in result

# After:
assert '"analysis_status": "new"' in result  # field name + value validated
# Or parse the output:
assert "new" in result  # status value present
assert "status" not in result or "analysis_status" in result  # right field name
```

### Change 5: Chat tool integration smoke tests

One integration test per tool that exercises the real code path:

```python
@pytest.mark.integration
class TestChatToolsSmoke:
    """Smoke tests: each chat tool against real DB, validates output structure."""

    async def test_list_tasks_output_format(self, session, seeded_tasks):
        result = await list_tasks_impl(session, "default", limit=5)
        # Validates structural invariants
        assert "Found" in result
        assert "tasks" in result
        # No MagicMock strings in output
        assert "MagicMock" not in result
        # Categories are present (new requirement)
        assert "[" in result  # category brackets

    async def test_search_alerts_no_crash(self, session, seeded_alerts):
        result = await search_alerts_impl(session, "default", severity="high")
        assert "Found" in result or "No alerts" in result
        assert "MagicMock" not in result

    async def test_get_workflow_run_uses_correct_service(self, session, seeded_workflow_run):
        result = await get_workflow_run_impl(session, "default", str(seeded_workflow_run.id))
        assert "Workflow Run" in result
        assert "status" in result.lower()
```

These would have caught all 5 bugs immediately.

## Migration Path

This is NOT a big-bang rewrite. Incremental adoption:

### Phase 1: Output schemas (eliminates RC-2) — ~1 day
- Create `chat_tool_output.py` with `AlertChatSummary`, `TaskChatSummary`, `WorkflowChatSummary`
- Refactor `*_impl` functions to use `from_*()` constructors and `to_chat_line()`
- Existing tests continue to work (output format stays similar)

### Phase 2: Generated docstrings (eliminates RC-3) — ~half day
- Create `chat_tool_docs.py` with docstring templates using `_enum_values()`
- Replace hard-coded docstrings in `_build_agent`
- Add a CI check: `validate_chat_tool_docs()` that asserts no enum value mismatch

### Phase 3: Tool registry (eliminates RC-1, RC-5) — ~1 day
- Create `chat_tool_registry.py` with `ChatTool` descriptors
- Replace `_build_agent` internals with `register_tools()` loop
- Each tool descriptor lives next to its `*_impl` function

### Phase 4: Test hardening (eliminates RC-4) — ~1 day
- Switch all chat tool mocks to `spec_set=True`
- Add structural output assertions
- Add integration smoke tests (1 per tool)

**Total estimate: 3-4 days, fully incremental, zero breaking changes.**

## What We DON'T Change

- **Security model unchanged** — injection scanning, tool result capping, output guard all remain
- **Pydantic AI framework** — still used, just with generated tool wrappers instead of hand-written ones
- **Two-phase confirmation** — action tools still require confirmation
- **Token budget management** — `cap_tool_result()` and `sanitize_tool_result()` still applied to every output
- **RBAC gating** — permission checks still enforced, just declared in the descriptor

## Comparison

| Aspect | Current | After Redesign |
|--------|---------|----------------|
| Files to add a filter | 4-6 | 1-2 (impl + descriptor) |
| Output format source | Manual strings | Pydantic model |
| Enum values in docs | Hand-copied | Generated from model |
| Wrong attribute detection | Silent (MagicMock) | Immediate (spec_set) |
| `_build_agent` size | 561 lines | ~50 lines (loop) |
| Integration test coverage | 0 tools | All tools |
| Security/safety | Full | Unchanged |
