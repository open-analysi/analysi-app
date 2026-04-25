# NIST NVD Investigation Patterns

All patterns below use the **Safe Lookup Pattern** from `actions-reference.md` for calling `cve_lookup`. Refer to that file for parameter schema, response field tables, and error handling details.

## Pattern 1: CVE Enrichment Task (Standalone)

Use when a vulnerability alert contains a CVE ID and you need to enrich the alert with NVD data and an LLM-driven risk assessment.

### When to Use

- Alert `rule_name` mentions a CVE ID (e.g., "Exploit Attempt for CVE-2024-3400")
- IOCs contain entries with `type: "cve"`
- Alert title or description references a specific vulnerability

### CVE ID Extraction

CVE IDs appear in different alert fields depending on source. Extract with this fallback chain:

```cy
# Strategy 1: IOC with type "cve"
cve_ids = [ioc.value for(ioc in (input.iocs ?? [])) if(ioc.type == "cve")]
cve_id = if (len(cve_ids) > 0) { cve_ids[0] } else { "" }

# Strategy 2: primary_ioc_value (when alert is CVE-centric)
if (cve_id == "") {
    candidate = input.primary_ioc_value ?? ""
    if (startswith(candidate, "CVE-")) {
        cve_id = candidate
    }
}

# Strategy 3: Extract from rule_name using regex
if (cve_id == "") {
    cve_id = regex_extract(r"CVE-\d{4}-\d{4,}", input.rule_name ?? "") ?? ""
}
```

### Complete Cy Task Template

```cy
# === CVE Enrichment Task ===
# Extracts CVE ID from alert, looks up NVD data, assesses risk with LLM

# 1. Extract alert context
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.title ?? "unknown alert"

# 2. Extract CVE ID (multi-strategy — see CVE ID Extraction above)
cve_ids = [ioc.value for(ioc in (input.iocs ?? [])) if(ioc.type == "cve")]
cve_id = if (len(cve_ids) > 0) { cve_ids[0] } else { "" }

if (cve_id == "") {
    candidate = input.primary_ioc_value ?? ""
    if (startswith(candidate, "CVE-")) {
        cve_id = candidate
    }
}

if (cve_id == "") {
    cve_id = regex_extract(r"CVE-\d{4}-\d{4,}", input.rule_name ?? "") ?? ""
}

# 3. Early return if no CVE found
if (cve_id == "") {
    enrichment = {
        "status": "no_cve_found",
        "ai_analysis": "No CVE identifier found in alert. Skipping NVD enrichment."
    }
    return enrich_alert(input, enrichment)
}

# 4. Safe NVD lookup (see actions-reference.md § Safe Lookup Pattern)
nvd = null
try {
    nvd = app::nistnvd::cve_lookup(cve=cve_id)
    if (nvd.not_found ?? False) {
        nvd = null
    }
} catch (e) {
    log("NVD lookup failed for ${cve_id}: ${e}")
}

# 5. Handle not-found / lookup-failed case
if (nvd == null) {
    analysis = llm_run(
        prompt="""Alert Context: ${alert_context}

CVE ${cve_id} was referenced in this alert but is not found in NIST NVD.
This may indicate a recently reserved CVE or a typo.

Return JSON (no markdown): {"risk_level": "unknown", "reason": "one sentence"}"""
    )
    enrichment = {"cve_id": cve_id, "status": "not_found", "ai_analysis": analysis}
    return enrich_alert(input, enrichment)
}

# 6. Extract key metrics (see actions-reference.md § Field Access Patterns)
score = nvd.cvss_metrics.base_score ?? 0
severity = nvd.cvss_metrics.base_severity ?? "unknown"
attack_vector = nvd.cvss_metrics.attack_vector ?? "unknown"
attack_complexity = nvd.cvss_metrics.attack_complexity ?? "unknown"
privs = nvd.cvss_metrics.privileges_required ?? "unknown"
is_kev = nvd.cisa_kev != null
kev_action = nvd.cisa_kev.required_action ?? ""
kev_due = nvd.cisa_kev.due_date ?? ""

# 7. LLM risk assessment with alert context
analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

Assess CVE ${cve_id} in the context of this specific alert:
- CVSS: ${score}/10 (${severity})
- Attack Vector: ${attack_vector}, Complexity: ${attack_complexity}, Privileges: ${privs}
- CISA KEV: ${is_kev} ${if (is_kev) { "(Action: ${kev_action}, Due: ${kev_due})" } else { "" }}
- Description: ${nvd.description}

Assess:
1. How does this vulnerability relate to the alert?
2. Is this an active exploitation attempt or informational?
3. What is the patch urgency?

Return JSON (no markdown): {"relevance": "high|medium|low", "risk_level": "critical|high|medium|low", "patch_urgency": "immediate|soon|routine", "assessment": "2-3 sentence analysis"}"""
)

# 8. Enrich alert
enrichment = {
    "cve_id": cve_id,
    "cvss_score": score,
    "cvss_severity": severity,
    "attack_vector": attack_vector,
    "in_cisa_kev": is_kev,
    "cisa_required_action": kev_action,
    "cisa_due_date": kev_due,
    "description": nvd.description ?? "",
    "published_date": nvd.published_date ?? "",
    "ai_analysis": analysis
}
return enrich_alert(input, enrichment)
```

