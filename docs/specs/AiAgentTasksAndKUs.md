+++
version = "2.0"
date = "2025-11-17"
status = "active"

[[changelog]]
version = "2.0"
date = "2025-11-17"
summary = "v2 — Knowledge Modules, refined Task model"
+++

# Background

## Summary

AI Agents perform **Tasks** — such as transforming data, explaining complex information, or making decisions (reasoning). Each Task has one or more inputs and produces a single output. To perform these Tasks, Agents rely on **Knowledge Units (KUs)** — reusable components of information or capability. For better re-usability, KUs can be combined together into **Knowledge Modules (KMs)** making it easier for them to be used together.

There are three types of Knowledge Units:

* **Tables** – Structured lists of information (e.g., allow-listed software, known bad actors, crown jewels).
* **Documents** \- These are unstructured documents (imported from PDF, copy pasted text, etc.) that are referenced during a Task. Irrespective of the source format (e.g., PDF or raw text) all documents are internally represented using Markdown.
* **Tools** – External interfaces that fetch or compute information dynamically (e.g., querying a database or performing a web search). Tools are often accessed via MCP (Model Context Protocol) APIs.

Tasks **consume** Knowledge Units (KUs), and KUs may **reference or build on each other**. For example, the task that identifies the severity of an Alert will need to consume a list of the crown jewels assets of the organization to better achieve its goals. In terms of KUs building on each other, consider the example where two documents may be summarized together to form a new summary document.

The dependencies mentioned above are captured in our data model via **Knowledge Dependency Graphs (KDGs)**. KDGs are key in providing transparency and the ability to visually customize the knowledge available to a Task.

Example of a KDG and the key relationships it captures:

* Task1 uses Table1 and Document5
* Document1 was summarized into Table 1
* Task1 generated/updates Document2 when it runs

## Key Terms

* **Task**: An action performed by an AI agent. Tasks have inputs and outputs (like functions) and may depend on KUs and generate new KUs if needed.
* **Workflows**: Tasks are chained together to solve complex problems forming workflows. In a workflow, tasks run in particular order and often the output of one chained task is provided as input or context to another task. Workflows are also referred to as “Task Execution Graphs”.
* **Task Run**: An instance/record of a running/completed Task.
* **Alert Analysis Workflows**: The most important set of workflows in the products. These are the ones responsible for triaging and investigating incoming alerts, which is the main goal of this product.
* **Task Execution Graphs (TEG)**: another name for Workflows
* **Cy Script:** Cy is the name of the programming language for Tasks. Every task has a Cy script that defines its execution. Cy scripts may call multiple tools, native functions, including making calls to LLMs.
* **Document**: A type of Knowledge Unit. Often they function as Context while executing a task. Docs are more effective if they are below 200 lines. If Docs grow large, it’s better to chunk them and add them into a RAG index.
* **Index**: A type of Knowledge Unit. A collection of text chunks access, stored in a vector database,  retrieved via semantic search. Often used for RAG.
* **Graph Index**: A type of Knowledge Unit. A type of index that can better reason over complex queries that need to do multiple step-wise retrievals in order to answer queries.
* **Table**: A type of Knowledge Unit. A structured dataset used for lookup or reasoning. May support semantic search via vector indexing.
* **Tool**: A type of Knowledge Unit. An external callable interface used to retrieve or compute dynamic knowledge at runtime.
* **Knowledge Unit (KU)**: A reusable unit of knowledge (Directive, Table, or Tool) consumed by Tasks.
* **Knowledge Module (KM)**: A group of KUs that can be used as a group to facilitate re-usability. Tasks technically depend on individual Knowledge Units. Knowledge Modules exist as reusable groupings of KUs, which are expanded into their constituent units during execution or dependency resolution.
* **Workbench**: A UI experience where users can freely test and CRUD Tasks.
* **Knowledge Dependency Graph (KDG)**: The network capturing dependencies and relationships between Tasks and Knowledge Units. Note that both Workflows (Task Execution Graphs) and KDGs can represent graphs between Tasks. The main difference is that KDG are fairly static and are explicitly defined by the Task authors. In contrast, workflows capture dynamic connections of Tasks brought together to solve a problem.
* **Universes**: This is an advanced concept where the product can be set up to have at most N different Universes. Each universe has its own versions and sets of Tasks that are taking place only for the critical Alert Analysis Workflow. This will allow analysis to change a few areas of the product without compromising the main Alert workflow. This is only a concept for now, keep it in mind for the design, but we do not implement this feature yet.
  * Universes convert the main processing Tasks and all Knowledge objects.
  * For simplicity, at most two universes may be enabled. The pro-universe is what we support now and some customers may choose to have a dev-universe. Where they can change up to 5 Tasks or KUs to validate an idea without compromising on the original design.

