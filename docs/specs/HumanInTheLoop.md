+++
version = "1.0"
status = "active"

[[changelog]]
version = "1.0"
summary = "Cy memoized replay, pause/resume (Project Kalymnos)"
+++

# Human-in-the-Loop (HITL) - v1

Spec Version: 1
Project Codename: Kalymnos

## Problem Statement

Security automation requires human judgment at critical decision points: escalation decisions, containment approvals, remediation sign-offs. The Analysi platform currently runs tasks and workflows to completion without any mechanism to pause execution, ask a human analyst a question, and resume based on their answer.

Humans are slow (minutes to hours). Tasks, workflows, and the alert analysis pipeline are designed for fast execution with tight timeouts. We need to pause at all three layers (task, workflow, analysis), release all compute resources, and resume cleanly when the human responds.

## Goals

- **G1**: A Cy script can call a hi-latency tool (e.g., Slack question) and the interpreter pauses at that point, resumes later with the answer, and continues execution naturally — no two-phase branching or script restructuring required.
- **G2**: Pause propagates cleanly through Task -> Workflow -> Analysis, releasing all compute (ARQ worker slots, async event loop, DB sessions). Zero resources held while waiting.
- **G3**: Resume propagates back down through Analysis -> Workflow -> Task when the human responds, using the existing control event bus.
- **G4**: Slack interactive messages (buttons) are received via Socket Mode (WebSocket) — no public URL required. Works behind firewalls for self-hosted deployments.
- **G5**: Multi-tenant: one Socket Mode connection per Slack workspace, shared across tenants that use the same workspace.
- **G6**: The Slack listener runs as a dedicated container (same Docker image, different entrypoint, exactly 1 replica).

## Non-Goals

- Communication channels other than Slack (email, Teams, PagerDuty) — future work, same backend plumbing
- Custom approval UIs or web forms — Slack buttons are sufficient for v1
- Real-time chat/streaming with humans — this is ask-and-wait, not conversation
- Free-form text responses — v1 uses button choices only (2-5 options)
- Multiple sequential HITL pauses in a single Cy script — v1 supports one pause point per task execution (may work with multiple but not a v1 guarantee)

---

## Architecture

```
  Cy Script (Task)                    Analysi Backend                    Slack
  ────────────────                    ──────────────                     ─────

  analysis = llm_run(...)
  answer = app::slack::ask(...)  ──▶  Post question via Slack API  ──▶  Message with buttons
      │                                                                 appears in channel
      │  Tool is hi-latency
      │  Cy pauses here
      │
      ▼
  ExecutionPaused raised          ──▶  TaskRun → "paused"
  with ExecutionCheckpoint             WorkflowNodeInstance → "paused"
  (node results cache +               WorkflowRun → "paused"
   variable snapshot)                  AlertAnalysis → "paused_human_review"
                                       ARQ worker freed
                                       ────────────────
                                       Zero resources held.
                                       State lives in PostgreSQL only.
                                       ────────────────

                                                            Hours later...

                                                                 Human clicks "Escalate"
                                                                        │
                                  Slack Listener (Socket Mode) ◀────────┘
                                  Receives interactive payload
                                       │
                                       ▼
                                  hitl_questions → "answered"
                                  control_events INSERT "human:responded"
                                       │
                                       ▼
                                  consume_control_events cron
                                  handle_human_responded():
                                    1. Load checkpoint from paused TaskRun
                                    2. Create new TaskRun with checkpoint
                                    3. Reset node → "pending"
                                    4. Reset workflow → "running"
                                    5. Re-queue analysis
                                       │
                                       ▼
  Cy resumes via memoized replay  ◀──  TaskExecutionService calls
  Cached nodes return instantly        interpreter.run_async(script, input, checkpoint)
  Hi-latency tool returns human's
  answer ("Escalate")
  Execution continues:
    if (answer == "Escalate") {
        app::jira::create(...)
    }
    return result
```

### Memoized Replay (Cy Language)

The Cy interpreter compiles scripts into an `ExecutionPlan` — a sequential list of `ExecutionNode`s, each with a unique `node_id`. The interpreter executes nodes one at a time, tracking results in an `ExecutionContext`.

For HITL, the interpreter supports **memoized replay**:

1. **First execution**: All nodes execute normally. When the executor reaches a `TOOL_CALL` node marked `hi_latency`, it saves a checkpoint (all completed node results + current variable state) and raises `ExecutionPaused`.

