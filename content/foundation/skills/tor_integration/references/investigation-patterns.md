# Tor Integration — Investigation Patterns

Practical triage patterns for using Tor exit node checks in SOC investigation workflows. For the base `lookup_ip` and `health_check` call syntax, see `actions-reference.md` § Cy Examples.

---

## Tor Lookup Helper

All patterns below use this shared helper to extract Tor status from a lookup result. Refer to `actions-reference.md` for parameter details and edge cases.

```cy
# Shared Tor lookup pattern — wraps the API call with error handling.
# Patterns below start AFTER this block, using the `is_tor` boolean.
tor_result = {}
try {
    tor_result = app::tor::lookup_ip(ip=ip)
} catch (e) {
    log("Tor lookup failed for ${ip}: ${e}")
    tor_result = {"results": [], "num_exit_nodes": 0}
}

is_tor = False
if (len(tor_result.results ?? []) > 0) {
    is_tor = (tor_result.results[0].is_exit_node) ?? False
}
```

---

## Pattern 1: Tor-Aware IP Enrichment Task

The most common use — enrich an alert's source IP with Tor status and feed results into LLM reasoning.

```cy
ip = input.primary_ioc_value ?? input.network_info.src_ip ?? "0.0.0.0"
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.rule_name ?? input.title ?? "unknown alert"

# --- Tor lookup (see helper above) ---
tor_result = {}
try {
    tor_result = app::tor::lookup_ip(ip=ip)
} catch (e) {
    log("Tor lookup failed for ${ip}: ${e}")
    tor_result = {"results": [], "num_exit_nodes": 0}
}

is_tor = False
if (len(tor_result.results ?? []) > 0) {
    is_tor = (tor_result.results[0].is_exit_node) ?? False
}
# --- End Tor lookup ---

tor_label = if (is_tor) { "a KNOWN Tor exit node" } else { "NOT a Tor exit node" }

analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

The source IP ${ip} is ${tor_label}.

Given this Tor status and the alert context:
1. Does Tor usage make sense for this type of activity?
2. Does it increase or decrease suspicion?

Return JSON (no markdown): {"tor_relevance": "high|medium|low", "assessment": "one sentence"}"""
)

enrichment = {
    "ip": ip,
    "is_tor_exit_node": is_tor,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

---

## Pattern 2: Multi-Source IP Corroboration (Tor + AbuseIPDB + WHOIS)

Combine Tor status with abuse reputation and network ownership for a comprehensive disposition.

```cy
ip = input.primary_ioc_value ?? input.network_info.src_ip ?? "0.0.0.0"
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.rule_name ?? "unknown alert"

# Parallel enrichment — Tor, AbuseIPDB, WHOIS
tor_result = {}
abuse_result = {}
whois_result = {}

try {
    tor_result = app::tor::lookup_ip(ip=ip)
} catch (e) {
    log("Tor lookup failed: ${e}")
    tor_result = {"results": [], "num_exit_nodes": 0}
}

try {
    abuse_result = app::abuseipdb::lookup_ip(ip=ip)
} catch (e) {
    log("AbuseIPDB lookup failed: ${e}")
    abuse_result = {}
}

try {
    whois_result = app::whois_rdap::lookup_ip(ip=ip)
} catch (e) {
    log("WHOIS lookup failed: ${e}")
    whois_result = {}
}

# Extract key fields
is_tor = False
if (len(tor_result.results ?? []) > 0) {
    is_tor = (tor_result.results[0].is_exit_node) ?? False
}
abuse_score = abuse_result.abuseConfidenceScore ?? 0
whois_org = whois_result.org ?? "unknown"
whois_country = whois_result.country ?? "unknown"

# Synthesize with LLM
analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

IP: ${ip}
- Tor exit node: ${is_tor}
- AbuseIPDB confidence score: ${abuse_score}/100
- WHOIS org: ${whois_org}, country: ${whois_country}

Assess this IP's threat level considering ALL sources together.
Is the combination of signals consistent with malicious activity related to this alert?

