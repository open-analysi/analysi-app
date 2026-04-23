# NIST NVD Actions Reference

## `cve_lookup` — Look Up CVE Information

<!-- EVIDENCE: MCP live query — list_integration_tools(nistnvd) -->
<!-- EVIDENCE: MCP live test — run_integration_tool(cve_lookup, {cve: "CVE-2021-44228"}) — success, CISA KEV present -->
<!-- EVIDENCE: MCP live test — run_integration_tool(cve_lookup, {cve: "CVE-2024-3400"}) — success, CISA KEV present, due_date null -->
<!-- EVIDENCE: MCP live test — run_integration_tool(cve_lookup, {cve: "CVE-2023-44487"}) — success -->
<!-- EVIDENCE: MCP live test — run_integration_tool(cve_lookup, {cve: "CVE-2014-0160"}) — success, CVSS v2 fallback -->
<!-- EVIDENCE: MCP live test — run_integration_tool(cve_lookup, {cve: "CVE-9999-99999"}) — not found -->
<!-- EVIDENCE: MCP live test — run_integration_tool(cve_lookup, {cve: "invalid-cve"}) — validation error -->
<!-- EVIDENCE: Source code — src/analysi/integrations/framework/integrations/nistnvd/actions.py -->
<!-- EVIDENCE: Web search — NVD API rate limits confirmed at https://nvd.nist.gov/developers/start-here -->

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `cve` | string | Yes | CVE ID in format `CVE-YYYY-NNNNN` (e.g., `CVE-2021-44228`). Case-insensitive; auto-uppercased and trimmed. |

**Validation rules** (enforced before API call):
- Must be a non-empty string
- Must start with `CVE-`
- Year part must be exactly 4 digits
- ID part must be numeric

### Cy Calling Convention

```cy
result = app::nistnvd::cve_lookup(cve="CVE-2021-44228")
```

The integration instance ID is `nistnvd-main`, but Cy scripts always use the type `nistnvd`.

### Success Response Schema

When the CVE is found, the response contains these top-level fields:

```
{
  "cve_id": "CVE-2021-44228",
  "description": "Apache Log4j2 2.0-beta9 through 2.15.0 ... allows remote code execution...",
  "published_date": "2021-12-10T10:15:09.143",
  "last_modified_date": "2023-11-07T03:39:45.697",
  "cvss_metrics": {
    "base_score": 10.0,
    "base_severity": "CRITICAL",
    "attack_vector": "NETWORK",
    "attack_complexity": "LOW",
    "privileges_required": "NONE",
    "user_interaction": "NONE",
    "scope": "CHANGED",
    "confidentiality_impact": "HIGH",
    "integrity_impact": "HIGH",
    "availability_impact": "HIGH",
    "exploitability_score": 3.89,
    "impact_score": 6.0
  },
  "references": [
    "https://logging.apache.org/log4j/2.x/security.html",
    "https://www.oracle.com/security-alerts/cpujan2022.html"
  ],
  "cisa_kev": {
    "vulnerability_name": "Apache Log4j2 Remote Code Execution Vulnerability",
    "required_action": "For all affected software assets...",
    "due_date": "2021-12-24",
    "date_added": "2021-12-10"
  },
  "full_data": { ... }
}
```

### Field Reference

#### Top-Level Fields

| Field | Type | Always present | Description |
|-------|------|----------------|-------------|
| `cve_id` | string | Yes | Normalized CVE identifier |
| `description` | string | Yes | English-language CVE description (empty string if unavailable) |
| `published_date` | string | Yes | ISO 8601 datetime when CVE was first published |
| `last_modified_date` | string | Yes | ISO 8601 datetime of last NVD update |
| `cvss_metrics` | dict | Yes | CVSS scoring object (may be empty `{}` for very new/reserved CVEs) |
| `references` | list | Yes | Array of reference URL strings (vendor advisories, exploit details, patches) |
| `cisa_kev` | dict or null | Yes | CISA Known Exploited Vulnerabilities data; `null` if not in KEV catalog |
| `full_data` | dict | Yes | Raw NVD API v2.0 response; contains CPE configurations, weakness types (CWE), and multi-source CVSS scores |

