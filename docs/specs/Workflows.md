+++
version = "2.0"
date = "2025-11-17"
status = "active"

[[changelog]]
version = "2.0"
date = "2025-11-17"
summary = "v2 — DAG workflows with typed nodes"
+++

# Workflows

**Version**: 2.0
**Previous Version**: `IntroducingWorkflows_v1.md`

> **IMPORTANT - Mutability Change**: As of v2, workflows are now **mutable**. The original v1 design treated workflows as immutable blueprints. See `MutableWorkflows_v1.md` for the mutation APIs, ad-hoc execution, and example management features.

## About

Workflows are graphs that define the precise sequence of steps to achieve a complex objective. They are similar to Argo and Airflow but specialized for the type of agentic work.

Within a Workflow Graph:

* **Nodes** signify units of work.
* **Edges** facilitate directional flow of information (directional edges).

Node Types:

* **Task Nodes:** These are saved or ad-hoc tasks that receive input from previous node(s), execute the task, and broadcast their output across all outgoing edges. **Executed by the Task Execution Service.**
* **Transformation Nodes:** These are lightweight tasks that take input(s), transform them using Python code templates, and output the results across all outgoing edges. **Executed by the Workflow Execution Service.**
* **Foreach Nodes**: These split an incoming array into multiple items, run a child node or subworkflow for each item (optionally in parallel), and then aggregate their outputs. **Executed by the Workflow Execution Service using built-in logic.**
* **Switch Nodes (future work)**: These evaluate a condition against their input and forward execution down exactly one of multiple possible outgoing edges. **Will be executed by the Workflow Execution Service using built-in logic.**
* **Aggregation Nodes (future work)**: These wait for results from multiple predecessors, merge their outputs into a single envelope, and broadcast the combined result downstream. **Will be executed by the Workflow Execution Service using built-in logic.**
* **Filter Nodes (future work):** Drops payloads unless a specified condition is true. **Will be executed by the Workflow Execution Service using built-in logic.**

All outgoing edges from any node type consistently convey the same information to all targeted nodes (broadcast by default). The main execution to this rule are switch Nodes, that are out of scope of our first version.

### Terminology

* **Workflow**: A description of a set of tasks and their timing order in the form of a Workflow graph.
* **Workflow Graph**: A workflow represented as a Directed Acyclic Graph (DAG). In most contexts, Workflow and Workflow Graph are synonymous.
* **Task Nodes**: Nodes in a workflow that represent Tasks. These nodes are executed and managed via the Task Execution Service. Task Nodes may have side-effects and may change the state of the system. They often use external services such as REST APIs and APIs to LLMs.
* **Transformation Nodes**: Take a JSON object as input, transform it and output it as a new JSON object. In most cases, these transformations are simple projections. For example, take an Alert and project the targeted User or Device. Transformation nodes use Node Templates which contain Python code for the transformation logic. These are executed by the Workflow Execution Service.
* **Foreach Nodes**: Control flow nodes that iterate over arrays, creating child node instances for each item. These are executed by the Workflow Execution Service using built-in iteration logic, not templates.
* **Workflow Executor**: A running thread that executes a workflow from start to finish.
* **Node Instance:** A running instance of a node.
* **Workflow Run (dynamic)**: A single execution with a run graph consisting of node instances and edge instances.
* **Workflow Execution Plan**: An organization of the execution order for nodes and edges in the Workflow. It’s the job of the Workflow Executor to execute the Workflow Execution Plan.
* **Task Execution Service**: An existing service that is responsible for running multiple Tasks in parallel. The service is responsible for the Task lifecycle.
* **Envelope**: Every node emits a standard envelope { name, description, context, result }. Consumers read from the result.

## Workflow Representation

Workflows are **mutable** DAGs that represent a plan through a series of nodes and directional edges. They act as a blueprint, dictating the order in which tasks are executed. Workflows can be modified after creation via mutation APIs (see `MutableWorkflows_v1.md`). While a workflow defines the "code" to be run, the exact number of loop iterations or chosen branches are unknown until execution. The detailed representation of a Workflow Run will be explained later.

The subsequent sections will provide a detailed breakdown of the information contained within a workflow graph, covering both overall workflow details and specific information pertaining to individual nodes and edges.

Workflow Information:

* id (uuid - globally unique) — Note: References to "workflow_id" elsewhere in this spec refer to this id field
* tenant_id: varchar(255) - tenant isolation for multi-tenancy
* name: text - human-readable workflow name
* description: text - what this workflow is about
* is\_dynamic: boolean - true if created dynamically by an AI planner, false otherwise
* io\_schema: jsonb - defines overall workflow input and output schemas for validation
* created\_by: text - User or System for static workflows; or Planner for dynamic workflows
* created\_at: timestamptz - when the workflow was created
* planner\_id: uuid - if a planner was used, points to the planner with details like logic version (future work)

Node Information:

* id (uuid - primary key for the node)
* workflow_id (uuid - foreign key to workflows table)
* node\_id (text - mnemonic id unique within a workflow, e.g., "n-start", "n-geoip")
* kind: task/foreach/transformation etc. (enumeration matching our component pattern)
* name (text - human-readable node name)
* task\_id (uuid - references task component_id if this is a task node, else null)
* node\_template\_id (uuid - references node_templates.id if this is a transformation node, else null)
* foreach\_config (jsonb - contains path, bindings, child ref for foreach nodes, else null)
* schemas (jsonb - input/output/envelope schemas for validation)
* created\_at (timestamptz - when the node was created)
  * Context: Templates can be static or dynamic. Static templates are created by the developer team and are available to use by everyone in a workflow. Dynamic workflows are generated to fill in a gap in available nodes.

Edge Information:

* id (uuid - primary key for the edge)
* workflow_id (uuid - foreign key to workflows table)
* edge\_id (text - mnemonic id unique within a workflow, e.g., "e1", "e2")
* from\_node\_uuid (uuid - FK reference to workflow_nodes.id for the source node)
* to\_node\_uuid (uuid - FK reference to workflow_nodes.id for the target node)
* alias (text - optional label for the edge)
* created\_at (timestamptz - when the edge was created)

