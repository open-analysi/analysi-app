---
name: task-builder
description: Use when creating or modifying Analysi Security Tasks (analyst automation components that accept OCSF alerts, query integrations, and use LLM reasoning). Also use when understanding Task patterns, validation requirements, or troubleshooting task creation. Requires Cy language proficiency (reference cy-language-programming skill first).
mcp_tools:
  - mcp__analysi__create_task
  - mcp__analysi__get_task
  - mcp__analysi__update_task
  - mcp__analysi__compile_script
  - mcp__analysi__list_integrations
  - mcp__analysi__list_integration_tools
  - mcp__analysi__run_script
  - mcp__analysi__validate_alert
  # Task Discovery (Progressive Disclosure)
  - mcp__analysi__list_tasks
dependencies:
  - cy-language-programming
  - cybersecurity-analyst
  - task-naming
  - hypothesis-building-task
---

# Analysi Task Builder

## Overview

Build production-ready security automation Tasks for the Analysi platform. **Tasks are re-usable sets of steps taken by a virtual Analyst to help resolve cyber security tickets.**

**What Tasks Do:**
- Accept alerts in OCSF (Open Cybersecurity Schema Framework) Detection Finding format
- Answer ONE specific investigative question (e.g., "Is this IP malicious?")
- Query integration tools (threat intel, IAM, EDR, SIEM)
- Use LLM reasoning to synthesize findings
- Return enriched alerts for the next task in the workflow

## ⭐ Canonical Task Architecture (MOST IMPORTANT)

**Most tasks follow this pattern: Integration Tool Call → LLM Reasoning**

```cy
# 1. Extract what to investigate from the alert using OCSF helpers
ip = get_primary_observable_value(input) ?? get_src_ip(input) ?? ""
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.finding_info.title ?? "unknown alert"

# 2. Call integration tool to get objective data
vt_result = app::virustotal::ip_reputation(ip=ip)

# 3. Use LLM to reason about the data IN CONTEXT of this alert
analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

    VirusTotal found ${vt_result.malicious_count}/80 engines flagged this IP.

    Is this IP malicious? How does this relate to the alert?
    Return JSON: {"verdict": "...", "confidence": "...", "reasoning": "..."}"""
)

# 4. Add findings to enrichments (uses task's cy_name automatically)
enrichment = {
    "ip": ip,
    "malicious_count": vt_result.malicious_count,
    "ai_analysis": analysis  # REQUIRED: LLM output goes in ai_analysis field
}

return enrich_alert(input, enrichment)
```

**Why this pattern works:**
- **Integration tools** provide objective, factual data (reputation scores, event logs)
- **LLM reasoning** interprets that data in the specific alert context
- **Without context**, LLM gives generic analysis; **with context**, it understands the investigation goal

**See:** `references/task_design_methodology.md` for detailed 4-step methodology.

**Prerequisites:**
- **Cy Language:** Use `cy-language-programming` skill for syntax and debugging
- **Splunk Tasks:** Use `splunk-skill` for SPL query construction
- **Security Context:** Use `cybersecurity-analyst` skill for investigation priorities
- **Task Naming:** Use `task-naming` skill for naming conventions when creating new tasks
- **Integration companion skills:** Some integrations ship with a `{id_with_hyphens}-integration` companion skill (e.g., `virustotal` → `virustotal-integration`, `ad_ldap` → `ad-ldap-integration`) that encodes authoritative action parameters, return shapes, rate limits, and investigation patterns. When one exists for an integration your task uses, load it — it produces fewer validation failures than tool-description-only designs.

## When to Use This Skill

**Use this skill for:**
- Creating new security automation Tasks
- Building alert enrichment tasks
- Converting playbooks into Tasks
- Troubleshooting Task validation errors

**DON'T use for:**
- Learning Cy syntax → use `cy-language-programming`
- Building Workflows → use `workflow-builder`
- Debugging Cy errors → use `cy-language-programming`

## 🔑 Three Critical Patterns (MUST KNOW)

### 1. Alert Context Pattern (MANDATORY)

Almost ALL tasks with LLM reasoning must use alert context from the `alert_context_generation` task that runs first in workflows.

