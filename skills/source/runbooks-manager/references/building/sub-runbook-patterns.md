# Sub-Runbook Patterns Guide

## Overview

Sub-runbooks are reusable investigation patterns extracted from detection-specific runbooks. They enable DRY (Don't Repeat Yourself) principles and ensure consistency across similar investigations.

## When to Extract a Sub-Runbook

### The Rule of Three

Extract a pattern to a sub-runbook when:
1. The same steps appear in **3 or more** detection runbooks
2. The logic is **source_category** or **alert_type** specific
3. The pattern represents a **standard investigation procedure**

### Extraction Triggers

| Pattern Type | When to Extract | Where to Place |
|--------------|----------------|----------------|
| Universal steps | Always present (e.g., alert understanding) | `common/universal/` |
| Source-specific | 3+ runbooks from same source_category | `common/by_source/` |
| Type-specific | 3+ runbooks of same alert_type | `common/by_type/` |
| Evidence collection | 3+ runbooks with similar queries | `common/evidence/` |
| Enrichment | 3+ runbooks using same external sources | `common/enrichment/` |
| Analysis | 3+ runbooks with same decision logic | `common/analysis/` |

## Sub-Runbook Structure

### Header Documentation

Every sub-runbook must start with a documentation header:

```markdown
<!--
Sub-Runbook: threat_intel_enrichment
Purpose: Enrich IOCs with threat intelligence from multiple sources
Category: enrichment
Parameters:
  - targets: List of IOCs to enrich (IPs, domains, hashes)
  - sources: Which threat intel sources to use (default: all)
  - skip_optional: Whether to skip optional sources (default: false)
Outputs:
  - threat_reputation: Combined reputation scores
  - threat_context: Contextual threat information
Usage: ![[common/enrichment/threat_intel_enrichment.md]]
-->
```

### Parameter Definition

Sub-runbooks can accept parameters for flexibility:

```markdown
<!-- Parameters:
- ${triggering_query}: SIEM query for triggering event
- ${time_window}: Time range for searches (default: -1h)
- ${correlation_field}: Field to correlate on (default: src_ip)
-->
```

### Body Structure

```markdown
### [Step Name]
- **Action:** ${action_description}
- **Pattern:** integration_query | llm_analysis | llm_synthesis
- **Integration:** ${integration_name}
- **Query:** `${triggering_query}`
- **Output:** ${output_key}
```

## Common Sub-Runbook Patterns

### 1. Alert Understanding (Universal)

**File:** `common/universal/alert-understanding.md`

```markdown
<!--
Sub-Runbook: alert-understanding
Purpose: Standard alert comprehension and hypothesis formation
Parameters: None (uses OCSF alert fields)
Outputs: context_summary, investigation_hypotheses
-->

### 1. Alert Understanding & Initial Assessment ★
- **Action:** Analyze alert and form investigation hypotheses
- **Pattern:** llm_analysis
- **Input:** OCSF alert fields, detection_rule
- **Outputs:**
  - context_summary: Human-readable alert summary
  - investigation_hypotheses: Theories to investigate
- **Focus:** Understanding what triggered the alert and possible explanations
```

### 2. SIEM Evidence Collection (Parameterized)

**File:** `common/evidence/siem_evidence_collection.md`

```markdown
<!--
Sub-Runbook: siem_evidence_collection
Purpose: Collect triggering and supporting evidence from SIEM
Parameters:
  - triggering_query: Query for the triggering event
  - supporting_query: Query for related events
  - time_window: Time range (default: -1h)
Outputs: triggering_event, supporting_evidence
-->

### Evidence Collection ★
- **Parallel:** Yes

#### a. Triggering Event ★
- **Action:** Retrieve event that triggered the alert
- **Pattern:** integration_query
- **Integration:** splunk
- **Query:** `${triggering_query}`
- **Output:** triggering_event

#### b. Supporting Evidence ★
- **Action:** Search for related activity
- **Pattern:** integration_query
- **Integration:** splunk
- **Query:** `${supporting_query} earliest=${time_window}`
- **Output:** supporting_evidence
```

### 3. Threat Intelligence Enrichment (Flexible)

**File:** `common/enrichment/threat_intel_enrichment.md`

```markdown
<!--
Sub-Runbook: threat_intel_enrichment
Purpose: Multi-source threat intelligence enrichment
Parameters:
  - targets: IOCs to enrich
  - skip_sources: Sources to skip
Outputs: Combined threat intelligence
-->

### Threat Intelligence Enrichment
- **Parallel:** Yes

#### a. IP Reputation
- **Action:** Check IP reputation
- **Pattern:** integration_query
- **Integration:** virustotal
- **Condition:** IF "virustotal" not in ${skip_sources}
- **Fields:** ${targets.ips}
- **Output:** ip_reputation

#### b. Domain Analysis
- **Action:** Analyze domains
- **Pattern:** integration_query
- **Integration:** virustotal
- **Condition:** IF "virustotal" not in ${skip_sources} AND domains exist
- **Fields:** ${targets.domains}
- **Output:** domain_reputation
```

### 4. Final Analysis Trio (Universal)

**File:** `common/universal/final-analysis-trio.md`

```markdown
<!--
Sub-Runbook: final-analysis-trio
Purpose: Standard conclusion pattern for all investigations
Parameters: None (uses all prior enrichments)
Outputs: detailed_analysis, disposition, summary
-->

### Final Analysis ★
- **Sequential:** Must run in order

#### a. Detailed Analysis ★
- **Action:** Comprehensive technical synthesis
- **Pattern:** llm_synthesis
- **Input:** ALL enrichments
- **Focus:** Complete technical analysis with threat assessment
- **Output:** detailed_analysis

#### b. Disposition & Summary ★
- **Parallel:** Yes
- **Actions:**
  - Determine verdict (TP/FP/Benign) with confidence score
  - Generate executive summary (128 chars max)
- **Pattern:** llm_analysis
- **Input:** enrichments.detailed_analysis
- **Output:** disposition, summary
```

## Using Sub-Runbooks

### Basic Include

```markdown
![[common/universal/alert-understanding.md]]
```

### Include with Parameters

```markdown
![[common/evidence/siem_evidence_collection.md]]
- **Parameters:**
  - triggering_query: `index=web uri="*UNION SELECT*" src="${source_ip}"`
  - supporting_query: `index=web src="${source_ip}"`
  - time_window: -2h
```

### Include with Overrides

```markdown
![[common/enrichment/threat_intel_enrichment.md]]
- **Override:**
  - targets: [${source_ip}, ${extracted_domains}]
  - skip_sources: [shodan, censys]  # Only use VT and AbuseIPDB
```

### Conditional Include

```markdown
![[common/by_source/web_common.md|if:source_category=Web]]
![[common/by_type/sql_injection_base.md|if:alert_type~=SQL]]
![[common/escalation/immediate_response.md|if:severity>=high]]
```

**Condition Operators:**
- `=` : Exact match
- `!=` : Not equal
- `~=` : Contains/pattern match
- `>=`, `<=`, `>`, `<` : Comparisons (for severity)

## Creating a New Sub-Runbook

### Step 1: Identify the Pattern

Look for repeated steps across runbooks:
- Same integration calls
- Same analysis logic
- Same evidence collection

### Step 2: Extract Common Elements

Identify what's:
- **Constant:** Same in all uses
- **Variable:** Different per runbook (becomes parameters)
- **Optional:** Sometimes present (becomes conditional)

### Step 3: Create the Sub-Runbook

```markdown
<!--
Sub-Runbook: [name]
Purpose: [description]
Category: [universal|by_source|by_type|evidence|enrichment|analysis]
Parameters:
  - param1: [description] (default: value)
  - param2: [description]
Outputs:
  - output1: [description]
  - output2: [description]
-->

### [Step structure following main pattern]
```

### Step 4: Update Detection Runbooks

Replace extracted steps with WikiLinks:

**Before:**
```markdown
### 2. Check IP Reputation
- **Action:** Query VirusTotal for IP
- **Pattern:** integration_query
- **Integration:** virustotal
- **Fields:** source_ip
- **Output:** ip_reputation

### 3. Check IP Abuse History
- **Action:** Query AbuseIPDB
- **Pattern:** integration_query
- **Integration:** abuseipdb
- **Fields:** source_ip
- **Output:** abuse_history
```

**After:**
```markdown
![[common/enrichment/threat_intel_enrichment.md]]
- **Parameters:**
  - targets: {ips: [${source_ip}]}
```

## Parameter Passing Patterns

### Simple Parameters

```markdown
- **Parameters:**
  - field_name: value
  - another_field: ${alert_field}
```

### Complex Parameters

```markdown
- **Parameters:**
  - targets:
      ips: [${source_ip}, ${dest_ip}]
      domains: ${extracted_domains}
      hashes: ${file_hashes}
```

### Conditional Parameters

```markdown
- **Parameters:**
  - time_window: ${severity == "critical" ? "-30m" : "-2h"}
  - depth: ${alert_type == "APT" ? "deep" : "standard"}
```

## Override Mechanisms

### Skip Steps

```markdown
- **Override:**
  - skip_steps: [2, 3]  # Skip steps 2 and 3
```

### Replace Values

```markdown
- **Override:**
  - integration: sentinel  # Use Sentinel instead of Splunk
  - query_index: security  # Override default index
```

### Add Conditions

```markdown
- **Override:**
  - add_condition: "AND severity >= high"
  - required: true  # Make optional step required
```

## Best Practices

### DO:
1. **Document thoroughly** - Include purpose, parameters, outputs
2. **Use meaningful names** - Describe what the sub-runbook does
3. **Parameterize wisely** - Balance flexibility vs complexity
4. **Version carefully** - Breaking changes need new versions
5. **Test thoroughly** - Validate with multiple runbooks
6. **Keep focused** - One sub-runbook, one purpose

### DON'T:
1. **Over-extract** - Not everything needs to be a sub-runbook
2. **Under-document** - Missing parameter docs cause errors
3. **Hard-code values** - Use parameters for flexibility
4. **Create duplicates** - Check existing patterns first
5. **Mix concerns** - Keep evidence, enrichment, analysis separate
6. **Forget validation** - Test parameter substitution

## Evolution Path

### Phase 1: Direct Steps
All steps directly in detection runbooks.

### Phase 2: Basic Extraction
Extract obvious patterns (alert understanding, final analysis).

### Phase 3: Parameterization
Add parameters to make sub-runbooks flexible.

### Phase 4: Advanced Patterns
Complex conditional logic, multi-level includes.

### Phase 5: Full Abstraction
Detection runbooks become primarily WikiLink includes with minimal custom logic.

## Troubleshooting

### Common Issues

**Problem:** Parameters not substituting
**Solution:** Check parameter names match exactly, including case

**Problem:** Circular reference detected
**Solution:** Sub-runbooks cannot include each other circularly

**Problem:** Output not found
**Solution:** Verify sub-runbook actually creates the expected output key

**Problem:** Integration not available
**Solution:** Use conditional includes or override to skip

## Validation

### Pre-Extraction Checklist
- [ ] Pattern appears in 3+ runbooks
- [ ] Logic is truly reusable
- [ ] Parameters identified
- [ ] Output keys documented

### Post-Extraction Checklist
- [ ] Documentation header complete
- [ ] Parameters work in all use cases
- [ ] Original runbooks updated to use WikiLinks (`![[path.md]]`)
- [ ] Validation passes