2. **Second execution (resume)**: The interpreter re-runs the same script with the same input, but with a **node result cache** from the checkpoint. Cached tool calls return instantly (no API calls, no LLM cost). The hi-latency tool returns the human's answer (injected into the cache). Execution continues past the pause point with new tool calls executing normally.

This is deterministic because all side-effectful operations in Cy are tool calls, and those results are cached during replay.

```
First execution:                          Second execution (resume):
─────────────────                         ──────────────────────────
node_1: ASSIGN    → executes              node_1: ASSIGN    → CACHE HIT (instant)
node_2: llm_run() → executes ($)          node_2: llm_run() → CACHE HIT (no LLM cost!)
node_3: ask()     → executes, PAUSE       node_3: ask()     → CACHE HIT (inject answer)
node_4: CONDITIONAL                       node_4: CONDITIONAL → executes (uses answer)
node_5: jira()                            node_5: jira()      → executes (new API call)
node_6: RETURN                            node_6: RETURN      → executes
```

---

## Requirements

### Cy Language (cy-language project)

- **R1**: Tool definitions accept a `hi_latency: bool` metadata flag. When `True`, the executor knows this tool may pause execution.
- **R2**: `PlanExecutor` accepts an optional `node_result_cache: Dict[str, Any]` parameter. Before executing any `TOOL_CALL` node, it checks the cache by `node_id`. Cache hit → return cached result without executing.
- **R3**: When a `TOOL_CALL` node is marked `hi_latency` and has no cache hit, the executor collects all completed node results and current variable state into an `ExecutionCheckpoint` dataclass, then raises `ExecutionPaused(checkpoint)`.
- **R4**: `ExecutionCheckpoint` is JSON-serializable. Contains: `node_results: Dict[str, Any]`, `pending_node_id: str`, `variables: Dict[str, Any]`, `plan_version: str`.
- **R5**: `Cy.run_async()` accepts an optional `checkpoint: ExecutionCheckpoint` parameter. When provided, it initializes the executor with the checkpoint's `node_result_cache`. The caller injects the hi-latency tool's result into the cache before calling resume.
- **R6**: `ExecutionPaused` exception carries the checkpoint and the pending tool call metadata (tool name, arguments) so the backend knows what was being called.

### Backend — Task Layer

- **R7**: `TaskExecutionService` detects `ExecutionPaused` from the Cy interpreter. Stores the checkpoint in `TaskRun.execution_context["_hitl_checkpoint"]` (JSONB). Returns `TaskExecutionResult(status=PAUSED)`.
- **R8**: `TaskExecutionService` on resume: loads checkpoint from the paused TaskRun, injects the human's answer as the cached result for `pending_node_id`, calls `interpreter.run_async(script, input, checkpoint=checkpoint)`.
- **R9**: A standalone task (no workflow) can pause and resume independently. The `human:responded` control event handler creates a new TaskRun and executes it.

### Backend — Workflow Layer

- **R10**: Add `PAUSED = "paused"` to `WorkflowConstants.Status`.
- **R11**: When `execute_node_instance()` receives `TaskExecutionResult(status=PAUSED)`, it marks the node as `"paused"` (existing behavior) and stores HITL metadata on the node instance.
- **R12**: `monitor_execution()` completion check: when paused nodes exist and no failed nodes exist, mark workflow as `"paused"` (not `"completed"`). Exit the monitor loop cleanly.
- **R13**: Resume: `handle_human_responded()` resets the paused node to `"pending"`, resets the workflow to `"running"`, and re-enters `monitor_execution()` via `_execute_workflow_synchronously()`.
- **R14**: Paused nodes do NOT block other branches. If a workflow has parallel branches and one pauses, the others continue normally. The workflow only pauses when all remaining activity is blocked by paused nodes.

### Backend — Analysis Layer

- **R15**: Add `PAUSED_HUMAN_REVIEW = "paused_human_review"` to `AnalysisStatus`.
- **R16**: The workflow execution pipeline step detects `workflow.status == "paused"` and raises `WorkflowPausedForHumanInput`. The pipeline catches this, marks the analysis as `"paused_human_review"`, and returns — freeing the ARQ worker.
- **R17**: After the workflow completes on resume, re-queue the `process_alert_analysis` ARQ job with the same `analysis_id`. The pipeline resumes from the workflow execution step, reads the now-completed workflow, and continues to disposition.
- **R18**: `reconcile_paused_alerts` handles `"paused_human_review"` as a safety net — detects stuck questions (past timeout), marks them as expired, and fails the analysis.

### HITL Question Tracking

