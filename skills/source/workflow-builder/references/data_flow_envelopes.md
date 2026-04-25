# Data Flow and Envelopes: Understanding Workflow Communication

## Overview

Workflows use a standardized envelope pattern for node-to-node communication. Understanding envelopes is critical for handling fan-in scenarios where multiple nodes feed into a single node.

## The Envelope Contract

Every node output follows this structure:

```json
{
  "node_id": "extract_ioc",
  "context": {},
  "description": "Extracted IOC from alert",
  "result": {
    "ip": "192.168.1.1",
    "domain": "malicious.com",
    "confidence": 0.95
  }
}
```

**Fields:**
- `node_id` (string) - Identifier of the node that produced this output
- `context` (object) - Optional metadata about execution
- `description` (string) - Human-readable description of what happened
- `result` (any) - **The actual data output from the node**

**Key Point:** The `result` field contains the actual data. Everything else is metadata.

## How Nodes Receive Input

### Single Predecessor (Simple Case)

When a node has **ONE** incoming edge:

**Task receives:** The `result` field content directly (simplified).

**Example:**

Node A outputs:
```json
{
  "node_id": "node_a",
  "result": {"ip": "192.168.1.1", "score": 85}
}
```

Node B (downstream) receives in task:
```cy
# Cy task code
ip_address = input["ip"]  // "192.168.1.1"
score = input["score"]     // 85

# input is simplified to just the result field
```

**Benefit:** Simple, intuitive access to predecessor data.

### Multiple Predecessors (Fan-in Case)

⚠️ **Important Inconsistency:** When a node has **MULTIPLE** incoming edges, the behavior changes.

**Task receives:** Array of predecessor objects, each with `node_id` and `result` fields.

**Example:**

Node A outputs:
```json
{
  "node_id": "node_a",
  "result": {"user_data": {"privilege": "admin"}}
}
```

Node B outputs:
```json
{
  "node_id": "node_b",
  "result": {"ip_data": {"reputation": "malicious"}}
}
```

Node C (downstream, receives from both A and B):
```cy
# Cy task code
results = input  // Array, NOT simplified!

# results structure:
# [
#   {"node_id": "node_a", "result": {"user_data": {...}}},
#   {"node_id": "node_b", "result": {"ip_data": {...}}}
# ]

# Must iterate and extract
for item in results {
    node_id = item["node_id"]
    data = item["result"]

    if (node_id == "node_a") {
        user_data = data["user_data"]
    } else if (node_id == "node_b") {
        ip_data = data["ip_data"]
    }
}
```

**Why the inconsistency?** Multiple predecessors need to be identifiable, so each keeps its `node_id` alongside its `result`.

## Handling Fan-in in Tasks

### Pattern 1: Merge Before Task (Recommended)

Use `merge` template to combine multiple object outputs into one:

```json
{
  "composition": [
    "identity",
    ["user_enrichment", "ip_enrichment"],
    "merge",  // Combines into single object
    "correlation_task"
  ]
}
```

**What merge does:**

Input to merge:
```json
[
  {"node_id": "user_enrichment", "result": {"user": "jsmith", "privilege": "admin"}},
  {"node_id": "ip_enrichment", "result": {"ip": "192.168.1.1", "reputation": "bad"}}
]
```

Output from merge:
```json
{
  "user": "jsmith",
  "privilege": "admin",
  "ip": "192.168.1.1",
  "reputation": "bad"
}
```

**correlation_task receives:**
```cy
# Simple, flat object
user = input["user"]
privilege = input["privilege"]
ip = input["ip"]
reputation = input["reputation"]
```

**Benefits:**
- Simple task code
- No iteration needed
- Clear field access

### Pattern 2: Collect Before Task

Use `collect` template to aggregate into array:

```json
{
  "composition": [
    "identity",
    ["source1", "source2", "source3"],
    "collect",  // Creates array
    "aggregation_task"
  ]
}
```

**What collect does:**

Input to collect:
```json
[
  {"node_id": "source1", "result": {"score": 85}},
  {"node_id": "source2", "result": {"score": 92}},
  {"node_id": "source3", "result": {"score": 78}}
]
```

Output from collect:
```json
[
  {"node_id": "source1", "result": {"score": 85}},
  {"node_id": "source2", "result": {"score": 92}},
  {"node_id": "source3", "result": {"score": 78}}
]
```

**aggregation_task receives:**
```cy
# Array of objects
results = input

total_score = 0
count = 0

for item in results {
    score = item["result"]["score"]
    total_score = total_score + score
    count = count + 1
}

average = total_score / count

output = {"average_score": average}
```

