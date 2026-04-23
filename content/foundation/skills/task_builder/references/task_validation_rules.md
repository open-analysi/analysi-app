# Task Validation Rules and Requirements

## Overview

Tasks must pass multiple levels of validation before they can be created or executed. This document provides comprehensive coverage of all validation rules and how to resolve common validation errors.

## Validation Layers

### Layer 1: Field Validation (Pydantic Schema)

Validates that all required fields are present and have correct types.

#### Required Fields

```json
{
  "name": "string (1-255 chars)",
  "script": "string (min 1 char)",
  "tenant": "string"
}
```

#### Optional but Validated Fields

```json
{
  "cy_name": "^[a-z][a-z0-9_]*$ (1-255 chars)",
  "function": "enrichment|summarization|extraction|reasoning|planning|data_conversion|visualization|search",
  "scope": "input|processing|output",
  "mode": "saved|ad_hoc",
  "categories": ["array", "of", "strings"],
  "data_samples": [{"sample": "data"}]
}
```

### Layer 2: Cy Script Syntax Validation

Script must be valid Cy language syntax.

**Validation:** Use `validate_cy_script` MCP tool before creating task.

```json
{
  "script": "return {\"result\": \"test\"}"
}
```

Returns:
```json
{
  "valid": true|false,
  "has_output": true|false,
  "errors": ["list of errors"]
}
```

### Layer 3: Output Statement Validation

**CRITICAL RULE:** All scripts MUST contain a `return {...}` statement.

✅ **Valid:**
```cy
return {"result": "value"}
```

```cy
data = process_data(input)
return {
    "processed": data,
    "status": "complete"
}
```

❌ **Invalid:**
```cy
# Missing return statement
data = process_data(input)
```

```cy
# Cy uses return, not output assignment
output = {"result": "value"}
```

### Layer 4: data_samples Validation

**Core Philosophy:** Include ONLY fields your script actually uses. Don't add fields "just in case" or because they exist in the OCSF alert schema.

#### Rule 1: Must be non-empty list

❌ **Invalid:**
```json
{
  "data_samples": null
}
```

```json
{
  "data_samples": []
}
```

✅ **Valid:**
```json
{
  "data_samples": [{"observables": [{"value": "185.220.101.45", "type": "IP Address"}]}]
}
```

#### Rule 2: Minimal Fields Approach - Only What Script Uses

**CRITICAL:** Include ONLY fields your script explicitly accesses. This reduces maintenance and avoids false dependencies.

❌ **Invalid - Too Many Fields:**
```cy
# Script only uses IP
ip = get_primary_observable_value(input) ?? "0.0.0.0"
return {"ip": ip}
```

```json
// BAD: Including unnecessary fields
{"data_samples": [{
  "alert_id": "AL-001",  // Script doesn't use this
  "title": "Alert",       // Script doesn't use this
  "severity": "high",     // Script doesn't use this
  "observables": [{"value": "185.220.101.45", "type": "IP Address"}],
  "enrichments": {}       // Script doesn't use this
}]}
```

✅ **Valid - Minimal Fields:**
```cy
# Script only uses IP
ip = get_primary_observable_value(input) ?? "0.0.0.0"
return {"ip": ip}
```

```json
// GOOD: Only what script needs
{"data_samples": [{
  "observables": [{"value": "185.220.101.45", "type": "IP Address"}]
}]}
```

#### Rule 3: Use validate_alert for OCSF Tasks

For tasks processing OCSF alerts, validate samples with the MCP tool:

```python
# Validate your minimal sample
sample = {
  "observables": [{"value": "185.220.101.45", "type": "IP Address"}],
  "enrichments": {}  # Only if script accesses enrichments
}

result = validate_alert(alert_data=sample)
assert result["valid"], f"Sample validation failed: {result['errors']}"
```

**Important:** The validator checks OCSF compliance, but your task may only need a subset of fields.

#### Rule 4: Realistic Test Data

Use real-world values from security scenarios:

❌ **Poor quality:**
```json
[{"ip": "1.2.3.4"}]  // Not a real IP
```

✅ **Good quality - Minimal but Realistic:**
```json
[
  {"observables": [{"value": "185.220.101.45", "type": "IP Address"}]},  // Real Tor exit node
  {"observables": [{"value": "8.8.8.8", "type": "IP Address"}]}          // Google DNS
]
```

#### Rule 5: Branch Coverage Requirements (MANDATORY)

**Create N data_samples where N ≥ number of major code branches:**