# Main Concepts

## Component Base Class

Both Tasks and Knowledge Units (KUs) share common management, versioning, and lifecycle properties. These are captured in a base Component class that provides:

### Common Component Fields

* **id**: Unique identifier (UUID)
* **tenant_id**: UUID - tenant isolation for multi-tenancy (indexed)
* **kind**: Component type discriminator (`task` or `ku`)
* **name**: Human-readable name
* **description**: Short summary of the component's purpose
* **version**: Semantic version (e.g., "1.0.0")
* **status**: `enabled` (default) or `disabled` - operational state
* **visible**: Boolean (default: false) - whether component is visible to users
* **system_only**: Boolean (default: false) - whether component can only be modified by system
* **app**: Name of the app namespace (default: "default")
* **categories**: Array of tags for classification and search
* **authored_by**: `system` or username - who originally created this
* **last_edited_by**: `system` or username - who last modified this
* **created_at**: Timestamp of creation
* **updated_at**: Timestamp of last update
* **last_used_at**: Timestamp of last usage

## Tasks

A task is a unit of work performed by an AI agent. It has inputs and outputs related to the task and makes use of Knowledge Units (KUs) to achieve its goal. Tasks are programmed using the Cy language. Tasks inherit from the Component base class.

The majority of the Tasks are going to be provided by us, the developers. Users can independently test and modify tasks (see Interacting with Tasks subsection below) as well as build new tasks as they please.

In the future, tasks may also be scheduled (e.g., run once a day using cron job scheduling), but for now we park this idea to simplify our MVP.

### Organizing Task

Tasks are organized into different sub-categories.

#### Task Function

Tasks can serve different functions:

* **Summarization**: A complex piece of information (e.g., a large JSON document) is summarized to its fundamentals.
* **Data Conversion:** Convert from one representation of the data to another.
* **Extraction**: Extract information from a larger corpus.
* **Reasoning**: When information is combined to make a decision, such as when deciding if an IP is malicious based on a set of observations.
* **Planning**: When a bigger problem is decomposed into a smaller set of sub-tasks.
  * While Tasks are currently executed explicitly, future versions may introduce Agent Planning layers that dynamically select and sequence tasks based on goals.
  * Only a small subset of tasks today may generate a Graph of Tasks that need to be executed
* **Visualization**:  When a piece of information is converted from Text to Visual.
* **Search:** Given a vector table, find the most relevant entries.

#### Task Scope

Tasks have a Scope that describes where in the processing pipeline they are applied. Each task has a single scope value.

* **Input Tasks**: Deal with how we import data into the system.
  * Example: Convert ingested data to our internal representation
* **Output Tasks**: Deal with how we export/sync information out of the system
  * Example: Sync Disposition to Splunk Task
* **Processing Tasks**: How we process information internally
  * Example: Select the best Runbook for this particular Alert

#### Task Mode

Task have two modes:

* **Ad-hoc**: In different parts of the product users can write Cy scripts and execute them to explore the data and what-if scenarios. The tasks may run once and we never see them again.
* **Saved**: Tasks that are pre-build by the developers and provide the cornerstone of this product. Users can create and manage Tasks using different UI and API experiences, like the UI Workbench.

#### Task Categories

Categories is an extensible way of tagging tasks with information to make it easy to search and document:

* Vendor Source Types: “Windows”, “Linux”, “MacOS”, “CrowdStrike”, “Google”, “Cisco”, “Palo Alto”
* Product specific: “Active Directory”, “Splunk Enterprise Security”
* Cy Script specific: Composite (uses other tasks), AI (uses AI/LLMs)
* State: Experimental, Production

#### Task Status

* **Enabled (default)**: Can be executed and included by the planner as part of a workflow.
* **Disabled**: Should not be included by a planner as part of a workflow.

#### Apps

Tasks can belong in Apps. Apps essentially form a namespace for Tasks and also for KUs. In the future, we plan to provide a marketplace where everyone can share their own Apps. Apps will bring new Tasks and new Knowledge Units. This is left for future work

* The “default” app is used as a placeholder for now

#### Visible

* **True**: The Task is visible to everyone
* **False** (default): The Tasks is internal and not visible for introspection or modification (sensitive system tasks can be tagged in this way)

#### System Only

* **True**: Task cannot be modified by the users (only system via a product update). This includes enabling or disabling them. Usually System Only Tasks are also Invisible (visible=false).
* **False** (default)

### Other Task Key Fields

