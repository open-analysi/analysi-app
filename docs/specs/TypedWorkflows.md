+++
version = "1.0"
status = "active"

[[changelog]]
version = "1.0"
summary = "Parametric type checking for workflows (Project Rodos)"
+++

# Typed Workflows (Rodos) - Specification v1

## Overview

The Rodos system introduces **parametric type checking** for workflows, enabling automated validation and composition of cybersecurity analysis workflows. This specification defines a type system that allows AI agents to compose workflows from well-typed Tasks and NodeTemplates, with immediate feedback on type compatibility.

## Core Vision

Our vision centers on creating a robust system for building and validating Cyber Security Analysis workflows where:

1. **Tasks are domain-specific**: Each task addresses a specific cybersecurity challenge with precise input/output schemas
2. **Type propagation is automatic**: Given an initial input schema, the system infers all node types throughout the workflow
3. **Validation provides actionable feedback**: Type errors include clear suggestions for agents to iteratively refine workflows
4. **Templates provide reusable patterns**: A small set of parametric NodeTemplates handle common data flow patterns

## Design Principles

### 1. Single-Input Constraint (with v5 Deprecation Path)

**Recommended Pattern**: All workflow nodes should accept exactly ONE input (type `T`), with two explicit exceptions:
- **Merge** nodes: Combine multiple object inputs
- **Collect** nodes: Aggregate multiple inputs into arrays

**Backward Compatibility (v5 Legacy)**:
For compatibility with existing workflows, nodes with multiple inputs will continue to execute using the v5 automatic aggregation mechanism (receiving `[{node_id, result}, ...]`). However, type validation will emit a **deprecation warning** recommending migration to explicit Merge/Collect nodes.

**Deprecation Timeline**:
- **Current (v6.0)**: v5 multi-input pattern supported with warnings
- **Future (v7.0)**: v5 automatic aggregation will be removed; only Merge/Collect will accept multiple inputs

**Rationale**: Simplifies type propagation, makes data flow explicit, and improves workflow clarity while maintaining backward compatibility.

### 2. Duck Typing for Compatibility

Type compatibility uses **structural typing** (duck typing): if an object has the required fields with compatible types, it satisfies the schema.

**Example**:
```
Required schema: {"name": "string", "age": "number"}
Actual input: {"name": "Alice", "age": 30, "email": "alice@example.com"}
Result: ✓ Compatible (has required fields, extra fields allowed)
```

### 3. Explicit Start Nodes

Workflows designate start nodes explicitly via `WorkflowNode.is_start_node: bool` field. All start nodes receive the workflow's input schema.

### 4. Manual Type Validation

Type checking is **opt-in**: workflows execute by default without validation. Designers/agents explicitly request validation via API endpoint, allowing iterative refinement.

### 5. Task Output Schemas

Tasks use duck typing for input validation via Cy type inference. Output schemas can be:
- **Explicitly declared**: Designer specifies `output_schema`
- **Automatically inferred**: Cy type inference analyzes the task's script to generate schema

**Input Validation**: When type propagation passes a schema to a task, Cy's `infer_output_schema()` is called. If Cy inference succeeds, the input is compatible (duck typing). If it fails, a type error is reported.

## Workflow Creation Requirements

To ensure type safety and enable proper validation, all workflows must meet the following requirements at creation time:

### 1. Entry Node Requirement

**Rule**: Every workflow MUST have exactly ONE entry node marked with `is_start_node: true`.

**Entry Node Constraints**:
- **Kind**: Must be `transformation` OR `task` (not `foreach`)
- **Reference**:
  - Transformation nodes must reference a `node_template_id` (typically an identity/passthrough template)
  - Task nodes must reference a `task_id`
- **Purpose**: The entry node receives the workflow input and distributes it to downstream nodes

**Rationale**: Explicit entry points make data flow unambiguous and enable type propagation to start from a single, well-defined input schema.

**Example 1 - Transformation Entry Node**:
```json
{
  "node_id": "entry",
  "kind": "transformation",
  "name": "Workflow Entry Point",
  "is_start_node": true,
  "node_template_id": "00000000-0000-0000-0000-000000000001",  // system identity template
  "schemas": {}
}
```

