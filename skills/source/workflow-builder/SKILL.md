---
name: workflow-builder
description: Build and manage Analysi Security Workflows using DAG-based composition. Use when creating workflow pipelines, chaining tasks together, orchestrating security operations, or building alert processing workflows. Requires familiarity with the task-builder skill for task creation.
dependencies:
  - task-builder
---

# Analysi Workflow Builder

## Overview

Build production-ready security workflow pipelines for the Analysi platform. Workflows are directed acyclic graphs (DAGs) that chain together Tasks and Transformations to automate complex security operations like alert enrichment, threat correlation, and incident response.

**Prerequisites:**
- Familiarity with Tasks (use `task-builder` skill for task creation)
- Understanding of DAG concepts (nodes, edges, data flow)

## Development Pattern: Compose First, Iterate to Fix

**The recommended workflow for building workflows:**

```
1. compose_workflow  → Create initial workflow structure
2. run_workflow      → Test with sample data
3. If issues found:
   - remove_workflow_node / remove_workflow_edge  → Remove problematic parts
   - add_workflow_node / add_workflow_edge        → Add corrections or new nodes
4. run_workflow      → Re-test
5. Repeat until all test cases pass
```

**Why this pattern?**
- `compose_workflow` handles 90% of cases (auto-wiring, validation, schema inference)
- Mutation tools handle edge cases without recreating the entire workflow
- Faster iteration than deleting and recreating workflows

**Key Parameters:**
- `node_label` - Node identifier within workflow
- `task_id_or_cy_name` - Task reference (cy_name like `"alert_context_generation"` preferred!)
- `from_node` / `to_node` - Edge connection endpoints

## Workflow Philosophy: Progressive Contextualization

Workflows orchestrate the journey of security alerts from raw events to actionable conclusions through **progressive contextualization** - each task adds layers of context to the OCSF Detection Finding, building toward a final disposition decision.

### The Alert Progression Pattern

Analysi workflows process OCSF alerts through these stages:

1. **Context Generation** (Start with Text): Begin with a textual summary of the alert for human understanding and downstream AI context
2. **🔍 Evidence Retrieval** (CRITICAL - Get Ground Truth): Retrieve raw SIEM events (triggering + supporting) to validate hypotheses about what actually happened
3. **Enrichment** (Add Data): Parallel tasks enrich the alert with threat intelligence, user data, asset context, endpoint telemetry
4. **Correlation** (Analyze): Merge enriched data and correlate risk factors across multiple dimensions
5. **Disposition** (Conclude): Final determination (true positive, false positive, benign) with confidence level and recommended actions

**Why Evidence Retrieval comes BEFORE external enrichment:**
- External threat intel tells you what an IP/domain/hash might be
- SIEM events tell you what it DID in YOUR environment
- Pattern detection requires correlation across YOUR event timeline
- Success/failure determination requires YOUR log data (response codes, execution results)

### Design Principles

**Each task adds context, never replaces it**: Tasks don't overwrite data - they enrich the alert's `enrichments` dict. The alert grows richer with each node, preserving the full investigation trail.

**Start with textual summary**: The first task typically generates a human-readable summary of the alert. This provides:
- Context for analysts who review the workflow output
- Background for downstream AI-powered tasks to better understand their role
- A consistent starting point regardless of alert source format

**Identify parallel execution opportunities**: Independent enrichment tasks (user lookup, IP reputation, endpoint query, SIEM correlation) run concurrently for speed. If tasks don't depend on each other's output, execute them in parallel.

**Merge sub-analyses before final decision**: Fan-in patterns combine parallel enrichment results into a complete picture. The `system_merge` template intelligently combines enrichments from multiple branches into a single enriched alert.

**Build toward disposition conclusion**: Every alert processing workflow has a goal - typically determining alert disposition with confidence score, risk assessment, and recommended response actions.

### Example: Login Risk Assessment Workflow

```
Alert → Generate Summary → [Splunk Triggering Event, Splunk Supporting Evidence] → Merge → [User AD Lookup, IP Reputation Check] → Merge → Correlate Risk Factors → Determine Disposition
```

**Flow breakdown:**
- **Start**: Generate readable summary: "User jsmith logged in from 185.220.101.45 at 3:47 AM"
- **Evidence Retrieval** (Parallel):
  - Branch A: Get triggering login event from SIEM with full details (timestamp, geolocation, user agent)
  - Branch B: Search for supporting evidence (previous logins from this IP, failed attempts, session duration)