* **Description:** A human readable short summary of what this task is all about. In the future we plan to create embeddings for this for semantically searching across Tasks.
* **Directive**: This is what goes into the system(\<text\>) message for all of the LLM calls called within the Cy script.
* **Script**: This is where we store the Cy script as a text to make it easy to show and execute when needed
* **Schedule**: A cron expression (Implementing the scheduler is left for Future work)
* **Version**: "1.0.0" Semantic versioning
* **LLM Configuration**: Settings for AI/LLM calls within the task
  * **Default Model**: Primary LLM model to use (e.g., "gpt-4", "claude-3-opus")
  * **Fallback Models**: Ordered list of backup models
  * **Temperature**: Creativity/randomness setting (0.0 - 1.0)
  * **Max Tokens**: Maximum response length
  * **Timeout**: Maximum time for LLM calls (in seconds)
* **authored_by**: `system` or username - who originally created this
* **last_edited_by**: `system` or username - who last modified this
* Time related fields
  * created_at
  * updated_at
  * last_run_at
* Cy Script Summary Stats
  * List of other tasks called within this task (Cy language doesn’t support this yet, but it will in the figure)
  * List of native tools is using
  * List of MCP tools is using
  * List of artifacts it generates

Note: We are going to have a dedicated entity for the Knowledge Dependency Graph that will capture the relationships between Tasks and KUs, thus we do not explicitly list those here.

#### Suggested Db field names

Simple Fields

* id (PK)
* name
* description
* directive: System message for LLM calls
* script: Cy script content
* function: summarization, planning, etc.
* scope: input, processing, or output (single value)
* status: `enabled` or `disabled`
* schedule: Cron expression (optional)
* llm_config: JSON object with LLM settings
  * default_model: Primary LLM model (e.g., "gpt-4")
  * fallback_models: Array of backup model names
  * temperature: Float 0.0-1.0
  * max_tokens: Integer
  * timeout_seconds: Integer
* categories: Array of tags
* version: Semantic version
* authored_by: `system` or username - who originally created this
* last_edited_by: `system` or username - who last modified this
* created_at: Timestamp
* updated_at: Timestamp
* last_used_at: Timestamp of last usage

### Example Tasks

* **Convert Splunk Notable to our internal Alert Representation**
  * Scope: Input
  * Function: Data Conversion
  * Categories: Splunk Notable, Splunk Enterprise Security
  * Description: Transforms Splunk Notable events into standardized alert format
  * Status: enabled
  * Authored_by: system

* **Summarize a Palo Alto THREAT Event**
  * Scope: Processing
  * Function: Summarize
  * Categories: Palo Alto, AI
  * Description: Condenses Palo Alto THREAT logs into actionable summaries
  * Status: enabled
  * Authored_by: system

* **Summarize a VirusTotal report**
  * Scope: Processing
  * Function: Summarize
  * Categories: VirusTotal, AI, Threat Intelligence
  * Description: Extracts key findings from VirusTotal scan results
  * Status: enabled
  * Authored_by: system

* **Select the proper Runbook to use for investigating a particular Alert**
  * Scope: Processing
  * Function: Search
  * Categories: AI, Composite
  * Description: Matches alerts to most relevant investigation runbooks using semantic search
  * Status: enabled
  * Authored_by: system

* **Find Alerts that are similar to the current Alert**
  * Scope: Processing
  * Function: Search
  * Categories: AI
  * Description: Identifies historical alerts with similar patterns for correlation
  * Status: enabled
  * Authored_by: system

* **Extract Artifacts from a Palo Alto Traffic event**
  * Scope: Processing
  * Function: Extraction
  * Categories: Palo Alto
  * Description: Pulls IOCs and observables from Palo Alto traffic logs
  * Status: enabled
  * Authored_by: system

* **Map our Disposition to the Disposition used by a customer**
  * Scope: Output
  * Function: Data Conversion
  * Categories: Integration
  * Description: Translates internal dispositions to customer-specific formats
  * Status: enabled
  * Authored_by: system

### Task Execution Runs ("Task Run" for short)

When a task gets executed (e.g., `POST /v1/tenant/default/tasks/{task_id}/run`) we create a record in our `task_runs` db table.
The records capture important information needed for trasparency, observability, and autidability.

When a task is added for execution, we first create a task_runs. We create Task Run ID (trid) and return that to the caller. From that point onwards this become an Async execution. The Task Run will then be assigned to an available pool of async executor threads in our Python module. As they execute the tasks they make the proper updates to the tasks run record. These Task Executor Threads for now simply execute the Cy script using the default executor. In the future, via a configuration, we can instruct them to use a different executor (like a full parallel one).

#### Task Status Polling API

**Full task run details:**
- `GET /v1/{tenant}/task-runs/{trid}` - Returns complete task run information

**Lightweight status polling:**
- `GET /v1/{tenant}/task-runs/{trid}/status` - Returns only status and updated_at for efficient polling


#### Fields