**The Pattern:**
```cy
# ALWAYS extract context using this pattern
alert_context = input.enrichments.alert_context_generation.ai_analysis ??
                input.finding_info.title ??
                input.title ??
                "unknown alert"

# ALWAYS include context in LLM directives
analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

    Analyze this IP reputation in the context of this specific alert..."""
)
```

**Why Critical:** Without context, LLM analysis is generic and unfocused. With context, it understands the investigation goal.

**See:** `references/task_dependencies_pattern.md` for full details.

### 2. Additive Enrichment Pattern (MANDATORY)

Use the `enrich_alert()` function to add enrichments. It automatically:
- Uses the task's `cy_name` as the enrichment key
- Preserves existing enrichments from previous tasks
- Creates the `enrichments` dict if needed

```cy
# Build your enrichment data
enrichment = {
    "risk_level": "high",
    "ai_analysis": llm_result  # REQUIRED field name for LLM output
}

# enrich_alert stores under alert["enrichments"][cy_name]
return enrich_alert(input, enrichment)
```

**Required Field:** If your task uses `llm_run()`, the enrichment MUST include an `ai_analysis` field containing the LLM output. This standardized field name enables consistent access across all tasks.

**Why Critical:** Workflows chain tasks (A → B → C). Each must preserve prior enrichments.

**See:** `references/ocsf_enrichment_pattern.md` for complete pattern.

### 3. NEVER Access raw_data Fields (MANDATORY)

**CRITICAL: `raw_data` is vendor-specific and MUST NEVER be accessed directly.**

The `raw_data` field contains the original, unprocessed alert data from the source system. Its structure varies completely by vendor and is unpredictable.

**The Rule:**
```cy
# NEVER DO THIS - Breaks with different vendors
domain = input.raw_data.domain
username = input.raw_data.user.name
host = input.raw_data.fields.hostname

# ALWAYS DO THIS - Use OCSF helpers with defensive defaults
ip = get_primary_observable_value(input) ?? "0.0.0.0"
domain = (get_observables(input, type="domain")[0].value) ?? "unknown.com"
username = get_primary_user(input) ?? "unknown_user"
host = get_primary_device(input) ?? "unknown_host"
src_ip = get_src_ip(input) ?? "0.0.0.0"
```

**Why This is MANDATORY:**

1. **Vendor Independence**: `raw_data` structure differs between Okta, Splunk, CrowdStrike, Palo Alto, etc.
2. **Field Name Inconsistency**: One vendor uses "domain", another uses "dest_domain", another uses "dns_name"
3. **Task Fragility**: Tasks that access `raw_data` fields break when used with different alert sources
4. **OCSF + Helpers Solve This**: All critical fields are accessible through standardized helper functions

**The ONLY Valid Use of raw_data:**

Pass it wholesale to LLM for additional context (the LLM can interpret vendor-specific formats):

```cy
# ACCEPTABLE - Give LLM the full raw data for context
analysis = llm_run(
    prompt="""Analyze this alert. Use the raw alert data for additional context:

    Raw Alert: ${input.raw_data}

    Focus on security implications..."""
)
```

**Standard Helpers to Use Instead:**

| Don't Access | Use Instead (with `?? default`) |
|--------------|----------------------------------|
| `raw_data.ip`, `raw_data.source_ip` | `get_primary_observable_value(input) ?? "0.0.0.0"`<br>`get_src_ip(input) ?? "0.0.0.0"` |
| `raw_data.domain`, `raw_data.hostname` | `get_primary_device(input) ?? "unknown_host"`<br>`get_observables(input, type="domain")` |
| `raw_data.user`, `raw_data.username` | `get_primary_user(input) ?? "unknown_user"` |
| `raw_data.file_hash`, `raw_data.md5` | `get_observables(input, type="filehash")` |
| `raw_data.url` | `get_url(input) ?? ""`<br>`get_observables(input, type="url")` |
| `raw_data.cve` | `get_cve_ids(input)` |
| `raw_data.*` (anything else) | Find appropriate OCSF helper<br>Or pass entire `raw_data` to LLM |

**See:** `references/ocsf_schema_overview.md` for complete OCSF helper reference and access patterns.

## Quick Start: Create Your First Task

### Step 1: Define What It Does

```
Question: "What reputation does this IP have?"
Input Fields: observables (IP type) or evidences[].src_endpoint.ip
Integration: VirusTotal
Output: Enriched alert with ip_reputation
```

### Step 2: Write Minimal Cy Script

