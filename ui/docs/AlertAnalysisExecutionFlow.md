# Alert Analysis & Workflow Generation — UI Execution Flow

This document is a guide for UI developers who need to understand how the
alert analysis pipeline and workflow generation orchestration are surfaced
in the analysi-app frontend. It is deliberately scoped to what the UI does;
for the authoritative backend contract see `docs/specs/Alerts.md` (pipeline)
and `docs/specs/AutomatedWorkflowBuilder.md` (workflow generation). Ground
truth for the pipeline steps is the code under
`src/analysi/alert_analysis/pipeline.py` and
`src/analysi/alert_analysis/steps/`.

## High-Level Flow Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          ALERT INGESTION                                      │
│  POST /v1/{tenant}/alerts → Alert created with analysis_status: "new"        │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                     ANALYSIS TRIGGERED                                        │
│  POST /v1/{tenant}/alerts/{id}/analyze → analysis_status: "in_progress"      │
│  Returns: { analysis_id, status: "accepted" }                                │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    ANALYSIS PIPELINE (4 steps)                                │
│                                                                               │
│  Step 1: PRE-TRIAGE                                                          │
│  └─ Initial classification and priority assessment                           │
│                                                                               │
│  Step 2: WORKFLOW BUILDER                                                     │
│  ├─ Look up the workflow for this alert type (via rule_name)                 │
│  ├─ If a workflow exists → proceed to Step 3                                 │
│  └─ Otherwise → PAUSE (AnalysisStatus="paused") and trigger Workflow         │
│                 Generation; resume automatically when it completes            │
│                          │                                                    │
│                          ▼                                                    │
│         ┌────────────────────────────────────────┐                           │
│         │     WORKFLOW GENERATION JOB            │                           │
│         │  (Async, runs in parallel)             │                           │
│         │                                        │                           │
│         │  Stage 1: Runbook Generation           │                           │
│         │  Stage 2: Task Proposal                │                           │
│         │  Stage 3: Task Building                │                           │
│         │  Stage 4: Workflow Assembly            │                           │
│         │                                        │                           │
│         │  On complete → Resume paused alerts    │                           │
│         └────────────────────────────────────────┘                           │
│                          │                                                    │
│                          ▼                                                    │
│  Step 3: WORKFLOW EXECUTION                                                   │
│  └─ Run the workflow, producing a WorkflowRun + TaskRuns                     │
│                                                                               │
│  Step 4: FINAL DISPOSITION UPDATE                                             │
│  └─ Extract disposition/summaries from workflow artifacts, update alert      │
└──────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                          COMPLETED                                            │
│  Alert.analysis_status: "completed"                                          │
│  AlertAnalysis.status: "completed"                                           │
│  Disposition, confidence, and summaries populated                            │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Status States & Transitions

There are two related but distinct status fields the UI cares about.

### Alert-facing status (`Alert.analysis_status`)

This is the simplified value shown in alert lists, tables, and badges. The
values come from the `Status` schema in `ui/src/generated/api.ts`.

| Value | Meaning | Typical UI |
|---|---|---|
| `new` | Alert has not been analyzed yet | Gray badge, "Analyze" CTA visible |
| `in_progress` | Pipeline is executing (may be internally paused) | Animated badge, "Analyzing…" |
| `completed` | Pipeline finished successfully | Green badge, "Re-analyze" CTA |
| `failed` | Pipeline encountered an error | Red badge, "Retry" CTA |
| `cancelled` | Analysis was cancelled | Neutral badge |

Importantly, when the *internal* `AnalysisStatus` is `paused` (waiting on
workflow generation) or `paused_human_review` (HITL), the alert-facing
`analysis_status` stays `in_progress`. End users do not need to know about the
internal pause — the pipeline progress panel is what surfaces that detail.

### Internal analysis status (`AlertAnalysis.status`)

This comes from the `AnalysisStatus` schema. It is what the pipeline worker
writes and what `GET /alerts/{id}/analysis/progress` returns in the `status`
field.

| Value | Meaning |
|---|---|
| `running` | Pipeline is actively executing a step |
| `paused` | Paused mid-pipeline waiting for workflow generation to finish (Step 2) |
| `paused_human_review` | Paused at a Human-in-the-Loop question (see `docs/specs/HumanInTheLoop.md`) |
| `completed` | All steps finished |
| `failed` | Any step failed terminally |
| `cancelled` | User cancelled |