- **Merge**: Combine SIEM event data
- **External Enrichment** (Parallel):
  - Branch A: Query AD LDAP for user privilege level, department, group memberships
  - Branch B: Query VirusTotal and AbuseIPDB for IP reputation
- **Merge**: Combine user context and IP reputation into single enriched alert
- **Analyze**: Correlate findings: High-privilege user + malicious IP + multiple failed attempts = critical risk
- **Conclude**: Disposition = "True Positive, Critical", recommend immediate password reset and account review

### Why This Matters

This pattern enables:
- **Composable workflows**: Tasks are reusable across different alert types
- **Efficient processing**: Parallel enrichment reduces total workflow execution time
- **Complete context**: Final disposition has full investigation trail for audit and review
- **Consistent quality**: Every alert follows the same rigorous analysis pattern

See the **task-builder** skill for guidance on creating Tasks that follow additive enrichment patterns.

## When to Use This Skill

Use this skill when:
- Chaining multiple tasks into automated workflows
- Building alert processing pipelines (enrichment → analysis → disposition)
- Creating multi-step security operations (investigate → correlate → respond)
- Orchestrating parallel enrichment from multiple threat intel sources
- Composing reusable workflow patterns

**Do NOT use this skill for:**
- Creating individual tasks (use `task-builder` instead)
- One-off task execution (execute tasks directly)

## Core Capabilities

### 1. Workflow Composition

#### High-Level: `compose_workflow` (Recommended)

Simple array-based syntax with automatic validation:
```json
{
  "composition": ["identity", "task1", ["task2", "task3"], "merge", "task4"],
  "name": "My Workflow",
  "description": "...",
  "tenant": "default"  // "default" for single-tenant; use org ID for multi-tenant
}
```

**Benefits:**
- Auto-resolves task cy_names
- Validates types automatically
- Detects cycles and errors
- Generates helpful error messages

**Composition Syntax:**
- `"task_cy_name"` - Task node by cy_name (recommended as first node)
- `["task1", "task2"]` - Parallel fan-out
- `"merge"` - Combine multiple objects into one
- `"collect"` - Aggregate into array
- `"identity"` - Pass-through (avoid as first node, use mid-workflow only)

#### Low-Level: `create_workflow` (Dropped)

**Note:** `create_workflow` has been replaced by `compose_workflow`. Use `compose_workflow` for all workflow creation. The low-level `create_workflow` tool is no longer recommended.

### 2. Task Discovery

#### Progressive Disclosure Pattern

**Step 1:** Browse lightweight task summaries
```json
// MCP: list_tasks
{
  "tenant": "default",
  "function": "enrichment"  // Optional filter
}
```

Returns task metadata (id, cy_name, name, description, function, scope) without scripts.

**Step 2:** Get full details for selected tasks
```json
// MCP: get_task
{
  "tenant": "default",
  "task_ids": ["ip_reputation_enrichment", "user_privilege_enrichment"]
}
```

Returns complete task details including Cy scripts.

### 3. Workflow Discovery

Before creating a new workflow, browse existing workflows to check if one already exists that meets your needs.

#### List Existing Workflows

**Tool**: `list_workflows`

Returns thin representations of all workflows with composition arrays and metadata.

```json
// MCP: list_workflows
{
  "limit": 10  // Optional: limit number of results
}
```

**Returns**:
```json
{
  "workflows": [
    {
      "workflow_id": "uuid-string",
      "name": "IP Threat Enrichment",
      "description": "Enriches IP with VirusTotal and AbuseIPDB",
      "composition": ["alert_context_generation", ["virustotal_ip_reputation", "abuseipdb_ip_check"], "merge"],
      "created_by": "analyst",
      "created_at": "2025-10-29T10:00:00Z",
      "status": "active"
    }
  ],
  "total": 15
}
```

**Composition Format** (as of Phase 35):
- Task nodes appear as **cy_names** (e.g., `"alert_context_generation"`)
- Template nodes appear as **shortcuts** (e.g., `"identity"`, `"merge"`, `"collect"`)
- Parallel branches preserved as **nested arrays** (e.g., `["task1", ["task2", "task3"], "merge"]`)
- This makes workflows immediately readable without additional lookups!

