# Workflows Domain Knowledge

## What Are Workflows

Workflows are DAG-based (Directed Acyclic Graph) orchestrations that chain multiple tasks and transformations together. A workflow defines a blueprint that can be executed multiple times with different inputs. They are the primary mechanism for building multi-step investigation and automation pipelines.

## Workflow Structure

A workflow consists of:
- **Metadata**: name, description, tenant_id, status, is_dynamic
- **io_schema**: JSON Schema defining input and output types. Input must be `{"type": "object", "properties": {...}, "required": [...]}` -- bare `{"type": "object"}` is not allowed.
- **data_samples**: Required list of sample inputs that validate against io_schema.input. Used for testing and validation.
- **Nodes**: Units of work within the workflow
- **Edges**: Connections defining data flow between nodes

### Workflow Statuses
- **draft**: Created but not yet validated
- **validated**: Passed DAG structure check and type propagation
- **invalid**: Has validation errors

### Ephemeral Workflows
Workflows can be marked as ephemeral (`is_ephemeral=true`) with an expiration time. These are typically auto-generated for one-time alert analysis and are cleaned up after expiration.

## Node Types

### Task Nodes (`kind: "task"`)
Execute a saved task's Cy script. Reference a task via `task_id` (which points to component.id). The task's input/output is determined by its data_samples and script analysis.

### Transformation Nodes (`kind: "transformation"`)
Execute a code template (NodeTemplate) for data manipulation. Three system templates are available:
- **system_identity** (ID: 00000000-0000-0000-0000-000000000001): Passthrough -- forwards input unchanged. Used as the entry node to distribute workflow input.
- **system_merge** (ID: 00000000-0000-0000-0000-000000000002): Merges multiple inputs into one object.
- **system_collect** (ID: 00000000-0000-0000-0000-000000000003): Collects multiple inputs into an array (for foreach aggregation).

### Foreach Nodes (`kind: "foreach"`)
Iterates over a list, executing child nodes for each item. Configuration stored in `foreach_config` with item_index, item_key, and total_items tracking.

## Entry Node Requirement

Every workflow must have exactly one entry node with `is_start_node=true`. This node receives the workflow input and distributes it to downstream nodes. The entry node must be kind="transformation" (typically using the identity template) or kind="task".

## Edges

Edges connect nodes and define data flow:
- **edge_id**: Logical identifier within the workflow (e.g., "e1", "e2")
- **from_node_uuid** / **to_node_uuid**: Database UUIDs of the connected WorkflowNode records
- **alias**: Optional label for the edge

The workflow must form a valid DAG (no cycles). This is validated on creation and can be re-validated on demand.

## Type System

Workflows have a type propagation system that infers and validates types across the DAG:

1. **Input types flow forward**: The workflow's io_schema.input is propagated through the entry node to downstream nodes.
2. **Node schemas**: Each node has a `schemas` JSONB field storing inferred_input, inferred_output, type_checked status, and validated_at timestamp.
3. **Type validation**: The validate-types endpoint checks type safety without persisting. The apply-types endpoint validates and persists type annotations.

## Workflow Composition

The compose endpoint provides a simplified way to build workflows:
- Accepts an array of cy_names, shortcuts, or nested arrays
- Automatically resolves tasks, infers schemas, creates nodes and edges
- Returns errors, warnings, questions (for ambiguous choices), and a composition plan
- Optional `execute=true` flag to immediately run the composed workflow

## Workflow Execution

### Starting Execution
Execute a workflow by submitting input_data and optional execution_context.
Returns 202 Accepted with workflow_run_id. Response includes Location header for polling.

### Workflow Run Statuses
- **pending**: Created, not yet started
- **running**: Actively executing nodes
- **completed**: All nodes finished successfully
- **failed**: One or more nodes failed
- **cancelled**: User cancelled the run
- **paused**: Waiting for HITL response (Project Kalymnos)

### Execution Model
1. WorkflowRun record is created (status: pending -> running)
2. Entry node receives workflow input, creates WorkflowNodeInstance
3. Node instances execute in topological order respecting the DAG
4. For task nodes: creates a TaskRun, executes the Cy script, stores output
5. For transformation nodes: runs the template code, produces output
6. For foreach nodes: iterates over list, creates child node instances per item
7. Edge instances track data delivery between nodes
8. When all nodes complete, the WorkflowRun is marked completed and output is stored

### LLM Usage Tracking
Workflow runs track aggregate LLM token usage in execution_context["_llm_usage"]:
```json
{"input_tokens": 1234, "output_tokens": 567, "total_tokens": 1801, "cost_usd": 0.05}
```

## Common User Questions

### "How do I create a workflow?"
Create a workflow with name, io_schema (input/output schemas), data_samples, nodes array, and edges array. Each workflow needs exactly one entry node (is_start_node=true). See the **api** skill for endpoint details.

### "What tasks can I use in a workflow?"
List available tasks to see component_ids that you reference as task_id in workflow nodes.

### "How do I run a workflow?"
Execute the workflow with `{"input_data": {...}}` matching the workflow's io_schema.input. Poll the status endpoint for progress.

### "Why did my workflow fail?"
Check the execution graph to see which nodes succeeded, failed, or were skipped. Failed nodes include error_message.

### "Can I cancel a running workflow?"
Yes. The cancel endpoint stops the run and any pending nodes. Returns 204 on success.

### "What is the compose endpoint?"
A shortcut for building workflows. Instead of manually defining nodes and edges, you provide an array of task cy_names and it wires everything together with correct types and templates. Example: `{"composition": ["geoip_lookup", "virustotal_check"], "name": "IP Investigation"}`.

## Workflow Execution Graph

The execution graph endpoint returns a materialized view of the execution showing:
- All node instances with their status, timing, input/output data
- Edge instances showing data delivery between nodes
- A summary counting nodes by status (pending, running, completed, failed, cancelled)
- Whether the graph is complete (all nodes finished)

This is designed for visualization: render each node as a box with status color, connect with edges, show data flow.

## Validation Details

On-demand validation performs:
1. **DAG validation**: Checks for cycles in the node graph using DFS. Invalid graphs are rejected.
2. **Entry node check**: Exactly one node must have is_start_node=true. It must be kind="transformation" or kind="task".
3. **Type propagation**: Infers input/output types for each node based on the workflow io_schema and node schemas. Reports type mismatches as warnings or errors.
4. **Data sample validation**: Validates data_samples against io_schema.input using JSON Schema validation.

After validation, the workflow status is updated to "validated" or "invalid".

## Best Practices for Workflow Design

- Always provide data_samples that match io_schema.input -- they are required for creation and used for testing
- Use the identity template as the entry node to distribute workflow input to downstream task nodes
- Use the merge template when multiple nodes need to combine their outputs
- Use the collect template before foreach nodes to aggregate results
- Keep workflows focused -- prefer smaller, composable workflows over large monolithic ones
- Use `?validate=true` on creation to catch type errors early

## Data Retention

Workflow run data (workflow_runs, workflow_node_instances, workflow_edge_instances) is partitioned by created_at. Default retention is 90 days.
