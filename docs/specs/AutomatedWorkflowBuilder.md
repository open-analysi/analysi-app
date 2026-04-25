+++
version = "1.0"
status = "active"

[[changelog]]
version = "1.0"
summary = "AI-powered workflow generation (Project Kea)"
+++

# Automated Workflow Builder (Project Kea) \- v1

## Overview

Project Kea enhances alert processing by automatically composing custom analysis workflows for each Analysis Group. It replaces the previous hardcoded workflow selection in the alert analysis pipeline with intelligent, context-aware workflow generation.

## Integration Points

- **Input**: NAS Alert (standardized schema from Alerts\_v2.md)
- **Output**: Executable Workflow (validated via TypedWorkflows\_v2.md)
- **Pipeline**: Replaces Step 3 (Workflow Builder) in Alert Analysis Pipeline (see `analyses` API)
- **MCP Servers**: `workflow-builder`, `cy-script-assistant` (task building)

## Technology Stack

- **AI Model**: Claude (via the Agent SDK)
- **Orchestration**: Plain asyncio with pluggable stages pattern
- **Deployment**: Enhanced alert-worker Docker container
- **Skills/Agents**: Packaged and committed to git for deployment (see Agent/Skills Management below)

## Analysis Groups and Workflow Routing Rules

This section defines the new resources, database tables, and REST APIs required for Project Kea.

### Analysis Groups

An Analysis Group is a grouping of alerts that share the same analysis plan. For example, alerts from the same detection rule follow the same decision tree for triage and investigation. Every alert must belong to exactly one group.

**V1 Approach**: The alert's `rule_name` field value directly determines its Analysis Group. This keeps the initial implementation simple while covering the most common use case.

**API: Analysis Groups**
- GET /v1/{tenant_id}/analysis-groups - List all groups
- GET /v1/{tenant_id}/analysis-groups/{uuid} - Get specific group
- POST /v1/{tenant_id}/analysis-groups - Create group
- DELETE /v1/{tenant_id}/analysis-groups/{uuid} - Delete group

**Database Table: `analysis_groups`**
- id (UUID, auto-generated)
- title (unique)
- created_at

Note: Additional fields like `rule_name` can be added later as needed.

#### Alert-worker Execution Steps

Alert workers use analysis-group-rules to map each NAS alert to a unique Analysis Group. These rules should be refreshed periodically to pick up new configurations.

When an alert-worker encounters an alert whose Group doesn't exist yet, it must:
1. Create the new Analysis Group
2. Start a Workflow Generation process for that group

**API: Workflow Generations**
- GET /v1/{tenant_id}/workflow-generations/{uuid} - Get generation status
- POST /v1/{tenant_id}/workflow-generations - Start new generation (requires `analysis_group` UUID)

**Database Table: `workflow_generations`**
- id (UUID, auto-generated)
- analysis_group (FK)
- created_at
- status (enum: running, success, failed, paused)
- current_phase (JSONB) - tracks progress through generation phases

Note: Use proper Pydantic schemas for JSONB fields to ensure type safety. Reuse existing status enums if available (e.g., from analyses).

When workflow generation completes, the new workflow is assigned to the Analysis Group so that subsequent alerts of that Group are routed to it.

**API: Alert Routing Rules**
- GET /v1/{tenant_id}/alert-routing-rules/{uuid} - Get specific rule
- POST /v1/{tenant_id}/alert-routing-rules - Create routing rule (requires analysis_group and workflow IDs)

**Database Table: `alert_routing_rules`**
- id (UUID, auto-generated)
- analysis_group (FK)
- workflow_generation (FK)
- workflow (FK)

**Caching**: Alert-workers should maintain an in-memory cache of known Analysis Groups to avoid repeated database lookups. On cache miss, the worker queries the database and attempts to register the group as new. Since multiple worker replicas may process alerts concurrently, this registration may fail if another worker registered it first—this is expected and should be handled gracefully (skip and continue).

## Workflow Generation (Project Kea)