**Task creation fields:**
- `function`: `"enrichment"`
- `scope`: `"processing"`
- `app`: `"nistnvd"`
- `directive`: `"You are a vulnerability analyst assessing CVE severity and exploitation risk in the context of security alerts. Provide concise, actionable assessments."`
- `llm_config`: `{"default_model": "gpt-4o-mini", "temperature": 0.2, "max_tokens": 800}`

### data_samples for This Pattern

```json
[
  {
    "rule_name": "Exploit Attempt - CVE-2024-3400 PAN-OS Command Injection",
    "primary_ioc_value": "CVE-2024-3400",
    "iocs": [{"type": "cve", "value": "CVE-2024-3400", "description": "PAN-OS RCE"}],
    "enrichments": {}
  },
  {
    "rule_name": "Suspicious Network Connection to Known Malicious IP",
    "primary_ioc_value": "185.220.101.45",
    "iocs": [{"type": "ipv4", "value": "185.220.101.45"}],
    "enrichments": {}
  }
]
```

The first sample tests the happy path (CVE found in NVD with CISA KEV). The second tests the "no CVE found" early-return branch.

---

## Pattern 2: Multi-CVE Batch Triage

When a vulnerability scanner alert or attack chain alert lists multiple CVEs (common with Qualys, Nessus, Tenable, or attack chains like ProxyNotShell), enrich each CVE and prioritize by risk. Uses the Batch Pattern from `actions-reference.md` for the loop structure.

### Cy Task Template

