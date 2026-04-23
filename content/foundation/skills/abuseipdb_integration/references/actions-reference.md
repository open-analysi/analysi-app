# AbuseIPDB Actions Reference

## lookup_ip

Query IP reputation and abuse reports from AbuseIPDB's crowd-sourced database.

<!-- EVIDENCE: MCP live query — list_integration_tools(abuseipdb) -->
<!-- EVIDENCE: MCP live test — run_integration_tool(lookup_ip, {ip: "185.220.101.45"}) -->
<!-- EVIDENCE: MCP live test — run_integration_tool(lookup_ip, {ip: "8.8.8.8", days: 90}) -->
<!-- EVIDENCE: MCP live test — run_integration_tool(lookup_ip, {ip: "192.168.1.1"}) -->

### Cy Syntax

```cy
result = app::abuseipdb::lookup_ip(ip="185.220.101.45")
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `ip` | string | Yes | — | IPv4 or IPv6 address to check |
| `days` | integer | No | 10 | Lookback period in days (max 365). Note: the Analysi integration defaults to 10 days; the upstream AbuseIPDB API defaults to 30. |

The action also accepts `ip_address` as an alias for `ip`.

**IPv6 support:** AbuseIPDB accepts full IPv6 addresses (e.g., `"2001:db8::1"`). IPv6 addresses tend to have fewer crowd-sourced reports than IPv4, so expect lower `total_reports` and potentially less reliable `abuse_confidence_score` values. A low score for an IPv6 address may reflect sparse data rather than benign status.

### Response Fields

The Analysi integration flattens most fields from the AbuseIPDB API response to the top level for convenient access. Two fields — `isTor` and `ipVersion` — remain nested inside the raw API wrapper at `full_data.data` because they are not part of the standard flattened schema.

Top-level fields:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `abuse_confidence_score` | integer | 0–100 abuse likelihood (higher = worse) | `100` |
| `total_reports` | integer | Number of abuse reports in the lookback window | `13` |
| `num_distinct_users` | integer | Unique reporters — higher = more credible | `10` |
| `ip_address` | string | Echoed IP address | `"185.220.101.45"` |
| `is_public` | boolean | Whether the IP is publicly routable | `true` |
| `is_whitelisted` | boolean | AbuseIPDB's internal whitelist (major services) | `false` |
| `country_code` | string\|null | ISO 3166-1 alpha-2 country code | `"DE"` |
| `usage_type` | string\|null | ISP classification | `"Fixed Line ISP"` |
| `isp` | string\|null | Internet Service Provider name | `"Network for Tor-Exit traffic."` |
| `domain` | string\|null | Associated domain | `"for-privacy.net"` |
| `hostnames` | array | Reverse DNS hostnames | `["tor-exit-45.for-privacy.net"]` |
| `last_reported_at` | string\|null | ISO 8601 timestamp of most recent report | `"2026-03-17T19:03:01+00:00"` |
| `full_data` | object | Raw API response wrapper (see nested fields below) | — |

#### Nested Fields in `full_data.data`

| Field | Type | Description |
|-------|------|-------------|
| `isTor` | boolean | Whether IP is a known Tor exit node |
| `ipVersion` | integer | IP version (4 or 6) |

Access via `result.full_data.data.isTor` and `result.full_data.data.ipVersion`.

### Response Examples

**Malicious Tor Exit Node** (score 100):
```json
{
  "abuse_confidence_score": 100,
  "total_reports": 13,
  "num_distinct_users": 10,
  "is_public": true,
  "is_whitelisted": false,
  "country_code": "DE",
  "usage_type": "Fixed Line ISP",
  "isp": "Network for Tor-Exit traffic.",
  "domain": "for-privacy.net",
  "hostnames": ["tor-exit-45.for-privacy.net"],
  "last_reported_at": "2026-03-17T19:03:01+00:00"
}
```

**Benign Whitelisted IP** (score 0):
```json
{
  "abuse_confidence_score": 0,
  "total_reports": 66,
  "num_distinct_users": 34,
  "is_public": true,
  "is_whitelisted": true,
  "country_code": "US",
  "usage_type": "Content Delivery Network",
  "isp": "Google LLC",
  "domain": "google.com",
  "hostnames": ["dns.google"]
}
```
Note: 8.8.8.8 has `total_reports: 66` but `abuse_confidence_score: 0` and `is_whitelisted: true`. Reports alone do not indicate malice — the confidence score is the authoritative signal.

**Private/RFC1918 IP** (192.168.1.1):
```json
{
  "abuse_confidence_score": 0,
  "total_reports": 0,
  "is_public": false,
  "country_code": null,
  "usage_type": "Reserved",
  "isp": null,
  "domain": null,
  "hostnames": []
}
```
Private IPs return `is_public: false` with null geo/ISP fields. Querying private IPs is not an error — it just yields no reputation data.

### Cy Usage Pattern

```cy
ip = input.primary_ioc_value ?? input.network_info.src_ip ?? "0.0.0.0"