**Core Execution Fields:**
* `id` (PK) - Primary key (exposed as `trid` in API responses)
* `task_id` (FK) - References saved task (nullable for ad-hoc executions)
* `cy_script` - Stores the Cy script for ad-hoc executions (when task_id is null)
* `status` - Enum: `{running, failed, succeeded, paused_by_user}`
* `duration` - Execution time interval
* `start_time` - Timestamp when execution started
* `end_time` - Timestamp when execution completed

**Input/Output Storage Fields:**
* `input_type` - Enum: `{inline, s3, file}` - Type of input storage
* `input_location` - Text: S3 path, file path, or inline content
* `input_content_type` - Text: MIME type (application/json, text/plain, text/csv, etc.)
* `output_type` - Enum: `{inline, s3, file}` - Type of output storage
* `output_location` - Text: S3 path, file path, or inline content
* `output_content_type` - Text: MIME type for output content

**Execution Configuration:**
* `executor_config` - JSONB: Extensible configuration for executor selection and settings
  ```json
  {
    "executor_type": "default",  // or "parallel", "distributed"
    "max_workers": 4,
    "timeout_seconds": 3600,
    "priority": "normal"
  }
  ```

* `execution_context` - JSONB: Runtime context and available resources
  ```json
  {
    "available_tools": ["mcp_tool_1", "mcp_tool_2"],
    "knowledge_units": ["ku_id_1", "ku_id_2"],
    "llm_model": "gpt-4",
    "tenant_context": {...},
    "runtime_version": "cy-2.1"
  }
  ```

**Future Work:**
* `feedback` - Reserved for future implementation (thumbs up/down, comments)

## API Requirements

### Task Endpoints with Optional Relationships

Task API endpoints should support an optional query parameter `include_relationships` to include related Knowledge Units in the response:

#### Endpoints Supporting Relationships:
- `GET /v1/{tenant}/tasks?include_relationships=true`
- `GET /v1/{tenant}/tasks/{id}?include_relationships=true`

#### Response Format with Relationships:
When `include_relationships=true`, task responses include a `knowledge_units` array:

```json
{
  "tasks": [
    {
      "id": "task-uuid",
      "name": "Generate Alert Timeline",
      // ... all existing task fields ...
      "knowledge_units": [
        {
          "id": "ku-uuid",
          "name": "Crown Jewels Assets",
          "ku_type": "table"
        },
        {
          "id": "ku-uuid-2",
          "name": "Security Policies",
          "ku_type": "document"
        }
      ]
    }
  ]
}
```

#### Relationship Selection Logic:
Include Knowledge Units where the task has these KDG relationship types:
- **`uses`**: Task consumes the KU as input/context
- **`calls`**: Task invokes the KU (for tool-type KUs)

Exclude relationship types like `generates` since those represent KUs created by the task, not consumed.

#### Performance Considerations:
- Default behavior (without parameter): No relationship data included for optimal performance
- With parameter: Additional KDG joins required, acceptable for UI needs

### Details on Cy Scripts

Cy is a domain-specific language designed for building AI agents to analyze, prioritize, and resolve cybersecurity alerts within the Analysi Security platform. Purpose-built for orchestrating LLM-based workflows, Cy provides a secure alternative to executing arbitrary Python scripts in SaaS environments by constraining behavior and enabling policy auditing. The language features a Bash and Python-inspired syntax with distinctive dollar-sign variable references, comprehensive control flow (if/elif/else, while loops, returns), mathematical and boolean operations, string interpolation with nested expressions, and robust data structure support including lists, dictionaries, and complex indexing. Cy programs compile into structured Task Execution Plans—graph-based representations that can be interpreted sequentially or converted into parallel DAGs—while supporting native utility functions, LLM-powered functions for agentic workflows, and remote tool integration via Model Context Protocol servers, making it ideal for creating dynamic, interactive directives that guide AI agents through complex cybersecurity analysis tasks.

Example:

```cy
#!cy 2.1
// Cybersecurity Alert Analyzer - Cy Language Demo

// Data structures and variables
$alert = {
    "severity": 65,
    "type": "intrusion_attempt",
    "ips": ["192.168.1.50", "10.0.0.23"],
    "affected": [
        {"host": "web-01", "risk": 78},
        {"host": "db-01", "risk": 92}
    ]
}

// Mathematical operations and boolean logic
$threshold = 75
$time_multiplier = 1.2
$final_score = $alert["severity"] * $time_multiplier
$is_critical = $final_score >= $threshold

// Control flow with nested structures
$priority = "LOW"
$systems_at_risk = 0
if ($is_critical) {
    $priority = "HIGH"
    // Count high-risk systems using while loop
    $i = 0
    while ($i < 2) {
        if ($alert["affected"][$i]["risk"] > 75) {
            $systems_at_risk = $systems_at_risk + 1
        }
        $i = $i + 1
    }
}

// String operations and interpolation
$source_ip = $alert["ips"][0]
$highest_risk = $alert["affected"][1]["host"]
$highest_risk_score = $alert["affected"][1]["risk"]
$summary = "Alert: " ++ $alert["type"] ++ " from " ++ $source_ip

// Output with multiple formats
$output = """
🔒 Security Alert Analysis
Priority: ${priority} | Score: ${final_score}
Type: ${alert.type}
Source: ${source_ip}
Critical Systems: ${systems_at_risk}
Highest Risk: ${highest_risk} at ${highest_risk_score}% risk
Affected Systems: ${alert.affected|csv}
"""
```

