# Terminology

Every domain term used across the docs and codebase, with a precise one-sentence definition and a link to the canonical implementation. Verified against the source.

## Alerts and detection

| Term | Definition | Canonical location |
|------|------------|-------------------|
| **Alert** | A security event normalized to OCSF Detection Finding shape, stored with column-level filterable fields and JSONB containers for the rest. | [`models/alert.py:33`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/models/alert.py#L33) |
| **OCSF Detection Finding** | Open Cybersecurity Schema Framework Detection Finding v1.8.0 (class 2004) — the canonical event class Analysi normalizes alerts to. | [`schemas/ocsf/detection_finding.py`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/schemas/ocsf/detection_finding.py) |
| **Disposition** | A classification record (category, subcategory, priority 1–10) attached to an alert as the verdict of an investigation. | [`models/alert.py:318`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/models/alert.py#L318) |
| **Detection rule** | The vendor-side rule that produced the alert; extracted from `ocsf.finding_info.analytic.name` and stored as `Alert.rule_name`. The key Analysi uses to look up workflows. | [`alert_ingest.py:175`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/integrations/framework/alert_ingest.py#L175) |
| **Analysis Group** | A grouping of alerts by `rule_name` (one per detection rule per tenant); the join target between detection rules and routing rules. | [`models/kea_coordination.py:14`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/models/kea_coordination.py#L14) |

## Investigation primitives

| Term | Definition | Canonical location |
|------|------------|-------------------|
| **Task** | An executable unit of Cy script (with optional LLM config) that can run standalone or as a node in a workflow. See **Cy language** below. | [`models/task.py:27`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/models/task.py#L27) |
| **Workflow** | A static DAG blueprint of nodes (Tasks, transformations, foreach loops) and edges (data flow), instantiated as a `WorkflowRun` for execution. | [`models/workflow.py:30`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/models/workflow.py#L30) |
| **Cy language** | Compiled-to-Python-bytecode DSL for orchestrating integration actions and LLM calls; Tasks are written in Cy. See the [Cy language tutorial](https://github.com/open-analysi/cy-language/blob/main/docs/TUTORIAL.md) and [Cy in Analysi](../concepts/cy-language.md) for what Analysi adds on top. | [`mcp/tools/cy_tools.py:5`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/mcp/tools/cy_tools.py#L5) |

## Execution records

| Term | Definition | Canonical location |
|------|------------|-------------------|
| **TaskRun** | A single execution of a Task; can be ad-hoc (no `task_id`) or part of a workflow (via `workflow_run_id`). | [`models/task_run.py:23`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/models/task_run.py#L23) |
| **WorkflowRun** | A single execution of a Workflow blueprint; partitioned by `created_at`; owns its child TaskRuns. | [`models/workflow_execution.py:17`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/models/workflow_execution.py#L17) |
| **JobRun** | An audit record created when a Schedule fires; bridges scheduled triggers to the resulting TaskRun or WorkflowRun. | [`models/job_run.py:20`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/models/job_run.py#L20) |
| **Schedule** | A row in the `schedules` table with a `target_type` (`task`/`workflow`) and `next_run_at`, polled every 30 s by the integrations worker and enqueued to the alerts worker. | [`models/schedule.py:19`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/models/schedule.py#L19) |

## Events and rules

| Term | Definition | Canonical location |
|------|------------|-------------------|
| **Control Event** | A transactional outbox entry on the event bus, consumed by rules that dispatch Tasks/Workflows or by hardcoded handlers (`human:responded`). | [`models/control_event.py:24`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/models/control_event.py#L24) |
| **Alert Routing Rule** | Auto-generated mapping `analysis_group → workflow_id` written as a side effect of workflow generation; one per detection rule the system has processed. | [`models/kea_coordination.py:140`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/models/kea_coordination.py#L140) |
| **Event Reaction Rule** | User-configured rule matching on disposition control events; fans out to side effects (Slack, Jira, SIEM ticket update, page on-call). | [`routers/control_event_rules.py`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/routers/control_event_rules.py) |

## Integrations

| Term | Definition | Canonical location |
|------|------------|-------------------|
| **Integration** | A directory with a `manifest.json` that declares one or more archetypes and one or more actions, plus `IntegrationAction` subclasses that implement them. | [`framework/models.py:94`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/integrations/framework/models.py#L94) |
| **Archetype** | A category (e.g. SIEM, EDR, ThreatIntel) declaring which capabilities an integration implements; 27 archetypes defined in the `Archetype` enum. | [`framework/models.py:14`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/integrations/framework/models.py#L14) |
| **Action** | An `async execute()` method on an `IntegrationAction` subclass with declared input/output schemas in the manifest; callable from Cy as `app::{integration}::{action}()`. | [`framework/base.py:21`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/integrations/framework/base.py#L21) |

## Knowledge

| Term | Definition | Canonical location |
|------|------------|-------------------|
| **Knowledge Unit (KU)** | A reusable knowledge artifact with a `ku_type` discriminator (`table`, `document`, `tool`, `index`); referenced by Tasks and Workflows. | [`models/knowledge_unit.py:22`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/models/knowledge_unit.py#L22) |
| **Skill** | A Knowledge Module of `module_type = "skill"` — a namespaced container of knowledge documents (with a root `SKILL.md`) loaded into the runtime for agentic workflows. | [`models/knowledge_module.py:25`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/models/knowledge_module.py#L25) |
| **Content Pack** | A directory with a `manifest.json` plus subdirectories for tasks, workflows, skills, KUs, KDG edges, and control event rules; installed via `analysi packs install <name>`. | [`content/foundation/manifest.json`](https://github.com/open-analysi/analysi-app/blob/main/content/foundation/manifest.json) |

## "Tool" — three meanings, one word

The term **Tool** appears in three distinct senses in the codebase. Match the meaning to the context:

| Sense | What it is | Where it lives |
|-------|-----------|---------------|
| **KU subtype** *(canonical user-facing meaning)* | A Knowledge Unit with `ku_type = "tool"` — a callable referenced from agentic workflows, with input/output schemas, auth, and rate-limit metadata. | [`models/knowledge_unit.py:196`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/models/knowledge_unit.py#L196) |
| **MCP tool** | A function exposed by Analysi's MCP server (cy_tools, schema_tools, task_tools, workflow_tools) for use by external AI clients authoring workflows. | [`mcp/tools/`](https://github.com/open-analysi/analysi-app/tree/main/src/analysi/mcp/tools) |
| **Integration action** *(informal usage)* | An action exposed by an integration (e.g. `pull_alerts`, `lookup_ip`) — sometimes called a "tool action" in code comments. | [`framework/base.py:92`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/integrations/framework/base.py#L92) |