try {
    result = app::abuseipdb::lookup_ip(ip=ip, days=30)
    score = result.abuse_confidence_score ?? 0
    reports = result.total_reports ?? 0
    is_tor = result.full_data.data.isTor ?? False
    is_whitelisted = result.is_whitelisted ?? False
    isp_name = result.isp ?? "unknown"
    country = result.country_code ?? "unknown"
} catch (e) {
    log("AbuseIPDB lookup failed for ${ip}: ${e}")
    score = -1
    reports = 0
    is_tor = False
    is_whitelisted = False
    isp_name = "unknown"
    country = "unknown"
}
```

### Interpreting the Confidence Score

| Score Range | Interpretation | Typical Triage Action |
|-------------|---------------|----------------------|
| 0 | No abuse reports or whitelisted | Likely benign — check other sources |
| 1–25 | Low confidence — few or old reports | Investigate further, not conclusive |
| 26–75 | Moderate — multiple reporters agree | Correlate with VT/Splunk, lean suspicious |
| 76–100 | High confidence — widely reported | Strong malicious signal, corroborate for TP |

Key nuances:
- `is_whitelisted: true` overrides score (e.g., Google DNS has reports but score 0)
- `num_distinct_users` adds credibility — 1 reporter vs 10 matters
- `isTor: true` is informational, not inherently malicious (depends on alert context)
- `total_reports` reflects the lookback window (`days` parameter), not all-time

### Error Handling

The action returns error objects (not exceptions) for validation failures:

| Error | Cause | Handling |
|-------|-------|----------|
| `"IP address is required"` | Missing or empty `ip` parameter | Check input extraction logic |
| `"Invalid IP address format: ..."` | Malformed IP string | Validate before calling |
| `"Rate limit exceeded"` | HTTP 429 from AbuseIPDB API | Back off; reduce batch sizes |
| `"Request timed out after 30 seconds"` | API timeout (retries exhausted) | Degrade gracefully; skip enrichment |
| `"Invalid API key"` | HTTP 401 | Configuration issue; alert ops team |

The integration retries transient failures automatically (3 attempts, exponential backoff 2–10s). Permanent errors surface immediately.

---

## report_ip

Report an IP address for abusive behavior to AbuseIPDB.

### Cy Syntax

```cy
result = app::abuseipdb::report_ip(ip="185.220.101.45", categories="18,22")
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ip` | string | Yes | IP address to report |
| `categories` | string | Yes | Comma-separated AbuseIPDB category IDs (see full table below) |
| `comment` | string | No | Free-text description of the abuse |

### AbuseIPDB Category IDs

Use these numeric IDs in the `categories` parameter. Multiple categories can be combined: `categories="14,18,22"`.

| ID | Category | Common Alert Types |
|----|----------|--------------------|
| 1 | DNS Compromise | DNS hijacking |
| 2 | DNS Poisoning | DNS cache poisoning |
| 3 | Fraud Orders | E-commerce fraud |
| 4 | DDoS Attack | Volumetric attacks |
| 5 | FTP Brute-Force | FTP login attempts |
| 6 | Ping of Death | Malformed ICMP |
| 7 | Phishing | Phishing campaigns |
| 8 | Fraud VoIP | VoIP fraud |
| 9 | Open Proxy | Proxy abuse |
| 10 | Web Spam | Comment/form spam |
| 11 | Email Spam | Spam campaigns |
| 12 | Blog Spam | Blog comment spam |
| 13 | VPN IP | VPN-sourced abuse |
| 14 | Port Scan | Network reconnaissance |
| 15 | Hacking | Generic hacking |
| 16 | SQL Injection | SQL injection specifically |
| 17 | Spoofing | IP/email spoofing |
| 18 | Brute-Force | SSH/RDP/auth brute force |
| 19 | Bad Web Bot | Malicious crawlers/scrapers |
| 20 | Exploited Host | Compromised system |
| 21 | Web App Attack | XSS, RFI, LFI, etc. |
| 22 | SSH | SSH-specific abuse |
| 23 | IoT Targeted | IoT exploitation |

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `ip_address` | string | Reported IP |
| `abuse_confidence_score` | integer | Updated score after report |
| `message` | string | `"IP successfully reported to AbuseIPDB"` |

### Cy Usage Pattern

**Only call after confirmed true positive disposition:**

```cy
# IMPORTANT: Only report after confirmed TP with human approval
ip = input.primary_ioc_value ?? ""
alert_type = input.rule_name ?? "unknown"

# Map alert types to AbuseIPDB categories
# See investigation-patterns.md § Category Mapping for full mapping table
categories = "15"  # default: generic hacking
if (alert_type == "SSH Brute Force") {
    categories = "18,22"
} elif (alert_type == "Port Scan") {
    categories = "14"
} elif (alert_type == "SQL Injection") {
    categories = "16,21"
} elif (alert_type == "Phishing") {
    categories = "7"
}

try {
    report = app::abuseipdb::report_ip(
        ip=ip,
        categories=categories,
        comment="Confirmed ${alert_type} from SOC investigation"
    )
    log("Reported ${ip} to AbuseIPDB: score=${report.abuse_confidence_score}")
} catch (e) {
    log("AbuseIPDB report failed for ${ip}: ${e}")
}
```

### Guardrails

- **Never auto-report during triage** — reporting is a write operation that affects the global AbuseIPDB database
- **Require human-in-the-loop** before calling `report_ip` (e.g., Slack approval via `slack_disposition_approval_request` task)
- **Validate categories** — invalid or empty category strings return `ValidationError`
- **Duplicate reports** from the same API key within a short window may be rate-limited

---

## Not Available Actions

These actions exist for ThreatIntel archetype compliance but return `NotSupportedError` immediately. Do not call them.

| Action | Returns |
|--------|---------|
| `lookup_domain` | `"Domain lookups are not supported by AbuseIPDB. Use lookup_ip instead."` |
| `lookup_file_hash` | `"File hash lookups are not supported by AbuseIPDB. Use lookup_ip instead."` |
| `lookup_url` | `"URL lookups are not supported by AbuseIPDB. Use lookup_ip instead."` |

For domain, URL, and file hash reputation, use VirusTotal (`app::virustotal::domain_reputation`, `app::virustotal::url_reputation`, `app::virustotal::file_reputation`).