**Important field name note**: The correct paths are `cvss_metrics.base_score` and `cvss_metrics.base_severity`. Do NOT use `cvss_v3_score` or `cvss_v3_severity` — those field names do not exist in the response.

#### cvss_metrics Fields (CVSS v3.1)

Present when the CVE has CVSS v3.1 scoring. The integration prefers v3.1 and falls back to v2 for older CVEs.

<!-- EVIDENCE: Source code — actions.py lines 258-291 -->

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `base_score` | number | 0.0–10.0 | CVSS base score |
| `base_severity` | string | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` | Qualitative severity rating |
| `attack_vector` | string | `NETWORK`, `ADJACENT_NETWORK`, `LOCAL`, `PHYSICAL` | How the vulnerability is exploited |
| `attack_complexity` | string | `LOW`, `HIGH` | Complexity of attack |
| `privileges_required` | string | `NONE`, `LOW`, `HIGH` | Privilege level needed |
| `user_interaction` | string | `NONE`, `REQUIRED` | Whether user interaction is needed |
| `scope` | string | `UNCHANGED`, `CHANGED` | Whether impact crosses security boundaries |
| `confidentiality_impact` | string | `NONE`, `LOW`, `HIGH` | Impact on data confidentiality |
| `integrity_impact` | string | `NONE`, `LOW`, `HIGH` | Impact on data integrity |
| `availability_impact` | string | `NONE`, `LOW`, `HIGH` | Impact on system availability |
| `exploitability_score` | number | 0.0–3.9 | Exploitability sub-score |
| `impact_score` | number | 0.0–6.0 | Impact sub-score |

#### CVSS v2 Fallback

For older CVEs without v3.1 scores (e.g., CVE-2014-0160 Heartbleed), the integration falls back to CVSS v2. Both versions populate the same `cvss_metrics` object, but v2 has fewer fields:

| Field | Type | Description |
|-------|------|-------------|
| `base_score` | number | CVSS v2 base score (0.0–10.0) |
| `base_severity` | string | `LOW`, `MEDIUM`, `HIGH` — no `CRITICAL` in v2, so a v2 `HIGH` (7.0–10.0) may be critical-equivalent |
| `attack_vector` | string | Normalized from v2 `accessVector`: `NETWORK`, `ADJACENT_NETWORK`, `LOCAL` |
| `attack_complexity` | string | Normalized from v2 `accessComplexity`: `LOW`, `MEDIUM`, `HIGH` (three levels, not two as in v3.1) |
| `exploitability_score` | number | Exploitability sub-score |
| `impact_score` | number | Impact sub-score |

**Fields absent in v2**: `privileges_required`, `user_interaction`, `scope`, `confidentiality_impact`, `integrity_impact`, `availability_impact`. For v2-only CVEs, rely more on description text and LLM analysis rather than metric-based decision trees.

**CVSS v4.0**: The NVD API v2.0 returns CVSS v4.0 data under `cvssMetricV40`, but this integration does not extract it. CVEs scored exclusively with CVSS v4.0 will have an empty `cvss_metrics` object. If you encounter empty metrics on a recent CVE, check `full_data.vulnerabilities[0].cve.metrics.cvssMetricV40` as a fallback — but parsing this in Cy is complex and best avoided.

Fields not present in the response (or when CVSS data is missing entirely) will be `null`. Always use `??` when accessing any CVSS field.

#### cisa_kev Fields

Present only when the CVE appears in CISA's Known Exploited Vulnerabilities catalog. If `cisa_kev` is not `null`, the vulnerability has confirmed active exploitation in the wild.

| Field | Type | Description |
|-------|------|-------------|
| `vulnerability_name` | string | CISA's name for the vulnerability |
| `required_action` | string | Mandated remediation action |
| `due_date` | string or null | Remediation deadline (YYYY-MM-DD); may be `null` for some entries |
| `date_added` | string or null | Date added to KEV catalog (YYYY-MM-DD) |

**Triage significance**: If `cisa_kev != null`, the CVE has confirmed active exploitation in the wild. This is a strong true-positive signal and drives patch urgency. Federal agencies have binding remediation deadlines; private sector should treat KEV membership as an escalation trigger. Use `required_action` in SOC response recommendations. Additions within the last 30 days suggest active campaigns.

#### full_data — When to Use

The `full_data` field contains the complete NVD API v2.0 response. Access it for:
- **CPE configurations**: `full_data.vulnerabilities[0].cve.configurations` — lists affected products/versions
- **CWE weakness types**: `full_data.vulnerabilities[0].cve.weaknesses` — root cause classification
- **Multiple CVSS sources**: `full_data.vulnerabilities[0].cve.metrics.cvssMetricV31` — may contain scores from both NVD and vendor

Avoid passing `full_data` to LLM prompts — it can be very large (10K+ tokens for CVEs with many affected product versions). Extract specific fields instead. For product-level analysis, pass `description` to LLM.

### Field Access Patterns in Cy

```cy
# Top-level fields
cve_id = result.cve_id ?? ""
description = result.description ?? ""
published = result.published_date ?? ""
modified = result.last_modified_date ?? ""

