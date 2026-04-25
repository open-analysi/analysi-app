---
name: runbook-to-workflow
description: Convert standardized runbook.md files into executable Tasks and Workflows. Use when transforming investigation runbooks into automated alert processing workflows. (project, gitignored)
dependencies:
  - cy-language-programming
  - runbooks-manager
  - task-builder
  - task-naming
  - workflow-builder
---

# Runbook-to-Workflow Skill

## Prerequisites

**🚨 CRITICAL SKILL REQUIREMENTS 🚨**

This skill REQUIRES other skills to be loaded at specific steps. You MUST follow these requirements:

1. **BEFORE starting ANY runbook conversion work:**
   - ✅ **LOAD** `runbooks-manager` skill FIRST
   - ❌ DO NOT attempt to parse or convert runbooks without loading this skill

2. **BEFORE creating any Tasks:**
   - ✅ **LOAD** `cy-language-programming` skill FIRST
   - ✅ **LOAD** `task-builder` skill FIRST
   - ✅ **LOAD** `task-naming` skill for naming conventions
   - ❌ DO NOT attempt to create tasks without loading these skills

3. **BEFORE creating any Workflows:**
   - ✅ **LOAD** `workflow-builder` skill FIRST
   - ❌ DO NOT attempt to create workflows without loading this skill

**Why this matters:**
- `runbooks-manager` contains runbook format specifications, matching algorithms, composition strategies, pattern definitions, and field reference guidance
- Without it, you will misinterpret runbook structure, patterns, and integration hints
- The skill provides context that is not available in raw runbook files

## Overview

Converts standardized runbook.md files into executable Workflows by:
1. Parsing runbook YAML frontmatter and markdown steps
2. Creating/identifying Tasks for each investigation step
3. Composing a Workflow using workflow-builder
4. Testing with alert_examples from the runbook

**Key Principle:** Runbooks describe WHAT to investigate, this skill implements HOW.

## When to Use This Skill

Use this skill when:
- Converting a new runbook.md into an executable workflow
- Updating an existing workflow based on runbook changes
- Validating that a runbook can be implemented with available tools
- Building end-to-end alert processing automation

**DON'T use for:**
- Creating runbooks (use runbook-builder)
- Writing individual tasks (use task-builder)
- Analyzing ground-truth analyst investigations (use a runbook-generation agent)

## Process Overview

### Phase 1: Runbook Analysis
1. Parse YAML frontmatter
2. Extract investigation steps
3. Identify @include directives
4. Map patterns to implementation strategies

### Phase 2: Task Creation/Identification
1. Check for existing tasks by cy_name
2. Create new tasks for unmapped steps
3. Validate task compatibility with runbook requirements

### Phase 3: Workflow Composition
1. Determine step dependencies and parallelism
2. Compose workflow using workflow-builder
3. Validate type compatibility

### Phase 4: Testing & Validation
1. Execute workflow with alert_examples
2. Validate outputs match runbook expectations
3. Document any gaps or limitations

## Critical Architectural Patterns

### The Mandatory Workflow Structure

**CRITICAL:** All alert investigation workflows MUST follow this standard structure.

```
1. alert_context_generation (CONSTANT PREFIX - REQUIRED)
2. [Investigation tasks] (workflow-specific)
3. Mandatory Triad (CONSTANT SUFFIX - REQUIRED):
   - detailed_analysis
   - disposition_determination
   - summary_generation
```

**Why This Pattern Exists:**

1. **alert_context_generation (Start)**
   - **Purpose:** Converts structured OCSF alert (JSON) into textual summary
   - **Why Required:** LLMs work better with natural language than structured data
   - **Runbook Parallel:** Alert Understanding step (JSON→text only)
   - **Never Skip:** Foundation for all downstream LLM tasks
   - **⚠️ DOES NOT include hypothesis generation** - see below

   **Hypothesis Generation is NOT Part of Fixed Prefix:**

   If the runbook has a step with `pattern: hypothesis_formation` or outputs `investigation_hypotheses`,
   this requires a SEPARATE investigation task. `alert_context_generation` only does JSON→text
   conversion - it does not form hypotheses.

   Hypothesis tasks are workflow-specific (not reusable) and should:
   - Be created NEW for each workflow during Kea generation
   - Contain static hypotheses extracted from the runbook (baked in at creation time)
   - Allow LLM to add alert-specific hypotheses at runtime

   See `task-builder` skill → "Hypothesis Task Pattern" for implementation details.