**Example 2 - Task Entry Node**:
```json
{
  "node_id": "initial-check",
  "kind": "task",
  "name": "Initial Security Check",
  "is_start_node": true,
  "task_id": "550e8400-e29b-41d4-a716-446655440000",  // reference to a task
  "schemas": {}
}
```

**Validation Errors**:
```
❌ No entry node: "Workflow must have exactly one entry node with is_start_node=True"
❌ Multiple entry nodes: "Workflow must have exactly one entry node, found 2: ['entry1', 'entry2']"
❌ Wrong node type: "Entry node 'start' must be kind='transformation' or kind='task'. Found kind='foreach'"
❌ Missing template: "Entry node 'start' with kind='transformation' must reference a NodeTemplate via node_template_id"
❌ Missing task: "Entry node 'check' with kind='task' must reference a Task via task_id"
```

### 2. Input Schema Requirements

**Rule**: Workflow `io_schema.input` MUST define a `properties` field with concrete property definitions.

**Invalid** (bare object):
```json
{
  "io_schema": {
    "input": {"type": "object"},  // ❌ Too permissive - no properties defined
    "output": {"type": "object"}
  }
}
```

**Valid** (explicit properties):
```json
{
  "io_schema": {
    "input": {
      "type": "object",
      "properties": {
        "ip": {"type": "string"},
        "context": {"type": "string"}
      },
      "required": ["ip", "context"]  // Optional but recommended
    },
    "output": {"type": "object"}
  }
}
```

**Rationale**: Explicit schemas enable:
- **Type propagation**: Cy can infer which input fields tasks can access
- **Validation**: Catch typos like `input["ip_addres"]` vs `input["ip_address"]`
- **Documentation**: Clear API contracts for workflow consumers

**Validation Error**:
```
❌ "io_schema.input must define 'properties'. Bare {'type': 'object'} is not allowed.
   Example: {'type': 'object', 'properties': {'ip': {'type': 'string'}}, 'required': ['ip']}"
```

### 3. Data Samples Requirement

**Rule**: Workflows MUST provide at least one valid `data_sample` that conforms to the input schema.

**Purpose**:
- **Testing**: Validate workflows can handle real input structures
- **Documentation**: Show example usage
- **Type checking**: Verify input schema is realistic

**Example**:
```json
{
  "name": "IP Threat Analysis Workflow",
  "io_schema": {
    "input": {
      "type": "object",
      "properties": {
        "ip": {"type": "string"},
        "port": {"type": "number"}
      },
      "required": ["ip", "port"]
    },
    "output": {"type": "object"}
  },
  "data_samples": [
    {"ip": "192.168.1.100", "port": 443},
    {"ip": "10.0.0.50", "port": 80, "protocol": "http"}  // Extra fields allowed (duck typing)
  ]
}
```

**Validation using JSON Schema**:
- Each `data_samples[i]` is validated against `io_schema.input`
- Uses `jsonschema` library for validation
- Provides detailed error messages showing which sample failed and why

**Validation Errors**:
```
❌ Missing field: "data_samples must be a non-empty list of sample inputs"
❌ Empty array: "data_samples must contain at least one sample input"
❌ Schema mismatch: "data_samples[0] does not match io_schema.input: 'port' is a required property"
```

### 4. Two-Tier Validation Status

Workflows track validation state through a `status` field with three values:

#### Status Values

**`draft`** (default):
- Workflow has been created but not type-checked
- May have type errors (unknown until validation)
- Safe to modify and iterate
- **Transitions**: Set when workflow is created or types are cleared

**`validated`**:
- Type propagation completed successfully
- All node connections are type-safe
- Workflow output schema has been inferred
- **Transitions**: Set when `apply_workflow_types()` succeeds

**`invalid`**:
- Type validation detected errors
- Contains validation errors in workflow metadata
- Cannot be executed until fixed
- **Transitions**: Set when type propagation fails

#### Validation Workflow

```
1. Create workflow → status = "draft"
   POST /api/v1/workflows

2. (Optional) Validate types → status unchanged, returns errors/warnings
   POST /api/v1/workflows/{id}/validate-types
   {
     "initial_input_schema": {...}
   }

3. Apply validated types → status = "validated" (if successful)
   POST /api/v1/workflows/{id}/apply-types
   {
     "initial_input_schema": {...}
   }
   - Persists inferred schemas to database
   - Updates workflow.io_schema.output with inferred output
   - Sets workflow.status = "validated"

4. Clear types → status = "draft"
   POST /api/v1/workflows/{id}/clear-types
   - Removes inferred type annotations
   - Resets workflow to draft state
```