###

### Versioning

We want to support versioning for Task and in the future we want to have multiple versions of a Task enabled.

**Ideas**: To support multiple concurrent versions of a Task, we separate the core Task definition from its versions. Each Task acts as a container for its versions, which are stored independently. Every version includes metadata such as whether it’s active, in testing, or the default version used by the system. This allows customers to create and test new versions without affecting the current default. Multiple versions can be marked as active simultaneously, enabling gradual rollouts, side-by-side testing, and explicit version selection during execution. Only one version is designated as the default, ensuring consistent behavior when a specific version isn’t specified.

### Relationships

* Many-to-many with KUs, KMs, and other Tasks

### Task Execution API Reference

Concrete endpoints for executing Tasks asynchronously and polling for
results. Both saved tasks and ad-hoc Cy scripts return `202 Accepted`
immediately with a Task Run ID (`trid`) plus a `Location` header the
client can use for status polling.

| Verb | Path | Purpose |
|------|------|---------|
| `POST` | `/v1/{tenant}/tasks/{task_id}/run` | Run a saved task |
| `POST` | `/v1/{tenant}/tasks/run` | Run an ad-hoc Cy script |
| `GET`  | `/v1/{tenant}/task-runs/{trid}/status` | Lightweight status check |
| `GET`  | `/v1/{tenant}/task-runs/{trid}` | Full run details (input, output, context) |

**Run request body** (both POST variants accept `input` and optional
`executor_config`; the ad-hoc variant additionally requires `cy_script`):

```json
{
  "input": { "message": "Alert data to process", "severity": "high" },
  "executor_config": { "timeout_seconds": 60 }
}
```

**Status values:** `running`, `succeeded`, `failed`, `paused_by_user`.

#### Storage strategy

The API selects storage by payload size:

- **< 512 KB** — stored inline in `input_location` / `output_location`
  (JSON-encoded string with `*_content_type = application/json`).
- **≥ 512 KB** — stored in S3; location fields contain an S3 path.

The UI should branch on `output_type` (`inline` vs `s3`) when parsing.

#### Polling pattern

1. Submit the run, capture `trid` and the `Retry-After` header.
2. Poll `/task-runs/{trid}/status` until `status != "running"`.
3. On terminal status, fetch full details from `/task-runs/{trid}` and
   parse `output_location` according to `output_type`.

Respect `Retry-After` and consider exponential backoff on failures.
`execution_context` on the full-details response exposes the LLM model,
available tools, KU bindings, and runtime version for debugging.

## Knowledge Units (KUs)

Knowledge Units are specialized components that provide reusable data, capabilities, and tools for Tasks. All KUs inherit from the Component base class (with kind='ku') and have an intermediate KU table that stores the ku_type discriminator. There are four types of KUs: Tables, Documents, Tools, and Indexes.

### KU Inheritance Structure

All KUs inherit common fields from the Component base class and add a KU-specific discriminator:

**From Component base class:**
- All the common fields listed above (id, name, description, version, status, visible, system_only, app, categories, authored_by, last_edited_by, timestamps)

**KU-specific field:**
- **ku_type**: Enum discriminator (`table`, `document`, `tool`, `index`) — stored in the intermediate KU table


## Tables

Tabulated lists of structured information (think JSON lists) that can be referenced to by Cy Scripts or used as default Context by Tasks. Some examples of tables include:

* List of admins
* List of crown jewels
* Domain controllers
* Internal IP ranges
* Departing employees
* Allowed listed software
* Watchlists

When a Table is imported in a Cy Script is treated as a List of Structures. In a Cy script, the can also serve as lookup tables, enriching other data (a form of a JOIN operation).

~~List can only include Vector information to be searchable via embedding similarity. Examples are:~~

* ~~Runbooks~~
* ~~Historical Alerts~~
* ~~Task Specific Examples~~

### Table-Specific Fields

Tables inherit from Component (via KU) and add:

* **content**: Everything as a JSON encoded document
* **file_path**: An S3 or DB location where the file is stored (we want to avoid storing large documents in the database in the future)
* **row_count**: Number of rows in the table
* **column_count**: Number of columns in the table
* **schema**: JSON schema defining the table structure

