# Cy in Analysi

Cy is the scripting language Analysi uses to express Tasks. It's a small, sandboxed, AI-friendly DSL maintained as a separate project: **[open-analysi/cy-language](https://github.com/open-analysi/cy-language)**. The repo's [README](https://github.com/open-analysi/cy-language#readme) and [TUTORIAL](https://github.com/open-analysi/cy-language/blob/main/docs/TUTORIAL.md) are the canonical reference for syntax, the embedding API, native functions, and the pause/resume model.

This page only covers what Analysi adds on top — where the interpreter runs, the tools registered into it, and how Cy's pause checkpoints become long-running platform actions.

## Where Cy runs

Cy execution is driven by the `execute_task_run` ARQ job, registered on the **Alerts Worker** ([`alert_analysis/worker.py:67`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/alert_analysis/worker.py#L67)). The job calls `TaskExecutionService.execute_and_persist`, which builds the tool dictionary, constructs an interpreter, and runs the script. The construction site is [`services/task_execution.py:162`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/services/task_execution.py#L162):

```python
interpreter = await Cy.create_async(
    tools=tools, mcp_servers=mcp_servers, captured_logs=captured_logs
)
result = await interpreter.run_native_async(
    cy_script, input_data, checkpoint=checkpoint
)
```

A sync fallback (`Cy(tools=tools, mcp_servers=mcp_servers)` + `run_native`) exists for older Cy versions but is not the hot path.

Because Cy compiles scripts to Python bytecode, **the Alerts Worker container's Python version must match the version Cy was built against** — currently `python:3.13-slim` ([`deployments/docker/Dockerfile`](https://github.com/open-analysi/analysi-app/blob/main/deployments/docker/Dockerfile)). A mismatch surfaces as `invalid syntax` errors at runtime, not at build time.

## Tools registered into the interpreter

A Cy script can only call tools the host explicitly registers. `TaskExecutionService.execute` ([`task_execution.py:60`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/services/task_execution.py#L60)) assembles the tool dictionary from many loaders before constructing the interpreter:

| Loader | What it adds | Defined at |
|--------|-------------|-----------|
| `_load_tools` | Cy native functions registered in the cy-language `default_registry` (e.g. `len`, `sum`, `from_json`, `to_json`, `uppercase`, `lowercase`, `join`, `log`) | [`task_execution.py:300`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/services/task_execution.py#L300) |
| `_load_time_functions` | Time utilities | [`task_execution.py:736`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/services/task_execution.py#L736) |
| `_load_sleep_functions` | Sleep utility (job-lifecycle testing) | [`task_execution.py:757`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/services/task_execution.py#L757) |
| `_load_artifact_functions` | Artifact create/read/link helpers | [`task_execution.py:396`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/services/task_execution.py#L396) |
| `_load_llm_functions` | `llm_run`, `llm_evaluate_results`, `llm_summarize`, `llm_extract` — **override** cy-language defaults; route through Naxos integration actions (anthropic_agent, openai, gemini) ([`cy_llm_functions.py:656`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/services/cy_llm_functions.py#L656)) | [`task_execution.py:329`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/services/task_execution.py#L329) |
| `_load_ku_functions` | Knowledge Unit access (table / document) | [`task_execution.py:463`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/services/task_execution.py#L463) |
| `_load_index_functions` | Semantic search over indexes | [`task_execution.py:504`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/services/task_execution.py#L504) |
| `_load_task_functions` | Task composition (call other Tasks from inside a Cy script) | [`task_execution.py:648`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/services/task_execution.py#L648) |
| `_load_alert_functions` | Alert data access by tenant | [`task_execution.py:564`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/services/task_execution.py#L564) |
| `_load_enrichment_functions` | Helpers to attach enrichments to alerts | [`task_execution.py:600`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/services/task_execution.py#L600) |
| `_load_ocsf_helper_functions` | OCSF Detection Finding navigation helpers | [`task_execution.py:629`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/services/task_execution.py#L629) |
| `_load_app_tools` | **`app::{integration}::{action}`** — auto-generated from each enabled integration's `manifest.json`. FQN built at [`task_execution.py:855`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/services/task_execution.py#L855) as `f"app::{integration_type}::{short_name}"`. Tools whose short name collides with a Cy native are skipped. | [`task_execution.py:783`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/services/task_execution.py#L783) |
| `_load_ingest_functions` | Ingest + checkpoint helpers | [`task_execution.py:688`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/services/task_execution.py#L688) |
| `_configure_mcp_servers` | **`mcp::{server}::{tool}`** — loaded from MCP servers configured via the `MCP_SERVERS` environment variable (JSON). Returns `None` when unset; no MCP servers are hardcoded. | [`task_execution.py:1418`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/services/task_execution.py#L1418) |

The cy-language [README](https://github.com/open-analysi/cy-language#tool-namespaces) defines the namespace conventions — `app::` for application/integration tools, `mcp::` for MCP servers, native tools as flat or `str::*`/`list::*`/`json::*`/etc.

## HITL: how `hi_latency` becomes a Slack question

cy-language defines a generic mechanism: a tool registered with `hi_latency: True` causes the script to suspend when it's called, returning an `ExecutionPaused` checkpoint that the host stores and resumes later when the result arrives. See the cy-language [pause/resume](https://github.com/open-analysi/cy-language#pause-and-resume) docs for the language-level contract.

Analysi turns this generic mechanism into human-in-the-loop investigations driven by Slack: the Slack integration declares three `hi_latency` actions (`ask_question`, `ask_question_channel`, `get_response`); when the interpreter hits one, the backend posts the message, the Cy interpreter pauses, and a `human:responded` control event resumes it when the analyst replies. Pauses propagate up through `TaskRun`, `WorkflowNodeInstance`, and `AlertAnalysis`.

For the full mechanism — the Slack action params, the diagram, the `hitl_questions` table, three-layer propagation, memoised replay, and the timeout/reconciliation cron — see the dedicated **[Human-in-the-loop](hitl.md)** page.

## Authoring Cy from external clients (MCP)

Analysi's MCP server exposes a set of Cy authoring tools so external AI clients can compose, validate, and dry-run scripts against the live tool registry — without round-tripping through the API. The tools live in [`mcp/tools/cy_tools.py`](https://github.com/open-analysi/analysi-app/blob/main/src/analysi/mcp/tools/cy_tools.py):

| MCP tool | Purpose |
|----------|---------|
| `quick_syntax_check_cy_script` | Parse-only validation (no symbol/type checks) |
| `compile_cy_script` | Full compile + typecheck against the tenant's tool registry |
| `analyze_dependencies` | List tools and external variables a script references |
| `visualize_plan` | Inspect the compiled execution plan |
| `get_plan_stats` | Stats over the compiled plan |
| `list_all_active_tool_summaries` | Discover tools available at this tenant |
| `get_tool_details` | Detailed schema for specified tool FQNs |
| `execute_cy_script_adhoc` | Run a script as an ad-hoc TaskRun (calls the backend `/tasks/execute` endpoint, which enqueues `execute_task_run` on the Alerts Worker) |

These wrap the cy-language [`analyze_types`](https://github.com/open-analysi/cy-language#type-checking) and [`analyze_script`](https://github.com/open-analysi/cy-language#script-analysis) APIs and add the live tool registry as context.

## How Cy fits with Tasks and Workflows

- A **[Task](tasks.md)** is a saved Cy script plus IO schemas and metadata. The script's `input` variable is the Task's input payload.
- A **[Workflow](workflows.md)** orchestrates Tasks as a DAG; each Task node receives the upstream envelope as its `input`. Cy itself has no notion of the workflow — the Workflow Executor handles routing and the script just sees JSON in, JSON out.