Return JSON (no markdown): {"verdict": "malicious|suspicious|benign", "reason": "one sentence"}"""
)

enrichment = {
    "ip": ip,
    "is_tor_exit_node": is_tor,
    "abuse_confidence_score": abuse_score,
    "whois_org": whois_org,
    "whois_country": whois_country,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

---

## Pattern 3: Tor + Splunk Event Context

Pull triggering events from Splunk and correlate with Tor status to assess whether the source IP was using Tor during the suspicious activity.

```cy
ip = input.primary_ioc_value ?? input.network_info.src_ip ?? "0.0.0.0"
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.rule_name ?? "unknown alert"

# Tor lookup
tor_result = {}
try {
    tor_result = app::tor::lookup_ip(ip=ip)
} catch (e) {
    log("Tor lookup failed: ${e}")
    tor_result = {"results": [], "num_exit_nodes": 0}
}

is_tor = False
if (len(tor_result.results ?? []) > 0) {
    is_tor = (tor_result.results[0].is_exit_node) ?? False
}

# Pull Splunk events for context
splunk_events = {}
try {
    spl_query = "search index=* src_ip=\"${ip}\" earliest=-24h | head 20"
    splunk_events = app::splunk::search(query=spl_query)
} catch (e) {
    log("Splunk search failed: ${e}")
    splunk_events = {"results": []}
}

event_count = len(splunk_events.results ?? [])

analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

IP ${ip} is ${if (is_tor) { "a Tor exit node" } else { "NOT a Tor exit node" }}.
Splunk returned ${event_count} events for this IP in the last 24h.

Events (first 20): ${splunk_events.results ?? []}

Considering the Tor status and event patterns:
1. Does the activity volume/type match expected Tor behavior?
2. Is this likely automated (brute force, scanning) or targeted?

Return JSON (no markdown): {"threat_type": "brute_force|scanning|targeted|benign", "confidence": "high|medium|low", "reason": "one sentence"}"""
)