#### Example Lifecycle

```json
// 1. Create workflow
{
  "id": "wf-123",
  "name": "IP Analysis",
  "status": "draft",  // Initial state
  "io_schema": {
    "input": {
      "type": "object",
      "properties": {"ip": {"type": "string"}},
      "required": ["ip"]
    },
    "output": {"type": "object"}  // Not yet inferred
  },
  "data_samples": [{"ip": "1.2.3.4"}],
  "nodes": [...]
}

// 2. Apply types (validation succeeds)
{
  "id": "wf-123",
  "name": "IP Analysis",
  "status": "validated",  // Type-checked and safe
  "io_schema": {
    "input": {
      "type": "object",
      "properties": {"ip": {"type": "string"}},
      "required": ["ip"]
    },
    "output": {  // Inferred from terminal nodes
      "type": "object",
      "properties": {
        "threat_score": {"type": "number"},
        "verdict": {"type": "string"}
      }
    }
  },
  "nodes": [
    {
      "node_id": "analyze",
      "schemas": {
        "inferred_input": {"type": "object", "properties": {"ip": {"type": "string"}}},
        "inferred_output": {"type": "object", "properties": {"threat_score": {"type": "number"}}},
        "type_checked": true,
        "validated_at": "2026-04-26T20:15:00Z"
      }
    }
  ]
}
```

#### Database Schema

```sql
ALTER TABLE workflows
ADD COLUMN status TEXT NOT NULL DEFAULT 'draft'
CHECK (status IN ('draft', 'validated', 'invalid'));
```

**Migration**: `V001__baseline.sql`

## NodeTemplate Catalog (MVP)

The MVP includes **3 core templates**, with 2 deferred for future phases:

### 1. Identity Template

**Signature**: `T => T`

**Purpose**: Pass-through node that forwards input unchanged.

**Type Rule**: Output type = Input type

**Use Case**: Explicit data forwarding, workflow readability

**Example**:
```json
{
  "kind": "transformation",
  "node_template_id": "identity-template-uuid",
  "input_type": {"type": "object", "properties": {"ip": {"type": "string"}}},
  "output_type": {"type": "object", "properties": {"ip": {"type": "string"}}}
}
```

### 2. Merge Template

**Signature**: `[{result: T1}, {result: T2}, ...] => {...T1, ...T2}`

**Purpose**: Combine multiple object inputs into a single merged object.

**Input Constraint**: ONLY accepts multiple inputs (violates single-input rule explicitly)

**Type Rules**:
1. **All inputs must be objects** - Error if any input is primitive/array
2. **Shared fields must have matching types** - Error on type conflict
3. **Empty objects are identity** - Merging `{}` with `{"a": 1}` yields `{"a": 1}`
4. **Array fields concatenate** - Merging `{"tags": ["a"]}` with `{"tags": ["b"]}` yields `{"tags": ["a", "b"]}`

**Use Case**: Fan-in for consolidating parallel data sources

**Example**:
```json
Input 1: {"ip": "1.2.3.4", "threat_score": 85}
Input 2: {"ip": "1.2.3.4", "geo_location": "US"}
Output: {"ip": "1.2.3.4", "threat_score": 85, "geo_location": "US"}
```

**Error Example**:
```json
Input 1: {"status": 200}        // status is number
Input 2: {"status": "success"}  // status is string
Error: "Cannot merge: field 'status' has incompatible types (number vs string)"
```

### 3. Collect Template

**Signature**: `[{result: T1}, {result: T2}, ...] => [T1, T2, ...]`

**Purpose**: Aggregate multiple inputs into a single array.

**Input Constraint**: ONLY accepts multiple inputs (violates single-input rule explicitly)

**Type Rules**:
1. **Heterogeneous types allowed** - Output type is `[T1 | T2 | ...]` union
2. **Envelope structure removed** - Extracts `result` field from each input
3. **Order preserved** - Array order matches workflow edge order

**Use Case**: Fan-in for batch processing, parallel result gathering