A new workflow is created once per distinct Analysis Group. This one-time generation is important because: (a) workflow creation is expensive and slow, and (b) a consistent workflow ensures predictable behavior across invocations.

The detailed workflow generation process is covered in the Agentic Implementation section below. First, we address the coordination of workflow generation across workers.

### Workflow Generation \- Coordination

Workflow generation occurs synchronously during alert ingestion. Since generation is AI-heavy and can take several minutes, coordination is critical when multiple workers may be processing alerts for the same Analysis Group concurrently.

**Proposal**: The first alert-worker to encounter a new Analysis Group creates both the Analysis Group and its Workflow Generation as an atomic transaction.

**API Option 1** (query parameter):
- POST /v1/{tenant_id}/analysis-groups?workflow_gen=true

**API Option 2** (dedicated endpoint):
- POST /v1/{tenant_id}/analysis-groups/with-workflow-generation

Both options create entries in `analysis_groups` and `workflow_generations` tables atomically.

TODO: Review which API design is cleaner.

Subsequent alerts of the same group are stored normally in the `alerts` table but marked with:
- `Alert.analysis_status`: `paused` (already supported in existing enum)
- `AlertAnalysis.current_step`: `Workflow Builder`

This indicates the alert is waiting for workflow generation to complete. Alert-workers recognize this state and do not trigger analysis for these alerts.

**Design Note**: We use `Alert.analysis_status` as the single source of truth for pause state (proper normalization). `AlertAnalysis.status` remains `running` - no schema changes needed.

Since alerts can now be stored in a `paused` state, we need a periodic reconciliation process (ARQ job running every 10 seconds) that:
1. Finds alerts with `Alert.analysis_status='paused'` and `AlertAnalysis.current_step='Workflow Builder'`
2. Checks if their Analysis Group now has a completed workflow
3. Resumes analysis for those alerts (transitions `Alert.analysis_status` from `paused` to `analyzing`)

**Coordination**: This job runs on all alert-worker instances using a first-come-first-serve mechanism:
- The first worker to successfully transition an alert's status claims it for processing
- Other workers that attempt the same alert simply skip it and continue

See the Connectors Container ARQ implementation for reference.

**Opportunity**: While implementing this reconciliation, consider also resuming alerts that failed due to unexpected errors (e.g., worker restarts or crashes). This would address the existing issue where failed analyses are never retried.

### Workflow Generation \- Agentic Implementation

The Kea **Agent Orchestrator (AO)** uses plain asyncio with a pluggable stages pattern. Each node executes one phase of workflow generation by calling the Claude Agent SDK's `query()` API.

**Node Execution Model:**
- Each node receives a system prompt and an agent Markdown file as its user prompt
- The prompt instructs the agent to load specific skills for that phase
- Subagents can be triggered within a `query()` to handle parallel subtasks
- Phase 3 (Task Building) uses `asyncio.gather()` for parallel execution

**Why plain asyncio instead of LangGraph?** The Claude Agent SDK uses anyio internally, but our workers run under asyncio. When running parallel SDK queries with LangGraph's Send API, cleanup raised `RuntimeError: Attempted to exit cancel scope in a different task`. Plain asyncio with proper error recovery avoids this issue.

**Why agent Markdown files?** Claude Code subagents cannot trigger other subagents. By using agent Markdown files as user prompts (rather than directly triggering subagents), we preserve the ability for the agent to spawn its own subagents as needed.