2. **Investigation Tasks (Middle)**
   - **Purpose:** Workflow-specific enrichment, evidence gathering, analysis
   - **Runbook Parallel:** The specific investigation steps from the runbook
   - **Design Freedom:** Map runbook steps to tasks based on available integrations
   - **Parallel Opportunities:** Tasks that analysts could do simultaneously should run in parallel

3. **Mandatory Triad (End)**
   - **Purpose:** Standard outputs required by SOC analysts for every alert
   - **Why Required:** SOC management needs consistent reporting format
   - **Components:**
     - `detailed_analysis`: Deep dive synthesis of all evidence
     - `disposition_determination`: TP/FP verdict, severity, escalation decision
     - `summary_generation`: Executive summary for SOC dashboard
   - **Runbook Parallel:** Final Analysis Trio (@include: common/universal/final-analysis-trio.md)
   - **Typical Pattern:** detailed_analysis → [disposition + summary in parallel] → merge

**Example Structure (SQL Injection):**
```
alert_context_generation
    ↓
[parallel: url_decode + vt_ip + abuseipdb + splunk_trigger]
    ↓
merge
    ↓
splunk_supporting_evidence
    ↓
sql_injection_attack_success
    ↓
detailed_analysis (Triad 1/3)
    ↓
[parallel: disposition + summary] (Triad 2/3 + 3/3)
    ↓
merge
```

### The Integration + LLM Reasoning Pattern

**Core Principle:** Almost all tasks follow the **Integration + LLM Reasoning Pattern**:

1. **Data Retrieval**: Pull raw data from integration tools (EDR, SIEM, ThreatIntel, CVE databases)
2. **LLM Analysis**: Use LLM to reason about the data and provide security-informed analysis

This pattern combines:
- **Precision**: Integration tools provide accurate, structured data from authoritative sources
- **Intelligence**: LLMs provide context-aware reasoning and security expertise

**Task Types:**

| Task Type | Pattern | Example | Runbook Pattern |
|-----------|---------|---------|-----------------|
| Integration + LLM | Fetch → Analyze | `app::virustotal::ip_reputation()` → LLM interprets | `integration_query` |
| LLM-Only Synthesis | Combine enrichments | LLM merges multiple enrichments | `threat_synthesis` |
| LLM-Only Analysis | Analyze existing data | LLM decodes payload | `payload_analysis` |
| Integration-Only | Retrieve raw data | Fetch SIEM events for later | `integration_query` (rare) |

**Examples:**
- **VirusTotal IP check**: `app::virustotal::ip_reputation()` → LLM interprets reputation score
- **URL decoding**: LLM decodes and analyzes SQL injection payload
- **SIEM search**: `app::splunk::spl_run()` → LLM finds suspicious patterns
- **CVE lookup**: `app::nistnvd::get_cve()` → LLM summarizes impact

**Reference:** See `references/integration_llm_pattern.md` for detailed guidance, examples, and best practices.

### Never Create Fake Tasks

**Critical Principle:** Don't create tasks that pretend features exist.

**❌ WRONG:**
```cy
# Detection Logic RAG doesn't exist!
rule_logic = app::detection_rag::get_rule(rule_id=alert.finding_info.analytic.name)
```

**✅ CORRECT:**
```cy
# Use LLM with available alert fields
rule_analysis = llm_run(
    directive="Infer detection logic from alert fields...",
    input_data={"rule_name": alert.rule_name ?? alert.finding_info.analytic.name, "trigger_reason": alert.raw_data?.alert_trigger_reason}
)
# Document: "Detection Logic RAG not available - using LLM inference"
```

**When capabilities are missing:**
- Use available tools as fallback (LLM reasoning with available data only)
- Document the limitation clearly in workflow
- Note as "future enhancement"
- Don't create fake/mock integration calls

**Critical: Missing Integration Impact on Disposition**

If runbook says "Analyst used EDR for X" but no EDR configured:

