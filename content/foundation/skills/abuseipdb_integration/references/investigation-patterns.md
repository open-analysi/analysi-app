# AbuseIPDB Investigation Patterns

## Pattern 1: Single-Source IP Reputation Enrichment

The simplest pattern — enrich an alert with AbuseIPDB data and use LLM to interpret the results in alert context.

```cy
# Extract IP and alert context
ip = input.primary_ioc_value ?? input.network_info.src_ip ?? "0.0.0.0"
alert_context = input.enrichments.alert_context_generation.ai_analysis ??
                input.rule_name ??
                input.title ??
                "unknown alert"

# Query AbuseIPDB
abuse_result = {}
abuse_error = ""
try {
    abuse_result = app::abuseipdb::lookup_ip(ip=ip, days=30)
} catch (e) {
    abuse_error = "${e}"
    log("AbuseIPDB lookup failed: ${e}")
}

score = abuse_result.abuse_confidence_score ?? -1
reports = abuse_result.total_reports ?? 0
distinct_users = abuse_result.num_distinct_users ?? 0
is_tor = abuse_result.full_data.data.isTor ?? False
is_whitelisted = abuse_result.is_whitelisted ?? False
isp_name = abuse_result.isp ?? "unknown"
country = abuse_result.country_code ?? "unknown"

# LLM analysis with context
analysis = ""
if (score >= 0) {
    analysis = llm_run(
        prompt="""Alert Context: ${alert_context}

AbuseIPDB results for ${ip}:
- Abuse confidence score: ${score}/100
- Total reports: ${reports} from ${distinct_users} distinct reporters
- Is Tor exit node: ${is_tor}
- Is whitelisted: ${is_whitelisted}
- ISP: ${isp_name}
- Country: ${country}

Based on the alert context, assess this IP. Consider:
1. Does the abuse score corroborate the alert?
2. Is Tor usage expected or suspicious in this context?
3. Does the ISP/geo suggest a known threat region?

Return JSON (no markdown): {"verdict": "malicious|suspicious|benign|unknown", "reason": "one sentence"}"""
    )
} else {
    analysis = """{"verdict": "unknown", "reason": "AbuseIPDB lookup failed: """ + abuse_error + """"}"""
}

enrichment = {
    "ip": ip,
    "abuse_confidence_score": score,
    "total_reports": reports,
    "num_distinct_users": distinct_users,
    "is_tor": is_tor,
    "is_whitelisted": is_whitelisted,
    "isp": isp_name,
    "country_code": country,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

---

## Pattern 2: Multi-Source IP Correlation (AbuseIPDB + VirusTotal)

Cross-reference AbuseIPDB crowd-sourced reports with VirusTotal scanner verdicts for higher-confidence triage. Both calls run in parallel via Cy's for-in auto-parallelization.

```cy
ip = input.primary_ioc_value ?? input.network_info.src_ip ?? "0.0.0.0"
alert_context = input.enrichments.alert_context_generation.ai_analysis ??
                input.rule_name ??
                "unknown alert"

# Parallel reputation queries
abuse_result = {}
vt_result = {}
abuse_error = ""
vt_error = ""

try {
    abuse_result = app::abuseipdb::lookup_ip(ip=ip, days=30)
} catch (e) {
    abuse_error = "${e}"
    log("AbuseIPDB failed: ${e}")
}

try {
    vt_result = app::virustotal::ip_reputation(ip=ip)
} catch (e) {
    vt_error = "${e}"
    log("VirusTotal failed: ${e}")
}

# Extract key signals
abuse_score = abuse_result.abuse_confidence_score ?? -1
abuse_reports = abuse_result.total_reports ?? 0
abuse_users = abuse_result.num_distinct_users ?? 0
is_tor = abuse_result.full_data.data.isTor ?? False
is_whitelisted = abuse_result.is_whitelisted ?? False

vt_malicious = vt_result.data.attributes.last_analysis_stats.malicious ?? 0
vt_suspicious = vt_result.data.attributes.last_analysis_stats.suspicious ?? 0
vt_reputation = vt_result.data.attributes.reputation ?? 0

# LLM correlation analysis
analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

Multi-source IP reputation for ${ip}:

AbuseIPDB:
- Abuse confidence: ${abuse_score}/100
- Reports: ${abuse_reports} from ${abuse_users} reporters
- Tor exit: ${is_tor}, Whitelisted: ${is_whitelisted}
- Error: ${abuse_error}

VirusTotal:
- Malicious detections: ${vt_malicious}/80+
- Suspicious detections: ${vt_suspicious}
- Reputation score: ${vt_reputation}
- Error: ${vt_error}