```
╔══════════════════════════════════════════════════════════════╗
║ 🎯 BRANCH COVERAGE REQUIREMENT                               ║
╠══════════════════════════════════════════════════════════════╣
║ Each sample must trigger a DIFFERENT code path:              ║
║ • Happy path (all fields present)                            ║
║ • Fallback paths (each ?? chain needs a sample)              ║
║ • Early returns (missing required field)                     ║
║ • Error handling paths                                       ║
╚══════════════════════════════════════════════════════════════╝
```

**If integration IS configured/testable:**
- Provide **N samples** (one per major branch, minimum 2)
- Test each with `run_script`
- Document which branch each sample triggers:
  ```
  Sample 1: Tests observables[0].value path (happy path)
  Sample 2: Tests evidences[0].src_endpoint.ip fallback
  Sample 3: Tests missing IP early return
  ```

**If integration NOT configured:**
- Provide **N samples** (one per major branch)
- Must compile successfully with `validate_cy_script`
- Mark task description with "⚠️ Requires {integration} configuration"

**All samples must cover:**
- At least one happy path (normal operation)
- Fallback paths for each ?? chain in extraction logic
- Edge cases (empty result, missing field, error condition)
- Realistic security data (real IP addresses, usernames, IOCs)

✅ **Branch Coverage Example (3 branches → 3 samples):**

For a script with: `ip = get_primary_observable_value(input) ?? get_src_ip(input) ?? null`

```json
{
  "data_samples": [
    {
      "_branch": "Happy path - observable present",
      "finding_info": {"title": "Suspicious IP Connection to 185.220.101.45", "uid": "sample-001", "analytic": {"name": "Suspicious IP Connection", "type": "Rule", "type_id": 1}},
      "observables": [{"value": "185.220.101.45", "type": "IP Address"}],
      "enrichments": {}
    },
    {
      "_branch": "Fallback - uses src_endpoint IP from evidence",
      "finding_info": {"title": "Internal Connection Alert from 192.168.1.100", "uid": "sample-002", "analytic": {"name": "Internal Connection Alert", "type": "Rule", "type_id": 1}},
      "evidences": [{"src_endpoint": {"ip": "192.168.1.100"}}],
      "enrichments": {}
    },
    {
      "_branch": "Early return - no IP available",
      "finding_info": {"title": "Policy Violation Detected", "uid": "sample-003", "analytic": {"name": "Non-IP Alert", "type": "Rule", "type_id": 1}},
      "enrichments": {}
    }
  ]
}
```

**Best Practices:**
- Document each sample's purpose with `_branch` or comments
- Use real-world data (actual IPs, domains, usernames)
- Include edge cases: empty results, null values, error conditions
- Keep samples minimal - only fields the script uses

### Layer 5: cy_name Validation

#### Auto-Generation Rules

If `cy_name` is not provided, it's auto-generated from `name`:

```
Name: "IP Reputation Enrichment"
→ cy_name: "ip_reputation_enrichment"

Name: "User Privilege Check (AD LDAP)"
→ cy_name: "user_privilege_check_ad_ldap"

Name: "Alert Summary - V2"
→ cy_name: "alert_summary_v2"
```

Algorithm:
1. Convert to lowercase
2. Replace spaces and special characters with underscore
3. Remove consecutive underscores
4. Trim leading/trailing underscores

#### Validation Pattern

`cy_name` must match: `^[a-z][a-z0-9_]*$`

✅ **Valid:**
- `ip_reputation_check`
- `user_analysis`
- `alert_v2`

❌ **Invalid:**
- `IP_Check` (uppercase not allowed)
- `123_task` (cannot start with number)
- `user-check` (hyphens not allowed)
- `_hidden_task` (cannot start with underscore)

#### Uniqueness Check

`cy_name` must be unique within a tenant.

**Error:** "Task with cy_name 'ip_reputation_enrichment' already exists for tenant 'default'"

**Resolution:** Choose a different name or use a versioned suffix:
- `ip_reputation_enrichment_v2`
- `ip_reputation_enrichment_vt_only`

## Common Validation Errors

### Error 1: Missing Required Fields

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "script"],
      "msg": "Field required"
    }
  ]
}
```

**Resolution:** Provide all required fields (name, script, tenant).

### Error 2: Invalid Cy Syntax

```json
{
  "detail": "Cy script validation failed: Unexpected token at line 5"
}
```

**Resolution:**
1. Use `validate_cy_script` MCP tool to check syntax
2. Review Cy language documentation (cy_language_programming skill)
3. Check for common issues:
   - Missing quotes around strings
   - Using $ outside interpolation ($ only in "${var}" strings)
   - Wrong operators (use `==` for comparison, `=` for assignment)

### Error 3: Script Missing Return Statement

```json
{
  "detail": "Script must contain 'return {...}' statement"
}
```

**Resolution:** Add `return {...}` statement at the end of your script.

### Error 4: Invalid Function Type

```json
{
  "detail": "Invalid task function 'analysis'. Must be one of: enrichment, summarization, extraction, reasoning, planning, data_conversion, visualization, search"
}
```

**Resolution:** Use one of the valid function types.

### Error 5: Invalid Scope

```json
{
  "detail": "Invalid task scope 'transform'. Must be one of: input, processing, output"
}
```

**Resolution:** Use one of the valid scopes:
- `input` - for data ingestion tasks
- `processing` - for internal transformation/analysis
- `output` - for export/sync tasks

### Error 6: data_samples Validation Failure

```json
{
  "detail": "data_samples[0] missing field accessed by script: 'observables'"
}
```

**Resolution:** Include ONLY the fields your script actually accesses:

```cy
# If script ONLY does this:
ip = get_primary_observable_value(input) ?? get_src_ip(input)