```cy
# ❌ WRONG - Don't hallucinate EDR data
edr_analysis = llm_run(
    directive="Imagine what EDR would show for this process..."  // NO!
)

# ✅ CORRECT - Document gap, analyze without it
disposition = llm_run(
    directive="""Determine disposition based on available evidence.

    IMPORTANT: EDR data not available (integration not configured).
    Base verdict on: SIEM logs, threat intel, payload analysis only.

    Note in disposition: "Confidence: Medium - EDR validation unavailable"
    """,
    input_data={...}  // Only actual data, no fake EDR
)
```

**Document gaps in workflow creation:**
- "Task X skipped - EDR not configured"
- "Disposition based on partial evidence (no EDR/identity/etc.)"
- Impact on confidence level in final verdict

### Runbook Pattern to Task Pattern Mapping

How runbook patterns translate to Cy/Task implementation:

| Runbook Pattern | Cy Tool | Task Function | Description |
|-----------------|---------|---------------|-------------|
| `hypothesis_formation` | `llm_run` | `reasoning` | Form investigation theories |
| `evidence_correlation` | `llm_run` | `reasoning` | Correlate evidence sources |
| `payload_analysis` | `llm_run` | `enrichment` | Decode and analyze payloads |
| `impact_assessment` | `llm_run` | `reasoning` | Determine attack success |
| `threat_synthesis` | `llm_run` | `synthesis` | Full context analysis |
| `integration_query` | `app::integration::action` | `search/enrichment` | Direct integration calls |

## Detailed Process Steps

### Step 1: Parse Runbook Structure

**Read and analyze the runbook.md file:**

1. **Extract YAML frontmatter:**
   - `detection_rule`: Maps to workflow name
   - `alert_type`, `source_category`: Workflow metadata
   - `integrations_required`: Required integrations validation
   - `alert_examples`: Test data for workflow execution

2. **Parse markdown steps:**
   - Identify step headers (e.g., `### 1. Alert Understanding ★`)
   - Extract step attributes (Action, Pattern, Integration, etc.)
   - Note criticality markers (★)
   - Detect @include directives

3. **Resolve @include directives:**
   - Read referenced sub-runbooks
   - Merge parameters/overrides
   - Expand into full step list

**Output:** Complete list of investigation steps with all attributes.

### Step 2: Map Steps to Tasks

For each runbook step, determine implementation:

#### Pattern-to-Task Mapping

| Runbook Pattern | Implementation | Task Function | Notes |
|-----------------|----------------|---------------|-------|
| `hypothesis_formation` | `llm_run` task | `reasoning` | Create new task if needed |
| `evidence_correlation` | `llm_run` task | `reasoning` | May reuse existing correlation task |
| `payload_analysis` | `llm_run` task | `enrichment` | Create specialized decoder task |
| `impact_assessment` | `llm_run` task | `reasoning` | Create verdict determination task |
| `threat_synthesis` | `llm_run` task | `synthesis` | Create comprehensive analysis task |
| `integration_query` | Integration tool | `search/enrichment` | Map category to specific integration |

#### Field Mapping Strategy

Runbooks use symbolic field references (e.g., `alert.source_ip`). Map to OCSF paths using helper functions:

| Runbook Reference | OCSF Access Pattern | Cy Helper |
|------------------|---------------------|-----------|
| `alert.source_ip` | `alert.evidences[0].src_endpoint.ip` | `get_src_ip(alert)` |
| `alert.destination_ip` | `alert.evidences[0].dst_endpoint.ip` | `get_dst_ip(alert)` |
| `alert.url` | `alert.evidences[0].url.url_string` | `get_url(alert)` |
| `alert.user` | `alert.actor.user.name` | `get_primary_entity_value(alert)` |

**Note:** Use OCSF helper functions for common field access. See `ocsf_alert_structure.md` in task-builder references.

#### Integration Selection

Runbooks specify integration categories. Map to configured integrations:

| Runbook Category | Check Available | Select Strategy |
|-----------------|-----------------|-----------------|
| `threat_intel` | VirusTotal, AbuseIPDB, etc. | Prefer VirusTotal for IP/URL/domain |
| `siem` | Splunk, SentinelOne, etc. | Use configured SIEM |
| `edr` | SentinelOne, CrowdStrike, etc. | Use configured EDR |

