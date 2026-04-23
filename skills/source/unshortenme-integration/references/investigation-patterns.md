# Investigation Patterns: URL Expansion in Phishing Triage

## Pattern 1: Phishing Alert URL Expansion Task

The core use case — extract shortened URLs from a phishing alert, expand them, and assess suspicion.

### Decision Tree

```
Alert contains URL IOC?
├── No → Skip URL expansion, return "not applicable"
└── Yes → Is URL from a known shortener domain?
    ├── No → Skip expansion (don't waste rate-limited calls)
    └── Yes → Call unshorten_url()
        ├── Success → Compare resolved domain to expected context
        │   ├── Domain is known-malicious or mismatched → Flag suspicious
        │   └── Domain looks benign → Note as low-risk, continue triage
        └── Error →
            ├── "Unknown Error!" → Treat as suspicious (expired/taken-down link)
            ├── "Invalid Short URL" → Malformed, note and move on
            └── Other error → Log, fall back to raw URL for downstream enrichment
```

### Cy Task Template: URL Expansion for Phishing Triage

The shortener pre-filter below uses the canonical domain list from `actions-reference.md` § Rate Limit Management. Keep that list as the single source of truth.

```cy
# ── Input extraction ──
url = input.primary_ioc_value ?? ""
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.title ?? "unknown alert"

if (url == "") {
    enrichment = {
        "status": "skipped",
        "reason": "no URL IOC in alert",
        "ai_analysis": "No URL found — URL expansion not applicable to this alert."
    }
    return enrich_alert(input, enrichment)
}

# ── Pre-filter: only expand known shortener domains ──
# Canonical list maintained in actions-reference.md § Rate Limit Management
is_shortened = False
shortener_domains = [
    "bit.ly", "tinyurl.com", "t.co", "goo.gl",
    "ow.ly", "is.gd", "buff.ly", "rebrand.ly",
    "short.io", "cutt.ly", "rb.gy", "t.ly",
    "surl.li", "tiny.cc", "shorturl.at"
]
for (domain in shortener_domains) {
    found = regex_match(domain, url)
    if (found) {
        is_shortened = True
    }
}

if (not is_shortened) {
    enrichment = {
        "status": "skipped",
        "original_url": url,
        "reason": "URL is not from a known shortener domain",
        "ai_analysis": "URL does not appear to be shortened — no expansion needed. Proceed with direct URL/domain reputation checks."
    }
    return enrich_alert(input, enrichment)
}

# ── Expand the URL ──
resolved_url = ""
expansion_error = ""
remaining_calls = -1

try {
    result = app::unshortenme::unshorten_url(url=url)
    resolved_url = result.resolved_url ?? url
    remaining_calls = result.remaining_calls ?? -1
} catch (e) {
    expansion_error = "${e}"
    resolved_url = url
}

url_changed = resolved_url != url and resolved_url != ""

# ── LLM assessment ──
analysis = ""
if (url_changed) {
    analysis = llm_run(
        prompt="""Alert Context: ${alert_context}

        A shortened URL from a phishing alert was expanded:
        - Original shortened URL: ${url}
        - Resolved destination: ${resolved_url}

        Assess suspicion level:
        1. Does the destination domain match what the alert context suggests?
        2. Does the URL path contain suspicious patterns (login, verify, account, .exe, .zip)?
        3. Is the domain a known brand impersonation or lookalike?

        Return JSON (no markdown): {"suspicious": true/false, "risk_level": "high/medium/low", "reason": "one sentence"}"""
    )
} elif (expansion_error != "") {
    analysis = llm_run(
        prompt="""Alert Context: ${alert_context}

        A shortened URL could not be expanded:
        - URL: ${url}
        - Error: ${expansion_error}

        In phishing triage, an unresolvable shortened URL is often suspicious — the link
        may have been taken down after abuse reports or is deliberately evasive.

        Return JSON (no markdown): {"suspicious": true/false, "risk_level": "high/medium/low", "reason": "one sentence"}"""
    )
}

enrichment = {
    "original_url": url,
    "resolved_url": resolved_url,
    "url_changed": url_changed,
    "expansion_error": expansion_error,
    "remaining_api_calls": remaining_calls,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

---

## Pattern 2: Multi-Source URL Corroboration

After expanding a URL, chain with other integrations to build a full picture of the destination.

### Workflow Sequence

```
[URL Expansion] → [Global DNS on resolved domain] → [WHOIS RDAP on resolved domain] → [LLM Synthesis]
```

### Cy Task Template: URL Expansion + DNS + WHOIS

```cy
url = input.primary_ioc_value ?? ""
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.title ?? "unknown alert"

