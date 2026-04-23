# Eval Test Guidelines

## Quick Start

```bash
make test-eval-quick    # Core tests: ~$3, ~10min (SDK sanity + first subgraph + DB skills)
make test-eval          # Full suite: ~$12, ~40min (all 26 tests)
```

Both require `ANTHROPIC_API_KEY`. Cost tracking is automatic — a summary table prints at session end.

## Test Inventory & Value Assessment

### High Value — run these always (`make test-eval-quick`)

| File | Tests | Cost | What it proves |
|------|-------|------|----------------|
| `test_00_sdk_sanity` | 1 | ~$0.13 | SDK subprocess launches, can write files. Gate test — if this fails, skip everything else. |
| `test_first_subgraph` | 4 | ~$2 | Full runbook generation pipeline: agent reads runbooks skill, scores alert, composes runbook, proposes tasks with correct schema. Uses cached fixture (1 LLM call → 4 tests). |
| `test_phase1_db_skills` | 8 | ~$0.43 | LangGraph composition path with DB-backed skills: runbook composed, persisted to DB, index updated, correct strategy selected. Fast — no SDK subprocess overhead. |

**Total: 13 tests, ~$2.56, ~10 min.** These cover the core value proposition: "give me an alert, get back a runbook and task plan."

### Medium Value — run for deeper validation

| File | Tests | Cost | What it proves |
|------|-------|------|----------------|
| `test_task_building_basic` | 5 | ~$1.57 | Workspace isolation, agent file writes, MCP tool access, task building node produces output. Validates the AgentWorkspace pattern all agents depend on. |
| `test_second_subgraph` | 6 | ~$5.73 | Task building from proposals, workflow composition, edge cases (empty proposals, parallel building, existing tasks). Most expensive file — 4 of 6 tests are independent (uncached). |

### Low Value — run when debugging task builder agent

| File | Tests | Cost | What it proves |
|------|-------|------|----------------|
| `test_task_creation_e2e` | 2 | ~$2.68 | cybersec-task-builder agent creates a task via MCP then runs it. Detailed metrics dump. Research/diagnostic test. |

## Why the Costs Are What They Are

The Claude Agent SDK bundles a full Claude Code CLI binary (176MB). Every `execute_stage()` call:
1. Spawns a subprocess running the full CLI
2. CLI loads its ~16K token built-in system prompt (tool definitions, safety instructions)
3. On top of that, it loads any CLAUDE.md files from `cwd` and `setting_sources`

This means **every SDK call has a ~$0.05 floor cost** just for the system prompt, regardless of what you ask. A "say hello" costs the same base as a complex task building session.

The LangGraph-based tests (`test_phase1_db_skills`) bypass the SDK entirely — they call `ChatAnthropic` directly. Same LLM, no CLI overhead. That's why 8 tests + 35 LLM calls cost only $0.43.

### Executor Isolation

All eval executors use `setting_sources=["project"]` pointing at an isolated temp directory. This prevents loading:
- `~/.claude/CLAUDE.md` (personal dev config, ~1.4KB)
- Project root `CLAUDE.md` (15.5KB of dev instructions about migrations, Docker, naming conventions)

Without isolation, every SDK call would waste ~4,400 extra tokens on context irrelevant to agent execution.

Use the factory functions — never instantiate `AgentOrchestrationExecutor` directly:
```python
# Eval tests
from analysi.agentic_orchestration import create_eval_executor
executor = create_eval_executor(api_key=key, isolated_project_dir=tmpdir)

# Production jobs
from analysi.agentic_orchestration import create_executor
executor = create_executor(tenant_id=tid, oauth_token=token)
```

## Critical Rules

### 1. NEVER Run the Same LLM Call Multiple Times

Use module-scoped pytest fixtures to cache results:

```python
# In conftest.py — runs ONCE, shared across 4 tests
@pytest.fixture(scope="module")
def subgraph_result(anthropic_api_key):
    return asyncio.run(run_subgraph(alert, executor))

# In test file — free, just reads cached result
@pytest.mark.eval
async def test_produces_runbook(subgraph_result):
    assert subgraph_result["runbook"] is not None

@pytest.mark.eval
async def test_produces_proposals(subgraph_result):
    assert subgraph_result["proposals"] is not None
```

### 2. LLM Assertions Must Tolerate Non-Determinism

LLM outputs vary between runs. Never assert exact equality:

```python
# BAD — brittle, fails on LLM non-determinism
assert result["composition"] == ["task_a", "task_b"]

# GOOD — checks presence, tolerates ordering/wrapping
assert "task_a" in flatten(result["composition"])
assert "task_b" in flatten(result["composition"])
```

### 3. Always Close Async Generators Properly

The SDK's `query()` returns an async generator with anyio task groups. See `sdk_wrapper.py` for the "don't break, continue and flag" pattern that avoids cancel scope errors.

For module-scoped fixtures using `asyncio.run()`, add `await asyncio.sleep(1.0)` before returning to let SDK background tasks complete cleanup.

### 4. Cost Tracking (Automatic)

Cost tracking is automatic — `conftest.py` installs interceptors at session start:

- **SDK calls** (`execute_stage`) — exact cost from `ResultMessage`
- **LangChain calls** (`ChatAnthropic.ainvoke`) — estimated from token counts

Summary prints at session end:
```
============================== Eval Cost Summary ===============================
  Test                                                Cost      In     Out  Cache R  Cache W
  ────────────────────────────────────────────────────────────────────────────────────────
  tests/eval/test_00_sdk_sanity.py::test_sdk_...   $0.1264       3     221   17,711   17,927
  fixture                                          $2.3127  35,511  27,331  742,689  117,219
  ────────────────────────────────────────────────────────────────────────────────────────
  TOTAL (39 calls)                                $12.4194  35,655 101,743 ...

  Total session cost: $12.4194
```

For custom LLM calls (not SDK or LangChain), use the fixture:
```python
def test_custom(eval_cost_tracker):
    eval_cost_tracker.record(cost_usd=0.05, label="custom call")
```

Update `_PRICE_PER_M` in `cost_tracker.py` when model pricing changes.

### 5. Test Independence

Even with cached fixtures, never mutate shared state:
```python
# GOOD — read-only
assert "investigation" in subgraph_result["runbook"].lower()

# BAD — mutates shared fixture
subgraph_result["proposals"].append({"new": "proposal"})
```

## Isolated Test Environment

Each eval test gets a fresh temp directory with copied `agents/dist/`:

```
/tmp/eval-test-XXXXX/
├── .claude/
│   └── agents/        ← copied from agents/dist/
└── outputs/           ← agent writes here
```

- `setting_sources=["project"]` → SDK only reads from this temp `.claude/`
- No pollution of `~/.claude/` or project source
- Directories auto-cleaned after 48 hours
- Preserve with `ANALYSI_PRESERVE_WORKSPACES=true`

## File Index

```
tests/eval/
├── CLAUDE.md              ← This file
├── conftest.py            ← Fixtures, cost tracking, isolated directories
├── cost_tracker.py        ← EvalCostTracker + SDK/LangChain interceptors
├── test_00_sdk_sanity.py  ← Gate test (run first)
├── test_first_subgraph.py ← Core: runbook generation + task proposals
├── test_phase1_db_skills.py ← Core: LangGraph composition with DB skills
├── test_second_subgraph.py  ← Task building + workflow assembly
├── test_task_building_basic.py ← Workspace + MCP mechanics
└── test_task_creation_e2e.py   ← Full task create+run diagnostic
```