Assess source agreement:
1. Do both sources agree on threat level?
2. If they disagree, which is more reliable for this alert type?
3. What is the combined verdict?

Return JSON (no markdown): {"verdict": "malicious|suspicious|benign|unknown", "confidence": "high|medium|low", "source_agreement": true/false, "reason": "one sentence"}"""
)

enrichment = {
    "ip": ip,
    "abuseipdb": {
        "score": abuse_score,
        "reports": abuse_reports,
        "distinct_users": abuse_users,
        "is_tor": is_tor,
        "is_whitelisted": is_whitelisted
    },
    "virustotal": {
        "malicious": vt_malicious,
        "suspicious": vt_suspicious,
        "reputation": vt_reputation
    },
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

### Source Agreement Decision Tree

```
Both abuse_score >= 75 AND vt_malicious >= 3
  → HIGH confidence malicious — likely TP

abuse_score >= 75 BUT vt_malicious == 0
  → AbuseIPDB-only signal — check if newly reported (VT lags crowd-sourced)
  → Medium confidence — correlate with Splunk event volume

abuse_score == 0 AND vt_malicious >= 5
  → VT-only signal — may be new threat not yet in AbuseIPDB
  → Medium confidence — check is_whitelisted

Both abuse_score < 25 AND vt_malicious < 2
  → LOW threat signal — likely benign or insufficient data

is_whitelisted == true (regardless of reports)
  → Trusted infrastructure (Google, Cloudflare, etc.) — likely FP
```

---

## Pattern 3: Brute Force Investigation with Splunk Correlation

For brute force alerts, combine AbuseIPDB reputation with Splunk authentication logs to assess attack severity and success.

```cy
ip = input.primary_ioc_value ?? input.network_info.src_ip ?? "0.0.0.0"
alert_context = input.enrichments.alert_context_generation.ai_analysis ??
                input.rule_name ??
                "unknown alert"
username = input.primary_risk_entity_value ?? "unknown_user"

# Get reputation
abuse_result = {}
try {
    abuse_result = app::abuseipdb::lookup_ip(ip=ip, days=30)
} catch (e) {
    log("AbuseIPDB failed: ${e}")
}

abuse_score = abuse_result.abuse_confidence_score ?? -1
is_tor = abuse_result.full_data.data.isTor ?? False
isp = abuse_result.isp ?? "unknown"

# Get Splunk auth events for this IP
splunk_results = {}
try {
    splunk_results = app::splunk::search(
        query="""search index=* sourcetype=*auth* src="${ip}"
| stats count as total_attempts,
        count(eval(action="success")) as successful,
        count(eval(action="failure")) as failed,
        dc(user) as targeted_users,
        values(user) as users
| eval success_rate=round(successful/total_attempts*100, 1)""",
        earliest="-24h",
        latest="now"
    )
} catch (e) {
    log("Splunk query failed: ${e}")
}

analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

Brute Force Investigation for IP ${ip}:

Reputation:
- AbuseIPDB score: ${abuse_score}/100
- Tor exit: ${is_tor}
- ISP: ${isp}

Authentication Activity (Splunk):
${to_json(splunk_results, 2)}

Assess:
1. Is this a brute force attack or normal activity?
2. Were any logins successful (potential compromise)?
3. Is the attacker targeting one user or spraying?
4. Given the reputation, is this likely automated?

Return JSON (no markdown): {"attack_confirmed": true/false, "compromised": true/false, "attack_type": "credential_stuffing|password_spray|targeted_brute_force|normal_activity", "reason": "one sentence"}"""
)