enrichment = {
    "ip": ip,
    "is_tor_exit_node": is_tor,
    "splunk_event_count": event_count,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

---

## Pattern 4: Pre-Flight Health Check in Workflows

When Tor enrichment is part of a larger workflow, check availability first so a downed endpoint doesn't block the pipeline. Uses `health_check` — see `actions-reference.md` § Action: health_check for the response schema.

```cy
tor_healthy = False
try {
    health = app::tor::health_check()
    tor_healthy = health.healthy ?? False
} catch (e) {
    log("Tor health check failed: ${e}")
}

ip = input.primary_ioc_value ?? "0.0.0.0"
is_tor = False

if (tor_healthy) {
    try {
        tor_result = app::tor::lookup_ip(ip=ip)
        if (len(tor_result.results ?? []) > 0) {
            is_tor = (tor_result.results[0].is_exit_node) ?? False
        }
    } catch (e) {
        log("Tor lookup failed despite healthy check: ${e}")
    }
} else {
    log("Tor integration unavailable — skipping Tor enrichment")
}

enrichment = {
    "ip": ip,
    "is_tor_exit_node": is_tor,
    "tor_data_available": tor_healthy,
    "ai_analysis": ""
}

return enrich_alert(input, enrichment)
```

---

## Decision Tree: Tor IP Disposition

Use this logic when a source IP is confirmed as a Tor exit node:

```
Is IP a Tor exit node?
├─ NO → Tor is not a factor. Continue with standard IP enrichment.
└─ YES → What type of alert?
   ├─ Authentication (login, brute force, credential stuffing)
   │  ├─ Multiple failed logins → HIGH risk. Tor + failed auth = likely attack.
   │  ├─ Successful login from Tor (user never used Tor before) → HIGH risk. Account compromise.
   │  └─ Successful login from Tor (user has Tor history) → MEDIUM. May be legitimate privacy user.
   │
   ├─ Web application attack (SQLi, XSS, path traversal)
   │  └─ Tor + web attack signature → HIGH risk. Attacker hiding origin.
   │
   ├─ Scanning / Reconnaissance
   │  └─ Tor + port scan or vuln scan → MEDIUM. Common Tor abuse, but low impact.
   │
   ├─ Data exfiltration / C2 communication
   │  └─ Internal host connecting TO Tor → HIGH risk. Possible compromised host.
   │
   └─ Informational / low-severity
      └─ Tor alone doesn't elevate low-severity alerts. Note it and move on.
```

### Key Insight: Direction Matters

- **Inbound from Tor** (external Tor IP → your network): Attacker anonymizing their source. Common for brute force, credential stuffing, web attacks.
- **Outbound to Tor** (internal host → Tor network): Potential data exfiltration, C2 callback, or compromised host. Often higher severity than inbound.

The `lookup_ip` action checks if an IP is a Tor *exit* node (outbound endpoint of the Tor network). For outbound-to-Tor detection, check if the *destination* IP is a known Tor entry/guard node — this requires a different data source (not covered by this integration; see `actions-reference.md` § Known Limitations).

---

## IPv6 Handling

Alerts may contain IPv6 source IPs. The Tor exit list is IPv4-only (see `actions-reference.md` § Known Limitations), so passing an IPv6 address to `lookup_ip` returns a misleading `false`. Guard against this:

```cy
ip = input.primary_ioc_value ?? input.network_info.src_ip ?? "0.0.0.0"

# Skip Tor check for IPv6 — the exit list only covers IPv4
tor_checked = False
is_tor = False
if (is_ipv4(ip)) {
    tor_checked = True
    try {
        tor_result = app::tor::lookup_ip(ip=ip)
        if (len(tor_result.results ?? []) > 0) {
            is_tor = (tor_result.results[0].is_exit_node) ?? False
        }
    } catch (e) {
        log("Tor lookup failed: ${e}")
    }
} else {
    log("Skipping Tor check for non-IPv4 address: ${ip}")
}

enrichment = {
    "ip": ip,
    "is_tor_exit_node": is_tor,
    "tor_check_performed": tor_checked,
    "ai_analysis": ""
}

return enrich_alert(input, enrichment)
```

The `tor_check_performed` field lets downstream tasks distinguish "not a Tor node" from "couldn't check."

---

## Workflow Composition Tips

### Where Tor Fits in a Pipeline

Tor enrichment is a fast, lightweight check (~800ms) that should run early in the enrichment phase, typically in parallel with other IP reputation lookups:

```
[identity] → [alert_context_generation] → [tor_ip_check, abuseipdb_lookup, whois_lookup] → [merge] → [disposition_analysis]
```

### Batch and Scale Considerations

- **Single alert**: One `lookup_ip` call per alert is fine. At ~800ms, it won't bottleneck the pipeline.
- **Burst of alerts**: Each alert triggers its own task execution, so lookups happen in parallel across alerts naturally. No special batching needed.
- **Multiple IPs per alert**: Use comma-separated batch mode (see `actions-reference.md` § Batch lookup) to check src and dst IPs in a single call rather than two sequential calls.
- **No client-side rate limit** is enforced, but the upstream Tor Project endpoint is a shared public resource. If you're processing hundreds of alerts per minute, consider caching the exit node list locally or using `health_check` to verify the endpoint hasn't started throttling.

### Combining Tor with Other Enrichments

| Combination | Signal strength | Interpretation |
|---|---|---|
| Tor + AbuseIPDB score > 80 | Strong | Known bad actor using anonymization |
| Tor + AbuseIPDB score < 20 | Moderate | Tor exit node not widely reported — possible fresh node or privacy user |
| Tor + WHOIS shows hosting provider | Strong | Likely dedicated Tor relay, not a compromised residential host |
| Tor + Splunk shows many failed logins | Strong | Brute force via Tor — classic attack pattern |
| Tor + single successful login | High priority | Investigate immediately — possible account takeover via anonymous access |