**Example**:
```json
Input 1 (Node A): {"verdict": "malicious", "confidence": 0.95}
Input 2 (Node B): {"verdict": "clean", "confidence": 0.87}
Input 3 (Node C): {"verdict": "suspicious", "confidence": 0.62}
Output: [
  {"verdict": "malicious", "confidence": 0.95},
  {"verdict": "clean", "confidence": 0.87},
  {"verdict": "suspicious", "confidence": 0.62}
]
```

### Deferred Templates (Future Phases)

#### 4. Projection Template (Deferred)

**Future Signature**: `T => U` (with transformation logic)

**Purpose**: Filter/transform object fields using Cy-based expressions

**Deferred Because**: Requires design of projection language (likely Cy subset)

#### 5. Branching Template (Deferred)

**Future Signature**: `T => T` (conditional routing)

**Purpose**: Conditional workflow paths based on input properties

**Deferred Because**: Requires condition language design (likely Cy expressions)

## Type Propagation Algorithm

### Input

1. **Workflow definition**: Nodes, edges, NodeTemplate/Task references
2. **Initial input schema**: JSON Schema for workflow input
3. **Start node designation**: `WorkflowNode.is_start_node = true` for entry points

### Process

```
1. Identify start nodes (where is_start_node = true)
2. Apply initial input schema to all start nodes
3. Topologically sort workflow DAG
4. For each node in topological order:
   a. Determine predecessor count
   b. If single predecessor:
      - Input type = predecessor's output type
   c. If multiple predecessors:
      - Validate node is Merge or Collect (error otherwise)
      - Input = array of predecessor outputs
   d. Infer output type:
      - If Task node: Call Cy infer_output_schema(task.script, input_schema)
      - If Template node: Apply template-specific type rules
   e. Store inferred schemas in WorkflowNode.schemas:
      {
        "input": {...},
        "output_result": {...},
        "type_checked": true
      }
5. Aggregate terminal node types for workflow output schema
6. Return validation result (success or error list)
```

### Output

**Success**:
```json
{
  "status": "valid",
  "nodes": [
    {
      "node_id": "n1",
      "inferred_input": {"type": "object", ...},
      "inferred_output": {"type": "object", ...}
    },
    ...
  ],
  "workflow_output": {"type": "object", ...}
}
```

**Failure**:
```json
{
  "status": "invalid",
  "errors": [
    {
      "node_id": "n2",
      "error_type": "single_input_violation",
      "message": "Node 'analyze_data' (kind: task) has 3 incoming edges but only Merge/Collect nodes support multiple inputs.",
      "suggestion": "Insert a Merge or Collect node to combine predecessors."
    },
    {
      "node_id": "n3",
      "error_type": "type_mismatch",
      "message": "Expected input with field 'ip: string', actual output has 'ip: number'",
      "suggestion": "Check predecessor node output schema or add transformation."
    }
  ]
}
```

## Node Output Wrapper & Type Propagation Scope

### The Node Output Wrapper

During workflow execution, the system wraps **all** node outputs in an execution metadata structure (referred to as the "Node Output Wrapper"):

```json
{
  "node_id": "unique-node-identifier",
  "context": {...},
  "description": "Human-readable description",
  "result": <ACTUAL_TASK_OR_TEMPLATE_OUTPUT>
}
```

**Critical**: This wrapper is **transparent to the type system**. The wrapper itself is always an object containing execution metadata, but the `result` field can be **any JSON type** (string, number, boolean, array, object, or null).

### Type Propagation Operates on `result` Only

When this specification refers to:
- **"Node output schema"** → The schema of the `result` field
- **"Type propagation"** → Inference and validation of `result` field schemas
- **"Node input"** → The next node receives the unwrapped `result` value

**Example**:
```javascript
// Task Cy script
output = "Hello World"
```

**Actual execution output** (with wrapper):
```json
{
  "node_id": "greeting_node",
  "context": {...},
  "description": "Generated greeting",
  "result": "Hello World"  ← This is a string
}
```

**Schema propagated to next node**: `{"type": "string"}` (schema of `result` field only)

**Next node receives as input**: Just the unwrapped string: `"Hello World"`

### Tasks and Templates Operate on Unwrapped Values

- **Task input**: Receives the `result` value from predecessor (not the full wrapper)
- **Task output**: The `output` variable in Cy becomes the `result` field value
- **Template input**: Receives `result` value(s) from predecessor(s)
- **Template output**: The template's computed output becomes the `result` field value

