# Data Samples Guide for Tasks

## Overview

This guide provides comprehensive instructions for creating `data_samples` - the test inputs required for every Task. The key principle: **include critical fields ALWAYS, then add ONLY the fields your script actually uses**.

## ⚠️ CRITICAL FIELDS REQUIREMENT

**ALWAYS include these fields in EVERY data_sample, regardless of whether your script explicitly accesses them:**

### 1. `finding_info` (REQUIRED)
The detection finding metadata — title, unique ID, and detection analytic (rule name).

**IMPORTANT: `title` vs `analytic.name` are different:**
- `finding_info.title` — human-readable alert summary, may vary per alert instance (e.g., "Suspicious login from 185.220.101.45")
- `finding_info.analytic.name` — stable detection rule name used for alert routing (e.g., "SOC165 - Possible SQL Injection Payload Detected")

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

### 2. `observables` (REQUIRED if applicable)
OCSF observables (IOC pointers) are essential for:
- IP reputation checks
- Domain analysis
- URL scanning
- File hash lookups
- Many enrichment tasks depend on observables being present

**Example:**
```json
{
  "finding_info": {
    "title": "Malicious IP Communication Detected",
    "uid": "alert-002",
    "analytic": {"name": "Malicious IP Communication", "type": "Rule", "type_id": 1}
  },
  "observables": [
    {"type_id": 2, "type": "IP Address", "value": "185.220.101.45"},
    {"type_id": 1, "type": "Hostname", "value": "evil.com"}
  ]
}
```

### Why These Fields Are Critical

**Without `finding_info`:**
- MCP validation will fail if your script uses fallback patterns
- LLM context generation becomes less effective
- Tasks cannot reliably identify alert types or detection rules

**Without `observables`:**
- Enrichment tasks (IP reputation, domain analysis) will fail
- Workflow execution produces empty/incomplete results
- Integration tools have no data to query

### Template for Every Task

Start with this baseline structure, then add script-specific fields:

```json
{
  "finding_info": {
    "title": "Alert Title (human-readable summary)",
    "uid": "sample-001",
    "analytic": {"name": "Detection Rule Name", "type": "Rule", "type_id": 1}
  },
  "observables": [
    {"type_id": 2, "type": "IP Address", "value": "185.220.101.45"}
  ]
}
```

**If your alert has NO observables** (e.g., purely user-behavior alerts), use an empty array:
```json
{
  "finding_info": {
    "title": "User Privilege Escalation Detected",
    "uid": "alert-003",
    "analytic": {"name": "User Privilege Escalation", "type": "Rule", "type_id": 1}
  },
  "observables": []
}
```

### ⚠️ NEVER Access raw_data Fields

**Your script should NEVER access fields inside `raw_data`.**

The `raw_data` field is vendor-specific and unpredictable. Use standardized OCSF fields instead:

```cy
# ❌ WRONG - Script should never do this
domain = input.raw_data.domain

# ✅ CORRECT - Use OCSF fields with helper functions
domain = get_primary_observable_value(input) ?? "unknown.com"
ip = get_src_ip(input) ?? "0.0.0.0"
username = get_primary_entity_value(input) ?? "unknown_user"
```

**For data_samples:** Include `raw_data` as opaque vendor data, but don't expect scripts to access its internal fields.

```json
{
  "finding_info": {"title": "Suspicious Connection Detected", "uid": "sample-001", "analytic": {"name": "Suspicious Outbound Connection", "type": "Rule", "type_id": 1}},
  "observables": [{"type": "Domain Name", "value": "evil.com"}],
  "raw_data": {
    "vendor_field_1": "...",
    "vendor_field_2": "..."
  }
}
```

**See:** task-builder SKILL.md Pattern #3 for complete guidance on avoiding raw_data access.

## Core Philosophy: Start Minimal (For Non-Critical Fields)

**Don't include fields just because they exist in the OCSF schema.** Only add fields that your script explicitly accesses. This approach:
- Reduces maintenance burden
- Makes tests clearer
- Avoids false dependencies
- Simplifies debugging

## Using validate_alert MCP Tool

Before finalizing your data_samples, validate them using the MCP tool:

```python
# Validate a sample
result = validate_alert(alert_data=sample)

# Check results
if result["valid"]:
    print("✅ Sample is valid OCSF")
else:
    print(f"❌ Validation errors: {result['errors']}")
    print(f"⚠️ Warnings: {result['warnings']}")
```

**Important**: The validator checks OCSF compliance, but your task may work with a subset of fields.

## Minimal Sample Patterns

### Pattern 1: IP-Based Tasks

For tasks that need an IP address (ALWAYS include finding_info with analytic and observables):