#### Progressive Disclosure for Workflows

To get the full picture of a workflow:

**Step 1:** Browse thin representations
```json
list_workflows({"limit": 20})
```

**Step 2:** Get full workflow details (includes task relationships)
```json
get_workflow({
  "workflow_id": "uuid-from-step-1",
  "include_validation": true,
  "slim": true  // Default for MCP (optimized for LLMs)
})
```

**Slim Mode** (as of Phase 35):
- **MCP default**: `slim=true` - Returns minimal verbosity response optimized for LLM consumption
- **REST API default**: `slim=false` - Full details for backward compatibility (use `?slim=true` query param)
- **Slim response** removes: timestamps, database UUIDs, template code, verbose schemas
- **Slim response** keeps: node_id, kind, name, identifier (cy_names), edges
- Reduces 15-node workflow from ~1500 lines to ~200 lines

**Example slim response**:
```json
{
  "id": "workflow-uuid",
  "name": "Alert Analysis Workflow",
  "status": "draft",
  "nodes": [
    {"node_id": "context_gen", "kind": "task", "name": "Context Generation", "identifier": "alert_context_generation"},
    {"node_id": "merge1", "kind": "transformation", "name": "Merge", "identifier": "merge"}
  ],
  "edges": [
    {"from": "context_gen", "to": "merge1"}
  ]
}
```

This returns complete node definitions including task cy_names via the `identifier` field.

**Step 3:** Fetch task scripts

**Batch lookup (analysi MCP):**
```json
get_task({
  "task_ids": ["vt_ip_reputation", "abuse_ip_check"]
})
```

**Individual lookup (analysi MCP):**
```json
get_task({
  "task_ids": ["vt_ip_reputation"]
})
```

#### When to Use Workflow Discovery

- **Before creating workflows**: Check if similar workflow exists
- **Code reuse**: Find workflows with similar patterns to replicate
- **Understanding system**: Browse existing automation pipelines
- **Refactoring**: Identify workflows that can be consolidated

#### Example: Complete Workflow Discovery Flow

```json
// 1. Browse existing workflows (cy_names visible in composition!)
list_workflows({})

// Response shows composition with readable cy_names:
// "composition": ["alert_context_generation", ["virustotal_ip_reputation", "abuseipdb_ip_check"], "merge"]

// 2. Get slim workflow details (default for MCP)
get_workflow({
  "workflow_id": "alert-analysis-uuid",
  "include_validation": true
  // slim=true is default for MCP
})

// Response shows nodes with cy_names in identifier field:
// {"node_id": "context_gen", "identifier": "alert_context_generation", ...}

// 3. Get task scripts (batch) - use cy_names from composition or identifier field
get_task({
  "task_ids": ["alert_context_generation", "virustotal_ip_reputation", "abuseipdb_ip_check"]
})

// Complete picture retrieved:
// - Workflow structure visible in composition array (step 1)
// - Minimal node details from slim response (step 2)
// - Full task scripts and logic (step 3)
```

### 4. System Templates (Built-in)

Analysi provides three built-in transformation templates that handle common data flow patterns. These are **system templates** - custom templates cannot be created, only these existing ones can be used.

**List available templates:**
```json
// MCP: list_templates
{
  "tenant": "default",
  "kind": "identity"  // Optional filter: identity, merge, collect
}
```

#### Template Reference

**`system_identity` (Shortcut: `"identity"`)**
- **Purpose**: Pass-through transformation, no changes to data
- **Type**: T → T (input type equals output type)
- **When to use**:
  - Mid-workflow placeholders
  - Testing data flow
  - **Avoid as first node** - always start with a Task instead
- **Example composition**: `["task1", "identity", "task2"]`

**`system_merge` (Shortcut: `"merge"`)**
- **Purpose**: Combine multiple objects from parallel branches into single object
- **Type**: [T1, T2, ...] → Object (fan-in: array of objects → merged object)
- **Merge behavior**:
  - First item in array = base (inherited from parent node)
  - Subsequent items = modifications from parallel branches
  - Field-level conflict detection: error if multiple branches modify same field
  - Deletions allowed: branches can omit fields to delete them
  - Agreement on deletions: multiple branches deleting same field = OK (no conflict)
- **When to use**:
  - After parallel branches that enrich different fields
  - Fan-in pattern where each branch adds/modifies different data
  - Diamond pattern: split → parallel processing → merge back
