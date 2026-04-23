# OCSF Alert Schema Overview

Alerts use the OCSF (Open Cybersecurity Schema Framework) Detection Finding class 2004, v1.8.0. This is the industry standard used by AWS, Splunk, CrowdStrike, and 15+ vendors.

**Key principle:** Cy scripts access alert data through **helper functions**, not by navigating OCSF paths directly. If the schema changes, only the helpers change — not your tasks.

## Alert Structure (Top-Level)

| Section | Description | Access via |
|---------|-------------|------------|
| `finding_info` | Title, UID, detection analytic (rule name), types | `input.finding_info.title`, `input.finding_info.analytic.name`, `input.finding_info.uid` |
| `severity_id` | 1-5 integer (Info, Low, Medium, High, Critical) | `input.severity_id` |
| `metadata` | Product info, labels, version | `get_label(input, "source_category")` |
| `actor` | User who triggered the event | `get_primary_user(input)` |
| `device` | Host/device involved | `get_primary_device(input)` |
| `observables[]` | Lightweight IOC pointers (type + value) | `get_observables(input)` |
| `evidences[]` | Rich evidence artifacts (endpoints, process, file, URL) | `get_src_ip(input)`, `get_dst_ip(input)`, etc. |
| `vulnerabilities[]` | CVE information | `get_cve_ids(input)` |
| `enrichments` | Task enrichment chain (same as before) | `input.enrichments.task_name.ai_analysis` |
| `raw_data` | Original vendor-specific alert (NEVER access fields from this) | Pass to LLM for context only |

## Helper Functions Reference

These are built-in Cy functions. Pass `input` (the alert) as the first argument.

### Entity Helpers

```cy
# Primary entity (user or device — returns whichever is present)
entity_type = get_primary_entity_type(input)   # "user" or "device" or null
entity_value = get_primary_entity_value(input)  # username, hostname, or IP

# Specific entity access
username = get_primary_user(input)              # actor.user.name or .uid
device = get_primary_device(input)              # device.hostname or .name or .ip
```

### Observable / IOC Helpers

```cy
# Primary observable (first in array)
ioc_type = get_primary_observable_type(input)    # "ip", "domain", "url", "filehash", etc.
ioc_value = get_primary_observable_value(input)  # The observable value string

# Primary observable as dict (with optional type filter)
obs = get_primary_observable(input)              # {"type": "ip", "value": "203.0.113.50", ...}
obs = get_primary_observable(input, type="ip")   # First observable matching type "ip"

# All observables (with optional type filter)
all_obs = get_observables(input)                 # List of all observables
ip_obs = get_observables(input, type="ip")       # Only IP observables
url_obs = get_observables(input, type="url")     # Only URL observables
```

**Observable types:** `ip`, `domain`, `url`, `filehash`, `filename`, `process`, `user_agent`

Each observable dict contains at minimum `{"type": str, "value": str}`. May also have `reputation`, `type_id`, and other OCSF fields.

### Network Helpers

```cy
src_ip = get_src_ip(input)     # Source IP from evidences[].src_endpoint.ip
dst_ip = get_dst_ip(input)     # Destination IP from evidences[].dst_endpoint.ip
```

### Web / URL Helpers

```cy
url = get_url(input)           # Full URL from evidences[].url.url_string
path = get_url_path(input)     # URL path from evidences[].url.path
```

### CVE Helpers

```cy
cve_ids = get_cve_ids(input)   # List of CVE ID strings, e.g. ["CVE-2021-44228"]
```

### Label / Metadata Helpers

```cy
category = get_label(input, "source_category")  # "EDR", "Firewall", "Identity", etc.
```

## Severity

OCSF uses integer `severity_id` (1-5):

| severity_id | Meaning |
|-------------|---------|
| 1 | Info |
| 2 | Low |
| 3 | Medium |
| 4 | High |
| 5 | Critical |

```cy
sev = input.severity_id ?? 3
is_critical = sev >= 5
```

## Title vs Rule Name

**These are different fields — do not confuse them.**

| Field | Purpose | Example | Stable? |
|-------|---------|---------|---------|
| `input.title` / `input.finding_info.title` | Human-readable alert summary | "Suspicious login from 185.220.101.45 by jsmith" | No — varies per alert |
| `input.rule_name` / `input.finding_info.analytic.name` | Detection rule that fired | "SOC165 - Possible SQL Injection Payload Detected" | Yes — same for all alerts from this rule |

**Alert routing uses `rule_name`** to match alerts to workflows. Never route on `title` — it contains per-instance data (IPs, usernames) that changes between alerts from the same rule.

```cy
# For display / LLM context — use title
alert_context = input.title ?? input.finding_info.title ?? "unknown alert"

# For routing / identification — use rule_name
rule = input.rule_name ?? input.finding_info.analytic.name ?? ""
```

## Enrichments (Workflow Chain)

The enrichment pattern is unchanged from before. Tasks add enrichments via `enrich_alert()`:

```cy
# Read enrichments from prior tasks
context = input.enrichments.alert_context_generation.ai_analysis ?? "unknown alert"

# Add your enrichment
enrichment = {"ai_analysis": analysis, "source": "VirusTotal"}
return enrich_alert(input, enrichment)
```

## Null Safety

All helpers return `None`/`null` when the data is missing. Always use `??` defaults:

```cy
ip = get_src_ip(input) ?? "0.0.0.0"
user = get_primary_user(input) ?? "unknown_user"
ioc = get_primary_observable_value(input) ?? ""
cves = get_cve_ids(input) ?? []
```

## See Also

- `ocsf_alert_structure.md` — Detailed OCSF object structure (evidences, observables, actor, device)
- `ocsf_enrichment_pattern.md` — How to add enrichments to alerts
- `critical_fields_guide.md` — Mandatory fields for data_samples
