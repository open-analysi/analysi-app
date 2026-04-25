# Agentic Orchestration Module

This module implements automated workflow generation using Claude Agent SDK with plain asyncio orchestration.

## Architecture: Keep Orchestration Pure

**The orchestration layer (`orchestrator.py`, `subgraphs/`, `nodes/`) MUST NOT directly call databases or REST APIs.**

- ✅ Use dependency injection: Pass `progress_callback` from job layer
- ❌ Never import or call database/httpx directly from orchestration code
- Why: Keeps orchestration testable without infrastructure

Example:
```python
# ✅ Job layer (workflow_generation_job.py) - couples to infrastructure
callback = DatabaseProgressCallback(...)
await run_full_orchestration(..., progress_callback=callback)

# ✅ Orchestration (orchestrator.py) - pure business logic
async def run_full_orchestration(..., progress_callback=None):
    if progress_callback:
        await progress_callback.on_stage_start(...)
```

## Critical SDK Configuration

The `AgentOrchestrationExecutor` MUST use these settings for file-based agent execution:

```python
# These are now defaults in AgentOrchestrationExecutor
# SECURITY: allowed_tools is an explicit allowlist (never None when MCP configured)
# MCP tools require wildcard entries: mcp__<server>__*
allowed_tools = ["Write", "Read", "Glob", "Grep", "Skill", "Task",
                 "mcp__analysi__*"]
permission_mode = "bypassPermissions"  # REQUIRED - auto-accepts file writes
setting_sources = ["user", "project"]  # REQUIRED - loads Skills from ~/.claude/skills/
max_turns = 100  # Complex multi-phase tasks need many turns
```

### Why These Settings Matter

| Setting | Default | Why It's Critical |
|---------|---------|-------------------|
| `permission_mode` | `"bypassPermissions"` | Without this, agents ask for permission and files won't be created |
| `setting_sources` | `["user", "project"]` | **MUST include "user"** to load Skills from `~/.claude/skills/`. Without it, Skill tool calls fail with "Unknown skill" |
| `max_turns` | `100` | Complex tasks (cybersec-task-builder) spawn subagents and run many test iterations. 25 turns is often insufficient |
| `allowed_tools` | Explicit allowlist | **SECURITY**: Never `None` with MCP. Must include `mcp__<server>__*` wildcards for each MCP server — without them agents can see tools but cannot call them |

### Creating Executors — Use the Factory Functions

Never instantiate `AgentOrchestrationExecutor` directly in production or eval code.
Use the factories in `config.py`:

```python
# Production (jobs, workers)
from analysi.agentic_orchestration import create_executor
executor = create_executor(tenant_id=tenant_id, oauth_token=oauth_token)

# Eval tests
from analysi.agentic_orchestration import create_eval_executor
executor = create_eval_executor(api_key=api_key, isolated_project_dir=tmpdir)
```

Both factories set `setting_sources=["project"]` so the SDK only reads `.claude/`
from the workspace directory — never from `~/.claude/` or the local project root.
This prevents dev CLAUDE.md files from leaking into agent execution (wasting tokens
and polluting agent behaviour).

## LangGraph Alternative Implementation

The runbook generation stage has an alternative LangGraph-based implementation that can be enabled via feature flag.

### Feature Flag

```bash
# Enable LangGraph implementation for runbook generation
export ANALYSI_USE_LANGGRAPH_PHASE1=true

# Default: Use Claude Agent SDK (current production)
export ANALYSI_USE_LANGGRAPH_PHASE1=false  # or unset
```

### When to Use Each

| Implementation | Use When |
|----------------|----------|
| **SDK (default)** | Production workloads, proven reliability |
| **LangGraph** | Testing composition strategies, research, experimentation |

### Architecture Comparison

| Aspect | SDK Implementation | LangGraph Implementation |
|--------|-------------------|--------------------------|
| Entry point | `runbook_generation_node()` | `runbook_generation_node_langgraph()` |
| Agent execution | `runbook-match-agent.md` via `AgentWorkspace` | `run_phase1()` StateGraph |
| Skills access | Skill tool calls in agent | SkillsIR progressive retrieval |
| Output | `{runbook, matching_report, metrics}` | Same structure (JSON string for matching_report) |

### Configuration

LangGraph uses these environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `ANALYSI_USE_LANGGRAPH_PHASE1` | Enable LangGraph for runbook generation | `false` |
| `ANALYSI_RUNBOOKS_SKILL_PATH` | Skills directory for SkillsIR | N/A (skills are DB-only) |
| `ANTHROPIC_API_KEY` | API key for LangChain LLM | (required) |

### Files

- `nodes/runbook_generation.py` - Feature flag dispatch
- `nodes/runbook_generation_langgraph.py` - LangGraph wrapper node
- `langgraph/config.py` - LLM and store configuration
- `langgraph/metrics.py` - Metrics collection
- `langgraph/kea/phase1/` - LangGraph runbook matching implementation

## CRITICAL: SDK Cleanup Error Handling

**Problem:** The Claude Agent SDK uses anyio internally, but we run under asyncio. When running parallel SDK queries with `asyncio.gather()`, cleanup can raise:
```
RuntimeError: Attempted to exit cancel scope in a different task than it was entered in
```

