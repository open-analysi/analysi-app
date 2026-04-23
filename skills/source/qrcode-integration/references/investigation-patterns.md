# QR Code Investigation Patterns

## Quishing Investigation Decision Tree

```
Alert arrives (phishing with image/attachment)
│
├─ Does alert contain image attachments or embedded images?
│  ├─ NO → Skip QR analysis, proceed with standard phishing triage
│  └─ YES → Decode QR code(s) from base64 image data
│           │
│           ├─ Result is null
│           │  → Log and continue standard phishing triage
│           │    (see actions-reference.md § Return Value for null semantics)
│           │
│           └─ QR decoded successfully → Analyze payload
│              │
│              ├─ Payload is a URL
│              │  ├─ Is URL shortened? (bit.ly, tinyurl, etc.)
│              │  │  ├─ YES → Unshorten with unshortenme
│              │  │  └─ NO → Use URL directly
│              │  │
│              │  ├─ Extract domain from URL
│              │  │  ├─ DNS resolve domain → get IP(s)
│              │  │  ├─ Check IP against Tor exit nodes
│              │  │  ├─ WHOIS lookup on IP
│              │  │  └─ Check MX/TXT records on domain (SPF/DKIM/DMARC)
│              │  │
│              │  └─ LLM analysis: Is this URL suspicious?
│              │     Inputs: domain age, Tor status, WHOIS org, DNS records, URL path
│              │
│              ├─ Payload is plain text (not URL)
│              │  → LLM analysis: Is this text part of a social engineering scheme?
│              │
│              └─ Payload is other (vCard, WiFi config, etc.)
│                 → Flag as unusual, pass to LLM for contextual analysis
```

---

## Pattern 1: Full Quishing Triage Task

The primary pattern — decode QR, unshorten if needed, resolve DNS, check Tor/WHOIS, and produce a risk assessment via LLM.

**Prerequisite:** Apply the canonical decode preamble from `actions-reference.md` § Cy Example — Basic Decode first. It handles: extract `image_b64` from `input.attachments[0].content_base64`, guard on empty, call `decode_qr_code`, handle errors and null. After the preamble, `decoded` holds the QR payload string. The code below picks up from there, adding `alert_context` extraction and multi-integration URL analysis.

```cy
# === Context extraction (add before the decode preamble) ===
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.title ?? "unknown alert"

# === After decode preamble: `decoded` is a non-null string ===

# === URL analysis (if payload is a URL) ===
is_url = regex_match(r"^https?://", decoded ?? "")
url_intel = {}

if (is_url) {
    final_url = decoded

    # Unshorten if it looks like a short URL
    is_short = regex_match(r"(bit\.ly|tinyurl|t\.co|goo\.gl|ow\.ly|is\.gd|buff\.ly|rebrand\.ly|short\.io)", decoded ?? "")
    if (is_short) {
        try {
            unshortened = app::unshortenme::unshorten_url(url=decoded)
            final_url = unshortened.resolved_url ?? decoded
            url_intel.original_short_url = decoded
            url_intel.unshortened_url = final_url
        } catch (e) {
            log("Unshorten failed: ${e}")
            url_intel.unshorten_error = "${e}"
        }
    }

    # Extract domain from URL
    domain = regex_extract(r"https?://([^/:\?]+)", final_url ?? "")

    if (domain != "") {
        # DNS resolution
        try {
            dns_result = app::global_dns::resolve_domain(domain=domain)
            url_intel.dns = dns_result
            resolved_ip = dns_result.addresses[0] ?? ""

            if (resolved_ip != "") {
                # Tor exit node check
                try {
                    tor_result = app::tor::lookup_ip(ip=resolved_ip)
                    url_intel.tor_check = tor_result
                } catch (e) {
                    log("Tor check failed: ${e}")
                }

                # WHOIS lookup
                try {
                    whois_result = app::whois_rdap::whois_ip(ip=resolved_ip)
                    url_intel.whois = whois_result
                } catch (e) {
                    log("WHOIS failed: ${e}")
                }
            }
        } catch (e) {
            log("DNS resolve failed: ${e}")
            url_intel.dns_error = "${e}"
        }
    }
}

# === LLM risk assessment ===
analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

A QR code was found in an email attachment. Decoded payload:
${decoded}

URL intelligence gathered:
${to_json(url_intel, 2)}

Analyze this for quishing (QR-based phishing):
1. Is the decoded URL/payload suspicious?
2. Do the DNS/WHOIS/Tor results indicate malicious infrastructure?
3. What is the risk level (high/medium/low)?

Return JSON (no markdown): {"verdict": "malicious|suspicious|benign", "risk_level": "high|medium|low", "reason": "one sentence explanation"}"""
)

# === Return enriched alert ===
return enrich_alert(input, {
    "decoded_data": decoded,
    "is_url": is_url,
    "url_intel": url_intel,
    "ai_analysis": analysis
})
```

---

## Pattern 2: Multi-Attachment Scan with URL Expansion

Scan all attachments, decode QR codes, expand shortened URLs, and summarize findings.

**Prerequisite:** This extends the canonical batch loop from `actions-reference.md` § Cy Example — Batch Decode. The base loop iterates `input.attachments`, decodes each, and collects results. The code below shows **only the URL expansion and LLM summarization that this pattern adds** — splice the expansion block into the batch loop's `if (decoded != null)` body.

