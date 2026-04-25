# Workflow Type Validation Requirements

## Overview

This guide covers workflow type-checking and validation. All workflows must pass validation before execution. Covers all validation requirements, common errors, and resolutions.

## Three Critical Requirements

###1. Entry Node Requirement

**Rule:** Every workflow MUST have **exactly ONE** entry node marked with `is_start_node: true`.

**Valid Entry Node:**
```json
{
  "node_id": "entry",
  "kind": "transformation",  // OR "task"
  "name": "Workflow Entry",
  "is_start_node": true,
  "node_template_id": "system_identity"  // For transformation
  // OR "task_id": "task_cy_name"  // For task
}
```

**Entry Node Constraints:**
- **Kind:** Must be `transformation` OR `task` (NOT `foreach`)
- **Reference:** Must have `node_template_id` (transformation) OR `task_id` (task)
- **Purpose:** Receives workflow input and distributes to downstream nodes

❌ **Common Errors:**

**Error: "Workflow must have exactly one entry node"**
```json
// Missing is_start_node
{
  "nodes": [
    {"node_id": "n1", "kind": "transformation"}  // No is_start_node!
  ]
}
```

**Fix:** Add `is_start_node: true` to first node:
```json
{
  "nodes": [
    {
      "node_id": "n1",
      "kind": "transformation",
      "is_start_node": true  // ✅ Added
    }
  ]
}
```

**Error: "Multiple entry nodes found"**
```json
// Two nodes marked as entry
{
  "nodes": [
    {"node_id": "n1", "is_start_node": true},
    {"node_id": "n2", "is_start_node": true}  // ❌ Duplicate!
  ]
}
```

**Fix:** Keep only ONE entry node:
```json
{
  "nodes": [
    {"node_id": "n1", "is_start_node": true},  // ✅ Entry
    {"node_id": "n2", "is_start_node": false}  // ✅ Regular node
  ]
}
```

### 2. Input Schema Requirement

**Rule:** Workflow `io_schema.input` MUST define `properties` with concrete field definitions.

❌ **Invalid** (bare object):
```json
{
  "io_schema": {
    "input": {"type": "object"}  // Too permissive, no properties!
  }
}
```

✅ **Valid** (explicit properties):
```json
{
  "io_schema": {
    "input": {
      "type": "object",
      "properties": {
        "alert_id": {"type": "string"},
        "source_ip": {"type": "string"},
        "username": {"type": "string"}
      },
      "required": ["alert_id"]  // Optional but recommended
    }
  }
}
```

**Why This Matters:**

Concrete schemas enable:
- Type validation across workflow
- Early error detection
- Schema inference for downstream nodes
- Better IDE/tooling support

❌ **Common Errors:**

**Error: "io_schema.input must define 'properties' field"**
```json
{"io_schema": {"input": {"type": "object"}}}
```

**Fix:** Add properties with field definitions:
```json
{
  "io_schema": {
    "input": {
      "type": "object",
      "properties": {
        "data": {"type": "object"}  // At minimum, define one property
      }
    }
  }
}
```

**Error: "properties cannot be empty object"**
```json
{
  "io_schema": {
    "input": {
      "type": "object",
      "properties": {}  // ❌ Empty!
    }
  }
}
```

**Fix:** Define at least one property:
```json
{
  "io_schema": {
    "input": {
      "type": "object",
      "properties": {
        "data": {"type": "object"}  // ✅ At least one field
      }
    }
  }
}
```

### 3. Data Samples Requirement

**Rule:** Workflows MUST provide at least **one** `data_sample` that conforms to the input schema.

❌ **Invalid:**
```json
{
  "data_samples": []  // Empty array
}
```

```json
{
  "data_samples": null  // Null
}
```

✅ **Valid:**
```json
{
  "data_samples": [
    {
      "alert_id": "AL-12345",
      "source_ip": "192.168.1.100",
      "username": "jsmith"
    }
  ]
}
```

**Why This Matters:**

Data samples enable:
- Quick testing without manual input
- Validation that schema matches real data
- Example-driven development
- Type inference validation

❌ **Common Errors:**

**Error: "data_samples must be a non-empty list"**
```json
{"data_samples": []}
```

**Fix:** Add at least one sample:
```json
{
  "data_samples": [
    {"alert_id": "AL-001", "source_ip": "192.168.1.1"}
  ]
}
```

**Error: "data_samples[0] does not match io_schema.input"**
```json
// Schema expects alert_id, source_ip
{
  "io_schema": {
    "input": {
      "type": "object",
      "properties": {
        "alert_id": {"type": "string"},
        "source_ip": {"type": "string"}
      },
      "required": ["alert_id"]
    }
  },
  // Sample missing required field
  "data_samples": [
    {"source_ip": "192.168.1.1"}  // ❌ Missing alert_id!
  ]
}
```

**Fix:** Ensure sample matches schema:
```json
{
  "data_samples": [
    {
      "alert_id": "AL-001",  // ✅ Included
      "source_ip": "192.168.1.1"
    }
  ]
}
```

## Two-Tier Validation

Workflows have a `status` field indicating validation state:

### Status Values

**draft** - Created but not yet type-checked
- Workflow exists but hasn't been validated
- Can be edited
- Cannot be executed

**validated** - Type-checked and valid
- Passed all validation checks
- Ready for execution

**invalid** - Has type errors
- Failed validation
- Shows specific error messages
- Must be fixed before execution

### Validation Process

**Automatic Validation (compose_workflow):**

`compose_workflow` automatically validates during creation:
```json
{
  "composition": ["identity", "task1"],
  "name": "My Workflow",
  "tenant": "default"
}
```

Returns validation results immediately.

**Manual Validation (compose_workflow):**

After creating with `compose_workflow`, validate explicitly:

```bash
POST /v1/default/workflows/{workflow_id}/validate
```

Returns:
```json
{
  "status": "validated",  // or "invalid"
  "errors": [],  // Empty if valid
  "warnings": []
}
```

## Type Checking Errors

### Error: "Type mismatch between node outputs and inputs"

**Cause:** Task output type doesn't match downstream task input type.

**Example:**
```
Node1 outputs: {"type": "string"}
Node2 expects: {"type": "object"}
```

**Fix:**
1. Check task schemas with `get_task`
2. Add transformation node between incompatible types
3. Or update task to match expected types

### Error: "Fan-in node missing aggregation"

**Cause:** Multiple nodes feed into single node without merge/collect.

❌ **Wrong:**
```json
{
  "composition": [
    "identity",
    ["task1", "task2"],
    "analysis_task"  // ❌ No aggregation!
  ]
}
```

✅ **Correct:**
```json
{
  "composition": [
    "identity",
    ["task1", "task2"],
    "merge",  // ✅ Aggregates results
    "analysis_task"
  ]
}
```

### Error: "Unreachable nodes detected"

**Cause:** Node has no path from entry node.

**Example:**
```
Entry → Node1 → Node2
Node3 (orphaned, no incoming edges)
```

**Fix:** Connect all nodes to the workflow or remove orphaned nodes.

### Error: "Cycle detected in workflow"

**Cause:** Workflow has circular dependencies (not a DAG).

**Example:**
```
Node1 → Node2 → Node3 → Node1 (cycle!)
```

**Fix:** Remove backwards edge to make it acyclic.

## Common Validation Patterns

### Pattern 1: Minimal Valid Workflow

```json
{
  "name": "Minimal Workflow",
  "description": "Simplest valid workflow",
  "io_schema": {
    "input": {
      "type": "object",
      "properties": {"data": {"type": "object"}}
    },
    "output": {"type": "object"}
  },
  "data_samples": [{"data": {}}],
  "created_by": "user",
  "nodes": [
    {
      "node_id": "entry",
      "kind": "transformation",
      "name": "Entry",
      "is_start_node": true,
      "node_template_id": "system_identity"
    }
  ],
  "edges": []
}
```

### Pattern 2: Simple Pipeline

```json
{
  "composition": [
    "identity",
    "task1",
    "task2"
  ],
  "name": "Pipeline",
  "description": "Sequential task execution",
  "tenant": "default"
}
```

**Validation Checks:**
✅ Entry node: `identity`
✅ Input schema: Inferred from `task1`
✅ Data samples: Auto-generated or must be provided
✅ Type compatibility: `task1.output` matches `task2.input`

### Pattern 3: Fan-in with Merge

```json
{
  "composition": [
    "identity",
    ["task1", "task2"],
    "merge",
    "task3"
  ],
  "name": "Fan-in",
  "description": "Parallel tasks merged",
  "tenant": "default"
}
```

**Validation Checks:**
✅ Entry node: `identity`
✅ Fan-out: `task1` and `task2` receive same input
✅ Merge: Combines `task1` and `task2` outputs
✅ Type compatibility: Merged output matches `task3` input

## Debugging Validation Errors

### Step 1: Read Error Message

Validation provides detailed error messages with context:

```json
{
  "status": "invalid",
  "errors": [
    {
      "error_type": "missing_entry_node",
      "message": "Workflow must have exactly one entry node with is_start_node=True",
      "context": {"node_count": 3, "entry_nodes_found": 0}
    }
  ]
}
```

### Step 2: Identify Root Cause

Common root causes:
- **Missing entry node:** No `is_start_node=True`
- **Bare schema:** No `properties` field
- **Missing samples:** Empty or null `data_samples`
- **Type mismatch:** Incompatible task types
- **Missing aggregation:** Fan-in without merge/collect

### Step 3: Fix and Re-validate

For `compose_workflow`: Just re-run with fixes.

For `compose_workflow`:
1. Update workflow definition
2. POST to `/workflows/{id}/validate`
3. Check new status

## Best Practices

### 1. Always Define Concrete Schemas

❌ Avoid:
```json
{"io_schema": {"input": {"type": "object"}}}
```

✅ Prefer:
```json
{
  "io_schema": {
    "input": {
      "type": "object",
      "properties": {
        "alert_id": {"type": "string"},
        "data": {"type": "object"}
      },
      "required": ["alert_id"]
    }
  }
}
```

### 2. Provide Realistic Data Samples

❌ Avoid:
```json
{"data_samples": [{}]}
```

✅ Prefer:
```json
{
  "data_samples": [
    {
      "alert_id": "AL-DEMO-001",
      "source_ip": "192.168.1.100",
      "username": "jsmith",
      "timestamp": "2026-04-26T10:00:00Z"
    }
  ]
}
```

### 3. Use compose_workflow for Automatic Validation

Instead of manual node/edge creation, use `compose_workflow` for built-in validation.

### 4. Test with Sample Data

After validation, test execution with provided data_samples:

```bash
POST /v1/default/workflows/{workflow_id}/run
{
  "input_data": <use_first_data_sample>
}
```

## Validation Checklist

Before submitting workflow:

- [ ] Exactly ONE entry node with `is_start_node: true`
- [ ] Entry node is `transformation` OR `task` (not `foreach`)
- [ ] Input schema has non-empty `properties` field
- [ ] At least one `data_sample` provided
- [ ] Data samples match input schema
- [ ] All nodes reachable from entry node
- [ ] No cycles in workflow (is a DAG)
- [ ] Fan-in nodes have aggregation (merge/collect)
- [ ] Type compatibility verified across edges

Run validation and confirm `status: "validated"`.

## See Also

- **data_flow_envelopes.md** - Understanding fan-in data structures
