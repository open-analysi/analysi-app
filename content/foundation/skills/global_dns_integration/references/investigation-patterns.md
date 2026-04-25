# Global DNS — Investigation Patterns

Practical triage patterns that chain Global DNS actions together and with other Analysi integrations. Each pattern includes decision guidance, a Cy task template, and interpretation notes.

## Table of Contents

- [Pick the First DNS Pivot](#pick-the-first-dns-pivot)
- [Normalize PTR Inputs](#normalize-ptr-inputs-before-reverse-lookup)
- [Pattern 1: Phishing Domain Full Profile](#pattern-1-phishing-domain-full-profile)
- [Pattern 2: IP-to-Infrastructure Mapping](#pattern-2-ip-to-infrastructure-mapping)
- [Pattern 3: Safe Small-Batch Enrichment](#pattern-3-safe-small-batch-enrichment)
- [Pattern 4: Lateral Movement DNS Verification](#pattern-4-lateral-movement-dns-verification)
- [Pattern 5: DKIM Key Verification](#pattern-5-dkim-key-verification)
- [Corroboration Chains](#corroboration-chains)
- [TP/FP Disposition Signals from DNS](#tpfp-disposition-signals-from-dns)
- [High-Signal Interpretation Notes](#high-signal-interpretation-notes)

---

## Pick the First DNS Pivot

| Alert clue | Start with | Immediate follow-up | Why it helps |
|---|---|---|---|
| Suspicious hostname, URL, or phishing landing page | `resolve_domain` (`A`, then `CNAME` if useful) | `get_ns_records`, `get_soa_record` | Maps the host and zone delegation quickly |
| Suspicious sender or return-path domain | `get_mx_records`, `get_txt_records` | `resolve_domain` on the domain or returned mail hosts | Shows whether the domain looks mail-capable and what auth/provider strings exist |
| Suspicious IP from firewall, EDR, or lateral movement | `reverse_lookup` | `resolve_domain` on the PTR hostname | Converts a bare IP into a hostname/provider pivot |
| Cluster of related lookalike domains | `get_ns_records`, `get_soa_record` | `resolve_domain` on the same set | Shared NS/SOA fields are often more stable clustering pivots than A records |

---

## Normalize PTR Inputs Before Reverse Lookup

Use this only when the alert does not already provide a clean IP string. The goal is to turn a URL or IPv4 CIDR fallback into a plain IP before calling `reverse_lookup`. For IPv6 literals, prefer normalized alert fields rather than string surgery.

```cy
network_info = input.network_info ?? {}
web_info = input.web_info ?? {}
ptr_input = network_info.dest_ip ?? network_info.src_ip ?? ""

if (ptr_input == "") {
    raw = input.primary_ioc_value ?? web_info.url ?? ""

    if raw.startswith("http://") or raw.startswith("https://") {
        url_parts = raw.split("/")
        if len(url_parts) > 2 {
            raw = url_parts[2]
        }
    }

    if "/" in raw and "." in raw {
        raw = raw.split("/")[0]
    }

    if ":" in raw and "." in raw {
        raw = raw.split(":")[0]
    }

    if "." in raw {
        ptr_input = raw
    }
}
```

---

## Pattern 1: Phishing Domain Full Profile

**When to use:** Alert involves a suspicious sender domain, phishing URL domain, or impersonation attempt.

**Actions chained:** `resolve_domain` → `get_mx_records` → `get_txt_records` (apex + `_dmarc.`) → `get_ns_records` → `get_soa_record`

**Decision tree:**

1. Does the domain resolve? (`resolve_domain`)
   - `NXDOMAIN` → Domain doesn't exist. If it appeared in an email, likely spoofed or already taken down. **Flag as suspicious.**
   - Resolves → Continue to step 2.
2. Does it have MX records? (`get_mx_records`)
   - No MX → Domain doesn't receive email. Unusual for a "business" sending you email. **Elevated suspicion.**
   - MX points to known providers (Google Workspace, Microsoft 365, Proofpoint) → Lowers suspicion.
   - MX points to obscure/self-hosted server → **Elevated suspicion.**
3. Does it have SPF and DMARC? (`get_txt_records` on apex + `_dmarc.` subdomain)
   - SPF with `-all` + DMARC `p=reject` → Well-configured, harder to spoof. More likely legitimate.
   - SPF with `~all` or `?all` + DMARC `p=none` → Permissive. Spoofing is easier.
   - No SPF + No DMARC → **Strong phishing indicator.** Legitimate domains almost always have at least SPF.
   - If the sender is a subdomain (e.g., `mail.example.com`) and `_dmarc.mail.example.com` returns no record, also check `_dmarc.example.com` — per RFC 7489, evaluators fall back to the organizational domain for DMARC policy.
4. What nameservers host it? (`get_ns_records`)
   - Major DNS providers (Cloudflare, Route53, Google) → Neutral.
   - Free/bulletproof hosting providers → **Red flag.**
   - Single nameserver → Possibly throwaway infrastructure.
5. Zone metadata? (`get_soa_record`)
   - Very low `minimum` TTL (≤60s) → Possible fast-flux. **Elevated suspicion.** (`minimum` is negative-cache TTL; `serial` is a zone version counter — neither indicates domain age.)
   - `rname` can help correlate multiple suspicious domains under the same operator.

**Cy task template:**

```cy
domain = alert["sender_domain"]
if domain == null {
    domain = alert["domain"]
}

profile = {"domain": domain}

// Step 1: Resolve to IPs
try {
    resolve = app::global_dns::resolve_domain(domain=domain)
    profile["ips"] = resolve["records"]
    profile["resolves"] = true
} catch e {
    profile["resolves"] = false
    profile["resolve_error"] = str(e)
}

// Step 2: MX records
try {
    mx = app::global_dns::get_mx_records(domain=domain)
    mail_hosts = []
    for rec in mx["mx_records"] {
        mail_hosts = mail_hosts + [rec["exchange"]]
    }
    profile["mx_servers"] = mail_hosts
    profile["has_mx"] = true
} catch e {
    profile["has_mx"] = false
}

// Step 3: SPF (from apex TXT)
try {
    txt = app::global_dns::get_txt_records(domain=domain)
    profile["spf"] = "NOT_FOUND"
    for record in txt["txt_records"] {
        if "v=spf1" in record {
            profile["spf"] = record
        }
    }
} catch e {
    profile["spf"] = "ERROR"
}

// Step 4: DMARC — check _dmarc.{domain}, fall back to org domain if subdomain
try {
    dmarc = app::global_dns::get_txt_records(domain="_dmarc." + domain)
    profile["dmarc"] = "NOT_FOUND"
    for record in dmarc["txt_records"] {
        if "v=DMARC1" in record {
            profile["dmarc"] = record
        }
    }
} catch e {
    profile["dmarc"] = "NOT_FOUND"
}

// DMARC org-domain fallback: if domain has 3+ labels and no DMARC was found,
// try the organizational domain. This heuristic works for standard TLDs
// (e.g., mail.example.com → example.com) but may be wrong for multi-label
// public suffixes (e.g., example.co.uk). When in doubt, inspect NS records
// to identify the actual zone boundary.
if profile["dmarc"] == "NOT_FOUND" {
    parts = domain.split(".")
    if len(parts) >= 3 {
        org_domain = ".".join(parts[1:])
        try {
            dmarc_org = app::global_dns::get_txt_records(domain="_dmarc." + org_domain)
            for record in dmarc_org["txt_records"] {
                if "v=DMARC1" in record {
                    profile["dmarc"] = record
                    profile["dmarc_source"] = "_dmarc." + org_domain
                }
            }
        } catch e {
            // Org-domain DMARC fallback failure is non-critical
        }
    }
}

// Step 5: CNAME check — if a CNAME exists, note the alias target for further pivoting
try {
    cname = app::global_dns::resolve_domain(domain=domain, record_type="CNAME")
    profile["cname_target"] = cname["records"]
} catch e {
    // No CNAME is normal for apex domains
}

// Step 6: Nameservers
try {
    ns = app::global_dns::get_ns_records(domain=domain)
    profile["nameservers"] = ns["nameservers"]
} catch e {
    profile["nameservers"] = []
}

// Step 7: SOA for zone metadata
try {
    soa = app::global_dns::get_soa_record(domain=domain)
    profile["soa_admin"] = soa["soa_record"]["rname"]
    profile["soa_min_ttl"] = soa["soa_record"]["minimum"]
    profile["soa_serial"] = soa["soa_record"]["serial"]
} catch e {
    // SOA failure is non-critical
}

// Compute risk signals
risk_signals = []
if profile["resolves"] == false {
    risk_signals = risk_signals + ["domain_does_not_resolve"]
}
if profile["has_mx"] == false {
    risk_signals = risk_signals + ["no_mx_records"]
}
if profile["spf"] == "NOT_FOUND" {
    risk_signals = risk_signals + ["no_spf"]
}
if profile["dmarc"] == "NOT_FOUND" {
    risk_signals = risk_signals + ["no_dmarc"]
}
if "soa_min_ttl" in profile {
    if profile["soa_min_ttl"] <= 60 {
        risk_signals = risk_signals + ["low_negative_cache_ttl"]
    }
}
profile["risk_signals"] = risk_signals
profile["risk_signal_count"] = len(risk_signals)

alert["enrichments"]["phishing_domain_profile"] = profile
```

**After DNS profiling:** Feed resolved IPs to `app::virustotal::ip_reputation` or `app::abuseipdb::check_ip` for reputation scoring. Search Splunk for historical connections to the resolved IPs to find other affected hosts.

---

## Pattern 2: IP-to-Infrastructure Mapping

**When to use:** Alert contains a suspicious IP (C2 callback, lateral movement destination, brute-force source) and you need to understand what infrastructure it belongs to.

**Actions chained:** `reverse_lookup` → `resolve_domain` (forward verification) → `get_ns_records` → `get_soa_record`

**Decision tree:**

1. Does the IP have a PTR record? (`reverse_lookup`)
   - No PTR → Common for cloud VMs, residential IPs, and VPN exits. Not inherently malicious but reduces attribution. **Proceed with IP-only enrichment** (AbuseIPDB, VirusTotal).
   - Has PTR → Continue to step 2.
2. Does forward resolution match? (`resolve_domain` on the PTR result)
   - Forward IP matches original IP → **Confirmed** forward-confirmed reverse DNS (FCrDNS). The hostname is trustworthy.
   - Forward IP differs → PTR record is stale or misconfigured. **Don't trust the hostname** for attribution.
3. What does the hostname tell you?
   - Matches internal naming convention (e.g., `srv-web-01.corp.example.com`) → Likely legitimate internal host.
   - CDN/cloud pattern (e.g., `ec2-52-1-2-3.compute-1.amazonaws.com`) → Cloud-hosted; check if expected.
   - Generic ISP hostname (e.g., `pool-1-2-3-4.res.example.net`) → Residential IP; unusual for server-to-server traffic.

**Cy task template:**

```cy
ip = alert["src_ip"]
infra = {"ip": ip}

// Step 1: Reverse lookup
try {
    rev = app::global_dns::reverse_lookup(ip=ip)
    infra["hostname"] = rev["primary_domain"]
    infra["all_hostnames"] = rev["domains"]
    infra["has_ptr"] = true

    // Step 2: Forward verification (FCrDNS)
    try {
        fwd = app::global_dns::resolve_domain(domain=rev["primary_domain"])
        infra["forward_ips"] = fwd["records"]
        infra["fcrdns_valid"] = ip in fwd["records"]
    } catch e {
        infra["fcrdns_valid"] = false
    }

    // Step 3: Find parent zone via NS query — walk progressively shorter
    // suffixes until NS records are found, avoiding public-suffix issues
    hostname = rev["primary_domain"]
    parts = hostname.split(".")
    parent_found = false
    idx = 1
    while idx < len(parts) - 1 and parent_found == false {
        candidate = ".".join(parts[idx:])
        try {
            ns = app::global_dns::get_ns_records(domain=candidate)
            infra["parent_domain"] = candidate
            infra["nameservers"] = ns["nameservers"]
            parent_found = true
        } catch e {
            // Try next level up
        }
        idx = idx + 1
    }
} catch e {
    infra["has_ptr"] = false
    infra["ptr_error"] = str(e)
}

alert["enrichments"]["ip_infrastructure"] = infra
```

**After DNS mapping:** If PTR lookup fails, keep investigating the IP directly with proxy, DNS, firewall, and reputation data — don't treat the miss as malicious by itself.

---

## Pattern 3: Safe Small-Batch Enrichment

**When to use:** Alert contains multiple indicators (IPs and domains) that all need DNS resolution. Keeps a serial batch cap to prevent one timeout from crashing the task. For larger sets, use workflow fan-out.

**Cy task template:**

```cy
iocs = input.iocs ?? []
dns_batch = []
i = 0
processed = 0

while (i < len(iocs) and processed < 10) {
    ioc = iocs[i]

    if (ioc.type == "domain" and (ioc.value ?? "") != "") {
        entry = {"domain": ioc.value, "errors": {}}

        try {
            entry["a"] = app::global_dns::resolve_domain(domain=ioc.value, record_type="A")
        } catch (e) {
            entry["errors"]["a"] = "${e}"
        }

        try {
            entry["ns"] = app::global_dns::get_ns_records(domain=ioc.value)
        } catch (e) {
            entry["errors"]["ns"] = "${e}"
        }

        dns_batch = dns_batch + [entry]
        processed = processed + 1
    }

    if (ioc.type == "ip" and (ioc.value ?? "") != "") {
        entry = {"ip": ioc.value, "errors": {}}

        try {
            rev = app::global_dns::reverse_lookup(ip=ioc.value)
            entry["hostname"] = rev["primary_domain"]
        } catch (e) {
            entry["errors"]["ptr"] = "${e}"
        }

        dns_batch = dns_batch + [entry]
        processed = processed + 1
    }

    i = i + 1
}

alert["enrichments"]["dns_bulk"] = {
    "results": dns_batch,
    "processed_count": processed,
    "throttle_note": "Serial DNS only; move larger batches into workflow fan-out"
}
```

---

## Pattern 4: Lateral Movement DNS Verification

**When to use:** Alert indicates internal lateral movement (e.g., unusual RDP, SMB, or SSH connections between hosts). Use DNS to verify whether destination IPs map to expected internal hostnames.

**Decision tree:**

1. Reverse-lookup the destination IP → Does the hostname match internal naming conventions?
   - Matches expected pattern (e.g., `dc01.corp.local`, `fileserver.internal.example.com`) → Likely legitimate. Cross-check with AD/LDAP.
   - No PTR or hostname doesn't match internal pattern → **Suspicious.** Internal IPs should have PTR records in well-managed environments.
2. If hostname resolves, check if it's a critical asset (domain controller, file server, database).
   - Lateral movement to a DC or database server → **High severity** — escalate immediately.

**Cy task template:**

```cy
dst_ip = alert["dst_ip"]
lateral = {"dst_ip": dst_ip}

try {
    rev = app::global_dns::reverse_lookup(ip=dst_ip)
    lateral["dst_hostname"] = rev["primary_domain"]

    // Check for critical asset patterns
    hostname_lower = rev["primary_domain"].lower()
    critical_patterns = ["dc", "domain", "sql", "db", "exchange", "mail", "backup", "admin"]
    is_critical = false
    for pattern in critical_patterns {
        if pattern in hostname_lower {
            is_critical = true
        }
    }
    lateral["is_critical_asset"] = is_critical
    if is_critical {
        lateral["escalation_recommended"] = true
        lateral["reason"] = "Lateral movement to potential critical asset: " + rev["primary_domain"]
    }
} catch e {
    lateral["dst_hostname"] = "UNRESOLVED"
    lateral["note"] = "No PTR record — verify if internal DNS is configured for this subnet"
}

alert["enrichments"]["lateral_movement_dns"] = lateral
```

---

## Pattern 5: DKIM Key Verification

**When to use:** A phishing alert includes the raw email with a `DKIM-Signature` header. You want to verify whether the claimed DKIM key exists in DNS for the signing domain.

**Prerequisites:** The email's `DKIM-Signature` header contains `s=<selector>` and `d=<domain>`. DNS cannot discover selectors — the selector must be extracted from the email header before querying.

**Example `DKIM-Signature` header:**
```
DKIM-Signature: v=1; a=rsa-sha256; d=example.com; s=selector1; ...
```
→ Extract `d=example.com` and `s=selector1`, then query `selector1._domainkey.example.com`.

**Cy task template:**

```cy
dkim_selector = alert.get("dkim_selector", null)
dkim_domain = alert.get("dkim_domain", null)
dkim_result = {}

if dkim_selector != null and dkim_domain != null {
    dkim_host = dkim_selector + "._domainkey." + dkim_domain
    try {
        txt = app::global_dns::get_txt_records(domain=dkim_host)
        dkim_result["status"] = "key_found"
        dkim_result["query"] = dkim_host
        dkim_result["records"] = txt["txt_records"]
        // Check if any record contains a DKIM public key
        has_key = false
        for record in txt["txt_records"] {
            if "v=DKIM1" in record or "p=" in record {
                has_key = true
                dkim_result["key_record"] = record
            }
        }
        dkim_result["valid_dkim_key"] = has_key
    } catch e {
        // No DKIM key at this selector — could mean spoofed DKIM-Signature
        dkim_result["status"] = "no_key"
        dkim_result["query"] = dkim_host
        dkim_result["error"] = str(e)
    }
} else {
    dkim_result["status"] = "skipped"
    dkim_result["reason"] = "DKIM selector or domain not available in alert"
}

alert["enrichments"]["dkim_verification"] = dkim_result
```

**Interpretation:**

- `key_found` + `valid_dkim_key: true` → Signing domain has published a DKIM key for this selector. DNS confirms the key exists (but doesn't verify the cryptographic signature itself).
- `no_key` with NXDOMAIN → No key published at this selector. If the email claimed a DKIM-Signature with this selector, **the signature is invalid** — strong phishing indicator.
- `no_key` with NoAnswer → Subdomain exists but has no TXT record. Same conclusion as above.

---

## Corroboration Chains

### DNS → VirusTotal

After resolving a domain to IPs, check each IP's reputation:

```cy
try {
    dns = app::global_dns::resolve_domain(domain=alert["domain"])
    for ip in dns["records"] {
        try {
            vt = app::virustotal::ip_reputation(ip=ip)
            // Process VT results...
        } catch e {
            // VT failure doesn't block investigation
        }
    }
} catch e {
    // DNS failure — skip VT enrichment for this domain
}
```

### DNS → AbuseIPDB

After reverse-looking up an IP, verify its abuse history:

```cy
try {
    rev = app::global_dns::reverse_lookup(ip=alert["src_ip"])
    hostname = rev["primary_domain"]
} catch e {
    hostname = "unknown"
}

try {
    abuse = app::abuseipdb::check_ip(ip=alert["src_ip"])
    alert["enrichments"]["ip_context"] = {
        "hostname": hostname,
        "abuse_score": abuse["data"]["abuseConfidenceScore"],
        "total_reports": abuse["data"]["totalReports"]
    }
} catch e {
    alert["enrichments"]["ip_context"] = {
        "hostname": hostname,
        "abuse_check": "failed"
    }
}
```

### DNS → Splunk / SIEM

Use resolved IPs or hostnames to search for related events:

```cy
try {
    dns = app::global_dns::resolve_domain(domain=alert["domain"])
    ip_list = dns["records"].join(" OR ")
    spl_query = "index=* (src=" + ip_list + " OR dest=" + ip_list + ") | stats count by src, dest, sourcetype | head 50"
    try {
        splunk_results = app::splunk::search(query=spl_query, earliest="-24h")
        alert["enrichments"]["related_traffic"] = splunk_results
    } catch e {
        // Splunk failure is non-critical
    }
} catch e {
    // DNS failure — cannot pivot to Splunk by IP
}
```

### DNS → Email Telemetry

Use exact auth-related hostnames extracted from email headers with `get_txt_records` to validate whether DMARC, DKIM, or vendor-verification data exists where the message claims it should.

### DNS → Lookalike Clustering

Compare `nameservers`, `soa_record.mname`, and `soa_record.serial` across several domains before over-weighting `A` records, which often sit behind shared hosting or CDN edges.

---

## TP/FP Disposition Signals from DNS

| Signal | Suggests TP (malicious) | Suggests FP (benign) |
|---|---|---|
| Domain doesn't resolve (NXDOMAIN) | Recently taken down C2/phishing domain | Typo in alert, expired legitimate domain |
| No SPF + No DMARC | Throwaway phishing domain | Very new legitimate startup (rare) |
| SPF `-all` + DMARC `p=reject` | — | Well-managed legitimate domain |
| No PTR on source IP | Cloud-hosted attack infra | Normal for some CDNs and cloud services |
| FCrDNS mismatch | Spoofed or misconfigured attacker infra | Legitimate but misconfigured host |
| Single nameserver | Disposable infra | Small personal site |
| MX points to known provider | — | Legitimate business using Google/Microsoft |
| Low SOA negative-cache TTL (≤60s) | Fast-flux C2 infrastructure | CDN or load-balanced service |
| DKIM key missing for claimed selector | Forged DKIM-Signature header | Rotated key (recently changed) |

DNS alone rarely gives a definitive verdict. Always corroborate with at least one additional source (VirusTotal, AbuseIPDB, Splunk logs) before making a TP/FP call.

---

## High-Signal Interpretation Notes

- Treat DNS as infrastructure context, not ground truth for intent.
- `MX` and `TXT` that align with expected enterprise mail infrastructure reduce suspicion only when they also match header evidence, user behavior, and known vendors.
- Shared `NS` or `SOA` data across multiple suspicious domains is often a stronger campaign signal than shared `A` records alone.
- Forward-confirm PTR hostnames before using them heavily in correlation or case summaries.
- If a `forward.cname` exists, pivot again on the returned alias target instead of stopping at the brand-looking hostname.