# CVSS metrics (nested — always use ?? for null safety)
base_score = result.cvss_metrics.base_score ?? 0
severity = result.cvss_metrics.base_severity ?? "unknown"
attack_vector = result.cvss_metrics.attack_vector ?? "unknown"
attack_complexity = result.cvss_metrics.attack_complexity ?? "unknown"
privs_required = result.cvss_metrics.privileges_required ?? "unknown"
user_interaction = result.cvss_metrics.user_interaction ?? "unknown"
scope = result.cvss_metrics.scope ?? "unknown"
confidentiality = result.cvss_metrics.confidentiality_impact ?? "unknown"
integrity = result.cvss_metrics.integrity_impact ?? "unknown"
availability = result.cvss_metrics.availability_impact ?? "unknown"
exploitability = result.cvss_metrics.exploitability_score ?? 0
impact = result.cvss_metrics.impact_score ?? 0

# CISA KEV (null when CVE is NOT in the catalog)
is_in_kev = result.cisa_kev != null
kev_name = result.cisa_kev.vulnerability_name ?? ""
kev_action = result.cisa_kev.required_action ?? ""
kev_due = result.cisa_kev.due_date ?? ""
kev_added = result.cisa_kev.date_added ?? ""

# References (array of URL strings)
refs = result.references ?? []
```

**Null-safety note**: Cy's null-coalescing chains through null intermediate fields. If `result` is `null`, `result.cvss_metrics.base_score ?? 0` safely returns `0`.

### Error Handling

The action raises exceptions on failure. Always wrap in `try/catch`:

```cy
try {
    cve_data = app::nistnvd::cve_lookup(cve=cve_id)
} catch (e) {
    log("NVD lookup failed for ${cve_id}: ${e}")
    cve_data = null
}
```

**Error scenarios** (tested live):

| Error Case | Error Message Pattern | How to Handle |
|------------|----------------------|---------------|
| Invalid CVE format | `"CVE ID must start with 'CVE-'"` or `"CVE ID year must be 4 digits"` | Validate format before calling; skip malformed IDs |
| CVE not found | `"No data found for CVE ..."` | Log and continue; CVE may be reserved/unreleased |
| Rate limit (HTTP 429) | `"Rate limit exceeded. Please try again later."` | Retried automatically by built-in retry logic |
| Service unavailable (HTTP 503) | `"NIST NVD service temporarily unavailable"` | Retried 3x with exponential backoff (2–10s); NVD has periodic maintenance windows |
| Timeout | `"Request timed out after 30 seconds"` | Retried; NVD can be slow for CVEs with large CPE lists |
| Network failure | `"Failed to connect to NIST NVD API: ..."` | Retried 3x |

**Soft not-found edge case**: If the NVD API returns HTTP 200 but the CVE resolves to a 404 internally, the action may return `{"not_found": True, "cve_id": "..."}` as a *success* (no exception thrown). Always check `result.not_found` after a successful call — see Safe Lookup Pattern below.

### Safe Lookup Pattern (Canonical)

Use this pattern whenever calling `cve_lookup`. It handles both exception errors and the soft not-found edge case:

```cy
nvd = null
try {
    nvd = app::nistnvd::cve_lookup(cve=cve_id)
    if (nvd.not_found ?? False) {
        log("CVE ${cve_id} not found in NVD")
        nvd = null
    }
} catch (e) {
    log("NVD lookup failed for ${cve_id}: ${e}")
}
# After this block: nvd is either a valid response dict or null
```

All examples in `investigation-patterns.md` use this pattern. When building new tasks, copy this block and proceed with an `if (nvd == null)` check.

### Batch Pattern (Multiple CVEs)

When an alert references multiple CVEs, loop through them. The for-in loop enables parallel execution in Cy, but NVD's rate limit (5 req/30s without API key) means bursts over 5 may trigger HTTP 429. The integration retries automatically (3 attempts, exponential backoff 2–10s), so moderate batches (up to ~10 CVEs) work without manual throttling.

```cy
iocs = input.iocs ?? []
cve_ids = [ioc.value for(ioc in iocs) if(ioc.type == "cve")]

