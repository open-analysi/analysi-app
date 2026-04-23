# OCSF Field Reference for Runbooks

How runbook field references map to OCSF Detection Finding (Class 2004, v1.8.0) paths.

## Why This Document Exists

Runbooks reference alert data from OCSF Detection Finding events. Some fields are accessed via direct OCSF paths (e.g., `severity`, `finding_info.title`), while others use helper functions that traverse nested arrays (e.g., `get_src_ip(alert)` walks `evidences[]` to find `src_endpoint.ip`). This document is the authoritative reference for all field access patterns used in runbooks.

## How Field References Work

Runbooks use three namespaces for data flow:

| Namespace | Source | Example |
|-----------|--------|---------|
| OCSF path / helper | Fields extracted from the OCSF Detection Finding | `get_src_ip(alert)`, `finding_info.title` |
| `outputs.*` | Results from previous investigation steps | `outputs.ip_reputation` |
| `params.*` | Parameters passed via WikiLinks embeds | `params.time_window` |

This document covers OCSF field access — direct paths and helper functions.

---

## Direct OCSF Paths

These fields map 1:1 to a single OCSF path. No traversal logic needed.

| Runbook usage | OCSF path | Type | Description |
|---------------|-----------|------|-------------|
| `finding_info.title` | `finding_info.title` | String | Detection rule title |
| `severity` | `severity` | String | Severity label (`"Low"`, `"Medium"`, `"High"`, `"Critical"`) |
| `time` | `time` | Timestamp | Event occurrence time (epoch ms or RFC 3339) |
| `disposition` | `disposition` | String | Action taken (`"Allowed"`, `"Blocked"`) |
| `finding_info.desc` | `finding_info.desc` | String | Why the detection rule fired. Fall back to `message` if absent. |

---

## Helper Functions

These fields require traversal of OCSF arrays (`evidences[]`, `observables[]`, `vulnerabilities[]`) or fallback chains across multiple paths. Each helper walks the relevant array and returns the first non-null match.

All helpers accept a single argument: the full OCSF Detection Finding dict.

### get_src_ip(alert)

Extracts the attacker/source IP address.

| | |
|---|---|
| **Used for** | Source/attacker IP |
| **OCSF path** | `evidences[].src_endpoint.ip` |
| **Returns** | `String \| null` — first non-null source IP found across all evidence artifacts |
| **Logic** | Iterates `evidences[]`, for each entry checks `src_endpoint.ip`. Returns the first match. |

**OCSF context:** The `evidences` array contains one or more Evidence Artifacts. Each artifact can include a `src_endpoint` (Network Endpoint object) with an `ip` field. Multiple evidence entries may exist when a detection correlates several events.

### get_dst_ip(alert)

Extracts the target/destination IP address.

| | |
|---|---|
| **Used for** | Target/destination IP |
| **OCSF path** | `evidences[].dst_endpoint.ip` |
| **Returns** | `String \| null` |
| **Logic** | Same traversal as `get_src_ip`, but reads `dst_endpoint.ip`. |

### get_url(alert)

Extracts the full request URL.

| | |
|---|---|
| **Used for** | Full request URL |
| **OCSF path** | `evidences[].url.url_string` |
| **Returns** | `String \| null` |
| **Logic** | Iterates `evidences[]`, for each entry checks `url.url_string`. Returns the first match. |

### get_url_path(alert)

Extracts just the path component of the URL.

| | |
|---|---|
| **Used for** | URL path component |
| **OCSF path** | `evidences[].url.path` |
| **Returns** | `String \| null` |
| **Logic** | Same traversal as `get_url`, but reads `url.path` instead of `url.url_string`. |

### get_primary_user(alert)

Extracts the user identity associated with the alert.

| | |
|---|---|
| **Used for** | User identity |
| **OCSF path** | `actor.user.name` → `actor.user.uid` |
| **Returns** | `String \| null` |
| **Logic** | Checks `actor.user.name` first. If absent, falls back to `actor.user.uid`. |

**OCSF context:** The `actor` object represents the entity that triggered the detection. Its `user` sub-object contains identity fields. The `name` field is the human-readable username; `uid` is the system identifier (e.g., SID, UUID).

### get_primary_device(alert)

Extracts the device/host associated with the alert.

| | |
|---|---|
| **Used for** | Device/host identifier |
| **OCSF path** | `device.hostname` → `device.name` → `device.ip` |
| **Returns** | `String \| null` |
| **Logic** | Tries `device.hostname` first, then `device.name`, then `device.ip`. Returns the first non-null value. |

**OCSF context:** The top-level `device` object describes the affected host. The fallback chain provides the most specific identifier available — hostname is preferred over a raw IP.

### get_primary_entity_type(alert)

Determines whether the primary risk entity is a user or a device.

| | |
|---|---|
| **Used for** | Primary entity classification |
| **OCSF path** | Inferred from `actor.user` and `device` |
| **Returns** | `"user" \| "device" \| null` |
| **Logic** | If `actor.user` exists → `"user"`. Else if `device` exists → `"device"`. Else `null`. |

### get_primary_entity_value(alert)

Returns the primary risk entity value regardless of type.

| | |
|---|---|
| **Used for** | Primary entity value (user or device) |
| **OCSF path** | Combines `get_primary_user` and `get_primary_device` |
| **Returns** | `String \| null` |
| **Logic** | Calls `get_primary_user(alert)`. If null, calls `get_primary_device(alert)`. |