```cy
alert_context = input.enrichments.alert_context_generation.ai_analysis ??
                input.rule_name ?? "unknown alert"

# Extract all CVE IOCs
cve_iocs = [ioc.value for(ioc in (input.iocs ?? [])) if(ioc.type == "cve")]

if (len(cve_iocs) == 0) {
    enrichment = {
        "status": "no_cves",
        "ai_analysis": "No CVE identifiers found in alert IOCs."
    }
    return enrich_alert(input, enrichment)
}

# Look up each CVE (see actions-reference.md § Rate Limits for throttling guidance)
cve_results = []
errors = []
kev_count = 0
max_score = 0
critical_cve = ""

for (cve_id in cve_iocs) {
    try {
        nvd = app::nistnvd::cve_lookup(cve=cve_id)
        if (nvd.not_found ?? False) {
            cve_results = cve_results + [{"cve_id": cve_id, "status": "not_found"}]
        } else {
            s = nvd.cvss_metrics.base_score ?? 0
            is_kev = if (nvd.cisa_kev != null) { True } else { False }
            if (is_kev) {
                kev_count = kev_count + 1
            }
            if (s > max_score) {
                max_score = s
                critical_cve = nvd.cve_id ?? cve_id
            }
            cve_results = cve_results + [{
                "cve_id": nvd.cve_id ?? cve_id,
                "base_score": s,
                "base_severity": nvd.cvss_metrics.base_severity ?? "unknown",
                "cisa_kev": is_kev,
                "attack_vector": nvd.cvss_metrics.attack_vector ?? "unknown",
                "description": nvd.description ?? ""
            }]
        }
    } catch (e) {
        log("Failed: ${cve_id}: ${e}")
        errors = errors + [{"cve_id": cve_id, "error": "${e}"}]
    }
}

# LLM prioritization
cve_summary = to_json(cve_results, 2)

analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

${len(cve_results)} CVEs found, ${len(errors)} lookups failed, ${kev_count} in CISA KEV.
Highest CVSS: ${critical_cve} (${max_score})

CVE Details:
${cve_summary}

Prioritize these vulnerabilities for patching. Which pose the greatest immediate risk?
Return JSON (no markdown): {"overall_risk": "critical|high|medium|low", "priority_order": ["CVE-..."], "critical_count": N, "assessment": "summary"}"""
)

enrichment = {
    "cve_results": cve_results,
    "lookup_errors": errors,
    "highest_cvss_score": max_score,
    "highest_cvss_cve": critical_cve,
    "kev_count": kev_count,
    "total_cves": len(cve_iocs),
    "ai_analysis": analysis
}
return enrich_alert(input, enrichment)
```

---

## Pattern 3: CVE + Splunk Correlation

Combine NVD lookup with Splunk event retrieval to determine if a vulnerable system was actually targeted or if the alert is informational.

### Use Case

An IDS/IPS or vulnerability scanner fires an alert mentioning a CVE. You need to:
1. Look up CVE severity from NVD
2. Query Splunk for exploit attempt logs targeting that CVE
3. Correlate to determine if this is an active exploit attempt (TP) or a scanner detection (FP)

### Cy Task Template

```cy
# === CVE + Splunk Correlation ===
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.title ?? "unknown alert"

cve_id = input.primary_ioc_value ?? ""
src_ip = input.network_info.src_ip ?? "0.0.0.0"
dest_ip = input.network_info.dest_ip ?? "0.0.0.0"

# Step 1: Safe NVD lookup (see actions-reference.md § Safe Lookup Pattern)
nvd = null
try {
    nvd = app::nistnvd::cve_lookup(cve=cve_id)
    if (nvd.not_found ?? False) {
        nvd = null
    }
} catch (e) {
    log("NVD lookup failed: ${e}")
}

score = if (nvd != null) { nvd.cvss_metrics.base_score ?? 0 } else { 0 }
severity = if (nvd != null) { nvd.cvss_metrics.base_severity ?? "unknown" } else { "unknown" }
is_kev = if (nvd != null and nvd.cisa_kev != null) { True } else { False }
cve_desc = if (nvd != null) { nvd.description ?? "" } else { "" }

# Step 2: Splunk — find exploit attempts related to this CVE
spl_query = """search index=ids_alerts OR index=proxy OR index=firewall
    "${cve_id}" OR "${src_ip}"
    earliest=-24h latest=now
    | stats count by src_ip, dest_ip, action, signature
    | sort -count
    | head 20"""

splunk_result = null
try {
    splunk_result = app::splunk::search(query=spl_query)
} catch (e) {
    log("Splunk query failed: ${e}")
}

# Step 3: LLM Correlation
splunk_summary = to_json(splunk_result ?? {"events": []}, 2)

analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

CVE ${cve_id}: CVSS ${score}/10 (${severity}), CISA KEV: ${is_kev}
Description: ${cve_desc}

Splunk events (last 24h):
${splunk_summary}

Based on the alert context, CVE details, and Splunk events:
1. Is this an active exploit attempt or informational/scanner detection?
2. What is the likely disposition (true_positive / false_positive / benign_true_positive)?
3. What immediate actions are recommended?

Return JSON (no markdown): {"disposition": "...", "confidence": "high|medium|low", "reason": "one sentence", "actions": ["action1", "action2"]}"""
)

enrichment = {
    "cve_id": cve_id,
    "base_score": score,
    "base_severity": severity,
    "cisa_kev": is_kev,
    "splunk_events_found": if (splunk_result != null) { True } else { False },
    "ai_analysis": analysis
}
return enrich_alert(input, enrichment)
```