if (url == "") {
    enrichment = {
        "status": "skipped",
        "ai_analysis": "No URL IOC — skipping URL investigation pipeline."
    }
    return enrich_alert(input, enrichment)
}

# ── Step 1: Expand shortened URL ──
resolved_url = url
expansion_worked = False
try {
    expand_result = app::unshortenme::unshorten_url(url=url)
    resolved_url = expand_result.resolved_url ?? url
    expansion_worked = True
} catch (e) {
    log("URL expansion failed: ${e}")
}

# ── Step 2: Extract domain from resolved URL ──
# Use regex to pull domain from the resolved URL
domain = regex_extract(r"https?://([^/]+)", resolved_url) ?? ""
if (domain == "") {
    domain = regex_extract(r"^([^/]+)", resolved_url) ?? ""
}

# ── Step 3: DNS resolution on destination domain ──
dns_result = {}
if (domain != "") {
    try {
        dns_result = app::global_dns::dns_lookup(domain=domain)
    } catch (e) {
        log("DNS lookup failed for ${domain}: ${e}")
    }
}

# ── Step 4: WHOIS on destination domain's IP ──
whois_result = {}
resolved_ip = dns_result.ip ?? ""
if (resolved_ip != "") {
    try {
        whois_result = app::whois_rdap::ip_lookup(ip=resolved_ip)
    } catch (e) {
        log("WHOIS lookup failed for ${resolved_ip}: ${e}")
    }
}

# ── Step 5: LLM synthesis ──
analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

    URL investigation results for a phishing alert:
    - Original URL: ${url}
    - Resolved URL: ${resolved_url}
    - URL was expanded: ${expansion_worked}
    - Destination domain: ${domain}
    - DNS result: ${to_json(dns_result)}
    - WHOIS info: ${to_json(whois_result)}

    Synthesize these findings:
    1. Is the destination suspicious? (newly registered domain, hosting in unusual geo, known phishing infra)
    2. Does the redirect chain suggest evasion?
    3. What is the overall risk level for this URL?

    Return JSON (no markdown): {"verdict": "malicious/suspicious/benign", "risk_level": "high/medium/low", "reason": "2-3 sentences with specific evidence"}"""
)

enrichment = {
    "original_url": url,
    "resolved_url": resolved_url,
    "destination_domain": domain,
    "resolved_ip": resolved_ip,
    "dns_data": dns_result,
    "whois_data": whois_result,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

---

## Pattern 3: Batch URL Triage with Rate Limit Awareness

When an alert contains multiple URLs (e.g., phishing email with several links), prioritize which to expand given the 10/hour limit.

### Cy Task Template: Prioritized Batch Expansion

```cy
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.title ?? "unknown alert"

# Extract all URL IOCs from the alert
iocs = input.iocs ?? []
url_iocs = []
for (ioc in iocs) {
    if (ioc.type ?? "" == "url") {
        url_iocs = url_iocs + [ioc.value ?? ""]
    }
}

if (len(url_iocs) == 0) {
    enrichment = {
        "status": "skipped",
        "ai_analysis": "No URL IOCs found in alert."
    }
    return enrich_alert(input, enrichment)
}

# ── Check API health and remaining budget ──
api_available = False
try {
    health = app::unshortenme::health_check()
    api_available = health.healthy ?? False
} catch (e) {
    log("unshorten.me health check failed: ${e}")
}

if (not api_available) {
    enrichment = {
        "status": "error",
        "reason": "unshorten.me API unavailable",
        "urls_found": url_iocs,
        "ai_analysis": "URL expansion service is unavailable. Proceed with raw URLs for domain/IP enrichment."
    }
    return enrich_alert(input, enrichment)
}

# ── Expand URLs (up to 3 to conserve rate limit) ──
max_expansions = 3
expanded = []
errors = []
remaining = -1

i = 0
done = False
while (i < len(url_iocs) and i < max_expansions and not done) {
    url = url_iocs[i]
    try {
        result = app::unshortenme::unshorten_url(url=url)
        remaining = result.remaining_calls ?? 0
        expanded = expanded + [{
            "original": url,
            "resolved": result.resolved_url ?? url,
            "changed": (result.resolved_url ?? url) != url
        }]
        # Stop if rate limit nearly exhausted
        if (remaining <= 1) {
            log("Rate limit nearly exhausted (${remaining} remaining), stopping expansion")
            done = True
        }
    } catch (e) {
        errors = errors + [{"url": url, "error": "${e}"}]
    }
    i = i + 1
}

# ── LLM synthesis of all expanded URLs ──
analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

    Batch URL expansion results from a phishing alert:
    - URLs found: ${len(url_iocs)}
    - URLs expanded: ${len(expanded)}
    - Expansion errors: ${len(errors)}
    - Expanded URLs: ${to_json(expanded)}
    - Errors: ${to_json(errors)}

    Assess the overall URL landscape:
    1. Do any resolved URLs point to suspicious destinations?
    2. Do the URLs share infrastructure (same domain/registrar)?
    3. Are unresolvable URLs (errors) themselves suspicious?

    Return JSON (no markdown): {"verdict": "malicious/suspicious/benign", "suspicious_urls": ["list of suspicious resolved URLs"], "reason": "2-3 sentences"}"""
)