Deprecated fields that now belong to Indexes:

* ~~data\_type (tabular vs vector-based)~~
* ~~embedding\_metadata (optional if vector)~~
* ~~source\_document\_id to track provenance for tables auto-generated from a doc (good for audit/logging).~~
* ~~authored\_by (system vs. user-generated)~~
* ~~Embedding to make it searchable (on description)~~
* ~~Embedding on content (periodically updated, good for infrequent updates)~~

### Relationships

* Many-to-many with Task
* Many-to-many with KUs:
  * Data transformation lineage is also captured. For example, when a document is converted to a Table, or a Table to an Index, etc.

## Tools

Tasks can use tools to achieve their goals. All tools are defined using the Model Context Protocol (MCP) standard. Users can define new Tools and allow tasks to use them.  New tools need to be explicitly added to tasks in order to be usable by them.

### Specific Metadata for Tools

- `Type: mcp, native 19419 Stevens Creekmcv`
- `integration_id` (optional, for audit/inventory). If this tool became possible because of an integration, e.g., with Splunk. Note that this information needs not be a field under tools. It could as well be under the integrations table (future work).

### Tool-Specific Fields

Tools inherit from Component (via KU) and add:

* **tool_type**: Enum - `mcp` (Model Context Protocol) or `native` (built-in)
* **mcp_endpoint**: URL/connection string for MCP tools (null for native tools)
* **mcp_server_config**: JSON configuration for MCP server connection
* **input_schema**: JSON schema defining expected input parameters
* **output_schema**: JSON schema defining expected output format
* **auth_type**: Enum - `none`, `api_key`, `oauth`, `basic`
* **credentials_ref**: Encrypted storage reference for authentication data
* **timeout_ms**: Maximum execution time in milliseconds
* **rate_limit**: Requests per minute allowed
* **integration_id**: Foreign key to integrations table (optional)

### ~~Fields~~

* ~~id (PK)~~
* ~~name~~
* ~~Description~~
* ~~Mcp\_endpoint~~
* ~~authored\_by (system vs. user-generated)~~
* ~~source\_document\_id to track provenance for tables auto-generated from a doc (good for audit/logging)~~
  * ~~This is typically via an Integration~~

### Relationships

* many-to-many with Task

## Documents

Documents serve as broader, referenceable sources of contextual knowledge. They are primarily used to provide supporting information, such as policy documents, playbooks, or vendor manuals.

Raw Documents are unstructured textual resources (e.g., PDFs, pasted text, extracted web content) that can be referenced by Tasks. Raw Documents are always normalized to Markdown documents to be able to be consumed by Tasks.

### Document-Specific Fields

Documents inherit from Component (via KU) and add:

* **doc_format**: Enum - `raw` (original format) or `normalized` (converted to Markdown)
* **content**: Text content for small documents (< 1MB)
* **file_path**: S3 or filesystem path for large documents
* **document_type**: Enum - `pdf`, `markdown`, `html`, `plaintext`, `docx`, `txt`
* **content_source**: Enum - `upload`, `api`, `integration`, `generated`
* **source_url**: Original URL if fetched from web (optional)
* **markdown_content**: Normalized Markdown representation
* **metadata**: JSON object with document-specific metadata
* **word_count**: Number of words in the document
* **character_count**: Number of characters in the document
* **page_count**: Number of pages (for PDFs)
* **language**: Primary language of content (ISO 639-1 code)

### Relationships

* many-to-many with Task
* Many-to-many with KUs:
  * Data transformation lineage is also captured. For example, when a document is converted to a Table, or a Table to an Index, etc.

## Indexes

When Tables and Documents become too large or contain a diverse set of Knowledge, they can be added to a semantic search Index. This typically involved chunking the document, creating embeddings, and storing the vectors and the chunks into a Vector Database.

Indexes can be used in Cy Scripts for RAG.

We plan to support different type of indexes:

* Simple RAG
* Graph RAG

Indexes can also be merged to form larger simple RAG or Graph RAG indexes.

### Index-Specific Fields

Indexes inherit from Component (via KU) and add:

* **index_type**: Enum - `simple_rag`, `graph_rag` (for future expansion)
* **vector_database**: Enum - `pinecone`, `weaviate`, `qdrant`, `pgvector`
* **embedding_model**: Model used for vectorization (e.g., `text-embedding-ada-002`)
* **embedding_dimensions**: Integer - dimension of embedding vectors
* **chunk_size**: Number of tokens per chunk
* **chunk_overlap**: Number of overlapping tokens between chunks
* **query_config**: JSON configuration for retrieval parameters
* **build_status**: Enum - `building`, `ready`, `updating`, `failed`
* **storage_location**: S3 or filesystem path for index data