---

## Pattern 4: CVE + Threat Intel Correlation

Combine NVD data with VirusTotal/AbuseIPDB to corroborate whether an exploit attempt is associated with known threat actors.

### Cy Task Template

```cy
cve_id = input.cve_info.cve_ids[0] ?? ""
src_ip = input.network_info.src_ip ?? input.primary_ioc_value ?? ""

alert_context = input.enrichments.alert_context_generation.ai_analysis ??
                input.rule_name ?? "unknown alert"

# Parallel lookups: CVE data + IP reputation
nvd = null
vt_data = null
abuse_data = null
cve_error = ""
vt_error = ""
abuse_error = ""

try {
    nvd = app::nistnvd::cve_lookup(cve=cve_id)
    if (nvd.not_found ?? False) {
        nvd = null
    }
} catch (e) {
    cve_error = "${e}"
}

if (src_ip != "" and src_ip != "0.0.0.0") {
    try {
        vt_data = app::virustotal::ip_reputation(ip=src_ip)
    } catch (e) {
        vt_error = "${e}"
    }

    try {
        abuse_data = app::abuseipdb::lookup_ip(ip=src_ip)
    } catch (e) {
        abuse_error = "${e}"
    }
}

# Build evidence summary for LLM
cvss_score = if (nvd != null) { nvd.cvss_metrics.base_score ?? 0 } else { 0 }
cvss_severity = if (nvd != null) { nvd.cvss_metrics.base_severity ?? "unknown" } else { "unknown" }
in_kev = if (nvd != null and nvd.cisa_kev != null) { True } else { False }

vt_malicious = vt_data.data.attributes.last_analysis_stats.malicious ?? 0
abuse_score = abuse_data.data.abuseConfidenceScore ?? 0

analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

Evidence:
- CVE: ${cve_id}, CVSS: ${cvss_score} (${cvss_severity}), CISA KEV: ${in_kev}
- Source IP: ${src_ip}
- VirusTotal: ${vt_malicious} engines flagged malicious ${if (vt_error != "") { "(lookup failed: ${vt_error})" } else { "" }}
- AbuseIPDB: confidence score ${abuse_score}% ${if (abuse_error != "") { "(lookup failed: ${abuse_error})" } else { "" }}
- CVE Description: ${if (nvd != null) { nvd.description ?? "unavailable" } else { "unavailable" }}

Correlate: Is this source IP actively exploiting ${cve_id}?
Consider: attack vector match, IP reputation, KEV status.

Return JSON (no markdown): {"verdict": "likely_exploit|possible_exploit|unlikely|insufficient_data", "confidence": "high|medium|low", "reasoning": "2-3 sentences"}"""
)

enrichment = {
    "cve_id": cve_id,
    "cvss_score": cvss_score,
    "in_cisa_kev": in_kev,
    "source_ip": src_ip,
    "vt_malicious_count": vt_malicious,
    "abuse_confidence": abuse_score,
    "ai_analysis": analysis
}
return enrich_alert(input, enrichment)
```

---

## Severity Triage Decision Tree

Use this logic to route alerts based on CVE data after enrichment:

```
CVE lookup succeeded?
├── No → Flag for manual review, risk_level = "unknown"
└── Yes
    ├── cisa_kev != null (in CISA KEV)
    │   └── CRITICAL: Active exploitation confirmed
    │       → Immediate patching required
    │       → Check due_date for compliance deadline (may be null)
    │       → Escalate if past due date
    │
    ├── cvss_metrics.base_score >= 9.0
    │   └── CRITICAL severity
    │       ├── attack_vector == "NETWORK" + attack_complexity == "LOW"
    │       │   └── Remotely exploitable from internet → highest urgency
    │       └── Otherwise → critical but requires local/adjacent access or high complexity
    │
    ├── cvss_metrics.base_score >= 7.0
    │   └── HIGH severity
    │       ├── privileges_required == "NONE" + user_interaction == "NONE"
    │       │   └── Wormable potential → escalate
    │       ├── In combination with known-malicious source IP → escalate
    │       └── Otherwise → standard high-priority patching
    │
    ├── cvss_metrics.base_score >= 4.0
    │   └── MEDIUM severity → standard patch cycle
    │
    └── cvss_metrics.base_score < 4.0
        └── LOW severity → track, no immediate action
```

### Cy Implementation

```cy
# Assumes nvd result and extracted fields from Pattern 1 (step 6)
risk_level = "unknown"
patch_urgency = "routine"
escalate = False

if (is_kev) {
    risk_level = "critical"
    patch_urgency = "immediate"
    escalate = True
} elif (score >= 9.0) {
    risk_level = "critical"
    if (attack_vector == "NETWORK" and attack_complexity == "LOW") {
        patch_urgency = "immediate"
        escalate = True
    } else {
        patch_urgency = "soon"
    }
} elif (score >= 7.0) {
    risk_level = "high"
    user_interaction = nvd.cvss_metrics.user_interaction ?? "REQUIRED"
    if (privs == "NONE" and user_interaction == "NONE") {
        patch_urgency = "soon"
        escalate = True
    } else {
        patch_urgency = "soon"
    }
} elif (score >= 4.0) {
    risk_level = "medium"
    patch_urgency = "routine"
} else {
    risk_level = "low"
    patch_urgency = "routine"
}
```

---

## TP/FP Disposition with CVE Context

Use alongside the severity tree to determine alert disposition:

```
Alert with CVE reference
├── CVE lookup succeeded
│   ├── CISA KEV = true + source IP is external + malicious reputation
│   │   └── Strong TRUE POSITIVE signal
│   │       → Correlate with Splunk for additional attack indicators
│   │
│   ├── CVSS attack_vector == "NETWORK" + alert shows network exploit attempt
│   │   └── Attack vector matches alert type → TRUE POSITIVE likely
│   │       → Check HTTP response codes (Splunk) for success/failure
│   │
│   ├── CVSS attack_vector == "LOCAL" but alert shows network traffic
│   │   └── Mismatch → possible SCANNER / FALSE POSITIVE
│   │       → Verify with payload analysis
│   │
│   └── CVE published_date is recent (< 30 days)
│       └── Zero-day / N-day exploitation attempt → high confidence TP
│
├── CVE not found in NVD
│   └── Possibly reserved/rejected CVE → cannot assess, note in enrichment
│
└── CVE lookup failed (timeout/rate limit)
    └── Continue investigation without NVD data, note degraded confidence
```

### CVSS Field Combinations for Disposition

For field value definitions and v2 vs v3.1 differences, see `actions-reference.md` § cvss_metrics Fields.

| Scenario | CVSS Indicators | Likely Disposition |
|----------|----------------|--------------------|
| Remote exploit, no auth, no interaction | `attack_vector=NETWORK`, `privileges_required=NONE`, `user_interaction=NONE` | High confidence TP if matching traffic observed |
| Local exploit requiring privileges | `attack_vector=LOCAL`, `privileges_required=HIGH` | Likely FP unless attacker already has local access |
| Scope changed + high CIA impact | `scope=CHANGED`, all impacts `HIGH` | Highest severity — can pivot to other systems |
| Network vector but high complexity | `attack_vector=NETWORK`, `attack_complexity=HIGH` | May be TP but exploitation is unreliable |

### Working with CVSS v2-only CVEs

Older CVEs may only have CVSS v2 metrics. Key differences that affect triage logic (field schema details in `actions-reference.md` § CVSS v2 Fallback):