- **Example composition**: `["task1", ["task2", "task3"], "merge", "task4"]`
- **Conflict example**:
  ```json
  // Base: {a: 1}
  // Branch A: {a: 2, b: 2}  (modifies 'a', adds 'b')
  // Branch B: {a: 3, c: 3}  (modifies 'a', adds 'c')
  // Result: ERROR - both branches modified 'a'
  ```
- **Success example**:
  ```json
  // Base: {ip: "1.2.3.4"}
  // Branch A: {ip: "1.2.3.4", reputation: "malicious"}  (adds 'reputation')
  // Branch B: {ip: "1.2.3.4", geolocation: "US"}  (adds 'geolocation')
  // Result: {ip: "1.2.3.4", reputation: "malicious", geolocation: "US"}
  ```

**`system_collect` (Shortcut: `"collect"`)**
- **Purpose**: Aggregate multiple results into an array
- **Type**: [T1, T2, ...] → Array (fan-in: multiple items → array of items)
- **When to use**:
  - Collecting results from parallel branches for iteration
  - Building arrays of enrichment results
  - Aggregating multiple threat intel lookups
- **Example composition**: `["task1", ["task2", "task3"], "collect", "task4"]`
- **Output format**: `[result2, result3]` (array of all branch results)

#### Template Usage in Compose vs Create

**With `compose_workflow` (recommended):**
Use lowercase shortcuts directly in composition array:
```json
{
  "composition": ["task1", ["task2", "task3"], "merge", "task4"]
}
```

**Template shortcuts in `compose_workflow`:**
Use template names directly in the composition array — no UUIDs needed:
```json
{
  "composition": ["identity", "task1", ["task2", "task3"], "merge", "task4"]
}
```

Available shortcuts: `"identity"`, `"merge"`, `"collect"`.
Use `list_templates()` to discover all available templates.

### 5. Type Validation

All workflows must meet strict requirements:

#### Entry Node Requirement

**Exactly ONE** entry node with `is_start_node: true`.

Valid kinds: `transformation` (with `node_template_id`) OR `task` (with `task_id`)

#### Input Schema Requirement

Must define concrete `properties`:

❌ Invalid:
```json
{"io_schema": {"input": {"type": "object"}}}
```

✅ Valid:
```json
{
  "io_schema": {
    "input": {
      "type": "object",
      "properties": {
        "observables": {"type": "array"},
        "severity": {"type": "string"}
      },
      "required": ["observables"]
    }
  }
}
```

#### Data Samples Requirement

Provide at least one sample matching input schema:
```json
{
  "data_samples": [{
    "observables": [{"value": "192.168.1.100", "type": "IP Address"}],
    "severity": "high"
  }]
}
```

See **references/type_validation.md** for complete requirements.

#### Data Samples Structure Convention

**IMPORTANT**: Both Tasks and Workflows use the same standardized test metadata wrapper structure for `data_samples`:

```json
{
  "data_samples": [
    {
      "name": "Test case descriptive name",
      "input": {
        "observables": [{"value": "192.168.1.100", "type": "IP Address"}],
        "enrichments": {}
      },
      "description": "What this test case validates",
      "expected_output": {
        "enrichments": {"...": "..."}
      }
    }
  ]
}
```

**Key Points:**
- `input` - The **actual runtime data** that executes (required) - this is what Tasks/Workflows receive
- `name` - Test case name for identification (metadata only)
- `description` - Test case purpose documentation (metadata only)
- `expected_output` - Expected result for validation (metadata only)

**Runtime Behavior:**
- At execution time, **only the `input` field content is passed** to Tasks/Workflows
- The wrapper structure (`name`, `description`, `expected_output`) is **never passed to execution**
- It exists purely for documentation, testing, and UI display purposes

**Workflow Bootstrap Pattern:**

Copy the first task's data_samples structure directly:

```json
// 1. Get first task's data_samples
get_task({"task_ids": ["alert_context_generation"]})

// 2. Copy the exact same structure to workflow
{
  "data_samples": [
    {
      "name": "Exchange CVE Exploitation - Critical Severity",
      "input": {
        "title": "PowerShell in URL - CVE-2022-41082",
        "severity": "critical",
        "raw_data": "..."
      },
      "description": "High-severity web attack",
      "expected_output": {"alert_context": "..."}
    }
  ]
}
```