```cy
# Extract IP (with fallbacks via OCSF helpers)
ip = get_primary_observable_value(input) ?? get_src_ip(input) ?? "0.0.0.0"

# Get alert context
alert_context = input.enrichments.alert_context_generation.ai_analysis ??
                input.finding_info.title ?? "unknown alert"

# Query integration
vt_result = app::virustotal::ip_reputation(ip=ip)

# LLM analysis with context
analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

    Analyze IP ${ip} reputation:
    - Detections: ${vt_result.reputation_summary.malicious}/80

    Provide risk level (high/medium/low) and 2-sentence summary."""
)

# Enrich and return (uses task's cy_name as key)
enrichment = {
    "source": "VirusTotal",
    "ai_analysis": analysis  # REQUIRED field for LLM output
}

return enrich_alert(input, enrichment)
```

### Step 3: Create data_samples with Critical Fields + Script-Used Fields

```
╔══════════════════════════════════════════════════════════════╗
║ CRITICAL ALERT FIELDS - ALWAYS INCLUDE IN data_samples       ║
╠══════════════════════════════════════════════════════════════╣
║ - finding_info: Title + analytic.name + uid (REQUIRED)       ║
║ - observables: Array of IOC pointers, even if [] (REQUIRED)  ║
║ - severity_id: 1-5 integer severity (recommended)            ║
║ - enrichments: {} to start, preserves workflow chain         ║
╚══════════════════════════════════════════════════════════════╝
```

These fields enable alert context extraction, workflow chaining, and proper IOC tracking.

```json
{
  "data_samples": [
    {
      "finding_info": {"title": "Suspicious Outbound Connection to 185.220.101.45", "uid": "sample-001", "analytic": {"name": "Suspicious Outbound Connection", "type": "Rule", "type_id": 1}},
      "severity_id": 4,
      "observables": [
        {"type_id": 2, "type": "IP Address", "value": "185.220.101.45"}
      ],
      "enrichments": {}
    },
    {
      "finding_info": {"title": "DNS Query to External Resolver 8.8.8.8", "uid": "sample-002", "analytic": {"name": "External DNS Resolution", "type": "Rule", "type_id": 1}},
      "severity_id": 3,
      "observables": [
        {"type_id": 2, "type": "IP Address", "value": "8.8.8.8"}
      ],
      "enrichments": {}
    }
  ]
}
```

**See:** `references/data_samples_guide.md` for complete critical fields requirement and patterns.

### 🚨 Step 4: TEST BEFORE CREATING (MANDATORY - DO NOT SKIP)

```
╔═════════════════════════════════════════════════════════════╗
║ 🚨 CRITICAL: You MUST test the COMPLETE task as ad-hoc     ║
║    BEFORE calling create_task()                             ║
║                                                             ║
║ ✅ Test with ALL data_samples covering ALL code branches   ║
║ ✅ Each sample must trigger its intended code path         ║
║                                                             ║
║ Skipping = 3-5x longer task creation time!                 ║
╚═════════════════════════════════════════════════════════════╝
```

**Branch Coverage Testing:**
- Create N data_samples where N ≥ number of major code branches
- Each sample should trigger a DIFFERENT path (happy path, fallback, early return)
- Example: Script with 3 fallbacks needs at least 3 samples
- Document which branch each sample tests

**Why This Is Mandatory:**
- Ad-hoc execution catches: data flow bugs, integration timeouts, LLM prompt issues
- Branch coverage ensures all code paths work, not just the happy path
- Creating untested tasks forces slow create→fail→debug→recreate cycles
- Ad-hoc testing takes 30 seconds and prevents hours of debugging

**Required Testing Sequence:**

1. **Compile Validation**:
   ```
   mcp__analysi__compile_script(script=your_script)
   ```
   - Verifies syntax and type correctness
   - Fix any compilation errors before proceeding

2. **Ad-Hoc Execution Test** (MANDATORY):
   ```
   mcp__analysi__run_script(
       script=your_script,
       input_data=sample_alert
   )
   ```
   - Test with ALL data_samples you plan to include
   - Verify complete end-to-end execution succeeds
   - Check outputs match expected enrichment structure
   - Validate error handling with edge cases

**ONLY proceed to Step 5 (create_task) if ad-hoc execution succeeds for all samples.**

