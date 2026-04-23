# Human-in-the-Loop (HITL)

The HITL system (Project Kalymnos) enables automated workflows to pause, ask a human a question (via Slack), wait for the answer, and resume execution with the human's response. This is used when automation cannot make a decision alone -- for example, asking a security analyst whether to escalate an alert or approve a remediation action.

## Three-Layer Pause Propagation

When a HITL question is triggered, the pause propagates upward through three layers:

1. **TaskRun** -- The Cy script interpreter pauses at the hi-latency tool call. `TaskRun.status` becomes `"paused"`.
2. **WorkflowNodeInstance** -- If the task runs inside a workflow, the containing node instance also pauses. `WorkflowNodeInstance.status` becomes `"paused"`.
3. **AlertAnalysis** -- If the workflow is part of an alert analysis pipeline, the analysis pauses too. `AlertAnalysis.status` becomes `"paused_human_review"`.

This ensures that the entire execution chain is correctly marked as waiting for human input, and no upstream process tries to finalize results while a question is outstanding.

## The ask_question_channel Cy Function

The HITL pause is triggered when a Cy script calls a hi-latency tool -- specifically `app::slack::ask_question_channel` (or `app::slack::ask_question` for DMs). These tools are marked with `hi_latency: true` in the Slack integration manifest.

Parameters:
- `destination` -- Slack channel (e.g., `#security-ops` or channel ID `C1A1A1AAA`)
- `question` -- The question text to display
- `responses` -- Comma-separated button labels (e.g., `"Approve, Reject, Escalate"`). Maximum 5 buttons.

When the Cy interpreter encounters a hi-latency tool call, it does NOT execute the tool itself. Instead:
1. The interpreter saves its current state (variables, completed steps, pending tool arguments) into an `ExecutionCheckpoint`.
2. A row is inserted into the `hitl_questions` table with status `"pending"`.
3. The backend sends the Slack message (via `send_hitl_question`) with Block Kit buttons.
4. The `question_ref` column is updated with the Slack `message_ts` so incoming button clicks can be matched back.
5. The task run status is set to `"paused"` and pause propagates upward.

The key detail: `pending_tool_result` is `None` at pause time. The tool has not executed -- the backend handles message delivery separately.

## Resume Flow

When a human clicks a button in Slack:

1. The Slack listener (Socket Mode) receives the interaction payload.
2. The handler matches the click to a pending question via `(message_ts, channel_id)` = `(question_ref, channel)`.
3. The question row is updated: `status` -> `"answered"`, `answer` set to the button value, `answered_by` set to the Slack user ID, `answered_at` set to current time.
4. A `human:responded` control event is emitted with the answer payload.
5. The control event bus picks up the event and triggers the resume handler.
6. The resume handler loads the `ExecutionCheckpoint`, injects the human's answer as `pending_tool_result`, and restarts the Cy interpreter from the checkpoint.
7. The interpreter replays completed steps from the memoized cache (no LLM re-calls), then continues execution past the hi-latency tool with the answer.
8. TaskRun, WorkflowNodeInstance, and AlertAnalysis statuses are updated back to `"running"`.

## Memoized Replay

The `ExecutionCheckpoint` stores:
- `node_results` -- outputs from already-completed workflow nodes
- `pending_tool_args` -- arguments of the hi-latency tool that caused the pause
- `variables` -- Cy interpreter variable state at pause time

On resume, completed nodes are replayed from cache. The LLM is not re-invoked for steps that already succeeded. This means resume is fast and deterministic -- only the remaining steps after the pause point require new computation.

## Question Tracking

The `hitl_questions` table tracks all HITL interactions. It is monthly-partitioned by `created_at`.

Key columns:
- `id`, `created_at` -- composite primary key (partitioned)
- `tenant_id` -- multi-tenant isolation
- `question_ref` -- Slack `message_ts` (set after message is posted)
- `channel` -- Slack channel ID
- `question_text` -- the question displayed to the human
- `options` -- JSONB array of button options
- `status` -- lifecycle: `"pending"` -> `"answered"` | `"expired"`
- `answer` -- the selected button value (null until answered)
- `answered_by` -- Slack user ID who clicked the button
- `answered_at` -- timestamp of the answer
- `timeout_at` -- deadline for answering (default: 4 hours from creation)
- `task_run_id`, `workflow_run_id`, `node_instance_id`, `analysis_id` -- links to paused execution (no foreign keys due to partitioning)

## Timeout and Expiry

Questions that are not answered within the timeout period are automatically expired by the reconciliation job:

- The reconciliation cron runs every 10 seconds.
- It finds `hitl_questions` rows where `status = "pending"` and `timeout_at < now()`.
- Expired questions have their status set to `"expired"`.
- The associated TaskRun, WorkflowNodeInstance, and AlertAnalysis are marked as failed with an appropriate error message.
- The default timeout is 4 hours (`HITLQuestionConstants.DEFAULT_TIMEOUT_HOURS`).

## Audit Trail

HITL answers are logged as `hitl.question_answered` activity audit events, capturing who answered, what they answered, and when. This provides a complete audit trail for compliance and investigation.

## Common User Questions

- "How do I add a human approval step to a workflow?" -- Use the `app::slack::ask_question_channel` tool in your Cy script. Provide the channel, question, and response options. The workflow will automatically pause and resume when answered.
- "What happens if nobody answers?" -- The question expires after 4 hours (configurable). The task and any parent workflow/analysis are marked as failed.
- "Can I ask questions via Microsoft Teams?" -- Teams HITL support is planned but not yet implemented. Currently only Slack is supported.
- "Does resume re-run the entire workflow?" -- No. Completed steps are replayed from cache (memoized). Only the remaining steps after the pause point execute.
