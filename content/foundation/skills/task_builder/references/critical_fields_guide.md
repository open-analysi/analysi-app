# Critical Fields for Task data_samples

## Overview

This guide defines the **mandatory fields** that MUST be included in every Task's `data_samples`, regardless of whether the task script explicitly accesses them. These fields ensure reliable workflow execution, proper MCP validation, and effective LLM reasoning.

Alerts use the OCSF Detection Finding schema. Tasks access alert data through **helper functions** (see `ocsf_schema_overview.md`), but `data_samples` must contain the underlying OCSF fields those helpers read from.

## The Two Critical Fields

### 1. `finding_info` (ALWAYS REQUIRED)

**What it is:** The detection finding metadata — title, unique ID, and detection analytic (rule name).

**Why it's critical:**
- **LLM Context**: Title provides essential context for alert-specific reasoning
- **Alert Routing**: `analytic.name` is the detection rule name — used to route alerts to workflows. All alerts from the same detection rule share this value.
- **Workflow Identification**: Enables correlation across workflow steps
- **Investigation Tracking**: Links tasks back to specific detection rules

**IMPORTANT: `title` vs `analytic.name` are different:**
- `title` — human-readable summary, may vary per alert (e.g., "Suspicious login from 185.220.101.45")
- `analytic.name` — stable detection rule name (e.g., "SOC165 - Possible SQL Injection Payload Detected")

**Example:**
```json
{
  "finding_info": {
    "title": "Suspicious Login from Unusual Location",
    "uid": "alert-001",
    "analytic": {
      "name": "Unusual Login Location Detection",
      "type": "Rule",
      "type_id": 1
    }
  }
}
```

**Common Mistakes:**
- Do not omit `finding_info` because the script doesn't explicitly read it
- Do not use generic titles like "Test Alert" or "Unknown"
- Do not put the rule name in `finding_info.title` — it belongs in `finding_info.analytic.name`
- Use specific, descriptive titles that match real alert summaries

### 2. `observables` (ALWAYS REQUIRED)

**What it is:** Array of OCSF observables (IOC pointers) extracted from the alert. Each has a `type_id` (integer) and `value` (string).

**Why it's critical:**
- **Enrichment Tasks**: IP reputation, domain analysis, URL scanning depend on observables
- **Integration Queries**: Most threat intel integrations require observable values
- **Helper Functions**: `get_observables(input)`, `get_primary_observable_value(input)` read from this array
- **Investigation Completeness**: Observables drive the investigation process

**Example:**
```json
{
  "finding_info": {"title": "Malicious IP Communication Detected", "uid": "alert-002", "analytic": {"name": "Malicious IP Communication", "type": "Rule", "type_id": 1}},
  "observables": [
    {"type_id": 2, "type": "IP Address", "value": "185.220.101.45"},
    {"type_id": 1, "type": "Hostname", "value": "attacker.example"},
    {"type_id": 6, "type": "URL String", "value": "https://example.com/api?id=1%27%20OR%20%271%27%3D%271"}
  ]
}
```

**Observable type_id values:**
- `2` - IP Address
- `1` - Hostname / Domain
- `6` - URL String (must be URL-encoded if special characters)
- `8` - Hash (file hash: MD5, SHA1, SHA256)
- `5` - Email Address
- `7` - File Name
- `9` - Process Name

**When Alert Has No Observables:**

Some alerts (user behavior, policy violations) may not have technical IOCs. In these cases, use an empty array:

```json
{
  "finding_info": {"title": "User Privilege Escalation Detected", "uid": "alert-003", "analytic": {"name": "User Privilege Escalation", "type": "Rule", "type_id": 1}},
  "observables": []
}
```

**Common Mistakes:**
- Do not omit `observables` field entirely
- Do not use `null` instead of empty array `[]`
- Do not forget `type_id` — helpers depend on it for type filtering
- Always include `observables` field (populated or empty array)
- URL-encode URLs with special characters
- Use correct `type_id` from the list above

## Validation Rules

### MCP Validation Failure

If you omit critical fields, MCP validation will fail with errors like:

```
Task data_samples validation failed: field 'finding_info' not found in input schema.
Script accesses fields not present in data_samples.
```

**Root Cause:** Script uses `input.finding_info.title` or `input.finding_info.analytic.name` but data_samples lacks `finding_info`.

**Solution:** Always include both `finding_info` and `observables` in EVERY sample.

### Required Structure

```json
{
  "data_samples": [
    {
      "finding_info": {"title": "Required: Never omit this", "uid": "sample-001", "analytic": {"name": "Detection Rule Name", "type": "Rule", "type_id": 1}},
      "observables": [
        {"type_id": 2, "type": "IP Address", "value": "185.220.101.45"}
      ],
      "severity_id": 4,
      "enrichments": {}
    }
  ]
}
```

## Implementation Checklist

Before finalizing any Task:

- [ ] **Every data_sample includes `finding_info` with title and analytic.name**
- [ ] **Every data_sample includes `observables` (array or empty `[]`)**
- [ ] Title is specific and descriptive (not "Test" or "Unknown")
- [ ] Observables use correct `type_id` values (2=IP, 1=Domain, 6=URL, etc.)
- [ ] URLs are properly URL-encoded
- [ ] At least 2 samples provided
- [ ] Samples cover normal and edge cases
- [ ] Validated with `mcp__analysi__validate_alert`
- [ ] Tested with `mcp__analysi__run_script`

## Why This Matters

### Historical Context

In earlier implementations, we followed a "minimal data_samples" philosophy:
> "Include ONLY fields your script explicitly accesses"

This caused widespread failures when:
1. Scripts used fallback patterns like `input.finding_info.title ?? input.title` or `input.rule_name ?? input.finding_info.analytic.name`
2. Enrichment tasks expected observables but found empty data
3. MCP validation rejected scripts for accessing "missing" fields

### Current Best Practice

**Critical fields first, then minimal:**
1. Start with `finding_info` and `observables`
2. Add only script-specific fields (e.g., `evidences`, `actor`, `device`)
3. Keep it as simple as possible, but no simpler

This ensures tasks work reliably while maintaining manageable data_samples.

## Related Documentation

- **Complete Guide**: `data_samples_guide.md` - Full patterns and examples
- **Task Builder**: `../SKILL.md` - Task creation workflow
- **Alert Context Pattern**: `task_dependencies_pattern.md` - Why finding_info matters
- **OCSF Schema**: See `ocsf_schema_overview.md` and `ocsf_alert_structure.md` for complete field reference

## Quick Reference

**Template for Every Task:**
```json
{
  "finding_info": {"title": "Specific Alert Title", "uid": "sample-001", "analytic": {"name": "Detection Rule Name", "type": "Rule", "type_id": 1}},
  "observables": [
    {"type_id": 2, "type": "IP Address", "value": "185.220.101.45"}
  ],
  "severity_id": 4,
  "enrichments": {}
}
```

**Remember:**
- `finding_info` - ALWAYS (with descriptive title AND analytic.name for the rule)
- `observables` - ALWAYS (even if empty `[]`)
- Then add script-specific fields (`evidences`, `actor`, `device`, etc.)
- Validate before creating task