See **MCP Tools Quick Reference** section below for detailed usage.

### Step 5: Create Task (Should Succeed First Try)

After Step 4 testing passes:

```json
mcp__analysi__create_task({
  "name": "IP Reputation Analysis",
  "script": "...",
  "data_samples": [...],
  "function": "enrichment",
  "scope": "processing"
})
```

**If this fails, you skipped Step 4 - go back and test!**

## Design Philosophy: Less Is More

```
╔══════════════════════════════════════════════════════════════╗
║ 🎯 MINIMALIST TASK DESIGN PRINCIPLES                        ║
╠══════════════════════════════════════════════════════════════╣
║ 📏 TARGET SIZE: 50-80 lines of Cy code                      ║
║    - Under 50: Consider if task does enough                 ║
║    - Over 80: Consider splitting into multiple tasks        ║
║                                                              ║
║ ❌ AVOID: Computing ratios, percentages, derived metrics    ║
║ ❌ AVOID: Classifying numeric ranges into categories        ║
║ ❌ AVOID: Multiple fallback strategies if one path works    ║
║                                                              ║
║ ✅ DO: Answer ONE specific question                          ║
║ ✅ DO: Let LLM interpret raw values when analysis needed    ║
║ ✅ DO: Return raw integration data for downstream flex      ║
╚══════════════════════════════════════════════════════════════╝
```

**Why Minimalism Matters:**
- Simpler tasks are easier to test and debug
- Raw data gives downstream tasks flexibility
- Computed metrics often need to change anyway
- LLMs excel at contextual interpretation

**Key Takeaway:** Focus on data retrieval + one analytical question. Resist the urge to add "nice to have" computations.

## Default Value Convention: Always Lowercase

**ALWAYS use lowercase for default/fallback values.** This ensures consistency across all tasks.

```
╔══════════════════════════════════════════════════════════════╗
║ 🔤 DEFAULT VALUE CONVENTION                                  ║
╠══════════════════════════════════════════════════════════════╣
║ ✅ CORRECT: "unknown", "unknown alert", "unknown_user"       ║
║ ❌ WRONG:   "Unknown", "Unknown Alert", "Unknown_User"       ║
╚══════════════════════════════════════════════════════════════╝
```

**Standard defaults by field type:**

| Field Type | Default Value |
|------------|---------------|
| Severity | `"unknown"` |
| Alert context | `"unknown alert"` |
| Username | `"unknown_user"` |
| Hostname | `"unknown_host"` |
| IP address | `"0.0.0.0"` |
| Domain | `"unknown.com"` |
| Product/Source | `"unknown"` |
| Generic string | `""` (empty string) |

**Examples:**
```cy
# CORRECT - lowercase defaults
alert_severity = input.severity_id ?? 3
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? "unknown alert"
username = get_primary_user(input) ?? "unknown_user"
source_vendor = (input.metadata.product.vendor_name) ?? "unknown"

# WRONG - mixed case
alert_context = input.finding_info.title ?? "Unknown Alert"
username = get_primary_user(input) ?? "Unknown_User"
```

**Why lowercase?**
- Consistent parsing in downstream tasks
- Easier string comparison (`if severity == "unknown"`)
- No ambiguity between "Unknown" and "unknown"
- Standard convention across all security tools

## Task Architecture

### Component Fields
```json
{
  "name": "IP Reputation Enrichment",
  "cy_name": "ip_reputation_enrichment",  // auto-generated
  "description": "Enriches with IP reputation",
  "function": "enrichment",               // enrichment|reasoning|summarization
  "scope": "processing",                  // input|processing|output
  "categories": ["threat_intel"],
  "status": "enabled",
  "authored_by": "security_team"
}
```

### Task-Specific Fields
```json
{
  "script": "# Cy code...",              // REQUIRED
  "app": "Splunk",                       // REQUIRED - integration name
  "data_samples": [{...}],               // REQUIRED - see data_samples_guide.md
  "directive": "You are an analyst...",  // REQUIRED if using llm_run()
  "llm_config": {...}                    // REQUIRED if using llm_run()
}
```

## Common Task Patterns