**CRITICAL: Using Alerts as Data Samples**

When building workflows for alert processing:

1. **Use the provided alert** - If you're given an alert to test the workflow against, use that alert's structure as your `data_samples[].input`
2. **Always populate the IOCs list** - Many tasks depend on indicators of compromise being present in the alert:

```json
{
  "data_samples": [
    {
      "name": "SQL Injection Attack Alert",
      "input": {
        "title": "SQL Injection Detected on Web Server",
        "severity": "critical",
        "observables": [
          {
            "type": "IP Address",
            "type_id": 2,
            "value": "185.220.101.45",
            "name": "src_ip"
          },
          {
            "type": "URL String",
            "type_id": 6,
            "value": "https://example.com/api?id=1%27%20OR%20%271%27%3D%271",
            "name": "request_url"
          },
          {
            "type": "Domain Name",
            "type_id": 1,
            "value": "malicious-c2.com",
            "name": "c2_domain"
          }
        ],
        "evidences": [
          {
            "src_endpoint": {"ip": "185.220.101.45"},
            "dst_endpoint": {"ip": "10.0.0.1"}
          }
        ],
        "raw_data": "{...}"
      },
      "description": "Critical severity web attack with multiple IOCs"
    }
  ]
}
```

**Why IOCs are critical:**
- IP reputation tasks need IP addresses to look up
- Domain analysis tasks need domains to check
- Hash lookup tasks need file hashes to query
- Threat correlation tasks need all IOCs for cross-referencing
- **Without IOCs, many enrichment tasks cannot function**

**Observable Types to Include (as applicable, using OCSF type_id):**
- `IP Address` (type_id=2) - IP addresses from network traffic
- `Domain Name` (type_id=1) - Domain names from URLs, DNS queries
- `URL String` (type_id=6) - Full URLs from web requests
- `Hash` (type_id=8) - File hashes from malware/executables
- `Email Address` (type_id=5) - Email addresses from phishing attempts
- `User Agent` (type_id=18) - User agents from suspicious requests

**Schema Inference:**
- The composer automatically extracts `data_samples[].input` when inferring `io_schema.input`
- This means `io_schema.input` describes the actual runtime data structure
- Example: If `data_samples[0].input = {title: "...", severity: "..."}`, then `io_schema.input` will have `{type: "object", properties: {title: {...}, severity: {...}}}`

**API Execution Example:**
```bash
# When executing a workflow, pass ONLY the input field content
POST /v1/default/workflows/{workflow_id}/run
{
  "input_data": {
    "title": "PowerShell in URL",
    "severity": "critical",
    "raw_data": "..."
  }
}

# NOT the wrapper structure!
```

### 6. Common Workflow Patterns

#### Pattern 1: Simple Pipeline
```
Input → Transform → Task → Output
```

Use when: Sequential processing with no branching.

#### Pattern 2: Fan-out
```
Input → [Task1, Task2, Task3]
```

Use when: Multiple independent operations on same input.

#### Pattern 3: Fan-in
```
[Node1, Node2] → Merge → Aggregation
```

Use when: Combining results from multiple sources.

#### Pattern 4: Diamond
```
     → Branch1 →
Input            → Merge → Output
     → Branch2 →
```

Use when: Parallel processing paths that converge.

#### Pattern 5: The Splunk Evidence Validation Pattern (CRITICAL for Alert Workflows)

**🔍 MUST-HAVE: Splunk Event Retrieval Tasks**

For security alert workflows, **ALWAYS include BOTH Splunk tasks** to validate hypotheses about what's happening:

```python
[
    "alert_context_generation",
    # 🚨 CRITICAL: Retrieve raw events from SIEM
    [
        "splunk_triggering_event_retrieval",    # Get the specific event that triggered the alert
        "splunk_supporting_evidence_search"     # Search for related events (before/after, same source, patterns)
    ],
    "merge",
    # Now you have raw event data to validate hypotheses
    [
        "attack_payload_analysis",   # Can analyze actual payload from events
        "ip_reputation_check",
        "edr_context_enrichment"
    ],
    "merge"
]
```

**The Two Essential Splunk Tasks:**

