# Tasks Domain Knowledge

## What Are Tasks

Tasks are reusable units of work in Analysi. Each task executes a Cy script -- a Python-like language that can call LLMs, query integrations, manipulate data, and produce structured output. Tasks are the building blocks of workflows and can also run standalone.

## Task Structure

A task is composed of two linked records:

### Component (shared metadata)
- **id**: UUID, the public-facing task identifier (this is component.id, used in all API calls)
- **tenant_id**: Tenant scope
- **name**: Human-readable task name
- **description**: What the task does
- **cy_name**: Script-friendly identifier for Cy references (e.g., `geoip_lookup`, `virustotal_check`). Must match `^[a-zA-Z_][a-zA-Z0-9_]*$`.
- **version**: Semantic version string (default "1.0.0")
- **status**: `enabled` or `disabled`
- **visible**: Whether the task appears in user-facing lists
- **system_only**: If true, task cannot be modified or deleted by users
- **app**: Application group (default "default")
- **categories**: Array of category tags (e.g., ["enrichment", "threat_intel"])
- **created_by**: UUID of the creating user
- **last_used_at**: Timestamp of last execution

### Task (execution details)
- **script**: The Cy script source code
- **directive**: Natural language instruction for the task (used by AI agents when building workflows)
- **function**: Task function type: summarization, data_conversion, extraction, reasoning, planning, visualization, search
- **scope**: Task scope: input, processing, output
- **mode**: `saved` (persistent) or `ad_hoc` (one-time execution)
- **schedule**: Optional cron expression for scheduled execution
- **data_samples**: Sample input/output for testing and type inference
- **llm_config**: JSON configuration for LLM calls (model, temperature, etc.)
- **last_run_at**: Timestamp of the most recent execution

## Cy Language Overview

Cy is a Python-like scripting language that compiles to Python bytecode. It provides a safe, sandboxed execution environment for tasks.

### Key Features
- Python-like syntax with familiar control flow (if/else, for, while)
- Built-in functions: sum, len, keys, join, str, int, float, etc.
- Variable assignment and data manipulation
- String interpolation and formatting

### Tool Calling
Cy scripts call external tools using fully qualified names (FQNs):
- **Built-in tools**: `sum()`, `len()`, `keys()`, `join()`, etc.
- **Native tools**: `native::llm_run(...)`, `native::store_artifact(...)`, `native::enrich_alert(...)`
- **Integration tools**: `app::virustotal::ip_reputation(ip="1.2.3.4")`, `app::shodan::host_lookup(ip="...")`

### Script Analysis
The platform can statically analyze Cy scripts to extract:
- **tools_used**: List of tool FQNs referenced in the script
- **external_variables**: Variables referenced but not defined in the script
- **errors**: Syntax errors if any

## Task Execution

### Saved Task Execution
Execute a saved task with input data. Returns 202 Accepted with a task run ID (trid).

### Ad-hoc Execution
Execute an ad-hoc Cy script with input data. No saved task needed. Creates a one-time task run.

### Task Run Lifecycle
```
Created -> Running -> Completed (with output)
                   \-> Failed (with error)
                   \-> Paused (HITL, waiting for human)
```

### Task Run Statuses
- **pending**: Created, waiting to start
- **running**: Currently executing
- **completed**: Finished successfully with output
- **failed**: Execution error occurred
- **paused**: Waiting for human-in-the-loop response (HITL)

### Task Run Record
Each execution creates a TaskRun with:
- **id**: UUID (also called trid in API)
- **task_id**: Reference to saved task (null for ad-hoc)
- **workflow_run_id**: If running within a workflow
- **workflow_node_instance_id**: Specific node instance in workflow
- **cy_script**: Script that was executed (stored for ad-hoc runs)
- **status**: Current execution status
- **duration**: Execution time interval
- **started_at** / **completed_at**: Timing
- **input_type** / **input_location**: Where input data is stored (inline or s3)
- **output_type** / **output_location**: Where output data is stored
- **executor_config**: Execution parameters (timeout, etc.)
- **execution_context**: Runtime context (cy_name, analysis_id, etc.)

### Output Storage
Task output is stored either inline (for small results, under 512KB) or in object storage (S3) for larger results. The output_type field indicates which.

### Artifacts
Tasks can produce artifacts during execution (via `store_artifact()`). Artifacts are stored in the artifacts table with metadata including type, content, and association to the task run.

### Execution Logs
Cy scripts can emit log entries via `log()`. These are persisted as execution_log artifacts and retrievable via the task run logs endpoint.

## Common User Questions

### "How do I create a task?"
Create a task with name, description, script (Cy code), directive, function type, and data_samples. The cy_name is auto-generated from the name if not provided. See the **api** skill for endpoint details.

### "How do I run a task?"
For a saved task, execute it with `{"input": {...}}`. For ad-hoc, provide `{"cy_script": "...", "input": {...}}`. Both return 202 with a trid for tracking.

### "How do I check if a task finished?"
Poll the task run status endpoint. When status is "completed" or "failed", the run is done.

### "Can I delete a task that's used in a workflow?"
No. The API returns 409 with a list of workflows using the task. Use the check-delete endpoint first to see if it's safe.

### "What tools can my Cy script call?"
Use the integration tools listing to see all available tools (built-in + native + integration tools) with their FQNs and parameter schemas.

### "How do I see what a task produced?"
Get the task run for full details. For enrichment data specifically use the enrichment endpoint. For log output use the logs endpoint.

## Task Categories and Functions

Tasks are classified by function type and categories:

### Function Types
- **summarization**: Produces summaries of data (alert summaries, investigation reports)
- **data_conversion**: Transforms data between formats
- **extraction**: Extracts specific fields or entities from unstructured data
- **reasoning**: Makes analytical judgments (risk scoring, threat assessment)
- **planning**: Creates action plans or investigation strategies
- **visualization**: Produces visual representations of data
- **search**: Queries external sources for information

### Categories
Categories are free-form string tags assigned to tasks (e.g., "enrichment", "threat_intel", "compliance", "incident_response"). The list endpoint supports filtering by categories with AND semantics -- a task must have all specified categories to match.

## System Tasks

Some tasks are marked as `system_only=true`. These are platform-provided tasks that:
- Cannot be modified by users (PUT returns 403)
- Cannot be deleted by users (DELETE returns 403)
- Provide core functionality (e.g., alert triage, disposition assignment)
- Are visible in task listings but protected from changes

## Task and Workflow Integration

Tasks are referenced in workflows by their component_id (the public task ID). When a task is used in a workflow:
- The task's Cy script runs within the workflow execution context
- Input comes from the upstream node's output (routed through edges)
- Output is passed to downstream nodes
- A TaskRun is created linked to both the task and the workflow_run_id/workflow_node_instance_id

A task cannot be deleted if it is used by any workflow. Use the check-delete endpoint to verify before attempting deletion.

## LLM Configuration

Tasks that call LLMs can specify configuration in the `llm_config` JSONB field:
- **model**: Which model to use (e.g., "gpt-4o", "claude-sonnet-4-20250514")
- **temperature**: Sampling temperature
- **max_tokens**: Maximum output tokens
- Other provider-specific parameters

The actual LLM call is made through the native::llm_run tool or integration AI tools.

## Data Retention

Task run data is partitioned by created_at. Default retention is 90 days, managed by pg_partman.