Example of edges
```json
"edges": \[
    { "edge\_id": "e1", "from": { "node\_id": "n-start" },   "to": { "node\_id": "n-pick-ip" }, "alias": "optional \- str” },
    { "edge\_id": "e2", "from": { "node\_id": "n-pick-ip" }, "to": { "node\_id": "n-geoip" }, "alias": "optional \- str” },
    { "edge\_id": "e3", "from": { "node\_id": "n-geoip" },   "to": { "node\_id": "n-block-ip" }, "alias": "optional \- str” }
  \]
```

**Versioning & immutability:** Workflows bind to a **specific version** of a node. New versions should not silently change existing workflows.

### Schema Specs

**Core rule**: Each node operates with a single input and a single output. The output is standardized within an envelope. If a node receives input from multiple predecessors, their outputs are consolidated into a single input (either an array or an object) before the node is executed. While a node produces only one output, this output can be directed to multiple subsequent nodes through various outgoing connections.

**Schemas**: Schemas define strict contracts for workflows and nodes, ensuring safety and consistency. At the workflow level, `io_schema` describes the overall input and output so clients know what to provide and expect. At the node level, each node validates both the full `output_envelope` (the uniform wrapper with metadata, provenance, and `result`) and the node-specific `output_result` (the actual payload). This two-layer approach means executors and monitoring can always rely on a consistent envelope structure, while producers and consumers are guaranteed compatible payloads.

**Examples:**

* Workflow-level schema:

"io\_schema": {
  "input": { "type": "object", "properties": { "alert": { "type": "object" } }, "required": \["alert"\] },
  "output": { "type": "object", "properties": { "ticket\_id": { "type": "string" } } }
}

* Node output envelope schema:
```json
{
  "type": "object",
  "properties": {
    "node\_id": { "type": "string" },
    "context": { "type": "object" },
    "description": { "type": "string" },
    "result": { "type": "object" }
  },
  "required": \["node\_id", "result"\]
}
```

* Node output result schema (GeoIP task):

```json
{
  "type": "object",
  "properties": {
    "primary\_ip": { "type": "string" },
    "geo": { "type": "object", "properties": { "country": { "type": "string" }, "city": { "type": "string" } } }
  },
  "required": \["primary\_ip", "geo"\]
}
```

### Examples

**Scenario:** Pick a primary IP from the alert, enrich with GeoIP (Task), then call a blocking API (Task).
```json
{
  "workflow\_id": "wf-0001-minimal",  // uuid in production
  "created\_at": "2025-08-16T18:00:00Z",
  "created\_by": "user",
  "is\_dynamic": false,
  "io\_schema": {
    "input": { "type": "object", "properties": { "alert": { "type": "object" } }, "required": \["alert"\] },
    "output": { "type": "object" }
  },
  "nodes": \[
    {
      "node\_id": "n-start",
      "kind": "transformation",
      "name": "Start (no-op passthrough)",
      "spec": {
        "node\_template\_id": "pass\_throug\_template", // uuid in production
        "language": "python", // copied over from template id
        "code": "return inp  \# assume inp is the initial workflow input envelope" // copied over from template id
      },
      "schemas": {
        "input": { "type": "object" },
        "output\_envelope": { "type": "object" },
        "output\_result": { "type": "object" }
      }
    },
    {
      "node\_id": "n-pick-ip",
      "kind": "transformation",
      "name": "Pick Primary IP",
      "spec": {
        "node\_template\_id": "map.pick\_primary\_ip.v1", // uuid in production
        "language": "python", // copied over from template id
        "code": "alert \= (inp\['result'\] if 'result' in inp else inp)\['alert'\]\\nips \= \[alert.get('dest',{}).get('ip'), alert.get('src',{}).get('ip')\]\\nprimary \= next((ip for ip in ips if ip), None)\\nreturn { 'primary\_ip': primary }" // copied over from template id
      },
      "schemas": {
        "input": { "type": "object" },
        "output\_envelope": { "type": "object" },
        "output\_result": { "type": "object", "properties": { "primary\_ip": { "type": \["string","null"\] } } }
      }
    },
    {
      "node\_id": "n-geoip",
      "kind": "task",
      "name": "GeoIP Enrichment",
      "spec": {
        "task\_id": "task.geoip.lookup"
      },
      "schemas": {
        "input": { "type": "object", "properties": { "primary\_ip": { "type": \["string","null"\] } }, "required": \["primary\_ip"\] },
        "output\_envelope": { "type": "object" },
        "output\_result": {
          "type": "object",
          "properties": {
            "primary\_ip": { "type": \["string","null"\] },
            "geo": { "type": "object" }
          }
        }
      }
    },
    {
      "node\_id": "n-block-ip",
      "kind": "task",
      "name": "Block IP in FW",
      "spec": {
        "task\_id": "task.firewall.block\_ip"
      },
      "schemas": {
        "input": { "type": "object", "properties": { "primary\_ip": { "type": "string" }, "geo": { "type": "object" } }, "required": \["primary\_ip"\] },
        "output\_envelope": { "type": "object" },
        "output\_result": { "type": "object", "properties": { "action\_id": { "type": "string" } }, "required": \["action\_id"\] }
      }
    }
  \],
  "edges": \[
    { "edge\_id": "e1", "from": { "node\_id": "n-start" },   "to": { "node\_id": "n-pick-ip" } },
    { "edge\_id": "e2", "from": { "node\_id": "n-pick-ip" }, "to": { "node\_id": "n-geoip" } },
    { "edge\_id": "e3", "from": { "node\_id": "n-geoip" },   "to": { "node\_id": "n-block-ip" } }
  \]
}
```

### Foreach Node Spec
```json
{
  "node\_id": "uuid",
  "kind": "foreach",
  "name": "string",
  "spec": {
    "path": "JSONPath to array within input envelope (e.g., \\"$.result.items\\")",

    "bindings": {
      /\* Map child input fields to JSONPath expressions evaluated per item.
         Expressions are evaluated relative to the item (\\"$\\" \= the item). \*/
      "fieldA": "$.a",
      "fieldB": "$.b",
      "whole\_item": "$"      /\* pass the entire item \*/
    },

    "child": { "ref\_node": "node\_id" },
    /\* OR \*/
    "subworkflow\_ref": { "id": "wf-id" },

    "order": "preserve|none",   /\* preserve \= output keeps original item order \*/

    "selectors": {
      "output": "$.result"      /\* JSONPath inside child output envelope for the per-item value \*/
    },

    "envelope": {
      /\* optional envelope enrichments applied to each child input envelope \*/
      "context\_overrides": { "loop": { "index": "$\_\_index", "key": "$.id" } }
    }
  },
  "schemas": {
    "input": { /\* JSON Schema for the incoming envelope.result \*/ },
    "output\_result": {
      /\* Aggregated output shape after all children finish.
         Common patterns: array of objects or { ok:\[\], err:\[\] } \*/
    }
  }
}
```