- No `CRITICAL` severity — highest is `HIGH` (7.0–10.0), so a v2 `HIGH` may actually be critical-equivalent
- `attack_complexity` has three levels (`LOW`, `MEDIUM`, `HIGH`) instead of two
- `privileges_required`, `user_interaction`, and `scope` are absent — the wormability check in the severity tree cannot be applied
- For v2-only CVEs, rely more on description text and LLM interpretation rather than metric-based branching

### CISA KEV Triage Significance

If `cisa_kev` is not null, the vulnerability has **confirmed active exploitation in the wild**. This changes the triage calculus regardless of CVSS score:

- Treat any alert referencing a KEV CVE as at minimum HIGH priority
- Use `required_action` in SOC response recommendations — it contains CISA's mandated remediation
- `due_date` (when present) indicates the federal remediation deadline — useful as urgency proxy even for non-federal organizations
- `date_added` indicates when exploitation was confirmed — additions within the last 30 days suggest active campaigns

---

## Workflow Composition Examples

### CVE Enrichment in a Standard Triage Pipeline

```
identity → [alert_context_generation] → [nistnvd_cve_enrichment, splunk_triggering_events] → merge → [alert_detailed_analysis] → [alert_disposition]
```

The NVD lookup runs in parallel with Splunk event retrieval. Both enrich the alert before the detailed analysis task synthesizes all findings.

### Vulnerability-Specific Investigation

```
identity → [alert_context_generation] → [nistnvd_cve_enrichment] → [splunk_supporting_evidence_search] → [attack_success_determination] → [alert_disposition]
```

CVE data informs the evidence search — the LLM in `splunk_supporting_evidence_search` uses CVE context (attack vector, affected product) to generate more targeted SPL queries.

---

## Data Sample Templates

### Alert with CVE in IOCs

```json
{
    "rule_name": "Exploit Attempt - CVE-2021-44228 Log4Shell",
    "title": "Log4j RCE exploitation attempt detected",
    "severity": "critical",
    "primary_ioc_value": "185.220.101.45",
    "primary_ioc_type": "ipv4",
    "iocs": [
        {"type": "ipv4", "value": "185.220.101.45", "description": "Attacker IP"},
        {"type": "cve", "value": "CVE-2021-44228", "description": "Log4Shell"}
    ],
    "cve_info": {
        "cve_ids": ["CVE-2021-44228"]
    },
    "network_info": {
        "src_ip": "185.220.101.45",
        "dst_ip": "10.0.1.50",
        "dst_port": 8080
    },
    "enrichments": {}
}
```

### Alert with CVE as primary IOC (no cve_info)

```json
{
    "rule_name": "Vulnerability Scanner Finding",
    "title": "Critical vulnerability detected on server",
    "severity": "high",
    "primary_ioc_value": "CVE-2023-44487",
    "primary_ioc_type": "cve",
    "iocs": [
        {"type": "cve", "value": "CVE-2023-44487", "description": "HTTP/2 Rapid Reset"}
    ],
    "enrichments": {}
}
```

### Alert referencing multiple CVEs

```json
{
    "rule_name": "ProxyNotShell Exploitation Attempt",
    "title": "Exchange ProxyNotShell attack chain detected",
    "severity": "critical",
    "primary_ioc_value": "CVE-2022-41082",
    "primary_ioc_type": "cve",
    "iocs": [
        {"type": "cve", "value": "CVE-2022-41082", "description": "ProxyNotShell RCE"},
        {"type": "cve", "value": "CVE-2022-41040", "description": "ProxyNotShell SSRF"}
    ],
    "cve_info": {
        "cve_ids": ["CVE-2022-41082", "CVE-2022-41040"]
    },
    "web_info": {
        "request_url": "/autodiscover/autodiscover.json?@attacker.example/powershell&Email=autodiscover/autodiscover.json%3F@attacker.example"
    },
    "network_info": {
        "src_ip": "203.0.113.50"
    },
    "enrichments": {}
}
```
