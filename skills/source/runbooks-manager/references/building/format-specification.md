# Runbook.md Format Specification

## Structure
```
---
[YAML Frontmatter]
---

[Markdown Body]
```

## YAML Frontmatter

### Required Fields

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| detection_rule | string | Exact detection rule name | `"SOC165 - SQL Injection"` |
| alert_type | string | Threat category | `"SQL Injection"` |
| source_category | enum | Alert source (see MCP tool) | `WAF`, `EDR`, `Identity` |
| mitre_tactics | array | MITRE ATT&CK IDs | `[T1190, T1059]` |
| integrations_required | array | Must-have integrations | `[splunk]` |
| integrations_optional | array | Nice-to-have integrations | `[virustotal, abuseipdb]` |

### Optional Fields
- `version`: Semantic versioning (e.g., `"1.2.0"`)
- `last_updated`: YYYY-MM-DD format
- `author`: Maintainer identifier

## Markdown Body Specification

### Title Format
```markdown
# [Detection Rule Name] Investigation Runbook
```

### Steps Section
```markdown
## Steps
```

### Step Structure

#### Basic Step
```markdown
### N. Step Name [★]
- **Action:** What to do
- **Pattern:** pattern_type
- **Input:** input_data
- **Output:** output_key
```

#### Parallel Sub-Steps
```markdown
### N. Parent Step Name
- **Parallel:** Yes

#### Na. First Sub-Step
- **Action:** ...

#### Nb. Second Sub-Step
- **Action:** ...
```

### Step Attributes

| Attribute | Required | Description | Example |
|-----------|----------|-------------|---------|
| Action | ✅ | What to do | `"Analyze alert and form hypotheses"` |
| Pattern | ✅ | Execution type | `hypothesis_formation`, `integration_query` |
| Input | ✅ | Data sources | `get_src_ip(alert)`, `outputs.sql_payloads` |
| Output | ✅ | Result key | `context_summary`, `attack_verdict` |
| Depends On | ⚪ | Step dependencies | `Steps 2a, 2b, 3` |
| Integration | ⚪ | Suggests category of tool | `siem`, `threat_intel`, `edr` |
| Query | ⚪ | ONLY if exact query provided | Omit unless analysts documented |
| Parallel | ⚪ | Concurrent execution | `Yes` or `No` |
| Condition | ⚪ | Conditional logic | `IF virustotal configured` |
| Focus | ⚪ | Analysis guidance | `Decode payloads, assess sophistication` |
| Decision Points | ⚪ | Success criteria | See patterns below |

### Pattern Types
- `hypothesis_formation` - Form investigation theories
- `evidence_correlation` - Correlate multiple sources
- `payload_analysis` - Decode/analyze payloads
- `impact_assessment` - Determine attack success
- `threat_synthesis` - Full context analysis
- `integration_query` - Direct integration call

### Criticality Markers

#### ★ (Star)
- **Meaning:** Critical step - MUST execute for minimum viable investigation
- **Placement:** After step name
- **Example:** `### 1. Alert Understanding ★`

#### No Marker
- **Meaning:** Optional/degradable step
- **Behavior:** Can skip if integration unavailable or for speed

## Include Directives (WikiLinks Syntax)

### Basic Include
```markdown
![[path/to/sub_runbook.md]]
```

### Include with Parameters
```markdown
![[common/evidence/siem_evidence.md]]
- **Parameters:**
  - triggering_query: `query_string`
  - time_window: -1h
```

### Include with Overrides
```markdown
![[common/threat_intel.md]]
- **Override:**
  - integrations: [virustotal]
  - skip_steps: [3, 4]
```

### Conditional Include
```markdown
![[path/to/sub_runbook.md|if:condition]]
```

**Condition Examples:**
- `if:source_category=Web`
- `if:alert_type=SQL*`
- `if:severity>=high` (Note: `severity` is an OCSF path on the Detection Finding)

## Conditional Logic Section

```markdown
## Conditional Logic

### Branch: [Branch Name]
- **Condition:** condition_expression
- **Additional Steps:** steps_to_add
- **Skip:** steps_to_skip
- **Fast Track:** shortcut_description
- **Escalation:** escalation_action
```

## Query Templates and Integration Suggestions

**IMPORTANT:** Queries and integrations in runbooks are **templates and suggestions**, not exact implementations.

The alert-planner will:
- Choose specific tools based on what's available (VirusTotal vs Cisco Talos for threat intel)
- Adapt query syntax to the actual SIEM (Splunk SPL vs Sentinel KQL vs Sumo Logic)
- Select appropriate integration instances (production vs test environments)

Examples:
- Runbook says: `Integration: threat_intel` → Planner picks available TI tool
- Runbook says: `Query: search for lateral movement` → Planner writes actual query
- Runbook says: `Integration: siem` → Planner uses configured SIEM

## Field References Use OCSF Paths and Helpers