- **R19**: New `hitl_questions` table (partitioned monthly by `created_at`):

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `tenant_id` | VARCHAR(100) | Multi-tenant isolation |
| `question_ref` | VARCHAR(100) | Slack message timestamp |
| `channel` | VARCHAR(100) | Slack channel ID |
| `question_text` | TEXT | The question asked |
| `options` | JSONB | Button options offered |
| `status` | VARCHAR(50) | `pending`, `answered`, `expired` |
| `answer` | VARCHAR(500) | The selected option (nullable) |
| `answered_by` | VARCHAR(100) | Slack user ID (nullable) |
| `answered_at` | TIMESTAMP(tz) | When answered (nullable) |
| `timeout_at` | TIMESTAMP(tz) | When the question expires |
| `task_run_id` | UUID | The paused TaskRun |
| `workflow_run_id` | UUID | The paused WorkflowRun (nullable) |
| `node_instance_id` | UUID | The paused WorkflowNodeInstance (nullable) |
| `analysis_id` | UUID | The paused AlertAnalysis (nullable) |
| `created_at` | TIMESTAMP(tz) | Partition key |

- **R20**: When a task pauses with a Slack question, a `hitl_questions` row is created in the same transaction as the TaskRun status update.

### Slack Listener (Dedicated Container)

- **R21**: A new entrypoint `analysi.slack_listener` runs as a dedicated container with exactly 1 replica (`strategy: Recreate` in Helm).
- **R22**: On startup, queries the database for all enabled Slack integrations across all tenants. Opens one Socket Mode WebSocket connection per unique Slack workspace.
- **R23**: On receiving an interactive payload (button click): matches `(channel, message_ts)` to `hitl_questions` table, stores the answer, emits `human:responded` control event. Acknowledges to Slack and updates the message (removes buttons, shows response).
- **R24**: Dynamically detects new/removed Slack integrations. Periodically (every 60s) re-queries the database and opens/closes connections as needed.
- **R25**: Handles WebSocket reconnection with exponential backoff. Logs connection state changes via structlog.

### Control Event Integration

- **R26**: New internal channel `human:responded` with handler in `control_events.py`.
- **R27**: Handler payload: `{question_id, answer, answered_by, workflow_run_id, node_instance_id, task_run_id}`.
- **R28**: Handler loads the paused TaskRun's checkpoint, injects the answer, creates a new TaskRun, resets the workflow node and workflow to resume, and calls `_execute_workflow_synchronously()`.
- **R29**: For standalone tasks (no workflow), the handler creates a new TaskRun with the checkpoint and executes it directly.

---

## Constraints

- **C1**: Zero compute resources held while waiting for human input. No polling loops, no blocked workers, no held DB sessions.
- **C2**: Socket Mode only — no public HTTP URL required. Deployable behind corporate firewalls.
- **C3**: The Cy language changes are in the `cy-language` project (separate repository). Backend changes must be compatible with both the new cy-language version (with checkpoint support) and older versions (graceful degradation — hi-latency tools fail with clear error on old versions).
- **C4**: All timestamps timezone-aware. All new tables partitioned by `created_at`.
- **C5**: Same Docker image for all containers (API, workers, Slack listener). Only entrypoint differs.
- **C6**: Never edit existing Flyway migrations — create new migration files.

---

## Error Handling

| Scenario | Behavior | User Impact |
|----------|----------|-------------|
| Slack workspace unreachable | Listener logs error, retries with backoff. Question stays `pending`. | Human won't see the question until Slack recovers. Analysis stays paused. |
| Question timeout (e.g., 4h) | Reconciliation cron marks question `expired`, fails the analysis | SOC dashboard shows failed analysis with "human review timeout" reason |
| Duplicate button click | First click stores answer. Second click finds `status != pending`, no-op | Slack shows "already answered" message |
| Listener container restarts | Reconnects to all workspaces on startup. Pending questions unaffected (state in DB) | Brief gap in receiving clicks. Clicks during gap are lost by Slack (Socket Mode limitation). Reconciliation handles timeouts. |
| Cy checkpoint deserialization fails | Task fails with error. Workflow/analysis fail. | Analysis shows failure. Must re-run from scratch. |
| Multiple tenants, same workspace | Single WebSocket connection. `hitl_questions.tenant_id` disambiguates | Transparent to users |
| Task pauses outside workflow | Only TaskRun pauses. No workflow/analysis to propagate to. `human:responded` handler creates new TaskRun directly | Works, but no workflow UI to show "waiting" status |

---

## Testing Checklist