enrichment = {
    "urls_found": len(url_iocs),
    "expanded": expanded,
    "errors": errors,
    "remaining_api_calls": remaining,
    "ai_analysis": analysis
}

return enrich_alert(input, enrichment)
```

---

## Pattern 4: Workflow Composition

Compose URL expansion as a node in a larger phishing investigation workflow.

### Recommended Workflow DAG

```
[identity] → [alert_context_generation] → [url_expansion_task] → [global_dns_enrichment] → [whois_enrichment] → [alert_disposition]
```

### Compose via Analysi Workflow API

```
compose_workflow(
    name="Phishing URL Triage",
    description="Expand shortened URLs, resolve DNS, check WHOIS, and determine disposition",
    composition=["identity", "alert_context_generation", "url_expansion", ["global_dns_enrichment", "whois_enrichment"], "merge", "alert_disposition"]
)
```

The parallel step `["global_dns_enrichment", "whois_enrichment"]` runs DNS and WHOIS lookups concurrently on the resolved URL's domain/IP, then merges results before final disposition.

---

## Interpreting Results for TP/FP Decisions

### Signals Pointing to True Positive (Phishing)

| Signal | Evidence | Weight |
|---|---|---|
| Shortened URL resolves to login/credential page | `resolved_url` contains `/login`, `/verify`, `/account`, `/signin` | High |
| Domain is a brand lookalike | `resolved_url` domain mimics a known brand (e.g., `paypa1.com`) | High |
| URL expansion fails with `Unknown Error!` | Short link was taken down (possibly after abuse report) | Medium |
| Newly registered domain | WHOIS shows creation date < 30 days old | High |
| Domain hosted in unexpected geography | WHOIS/DNS geo doesn't match claimed sender's org | Medium |

### Signals Pointing to False Positive (Benign)

| Signal | Evidence | Weight |
|---|---|---|
| Resolves to known legitimate service | `resolved_url` is google.com, microsoft.com, etc. | High |
| URL matches sender's organization | Company sends emails with their own shortener | Medium |
| Domain has long registration history | WHOIS shows 5+ years of registration | Medium |
| URL is a marketing tracker | Resolves to email marketing platform (mailchimp, hubspot) | Medium |

### Disposition Logic

```
IF resolved domain is known-malicious OR brand lookalike:
    → TRUE POSITIVE (high confidence)
ELIF expansion failed AND alert has other phishing indicators:
    → TRUE POSITIVE (medium confidence)
ELIF resolved domain is legitimate AND matches sender context:
    → FALSE POSITIVE (high confidence)
ELSE:
    → NEEDS REVIEW (escalate to analyst)
```