### Integration + LLM Pattern
```cy
# 1. Get data from integration
vt_data = app::virustotal::ip_reputation(ip=ip)

# 2. Project key fields (don't pass entire response)
threat_summary = {
    "detections": vt_data.reputation_summary.malicious ?? 0,
    "asn_owner": vt_data.network_info.as_owner ?? ""
}

# 3. LLM analysis with context
analysis = llm_run(
    prompt="Alert Context: ${alert_context}...",
    data=threat_summary  # 50 tokens, not 3000!
)
```

### LLM Prompt Formatting (IMPORTANT)

**Always use triple-quoted multiline strings (`"""`) for LLM directives:**

```cy
# ✅ CORRECT - Use """ for readable, maintainable prompts
analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

    Analyze this IP reputation data and determine:
    1. Is this IP malicious?
    2. What is the confidence level?
    3. What actions should be taken?

    Provide a structured response with risk_level (high/medium/low).""",
    data=threat_summary
)

# ❌ AVOID - Single line strings are hard to read and maintain
analysis = llm_run(
    prompt="Alert Context: ${alert_context} Analyze this IP reputation data and determine: 1. Is this IP malicious? 2. What is the confidence level?",
    data=threat_summary
)
```

**Why multiline strings matter:**
- Prompts are often 5-20 lines - readability is critical
- Easy to add/remove instructions during iteration
- Variable interpolation (`${var}`) works the same way
- Makes code review and debugging much easier

### LLM JSON Output Guidelines (CRITICAL)

When asking the LLM to return JSON, follow these three rules:

```
╔══════════════════════════════════════════════════════════════╗
║ 🎯 JSON OUTPUT RULES                                         ║
╠══════════════════════════════════════════════════════════════╣
║ 1. KEEP IT SIMPLE: Only include fields needed for the goal   ║
║ 2. NO EXTRA FLAVOR: Don't ask for metadata, confidence       ║
║    scores, or analysis summaries unless actually needed      ║
║ 3. NO MARKDOWN WRAPPING: Ask for raw JSON, not ```json```    ║
╚══════════════════════════════════════════════════════════════╝
```

**❌ BAD - Over-engineered JSON request:**
```cy
analysis = llm_run(
    prompt="""Analyze this IP and return JSON with:
    {
      "verdict": "malicious|benign|suspicious",
      "confidence": "high|medium|low",
      "confidence_score": 0-100,
      "reasoning": "detailed explanation",
      "evidence": ["list", "of", "evidence"],
      "recommendations": ["list", "of", "actions"],
      "risk_factors": {...},
      "metadata": {...}
    }"""
)
```

**✅ GOOD - Simple, focused JSON request:**
```cy
analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

    Is IP ${ip} malicious based on ${vt_result.malicious_count}/80 detections?

    Return JSON (no markdown): {"verdict": "malicious|benign", "reason": "one sentence"}"""
)
```

**Why simple JSON matters:**
- Complex schemas often get partially filled or hallucinated
- Downstream tasks may only need 1-2 fields anyway
- Simpler prompts = more reliable outputs
- Extra fields add token cost without value

**For hypothesis/analysis tasks specifically:**
```cy
# ✅ GOOD - Ask for just the hypothesis
analysis = llm_run(
    prompt="""Based on the alert context and evidence, what is your hypothesis?

    Return JSON (no markdown): {"hypothesis": "your hypothesis here"}"""
)

# ❌ BAD - Asking for unnecessary structure
analysis = llm_run(
    prompt="""Provide analysis with:
    {
      "hypothesis": "...",
      "supporting_evidence": [...],
      "counter_evidence": [...],
      "confidence": "...",
      "next_steps": [...]
    }"""
)
```

**Always include "no markdown" or "raw JSON" in the prompt** to prevent the LLM from wrapping the response in \`\`\`json\`\`\` code blocks, which breaks JSON parsing.

### Multi-Integration Pattern
```cy
# Query multiple sources
vt_result = app::virustotal::ip_reputation(ip=ip)
abuse_result = app::abuseipdb::lookup_ip(ip=ip)

