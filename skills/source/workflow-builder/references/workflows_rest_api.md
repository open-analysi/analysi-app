# Workflows Tutorial

This tutorial explains how to create, understand, and use workflows in Analysi. All examples have been verified against the actual implementation.

## Table of Contents
1. [Core Concepts](#core-concepts)
2. [Node Types](#node-types)
3. [Data Flow and Envelopes](#data-flow-and-envelopes)
4. [Creating Workflows](#creating-workflows)
5. [Working Examples](#working-examples)
6. [Testing Workflows](#testing-workflows)
7. [Common Patterns](#common-patterns)

## Core Concepts

### What is a Workflow?
A workflow is a directed acyclic graph (DAG) that defines a sequence of operations. Each workflow consists of:
- **Nodes**: Units of work (tasks or transformations)
- **Edges**: Directional connections that define data flow

### Key Principles
1. **Mutable DAGs**: Workflows can be edited after creation — add/remove nodes and edges via API or MCP tools
2. **Single Input/Output**: Each node has one input and one output
3. **Broadcast**: Node output is sent to ALL connected downstream nodes
4. **Envelope Pattern**: All nodes emit standardized envelopes

### Workflow Validation Requirements (Rodos)

All workflows must meet these requirements for type safety and validation:

#### 1. Entry Node Requirement
Every workflow MUST have **exactly ONE** entry node marked with `is_start_node: true`.

**Entry Node Constraints**:
- **Kind**: Must be `transformation` OR `task` (not `foreach`)
- **Reference**:
  - Transformation nodes must reference a `node_template_id`
  - Task nodes must reference a `task_id`
- **Purpose**: The entry node receives workflow input and distributes it to downstream nodes

```json
{
  "node_id": "entry",
  "kind": "transformation",
  "name": "Workflow Entry",
  "is_start_node": true,
  "node_template_id": "uuid-here",
  "schemas": {}
}
```

#### 2. Input Schema Requirement
Workflow `io_schema.input` MUST define `properties` with concrete field definitions.

**Invalid** (bare object):
```json
{
  "io_schema": {
    "input": {"type": "object"},  // ❌ Too permissive
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
      "required": ["ip"]
    },
    "output": {"type": "object"}
  }
}
```

#### 3. Data Samples Requirement
Workflows MUST provide at least one `data_sample` that conforms to the input schema.

```json
{
  "data_samples": [
    {"ip": "192.168.1.1", "context": "test"}
  ]
}
```

#### 4. Two-Tier Validation
Workflows have a `status` field indicating validation state:
- **draft**: Created but not yet type-checked
- **validated**: Type-checked and valid
- **invalid**: Has type errors

Type checking is performed via the `/workflows/{id}/validate` endpoint.

## Node Types

### 1. Transformation Nodes
Lightweight Python code that transforms data. Executed by the Workflow Execution Service.

```json
{
  "node_id": "extract_field",
  "kind": "transformation",
  "name": "Extract IP from Alert",
  "node_template_name": "extract_alert_ioc"
}
```

### 2. Task Nodes
Complex operations that may have side effects. Executed by the Task Execution Service.

```json
{
  "node_id": "analyze_ip",
  "kind": "task",
  "name": "IP Reputation Analysis",
  "task_name": "IP Reputation Analysis"
}
```

## Data Flow and Envelopes

### The Envelope Contract
Every node output follows this structure:

```json
{
  "node_id": "extract_ioc",
  "context": {},
  "description": "Extracted IOC from alert",
  "result": {
    "ip": "192.168.1.1",
    "context": "Suspicious activity detected"
  }
}
```

### How Nodes Receive Input

#### Single Predecessor
When a node has one predecessor, it receives the envelope and can access:
- `inp`: The `result` field content (simplified)
- `workflow_input`: The full envelope (when needed)

```python
# Template code example
# inp contains the actual data
ip_address = inp.get('ip')
# Or access the full envelope if needed
node_id = workflow_input.get('node_id')
```

#### Multiple Predecessors (Fan-in)
**⚠️ Important Inconsistency**: When a node has multiple predecessors, the behavior changes:
- `inp`: An array of predecessor objects, each with `node_id` and `result` fields
- `workflow_input`: The full envelope containing the array

This is **different** from the single predecessor case where `inp` is simplified. With multiple predecessors, you must access the `result` field of each predecessor explicitly:

```python
# inp is an array of predecessor objects (NOT simplified)
for predecessor in inp:
    node_id = predecessor['node_id']  # Identify which predecessor
    result = predecessor['result']    # Access the actual data
    # Process each predecessor's output
```

**Why this inconsistency?** Multiple predecessors need to be identifiable, so each keeps its `node_id` alongside its `result`. This allows your node to know which data came from which predecessor.

## Creating Workflows

### Step 1: Create Node Templates

```bash
# Create a passthrough template
curl -X POST "http://localhost:8001/v1/default/workflows/node-templates" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "passthrough",
    "description": "Pass input unchanged",
    "input_schema": {"type": "object"},
    "output_schema": {"type": "object"},
    "code": "return inp",
    "language": "python",
    "type": "static"
  }'
```

### Step 2: Create Tasks (if needed)

```bash
# Create an IP analysis task
curl -X POST "http://localhost:8001/v1/default/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "IP Reputation Analysis",
    "script": "# Cy script for IP analysis\n$ip = $input[\"ip\"]\n# Analysis logic here\n$output = {\"reputation\": \"clean\"}",
    "authored_by": "security_team"
  }'
```

### Step 3: Create the Workflow

```bash
curl -X POST "http://localhost:8001/v1/default/workflows" \
  -H "Content-Type: application/json" \
  -d @workflow_definition.json
```

## Working Examples

### Example 1: Simple Pipeline (Rodos-Compliant)
This example demonstrates a simple workflow that meets all Rodos requirements:

```json
{
  "name": "Simple IP Analysis Workflow",
  "description": "Simple workflow: normalize event and analyze IP",
  "is_dynamic": false,
  "io_schema": {
    "input": {
      "type": "object",
      "properties": {
        "ip": {"type": "string"},
        "context": {"type": "string"}
      },
      "required": ["ip"]
    },
    "output": {"type": "object"}
  },
  "created_by": "security_team",
  "data_samples": [
    {
      "ip": "192.168.1.1",
      "context": "Suspicious SSH activity"
    }
  ],
  "nodes": [
    {
      "node_id": "input_node",
      "kind": "transformation",
      "name": "Input Processor",
      "is_start_node": true,
      "node_template_name": "passthrough",
      "schemas": {}
    },
    {
      "node_id": "ip_analysis",
      "kind": "task",
      "name": "IP Reputation Analysis",
      "task_name": "IP Reputation Analysis",
      "schemas": {}
    }
  ],
  "edges": [
    {
      "edge_id": "e1",
      "from_node_id": "input_node",
      "to_node_id": "ip_analysis"
    }
  ]
}
```

**Key Rodos Features**:
- `is_start_node: true` on the entry node
- Input schema defines `properties` field
- `data_samples` provided for testing

### Example 2: Fan-out/Fan-in Pattern (Rodos-Compliant)
For alert analysis with multiple paths converging:

```json
{
  "name": "Alert Analysis Workflow",
  "description": "Analyze alerts with multiple enrichment paths",
  "io_schema": {
    "input": {
      "type": "object",
      "properties": {
        "alert_id": {"type": "string"},
        "primary_ioc_value": {"type": "string"},
        "alert_data": {"type": "object"}
      },
      "required": ["alert_id", "primary_ioc_value"]
    },
    "output": {"type": "object"}
  },
  "created_by": "security_team",
  "data_samples": [
    {
      "alert_id": "ALT-12345",
      "primary_ioc_value": "192.168.1.100",
      "alert_data": {"severity": "high", "source": "firewall"}
    }
  ],
  "nodes": [
    {
      "node_id": "preserve_alert",
      "kind": "transformation",
      "name": "Preserve Alert Data",
      "is_start_node": true,
      "node_template_name": "passthrough",
      "schemas": {}
    },
    {
      "node_id": "extract_ioc",
      "kind": "transformation",
      "name": "Extract IOC",
      "node_template_name": "extract_alert_ioc",
      "schemas": {}
    },
    {
      "node_id": "analyze_ip",
      "kind": "task",
      "name": "IP Analysis",
      "task_name": "IP Reputation Analysis",
      "schemas": {}
    },
    {
      "node_id": "determine_disposition",
      "kind": "task",
      "name": "Determine Disposition",
      "task_name": "Alert Disposition Reasoning",
      "schemas": {}
    }
  ],
  "edges": [
    {"edge_id": "e1", "from_node_id": "preserve_alert", "to_node_id": "determine_disposition"},
    {"edge_id": "e2", "from_node_id": "preserve_alert", "to_node_id": "extract_ioc"},
    {"edge_id": "e3", "from_node_id": "extract_ioc", "to_node_id": "analyze_ip"},
    {"edge_id": "e4", "from_node_id": "analyze_ip", "to_node_id": "determine_disposition"}
  ]
}
```

**Important**: The `determine_disposition` node receives data from TWO predecessors, so its task must handle an array input.

**Key Rodos Features**:
- `is_start_node: true` on the entry node (`preserve_alert`)
- Input schema with explicit `properties` defining expected alert fields
- `data_samples` with sample alert data

## Testing Workflows

### Using Data Samples
Workflows include sample data for easy testing. All API responses use the standard envelope (`{data, meta}`):

```bash
# Get workflow with samples (note: .data[] to unwrap response envelope)
curl -s "http://localhost:8001/v1/default/workflows" | \
  jq '.data[] | select(.name == "Alert Analysis Workflow") | .data_samples'

# View all workflows' samples
curl -s "http://localhost:8001/v1/default/workflows" | \
  jq '.data[] | {name: .name, sample_count: (.data_samples | length), data_samples: .data_samples}'
```

### 1. Start a Workflow

```bash
# Get workflow ID first (unwrap response envelope with .data[])
WORKFLOW_ID=$(curl -s "http://localhost:8001/v1/default/workflows" | jq -r '.data[0].id')

# Start execution with sample data or custom input
curl -X POST "http://localhost:8001/v1/default/workflows/$WORKFLOW_ID/run" \
  -H "Content-Type: application/json" \
  -d '{
    "input_data": {
      "ip": "185.220.101.45",
      "context": "SSH brute force attempt"
    }
  }'
```

**Important**: The `input_data` field accepts any JSON-serializable type:
- Objects/Dicts (most common)
- Arrays (for fan-in scenarios)
- Strings
- Numbers
- Booleans
- null

### 2. Check Status

```bash
# Get workflow run ID from response
WORKFLOW_RUN_ID="..."

# Check status
curl "http://localhost:8001/v1/default/workflow-runs/$WORKFLOW_RUN_ID/status"

# Get execution graph
curl "http://localhost:8001/v1/default/workflow-runs/$WORKFLOW_RUN_ID/graph"
```

## Common Patterns

### Pattern 1: Simple Pipeline
Input → Transform → Task → Output

Use when: You need sequential processing with no branching.

### Pattern 2: Fan-out
Input → [Task1, Task2, Task3]

Use when: Multiple independent operations on the same input.

### Pattern 3: Fan-in
[Node1, Node2] → Aggregation Node

Use when: Combining results from multiple sources.

### Pattern 4: Diamond
```
     → Branch1 →
Input            → Output
     → Branch2 →
```

Use when: Parallel processing paths that converge.

## Workflow Output Behavior

### Key Points About Workflow Output

1. **Output = Terminal Node's Result**
   - The workflow's `output_data` is the `result` field from the terminal node's envelope
   - NOT the full envelope - just the `result` content
   - Terminal nodes are nodes with no outgoing edges

2. **Output Can Be Any Type**
   - Object/Dict (most common)
   - Array (from fan-in aggregations)
   - Primitive (string, number, boolean, null)
   - The schema was updated to `Any | None` to support all cases

3. **Multiple Terminal Nodes**
   - If multiple nodes have no outgoing edges, the last one to complete provides the output
   - Design workflows with a single terminal node for predictable output

4. **Fan-in Output Pattern**
   - When using passthrough with multiple predecessors, output is an array
   - Each element has `{node_id: string, result: any}` structure
   - Order is not guaranteed

## Important Notes

### For Task Authors
When writing tasks that will be used in fan-in scenarios:

```python
# Cy script for handling multiple predecessors
$input_data = $input

# Check if input is an array (multiple predecessors)
$is_array = type($input_data) == "array"

if ($is_array) {
    # Handle multiple predecessors
    $i = 0
    while ($i < len($input_data)) {
        $pred = $input_data[$i]
        # Process each predecessor
        $i = $i + 1
    }
} else {
    # Handle single predecessor
    $data = $input_data
}
```

### For Template Authors
Templates receive simplified input by default:

```python
# Simple template - just use inp
return {'extracted_ip': inp.get('primary_ioc_value')}

# Advanced template - access full envelope
source = workflow_input.get('node_id')
result = inp  # Already simplified
return {'result': result, 'from': source}
```

## Troubleshooting

### Issue: "No partition found for row"
**Solution**: Ensure partitions exist. pg_partman manages partitions automatically, but you can trigger maintenance:
```bash
make partition-maintenance
```

### Issue: Task not receiving expected input
**Check**:
1. Is it a fan-in scenario? (multiple predecessors)
2. Remember the inconsistency: single predecessor gives simplified `inp`, multiple gives array of `{node_id, result}` objects
3. Review the task's Cy script to handle arrays properly
4. Check the envelope structure in node outputs

### Issue: Workflow stays in "pending" state
**Check**:
1. Are all required tasks created?
2. Are all node templates created?
3. Check logs for execution errors

## API Reference

All responses use the standard envelope: `{"data": <payload>, "meta": {...}}`.

### Workflow CRUD
- `POST /v1/{tenant}/workflows` - Create workflow
- `GET /v1/{tenant}/workflows` - List workflows
- `GET /v1/{tenant}/workflows/{id}` - Get workflow details
- `PATCH /v1/{tenant}/workflows/{id}` - Update workflow metadata
- `DELETE /v1/{tenant}/workflows/{id}` - Delete workflow
- `POST /v1/{tenant}/workflows/validate` - Validate workflow types

### Workflow Mutation
- `POST /v1/{tenant}/workflows/{id}/nodes` - Add node
- `PUT /v1/{tenant}/workflows/{id}/nodes/{label}` - Update node
- `DELETE /v1/{tenant}/workflows/{id}/nodes/{label}` - Remove node
- `POST /v1/{tenant}/workflows/{id}/edges` - Add edge
- `DELETE /v1/{tenant}/workflows/{id}/edges/{edge_id}` - Remove edge

### Node Template Endpoints
- `POST /v1/{tenant}/workflows/node-templates` - Create template
- `GET /v1/{tenant}/workflows/node-templates` - List templates
- `GET /v1/{tenant}/workflows/node-templates/{id}` - Get template

### Workflow Execution
- `POST /v1/{tenant}/workflows/{id}/run` - Start execution (returns 202)
- `GET /v1/{tenant}/workflow-runs` - List runs (filterable by workflow_id, status)
- `GET /v1/{tenant}/workflow-runs/{id}` - Get run details (includes output_data)
- `GET /v1/{tenant}/workflow-runs/{id}/status` - Get run status (lightweight)
- `GET /v1/{tenant}/workflow-runs/{id}/graph` - Get execution graph
- `GET /v1/{tenant}/workflow-runs/{id}/nodes` - Get node instances