### Workflow Generation status (`WorkflowGeneration.status`)

From `WorkflowGenerationStatus`: `running | completed | failed`.

### Per-step progress

Each step in `steps_detail` has a `completed` boolean plus `started_at`,
`completed_at`, `retries`, and `error`. The UI treats them as simple stateful
rows — there is no separate step-level enum.

---

## Alert Analysis Pipeline

### The 4 steps

Source of truth: `src/analysi/alert_analysis/pipeline.py` and the individual
step modules in `src/analysi/alert_analysis/steps/`.

#### Step 1 — Pre-Triage (`pre_triage`)
- **File**: `steps/pre_triage.py`
- **Purpose**: Initial alert classification / priority hints before any
  expensive work.
- **Duration**: ~1–2 seconds.
- **Current state**: Minimal / stubbed; may return placeholder values.

#### Step 2 — Workflow Builder (`workflow_builder`)
- **File**: `steps/workflow_builder.py`
- **Purpose**: Resolve which workflow should handle this alert type.
- **Logic**:
  1. Extract `rule_name` from the alert.
  2. Check the in-memory cache, then call the coordination API to get / create
     the analysis group.
  3. Look for an alert routing rule mapping this group to a `workflow_id`.
  4. If found → return the `workflow_id`.
  5. If missing → trigger a `WorkflowGeneration` job and return `None`.
- **Pause behavior**: Returning `None` causes the pipeline to transition to
  `AnalysisStatus="paused"`. When the generation job completes, the
  coordination layer calls the resume-paused-alerts endpoint and this step
  re-runs with a fresh cache.

#### Step 3 — Workflow Execution (`workflow_execution`)
- **File**: `steps/workflow_execution.py`
- **Purpose**: Execute the workflow resolved in Step 2 and produce a
  `WorkflowRun` with task runs and artifacts.
- **API call**: `POST /v1/{tenant}/workflows/{id}/run`.
- **Duration**: seconds to minutes, depending on the workflow.
- **Output**: `workflow_run_id` stored in the analysis record.

#### Step 4 — Final Disposition Update (`final_disposition_update`)
- **File**: `steps/final_disposition_update.py`
- **Purpose**: Pull disposition and summary artifacts from the workflow run,
  fuzzy-match them against available dispositions, and write the result back
  to the alert.
- **Output**: Alert is fully analyzed with `disposition_id`, `confidence`,
  `short_summary`, and `long_summary`.

### Progress payload shape

```typescript
// Returned by GET /v1/{tenant}/alerts/{alertId}/analysis/progress
interface AnalysisProgress {
  analysis_id: string;
  current_step: string;
  completed_steps: number;
  total_steps: number; // 4 for current pipeline
  status: AnalysisStatus; // "running" | "paused" | ...
  error?: string;
  steps_detail?: Record<string, {
    completed: boolean;
    started_at: string | null;
    completed_at: string | null;
    retries: number;
    error: string | null;
  }>;
}
```

The actual TypeScript type lives at `ui/src/types/alert.ts` (`AnalysisProgress`).

---

## Workflow Generation Orchestration

Triggered when Step 2 cannot find an existing workflow for the alert's
`rule_name`. The generation is asynchronous and performed by AI agents.

### The 4 stages

| Key | Agent | Purpose |
|---|---|---|
| `runbook_generation` | `runbook-match-agent` | Draft a security investigation runbook |
| `task_proposal` | `runbook-to-task-proposals` | Decide which tasks are `existing` / `modification` / `new` |
| `task_building` | `cybersec-task-builder` | Build new/modified tasks in parallel |
| `workflow_assembly` | `workflow-builder` (prod) or `CloneWorkflowStage` (test) | Compose tasks into a runnable workflow |

In **test mode** (`ANALYSI_ALERT_PROCESSING_TEST_MODE=true`) stages 1–3 are
stubbed (~0s) and stage 4 clones a default workflow (~1s), so end-to-end
generation is near-instant. In **production**, full generation typically takes
15–30 minutes and costs dollars in LLM usage. TBD — verify current cost /
duration characteristics against the latest runs.

### WorkflowGeneration payload shape