This error occurs during generator cleanup (`aclose()`) and can **replace successful results with exceptions**, causing tasks that actually completed to be marked as failed.

### Three Pillars of the Solution

**1. Don't Break - Continue and Flag** (`sdk_wrapper.py`)
```python
# ❌ OLD - break triggers premature cleanup error
async for message in query_gen:
    if isinstance(message, ResultMessage):
        result = capture_result(message)
        break  # Triggers aclose() which raises cancel scope error

# ✅ NEW - continue lets loop exhaust naturally
got_result = False
async for message in query_gen:
    if got_result:
        continue  # Skip processing, keep iterating until SDK stops
    if isinstance(message, ResultMessage):
        result = capture_result(message)
        got_result = True  # Don't break!
```

**2. Catch Cleanup Errors After Loop** (`sdk_wrapper.py`)
```python
try:
    async for message in query_gen:
        # ... capture result before any cleanup error
except RuntimeError as e:
    # Cleanup error happens when loop ends and Python calls aclose()
    if result is not None and "cancel scope" in str(e).lower():
        pass  # Ignore - we have the result
    else:
        raise  # Real error - propagate
```

**3. BaseException Recovery with DB Check** (`second_subgraph_no_langgraph.py`)
```python
# CancelledError is BaseException in Python 3.8+, not Exception!
except BaseException as e:
    # Task may have completed despite cleanup error - check database
    existing_task = await _check_task_exists(tenant_id, proposal_name)
    if existing_task:
        return {"success": True, "task_id": existing_task["id"], "recovered": True}
    return {"success": False, "error": str(e)}
```

### Why This Works

| Step | What Happens | Why It's Safe |
|------|--------------|---------------|
| 1. Get ResultMessage | Capture result immediately | Result stored before any cleanup |
| 2. Set flag, continue | Loop exhausts naturally | No premature aclose() trigger |
| 3. Loop ends | Python calls aclose() | May raise cancel scope error |
| 4. Catch RuntimeError | Check if we have result | Ignore error if result captured |
| 5. DB recovery (parallel) | Check if task was created | Handles CancelledError in gather() |

### Key Files

- `sdk_wrapper.py`: Pillars 1 & 2 - don't break, catch cleanup errors
- `second_subgraph_no_langgraph.py`: Pillar 3 - BaseException + DB recovery
- `nodes/task_building.py`: Changed `except Exception` to `except BaseException`

### Tests

- `tests/unit/agentic_orchestration/test_sdk_wrapper_cleanup.py`
- `tests/unit/agentic_orchestration/test_second_subgraph_metrics.py`

## AgentWorkspace Pattern

Agents write files to disk, which are captured into orchestrator state. Each stage automatically receives a specialized system prompt based on the `WorkflowGenerationStage`:

```python
workspace = AgentWorkspace(run_id="workflow-123")
try:
    outputs, metrics = await workspace.run_agent(
        executor=executor,
        agent_prompt_path=Path("agents/runbook-match-agent.md"),
        context={"alert": alert_data},
        expected_outputs=["matching-report.json", "matched-runbook.md"],
        stage=WorkflowGenerationStage.RUNBOOK_GENERATION,
    )
    # outputs["matching-report.json"] = file content or None
finally:
    workspace.cleanup()
```

### Specialized System Prompts

The workspace automatically sets stage-specific system prompts:

| Stage | System Prompt |
|-------|---------------|
| RUNBOOK_GENERATION | "Expert Cyber Security Analyst specialized in creating comprehensive runbooks from security alerts" |
| TASK_PROPOSAL | "Expert Cyber Security Analyst specialized in identifying available tools and composing them into discrete Tasks" |
| TASK_BUILDING | "Expert Cyber Security Analyst specialized in DSL programming, with emphasis on quality, accuracy, and testing" |
| WORKFLOW_ASSEMBLY | "Expert Cyber Security Analyst specialized in workflow composition and validation, with emphasis on creating executable workflows" |

## User Prompt Structure

The workspace injects working directory and context into agent prompts:

```markdown
{agent .md file content}

## Working Directory
Write all output files to: /tmp/kea-abc12345-xyz/

## Input Context
```json
{
  "alert": { ... }
}
```
```

## Key Behaviors

- Missing expected files return `None` in outputs dict
- Large outputs (9KB+ runbooks) work without issues
- Isolated temp directories with tenant support: `kea-{tenant}-{run_id}-*`
- Cleanup in `finally` blocks; orphaned dirs cleaned by reconciliation job

## Available Nodes

| Node | Agent | Stage | Expected Outputs |
|------|-------|-------|------------------|
| `runbook_generation_node` | runbook-match-agent.md | RUNBOOK_GENERATION | matching-report.json, matched-runbook.md |
| `task_proposal_node` | runbook-to-task-proposals.md | TASK_PROPOSAL | task-proposals.json |
| `task_building_node` | cybersec-task-builder.md | TASK_BUILDING | task-result.json |
| `workflow_assembly_node` | workflow-builder.md | WORKFLOW_ASSEMBLY | workflow-result.json |