results = []
for (cve_id in cve_ids) {
    try {
        nvd = app::nistnvd::cve_lookup(cve=cve_id)
        if (nvd.not_found ?? False) {
            results = results + [{"cve_id": cve_id, "status": "not_found"}]
        } else {
            results = results + [{
                "cve_id": nvd.cve_id ?? cve_id,
                "base_score": nvd.cvss_metrics.base_score ?? 0,
                "base_severity": nvd.cvss_metrics.base_severity ?? "unknown",
                "cisa_kev": if (nvd.cisa_kev != null) { True } else { False },
                "description": nvd.description ?? ""
            }]
        }
    } catch (e) {
        log("Failed to lookup ${cve_id}: ${e}")
        results = results + [{"cve_id": cve_id, "status": "error", "error": "${e}"}]
    }
}
```

### Rate Limits

<!-- EVIDENCE: Backend source code — actions.py rate limit comments and retry logic -->
<!-- EVIDENCE: Verified via https://nvd.nist.gov/developers/start-here -->

| Configuration | Limit |
|---------------|-------|
| Without API key (default) | 5 requests per rolling 30-second window |
| With API key | 50 requests per rolling 30-second window |
| Built-in retries | 3 attempts with exponential backoff (2–10 seconds) |
| Request timeout | 30 seconds |

The rate limit is enforced by NVD, not by the integration. Bursts succeed until NVD responds with HTTP 429, at which point the built-in retry kicks in.

### Known Limitations

- **Single CVE per call** — No bulk endpoint; batch by looping (see Batch Pattern above).
- **No search by product/CPE** — Only exact CVE ID lookup. Cannot query "which CVEs affect Apache 2.4.49?". Pass product names to LLM to suggest relevant CVEs, or use Splunk to find CVE references in logs.
- **No date range queries** — Cannot search for CVEs published after a given date.
- **No affected product extraction** — CPE entries exist in `full_data.vulnerabilities[0].cve.configurations` but are not extracted to a top-level field.
- **No CWE extraction** — Weakness enumeration (CWE IDs) exists in `full_data` but is not surfaced as a top-level field.
- **CVSS v4.0 not extracted** — NVD returns CVSS v4.0 under `cvssMetricV40` but the integration only extracts v3.1 and v2. CVEs scored solely with v4.0 will have empty `cvss_metrics`.
- **CISA KEV `due_date` may be null** — Observed in live testing; check before using in urgency calculations.
- **Large `full_data`** — CVEs with many CPE entries (like Log4j) produce very large responses (100KB+); avoid passing to LLM prompts.