### Relationships

* many-to-many with Task
* Many-to-many with KUs:
  * Data transformation lineage is also captured. For example, when a document is converted to a Table, or a Table to an Index, etc.

## Knowledge Dependency Graph (KDG)

Graph that captures the relationships between Tasks and Knowledge Units (KUs). They serve in two ways:

* **Documentation**: Visually they explain the information path from source (e.g., Raw Documents) to the Tasks that use it.
* **Text Context**: When a Task is executed, the graph is used to define the type of tools and documents that become available to all the LLM calls within the Cy Script of the Tasks.
  * This is part of the Task Execution Service that we have not implemented yet and is part of future work.

### Database Schema

The KDG is stored as a directed graph using an edge table that captures relationships between nodes (Tasks and KUs).

#### KDG Edges Table
Stores the relationships between components:

* id (PK)
* tenant_id: UUID - tenant isolation (indexed)
* source_id: UUID of the source component
* target_id: UUID of the target component
* relationship_type: Enum - controlled set of relationship types
* is_required: Boolean - whether this dependency is mandatory
* execution_order: Integer - for relationships that imply sequence (optional)
* authored_by: `system` or username - who created this edge
* created_at: Timestamp
* updated_at: Timestamp

#### Relationship Types

Controlled enum of allowed relationship types:

* **`uses`**: Component uses another component as input/context
* **`generates`**: Component creates/outputs another component
* **`updates`**: Component modifies an existing component
* **`calls`**: Task invokes another Task
* **`transforms_into`**: Component is converted into another component
* **`summarizes_into`**: Document/Table is summarized into another component
* **`indexes_into`**: Document/Table is indexed into an Index
* **`derived_from`**: Component is derived/extracted from another component
* **`enriches`**: Component adds information to another component


### Examples

**Example 1: Alert Severity Assessment Workflow**
```
Task: "Assess Alert Severity"
├── Uses: Table "Crown Jewels Assets"
├── Uses: Table "Critical Systems Inventory"
├── Uses: Document "Security Policy Thresholds"
├── Uses: Tool "Query Asset Database" (MCP)
└── Generates: Document "Severity Assessment Report"
```

**Example 2: Threat Intelligence Enrichment Pipeline**
```
Document: "Raw Threat Feed" (PDF)
├── Summarized into → Table: "IOC Watchlist"
│   └── Used by → Task: "Enrich Alert with Threat Intel"
└── Chunked into → Index: "Threat Intelligence RAG"
    └── Used by → Task: "Find Related Threats"
```

**Example 3: Incident Response Runbook Selection**
```
Task: "Select Appropriate Runbook"
├── Uses: Index "Runbook Library" (Graph RAG)
├── Uses: Table "Historical Alert Patterns"
├── Uses: Tool "Query SIEM" (MCP)
├── Calls: Task "Summarize Alert Context"
│   └── Uses: Document "Alert Triage Guidelines"
└── Generates: Table "Recommended Actions"
```

**Example 4: Compliance Verification Chain**
```
Document: "NIST Framework"
├── Transformed into → Table: "Compliance Controls"
│   └── Used by → Task: "Map Controls to Assets"
│       ├── Uses: Table "Asset Inventory"
│       └── Generates: Document "Compliance Gap Analysis"
└── Added to → Index: "Compliance Knowledge Base"
    └── Used by → Task: "Generate Audit Report"
```

**Example 5: Alert Investigation Flow**
```
Task: "Investigate Security Alert"
├── Uses: Tool "Query Splunk" (MCP)
├── Uses: Index "Historical Alerts" (Simple RAG)
├── Calls: Task "Extract IOCs from Alert"
│   └── Generates: Table "Alert IOCs"
│       └── Used by → Task: "Check Threat Intelligence"
│           ├── Uses: Tool "Query VirusTotal API" (MCP)
│           └── Uses: Table "Known Bad Actors"
└── Generates: Document "Investigation Report"
    └── Summarized into → Table "Investigation Summary"
```

## Database Implementation Notes

The Component-based architecture uses Class Table Inheritance (CTI) with the following schema structure:

### Core Tables