enrichment = {
    "ip": ip,
    "abuse_confidence_score": abuse_score,
    "is_tor": is_tor,
    "isp": isp,
    "splunk_auth_summary": splunk_results,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

---

## Pattern 4: Batch IP Enrichment

When an alert contains multiple IOCs with IP addresses, enrich all of them in a single task. Cy's for-in loop auto-parallelizes the API calls.

**Rate limit consideration:** AbuseIPDB enforces per-key rate limits. For alerts with many IPs (>10), limit lookups to the most critical IPs — the primary IOC and the source IP. The remaining IPs can be queried in a follow-up task if needed.

```cy
iocs = input.iocs ?? []
alert_context = input.enrichments.alert_context_generation.ai_analysis ??
                input.rule_name ??
                "unknown alert"

# Filter to IP-type IOCs, cap at 10 to respect rate limits
ip_iocs = [ioc for(ioc in iocs) if((ioc.type ?? "") == "ipv4" or (ioc.type ?? "") == "ipv6" or (ioc.type ?? "") == "ip")]
ip_iocs = take(ip_iocs, 10)

# Enrich each IP (auto-parallelized by Cy)
ip_results = []
for (ioc in ip_iocs) {
    ioc_value = ioc.value ?? ""
    abuse_data = {}
    try {
        abuse_data = app::abuseipdb::lookup_ip(ip=ioc_value, days=30)
    } catch (e) {
        log("AbuseIPDB lookup failed for ${ioc_value}: ${e}")
        abuse_data = {"abuse_confidence_score": -1, "error": "${e}"}
    }

    ip_results = ip_results + [{
        "ip": ioc_value,
        "score": abuse_data.abuse_confidence_score ?? -1,
        "reports": abuse_data.total_reports ?? 0,
        "is_tor": abuse_data.full_data.data.isTor ?? False,
        "is_whitelisted": abuse_data.is_whitelisted ?? False,
        "isp": abuse_data.isp ?? "unknown",
        "country": abuse_data.country_code ?? "unknown"
    }]
}

# Summarize with LLM
summary = ""
if (len(ip_results) > 0) {
    summary = llm_run(
        prompt="""Alert Context: ${alert_context}

AbuseIPDB batch results for ${len(ip_results)} IPs:
${to_json(ip_results, 2)}

Summarize: Which IPs are most suspicious? Any patterns (same country, same ISP, all Tor)?

Return JSON (no markdown): {"high_risk_ips": ["list of IPs with score > 50"], "pattern": "one sentence summary", "overall_risk": "high|medium|low"}"""
    )
}

enrichment = {
    "ip_results": ip_results,
    "total_checked": len(ip_results),
    "ai_analysis": summary
}

return enrich_alert(input, enrichment)
```

---

## Pattern 5: Confidence Score Thresholds for Automated Disposition

Use AbuseIPDB scores as one input to automated TP/FP disposition logic. Never use AbuseIPDB as the sole signal — always combine with at least one other source.

```cy
ip = input.primary_ioc_value ?? "0.0.0.0"

abuse_result = {}
try {
    abuse_result = app::abuseipdb::lookup_ip(ip=ip, days=30)
} catch (e) {
    log("AbuseIPDB failed: ${e}")
}

score = abuse_result.abuse_confidence_score ?? -1
is_whitelisted = abuse_result.is_whitelisted ?? False
distinct_users = abuse_result.num_distinct_users ?? 0

# Automated disposition logic (combine with other enrichments)
disposition = "needs_review"

if (is_whitelisted) {
    disposition = "likely_fp"
} elif (score >= 80 and distinct_users >= 5) {
    disposition = "likely_tp"
} elif (score >= 50 and distinct_users >= 3) {
    disposition = "suspicious"
} elif (score == 0 and distinct_users == 0) {
    disposition = "no_data"
} elif (score < 25) {
    disposition = "likely_benign"
}

enrichment = {
    "ip": ip,
    "abuse_confidence_score": score,
    "distinct_reporters": distinct_users,
    "is_whitelisted": is_whitelisted,
    "auto_disposition": disposition,
    "ai_analysis": "AbuseIPDB score ${score}/100 from ${distinct_users} reporters. Auto-disposition: ${disposition}."
}

return enrich_alert(input, enrichment)
```

---

## AbuseIPDB Category Mapping for Alert Types

When building tasks that report confirmed TPs back to AbuseIPDB, map alert rule names to the most specific category IDs. See `actions-reference.md` § AbuseIPDB Category IDs for the full category table.

| Alert Pattern | AbuseIPDB Categories | IDs |
|--------------|---------------------|-----|
| SSH Brute Force | Brute-Force + SSH | `"18,22"` |
| RDP Brute Force | Brute-Force + Hacking | `"18,15"` |
| FTP Brute Force | FTP Brute-Force | `"5"` |
| Port Scan / Recon | Port Scan | `"14"` |
| SQL Injection | SQL Injection + Web App Attack | `"16,21"` |
| XSS / RFI / LFI | Web App Attack | `"21"` |
| Phishing | Phishing | `"7"` |
| Email Spam | Email Spam | `"11"` |
| DDoS / Volumetric | DDoS Attack | `"4"` |
| DNS Hijacking | DNS Compromise | `"1"` |
| Compromised Host | Exploited Host | `"20"` |
| Malicious Crawler | Bad Web Bot | `"19"` |
| IoT Botnet | IoT Targeted | `"23"` |
| Generic Malicious | Hacking | `"15"` |