Use the generated types from `ui/src/types/alert.ts` (re-exported from
`ui/src/types/api.ts`). The key fields the UI reads are:

- `id`, `status`, `current_phase`
- `workflow_id` (null until assembly completes)
- `orchestration_results` — contains the runbook, task proposals, stage
  metrics, total cost, and any terminal error

### Generated vs reused workflow

The UI can determine whether the workflow used by an alert was freshly
generated or reused by checking whether a `WorkflowGeneration` row exists for
the triggering analysis:

```http
GET /v1/{tenant}/workflow-generations?triggering_alert_analysis_id={analysis_id}
```

- `workflow_generations.length > 0` → this alert's analysis triggered a
  generation (show "new workflow" badge, link to stage metrics & cost).
- Empty array → the workflow was reused from an existing routing rule.

---

## API Reference

Only the endpoints the UI actively calls (or is likely to call soon) are listed
here. For the full REST contract, see `docs/specs/Alerts.md` and the OpenAPI
spec imported at `ui/src/generated/api.ts`.

### Alerts

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/{tenant}/alerts` | List alerts (paginated, filterable) |
| `GET` | `/v1/{tenant}/alerts/{alert_id}` | Single alert (optional `include_short_summary`) |
| `GET` | `/v1/{tenant}/alerts/search` | Full-text search across alerts |
| `GET` | `/v1/{tenant}/alerts/by-entity/{entity_value}` | Alerts touching an entity |
| `GET` | `/v1/{tenant}/alerts/by-ioc/{ioc_value}` | Alerts touching an IOC |

### Alert Analysis

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/{tenant}/alerts/{alert_id}/analyze` | Start analysis. Returns 202 with `{ analysis_id, status: "accepted", message }` |
| `GET` | `/v1/{tenant}/alerts/{alert_id}/analysis/progress` | Current progress (polled by the UI) |
| `GET` | `/v1/{tenant}/alerts/{alert_id}/analyses` | Full history of analyses for this alert |
| `PUT` | `/v1/{tenant}/alerts/{alert_id}/analysis-status` | Admin override of the alert-facing status |

Example `progress` response (pipeline paused waiting on workflow generation):

```json
{
  "analysis_id": "…",
  "current_step": "workflow_builder",
  "completed_steps": 1,
  "total_steps": 4,
  "status": "paused",
  "error": null,
  "steps_detail": {
    "pre_triage":              { "completed": true,  "started_at": "…", "completed_at": "…", "retries": 0, "error": null },
    "workflow_builder":        { "completed": false, "started_at": "…", "completed_at": null, "retries": 0, "error": null },
    "workflow_execution":      { "completed": false, "started_at": null, "completed_at": null, "retries": 0, "error": null },
    "final_disposition_update":{ "completed": false, "started_at": null, "completed_at": null, "retries": 0, "error": null }
  }
}
```

### Workflow Generation (Kea coordination)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/{tenant}/workflow-generations` | List generations; filter via `triggering_alert_analysis_id` |
| `GET` | `/v1/{tenant}/workflow-generations/{generation_id}` | Full generation record (stage results, metrics, workflow_id) |
| `GET` | `/v1/{tenant}/analysis-groups/active-workflow?title={rule_name}` | Check the routing rule + generation for a given alert type |

Internal endpoints (`PATCH .../progress`, `PUT .../results`, and the
`resume-paused-alerts` endpoint) are called by the worker, not the UI.

### Workflow Execution / Task Runs

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/{tenant}/workflows/{workflow_id}/run` | Start a workflow (used by Step 3) |
| `GET` | `/v1/{tenant}/workflow-runs/{workflow_run_id}` | Full run payload |
| `GET` | `/v1/{tenant}/workflow-runs/{workflow_run_id}/status` | Lightweight status poll |
| `GET` | `/v1/{tenant}/workflow-runs/{workflow_run_id}/graph` | Graph for the workflow visualization |
| `GET` | `/v1/{tenant}/workflow-runs/{workflow_run_id}/nodes` | Node instances |
| `POST` | `/v1/{tenant}/workflow-runs/{workflow_run_id}/cancel` | Cancel a run |
| `GET` | `/v1/{tenant}/task-runs` | List task runs (filter by `workflow_run_id`, `task_id`, `status`) |
| `GET` | `/v1/{tenant}/task-runs/{trid}` | Task run detail |

### Dispositions

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/{tenant}/dispositions` | All dispositions |
| `GET` | `/v1/{tenant}/dispositions/by-category` | Grouped by category |
| `GET` | `/v1/{tenant}/dispositions/{disposition_id}` | Single disposition |