```json
{
  "data_samples": [
    {
      "finding_info": {"title": "Suspicious Outbound Connection to Known Tor Node", "uid": "sample-001", "analytic": {"name": "Suspicious Outbound Connection", "type": "Rule", "type_id": 1}},
      "observables": [
        {"type": "IP Address", "type_id": 2, "value": "185.220.101.45", "name": "src_ip"}
      ]
    },
    {
      "finding_info": {"title": "DNS Query to External Resolver 8.8.8.8", "uid": "sample-002", "analytic": {"name": "External DNS Resolution", "type": "Rule", "type_id": 1}},
      "observables": [
        {"type": "IP Address", "type_id": 2, "value": "8.8.8.8", "name": "dst_ip"}
      ]
    }
  ]
}
```

**Alternative if script uses evidence endpoints:**
```json
{
  "evidences": [{"src_endpoint": {"ip": "185.220.101.45"}}]
}
```

### Pattern 2: User-Based Tasks

For tasks focused on user behavior (finding_info required, observables typically empty):

```json
{
  "data_samples": [
    {
      "finding_info": {"title": "User jsmith Escalated Privileges", "uid": "sample-001", "analytic": {"name": "User Privilege Escalation", "type": "Rule", "type_id": 1}},
      "actor": {"user": {"name": "jsmith"}},
      "observables": []
    },
    {
      "finding_info": {"title": "Admin Account Activity Outside Business Hours", "uid": "sample-002", "analytic": {"name": "Suspicious Admin Activity", "type": "Rule", "type_id": 1}},
      "actor": {"user": {"name": "admin"}},
      "observables": []
    }
  ]
}
```

### Pattern 3: Tasks That Use Enrichments

If your script reads or writes to enrichments:

```json
{
  "data_samples": [
    {
      "observables": [{"value": "185.220.101.45", "type": "IP Address"}],
      "enrichments": {}  // Empty but MUST be present
    },
    {
      "observables": [{"value": "8.8.8.8", "type": "IP Address"}],
      "enrichments": {
        "previous_analysis": {
          "risk_level": "low"
        }
      }
    }
  ]
}
```

### Pattern 4: Splunk Event Retrieval

For tasks that need event identifiers:

```json
{
  "data_samples": [
    {
      "source_event_id": "1234567890",
      "triggering_event_time": "2025-10-30T10:15:00Z"
    }
  ]
}
```

### Pattern 5: Multi-Field Dependencies

When your script needs multiple fields:

```json
{
  "data_samples": [
    {
      "finding_info": {"title": "Suspicious Login from 185.220.101.45", "uid": "sample-001", "analytic": {"name": "Suspicious Login Detection", "type": "Rule", "type_id": 1}},
      "actor": {"user": {"name": "jsmith"}},
      "evidences": [{"src_endpoint": {"ip": "185.220.101.45"}}],
      "time": "2025-10-30T10:15:00Z"
    }
  ]
}
```

## Building Realistic Test Data

### Good IP Addresses to Use

**Known Good IPs:**
- `8.8.8.8`, `8.8.4.4` - Google DNS
- `1.1.1.1`, `1.0.0.1` - Cloudflare DNS
- `208.67.222.222` - OpenDNS

**Known Malicious IPs (from public threat feeds):**
- `185.220.101.45` - Known Tor exit node
- `45.154.255.147` - Common in threat intel
- `194.180.224.124` - Often flagged malicious

**RFC 1918 Private IPs:**
- `192.168.1.100` - Private network
- `10.0.0.50` - Internal range
- `172.16.20.8` - Private subnet

### Good Usernames to Use

**Standard Users:**
- `jsmith`, `jdoe` - Typical employee
- `admin`, `administrator` - Privileged accounts
- `service_account`, `svc_backup` - Service accounts
- `guest`, `temp_user` - Low privilege

### Good Domains to Use

**Legitimate:**
- `google.com`, `microsoft.com`
- `github.com`, `stackoverflow.com`

**Suspicious (for testing):**
- `evil.com`, `malicious.org` (reserved for examples)
- `phishing-site.tk`
- Use `.tk`, `.ml` TLDs for suspicious examples

## Testing Your data_samples

### Step 1: Identify Required Fields

Look at your script and list ONLY fields it accesses:

```cy
# Script accesses these fields:
ip = get_primary_observable_value(input) ?? get_src_ip(input)
enrichments = input.enrichments ?? {}

# So data_sample needs ONLY:
# - observables (for primary observable) OR evidences (for src endpoint IP)
# - enrichments (if writing to it)
```

### Step 2: Create Minimal Sample

```json
{
  "observables": [{"value": "185.220.101.45", "type": "IP Address"}],
  "enrichments": {}
}
```

### Step 3: Validate with MCP Tool

```python
# In your testing
sample = {
    "observables": [{"value": "185.220.101.45", "type": "IP Address"}],
    "enrichments": {}
}

result = validate_alert(alert_data=sample)
assert result["valid"], f"Sample validation failed: {result['errors']}"
```