### Wrapper Handling Rules

1. **Single predecessor**: Wrapper contains the `result` field with actual data
   ```json
   {
     "node_id": "n1",
     "context": {...},
     "description": "...",
     "result": {"ip": "1.2.3.4"}  // Actual task output
   }
   ```

2. **Multiple predecessors** (Merge/Collect only):
   Workflow execution collects all predecessor wrappers, then Merge/Collect templates extract and process the `result` fields:
   ```json
   // What Merge/Collect templates receive (array of predecessor wrappers)
   [
     {"node_id": "n1", "context": {...}, "result": {"ip": "1.2.3.4"}},
     {"node_id": "n2", "context": {...}, "result": {"geo": "US"}}
   ]

   // Templates extract result fields: [{"ip": "1.2.3.4"}, {"geo": "US"}]
   // Then apply template logic (merge → {...} or collect → [...])
   ```

3. **Type propagation ignores wrappers**: Type inference operates on `result` field schemas only, never on the wrapper structure

### Terminology Clarification

To avoid confusion throughout this specification:

- **Node Output Wrapper**: The execution metadata structure `{node_id, context, description, result}`
- **Task/Template Output**: The actual data produced by node logic (stored in `result` field)
- **Type Propagation**: The inference algorithm that operates exclusively on `result` field schemas

**Note on v5 compatibility**: In v5, nodes with multiple predecessors received an implicit "aggregation format" (array of `{node_id, result}` objects). In Rodos v6, this implicit behavior is **replaced** by explicit Merge/Collect templates. Only these two template types can accept multiple inputs.

## Database Schema Changes

### 1. WorkflowNode - Add Start Node Designation

```sql
ALTER TABLE workflow_nodes
ADD COLUMN is_start_node BOOLEAN DEFAULT false NOT NULL;

CREATE INDEX idx_workflow_nodes_start
ON workflow_nodes(workflow_id)
WHERE is_start_node = true;
```

### 2. NodeTemplate - Add Template Kind

```sql
ALTER TABLE node_templates
ADD COLUMN kind TEXT DEFAULT 'identity' NOT NULL;

CREATE INDEX idx_node_templates_kind ON node_templates(kind);
```

Valid `kind` values: `'identity'`, `'merge'`, `'collect'`, `'projection'` (future), `'branching'` (future)

### 3. Task - Add Output Schema

```sql
ALTER TABLE task
ADD COLUMN output_schema JSONB DEFAULT NULL;

-- Add validation that output_schema is null or valid JSON object
ALTER TABLE task
ADD CONSTRAINT task_output_schema_is_object_or_null
CHECK (output_schema IS NULL OR jsonb_typeof(output_schema) = 'object');

-- Add comment
COMMENT ON COLUMN task.output_schema IS
'Optional JSON Schema defining task output structure. If NULL, output schema is inferred via Cy type inference.';
```

- `output_schema`: Optional JSON Schema; if NULL, will be inferred via Cy type inference
- **No input_schema**: Tasks use duck typing - Cy inference validates input compatibility implicitly

### 4. Workflow - Type Checking Status (Optional for MVP)

```sql
ALTER TABLE workflows
ADD COLUMN type_checked BOOLEAN DEFAULT false,
ADD COLUMN type_errors JSONB DEFAULT NULL;
```

## API Endpoints

### Validate Workflow Types

**Endpoint**: `POST /api/v1/workflows/{workflow_id}/validate-types`

**Request**:
```json
{
  "initial_input_schema": {
    "type": "object",
    "properties": {
      "alert_id": {"type": "string"},
      "ip_address": {"type": "string"}
    },
    "required": ["alert_id", "ip_address"]
  }
}
```

**Response (Success)**:
```json
{
  "status": "valid",
  "nodes": [
    {
      "node_id": "start",
      "kind": "task",
      "inferred_input": {...},
      "inferred_output": {...}
    },
    {
      "node_id": "merge_results",
      "kind": "transformation",
      "template_kind": "merge",
      "inferred_input": [...],
      "inferred_output": {...}
    }
  ],
  "workflow_output_schema": {
    "type": "object",
    "properties": {
      "verdict": {"type": "string"},
      "confidence": {"type": "number"}
    }
  }
}
```

