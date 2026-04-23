# VirusTotal Actions Reference

Integration instance: `virustotal-main` (type: `virustotal`). All actions use Cy namespace `app::virustotal::`.

## Table of Contents

1. [ip_reputation](#ip_reputation)
2. [domain_reputation](#domain_reputation)
3. [url_reputation](#url_reputation)
4. [file_reputation](#file_reputation)
5. [submit_url_analysis](#submit_url_analysis)
6. [get_analysis_report](#get_analysis_report)
7. [Common Response Patterns](#common-response-patterns)
8. [Detection Thresholds](#detection-thresholds)
9. [Known Limitations](#known-limitations)

---

## ip_reputation

Look up IP address reputation across ~80 detection engines.

**Parameter:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `ip` | string | yes | IPv4 or IPv6 address |

**Cy call:**
```cy
vt = app::virustotal::ip_reputation(ip=ip)
```

**Return schema:**
```
{
  "ip_address": "185.220.101.45",
  "reputation_summary": {
    "malicious": 12,
    "suspicious": 0,
    "harmless": 58,
    "undetected": 9
  },
  "network_info": {
    "asn": 205100,
    "as_owner": "F5 Inc.",
    "country": "DE"
  },
  "last_analysis_date": 1773770000,
  "full_data": { ... }
}
```

**Key fields for triage:**
- `reputation_summary.malicious` — primary signal; see § Detection Thresholds for interpretation
- `network_info.as_owner` — distinguishes infrastructure IPs (Google, Cloudflare, AWS) from suspicious hosting providers
- `network_info.country` — geographic context for geofencing decisions

**Minimal Cy example:** For a full task template with LLM reasoning, see `investigation-patterns.md` § Single IP Reputation Triage.
```cy
try {
    vt = app::virustotal::ip_reputation(ip=ip)
} catch (e) {
    return enrich_alert(input, {"status": "error", "reason": "${e}", "ip": ip})
}
return enrich_alert(input, {"ip": ip, "malicious": vt.reputation_summary.malicious ?? 0, "as_owner": vt.network_info.as_owner ?? "unknown"})
```

---

## domain_reputation

Look up domain reputation across ~80 detection engines.

**Parameter:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `domain` | string | yes | Domain name (e.g., `example.com`) |

**Cy call:**
```cy
vt = app::virustotal::domain_reputation(domain=domain)
```

**Return schema:**
```
{
  "domain": "malicious-phishing.com",
  "reputation_summary": {
    "malicious": 8,
    "suspicious": 2,
    "harmless": 55,
    "undetected": 15
  },
  "categories": {
    "BitDefender": "phishing",
    "Sophos": "malware",
    "Forcepoint ThreatSeeker": "phishing"
  },
  "creation_date": 1620000000,
  "last_analysis_date": 1773770000,
  "full_data": { ... }
}
```

**Key fields for triage:**
- `categories` — vendor-assigned categories. Values like "phishing", "malware", "spam" are strong signals
- `creation_date` — recently created domains (< 30 days) combined with any malicious detections are high-confidence indicators
- `reputation_summary.malicious` — see § Detection Thresholds

**Minimal Cy example:** For a full task template with LLM reasoning, see `investigation-patterns.md` § Domain Reputation Triage.
```cy
try {
    vt = app::virustotal::domain_reputation(domain=domain)
} catch (e) {
    return enrich_alert(input, {"status": "error", "reason": "${e}", "domain": domain})
}
return enrich_alert(input, {"domain": domain, "malicious": vt.reputation_summary.malicious ?? 0, "categories": vt.categories ?? {}})
```

---

## url_reputation

Look up URL reputation. VT base64-encodes the URL internally for the API path.

**Parameter:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `url` | string | yes | Full URL including scheme (e.g., `https://evil.com/payload`) |

**Cy call:**
```cy
vt = app::virustotal::url_reputation(url=url)
```

**Return schema:**
```
{
  "url": "https://evil.com/malware.exe",
  "reputation_summary": {
    "malicious": 5,
    "suspicious": 1,
    "harmless": 60,
    "undetected": 24
  },
  "categories": {
    "Sophos": "malware",
    "BitDefender": "malware"
  },
  "last_analysis_date": 1773770000,
  "first_submission_date": 1620000000,
  "times_submitted": 42,
  "full_data": { ... }
}
```

**Key fields for triage:**
- `times_submitted` — high submission count with 0 malicious = well-known clean URL. Low submission count = less confidence either way
- `categories` — "malware", "phishing", "spam" categories are strong signals
- If the URL has never been scanned, response includes `"not_found": true` — use `submit_url_analysis` for a fresh scan

**Minimal Cy example:** For a full task template with LLM reasoning, see `investigation-patterns.md` § URL Phishing Check.
```cy
try {
    vt = app::virustotal::url_reputation(url=url)
} catch (e) {
    return enrich_alert(input, {"status": "error", "reason": "${e}", "url": url})
}
return enrich_alert(input, {"url": url, "malicious": vt.reputation_summary.malicious ?? 0, "not_found": vt.not_found ?? False})
```

---

## file_reputation

Look up file hash reputation. Accepts MD5 (32 chars), SHA1 (40 chars), or SHA256 (64 chars).

**Parameter:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `file_hash` | string | yes | MD5, SHA1, or SHA256 hash (hex string) |

**Cy call:**
```cy
vt = app::virustotal::file_reputation(file_hash=file_hash)
```

**Return schema:**
```
{
  "file_hash": "44d88612fea8a8f36de82e1278abb02f",
  "reputation_summary": {
    "malicious": 65,
    "suspicious": 0,
    "harmless": 0,
    "undetected": 2
  },
  "file_info": {
    "size": 68,
    "type_description": "Powershell",
    "type_tag": "powershell",
    "creation_date": null,
    "first_submission_date": 1148301722
  },
  "last_analysis_date": 1773772938,
  "times_submitted": 1133396,
  "full_data": { ... }
}
```

**Key fields for triage:**
- `reputation_summary.malicious` — for files, even 1 detection warrants investigation; see § Detection Thresholds
- `file_info.type_description` — file type context (e.g., "Powershell", "PE32 executable", "PDF document")
- `full_data.data.attributes.popular_threat_classification.suggested_threat_label` — e.g., "virus.eicar/test", "trojan.emotet"
- `full_data.data.attributes.sandbox_verdicts` — sandbox analysis results
- `full_data.data.attributes.crowdsourced_yara_results` — YARA rule matches

**Deep inspection fields** (via `full_data.data.attributes`):
- `names` — known file names submitted under this hash
- `tags` — behavioral tags (e.g., "detect-debug-environment", "powershell", "via-tor")
- `sigma_analysis_stats` — Sigma rule match statistics
- `crowdsourced_ids_results` — IDS rule matches

**Hash validation:** The backend validates hash format by length (32=MD5, 40=SHA1, 64=SHA256) and hex characters. Invalid hashes throw a validation error.

**Minimal Cy example:** For a full task template with LLM reasoning, see `investigation-patterns.md` § File Hash Investigation.
```cy
try {
    vt = app::virustotal::file_reputation(file_hash=file_hash)
} catch (e) {
    return enrich_alert(input, {"status": "error", "reason": "${e}", "file_hash": file_hash})
}
threat_label = vt.full_data.data.attributes.popular_threat_classification.suggested_threat_label ?? "none"
return enrich_alert(input, {"file_hash": file_hash, "malicious": vt.reputation_summary.malicious ?? 0, "threat_label": threat_label})
```

---

## submit_url_analysis

Submit a URL for a fresh VT scan. Returns an `analysis_id` to poll with `get_analysis_report`.

**Parameter:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `url` | string | yes | Full URL to submit for analysis |

**Cy call:**
```cy
submission = app::virustotal::submit_url_analysis(url=url)
analysis_id = submission.analysis_id
```

**Return schema:**
```
{
  "url": "https://suspicious-site.com/login",
  "analysis_id": "u-0f115db062b7c0dd030b16878c99dea5c354b49dc37b38eb8846179c7783e9d7-0658e0ca",
  "message": "URL submitted for analysis. Use get_analysis_report with the analysis_id to get results.",
  "full_data": { ... }
}
```

For the complete submit-then-poll workflow, see `investigation-patterns.md` § Submit-and-Check URL Pattern.

---

## get_analysis_report

Retrieve results for a previously submitted URL analysis.

**Parameter:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `analysis_id` | string | yes | Analysis ID from `submit_url_analysis` |

**Cy call:**
```cy
report = app::virustotal::get_analysis_report(analysis_id=analysis_id)
```

**Return schema:**
```
{
  "analysis_id": "u-0f115db...",
  "analysis_status": "completed",
  "analysis_stats": {
    "malicious": 0,
    "suspicious": 0,
    "harmless": 68,
    "undetected": 27
  },
  "analysis_date": 1773773323,
  "full_data": { ... }
}
```

**Important:** Check `analysis_status` before using `analysis_stats`. If status is `"queued"`, the scan is still in progress and stats will be incomplete.

**Note:** The response uses `analysis_stats` (not `reputation_summary`) since this reports on a specific scan rather than aggregated reputation.

For the complete submit-then-poll workflow, see `investigation-patterns.md` § Submit-and-Check URL Pattern.

---

## Common Response Patterns

### The `reputation_summary` Object

All four reputation actions (IP, domain, URL, file) return this consistent structure:

```
"reputation_summary": {
    "malicious": <int>,     # engines that flagged as malicious
    "suspicious": <int>,    # engines that flagged as suspicious
    "harmless": <int>,      # engines that flagged as harmless/clean
    "undetected": <int>,    # engines that returned no verdict
    "timeout": <int>        # engines that timed out (usually 0; omitted when 0)
}
```

Total engines ≈ `malicious + suspicious + harmless + undetected + timeout`. Typically ~70-80 for URLs, ~80 for IPs/domains, ~67-76 for files.

### The `full_data` Object

Every action returns `full_data` containing the raw VT API v3 response. Key paths:

- `full_data.data.attributes.last_analysis_results` — per-engine verdicts (engine_name, category, result)
- `full_data.data.attributes.total_votes` — community votes (`harmless`, `malicious` counts)
- `full_data.data.attributes.reputation` — VT community reputation score (integer, higher = more trusted)
- `full_data.data.attributes.tags` — behavioral tags array

### The `not_found` Flag

When VT has no record for an indicator, reputation actions return:
```
{
  "not_found": true,
  "reputation_summary": { "malicious": 0, "suspicious": 0, "harmless": 0, "undetected": 0 },
  ...
}
```

**"Never seen" means unknown, not clean.** Do not treat `not_found` as a safe verdict. For URLs, use `submit_url_analysis` to request a fresh scan. For IPs/domains, corroborate with other sources (AbuseIPDB, Splunk logs). For file hashes, the file may be custom/targeted malware with no public VT submission.

---

## Detection Thresholds

General-purpose thresholds for interpreting `reputation_summary.malicious` across all VT actions. Adjust based on your organization's risk tolerance.

### IP Addresses

| Malicious Count | Risk Level | Recommended Action |
|-----------------|------------|-------------------|
| 0 (not_found) | Unknown | Check other sources (AbuseIPDB, Splunk logs) |
| 0 (found) | Clean | Low priority, monitor |
| 1-4 | Low | Check AS owner context; cloud/CDN providers are often FP |
| 5-9 | Medium | Investigate — corroborate with AbuseIPDB, check Splunk logs |
| 10+ | High | Likely malicious — recommend block, escalate |

### Domains

| Malicious Count | Context | Risk Level |
|-----------------|---------|------------|
| 0, benign categories | Clean | Low priority |
| 0, no categories | Unknown | Check domain age, WHOIS |
| 1-4, no phishing/malware category | Low-Medium | Monitor |
| 1-4, phishing/malware category | High | Likely malicious |
| 5+ | Any | Confirmed malicious |

### File Hashes

| Malicious Count | Risk Level | Action |
|-----------------|------------|--------|
| 0 (not_found) | Unknown | Possibly custom/targeted malware with no VT history |
| 0 (found) | Clean | Known clean file |
| 1-4 | Medium | Check sandbox verdicts and YARA matches for confirmation |
| 5+ | High | Confirmed malware — check `suggested_threat_label` for family |

### URLs

| Malicious Count | Context | Risk Level |
|-----------------|---------|------------|
| 0, high submissions | Clean | Well-known URL |
| 0, low submissions | Unknown | Not enough data |
| 1-4 | Medium | Check categories for phishing/malware |
| 5+ | High | Confirmed malicious URL |

---

## Known Limitations

- **Rate limits (429):** The backend retries automatically (3 attempts, exponential backoff 2-10s). Free-tier VT API keys allow 4 requests/minute; batch workflows with many IOCs will hit this. Space calls or use a premium key.
- **No file upload:** Only hash-based lookups are supported. You cannot submit a file binary — only check if a hash exists in VT's database.
- **No relationship queries:** VT API v3 relationship endpoints (communicating files, referrer URLs, subdomains, etc.) are not exposed. Use Splunk log queries for local pivoting instead.
- **URL reputation requires prior scan:** If a URL has never been submitted to VT, `url_reputation` returns `not_found: true`. Use `submit_url_analysis` first, then `get_analysis_report`.
- **Timeout:** Default 30s HTTP timeout. The exception message is "Request timed out after 30 seconds".
- **IP parameter name:** The backend accepts both `ip` and `ip_address` as parameter names for `ip_reputation`. In Cy scripts, use `ip=` (matching the manifest schema).