# Then data_samples needs ONLY:
```

```json
{
  "data_samples": [{
    "observables": [{"value": "185.220.101.45", "type": "IP Address"}]
  }]
}
```

**Remember:** Don't add fields "just because they exist in the OCSF schema" - only what your script uses.

### Error 7: cy_name Pattern Mismatch

```json
{
  "detail": "cy_name must match pattern ^[a-z][a-z0-9_]*$"
}
```

**Resolution:** Fix cy_name to:
- Start with lowercase letter
- Use only lowercase letters, numbers, underscores
- No spaces or special characters

## Validation Workflow Best Practices

### 1. Validate Script First

Before creating the task, validate the Cy script:

```json
// MCP tool call
{
  "tool": "validate_cy_script",
  "params": {
    "script": "return {\"result\": \"test\"}"
  }
}
```

### 2. Test with Minimal data_samples

Start with ONLY the fields your script uses:

```json
// If script only uses IP:
{
  "data_samples": [{
    "observables": [{"value": "185.220.101.45", "type": "IP Address"}]
  }]
}
```

For OCSF alert tasks, validate first:
```python
sample = {"observables": [{"value": "185.220.101.45", "type": "IP Address"}]}
validate_alert(alert_data=sample)
```

### 3. Incremental Complexity

Add fields incrementally:

```cy
# Step 1: Minimal
return {"test": "hello"}

# Step 2: Add input access
value = input["field"]
return {"value": value}

# Step 3: Add logic
value = input["field"]
processed = value * 2
return {"result": processed}
```

### 4. Use Descriptive Names

Choose clear, descriptive names that communicate purpose:

✅ Good:
- "IP Reputation Enrichment"
- "Login Risk Correlation"
- "Alert Disposition and Summary"

❌ Bad:
- "Task 1"
- "Helper"
- "Process"

## Integration-Specific Validation

When calling integrations using `app::` namespace syntax:

### 1. Verify Integration Exists

Use `list_integrations` to confirm:

```json
{
  "configured_only": true,
  "tenant": "default"
}
```

### 2. Verify Action Exists

Use `list_integration_tools`:

```json
{
  "integration_id": "virustotal"
}
```

### 3. Provide Required Parameters

Check action documentation for required params:

```cy
# VirusTotal ip_reputation requires "ip" parameter
source_ip = input.source_ip ?? "0.0.0.0"
vt_data = app::virustotal::ip_reputation(ip=source_ip)
```

## Pre-Creation Checklist

Before creating a task, verify:

- [ ] Script validates via `validate_cy_script`
- [ ] Script has `return {...}` statement
- [ ] data_samples provided (at least one)
- [ ] data_samples contain ONLY fields your script uses (minimal approach)
- [ ] For OCSF alert tasks: samples validated with `validate_alert`
- [ ] cy_name follows pattern (or let it auto-generate)
- [ ] function is one of valid types
- [ ] scope is one of valid scopes
- [ ] All integration actions verified
- [ ] Tested script with `run_script` using minimal samples

## Debugging Failed Validations

### Step 1: Read the Error Message

Error messages indicate:
- Which field failed validation
- What the expected format is
- Example of correct format

### Step 2: Validate Incrementally

```json
// Start minimal
{
  "name": "Test Task",
  "script": "return {}",
  "tenant": "default"
}

// Add fields one at a time
// Test after each addition
```

### Step 3: Use Validation Tools

```json
// Validate script syntax
{"tool": "validate_cy_script", "params": {"script": "..."}}

// Validate task structure
{"tool": "create_task", "params": {"name": "...", ...}}
```

### Step 4: Check Documentation

Reference:
- Cy language skill for syntax issues
- This validation guide for schema issues
- Integration docs for app:: namespace usage

## Version-Specific Notes

Tasks use semantic versioning (1.0.0 format) but currently:
- Version is informational only
- Multiple versions can exist (not enforced as unique)
- Future: Version management may become stricter