**Response (Errors)**:
```json
{
  "status": "invalid",
  "errors": [
    {
      "node_id": "analyze_ip",
      "error_type": "type_mismatch",
      "message": "Node 'analyze_ip' expects input with field 'ip: string', but predecessor 'extract_data' outputs field 'ip_address: string'",
      "suggestion": "Add a Projection node to rename 'ip_address' to 'ip', or update task input schema",
      "expected_schema": {"type": "object", "properties": {"ip": {"type": "string"}}},
      "actual_schema": {"type": "object", "properties": {"ip_address": {"type": "string"}}}
    }
  ]
}
```

## Error Types Reference

### 1. Deprecated Multi-Input Pattern (Warning)

**When**: Non-Merge/Collect node has multiple incoming edges (v5 compatibility mode)

**Severity**: Warning (non-blocking)

**Example**:
```json
{
  "status": "valid_with_warnings",
  "warnings": [
    {
      "node_id": "process_data",
      "warning_type": "deprecated_multi_input",
      "severity": "medium",
      "message": "Node has 2 predecessors using deprecated v5 automatic aggregation. This pattern will be removed in v7.0.",
      "predecessor_count": 2,
      "current_behavior": "Node receives array: [{node_id, result}, {node_id, result}, ...]",
      "migration_suggestion": "Replace with explicit Merge node (for object merging) or Collect node (for array aggregation)"
    }
  ]
}
```

**Migration Path**:
```
Before (v5 pattern):
[Node A] ──┐
            ├──> [Task: Process]
[Node B] ──┘

After (v6 recommended):
[Node A] ──┐
            ├──> [Collect] ──> [Task: Process]
[Node B] ──┘
```

### 2. Single-Input Violation (Future - v7.0+)

**When**: Non-Merge/Collect node has multiple incoming edges (after v5 deprecation removal)

**Severity**: Error (blocking)

**Example**:
```
Error: Node 'analyze_threat' (kind: task) has 3 incoming edges but only Merge/Collect nodes support multiple inputs.

Suggestion: Insert a Merge node (if inputs are objects to combine) or Collect node (if creating array) before 'analyze_threat'.
```

**Note**: This error will only be enforced in v7.0+ after the deprecation period.

### 2. Type Mismatch

**When**: Predecessor output doesn't match successor input schema

**Example**:
```
Error: Edge 'fetch_ip_data' → 'analyze_text' has incompatible types.

Expected: object with field 'text: string'
Actual: object with field 'ip: string'

Suggestion: Check if wrong nodes are connected, or add transformation logic.
```

### 3. Merge Conflict

**When**: Merge node receives objects with same field but different types

**Example**:
```
Error: Merge node 'combine_results' has conflicting field types.

Field 'status':
  - Node 'check_ip': type 'number' (200)
  - Node 'check_domain': type 'string' ("success")

Suggestion: Ensure all merge inputs have compatible types for shared fields, or rename conflicting fields.
```

### 4. Invalid Template Input

**When**: Template receives wrong input type (e.g., Merge gets non-object)

**Example**:
```
Error: Merge node 'combine' received non-object input from 'fetch_count'.

Expected: object type for merging
Actual: number (42)

Suggestion: Use Collect node instead to create array, or fix predecessor to output object.
```

## Integration with Cy Language

### Task Output Inference

For tasks without explicit `output_schema`, the system uses Cy's type inference API:

```python
from cy_language.type_inference_api import infer_output_schema

# Get task script and input schema
task_script = task.script
input_schema = <inferred from predecessor or workflow input>

# Infer output schema
output_schema = infer_output_schema(
    code=task_script,
    input_schema=input_schema,
    tool_registry=<available Cy tools>
)
```

### Cy Type Inference Behavior

- **Returns JSON Schema** representing script output type
- **Handles `$input` variable**: Uses provided `input_schema` for `$input` type
- **Handles `$output` variable**: If script assigns to `$output`, returns its type
- **Handles `return` statements**: Aggregates all return types into union if multiple paths
- **Unknown/Any types**: Returns `{}` (empty schema) when types cannot be determined

**Example**:
```cy
# Task script
ip = $input.ip_address
threat_level = check_threat(ip)
output = {
  "ip": ip,
  "threat_level": threat_level,
  "analyzed_at": now()
}
```

**Input Schema**:
```json
{"type": "object", "properties": {"ip_address": {"type": "string"}}}
```