# Combine for analysis
combined = {
    "vt_detections": vt_result.malicious_count,
    "abuse_score": abuse_result.abuseConfidenceScore
}
```

### Hypothesis Task Pattern

For hypothesis generation tasks (workflow-specific, not reusable), see the dedicated `hypothesis-building-task` skill which contains:
- Complete Cy script pattern
- JSON schema for hypothesis objects
- How to extract hypotheses from runbooks
- Static + dynamic augmentation pattern

**More patterns:** See existing reference files below.

## Production Checklist

Before deploying:
- [ ] ✅ **Compiled with `compile_script()` - no errors**
- [ ] ✅ **Executed with `run_script()` for ALL data_samples - all passed**
- [ ] Script has `return {...}` statement
- [ ] Uses alert context pattern for LLM tasks
- [ ] Uses `enrich_alert()` for enrichment (not manual dict manipulation)
- [ ] LLM output stored in `ai_analysis` field (required for tasks using `llm_run()`)
- [ ] Only includes fields script actually uses
- [ ] Error handling for missing fields
- [ ] Integration actions verified
- [ ] Clear task name and description

## Reference Documentation

### OCSF Alert Schema
1. **`references/ocsf_schema_overview.md`** - All OCSF helper functions, field structure, and access patterns
2. **`references/ocsf_alert_structure.md`** - Detailed OCSF objects: evidences, observables, actor, device, vulnerabilities
3. **`references/ocsf_enrichment_pattern.md`** - How to add enrichments to alerts
4. **`references/critical_fields_guide.md`** - Mandatory data_sample fields (finding_info, observables)

### Core Patterns
5. **`references/task_dependencies_pattern.md`** - Alert context pattern details
6. **`references/task_design_methodology.md`** - 4-step design pattern
7. **`references/data_samples_guide.md`** - Building minimal test data

### Validation & Testing
8. **`references/task_validation_rules.md`** - All validation requirements
9. **`references/mcp_tools_usage_guide.md`** - MCP tool gotchas and tips

### Integration Patterns
10. **`references/integration_usage_guide.md`** - Calling integrations. **⚠️ Read the "Cy-Boundary Shape vs MCP Shape" section before writing any `app::` call** — the Cy boundary strips `status` on success and raises on error, so `result.status == "success"`/`"error"` is dead code.
11. **`references/integration_catalog.md`** - 15+ real examples
12. **`references/splunk_task_patterns.md`** - Splunk-specific tasks

### Advanced Topics
13. **`references/task_run_patterns.md`** - Calling tasks from tasks
14. **`references/rest_api_reference.md`** - REST API for tasks

## Quick Reference

### MCP Tools
```bash
# Testing (USE BEFORE create_task!)
compile_script(script)                    # Step 1: Syntax/type validation
run_script(script, input_data)            # Step 2: Runtime validation

# Task Management (USE AFTER testing passes)
create_task(name, script, data_samples, ...)
get_task(task_ids=[...])
update_task(task_id, ...)

# Task Discovery (Progressive Disclosure)
# All tools via unified analysi MCP server:
#   mcp__analysi__list_tasks()  → Lightweight summaries (no scripts)
#   mcp__analysi__get_task([...]) → Full details for specific tasks

# Validation
validate_alert(alert_data)

# Integration Discovery
list_integrations(configured_only=true)
list_integration_tools(integration_type)
```

**Testing Workflow Example:**
```json
// 1. Compile first
compile_script({"script": "..."})
// → Fix errors, repeat until clean

// 2. Test with each sample
run_script({"script": "...", "input_data": data_samples[0]})
run_script({"script": "...", "input_data": data_samples[1]})
// → Verify outputs, fix errors

// 3. NOW create task (will succeed!)
create_task({...})
```

### Common Cy Patterns
```cy
# Access input with null-safety
field = input.field ?? input.other_field ?? "default"

# Call integration
result = app::integration::action(param=value)

# LLM with context
analysis = llm_run(
    prompt="Alert Context: ${context}...",
    data=enrichment_data
)

# Return enriched alert (uses task's cy_name as key)
return enrich_alert(input, enrichment_data)
```

### Task Creation Template
```json
{
  "name": "App: Task Description",
  "app": "AppName",
  "script": "...",
  "function": "enrichment",
  "scope": "processing",
  "data_samples": [{"name": "Test", "input": {"finding_info": {"title": "...", "uid": "sample-001", "analytic": {"name": "Rule Name", "type": "Rule", "type_id": 1}}, "observables": [], "severity_id": 3, "enrichments": {}}, "expected_output": {...}}],
  "directive": "You are a security analyst...",
  "llm_config": {"default_model": "gpt-4o-mini", "temperature": 0.3, "max_tokens": 1500}
}
```