1. **`splunk_triggering_event_retrieval`** - Retrieves the exact event(s) that triggered the alert
   - Provides ground truth: raw log data, timestamps, fields
   - Answers: "What exactly happened?"
   - Example: Gets the HTTP request with SQL injection payload

2. **`splunk_supporting_evidence_search`** - Searches SIEM for related events
   - Hypothesis-driven correlation across time windows
   - Answers: "What else was happening? Is this part of a pattern?"
   - Example: Finds other requests from same IP, response codes, error patterns

**Why BOTH are Critical:**

- **Hypothesis Validation**: Initial alert may be incomplete or noisy - raw events provide ground truth
- **Pattern Detection**: Single event might look benign; multiple events reveal attack pattern
- **Timeline Reconstruction**: Supporting evidence shows before/after context
- **False Positive Reduction**: Events that seem malicious in isolation may be normal when correlated
- **Success Assessment**: Response codes, payload execution, lateral movement all visible in logs

**Real Example - SQL Injection Investigation:**

```python
[
    "alert_context_generation",
    # Get BOTH types of evidence
    [
        "splunk_triggering_event_retrieval",    # Gets: URL with "OR 1=1--" payload
        "splunk_supporting_evidence_search"     # Finds: 6 other SQLi attempts from same IP, all HTTP 500 responses
    ],
    "merge",
    # Now we can validate: Multiple attempts + consistent 500 errors = unsuccessful attack
    "url_decode_sql_injection_analyzer",  # Decodes and analyzes the payload
    "attack_success_determination",       # Uses response codes to determine attack failed
    # ... rest of workflow
]
```

**Without Splunk Evidence:**
- Rely on external threat intel only (no context about YOUR environment)
- Miss patterns (multiple attempts, lateral movement)
- Can't determine attack success/failure
- Higher false positive rates

**Common Mistake:**
```python
# ❌ BAD: Only using external enrichment, no SIEM evidence
[
    "alert_context_generation",
    ["virustotal_ip_reputation", "abuseipdb_ip_check"],
    "merge",
    "disposition"
]

# ✅ GOOD: SIEM evidence FIRST, then external context
[
    "alert_context_generation",
    ["splunk_triggering_event_retrieval", "splunk_supporting_evidence_search"],
    "merge",
    ["virustotal_ip_reputation", "abuseipdb_ip_check"],
    "merge",
    "disposition"
]
```

#### Pattern 6: The Mandatory Triad (CRITICAL for Security Workflows)

**ALWAYS include these three tasks at the end of security alert workflows:**

1. **Detailed Analysis** (`alert_detailed_analysis`) - Runs FIRST, writes comprehensive technical breakdown with threat assessment, attack chain reconstruction, and impact analysis
2. **Disposition Determination** (`alert_disposition_determination`) - Reads detailed analysis and maps to clear verdict (True Positive, False Positive, Benign) with confidence score
3. **Summary Generation** (`alert_summary_generation`) - Reads detailed analysis and condenses to executive-friendly one-sentence summary (max 128 chars)

**Critical Sequencing:**
```
Enriched Alert → alert_detailed_analysis (Sequential - Must Complete First)
                           ↓
                    [Parallel after detailed analysis completes]
                           ↓
              → alert_disposition_determination
              → alert_summary_generation
                           ↓
                        merge
```

**Why sequencing matters:**
- **Detailed Analysis runs FIRST**: Creates comprehensive report that other tasks consume
- **Disposition & Summary run AFTER in parallel**: Both read the detailed analysis to:
  - Disposition: Maps analysis conclusions to disposition categories
  - Summary: Condenses detailed analysis to executive summary
- Running them in parallel would miss the analysis content!

**Why the triad matters:**
- Provides complete investigation output for different audiences
- Ensures consistent quality across all workflows
- Satisfies audit requirements with technical details AND executive summaries
- Enables proper alert closure with definitive disposition

**Example with full workflow:**
```python
[
    "alert_context_generation",
    # Pattern 5: SIEM evidence validation
    ["splunk_triggering_event_retrieval", "splunk_supporting_evidence_search"],
    "merge",
    # External enrichment
    [
        "multi_source_ip_reputation_correlation",
        "echo_edr_comprehensive_behavioral_analysis",
        "ad_ldap_privileged_user_check"
    ],
    "merge",
    # Pattern 6: MANDATORY TRIAD
    # Step 1: Detailed analysis runs FIRST (sequential)
    "alert_detailed_analysis",
    # Step 2: Disposition and summary run AFTER in parallel (both read detailed analysis)
    [
        "alert_disposition_determination",
        "alert_summary_generation"
    ],
    "merge"  # Final merge to combine triad outputs
]
```