**General-Purpose Tasks to Prefer:**

When Splunk integration is enabled, use this existing task instead of creating new SIEM-related tasks:

| Task | cy_name | When to Use |
|------|---------|-------------|
| Splunk: Triggering Event Retrieval with SPL Generation and LLM Summarization | `splunk_triggering_event_retrieval` | Runbook steps that retrieve and summarize the events that triggered the alert |

This task dynamically generates SPL queries to fetch triggering events and provides a basic summarization. Note: Subsequent searches for supporting evidence or additional context discovery may still require separate tasks.

**Use MCP tools:**
- `mcp__analysi__list_integrations(configured_only=True)` - Get available integrations
- `mcp__analysi__list_integration_tools(integration_type)` - Get tool capabilities

### Step 2.5: Search Existing Tasks

**Before creating new tasks, search for existing ones:**

```
1. list_tasks(function="enrichment", scope="processing")
2. Review cy_names and descriptions for matches
3. get_task(task_ids=["candidate1", "candidate2"])
4. Compare capabilities to runbook step requirements
```

**Decision Criteria:**

| Situation | Action | Example |
|-----------|--------|---------|
| Exact match exists | ✅ Reuse | `virustotal_ip_reputation` for IP checks |
| Generic task fits | ✅ Reuse | `payload_analysis` for any payload type |
| No match, reusable pattern | ⭐ Create new | `url_decoder` (useful for XSS, SQLi, LFI) |
| Too specific for reuse | ❌ Reconsider | Don't create a rule-specific decoder |

**Reusability Test:** Ask "Would this help other alert types?" If NO, don't create as separate task.

### Step 3: Create Missing Tasks

For each step that doesn't have an existing task:

1. **Generate cy_name:**
   ```
   {detection_rule_sanitized}_{step_sanitized}
   Example: sql_injection_payload_analysis
   ```

2. **Determine Task metadata:**
   - `name`: Human-readable (from runbook step title)
   - `description`: From step Action attribute
   - `function`: From pattern-to-task mapping
   - `scope`: "processing" for most investigation steps
   - `directive`: LLM instructions from step Focus/Decision Points

3. **Write Cy script:**
   - Use appropriate pattern (llm_run vs integration tool)
   - Map symbolic fields to OCSF paths using helper functions
   - Handle optional fields gracefully
   - Return structured output with enrichment pattern:

   ```cy
   # ✅ CORRECT - Additive enrichment
   return {
       "enrichments": {
           ...input.enrichments,  // Preserve existing
           "new_field": analysis  // Add new
       }
   }

   # Use null-safe access
   alert_context = input.enrichments?.alert_context?.context_summary ?? "No context"
   ```

4. **Add test data_samples:**
   - Use alert_examples from runbook
   - Create minimal test case for validation

**Use task-builder skill for detailed guidance on task creation.**

### Step 4: Compose Workflow

**Determine workflow structure:**

1. **Sequential vs Parallel:**

   **Sequential when:**
   - Second task needs first's output (data dependency)
   - Logical progression required (payload analysis → attack success)
   - alert_context_generation always first, Mandatory Triad always last

   **Parallel when:**
   - Independent data sources (VirusTotal + AbuseIPDB + SIEM)
   - Runbook has `Parallel: Yes` attribute
   - No shared dependencies between tasks

   **Common patterns:**
   - Enrichment phase: `["payload_decode", "ip_rep_vt", "ip_rep_abuse", "siem"]`
   - Final reporting: `["disposition", "summary"]` (both use detailed_analysis)

2. **Build composition array:**
   ```javascript
   // Example for SQL Injection runbook
   [
     "identity",
     "sql_injection_alert_understanding",           // Step 1 (critical)
     [                                               // Steps 2a-2c parallel
       "sql_injection_siem_evidence",                // Step 2a (critical)
       "virustotal_ip_reputation",                   // Step 2b (optional)
       "sql_injection_payload_decode"                // Step 2c (critical)
     ],
     "sql_injection_attack_success_determination",   // Step 3 (critical)
     "sql_injection_detailed_analysis",              // Step 4a (critical)
     [                                               // Steps 4b-4c parallel
       "sql_injection_disposition_determination",    // Step 4b (critical)
       "sql_injection_executive_summary"             // Step 4c (critical)
     ]
   ]
   ```