**CRITICAL:** Field references use **OCSF paths** for direct fields and **helper functions** for fields that require extraction logic.

| Reference | Type | Description |
|-----------|------|-------------|
| `finding_info.title` | OCSF path | Direct field on the Detection Finding |
| `severity` | OCSF path | Direct field on the Detection Finding |
| `time` | OCSF path | Direct field on the Detection Finding |
| `disposition` | OCSF path | Direct field on the Detection Finding |
| `finding_info.desc` | OCSF path | Direct field on the Detection Finding |
| `get_src_ip(alert)` | Helper function | Extracts source IP from alert |
| `get_dst_ip(alert)` | Helper function | Extracts destination IP from alert |
| `get_url(alert)` | Helper function | Extracts URL from alert |
| `get_primary_device(alert)` | Helper function | Extracts primary hostname from alert |
| `get_primary_user(alert)` | Helper function | Extracts primary user from alert |
| `get_http_method(alert)` | Helper function | Extracts HTTP method from alert |
| `get_user_agent(alert)` | Helper function | Extracts user agent from alert |
| `get_dst_domain(alert)` | Helper function | Extracts destination domain from alert |

**The planner uses these OCSF paths and helper functions to access alert data.**

## Parameter Substitution

### Variable Namespaces
- **Alert Fields:** OCSF paths or helper functions on the alert
  - Direct paths: `${finding_info.title}`, `${time}`, `${severity}`
  - Helper functions: `${get_src_ip(alert)}`, `${get_primary_user(alert)}`, `${get_url(alert)}`
- **Output References:** `${outputs.step_key.field}` - Previous step outputs
  - Examples: `${outputs.sql_injection_attempts.uri}`, `${outputs.response_patterns.unique_sizes}`
- **Parameters:** `${params.name}` - Sub-runbook parameters
  - Examples: `${params.time_window}`, `${params.triggering_query}`

### Field Access for Integrations
When specifying fields for integration queries:
- Use OCSF paths or helper functions: `get_src_ip(alert)`, `get_dst_ip(alert)`
- Example: `- **Fields:** get_src_ip(alert), get_dst_ip(alert)`

### Example
```markdown
- **Query:** `index=auth user="${get_primary_user(alert)}" src="${get_src_ip(alert)}" earliest="${time}-30m"`
- **Input:** outputs.sql_injection_attempts, outputs.response_patterns
- **Fields:** get_src_ip(alert)  # For integration field parameter
```

## Token Efficiency Guidelines

### Target Size
- **Optimal:** 500-800 tokens per runbook
- **Maximum:** 1000 tokens
- **Sub-runbooks:** 100-300 tokens each

### Efficiency Techniques
1. Use terse attribute format (not prose)
2. Extract common patterns to sub-runbooks
3. Use WikiLinks (`![[path.md]]`) instead of duplication
4. Avoid verbose descriptions
5. Use consistent abbreviations

## Validation Rules

### YAML Frontmatter
1. All required fields must be present
2. source_category must be valid enum value
3. MITRE tactics must match pattern T####
4. Arrays cannot be empty if required

### Markdown Body
1. Must have `## Steps` section
2. Step numbering must be sequential
3. Critical steps must have ★ marker
4. WikiLink include paths must be valid (e.g., `![[path.md]]`)
5. Pattern values must be valid enums

### Cross-Validation
1. Required integrations must appear in steps
2. Output keys must be unique
3. Input references must exist in prior steps
4. Parallel steps cannot have dependencies

## Example Minimal Valid Runbook

```markdown
---
detection_rule: Test Alert
alert_type: Test Type
source_category: Web
mitre_tactics: [T1190]
integrations_required: [splunk]
integrations_optional: []
---

# Test Alert Investigation Runbook

## Steps

### 1. Alert Understanding ★
- **Action:** Analyze alert
- **Pattern:** llm_analysis
- **Input:** OCSF alert fields
- **Output:** context_summary

### 2. Evidence Collection ★
- **Action:** Get triggering event
- **Integration:** splunk
- **Pattern:** integration_query
- **Query:** `index=* alert_id="${alert_id}"`
- **Output:** triggering_event

### 3. Final Analysis ★
- **Action:** Synthesize findings
- **Pattern:** llm_synthesis
- **Input:** ALL enrichments
- **Output:** detailed_analysis
```

## Parser Implementation Notes

When implementing a parser for runbook.md:

1. **Two-phase parsing:**
   - Phase 1: Parse YAML frontmatter
   - Phase 2: Parse markdown with context from YAML

2. **Include resolution:**
   - Resolve WikiLink includes (`![[path.md]]`) recursively
   - Apply parameters and overrides
   - Handle circular reference detection

3. **Step extraction:**
   - Use regex for step headers
   - Parse attributes as key-value pairs
   - Maintain step hierarchy (N, Na, Nb)

4. **Output format:**
   - Convert to structured JSON/dict
   - Preserve step ordering
   - Maintain parent-child relationships