```sql
-- Base component table
component(
    id uuid pk,
    tenant_id uuid not null,
    kind text check(kind in ('task','ku')),
    name text not null,
    description text,
    version text,
    status text check(status in ('enabled','disabled')) default 'enabled',
    visible boolean default false,
    system_only boolean default false,
    app text default 'default',
    categories text[] default '{}',
    authored_by text,
    last_edited_by text,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    last_used_at timestamptz
);

-- Tasks (when component.kind='task')
task(
    component_id uuid pk references component(id) on delete cascade,
    directive text,
    script text,
    function text,
    scope text,
    schedule text,
    llm_config jsonb
);

-- KU intermediate table (when component.kind='ku')
ku(
    component_id uuid pk references component(id) on delete cascade,
    ku_type text check(ku_type in ('table','document','tool','index'))
);

-- KU subtypes
ku_table(
    component_id uuid pk references ku(component_id) on delete cascade,
    schema jsonb,
    row_count int,
    column_count int,
    content jsonb,
    file_path text
);

ku_document(
    component_id uuid pk references ku(component_id) on delete cascade,
    doc_format text,
    content text,
    file_path text,
    markdown_content text,
    metadata jsonb
);

ku_tool(
    component_id uuid pk references ku(component_id) on delete cascade,
    tool_type text check(tool_type in ('mcp','native')),
    mcp_endpoint text,
    mcp_server_config jsonb,
    input_schema jsonb,
    output_schema jsonb,
    auth_type text,
    credentials_ref text,
    timeout_ms int,
    rate_limit int,
    integration_id uuid
);

ku_index(
    component_id uuid pk references ku(component_id) on delete cascade,
    index_type text,
    vector_database text,
    embedding_model text,
    embedding_dimensions int,
    chunk_size int,
    chunk_overlap int,
    query_config jsonb,
    build_status text,
    storage_location text
);

-- Knowledge Dependency Graph edges
kdg_edge(
    id uuid pk,
    tenant_id uuid not null,
    source_id uuid not null references component(id),
    target_id uuid not null references component(id),
    relationship_type text check(relationship_type in (
        'uses', 'generates', 'updates', 'calls', 'transforms_into',
        'summarizes_into', 'indexes_into', 'derived_from', 'enriches'
    )) not null,
    is_required boolean default false,
    execution_order int,
    authored_by text,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

-- Task execution runs table (partitioned by day)
task_runs(
    id uuid pk,  -- Exposed as 'trid' in API responses
    tenant_id varchar(255) not null,
    task_id uuid references task(component_id),
    cy_script text,  -- For ad-hoc executions when task_id is null
    status text check(status in ('running', 'failed', 'succeeded', 'paused_by_user')) not null,
    duration interval,
    start_time timestamptz,
    end_time timestamptz,
    -- Input/Output storage with content-type awareness
    input_type text check(input_type in ('inline', 's3', 'file')),
    input_location text,
    input_content_type text,  -- MIME type (application/json, text/plain, etc.)
    output_type text check(output_type in ('inline', 's3', 'file')),
    output_location text,
    output_content_type text,  -- MIME type for output content
    -- Execution configuration
    executor_config jsonb,  -- Executor type and settings
    execution_context jsonb,  -- Runtime context (tools, KUs, LLM model, etc.)
    -- Metadata
    created_at timestamptz default now() not null,  -- Required for partitioning
    updated_at timestamptz default now()
    -- feedback jsonb -- Reserved for future work
) PARTITION BY RANGE (created_at);

-- Example partition creation (automated in production)
CREATE TABLE task_runs_2025_08_13 PARTITION OF task_runs
    FOR VALUES FROM ('2025-08-13 00:00:00') TO ('2025-08-14 00:00:00');

-- Automatic partition management should be implemented via:
-- 1. pg_partman extension for auto-creation
-- 2. Scheduled job to create future partitions
-- 3. Retention policy to drop old partitions (e.g., after 90 days)
```

### Recommended Indexes

```sql
-- Tenant isolation indexes (critical for multi-tenant performance)
CREATE INDEX idx_component_tenant_id ON component(tenant_id);
CREATE INDEX idx_kdg_edge_tenant_id ON kdg_edge(tenant_id);
CREATE INDEX idx_task_runs_tenant_id ON task_runs(tenant_id);

-- Task runs query performance (indexes on partitioned table)
CREATE INDEX idx_task_runs_status ON task_runs(status);
CREATE INDEX idx_task_runs_task_id ON task_runs(task_id);
CREATE INDEX idx_task_runs_created_at ON task_runs(created_at);  -- Partition key index

-- Query performance indexes
CREATE INDEX idx_component_kind_status ON component(kind, status);
CREATE INDEX idx_component_app_categories ON component(app, categories);
CREATE INDEX idx_ku_type ON ku(ku_type);

-- Updated timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ language 'plpgsql';

CREATE TRIGGER update_component_updated_at BEFORE UPDATE
ON component FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_kdg_edge_updated_at BEFORE UPDATE
ON kdg_edge FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

### Future Work: Row Level Security (RLS)

For production multi-tenancy, consider implementing Row Level Security:
- Enable RLS on `component` and `kdg_edge` tables
- Create policies to automatically filter by `tenant_id`
- Use session variables or JWT claims to set tenant context
- Add composite indexes like `(tenant_id, kind, status)` for optimal query performance