### get_cve_ids(alert)

Extracts all CVE identifiers from the alert.

| | |
|---|---|
| **Used for** | CVE identifiers |
| **OCSF path** | `vulnerabilities[].cve.uid` |
| **Returns** | `List[String]` — empty list if none found |
| **Logic** | Iterates `vulnerabilities[]`, for each entry checks `cve.uid`. Collects all non-null values. |

**OCSF context:** The `vulnerabilities` array contains Vulnerability Details objects. Each can include a `cve` object with a `uid` field holding the CVE identifier (e.g., `"CVE-2024-3400"`).

### get_primary_observable_type(alert)

Returns the type of the first observable as a short string.

| | |
|---|---|
| **Used for** | Primary observable type classification |
| **OCSF path** | `observables[0].type_id` |
| **Returns** | `String \| null` — short name like `"ip"`, `"domain"`, `"url"`, `"filehash"` |
| **Logic** | Reads first observable's `type_id` and maps it via the type_id-to-short-name table (see appendix). |

### get_primary_observable_value(alert)

Returns the value of the first observable.

| | |
|---|---|
| **Used for** | Primary observable value |
| **OCSF path** | `observables[0].value` |
| **Returns** | `String \| null` |

### get_primary_observable(alert, type=None)

Returns the first observable matching the given type, or the first observable overall.

| | |
|---|---|
| **Used for** | First observable matching a type |
| **OCSF path** | `observables[]` filtered by `type_id` |
| **Returns** | `Dict \| null` — `{"type": str, "value": str, ...}` |
| **Logic** | If `type` is given (e.g., `"ip"`), iterates `observables[]` and matches against `type_id` or `type` string. Returns first match. If no type filter, returns `observables[0]`. |

### get_observables(alert, type=None)

Returns all observables, optionally filtered by type.

| | |
|---|---|
| **Used for** | All observables (optionally filtered) |
| **OCSF path** | `observables[]` |
| **Returns** | `List[Dict]` — each with `{"type": str, "value": str, ...}` |
| **Logic** | Same matching as `get_primary_observable`, but returns all matches instead of just the first. |

### get_label(alert, key)

Extracts a label value from metadata by key prefix.

| | |
|---|---|
| **Used for** | Metadata label extraction by key |
| **OCSF path** | `metadata.labels[]` |
| **Returns** | `String \| null` |
| **Logic** | Iterates `metadata.labels[]` (array of strings). Finds first entry starting with `"{key}:"` and returns everything after the colon. E.g., `get_label(alert, "source_category")` on `["source_category:WAF"]` returns `"WAF"`. |

---

### get_http_method(alert)

Extracts the HTTP request method.

| | |
|---|---|
| **Used for** | HTTP request method |
| **OCSF path** | `evidences[].http_request.http_method` |
| **Returns** | `String \| null` — e.g., `"GET"`, `"POST"` |
| **Logic** | `_first_evidence_value(alert, "http_request", "http_method")` |

### get_user_agent(alert)

Extracts the HTTP User-Agent header.

| | |
|---|---|
| **Used for** | HTTP User-Agent header |
| **OCSF path** | `evidences[].http_request.user_agent` |
| **Returns** | `String \| null` |
| **Logic** | `_first_evidence_value(alert, "http_request", "user_agent")` |

### get_dst_domain(alert)

Extracts the destination domain.

| | |
|---|---|
| **Used for** | Destination domain |
| **OCSF path** | `evidences[].dst_endpoint.domain` |
| **Returns** | `String \| null` |
| **Logic** | `_first_evidence_value(alert, "dst_endpoint", "domain")` |

### get_http_response_code(alert)

Extracts the HTTP response status code.

| | |
|---|---|
| **Used for** | HTTP response status code (attack success determination) |
| **OCSF path** | `evidences[].http_response.code` |
| **Returns** | `Integer \| null` |
| **Logic** | `_first_evidence_value(alert, "http_response", "code")` |

---

## Vendor-Specific Fields (Not in Standard OCSF)

These fields do **not** have standard OCSF paths. The data lives in `unmapped`, `raw_data`, or vendor-specific `observables` entries. They are only available when the original alert source provides them. In runbooks, reference them via `unmapped.*`.

| Runbook usage | Source location | Used in |
|---------------|-----------------|---------|
| `unmapped.request_payload` | `raw_data` or `unmapped` | Payload analysis steps |
| `unmapped.cookie` | `raw_data` or `unmapped` | Session analysis |
| `unmapped.country` | `unmapped` or `observables[type_id=14]` | Identity/geo runbooks |
| `unmapped.normal_country` | `unmapped` | Geo-anomaly detection |
| `unmapped.query_volume` | `unmapped` | DNS exfiltration runbooks |
| `unmapped.subdomain_patterns` | `unmapped` | DNS exfiltration runbooks |

---

## Observable type_id Short Name Mapping

Helper functions that work with observables convert OCSF numeric `type_id` values to short string names for readability:

| type_id | Short name | OCSF type |
|---------|------------|-----------|
| 1 | `domain` | Hostname |
| 2 | `ip` | IP Address |
| 6 | `url` | URL String |
| 7 | `filename` | File Name |
| 8 | `filehash` | Hash |
| 9 | `process` | Process Name |
| 16 | `user_agent` | HTTP User-Agent |