### Cy Language (cy-language project)
- [ ] Unit: tool call with `hi_latency=True` and no cache → raises `ExecutionPaused` with checkpoint
- [ ] Unit: resume with checkpoint → cached nodes skip execution, new nodes execute
- [ ] Unit: `ExecutionCheckpoint` serializes to JSON and deserializes correctly
- [ ] Unit: LLM calls in cached nodes don't re-execute (verify no API call)
- [ ] Unit: control flow (if/else, for loops) replays correctly with cached results

### Backend — Task Layer
- [ ] Unit: `TaskExecutionService` catches `ExecutionPaused`, stores checkpoint, returns PAUSED
- [ ] Unit: resume creates new TaskRun with checkpoint, calls interpreter with cache
- [ ] Integration: standalone task pauses and resumes end-to-end

### Backend — Workflow Layer
- [ ] Unit: paused node → workflow enters `"paused"` status (not `"completed"`)
- [ ] Unit: parallel branches — one pauses, others continue, workflow pauses only when all remaining work is blocked
- [ ] Integration: workflow with one HITL node pauses and resumes end-to-end
- [ ] Integration: workflow with HITL node + parallel non-HITL branch — non-HITL branch completes, workflow pauses at HITL branch, resumes when answered

### Backend — Analysis Layer
- [ ] Integration: full stack — alert analysis pauses at HITL task, ARQ worker freed, resumes on answer, disposition reached
- [ ] Integration: timeout — question expires, analysis fails with clear error
- [ ] Integration: reconciliation detects stuck `paused_human_review` analyses

### Slack Listener
- [ ] Unit: interactive payload parsed correctly, question matched, answer stored
- [ ] Unit: duplicate click handling (second click is no-op)
- [ ] Integration: multi-tenant — two tenants, same workspace, correct tenant_id on control event
- [ ] Integration: dynamic workspace detection — add Slack integration, listener opens new connection

### Control Events
- [ ] Unit: `human:responded` handler loads checkpoint, creates TaskRun, resets workflow
- [ ] Integration: end-to-end control event flow from answer to workflow resume

---

## Open Questions

- **Q1**: Should we support a configurable default timeout per-tenant or per-task? (Leaning: per-task via tool parameter, default 4h)
- **Q2**: What happens if the Cy script has multiple hi-latency calls? First one pauses — does the resume trigger a second pause at the next one? (Leaning: yes, natural behavior of memoized replay. But not a v1 guarantee — needs testing)
- **Q3**: Should the Slack listener update the original message to show "Answered: Escalate" or post a thread reply? (Leaning: update the message — removes buttons, prevents double-click confusion)
- **Q4**: Should we emit an audit trail event when a human answers? (Leaning: yes, `hitl_response` activity event)

---

## Future Work

- **Thread replies as input**: Poll `conversations.replies` for free-form text answers (no Socket Mode needed). Useful for simpler deployments.
- **HTTP webhook endpoint**: `POST /v1/webhooks/slack/interactive` for deployments with public URLs. Same backend plumbing, different entry point.
- **Other channels**: Microsoft Teams, PagerDuty, email. Each channel needs its own listener but reuses the `hitl_questions` table and `human:responded` control event.
- **Approval chain**: Multiple sequential approvals with different approvers. Built on multiple hi-latency tool calls in one script.
- **Approval dashboard**: Web UI showing pending questions, answered history, timeout status. Reads from `hitl_questions` table.
- **Auto-escalation**: If question not answered in X time, auto-escalate to a different channel/person.

---

## File Locations

| Component | Path |
|-----------|------|
| Spec | `docs/specs/HumanInTheLoop.md` |
| Migration: hitl_questions table | `migrations/flyway/sql/V001__baseline.sql` |
| Slack listener entrypoint | `src/analysi/slack_listener.py` |
| HITL repository | `src/analysi/repositories/hitl_repository.py` |
| Control event handler | `src/analysi/alert_analysis/jobs/control_events.py` (extend) |
| Task execution changes | `src/analysi/services/task_execution.py` (extend) |
| Workflow execution changes | `src/analysi/services/workflow_execution.py` (extend) |
| Analysis pipeline changes | `src/analysi/alert_analysis/pipeline.py` (extend) |
| Constants | `src/analysi/constants.py` (extend) |
| Schemas | `src/analysi/schemas/alert.py` (extend) |
| Docker Compose | `deployments/compose/core.yml` (notifications-worker service) |
| Helm | `deployments/helm/analysi/templates/notifications-worker-deployment.yaml` (new) |