## Step Handoff Contracts

Data flows through 4 steps via orchestrator state:

```
Alert → Step 1: Runbook Generation
          ↓ runbook: str
        Step 2: Task Proposal
          ↓ task_proposals: list[dict]
        Step 3: Task Building (parallel)
          ↓ tasks_built: list[dict]
        Step 4: Workflow Assembly
          ↓ workflow_id: str
```

**Step 1→2**: `runbook` (markdown string, 5-10KB)
**Step 2→3**: `task_proposals` with fields: `name` (human-readable), `cy_name` (for existing/modification), `designation` ("existing"|"modification"|"new"), `description`, `integration-mapping`
**Step 3→4**: `tasks_built` aggregated list with: `{success, task_id, cy_name, error}` per task
**Step 4→END**: `workflow_id` (UUID), `workflow_composition` (list of cy_names)

**Critical Fields**:
- `name`: Human-readable (Title Case) - e.g., "VirusTotal: IP Reputation Analysis"
- `designation`: Must be exactly "existing", "modification", or "new" (validated)
- `cy_name`: Required for existing/modification (from task list), auto-generated by MCP for new tasks

**Validation**: Task proposals validated by agent using `skills/source/runbook-to-workflow/scripts/validate_task_proposals.py`
**Naming Guidelines**: Use `task-naming` skill (available in `skills/source/task-naming/SKILL.md`)

### Task Building Node

Processes task proposals with designation "new" or "modification":

```python
from analysi.agentic_orchestration.nodes import task_building_node

# State must include:
state = {
    "task_proposals": [
        {"name": "IP Reputation", "designation": "new", ...},
        {"name": "Existing Check", "designation": "existing", ...},  # Skipped
    ],
    "alert": {...},
    "runbook": "...",
    "run_id": "uuid",
    "tenant_id": "acme",
}

result = await task_building_node(state, executor)
# result["tasks_built"] = [{"success": True, "task_id": "...", "cy_name": "..."}]
```

### Workflow Assembly Node

Gathers cy_names from existing proposals and built tasks, then composes workflow:

```python
from analysi.agentic_orchestration.nodes import workflow_assembly_node

# State must include task_proposals and tasks_built from prior stages:
state = {
    "task_proposals": [
        {"name": "Existing Check", "designation": "existing", "cy_name": "vt_ip_check"},
    ],
    "tasks_built": [
        {"success": True, "cy_name": "new_analysis", "task_id": "uuid-1"},
    ],
    "alert": {...},
    "runbook": "...",
    "run_id": "uuid",
    "tenant_id": "acme",
}

result = await workflow_assembly_node(state, executor)
# result["workflow_id"] = "uuid-workflow" or None
# result["workflow_composition"] = ["vt_ip_check", "new_analysis"]
# result["workflow_error"] = None or "error message"
```

## Agent and Skill Resolution

### Agent .md File Resolution

The system searches for agent .md files in multiple directories (in order):

1. `/app/agents` - In Docker container (copied from `agents/dist/` by Dockerfile)
2. `{PROJECT_ROOT}/agents/dist` - In local dev (single source of truth)

**Runtime Override:**
```bash
# Use custom agent directory for testing
ANALYSI_ALERT_PROCESSING_AGENT_DIR=/custom/path python ...
```

**How It Works:**
```python
from analysi.agentic_orchestration.config import get_agent_path

# Searches all configured directories in order
agent_path = get_agent_path("runbook-match-agent.md")
```

### Skill Resolution

**Skills are DB-only.** They are installed per-tenant via content packs (e.g., `analysi packs install foundation -t <tenant>` — see `content/CLAUDE.md` and `docs/projects/delos.md`) and accessed through `DatabaseResourceStore` / `TenantSkillsSyncer`. No filesystem skills directories are used. `analysi-demo-loader` is NOT involved in skill distribution — it only manages lab services, integration credentials, and alert replay.

### Agent Packaging

Production agents live in `agents/dist/` (committed to git). The Dockerfile copies them:

```dockerfile
COPY agents/dist /app/agents
RUN mkdir -p /home/appuser/.claude/agents && \
    cp -r /app/agents/* /home/appuser/.claude/agents/
```

To update agents:

```bash
# 1. Package prod agents from skilltree
make package-agents

# 2. Commit updates
git add agents/dist/
git commit -m "Update production agents"

# 3. Rebuild
make rebuild-alert-worker
```

## Module Structure

```
agentic_orchestration/
├── __init__.py           # Public exports
├── config.py             # Agent/skill directory resolution
├── observability.py      # Metrics, callbacks, stages
├── sdk_wrapper.py        # AgentOrchestrationExecutor
├── workspace.py          # AgentWorkspace for file capture
├── schemas/              # Pydantic models (TaskProposal, etc.)
├── nodes/                # Orchestration node functions
└── subgraphs/            # Asyncio-based subgraph definitions
```

## References

- Spec: `docs/specs/AutomatedWorkflowBuilder.md`
- Agent Packaging: `scripts/agents_management/CLAUDE.md`
- Operations Guide: `docs/operations/agent-skills-management.md`