3. **Handle conditional steps:**
   - Note: Current workflow composition may not support conditionals
   - Document as limitation or create separate workflows

**Use analysi MCP tools:**
- `mcp__analysi__list_tasks()` - Find existing tasks
- `mcp__analysi__compose_workflow()` - Create workflow from composition

### Step 5: Validate Workflow

1. **Type compatibility:**
   - Use `mcp__analysi__get_workflow(workflow_id)` to inspect types
   - Ensure task outputs match downstream inputs
   - Verify aggregation for parallel branches

2. **Integration availability:**
   ```
   # Check which integrations are configured
   configured = list_integrations(configured_only=True)
   configured_ids = [i['integration_id'] for i in configured]

   # Mark task status:
   # ✅ Active - integration configured
   # ❌ Requires Config - integration exists but not configured
   # 🟡 Flexible - optional integration (LLM fallback)
   ```

   **Readiness calculation:** `(Active Tasks / Total Tasks) × 100`
   - 100%: Production ready
   - 75-99%: Nearly ready
   - <75%: Significant gaps

   **Document missing integrations:**
   - "EDR validation skipped - no EDR configured"
   - "Identity enrichment unavailable - AD/LDAP not configured"
   - Impact: Include in disposition directive as data limitation
   - Update disposition confidence based on available evidence

3. **Critical step coverage:**
   - Ensure all ★ steps are implemented
   - Optional steps can be noted as "nice-to-have"

### Step 6: Test with Alert Examples

1. **Execute workflow:**
   ```python
   result = mcp__analysi__run_workflow(
       workflow_id=workflow_id,
       input_data=alert_example,  # From runbook YAML
       timeout_seconds=300
   )
   ```

2. **Validate outputs:**
   - Check final analysis was generated
   - Verify disposition (TP/FP/Benign) was determined
   - Ensure executive summary is present

3. **Document results:**
   - Success: Runbook fully automated
   - Partial: Note which steps failed/missing
   - Failure: Document blockers and required fixes

## Common Patterns

### Pattern 1: Alert Understanding Step

**Runbook:**
```markdown
### 1. Alert Understanding ★
- **Action:** Analyze alert and form hypotheses
- **Pattern:** hypothesis_formation
- **Input:** OCSF alert fields
- **Outputs:** context_summary, investigation_hypotheses
```

**Implementation:**
- **Task cy_name:** `{detection_rule}_alert_understanding`
- **Cy script:**
  ```cy
  llm_run(
      directive="Analyze this {alert.alert_type} alert...",
      input_data={
          "alert": alert,
          "detection_rule": "{detection_rule}"
      }
  )
  ```

### Pattern 2: SIEM Evidence Collection

**Runbook:**
```markdown
### 2a. SIEM Evidence Collection ★
- **Action:** Search SIEM for related events
- **Integration:** siem
- **Fields:** alert.src_ip, alert.time
- **Output:** siem_events
```

**Implementation:**
- Check for existing SIEM search task
- OR create new task with Splunk/SIEM integration tool
- **Cy script:**
  ```cy
  app::splunk::search(
      query="index=* src={get_src_ip(alert)}",
      earliest="-1h",
      latest="now"
  )
  ```

### Pattern 3: Threat Intel Enrichment

**Runbook:**
```markdown
### 2b. IP Reputation Check
- **Action:** Check IP in threat intel
- **Integration:** threat_intel
- **Fields:** alert.src_ip
- **Parallel:** Yes
```

**Implementation:**
- Use existing VirusTotal IP reputation task
- **Task cy_name:** `virustotal_ip_reputation` (already exists)
- Add to parallel branch in workflow composition

### Pattern 4: Final Analysis Trio

**Runbook:**
```markdown
### @include: common/universal/final-analysis-trio.md
```

**Implementation:**
- Creates 3 tasks: detailed_analysis, disposition, executive_summary
- Detailed analysis runs first
- Disposition + summary run in parallel
- Pattern used across all runbooks

## Error Handling

### Common Issues