```cy
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.title ?? "unknown alert"

# Inside the batch decode loop's `if (decoded != null)` block,
# replace the simple results accumulation with:
finding = {
    "filename": att.filename ?? "unknown",
    "decoded_data": decoded,
    "is_url": regex_match(r"^https?://", decoded ?? "")
}

# URL expansion — the unique addition
if (finding.is_url) {
    try {
        expanded = app::unshortenme::unshorten_url(url=decoded)
        finding.expanded_url = expanded.resolved_url ?? decoded
    } catch (e) {
        finding.expanded_url = decoded
        log("Unshorten failed: ${e}")
    }
}

findings = findings + [finding]
```

After the batch loop completes, add LLM summarization:

```cy
# LLM summary of all findings
analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

Scanned ${len(attachments)} attachment(s) for QR codes.
Found ${len(findings)} QR code(s):
${to_json(findings, 2)}

Summarize findings and assess quishing risk.
Return JSON (no markdown): {"total_qr_found": <n>, "urls_found": [<list>], "risk_level": "high|medium|low", "summary": "one sentence"}"""
)

return enrich_alert(input, {
    "attachments_scanned": len(attachments),
    "qr_codes_found": len(findings),
    "findings": findings,
    "ai_analysis": analysis
})
```

---

## Pattern 3: Sender Domain Verification (Complement to QR Decode)

After decoding a QR URL, verify whether the email sender's domain has proper mail authentication — a missing SPF/DMARC record strongly suggests spoofing. This task runs in parallel with URL analysis in workflow compositions.

```cy
sender_email = input.email_info.sender ?? ""
sender_domain = regex_extract(r"@(.+)$", sender_email)

if (sender_domain == "") {
    return enrich_alert(input, {
        "status": "skipped",
        "ai_analysis": "No sender domain to verify."
    })
}

mail_intel = {"domain": sender_domain}

# MX records — does this domain actually send mail?
try {
    mx = app::global_dns::get_mx_records(domain=sender_domain)
    mail_intel.mx_records = mx
} catch (e) {
    mail_intel.mx_error = "${e}"
}

# TXT records — SPF, DKIM, DMARC
try {
    txt = app::global_dns::get_txt_records(domain=sender_domain)
    mail_intel.txt_records = txt
} catch (e) {
    mail_intel.txt_error = "${e}"
}

alert_context = input.enrichments.alert_context_generation.ai_analysis ?? "unknown alert"

analysis = llm_run(
    prompt="""Alert Context: ${alert_context}

Verify sender domain mail authentication for: ${sender_domain}

Mail infrastructure data:
${to_json(mail_intel, 2)}

Check for:
1. Does the domain have MX records (can it send mail)?
2. Is SPF configured?
3. Is DMARC configured?
4. Any red flags (newly registered, no mail infra, permissive SPF)?

Return JSON (no markdown): {"has_mx": true|false, "has_spf": true|false, "has_dmarc": true|false, "suspicious": true|false, "reason": "one sentence"}"""
)

return enrich_alert(input, {
    "sender_domain": sender_domain,
    "mail_intel": mail_intel,
    "ai_analysis": analysis
})
```

---

## Workflow Composition Example

Chain QR decode → URL analysis → sender verification into a workflow:

```
["identity", "qr_decode_task", ["url_analysis_task", "sender_verification_task"], "merge", "quishing_disposition_task"]
```

- **qr_decode_task** — Uses the Basic Decode pattern from `actions-reference.md` as a standalone lightweight decode task. Stores decoded payload in enrichments.
- **url_analysis_task** — Reads decoded URL from enrichments, runs DNS/WHOIS/Tor checks (the URL analysis portion of Pattern 1 above).
- **sender_verification_task** — Pattern 3. Runs in parallel with URL analysis.
- **quishing_disposition_task** — LLM reads all enrichments, produces final TP/FP verdict.

For batch-processing workflows (scheduled scans of quarantined emails), consider calling `app::qrcode::health_check()` at the start of the workflow to confirm the decoder is available before processing a large queue. See `actions-reference.md` § Action: `health_check` for the Cy example.

---

## TP/FP Disposition Signals

When the LLM produces a final verdict, these signals help distinguish true positive quishing from benign QR codes:

**Strong TP indicators:**
- QR URL domain registered < 30 days ago (WHOIS)
- QR URL resolves to Tor exit node
- Shortened URL hides the actual destination
- Sender domain has no SPF/DMARC records
- QR URL path mimics a login page (`/signin`, `/verify`, `/account`)
- Domain uses typosquatting (e.g., `micros0ft.com`, `g00gle.com`)

**Strong FP indicators:**
- QR URL points to a well-known SaaS domain (zoom.us, teams.microsoft.com)
- Domain has valid SPF + DMARC + DKIM
- Domain registered > 1 year ago with reputable registrar
- URL is a known internal company domain
- QR code contains plain text (not a URL) such as a WiFi SSID or vCard

**Ambiguous — needs further investigation:**
- QR URL goes to a URL shortener and unshortening fails
- Domain resolves but WHOIS data is privacy-protected
- URL contains both legitimate and suspicious path components