#### Field semantics

* **path**: where the executor finds the array to iterate (resolved against the incoming **envelope**; usually $.result…).
* **bindings**: shapes each child’s **input payload** from one array item (JSONPath evaluated **relative to the item**). Use "$" to pass the whole item.
* **child / subworkflow\_ref**: run a single node per item *or* a whole subworkflow per item (choose exactly one).
* **order**:
  * preserve → aggregated output is in original item order.
  * none → executor may emit as children complete (faster, unordered).
* **selectors.output**: JSONPath into each **child’s output envelope** to extract the value to aggregate.
  * If you want to aggregate something other than the whole child result, set selectors.output accordingly; otherwise you can omit it (default is $.result).
* **envelope.context\_overrides**: lets you stamp per‑item context (e.g., index/key) onto child input envelopes; special token \_\_$index is provided by the workflow executor. For every item in the array, the executor creates one node instance.

#### Foreach Node Examples

##### Example 1 — Array of strings (IPs) → child node n-geoip

```json
{
  "node\_id": "n-foreach-geoip",
  "kind": "foreach",
  "name": "ForEach(ips) → GeoIP",
  "spec": {
    "path": "$.result.ips",
    "bindings": {
      "ip": "$"                     // item is a string; bind directly as { ip }
    },
    "child": { "ref\_node": "n-geoip" },
    "order": "preserve",
    "selectors": {
      "output": "$.result"          // take full child result
    }
  },
  "schemas": {
    "input": {
      "type": "object",
      "properties": {
        "ips": { "type": "array", "items": { "type": "string" } }
      },
      "required": \["ips"\]
    },
    "output\_result": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "ip": { "type": "string" },
          "geo": { "type": "object" }
        },
        "required": \["ip", "geo"\]
      }
    }
  }
}
```

Explanation:
This foreach takes an array of IP addresses from the parent node’s output ($.result.ips). Each IP string becomes the input { "ip": "\<value\>" } for one instance of the n-geoip task. The executor runs one child instance per IP, collects each child’s full $.result object, and aggregates them into an array as the foreach node’s output. Order is preserved, so the output array corresponds 1:1 with the original IP list.

Sample Input Envelope:
```json
{
  "result": {
    "ips": \["8.8.8.8", "1.1.1.1"\]
  }
}
```

Sample Output Envelope:
```json
{
  "result": \[
    { "ip": "8.8.8.8", "geo": { "country": "US", "city": "Mountain View" } },
    { "ip": "1.1.1.1", "geo": { "country": "AU", "city": "Sydney" } }
  \]
}
```

##### Example 2 — Array of objects (users) → child node n-enrich-user

```json
{
  "node\_id": "n-foreach-user-enrich",
  "kind": "foreach",
  "name": "ForEach(users) → EnrichUser",
  "spec": {
    "path": "$.result.users",
    "bindings": {
      "id": "$.id",
      "email": "$.email"
    },
    "child": { "ref\_node": "n-enrich-user" },
    "order": "none",
    "selectors": {
      "output": "$.result.profile"   // pick a subfield from child output
    }
  },
  "schemas": {
    "input": {
      "type": "object",
      "properties": {
        "users": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "id": { "type": "string" },
              "email": { "type": "string" }
            },
            "required": \["id", "email"\]
          }
        }
      },
      "required": \["users"\]
    },
    "output\_result": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "id": { "type": "string" },
          "profile": { "type": "object" }
        },
        "required": \["id", "profile"\]
      }
    }
  }
}
```

Explanation:
This foreach takes an array of user objects ($.result.users). Each item has an id and an email. For each user, the executor spawns a child task n-enrich-user with input { "id": ..., "email": ... }. From the child’s output envelope, it extracts only the $.result.profile field (using the selectors.output path). The foreach node then aggregates all profiles into a result array, dropping other child fields. Since order is none, profiles may appear in any order.

Sample Input Envelope:
```json
{
  "result": {
    "users": \[
      { "id": "u1", "email": "alice@example.com" },
      { "id": "u2", "email": "bob@example.com" }
    \]
  }
}
```

Sample Output Envelope:
```json
{
  "result": \[
    { "id": "u1", "profile": { "name": "Alice", "age": 30 } },
    { "id": "u2", "profile": { "name": "Bob", "age": 28 } }
  \]
}
```

## Node Templates (for Transformation Nodes)

Node Templates contain Python code for transformation nodes. These templates represent units of work that meet the following conditions:

* They are computationally trivial (single line of code and O(1) complexity). May contain if/else statements, access deep nested data structure, and build new data structures (e.g., dictionaries, lists)
* They are independent
* They don’t have any sideeffects

Here are some basic examples examples (TODO: help me write few more):

* Get the name of the user from the alert
  * Alert\[“src\_user”\]\[“name”\]