### Step 4: Test Execution

```python
# Test with your script
result = run_script(
    script=your_task_script,
    input_data=sample
)
assert result["status"] == "completed"
```

### Step 5: Add Edge Cases

Create at least 2-3 samples covering:

1. **Normal case** - Expected input
2. **Edge case** - Missing optional fields, empty values
3. **Error case** - How task handles bad data

## Common Mistakes to Avoid

### ❌ Don't Copy Entire Alerts

**Bad:**
```json
{
  "alert_id": "AL-001",
  "title": "Suspicious Activity",
  "severity": "high",
  "source_vendor": "Splunk",
  "source_product": "Enterprise Security",
  "source_category": "SIEM",
  "triggering_event_time": "2025-10-30T10:15:00Z",
  "observables": [{"value": "185.220.101.45", "type": "IP Address"}],
  "actor": {...},
  "device": {...},
  "evidences": [...],
  "enrichments": {}
}
```

**Good:**
```json
{
  "observables": [{"value": "185.220.101.45", "type": "IP Address"}],
  "enrichments": {}
}
```

### ❌ Don't Add Fields "Just In Case"

Only add fields your script actually uses. If the script doesn't access `severity`, don't include it.

### ❌ Don't Use Placeholder Data

**Bad:**
```json
{
  "observables": [{"value": "1.2.3.4", "type": "IP Address"}],  // Not a real IP
  "username": "user123"  // Generic placeholder
}
```

**Good:**
```json
{
  "observables": [{"value": "185.220.101.45", "type": "IP Address"}],  // Real Tor exit node
  "username": "jsmith"  // Realistic username
}
```

## Validation Checklist

Before finalizing your data_samples:

- [ ] **CRITICAL: `finding_info` included in EVERY sample (with title AND analytic.name)**
- [ ] **CRITICAL: `observables` field included (populated array or empty `[]`)**
- [ ] Each sample contains script-accessed fields
- [ ] Validated with `validate_alert` MCP tool
- [ ] Tested with `run_script`
- [ ] At least 2 samples (normal + edge case)
- [ ] Using realistic data (real IPs, domains, usernames)
- [ ] All samples pass execution without errors
- [ ] Edge cases properly handled

## Examples by Task Type

### IP Reputation Task

```json
{
  "data_samples": [
    {
      "observables": [{"value": "185.220.101.45", "type": "IP Address"}],
      "enrichments": {}
    },
    {
      "observables": [{"value": "8.8.8.8", "type": "IP Address"}],
      "enrichments": {}
    }
  ]
}
```

### User Privilege Check Task

```json
{
  "data_samples": [
    {
      "actor": {"user": {"name": "admin"}},
      "enrichments": {}
    },
    {
      "actor": {"user": {"name": "guest"}},
      "enrichments": {}
    }
  ]
}
```

### Splunk Event Retrieval Task

```json
{
  "data_samples": [
    {
      "source_event_id": "splunk-notable-12345",
      "triggering_event_time": "2025-10-30T10:15:00Z",
      "enrichments": {}
    },
    {
      "source_event_id": "splunk-notable-67890",
      "triggering_event_time": "2025-10-30T11:30:00Z",
      "enrichments": {}
    }
  ]
}
```

### Multi-Source Correlation Task

```json
{
  "data_samples": [
    {
      "observables": [{"value": "evil.com", "type": "Domain Name"}],
      "evidences": [{
        "src_endpoint": {"ip": "192.168.1.100"},
        "dst_endpoint": {"ip": "185.220.101.45"}
      }],
      "enrichments": {}
    }
  ]
}
```

## Quick Reference: Field Access Patterns

| If your script uses... | Include in data_sample... |
|------------------------|---------------------------|
| `get_primary_observable_value(input)` | `"observables": [{"value": "1.2.3.4", "type": "IP Address"}]` |
| `get_src_ip(input)` | `"evidences": [{"src_endpoint": {"ip": "IP"}}]` |
| `get_primary_entity_value(input)` | `"actor": {"user": {"name": "username"}}` |
| `input.enrichments` | `"enrichments": {}` (even if empty) |
| `input.time` | `"time": "ISO-8601"` |
| `input.actor.user` | `"actor": {"user": {"name": "name"}}` |
| Nothing (LLM-only task) | `{}` (empty object is valid) |

## Summary

1. **ALWAYS start with critical fields: `finding_info` (with title + analytic.name) and `observables` (or `[]`)**
2. **Add only additional fields your script explicitly accesses**
3. **Validate with `validate_alert`**
4. **Test with `run_script`**
5. **Use realistic data**
6. **Cover normal and edge cases**

Remember: Critical fields first, then minimal. This ensures tasks work reliably while keeping maintenance burden low.