#### Pattern 7: Data Dependency Sequencing
```
Stage 1: Data Retrieval → Stage 2: Data Analysis → Stage 3: Synthesis
```

**Some tasks require data from others to function:**
- **Payload Analysis** needs Splunk events containing the payload
- **Success Assessment** needs enrichment data to evaluate
- **Disposition** needs all analysis complete

**Example: Web Attack Investigation**
```python
[
    "alert_context_generation",
    # MUST retrieve events first to get payload
    "splunk_triggering_event_retrieval",
    # NOW can analyze payload from Splunk data
    [
        "attack_payload_analysis",  # Reads from enrichments.splunk_triggering_events
        "multi_source_ip_reputation_correlation",
        "echo_edr_comprehensive_behavioral_analysis"
    ],
    "merge",
    "attack_success_determination",  # Needs merged enrichment data
    # Triad: Detailed analysis FIRST, then disposition/summary in parallel
    "alert_detailed_analysis",
    ["alert_disposition_determination", "alert_summary_generation"],
    "merge"
]
```

**Key principle:** Structure stages to respect data flow - retrieve → enrich → analyze → conclude.

#### Pattern 8: Smart Field Projection
```
Full Alert JSON → Project Relevant Fields → LLM Analysis
```

**Avoid passing entire alert JSON to LLM tasks. Instead, project only relevant fields:**

**Bad (token-heavy, unfocused):**
```cy
success_assessment = llm_run(
    directive="Determine if attack succeeded",
    data=alert  # Entire alert with all fields
)
```

**Good (efficient, focused):**
```cy
# Smart projection of only relevant indicators
success_indicators = {
    http_response: get_http_status(alert),
    response_size: alert.evidences[0]?.http_response?.length,
    processes_created: alert.enrichments.echo_edr?.processes_created,
    files_written: alert.enrichments.echo_edr?.file_operations
}
success_assessment = llm_run(
    directive="Determine if attack succeeded based on these specific indicators",
    data=success_indicators
)
```

**Benefits:**
- Reduces token usage significantly
- Improves LLM focus on relevant data
- Faster processing
- More consistent results

See **references/workflow_patterns.md** for detailed examples.

### 7. Data Flow: The Envelope Pattern

Every node emits standardized envelopes:

```json
{
  "node_id": "extract_ioc",
  "context": {},
  "description": "Extracted IOC from alert",
  "result": {
    "ip": "192.168.1.1",
    "domain": "malicious.com"
  }
}
```

**Key Rules:**
- **Single predecessor:** Task receives `result` field content
- **Multiple predecessors (fan-in):** Task receives array of `{node_id, result}` objects

See **references/data_flow_envelopes.md** for fan-in handling.

### 8. Node Types

#### Transformation Nodes

Lightweight Python/template-based transformations:

```json
{
  "node_id": "extract_ioc",
  "kind": "transformation",
  "name": "Extract IOC",
  "node_template_id": "uuid-or-name",
  "is_start_node": false
}
```

#### Task Nodes

Execute Cy-based tasks:

```json
{
  "node_id": "analyze_ip",
  "kind": "task",
  "name": "IP Analysis",
  "task_id": "uuid-or-cy_name",
  "is_start_node": false
}
```

## Creating a Workflow

### Step 1: Design the Workflow

Define purpose and flow:
```
Purpose: Enrich and analyze suspicious login alerts
Flow: Alert → [User AD Data, IP Reputation] → Merge → Risk Analysis → Disposition
Nodes: 4 tasks + 1 merge
Pattern: Diamond (parallel enrichment, converge for analysis)
```

### Step 2: Discover Required Tasks

```json
// MCP: list_tasks
{
  "tenant": "default",
  "function": "enrichment"
}
```

If tasks don't exist, create them using `task-builder` skill.

### Step 3: Compose the Workflow

```json
// MCP: compose_workflow
{
  "composition": [
    "identity",
    ["user_privilege_enrichment", "ip_reputation_enrichment"],
    "merge",
    "login_risk_correlation"
  ],
  "name": "Login Risk Assessment Workflow",
  "description": "Enriches login alerts and assesses risk based on user privilege and IP reputation",
  "tenant": "default",
  "execute": false
}
```