---

## UI Implementation

### Key files

| Concern | Path |
|---|---|
| Alert details page | `ui/src/pages/AlertDetails.tsx` |
| Pipeline progress rail | `ui/src/components/alerts/AnalysisProgressDisplay.tsx` |
| Workflow generation sub-progress | `ui/src/components/alerts/WorkflowGenerationProgress.tsx` |
| Analysis details tab | `ui/src/components/alerts/AnalysisDetailsTab.tsx` |
| Overview / findings / decision banner | `ui/src/components/alerts/{OverviewTab,FindingsTab,DecisionBanner}.tsx` |
| Alerts list page | `ui/src/pages/Alerts.tsx` |
| State store (Zustand) | `ui/src/store/alertStore.ts` |
| Types (bridge + UI) | `ui/src/types/alert.ts` (re-exports from `ui/src/types/api.ts`, which re-maps from `ui/src/generated/api.ts`) |
| HTTP services | `ui/src/services/alertsApi.ts`, `ui/src/services/backendApi.ts` |

### Pipeline steps used by the UI

`AnalysisProgressDisplay.tsx` hard-codes the 4-step list the backend emits:

```ts
const analysisSteps = [
  { key: 'pre_triage',                label: 'Pre-triage',            order: 1 },
  { key: 'workflow_builder',          label: 'Workflow Builder',      order: 2 },
  { key: 'workflow_execution',        label: 'Workflow Execution',    order: 3 },
  { key: 'final_disposition_update',  label: 'Final Disposition',     order: 4 },
];
```

When the current step is `workflow_builder` and a `WorkflowGeneration` exists
for the analysis, the component renders a nested `WorkflowGenerationProgress`
panel showing the 4 generation stages.

### Status badge mapping (alert-facing status)

The mapping should follow the backend values (`new | in_progress | completed |
failed | cancelled`). Example:

```ts
const analysisStatusConfig = {
  new:         { label: 'New',        class: 'bg-gray-700 text-gray-300',           icon: null },
  in_progress: { label: 'Analyzing',  class: 'bg-blue-900 text-blue-300 animate-pulse', icon: 'spinner' },
  completed:   { label: 'Completed',  class: 'bg-green-900 text-green-300',         icon: 'check' },
  failed:      { label: 'Failed',     class: 'bg-red-900 text-red-300',             icon: 'error' },
  cancelled:   { label: 'Cancelled',  class: 'bg-dark-700 text-gray-400',           icon: 'x' },
};
```

The filter checkbox UI in `AlertFilters` uses its own keys
(`not_analyzed / analyzing / analyzed / analysis_failed`, see
`ui/src/types/alert.ts`) that map onto the canonical backend statuses at
query time.

## Polling Strategy

Implemented in `ui/src/store/alertStore.ts`.

1. The UI polls `GET /alerts/{id}/analysis/progress` after `startAnalysis` and
   also whenever the details page mounts for an alert in `in_progress`.
2. Polling continues while `progress.status` is `running` or `paused`.
3. **Adaptive interval**:
   - `running` → **2 seconds**
   - `paused` (waiting on workflow generation) → **10 seconds**
4. On transition to `completed` or `failed`, polling stops and the store
   refetches the alert + analyses list once (skipped if the alert already
   reflects the terminal state).
5. `AnalysisStatus="paused_human_review"` follows the HITL flow documented in
   `docs/specs/HumanInTheLoop.md`; resuming is driven by a Slack interaction,
   not UI polling. TBD — verify whether the UI needs its own stall timer for
   the HITL case.

### Quick reference: lifecycle

```
new ──[POST /analyze]──► in_progress
        │
        │  AnalysisStatus transitions (internal):
        │    running → (Step 2 miss) → paused
        │            │
        │            └─ WorkflowGeneration runs the 4 stages
        │                ↓ on completion, resume-paused-alerts fires
        │    paused  → running → … → completed / failed
        │
        ▼
  completed │ failed │ cancelled
```
