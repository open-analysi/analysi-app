# OCSF Alert Enrichment Pattern

## Overview

**Use Case:** Task that enriches an alert object without overwriting existing enrichments from previous tasks.

**Critical for:** Alert-centric security workflows where multiple tasks enrich the same alert in sequence or parallel branches.

## The `enrich_alert()` Function

Use the built-in `enrich_alert()` function for all enrichment tasks. It automatically:
- Uses the task's `cy_name` as the enrichment key (providing clear attribution)
- Preserves existing enrichments from previous tasks
- Creates the `enrichments` dict if it doesn't exist
- Handles edge cases (null values, wrong types)

## Basic Template

```cy
# Input: Full OCSF alert object
# Output: Alert with enrichment added under alert["enrichments"][cy_name]

# Step 1: Extract data from alert using helpers
ioc = get_primary_observable_value(input) ?? ""

# Step 2: Call integration to get enrichment data
result = app::integration_name::action_name(ioc=ioc)

# Step 3: Build enrichment object
enrichment = {
    "ioc": ioc,
    "data": result,
    "score": result.score
}

# Step 4: Enrich and return (uses task's cy_name automatically)
return enrich_alert(input, enrichment)
```

## Real-World Example: IP Reputation Enrichment

**Task cy_name:** `vt_ip_reputation`

```cy
# Extract IP using helpers (with fallback chain)
ip = get_primary_observable_value(input) ?? get_src_ip(input) ?? ""

# Query VirusTotal
vt_result = app::virustotal::ip_reputation(ip=ip)

# Build enrichment summary
enrichment = {
    "ip": ip,
    "malicious_score": vt_result.malicious,
    "reputation": vt_result.reputation,
    "country": vt_result.country
}

# Return enriched alert (stored under alert["enrichments"]["vt_ip_reputation"])
return enrich_alert(input, enrichment)
```

## Custom Key Name (Optional)

If you need a specific key instead of the task's `cy_name`, pass it as the third argument:

```cy
# Store under "threat_intel" instead of cy_name
return enrich_alert(input, enrichment, "threat_intel")
```

## DO and DON'T

```cy
# WRONG - Manual approach, error-prone
input["enrichments"] = input["enrichments"] ?? {}
input["enrichments"]["ip_reputation"] = vt_result
return input

# CORRECT - Use enrich_alert()
return enrich_alert(input, vt_result)
```

```cy
# WRONG - Overwrites all previous enrichments
input["enrichments"] = {"ip_reputation": vt_result}
return input

# CORRECT - Preserves existing enrichments automatically
return enrich_alert(input, vt_result)
```

## How It Works in Workflows

### Sequential Flow

```
Task A (cy_name: "ip_reputation"):     alert["enrichments"]["ip_reputation"] = {...}
Task B (cy_name: "user_context"):      alert["enrichments"]["user_context"] = {...}
Task C (cy_name: "risk_score"):        alert["enrichments"]["risk_score"] = {...}
```

Each task's enrichment is stored under its own `cy_name`, preventing collisions.

### Parallel Branches with Merge

```
Branch A (cy_name: "threat_intel"):    alert["enrichments"]["threat_intel"] = {...}
Branch B (cy_name: "edr_lookup"):      alert["enrichments"]["edr_lookup"] = {...}
Merge: Combines both enrichments automatically
```

## Function Signature

```cy
enrich_alert(alert, enrichment_data, key_name?)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `alert` | dict | The alert to enrich (typically `input`) |
| `enrichment_data` | any | Data to store in enrichments |
| `key_name` | string (optional) | Custom key. Defaults to task's `cy_name` |

**Returns:** The modified alert dict with enrichment added.

## When to Use This Pattern

Use `enrich_alert()` when:
- Your task is part of a workflow with multiple enrichment tasks
- The task needs to preserve context from previous tasks
- Alerts flow through sequential or parallel processing
- You're building composable, reusable enrichment tasks

## Related Patterns

- See **SKILL.md** for other common task patterns
- See **task_run_patterns.md** for task composition
- See **integration_usage_guide.md** for integration call patterns