* Get the main IP address of an alert
  * \[alert\[“dest”\]\[“ip”\], alert\[“src”\]\[“ip”\]

When a workflow is created it can reference a series of reusable templates. A collection of templates is curated and managed by the developers of the product. When a node is needed that is not yet available, there is the option in the future to use a GenAI model to code it on the fly.

### Collection of Basic Node Templates

Fields:

* id (uuid - primary key)
* resource\_id (uuid - groups versions of the same template; all versions share the same resource_id)
* name: text (mnemonic name, acts as the prefix for the mnemonic name id used in workflow creation)
* description: text
* input\_schema: jsonb (JSON schema for input validation)
* output\_schema: jsonb (JSON schema for output validation)
* code: text (the actual Python code that implements the template)
* language: text (e.g., 'python', default is 'python')
* type: text (static or dynamic - static for pre-built, dynamic for AI-generated)
* enabled: boolean (at most one version per resource_id can be enabled, strictly enforced via unique constraint)
* revision\_num: integer (increments for every version)
* created\_at: timestamptz (when the template was created)

The workflow definition points to the id of a template. When a Workflow Executor runs a workflow, it will replace the node with the proper code.

#### Persistence

Node Templates are stored in their own table in Postgres and can be accessed by their own endpoint.

## REST Endpoints

TODO: Suggested endpoints let’s review together

* Get all workflows with basic filtering. Create new workflows
  * /v1/{tenant}/workflows
* Update or delete an existing workflow
  * /v1/{tenant}/workflows/{id}
* Manage Node Templates
  * /v1/{tenant}/workflows/node-templates/
* Update or delete an existing node
  * /v1/{tenant}/workflows/node-templates/{id}

  # Workflow Execution Service

## About

A Workflow Executor Service orchestrates workflow execution, consisting of nodes (units of work) and edges (information flow). This service contains one or more configurable Workflow Executors and performs the following key functions:

* **Workflow Execution Plan Creation:**
  * Determines the optimal execution order for workflow nodes.
  * Identifies tasks suitable for concurrent execution.
* **Execution Facilitation via Workflow Executors:**
  * Schedules nodes based on the execution plan.
  * Manages input and output data flow between nodes.
  * Executes all non-task workflow nodes: transformation nodes (using templates), foreach nodes (using built-in logic), and future control flow nodes (Task Execution Service handles task nodes only).
* **Monitoring and Failure Handling:**
  * Monitors task progress during execution.
  * Handles failures (currently, the service exits on failure; future work will implement more robust handling).

In essence, the Workflow Execution Service provides workflow orchestration by ensuring correct node sequencing and accurate data flow. It's crucial to distinguish between **Workflows**, which are static blueprints, and **Workflow Runs**, which are dynamic execution instances of a given workflow. A single workflow can have multiple Workflow Runs, with identical or different inputs and outputs. Nodes in a workflow are referred to as static nodes, whereas nodes in a Workflow Run graph are called node instances.

## Architecture

In a Workflow, Task nodes are executed by the Task Execution Service exactly once because they have side-effects and are expensive. All other node types (transformation, foreach, and future control flow nodes) are executed by the Workflow Execution Service and can be executed at least once. These Workflow Execution Service nodes perform simple actions without side effects, allowing for safe re-execution of some or all of them after a restart.

### Workflow Executors

Workflow Executors are equipped to handle new workflows as they become pending. Each executor can concurrently manage multiple workflow runs. Due to the I/O-intensive nature of the workload, Python's asynchronous co-routines are ideal for these workflow executors. A single executor is sufficient to manage the entire lifecycle of a running workflow, negating the need for multiple executors to collaborate on a single workflow.

### Progressive Execution Algorithm

The Workflow Execution Service uses a progressive, dynamic approach to node instance creation and execution, unlike traditional workflow engines that pre-compute all nodes upfront.

#### Key Principles

1. **Dynamic Instance Creation**: Node instances are created only when all their predecessor instances exist (not necessarily completed)
2. **Progressive Discovery**: The graph unfolds as execution proceeds, especially important for foreach nodes where child count is unknown until runtime
3. **State-Driven Execution**: Each node instance has a status (pending/running/completed/failed/cancelled) that drives the execution flow

#### Execution Phases

**Phase 1: Initialization**
* Create workflow_run entry with status 'pending'
* Load the static workflow definition from the workflows table
* Create only the start node instance with status 'pending'
* No other node instances exist yet

**Phase 2: Main Execution Loop**
The executor continuously performs these steps:

1. **Process Newly Completed Instances**
   * Query for node instances that just transitioned to 'completed'
   * For each completed instance:
     * Find all outgoing edges from the static graph
     * Check if successor nodes can be created (all predecessors exist)
     * Create new instances for ready successors

2. **Handle Different Node Types**
   * **Task Nodes**: Create instance, dispatch to Task Execution Service, track via task_run_id (external execution)
   * **Transformation Nodes**: Create instance, execute Python template code inline within Workflow Execution Service, complete immediately
   * **Foreach Nodes**: Create instance, execute built-in iteration logic within Workflow Execution Service - extract array from parent output, create N child instances (up to limit), track parent-child relationship

3. **Execute Pending Instances**
   * Query for 'pending' instances where ALL predecessors are 'completed'
   * For single-predecessor nodes: Start execution immediately
   * For multi-predecessor nodes: Aggregate outputs, then execute
   * Update status to 'running' when execution begins

4. **Monitor Running Tasks**
   * Check task_run_id status with Task Execution Service
   * Update node instance when task completes
   * Capture output and store (inline or S3 based on size)

5. **Check Completion**
   * Workflow completes when no instances are pending or running
   * Final output is the output of sink node(s)

#### Progressive Instance Creation Example

Consider a workflow: Start → A → Foreach(B) → C

1. **Initial State**: Only Start instance exists
2. **Start completes**: A instance created (pending)
3. **A completes**: Foreach(B) instance created, discovers array has 3 items
4. **Foreach expands**: B[0], B[1], B[2] instances created as children
5. **B instances complete**: C instance created only after all B children done
6. **C completes**: Workflow done

#### Polling and Concurrency

* Executor polls database every 100ms for state changes
* Multiple node instances can execute in parallel
* Task nodes run asynchronously via Task Execution Service
* Transformation nodes execute synchronously in executor
* Database transactions ensure atomic state transitions

### Input and Output Validation

The workflow executor validates both the `output` envelope as well as the `result` schema.

Node output envelope schema (same for most nodes):
```json
{
  "type": "object",
  "properties": {
    "node\_id": { "type": "string" },
    "context": { "type": "object" },
    "description": { "type": "string" },
    "result": { "type": "object" }
  },
  "required": \["node\_id", "result"\]
}
```

Example of result schema (specific to the usecase):
```json
{
  "type": "object",
  "properties": {
    "primary\_ip": { "type": "string" },
    "geo": { "type": "object", "properties": { "country": { "type": "string" }, "city": { "type": "string" } } }
  },
  "required": \["primary\_ip", "geo"\]
}
```

**Validation example:** If a node emits an envelope missing `node_id`, it fails `output_envelope` validation. If it includes `node_id` but omits `primary_ip` in `result`, it passes envelope validation but fails `output_result` validation. This separation makes error handling precise and robust.

This two-layer approach makes error handling precise and robust.

#### **Executor behavior**

* **Transformation Nodes** — Executor constructs the output envelope around the template result.
* **Task Nodes** —
  * If task output already follows the envelope contract, missing fields (like node\_id) are auto-filled.
  * If not, the executor wraps raw output into the result field and adds envelope metadata.

#### **Aggregating multiple inputs**

When a node has multiple predecessors, the executor handles timing in two phases:

**Phase 1 - Instance Creation (when all predecessors are known):**
* As soon as all predecessor node instances exist (even if still running), create the successor node instance with status 'pending'
* This happens progressively as the workflow executes and predecessor instances are created
* The instance is created but NOT yet executed

**Phase 2 - Execution (when all predecessors complete):**
* Wait for ALL predecessor instances to reach 'completed' status
* Aggregate their outputs into a single input for the node
* Execute the node with the aggregated input

**Input Aggregation Format:**
* **Array of envelopes** (default) - Outputs from all predecessors in topological order
* **Object keyed by predecessor IDs** (future work)

The node's input schema must match the chosen aggregation shape.

**Example with 3 predecessors:**
1. Node A completes → Node D instance doesn't exist yet
2. Node B completes → Node D instance doesn't exist yet
3. Node C is created → Node D instance is created with status 'pending' (all 3 predecessors now known)
4. Node C completes → Node D can now execute with aggregated inputs from A, B, and C

### Reliability

In the current version, the Task Execution Service is responsible for reliable task execution. Although retry policies may be present in some workflow examples, their implementation is deferred to future work. Nodes executed by the Workflow Execution Service (transformation, foreach, and future control flow nodes), being simple logic, are unlikely to benefit from retries upon failure. Therefore, for this v1, there are no retries for any Node type in the event of a failure. If a failure occurs, the entire workflow fails and is marked as such. All inflight nodes are canceled at that point.

### Resource Limits

To prevent resource exhaustion and ensure system stability, the following limits are enforced:

#### Foreach Node Limits
* **Maximum items per foreach node**: 10 items (hard cap for MVP)
* The limit is checked when extracting the array from the parent node's output using the JSONPath specified in the foreach node's `path` field
* If the array exceeds 10 items, the workflow execution fails with a clear error message indicating the limit violation
* Each array item creates one child node instance with its own `loop_context` containing: `item_index`, `item_key` (from item.id or index), and `total_items`
* This limit prevents unbounded resource consumption and makes debugging easier during development

#### Future Resource Limits (not implemented in v1)
* Maximum parallel node executions per workflow
* Maximum workflow execution time
* Maximum total nodes per workflow run (including dynamically created foreach children)
* Per-tenant resource quotas

### Persistence

#### Workflows

Workflows, which serve as blueprints for execution, are stored in the PostgreSQL `workflows` table upon creation. They are persisted in PostgreSQL before execution. Workflows under 512KB are stored entirely as JSONB in PostgreSQL. Larger workflows have their JSON saved in a dedicated workflow\_runs bucket within an object store (MinIO or S3). The database schema needs to distinguish between these two storage methods, similar to the approach used by the Task Executor service.

#### Bucket Design for Workflow Runs (follow the Task Runs pattern)

analysi-storage/{tenant\_id}/workflow-runs/2025-08-14/{uuid}/workflow\_input/\*
analysi-storage/{tenant\_id}/workflow-runs/2025-08-14/{uuid}/workflow\_output/\*
analysi-storage/{tenant\_id}/workflow-runs/2025-08-14/{uuid}/workflow\_node\_instances/{uuid}/input/
analysi-storage/{tenant\_id}/workflow-runs/2025-08-14/{uuid}/workflow\_node\_instances/{uuid}/output/

#### Workflow Runs

A workflow begins execution when it is explicitly submitted to run. This action creates a new entry in the `workflow_runs` table in PostgreSQL. We repeat here to make it more clear that  there is an important distinction between `workflows` that define the blueprint, versus `workflow_runs` that denote the actual work being done.

**Execution Details:**

* The nodes within the workflow will execute in a specific order, as detailed later in this document.
* A running workflow (in `workflow_runs)` can exist in one of the following states:
  * **Pending:** The workflow is awaiting a Workflow executor to pick it up.
  * **In Progress:** At least one node in the workflow has started execution.
  * **Paused:** A user has triggered a pause (future work).
  * **Completed:** The workflow has finished, either with a **Failure** or **Success** outcome.

##### Node Instances

A **node instance** is a representation of a concrete execution of a static node (including repeats from `foreach` or retries). (A node that is defined in a workflow without any runtime information is referred to as a “static node”.) Both Tasks and Templated Nodes get to have an entry in the `node_instances` table. Note that for Tasks the input and output is already captured in the tasks-run table. For Templated Nodes we do not capture the input in the node\_instances table for debugging and better visualization of the workflow run on the UI. Input/output of 512KB are stored entirely as JSONB in PostgreSQL. Larger payloads have their JSON saved in a dedicated workflow\_runs bucket within an object store (MinIO or S3).

**Node Instances Fields:**

* `id (uuid)` — primary key, referenced as node_instance_id elsewhere
* `workflow_run_id (uuid)` — FK to workflow_runs table
* `node_id (text)` — mnemonic reference to the static node (e.g., "n-start", "n-geoip")
* `node_uuid (uuid)` — FK to workflow_nodes.id for the static node definition
* `task_run_id (uuid)` — FK to task_runs table if this is a task node, else null
* `parent_instance_id (uuid)` — FK to parent node instance for foreach children, else null
* `loop_context (jsonb)` — `{ item_index: 0, item_key: "...", total_items: 10 }` for foreach children
* `status (text)` — pending/running/completed/failed/cancelled
* `started_at (timestamptz)` — when node execution started
* `ended_at (timestamptz)` — when node execution ended
* `input_type (text)` — 'inline' or 's3' storage strategy for input
* `input_location (text)` — JSON if inline, S3 path if s3
* `output_type (text)` — 'inline' or 's3' storage strategy for output
* `output_location (text)` — JSON if inline, S3 path if s3
* `template_id (uuid)` — FK reference to immutable node_templates table for transformation nodes
* `error_message (text)` — populated if status is 'failed'
* `created_at (timestamptz)` — when the instance was created
* `updated_at (timestamptz)` — last update time

**Template Code Storage:**
* Store the `template_id` as a foreign key to the node_templates table
* Templates with a given UUID are immutable, ensuring the code doesn't change
* The template code can be retrieved by joining with the node_templates table when needed for debugging

##### Edge Instances

As the graph execution progresses, we also create the forming edges of the graph and persist them into the `workflow_edge_instances` table. The combination of the node\_instances and edge\_instances can be used to visualize the progression of the graph as it gets executed.

* `id (uuid)` — primary key, referenced as edge_instance_id elsewhere
* `workflow_run_id (uuid)` — FK to workflow_runs table
* `edge_id (text)` — mnemonic reference to the static edge (e.g., "e1", "e2")
* `edge_uuid (uuid)` — FK to workflow_edges.id for the static edge definition
* `from_instance_id (uuid)` — FK to workflow_node_instances.id for source node instance
* `to_instance_id (uuid)` — FK to workflow_node_instances.id for target node instance
* `delivered_at (timestamptz)` — when data was delivered across this edge
* `created_at (timestamptz)` — when the edge instance was created

##### Workflow Run

When we run a workflow we also create an entry in the `workflow_runs` table. As with Task Runs, we capture the input and output of the workflow. A similar policy as before (<512KB) is used for deciding if we are to keep the data in Postgres or in our object store (MinIO or S3).

* `id (uuid)` — primary key, referenced as workflow_run_id elsewhere
* `tenant_id (varchar(255))` — tenant isolation
* `workflow_id (uuid)` — FK to workflows table
* `status (text)` — pending/running/completed/failed/cancelled
* `started_at (timestamptz)` — when execution started
* `ended_at (timestamptz)` — when execution ended
* `input_type (text)` — 'inline' or 's3' storage strategy
* `input_location (text)` — JSON if inline, S3 path if s3
* `output_type (text)` — 'inline' or 's3' storage strategy
* `output_location (text)` — JSON if inline, S3 path if s3
* `error_message (text)` — populated if status is 'failed'
* `created_at (timestamptz)` — when the run was created
* `updated_at (timestamptz)` — last update time

Executors will periodically scan for incomplete workflows. The persistence mechanism must enable the restart of interrupted workflows without re-executing already completed tasks.

### Checkpoint and Recovery

The PostgreSQL persistence model provides complete checkpointing for workflow execution, allowing executors to resume from any interruption without data loss or duplicate execution.

#### What's Persisted for Recovery
* **Workflow run state** - Current status (pending/running/completed/failed), input/output data
* **Node instance state** - Every created instance with its status, input/output, parent relationships, and loop context
* **Edge instances** - Complete record of data flow between node instances
* **Task runs** - Linked from node instances via `task_run_id` foreign key

#### Recovery Process
When a workflow executor restarts or takes over an interrupted workflow:
1. **Load workflow run** - Query `workflow_runs` table for workflows with status 'pending' or 'running'
2. **Find execution point** - Identify all node instances by status (pending/running/completed/failed)
3. **Check running tasks** - For node instances with `task_run_id`, query the Task Execution Service to check if tasks completed while executor was down
4. **Resume from last state** - Continue execution using the persisted state without re-running completed nodes

#### No Gaps in Recovery
* All execution state is persisted in PostgreSQL - no in-memory only state that could be lost
* Node instances are created with status 'pending' before execution begins
* Task runs are tracked separately and maintain their own state
* Parent-child relationships for foreach nodes are preserved via `parent_instance_id`
* Edge instances show exact data flow and can be used to reconstruct node dependencies
* The 512KB storage threshold ensures all data (inline or S3) can be retrieved

## Database Schema

The workflow system uses PostgreSQL with a clear separation between static (blueprint) and dynamic (execution) tables.

**Note on API vs Database Field Names**: The database uses `id` as primary keys for consistency (e.g., `workflows.id`, `workflow_node_instances.id`). However, API responses use more descriptive field names for clarity:
- `workflows.id` → API field `workflow_id`
- `workflow_node_instances.id` → API field `node_instance_id`
- `workflow_edge_instances.id` → API field `edge_instance_id`

This makes API responses self-documenting and easier to understand for consumers, while keeping the database schema consistent with our existing patterns.

### Static Tables (Immutable Blueprints)

```sql
-- Workflow definitions
CREATE TABLE workflows (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id varchar(255) NOT NULL,
    name text NOT NULL,
    description text,
    is_dynamic boolean DEFAULT false,
    io_schema jsonb NOT NULL,  -- Overall workflow input/output schema
    created_by text NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    planner_id uuid,  -- If created by AI planner (future work)
    CONSTRAINT workflows_io_schema_valid CHECK (jsonb_typeof(io_schema) = 'object')
);

CREATE INDEX idx_workflows_tenant ON workflows(tenant_id);
CREATE INDEX idx_workflows_created ON workflows(created_at);

-- Node definitions within workflows
CREATE TABLE workflow_nodes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id uuid NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    node_id text NOT NULL,  -- Mnemonic: "n-start", "n-geoip", etc.
    kind text NOT NULL CHECK (kind IN ('task', 'transformation', 'foreach')),
    name text NOT NULL,
    -- Only one of these should be populated based on 'kind'
    task_id uuid REFERENCES tasks(component_id),  -- For task nodes
    node_template_id uuid REFERENCES node_templates(id),  -- For transformation nodes
    -- Foreach-specific configuration
    foreach_config jsonb,  -- Contains path, bindings, child ref, etc. for foreach nodes
    schemas jsonb NOT NULL,  -- Input/output/envelope schemas
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT workflow_nodes_unique_node_id UNIQUE(workflow_id, node_id),
    CONSTRAINT workflow_nodes_schemas_valid CHECK (jsonb_typeof(schemas) = 'object'),
    -- Ensure correct fields are populated based on kind
    CONSTRAINT workflow_nodes_kind_fields CHECK (
        (kind = 'task' AND task_id IS NOT NULL AND node_template_id IS NULL AND foreach_config IS NULL) OR
        (kind = 'transformation' AND node_template_id IS NOT NULL AND task_id IS NULL AND foreach_config IS NULL) OR
        (kind = 'foreach' AND foreach_config IS NOT NULL AND task_id IS NULL AND node_template_id IS NULL)
    )
);

CREATE INDEX idx_workflow_nodes_workflow ON workflow_nodes(workflow_id);
CREATE INDEX idx_workflow_nodes_task ON workflow_nodes(task_id) WHERE task_id IS NOT NULL;
CREATE INDEX idx_workflow_nodes_template ON workflow_nodes(node_template_id) WHERE node_template_id IS NOT NULL;

-- Edge definitions connecting nodes
CREATE TABLE workflow_edges (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id uuid NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    edge_id text NOT NULL,  -- Mnemonic: "e1", "e2", etc.
    from_node_uuid uuid NOT NULL REFERENCES workflow_nodes(id),
    to_node_uuid uuid NOT NULL REFERENCES workflow_nodes(id),
    alias text,  -- Optional edge label
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT workflow_edges_unique_edge_id UNIQUE(workflow_id, edge_id)
);

CREATE INDEX idx_workflow_edges_workflow ON workflow_edges(workflow_id);
CREATE INDEX idx_workflow_edges_nodes ON workflow_edges(from_node_uuid, to_node_uuid);

-- Node templates for transformations
CREATE TABLE node_templates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_id uuid NOT NULL,  -- Groups versions of same template
    name text NOT NULL,
    description text,
    input_schema jsonb NOT NULL,
    output_schema jsonb NOT NULL,
    code text NOT NULL,
    language text NOT NULL DEFAULT 'python',
    type text NOT NULL CHECK (type IN ('static', 'dynamic')) DEFAULT 'static',
    enabled boolean DEFAULT true,
    revision_num integer NOT NULL DEFAULT 1,
    created_at timestamptz DEFAULT now() NOT NULL,
    -- Only one enabled version per resource_id
    CONSTRAINT node_templates_unique_enabled UNIQUE(resource_id, enabled) WHERE enabled = true,
    CONSTRAINT node_templates_schemas_valid CHECK (
        jsonb_typeof(input_schema) = 'object' AND
        jsonb_typeof(output_schema) = 'object'
    )
);

CREATE INDEX idx_node_templates_resource ON node_templates(resource_id);
CREATE INDEX idx_node_templates_enabled ON node_templates(enabled) WHERE enabled = true;
```

### Dynamic Tables (Execution Instances)

**Note on Partitioning**: The three dynamic tables (`workflow_runs`, `workflow_node_instances`, `workflow_edge_instances`) are partitioned by `created_at` using the same daily partitioning strategy as `task_runs`. This is essential for performance as these tables will grow large with high-volume workflow execution. The partitioning follows the existing pattern established for task execution tracking.

```sql
-- Workflow execution instances (partitioned by created_at for performance)
CREATE TABLE workflow_runs (
    id uuid DEFAULT gen_random_uuid(),
    tenant_id varchar(255) NOT NULL,
    workflow_id uuid NOT NULL REFERENCES workflows(id),
    status text NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    started_at timestamptz,
    ended_at timestamptz,
    -- Input/Output with dual storage strategy (inline for <512KB, S3 for larger)
    input_type text CHECK (input_type IN ('inline', 's3')),
    input_location text,  -- JSON if inline, S3 path if s3
    output_type text CHECK (output_type IN ('inline', 's3')),
    output_location text,
    error_message text,  -- For failed status
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    -- Partitioned primary key must include partition column
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE INDEX idx_workflow_runs_tenant_status ON workflow_runs(tenant_id, status);
CREATE INDEX idx_workflow_runs_workflow ON workflow_runs(workflow_id);
CREATE INDEX idx_workflow_runs_created ON workflow_runs(created_at);

-- Node execution instances (partitioned by created_at for performance)
CREATE TABLE workflow_node_instances (
    id uuid DEFAULT gen_random_uuid(),
    workflow_run_id uuid NOT NULL, -- FK to workflow_runs, but partition-aware
    node_id text NOT NULL,  -- References static node_id
    node_uuid uuid NOT NULL REFERENCES workflow_nodes(id),
    task_run_id uuid,  -- FK to task_runs table if this is a task node
    parent_instance_id uuid, -- FK to workflow_node_instances, but partition-aware
    loop_context jsonb,  -- {item_index: 0, item_key: "...", total_items: 10}
    status text NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    started_at timestamptz,
    ended_at timestamptz,
    -- Input/Output with dual storage strategy
    input_type text CHECK (input_type IN ('inline', 's3')),
    input_location text,
    output_type text CHECK (output_type IN ('inline', 's3')),
    output_location text,
    -- Template reference
    template_id uuid REFERENCES node_templates(id),
    error_message text,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    -- Partitioned primary key must include partition column
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE INDEX idx_node_instances_run_status ON workflow_node_instances(workflow_run_id, status);
CREATE INDEX idx_node_instances_parent ON workflow_node_instances(parent_instance_id);
CREATE INDEX idx_node_instances_task_run ON workflow_node_instances(task_run_id);

-- Edge execution instances (partitioned by created_at for performance)
CREATE TABLE workflow_edge_instances (
    id uuid DEFAULT gen_random_uuid(),
    workflow_run_id uuid NOT NULL, -- FK to workflow_runs, but partition-aware
    edge_id text NOT NULL,  -- References static edge_id
    edge_uuid uuid NOT NULL REFERENCES workflow_edges(id),
    from_instance_id uuid NOT NULL, -- FK to workflow_node_instances, but partition-aware
    to_instance_id uuid NOT NULL, -- FK to workflow_node_instances, but partition-aware
    delivered_at timestamptz,
    created_at timestamptz DEFAULT now() NOT NULL,
    -- Partitioned primary key must include partition column
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

CREATE INDEX idx_edge_instances_run ON workflow_edge_instances(workflow_run_id);
CREATE INDEX idx_edge_instances_nodes ON workflow_edge_instances(from_instance_id, to_instance_id);

-- Updated timestamp triggers
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_workflow_runs_updated_at BEFORE UPDATE
    ON workflow_runs FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_node_instances_updated_at BEFORE UPDATE
    ON workflow_node_instances FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

### Future Work

**Security for Template Execution**: Sandbox Python template execution to prevent access to database, filesystem, or network resources.

**Error Handling Strategy**: Define partial failure handling - should workflows continue when some foreach children fail, or fail entirely?

**Tenant Isolation Rules**: Clarify cross-tenant workflow/task/template access permissions and data leakage prevention.

**Workflow Lifecycle Management**: Add pause/resume/cancel operations for running workflows.

**Ports**: Multiple named inputs/outputs per node for explicit data contracts and fan-out/fan-in operations.

## REST Endpoints

### Workflow Execution APIs

* **Execute a workflow**
  * `POST /v1/{tenant}/workflows/{id}/run`
    * Async execution - returns workflow_run_id immediately
    * Creates new workflow_run entry and begins execution
    * Follow same pattern as Task runs

* **List workflow runs**
  * `GET /v1/{tenant}/workflow-runs`
    * List all workflow runs with pagination support
    * Filtering: `?workflow_id={id}&status={status}&limit={n}&offset={n}`
    * Returns summary information (id, status, start/end times, workflow_id)

* **Get workflow run details**
  * `GET /v1/{tenant}/workflow-runs/{workflow_run_id}`
    * Complete workflow run information including input/output
    * Status, timing, error messages
    * References to source workflow definition

* **Get workflow run status (lightweight)**
  * `GET /v1/{tenant}/workflow-runs/{workflow_run_id}/status`
    * Fast polling endpoint returning just status and basic timing
    * Optimized for UI status updates

### Workflow Run Visualization APIs

* **Get materialized execution graph**
  * `GET /v1/{tenant}/workflow-runs/{workflow_run_id}/graph`
    * **Primary visualization endpoint** - materialized run graph with all node and edge instances
    * Shows complete graph if done, or partial graph with current progress
    * Includes completeness flag and snapshot timestamp for real-time updates
    * Perfect for driving graph-based visualizations

* **List node instances**
  * `GET /v1/{tenant}/workflow-runs/{workflow_run_id}/nodes`
    * List all node instances with pagination support
    * Filtering: `?node_id={id}&status={status}&parent_instance_id={id}&limit={n}&offset={n}`
    * Summary view of all node executions

* **Get specific node instance**
  * `GET /v1/{tenant}/workflow-runs/{workflow_run_id}/nodes/{node_instance_id}`
    * Detailed view of specific node instance execution
    * Includes full input/output data, timing, error details
    * Template code reference for transformation nodes

* **List edge instances**
  * `GET /v1/{tenant}/workflow-runs/{workflow_run_id}/edges`
    * List all edge instances showing data flow with pagination support
    * Filtering: `?edge_id={id}&from_instance_id={id}&to_instance_id={id}&limit={n}&offset={n}`
    * Useful for debugging data flow issues

About the Dynamic Graph representation during a workflow-run.What the graph endpoint returns:

* **Scope:** the **materialized run graph so far** (node **instances** \+ edges between instances that have actually occurred).
* **Monotonicity:** results are **append‑only** over time (no reusing instance IDs, no re‑ordering).
* **Stability:** instance IDs and edge instance IDs are **stable** once emitted.
* **Causality:** an edge instance appears **only after** both endpoint instances exist.
* **Completeness flag:** is\_complete: true|false tells the client whether it’s the final shape.
* **Snapshotting:** include snapshot\_at (timestamp) so UIs can diff/incrementally update.

Suggested response shape (instances view):

```json
{
  "workflow\_run\_id": "wr\_123",
  "is\_complete": false,
  "snapshot\_at": "2025-08-18T19:20:30Z",
  "summary": {
    "counts": { "ready": 4, "running": 2, "done": 7, "failed": 0, "canceled": 0 }
  },
  "nodes": \[
    {
      "node\_instance\_id": "ni\_1",
      "node\_id": "n-foreach-geoip",
      "status": "done",
      "loop\_ctx": null
    },
    {
      "node\_instance\_id": "ni\_2",
      "node\_id": "n-geoip",
      "status": "running",
      "loop\_ctx": { "item\_index": 3 }
    }
  \],
  "edges": \[
    {
      "edge\_instance\_id": "ei\_10",
      "edge\_id": "e2",
      "from\_node\_instance\_id": "ni\_1",
      "to\_node\_instance\_id": "ni\_2",
      "delivered\_at": "2025-08-18T19:19:59Z"
    }
  \]
}
```

## UI Implementation Notes

Guidance for building workflow visualization components in the UI. The
authoritative endpoint for dynamic visualization is
`GET /v1/{tenant}/workflow-runs/{workflow_run_id}/graph`, which returns the
materialized execution graph (nodes + edges with per-instance status,
timings, and I/O data). Use the lighter
`GET /v1/{tenant}/workflow-runs/{workflow_run_id}/status` for cheap
"is anything new?" checks.

### Polling strategy

- Poll the lightweight `/status` endpoint while `status === 'running'`.
- Suggested cadence: 1 s while running, 5 s otherwise.
- Stop polling on terminal statuses: `completed`, `failed`, `cancelled`.
- Use the `snapshot_at` timestamp from the graph response for incremental
  updates so the UI can detect "nothing new since last fetch".

### Progressive execution — UI implications

Node instances are materialized dynamically as upstream nodes complete;
a foreach may fan out into many child instances. The UI must not assume
that every static node has a matching instance at any given time. Render
a "waiting for predecessors" state for static nodes that do not yet have
an instance. Animate the appearance of new instances so the graph can
grow smoothly during execution, and keep pan/zoom enabled so users can
follow large graphs (100+ nodes) without losing their place.

### Status and node-kind color conventions

| Status      | Color     |
|-------------|-----------|
| pending     | `#6B7280` (gray)  |
| running     | `#3B82F6` (blue)  |
| completed   | `#10B981` (green) |
| failed      | `#EF4444` (red)   |
| cancelled   | `#F59E0B` (amber) |

| Node kind       | Color                |
|-----------------|----------------------|
| task            | `#1E40AF` (dark blue)   |
| transformation  | `#059669` (dark green)  |
| foreach         | `#D97706` (dark orange) |

### Data flow visualization

Each node instance exposes `input_data`, `output_data.result`, and
`output_data.context`. The UI can surface these via hover popovers,
side panels, or animated edge decorations to show data moving between
completed nodes. Size or weight edges by data volume if useful; large
payloads may be stored in S3 and will be referenced by artifact path
rather than inlined.