1. **Missing Integration:**
   - **Error:** Runbook requires `edr` but no EDR integration configured
   - **Solution:**
     - Skip the EDR task (don't hallucinate data)
     - Document: "EDR validation skipped - integration not configured"
     - Update disposition directive: "Base verdict on available evidence only (no EDR)"
     - Adjust confidence: "Confidence: Medium - EDR validation unavailable"
     - List missing integration in workflow documentation

2. **Field Not Found:**
   - **Error:** `alert.user` but alert has no user field
   - **Solution:** Add null checks in Cy script: `alert.primary_user?.name ?? "N/A"`

3. **Type Mismatch:**
   - **Error:** Task outputs string but downstream expects object
   - **Solution:** Modify task output schema or add transform task

4. **Circular Dependency:**
   - **Error:** Task A depends on B, B depends on A
   - **Solution:** Re-analyze runbook steps, break dependency

## Validation Checklist

Before marking conversion complete:

- [ ] All critical (★) steps have corresponding tasks
- [ ] Workflow composition respects step dependencies
- [ ] Parallel steps are properly grouped
- [ ] Required integrations are available and configured
- [ ] Type compatibility validated via analysi MCP tools
- [ ] Workflow executes successfully with alert_example
- [ ] Final output includes disposition and summary
- [ ] Optional steps documented (even if not implemented)

## Output Documentation

After conversion, document:

1. **Workflow ID and name**
2. **Tasks created** (cy_names and descriptions)
3. **Tasks reused** (existing tasks leveraged)
4. **Limitations:**
   - Optional steps not implemented
   - Missing integrations
   - Conditional logic not supported
5. **Test results** (from alert_example execution)

## MCP Tool Quick Reference

| Tool | When to Use | Returns |
|------|-------------|---------|
| `list_integrations(configured_only=True)` | Map runbook categories to integrations | Configured integration IDs, archetypes |
| `list_integration_tools(integration_type)` | Understand integration capabilities | Tool list with parameters |
| `list_tasks(function, scope)` | Search existing tasks | cy_names, descriptions (lightweight) |
| `get_task(task_ids)` | Get full task info | Complete task including scripts |
| `list_workflows()` | Check for existing workflows | Workflow summaries with compositions |
| `compose_workflow(composition, name, description)` | Create new workflow | Workflow ID or errors |
| `get_workflow(workflow_id, include_validation=True)` | After creation | Type compatibility report |
| `run_workflow(workflow_id, input_data, timeout)` | Test with alert_examples | Execution results |

## Best Practices

### DO:
- **Always follow the mandatory workflow structure** - alert_context → investigation → triad
- **Use the Integration + LLM pattern** - Most tasks pull data from integration, then use LLM to analyze
- **Map runbook critical steps (★) to workflow** - Ensure all critical steps are implemented
- **Leverage existing tasks** - Search `list_tasks()` before creating new
- **Use symbolic field references** - Map runbook's `alert.source_ip` to OCSF helper `get_src_ip(alert)`
- **Test with alert_examples** - Use the runbook's alert_examples for validation
- **Document missing capabilities** - If integration unavailable, note as limitation
- **Respect parallelism hints** - Runbook's "Parallel: Yes" → parallel execution in workflow
- **Include null-safe navigation** - Use `input.enrichments?.field ?? "default"` in Cy scripts

### DON'T:
- **Don't skip alert_context_generation** - Always required as first step
- **Don't skip the mandatory triad** - Always required as last steps
- **Don't create fake tasks** - If feature doesn't exist, document as limitation
- **Don't hallucinate missing integration data** - If runbook needs EDR but it's not configured, skip the task and note the gap in disposition
- **Don't ignore data limitations** - Include missing integration impacts in disposition confidence level
- **Don't ignore runbook field references** - Map symbolic references to OCSF paths using helpers
- **Don't skip validation** - Always run workflow with alert_example before marking complete
- **Don't forget integration availability** - Verify integrations are configured with MCP tools
- **Don't create duplicate tasks** - Reuse existing tasks when possible

## References

- `references/integration_llm_pattern.md` - Core architectural pattern for task implementation

## See Also

- **runbook-builder** skill - Runbook format specification
- **task-builder** skill - Creating individual tasks
- **workflow-builder** skill - Workflow composition patterns
- **cy-language-programming** skill - Cy script syntax