Reference: [Agent SDK Skills Documentation](https://docs.claude.com/en/docs/agent-sdk/skills)

**Agent Workspace Pattern:**

Agents write output files to disk (e.g., `matching-report.json`, `matched-runbook.md`). This enables:
- Local REPL testing with files appearing in the working directory
- Production execution with the same agent definitions

Each workflow generation run gets an isolated temporary workspace:

```python
class AgentWorkspace:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.work_dir = Path(tempfile.mkdtemp(prefix=f"kea-{run_id[:8]}-"))

    async def run_agent(self, executor, agent_prompt_path, context, expected_outputs):
        # Load agent .md, inject working directory and context
        # Execute via query()
        # Read expected output files into dict
        # Return outputs for orchestrator state

    def cleanup(self):
        shutil.rmtree(self.work_dir)
```

The user prompt includes working directory instructions:

```markdown
## Working Directory
Write all output files to: {work_dir}

## Input Context
{json context}
```

**Workspace Cleanup:**

Normal cleanup occurs in node `finally` blocks. For orphaned directories (crashed workflows), the reconciliation ARQ job also:
1. Lists directories matching `kea-*` in temp
2. Extracts run_id from directory name
3. Checks if corresponding workflow_generation exists and is terminal (success/failed)
4. Removes directories for completed or non-existent workflow generations

This ensures disk usage stays bounded even when workflows crash or containers restart.

The orchestrator implements the following phases:

**Phase 1: Runbook Generation**
- **Input**: NAS Alert
- **System Prompt**: Expert Cyber Security Analyst specialized in creating comprehensive runbooks from security alerts
- **User Prompt**: runbook-match-agent.md
- **Skills**: runbooks-manager, cybersecurity-analyst
- **Output**: Investigation runbook for the alert type

**Phase 2: Task Proposal**
- **System Prompt**: Expert Cyber Security Analyst specialized in identifying available tools and composing them into discrete Tasks
- **User Prompt**: runbook-to-task-proposals-agent.md
- **Skills**: runbook-to-workflow, cybersecurity-analyst
- **Output**: Structured list of tasks, each categorized as:
  - "New" - needs to be built
  - "Modify" - existing task needs changes
  - "Existing" - use as-is

*Phases 1-2 run sequentially in `first_subgraph.py`. Phases 3-4 run in `second_subgraph_no_langgraph.py`.*

**Phase 3: Parallel Task Building**
- Creates one async task per proposal from Phase 2, executed via `asyncio.gather()`
- **System Prompt**: Expert Cyber Security Analyst specialized in DSL programming, with emphasis on quality, accuracy, and testing
- **User Prompt**: cybersec-task-builder.md
- **Skills**: task-builder, cy-language-programming, cybersecurity-analyst
- **Subagents**: cy-script-segment-tester.md (for parallel testing of code segments)
- **Output**: All tasks created, validated, and adjusted

**Phase 4: Workflow Assembly**
- Combines tasks from Phase 3 with existing tasks from Phase 2 into a workflow
- **User Prompt**: workflow-builder.md
- **Skills**: workflow-builder
- **Output**: Validated, executable workflow
- TODO: Complete the testing description

## LangGraph Stage Alternatives (Extension)

This extension introduces alternative stage implementations using LangGraph instead of Claude Agent SDK, enabling multi-provider LLM support while maintaining the same orchestration framework.

### Motivation

1. **Multi-Provider Support**: Use OpenAI, Anthropic, Azure, or other LLM providers via LangChain
2. **Reduced LLM Dependency**: Deterministic logic (scoring, matching) runs without LLM calls
3. **Better Testability**: Deterministic components can be unit tested without mocks
4. **Feature Flag Control**: Gradual migration via `ANALYSI_RUNBOOK_STAGE_BACKEND` environment variable

### Stage Backend Selection

A provider factory enables runtime selection between Claude Agent SDK (`claude_agent`) and LangGraph (`langgraph`) implementations. The default is `claude_agent` for backward compatibility.

### Phase 1 Alternative: LangGraph Runbook Matcher

Replaces `runbook-match-agent.md` with a LangGraph graph that separates deterministic scoring from LLM composition.

**Architecture:**

```
Alert → LangGraph RunbookMatcherGraph
         │
    [load_index] ─── Deterministic
         │
    [calculate_scores] ─── Deterministic (reuses RunbookMatcher)
         │
    [determine_confidence] ─── Deterministic
         │
    ┌────┴─────────────────┐
    │                      │
 VERY HIGH/HIGH       MEDIUM/LOW/VERY LOW
    │                      │
[fetch_runbook]       ┌────┴────┐
    │            [analyze_gaps] ─── LLM (Step 1: What's missing?)
    │                  │
    │            [select_strategy] ─ LLM (Step 2: How to compose?)
    │                  │
    │            [extract_sections] ─ LLM (Step 3: What from each source?)
    │                  │
    │            [compose_runbook] ─ LLM (Step 4: Blend + generate)
    │                  │
    │            [validate_runbook] ─ Deterministic
    │                  │
    │            ┌─────┴─────┐
    │          PASS        FAIL
    │            │           │
    │            │     [fix_runbook] ─ LLM (Step 5: Self-correction)
    │            │        (loop max 3x)
    └────────────┴───────────┘
           │
    [write_outputs]
```

**Key Insight**: ~80% of the workflow is deterministic Python. LLM calls only needed for composition (MEDIUM/LOW/VERY LOW confidence scenarios).

**Composition is Multi-Step LLM** (observed in Phase 47 - see `tests/eval/phase_47_observation/OBSERVATIONS.md`):

The composition path isn't a single "compose this" LLM call. Observed agent behavior shows 5 distinct reasoning steps:

| Step | Node | What Happens |
|------|------|--------------|
| 1 | `analyze_gaps` | "IDOR runbook would completely miss the XSS component" |
| 2 | `select_strategy` | Choose Hybrid Blend, Category-Based, etc. |
| 3 | `extract_sections` | Decide what to take from each source |
| 4 | `compose_runbook` | Blend sources + generate novel content |
| 5 | `fix_runbook` | Self-correction after validation failure |

### Agentic Validation Loop

When composing runbooks, LLM output goes through a validation loop that enforces specifications from the runbooks-manager skill:

1. **LLM generates runbook** (after gap analysis, strategy selection, and extraction)
2. **Deterministic validation** checks:
   - No `@include` directives (must be self-contained)
   - Valid YAML frontmatter with required fields
   - Has `## Steps` section with at least one critical step (★)
   - Valid pattern types and enum values
3. **If validation fails** → errors sent back to LLM with correction instructions
4. **Loop** until validation passes OR max iterations (3) reached

This replicates the iterative self-correction behavior of Claude Agent SDK agents.

### Migration Path

1. Implement LangGraph alternative (feature flag defaults to `claude_agent`)
2. Enable for specific tenants, compare outputs
3. Default to LangGraph when stable
4. Optionally deprecate Claude Agent SDK implementation

## Enhancements to the Alert-Worker

With Kea, the alert-worker gains significant new capabilities. Some requirements below are inferred from earlier sections; others are new details added for clarity:

* The agent will be using Claude Agents SDK to create new Tasks and new Workflows
* External agents/skills are packaged and committed to git (see Agent/Skills Management section below)
* The container for alert-worker should have claude-code installed. We should be able to open a shell inside the container and run claude there.

**API Key Handling:**
- **Local Testing**: Pass ANTHROPIC_API_KEY from host environment to container for convenience when running `claude` directly inside the container.
- **All Other Cases** (demos, production): Alert-worker retrieves the API key from the Credentials Store via `/v1/{tenant}/credentials`. Use a standardized credential name for this purpose (to be defined). This is the same pattern used for integration credentials.

**MCP Server Configuration:**
Agent SDK `query()` calls require access to these MCP servers:

```json
{
  "cy-script-assistant": {
    "type": "http",
    "url": "http://{api-container-name}:8000/v1/{tenant}/mcp"
  },
  "workflow-builder": {
    "type": "http",
    "url": "http://{api-container-name}:8000/v1/{tenant}/workflows-builder/mcp"
  }
}
```

## Key Review Areas

No outstanding items - all review areas have been resolved.

## Proposed Breakdown

1. Identify all TODOs and areas requiring research or PoC. Complete design before implementation.
2. Build the Agentic Orchestration (AO) component:
   1. Make implementation observability-friendly (export progress, avoid complex DB transactions in core logic for easier testing/mocking)
   2. Create eval tests (new pytest annotation type) to validate LLM+Agent correctness. These run only on explicit request, not with unit/integration tests.
3. Build new REST APIs, database tables, and Pydantic schemas. Include integration tests for coordination logic.
4. Implement Alert-Worker enhancements with ARQ reconciliation. Full end-to-end testing at this stage.

## Future Work

* **Configurable Analysis Group Rules**: V1 uses `rule_name` directly as the Analysis Group identifier. Future versions could support configurable rules that map alerts to groups based on:
  - Simple: Single field (current default)
  - Basic: Two fields together uniquely define the Group
  - Advanced: Conditional predicates on multiple fields (e.g., if field A is in [X, Y] and field B is not Z, then Group is "Foo")

  This would require a new `analysis_group_rules` API and database table.

## Agent/Skills Management

### Design Decision: Commit External Resources to Git

External agents and skills (from `~/.claude` and other repos like `runbooks-y`) are **packaged and committed to git** rather than copied at Docker build time.

**Rationale:**

1. **Simpler Deployment** - No external dependencies during Docker build. AWS deployments and CI/CD "just work" without configuring access to external repos.

2. **Version Control** - Git tracks exactly which agent/skill versions were deployed. Easy to rollback to previous versions.

3. **Reproducible Builds** - Same git commit = same agents/skills every time. No surprises from external repos changing.

4. **CI/CD Friendly** - GitHub Actions can build containers without accessing `~/.claude` or external repos.

5. **Explicit Updates** - Developers consciously decide when to incorporate external changes via `make package-external-agents`, rather than automatically picking up latest at build time.

**Directory Structure:**

```
docker/agents_skills/
├── agents/    # External agents from ~/.claude/agents (committed)
└── skills/    # External skills from ~/.claude/skills (committed)
```

Local agents/skills (version-controlled) are in `/agents` and `/skills` at project root.

**What Gets Packaged:**

The packaging script **selectively** copies only required agents and skills:

- **3 agents** from `~/.claude/agents`: runbook-match-agent, cybersec-task-builder, cy-script-segment-tester
- **6 skills** from `~/.claude/skills`: runbooks-manager, cybersecurity-analyst, splunk-skill, cy-language-programming, task-builder, workflow-builder

This keeps the Docker image lean and deployment predictable.

**Workflow:**

Normal development uses packaged files already in git:
```bash
make rebuild-alert-worker  # Uses files from git
```

When external sources change, update manually:
```bash
make package-external-agents  # Selectively copy required files
git add docker/agents_skills/
git commit -m "Update external agents/skills"
make rebuild-alert-worker
```

Override source directories:
```bash
ANALYSI_BUILD_AGENTS_DIR=/custom/agents make package-external-agents
```

**Runtime Agent Resolution:**

At runtime, the system searches for agents in order:
1. `ANALYSI_ALERT_PROCESSING_AGENT_DIR` (if set) - Override for testing
2. `/app/agents` - Local agents (version-controlled in this repo)
3. `/app/docker/agents_skills/agents` - Packaged external agents

First match wins.

**Trade-offs:**

- **Pro**: Simpler deployment, version control, reproducibility
- **Con**: Manual updates required via `make package-external-agents`
- **Mitigation**: Clear documentation, simple one-command workflow

See `docs/operations/agent-skills-management.md` for complete operational guide.

## SDK Skills Integration (Hydra Phases 6-8)

This section describes how the Claude Agent SDK path integrates with DB-backed skills and the Knowledge Extraction (Hydra) pipeline for secure writeback.

### Problem

The default Agent SDK execution uses global skills from `~/.claude/skills/`:
- All tenants share the same skills (no isolation)
- Agent-created files (new runbooks) are lost when workspace is cleaned up
- No validation of agent-generated content before persistence

### Solution: DB-Backed Skills with Hydra Writeback

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  SDK Agent Execution Flow (per workflow generation)                         │
│                                                                             │
│  1. CREATE WORKSPACE                                                        │
│     AgentWorkspace(run_id, tenant_id, skills_syncer)                        │
│                                                                             │
│  2. SYNC SKILLS FROM DB                                                     │
│     TenantSkillsSyncer.sync_skills() → {workspace}/.claude/skills/          │
│     Records baseline manifest (hash of all synced files)                    │
│                                                                             │
│  3. RUN AGENT                                                               │
│     executor.skills_project_dir = workspace                                 │
│     setting_sources = ["project"]  ← loads ONLY from workspace              │
│     Agent reads skills, may create/modify runbooks                          │
│                                                                             │
│  4. DETECT NEW FILES                                                        │
│     workspace.detect_new_files() → compare against baseline                 │
│     Returns list of created/modified files                                  │
│                                                                             │
│  5. SUBMIT TO HYDRA                                                         │
│     a. ContentPolicy.filter_new_files()                                     │
│        - Block executables (.py, .sh, .js)                                  │
│        - Block suspicious patterns (os.system, eval, rm -rf)                │
│     b. submit_new_files_to_hydra()                                          │
│        - Create temp KUDocument                                             │
│        - Run extraction pipeline (classify, validate, place)                │
│        - Auto-apply approved extractions to skill                           │
│                                                                             │
│  6. CLEANUP                                                                 │
│     workspace.cleanup() — temp directory removed                            │
│     New runbooks now persisted in DB via Hydra                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Components

**TenantSkillsSyncer** (`skills_sync.py`):
- Syncs skills from DatabaseResourceStore to filesystem
- Records baseline manifest for later diffing
- Supports fallback to filesystem skills if DB unavailable

**ContentPolicy** (`content_policy.py`):
- Blocks executable extensions: `.py`, `.sh`, `.bash`, `.js`, `.ts`, `.exe`, `.bat`, `.cmd`, `.ps1`
- Detects suspicious code patterns in markdown code blocks
- Returns approved files + rejected files with reasons

**hydra_tenant_lock** (`skills_sync.py`):
- PostgreSQL advisory lock for serialized Hydra operations per tenant
- Prevents race conditions when multiple agents submit simultaneously

**submit_new_files_to_hydra** (`skills_sync.py`):
- Creates temporary KUDocument for each file
- Runs through Knowledge Extraction pipeline
- Auto-applies successful extractions (no human approval needed for agent outputs)

### Integration with Stages Path

The stages path (`run_orchestration_with_stages`) is the production execution model. Skills sync and Hydra integration are wired through:

```python
# StageStrategyProvider creates stages with skills_syncer
provider = StageStrategyProvider(
    executor=executor,
    skills_syncer=skills_syncer,  # For DB-backed skills
    session=session,               # For Hydra submission
)

# AgentRunbookStage uses skills_syncer
class AgentRunbookStage:
    def __init__(self, executor, skills_syncer=None, session=None):
        ...

    async def execute(self, state):
        workspace = AgentWorkspace(
            run_id=state["run_id"],
            tenant_id=state["tenant_id"],
            skills_syncer=self.skills_syncer,
        )

        # Sync skills before agent runs
        if self.skills_syncer:
            await workspace.setup_skills(skill_names)
            executor.skills_project_dir = workspace.work_dir

        # Run agent
        result = await runbook_generation_node(...)

        # Detect and submit new files to Hydra
        if self.skills_syncer and self.session:
            await self._detect_and_submit_to_hydra(workspace, state)

        workspace.cleanup()
```

### Tenant Isolation

When `skills_syncer` is provided:
- `setting_sources = ["project"]` (not `["user", "project"]`)
- SDK loads skills ONLY from `{workspace}/.claude/skills/`
- Each tenant sees only their own skills from DB
- Global skills in `~/.claude/skills/` are NOT used

### Backward Compatibility

- `skills_syncer` and `session` are optional parameters
- Without them, stages use global skills (existing behavior)
- No breaking changes to existing deployments

## Open Questions

* How do we allow users to control which Runbooks (from the Runbooks repo) are used for a particular AO Kea run, using our existing Knowledge Unit abstraction?
  * This likely requires changes to how skills load resources, possibly via a dedicated MCP server.
