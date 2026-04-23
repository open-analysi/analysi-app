# VirusTotal Investigation Patterns

Practical triage patterns for using VirusTotal in SOC alert investigation workflows. Each pattern includes a decision tree, Cy task template, and guidance on chaining with other integrations.

## Table of Contents

1. [When NOT to Use VirusTotal](#when-not-to-use-virustotal)
2. [Single IP Reputation Triage](#single-ip-reputation-triage)
3. [Domain Reputation Triage](#domain-reputation-triage)
4. [File Hash Investigation](#file-hash-investigation)
5. [URL Phishing Check](#url-phishing-check)
6. [Batch IOC Analysis](#batch-ioc-analysis)
7. [Multi-Source IP Corroboration (VT + AbuseIPDB)](#multi-source-ip-corroboration)
8. [Submit-and-Check URL Pattern](#submit-and-check-url-pattern)
9. [VT-to-Splunk Pivot](#vt-to-splunk-pivot)

---

## When NOT to Use VirusTotal

VT is a crowd-sourced reputation database — it has blind spots. Skip or supplement VT in these cases:

| Scenario | Why VT fails | Better approach |
|----------|-------------|-----------------|
| **RFC 1918 / private IPs** (10.x, 172.16-31.x, 192.168.x) | VT only tracks public internet indicators | Query Splunk for internal host activity |
| **Newly registered domains** (< 24 hours) | VT won't have scan data yet | Check WHOIS age + passive DNS; submit via `submit_url_analysis` if URL-based |
| **Custom/targeted malware** | Hash won't exist in VT's database (`not_found: true`) | Use sandbox analysis, YARA rules, EDR telemetry |
| **Legitimate infrastructure IPs** (Google, AWS, Cloudflare) | VT may show low `malicious` due to shared hosting; verdicts are unreliable | Check specific service logs; these IPs are almost never useful IOCs |
| **Internal domains / split-horizon DNS** | VT has no visibility into internal DNS | Query Splunk or internal DNS logs |
| **Encoded/obfuscated URLs** (data URIs, URL shorteners) | VT checks the literal URL, not the resolved target | Resolve/decode first, then check the final URL |

**Guard pattern for private IPs:**
```cy
ip = input.primary_ioc_value ?? ""
if (ip != "" and is_ipv4(ip) and is_private_ip(ip)) {
    return enrich_alert(input, {"status": "skipped", "reason": "private IP — not applicable for VT lookup"})
}
```

---

## Single IP Reputation Triage

**When to use:** Alert contains a suspicious source IP (brute force, C2 callback, lateral movement attempt).

**Decision tree:**
```
IP reputation lookup
├── malicious >= 10  → HIGH risk → recommend block + escalate
├── malicious 5-9    → MEDIUM risk → investigate further (check AbuseIPDB, Splunk logs)
├── malicious 1-4    → LOW risk → check AS owner context
│   ├── AS owner is major cloud/CDN (Google, AWS, Cloudflare) → likely FP
│   └── AS owner is hosting/VPN provider → investigate further
├── malicious == 0, not_found == true → UNKNOWN → no VT data, use other sources
└── malicious == 0, not_found != true → CLEAN → low priority
```

**Cy task template:**
```cy
# Single IP Reputation Triage
ip = input.primary_ioc_value ?? input.network_info.src_ip ?? ""

if (ip == "" or (not is_ipv4(ip) and not is_ipv6(ip))) {
    return enrich_alert(input, {"status": "skipped", "reason": "no valid IP"})
}

alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.title ?? "unknown alert"

try {
    vt = app::virustotal::ip_reputation(ip=ip)
} catch (e) {
    return enrich_alert(input, {"status": "error", "reason": "${e}", "ip": ip})
}

malicious = vt.reputation_summary.malicious ?? 0
suspicious = vt.reputation_summary.suspicious ?? 0
as_owner = vt.network_info.as_owner ?? "unknown"
country = vt.network_info.country ?? "unknown"
not_found = vt.not_found ?? False

analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

VirusTotal IP Reputation for ${ip}:
- Malicious detections: ${malicious}
- Suspicious detections: ${suspicious}
- AS Owner: ${as_owner}
- Country: ${country}
- Not found in VT: ${not_found}

Assess threat level considering the alert context. Is this IP relevant to the alert?
Return JSON (no markdown): {"verdict": "malicious|suspicious|benign|unknown", "confidence": "high|medium|low", "reason": "one sentence"}"""
)

enrichment = {
    "ip": ip,
    "reputation_summary": vt.reputation_summary,
    "network_info": vt.network_info,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

---

## Domain Reputation Triage

**When to use:** Alert involves a suspicious domain (DNS query, phishing email, web request to unknown domain).

**Decision tree:**
```
Domain reputation lookup
├── malicious >= 5 → HIGH risk → likely malicious domain
├── malicious 1-4 + categories contain "phishing"/"malware" → HIGH risk
├── malicious 1-4 + recently created (< 30 days) → MEDIUM-HIGH risk
├── malicious == 0 + categories contain "phishing"/"malware" → MEDIUM risk (recently flagged)
├── malicious == 0 + not_found == true → UNKNOWN → newly registered or obscure
└── malicious == 0 + categories are benign → CLEAN
```

**Cy task template:**
```cy
# Domain Reputation Triage
domain = input.primary_ioc_value ?? ""

if (domain == "") {
    return enrich_alert(input, {"status": "skipped", "reason": "no domain found"})
}

alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.title ?? "unknown alert"

try {
    vt = app::virustotal::domain_reputation(domain=domain)
} catch (e) {
    return enrich_alert(input, {"status": "error", "reason": "${e}", "domain": domain})
}

malicious = vt.reputation_summary.malicious ?? 0
categories = to_json(vt.categories ?? {})
creation_date = vt.creation_date
not_found = vt.not_found ?? False

analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

VirusTotal Domain Reputation for ${domain}:
- Malicious detections: ${malicious}
- Vendor categories: ${categories}
- Domain creation date: ${creation_date}
- Not found in VT: ${not_found}

Assess whether this domain is malicious considering the alert context.
Return JSON (no markdown): {"verdict": "malicious|suspicious|benign|unknown", "confidence": "high|medium|low", "reason": "one sentence"}"""
)

enrichment = {
    "domain": domain,
    "reputation_summary": vt.reputation_summary,
    "categories": vt.categories ?? {},
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

---

## File Hash Investigation

**When to use:** Alert contains a file hash from malware detection, EDR alert, or email attachment scanning.

**Decision tree:**
```
File hash reputation lookup
├── malicious >= 5 → MALWARE CONFIRMED → check threat_label for classification
│   ├── threat_label contains "ransomware" → CRITICAL escalation
│   ├── threat_label contains "trojan"/"rat" → HIGH escalation
│   └── threat_label contains "adware"/"pup" → MEDIUM (potentially unwanted)
├── malicious 1-4 → SUSPICIOUS → check sandbox_verdicts and YARA matches
├── malicious == 0, not_found == true → UNKNOWN hash → not in VT database
│   └── Consider: custom malware won't have VT history
└── malicious == 0, not_found != true → CLEAN → known clean file
```

**Cy task template:**
```cy
# File Hash Reputation Investigation
file_hash = input.primary_ioc_value ?? ""

if (file_hash == "") {
    return enrich_alert(input, {"status": "skipped", "reason": "no file hash found"})
}

alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.title ?? "unknown alert"

try {
    vt = app::virustotal::file_reputation(file_hash=file_hash)
} catch (e) {
    return enrich_alert(input, {"status": "error", "reason": "${e}", "file_hash": file_hash})
}

malicious = vt.reputation_summary.malicious ?? 0
file_type = vt.file_info.type_description ?? "unknown"
threat_label = vt.full_data.data.attributes.popular_threat_classification.suggested_threat_label ?? "none"
not_found = vt.not_found ?? False

analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

VirusTotal File Hash Reputation for ${file_hash}:
- Malicious detections: ${malicious}
- File type: ${file_type}
- Threat classification: ${threat_label}
- Not found in VT: ${not_found}

Determine if this file is malicious. Consider the threat label and file type.
Return JSON (no markdown): {"verdict": "malicious|suspicious|benign|unknown", "confidence": "high|medium|low", "reason": "one sentence", "threat_family": "name or none"}"""
)

enrichment = {
    "file_hash": file_hash,
    "malicious_detections": malicious,
    "file_type": file_type,
    "threat_label": threat_label,
    "not_found": not_found,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

---

## URL Phishing Check

**When to use:** Alert involves a suspicious URL (email link, web redirect, download URL).

**Cy task template:**
```cy
# URL Phishing / Malware Check
url = input.primary_ioc_value ?? ""

if (url == "") {
    return enrich_alert(input, {"status": "skipped", "reason": "no URL found"})
}

alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.title ?? "unknown alert"

try {
    vt = app::virustotal::url_reputation(url=url)
} catch (e) {
    return enrich_alert(input, {"status": "error", "reason": "${e}", "url": url})
}

malicious = vt.reputation_summary.malicious ?? 0
categories = to_json(vt.categories ?? {})
times_submitted = vt.times_submitted ?? 0
not_found = vt.not_found ?? False

analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

VirusTotal URL Reputation for ${url}:
- Malicious detections: ${malicious}
- Vendor categories: ${categories}
- Times submitted to VT: ${times_submitted}
- Not found in VT: ${not_found}

Assess if this URL is malicious (phishing, malware delivery, etc.).
Return JSON (no markdown): {"verdict": "malicious|suspicious|benign|unknown", "confidence": "high|medium|low", "reason": "one sentence"}"""
)

enrichment = {
    "url": url,
    "malicious_detections": malicious,
    "times_submitted": times_submitted,
    "not_found": not_found,
    "categories": vt.categories ?? {},
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

---

## Batch IOC Analysis

**When to use:** Alert contains multiple IOCs of different types (IPs, domains, URLs, file hashes) that all need VT enrichment.

**IOC type routing:**

| IOC type field | VT action | Parameter |
|----------------|-----------|-----------|
| `"ip"` or `"ipv4"` or `"ipv6"` | `ip_reputation` | `ip=value` |
| `"domain"` | `domain_reputation` | `domain=value` |
| `"url"` | `url_reputation` | `url=value` |
| `"filehash"` or `"file_hash"` | `file_reputation` | `file_hash=value` |

**Cy task template:**
```cy
# Batch IOC Analysis — routes each IOC to the correct VT action
iocs = input.iocs ?? []

if (len(iocs) == 0) {
    return enrich_alert(input, {"status": "skipped", "reason": "no IOCs in alert"})
}

alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.title ?? "unknown alert"
results = []
high_risk = 0

for (ioc in iocs) {
    ioc_type = ioc.type ?? "unknown"
    ioc_value = str(ioc.value ?? "")
    ioc_result = {"type": ioc_type, "value": ioc_value, "malicious": 0, "error": ""}

    if (ioc_value == "") {
        ioc_result.error = "empty value"
        results = results + [ioc_result]
    } elif (ioc_type == "ip" or ioc_type == "ipv4" or ioc_type == "ipv6") {
        try {
            vt = app::virustotal::ip_reputation(ip=ioc_value)
            ioc_result.malicious = vt.reputation_summary.malicious ?? 0
        } catch (e) {
            ioc_result.error = "${e}"
        }
        results = results + [ioc_result]
    } elif (ioc_type == "domain") {
        try {
            vt = app::virustotal::domain_reputation(domain=ioc_value)
            ioc_result.malicious = vt.reputation_summary.malicious ?? 0
        } catch (e) {
            ioc_result.error = "${e}"
        }
        results = results + [ioc_result]
    } elif (ioc_type == "url") {
        try {
            vt = app::virustotal::url_reputation(url=ioc_value)
            ioc_result.malicious = vt.reputation_summary.malicious ?? 0
        } catch (e) {
            ioc_result.error = "${e}"
        }
        results = results + [ioc_result]
    } elif (ioc_type == "filehash" or ioc_type == "file_hash") {
        try {
            vt = app::virustotal::file_reputation(file_hash=ioc_value)
            ioc_result.malicious = vt.reputation_summary.malicious ?? 0
        } catch (e) {
            ioc_result.error = "${e}"
        }
        results = results + [ioc_result]
    } else {
        ioc_result.error = "unsupported IOC type: ${ioc_type}"
        results = results + [ioc_result]
    }

    if (ioc_result.malicious >= 5) {
        high_risk = high_risk + 1
    }
}

results_json = to_json(results)

analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

Batch VT analysis of ${len(iocs)} IOCs. High-risk count: ${high_risk}.

Results: ${results_json}

Summarize findings. Which IOCs are most concerning and why?
Return JSON (no markdown): {"overall_risk": "high|medium|low", "summary": "two sentence assessment", "top_threat": "most concerning IOC value or none"}"""
)

enrichment = {
    "total_iocs": len(iocs),
    "high_risk_count": high_risk,
    "ioc_results": results,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

**Rate limit note:** Each IOC triggers a separate VT API call. With a free-tier key (4 req/min), batches of 5+ IOCs will hit rate limits. The backend auto-retries up to 3× with backoff. For large batches, consider limiting to the most critical IOCs.

---

## Multi-Source IP Corroboration

**When to use:** You want higher confidence in an IP verdict by cross-referencing VT with AbuseIPDB.

**Decision tree (consensus):**
```
VT malicious >= 5 AND AbuseIPDB confidence >= 50  → CONFIRMED malicious (high confidence)
VT malicious >= 5 AND AbuseIPDB confidence < 50   → VT-only signal (medium confidence, investigate)
VT malicious < 5  AND AbuseIPDB confidence >= 50   → AbuseIPDB-only signal (medium confidence, investigate)
VT malicious < 5  AND AbuseIPDB confidence < 50    → Likely benign (low risk)
Sources disagree significantly                       → Flag for manual review
```

**Cy task template:**
```cy
# Multi-Source IP Corroboration: VT + AbuseIPDB
ip = input.primary_ioc_value ?? input.network_info.src_ip ?? ""

if (ip == "" or (not is_ipv4(ip) and not is_ipv6(ip))) {
    return enrich_alert(input, {"status": "skipped", "reason": "no valid IP"})
}

alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.title ?? "unknown alert"

vt_error = ""
abuse_error = ""

try {
    vt = app::virustotal::ip_reputation(ip=ip)
} catch (e) {
    vt_error = "${e}"
    vt = null
}

try {
    abuse = app::abuseipdb::lookup_ip(ip=ip)
} catch (e) {
    abuse_error = "${e}"
    abuse = null
}

# Extract key metrics with safe defaults
vt_malicious = 0
vt_as_owner = "unknown"
if (vt != null) {
    vt_malicious = vt.reputation_summary.malicious ?? 0
    vt_as_owner = vt.network_info.as_owner ?? "unknown"
}

abuse_score = 0
abuse_reports = 0
if (abuse != null) {
    abuse_score = abuse.abuseConfidenceScore ?? abuse.data.abuseConfidenceScore ?? 0
    abuse_reports = abuse.totalReports ?? abuse.data.totalReports ?? 0
}

analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

Multi-source IP reputation for ${ip}:

VirusTotal:
- Malicious detections: ${vt_malicious}
- AS Owner: ${vt_as_owner}
- Error: ${vt_error}

AbuseIPDB:
- Abuse confidence score: ${abuse_score}%
- Total reports: ${abuse_reports}
- Error: ${abuse_error}

Do the sources agree? Assess overall threat level considering both sources and the alert context.
Return JSON (no markdown): {"verdict": "malicious|suspicious|benign|unknown", "confidence": "high|medium|low", "consensus": "agree|disagree|partial", "reason": "one to two sentences"}"""
)

enrichment = {
    "ip": ip,
    "virustotal": {"malicious": vt_malicious, "as_owner": vt_as_owner, "error": vt_error},
    "abuseipdb": {"confidence_score": abuse_score, "total_reports": abuse_reports, "error": abuse_error},
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

---

## Submit-and-Check URL Pattern

**When to use:** A URL in the alert has no VT history (`url_reputation` returned `not_found: true`) and you need a fresh scan.

```cy
# Submit unknown URL for analysis, then retrieve results
url = input.primary_ioc_value ?? ""

if (url == "") {
    return enrich_alert(input, {"status": "skipped", "reason": "no URL"})
}

# First check if URL already has reputation
try {
    existing = app::virustotal::url_reputation(url=url)
} catch (e) {
    return enrich_alert(input, {"status": "error", "reason": "lookup failed: ${e}"})
}

not_found = existing.not_found ?? False

if (not not_found) {
    # URL already has VT data — use it directly
    enrichment = {
        "url": url,
        "source": "existing_scan",
        "malicious_detections": existing.reputation_summary.malicious ?? 0,
        "ai_analysis": ""
    }
    return enrich_alert(input, enrichment)
}

# URL not in VT — submit for fresh scan
try {
    submission = app::virustotal::submit_url_analysis(url=url)
} catch (e) {
    return enrich_alert(input, {"status": "error", "reason": "submit failed: ${e}"})
}

analysis_id = submission.analysis_id ?? ""

# Retrieve analysis report
try {
    report = app::virustotal::get_analysis_report(analysis_id=analysis_id)
} catch (e) {
    return enrich_alert(input, {"status": "partial", "reason": "report retrieval failed: ${e}", "analysis_id": analysis_id})
}

status = report.analysis_status ?? "unknown"

enrichment = {
    "url": url,
    "source": "fresh_scan",
    "analysis_status": status,
    "malicious_detections": report.analysis_stats.malicious ?? 0,
    "analysis_id": analysis_id,
    "ai_analysis": ""
}

return enrich_alert(input, enrichment)
```

**Note:** If `analysis_status` is `"queued"`, the scan hasn't completed yet. In a workflow, store the `analysis_id` and check again in a later task.

---

## VT-to-Splunk Pivot

**When to use:** VT returned a positive or suspicious result, and you need to check your environment for related activity. This pattern enriches a VT finding with local log evidence from Splunk.

**Decision tree:**
```
VT malicious >= 5
├── IP → search Splunk for connections to/from IP in firewall, proxy, DNS logs
├── Domain → search Splunk for DNS queries resolving this domain
├── File hash → search Splunk for EDR/AV events referencing this hash
└── URL → search Splunk for proxy/web logs with this URL
```

**Cy task template (IP pivot):**
```cy
# VT-to-Splunk Pivot: enrich VT-flagged IP with local log evidence
ip = input.primary_ioc_value ?? ""

if (ip == "") {
    return enrich_alert(input, {"status": "skipped", "reason": "no IP"})
}

# Step 1: Get VT reputation
try {
    vt = app::virustotal::ip_reputation(ip=ip)
} catch (e) {
    return enrich_alert(input, {"status": "error", "reason": "VT lookup failed: ${e}", "ip": ip})
}

vt_malicious = vt.reputation_summary.malicious ?? 0

# Step 2: If VT flags it, search Splunk for local activity
splunk_hits = 0
splunk_error = ""
if (vt_malicious >= 3) {
    try {
        splunk_results = app::splunk::search_query(
            query="search index=* (src_ip=\"${ip}\" OR dest_ip=\"${ip}\") earliest=-7d | stats count by sourcetype, src_ip, dest_ip | head 20",
            max_results=20
        )
        splunk_hits = len(splunk_results.results ?? [])
    } catch (e) {
        splunk_error = "${e}"
    }
}

alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.title ?? "unknown alert"

analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

VT-to-Splunk pivot for IP ${ip}:
- VT malicious detections: ${vt_malicious}
- AS owner: ${vt.network_info.as_owner ?? "unknown"}
- Splunk log hits (7 days): ${splunk_hits}
- Splunk error: ${splunk_error}

If both VT flags it and Splunk shows activity, this IP is actively communicating with the environment — higher urgency.
Return JSON (no markdown): {"verdict": "malicious|suspicious|benign|unknown", "confidence": "high|medium|low", "local_exposure": "active|none|error", "reason": "one sentence"}"""
)

enrichment = {
    "ip": ip,
    "vt_malicious": vt_malicious,
    "splunk_hits": splunk_hits,
    "splunk_error": splunk_error,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

**Adapting for other IOC types:** Replace the Splunk query for domains (`query="search index=* query=\"${domain}\" earliest=-7d ..."`), file hashes (`query="search index=* file_hash=\"${hash}\" earliest=-7d ..."`), or URLs (`query="search index=* url=\"${url}\" earliest=-7d ..."`).