### Step 4: Create Workflow (Optional)

Set `execute: true` to save the workflow to database, or use REST API to run it:

```bash
POST /v1/default/workflows/{workflow_id}/run
{
  "input_data": {
    "observables": [{"value": "185.220.101.45", "type": "IP Address"}],
    "actor": {"user": {"name": "jsmith"}},
    "enrichments": {}
  }
}
```

## Production Readiness Checklist

Before deploying:

- [ ] Workflow has clear, descriptive name
- [ ] Input schema defines concrete properties (not bare object)
- [ ] Data samples provided and match schema
- [ ] Entry node marked with `is_start_node: true`
- [ ] Type validation passed (status = "validated")
- [ ] All referenced tasks exist and are tested
- [ ] Fan-in aggregation handled properly (merge or collect)
- [ ] Tested with realistic data samples

## Resources

### references/

- **type_validation.md** (~1,400 words): Complete type validation requirements and error resolution
- **data_flow_envelopes.md** (~1,200 words): Envelope structure and fan-in handling patterns

## Best Practices (Tested & Verified)

### ✅ DO: Include Splunk Evidence Retrieval Tasks (CRITICAL)

**For security alert workflows, ALWAYS include BOTH Splunk tasks:**

```python
[
    "alert_context_generation",
    ["splunk_triggering_event_retrieval", "splunk_supporting_evidence_search"],
    "merge",
    # ... rest of workflow
]
```

**Why this is mandatory:**
- **Hypothesis Validation**: Raw SIEM events provide ground truth about what actually happened
- **Pattern Detection**: Supporting evidence reveals attack patterns across time
- **False Positive Reduction**: Correlation with historical events separates noise from threats
- **Success Assessment**: Response codes, execution results visible in logs

**Without Splunk evidence:**
- Rely only on external threat intel (no YOUR environment context)
- Miss multi-step attack patterns
- Can't determine if attack succeeded or failed
- Higher false positive rates

See **Pattern 5: The Splunk Evidence Validation Pattern** for complete guidance.

### ✅ DO: Start with Task, Not Identity

**Recommended**:
```json
["task1", "task2", "task3"]
```

**Why**: compose_workflow automatically infers input schema from the FIRST task's data_samples. Starting with a task ensures proper schema and data_samples propagation.

**Avoid**:
```json
["identity", "task1", "task2"]  // ❌ Creates bare {"type": "object"} input
```

### ✅ DO: Use Parallel Enrichment with Merge

```json
["task1", ["task2", "task3"], "merge", "task4"]
```

**Pattern**: Sequential → Fan-Out → Merge → Continue

**Result**: Parallel tasks run concurrently, results merged into single object

### ✅ DO: Use Collect for Arrays

```json
["task1", ["task2", "task3"], "collect"]
```

**Result**: Parallel results aggregated into array `[result2, result3]`

### ❌ DON'T: Mix Incompatible Types

Tasks with type mismatches (e.g., one outputs `risk_score: number`, next expects `risk_score: integer`) will fail validation. Fix task schemas to match.

## Quick Start Example

```json
// 0. Check existing workflows first (best practice!)
list_workflows({})

// If no suitable workflow exists, proceed to create:

// 1. Discover tasks
list_tasks({})

// 2. Compose workflow (start with task, not identity!)
compose_workflow({
  "composition": [
    "ip_reputation_enrichment",
    "login_risk_correlation"
  ],
  "name": "Login Analysis",
  "description": "Analyze login with IP reputation",
  "execute": true  // Save workflow to database
})

// Returns workflow_id if successful

// 3. Verify workflow has proper data_samples
get_workflow({
  "workflow_id": "..."
})

// Should see data_samples from first task:
// "data_samples": [{"observables": [{"value": "185.220.101.45", ...}], "enrichments": {}, ...}]
```

## Troubleshooting

**"Entry node required"** → Add `is_start_node: true` to first node

**"Input schema must define properties"** → Add `properties` field with concrete types

**"Missing data_samples"** → Provide at least one sample matching input schema

**"Type mismatch"** → Check task output types match downstream input types

**"Needs aggregation"** → Add `merge` or `collect` before fan-in node

See **references/type_validation.md** for complete error reference.