**When to use collect:**
- Unknown number of predecessors
- Need to aggregate/sum/average
- Want to preserve node_id information

### Pattern 3: Direct Fan-in (Advanced)

Task handles raw array directly without merge/collect:

```cy
# Task receiving multiple predecessors
predecessors = input  // Array of {node_id, result}

# Initialize accumulators
enrichment_data = {}

# Iterate and combine
for pred in predecessors {
    node_id = pred["node_id"]
    result = pred["result"]

    # Merge result into accumulator
    for key in keys(result) {
        enrichment_data[key] = result[key]
    }
}

# Now enrichment_data has all fields from all predecessors
output = enrichment_data
```

**When to use:**
- Custom aggregation logic
- Conditional processing based on node_id
- Complex merging rules

## merge vs collect: Decision Guide

### Use merge when:
- Combining object outputs
- Want flat structure with all fields
- Downstream task expects single object
- Example: Combining user data + IP data + endpoint data

### Use collect when:
- Creating array of results
- Need to iterate/aggregate
- Want to preserve node_id information
- Example: Collecting scores from multiple risk assessments

## Common Pitfalls

### Pitfall 1: Assuming Single-Predecessor Behavior

❌ **Wrong:**
```cy
# Fan-in task expecting simplified input
ip_address = input["ip"]  // Error! input is array, not object
```

✅ **Correct:**
```cy
# Check if array (multiple predecessors)
if (type(input) == "array") {
    # Handle fan-in
    for item in input {
        process(item["result"])
    }
} else {
    # Handle single predecessor
    process(input)
}
```

### Pitfall 2: Forgetting Aggregation Node

❌ **Wrong:**
```json
{
  "composition": [
    "identity",
    ["task1", "task2"],
    "analysis_task"  // Receives array, might not expect it!
  ]
}
```

✅ **Correct:**
```json
{
  "composition": [
    "identity",
    ["task1", "task2"],
    "merge",  // or "collect"
    "analysis_task"
  ]
}
```

### Pitfall 3: Using collect When You Need merge

❌ **Wrong:**
```json
// Task expects merged object
{
  "composition": [
    "identity",
    ["user_enrich", "ip_enrich"],
    "collect",  // Creates array
    "correlation"  // Expects {user_data: ..., ip_data: ...}
  ]
}
```

✅ **Correct:**
```json
{
  "composition": [
    "identity",
    ["user_enrich", "ip_enrich"],
    "merge",  // Creates merged object
    "correlation"
  ]
}
```

## Workflow Output Behavior

### Terminal Node = Workflow Output

The workflow's final `output_data` is the `result` field from the **terminal node** (node with no outgoing edges).

**Example:**

```json
{
  "composition": [
    "identity",
    "task1",
    "task2"  // Terminal node
  ]
}
```

**task2 outputs:**
```json
{
  "node_id": "task2",
  "result": {"risk_score": 95, "disposition": "critical"}
}
```

**Workflow output_data:**
```json
{
  "risk_score": 95,
  "disposition": "critical"
}
```

**Note:** Only the `result` field becomes workflow output, NOT the full envelope.

### Multiple Terminal Nodes

If multiple nodes have no outgoing edges, the **last one to complete** provides the output.

**Recommendation:** Design workflows with a single terminal node for predictable output.

## Testing Envelope Handling

### Test Single Predecessor

```bash
POST /v1/default/workflows/{workflow_id}/run
{
  "input_data": {"test": "data"}
}

# Check task receives simplified input
GET /v1/default/workflow-runs/{run_id}/nodes/{node_id}/output
```

### Test Fan-in

```bash
# Execute workflow with fan-in
POST /v1/default/workflows/{workflow_id}/run
{
  "input_data": {"alert_id": "AL-001"}
}

# Check fan-in node receives array
GET /v1/default/workflow-runs/{run_id}/nodes/{fan_in_node_id}/input

# Should see array structure:
# [
#   {"node_id": "pred1", "result": {...}},
#   {"node_id": "pred2", "result": {...}}
# ]
```

## Best Practices

### 1. Always Use Aggregation for Fan-in

Don't rely on tasks handling raw arrays. Use `merge` or `collect` explicitly.

### 2. Prefer merge for Data Enrichment

When combining enrichment data, `merge` produces simpler downstream code.

### 3. Use collect for Aggregation Operations

When summing, averaging, or collecting results, `collect` preserves structure.

### 4. Document Fan-in Handling

If task handles fan-in directly, document expected input structure in task description.

### 5. Test Both Paths

Test tasks in both single-predecessor and multi-predecessor scenarios.

## See Also

- **type_validation.md** - Validation requirements