**Inferred Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "ip": {"type": "string"},
    "threat_level": {"type": "number"},
    "analyzed_at": {"type": "string"}
  }
}
```

## Workflow Output Handling

### Single Terminal Node

If workflow has one terminal node (no outgoing edges), workflow output = that node's output (envelope removed).

### Multiple Terminal Nodes

If workflow has N terminal nodes, workflow output is an object keyed by `node_id`:

```json
{
  "analyze_ip": {...},      // Terminal node 1 output
  "analyze_domain": {...},  // Terminal node 2 output
  "check_reputation": {...} // Terminal node 3 output
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "analyze_ip": <node output schema>,
    "analyze_domain": <node output schema>,
    "check_reputation": <node output schema>
  }
}
```

## Validation Workflow for AI Agents

Recommended agent workflow for building typed workflows:

```
1. Agent designs initial workflow structure (nodes + edges)
2. Agent calls POST /workflows to create workflow
3. Agent calls POST /workflows/{id}/validate-types with initial_input_schema
4. If validation succeeds:
   - Workflow is ready for execution
   - Agent can inspect inferred schemas for each node
5. If validation fails:
   - Agent receives error list with specific issues
   - Agent analyzes suggestions
   - Agent modifies workflow (add/remove/reconnect nodes)
   - Agent repeats step 3 (iterate until valid)
```

## Implementation Phases (High-Level)

The Rodos system will be implemented in **3 standalone phases**:

### Phase 27: Type System Foundation & Database Schema
- Implement parametric type system (type variables, unification, duck typing)
- Database migrations (WorkflowNode.is_start_node, NodeTemplate.kind, Task schemas)
- Core type propagation algorithm (without API)
- Unit tests for type operations

### Phase 28: NodeTemplate Type Rules & Cy Integration
- Implement Identity, Merge, Collect template type inference
- Integrate Cy `infer_output_schema()` for Task nodes
- Error reporter with actionable messages
- Integration tests with sample workflows

### Phase 29: Type Validation API & Runtime Enforcement
- `/workflows/{id}/validate-types` REST endpoint
- Store inferred schemas in WorkflowNode.schemas
- Update workflow execution to enforce single-input constraint at runtime
- End-to-end workflow validation tests

## Future Enhancements (Out of Scope for MVP)

1. **Projection Template**: Cy-based field filtering/transformation
2. **Branching Template**: Conditional routing with Cy expressions
3. **Transformation Template**: General Cy-based data transformation
4. **Type inference caching**: Cache inferred schemas to avoid re-computation
5. **Incremental validation**: Validate only changed portions of workflow
6. **Visual type indicators**: UI showing type flow through workflow graph
7. **Schema suggestions**: AI-powered suggestions for fixing type errors

## Design Decisions Summary

| Question | Decision | Rationale |
|----------|----------|-----------|
| **Merge field conflicts** | Error | Conflicts indicate design problems |
| **Merge empty objects** | `{} + {a:1} = {a:1}` | Empty object is identity |
| **Merge array fields** | Concatenate `[a] + [b] = [a,b]` | Intuitive for list aggregation |
| **Collect heterogeneity** | Allow `[T1\|T2\|...]` | Flexibility for mixed results |
| **Input schema storage** | `Workflow.io_schema.input` | Use existing field |
| **Validation trigger** | Manual/explicit | Opt-in for designer control |
| **Start node identification** | Explicit `is_start_node` bool | Clear, unambiguous |
| **Terminal output aggregation** | Object `{node_id: result}` | Matches runtime behavior |
| **Projection/Branching** | Defer to future | Needs language design |
| **Task input validation** | Duck typing via Cy inference | No explicit input_schema needed |
| **Task output schema** | Add `output_schema` | Optional, inferred if NULL |
| **Validation blocking** | Non-blocking | Workflows can execute without validation |
| **Error reporting** | All errors in list | Complete feedback for agents |

## References

- **Cy Language Type Inference**: [`cy_language/type_inference_api.py`](https://github.com/open-analysi/cy-language/blob/main/src/cy_language/type_inference_api.py) (in the `cy-language` repo)
- **Workflow Models**: `src/analysi/models/workflow.py`
- **Workflow Execution**: `src/analysi/services/workflow_execution.py`
- **Original Vision**: `PROJECT_RODOS.md` (to be replaced by this document)
