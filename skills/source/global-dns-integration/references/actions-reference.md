# Global DNS — Actions Reference

## Table of Contents

- [Quick Inventory](#quick-inventory)
- [Integration Config](#integration-config)
- [Runtime Behavior in Cy](#runtime-behavior-in-cy)
- [Common Error Types](#common-error-types)
- [resolve_domain](#resolve_domain)
- [reverse_lookup](#reverse_lookup)
- [get_mx_records](#get_mx_records)
- [get_txt_records](#get_txt_records)
- [get_ns_records](#get_ns_records)
- [get_soa_record](#get_soa_record)
- [health_check Connector Action](#health_check-connector-action)
- [Known Limitations](#known-limitations)

---

## Quick Inventory

| Action | Cy FQN | Required Params | Key Success Fields |
|---|---|---|---|
| Resolve domain | `app::global_dns::resolve_domain` | `domain` | `domain`, `record_type`, `records`, `dns_server` |
| Reverse lookup | `app::global_dns::reverse_lookup` | `ip` | `ip`, `domains`, `primary_domain`, `dns_server` |
| MX records | `app::global_dns::get_mx_records` | `domain` | `domain`, `mx_records`, `count`, `dns_server` |
| TXT records | `app::global_dns::get_txt_records` | `domain` | `domain`, `txt_records`, `count`, `dns_server` |
| NS records | `app::global_dns::get_ns_records` | `domain` | `domain`, `nameservers`, `count`, `dns_server` |
| SOA record | `app::global_dns::get_soa_record` | `domain` | `domain`, `soa_record`, `dns_server` |

---

## Integration Config

**Integration ID:** `global-dns` (use in Cy `app::` calls)
**Auth:** None required.
**Rate limits:** None documented (public DNS via the runtime's system resolver).
**Timeout:** 5s default, configurable 1–30s in integration settings. Applied to both `resolver.timeout` and `resolver.lifetime`. Use shorter values to fail fast during triage.

The `dns_server` setting is informational only — the action always creates a default `dns.asyncresolver.Resolver()` and uses the runtime's system resolver. The `dns_server` field returned in responses reflects the resolver actually used, not a configured preference.

---

## Runtime Behavior in Cy

- Tool namespace: `app::global_dns::*`.
- Every lookup should be wrapped in `try/catch`. See `disagreements.md` for a note on how errors surface in Cy.
- `health_check` is a `connector` action, not a `tool`, so it is not callable as `app::global_dns::health_check(...)` inside Cy.
- Every exposed action returns multiple fields — none collapse to a single scalar in Cy.
- The quickest Cy sanity check: call one tool in a `try/catch` — if the environment cannot egress DNS, you will see timeout exceptions.

---

## Common Error Types

All raw action responses use `status: "success"` or `status: "error"`. On error, `error_type` identifies the failure:

| Error Type | Meaning |
|---|---|
| `NXDOMAIN` | Domain/IP does not exist in DNS |
| `NoAnswer` | Domain exists but has no records of the requested type |
| `TimeoutError` | DNS query exceeded timeout |
| `ValidationError` | Missing required parameter or unsupported value |

---

## resolve_domain

Resolve a domain name to IP addresses. Supports A (IPv4), AAAA (IPv6), and CNAME record types.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `domain` | string | yes | — | Domain to resolve (e.g., `example.com`) |
| `record_type` | string | no | `"A"` | One of: `A`, `AAAA`, `CNAME` |

**Raw success response:**

```json
{
  "status": "success",
  "domain": "google.com",
  "record_type": "A",
  "records": ["142.250.191.46"],
  "dns_server": "127.0.0.11"
}
```

- `records` — array of strings: IPv4 for A, IPv6 for AAAA, target domain names for CNAME.

**Cy example:**

```cy
try {
    result = app::global_dns::resolve_domain(domain=alert["domain"])
    alert["enrichments"]["dns_resolution"] = {
        "ips": result["records"],
        "record_type": result["record_type"]
    }
} catch e {
    alert["enrichments"]["dns_resolution"] = {"error": str(e)}
}
```

**Interpretation and edge cases:**

- Use `A` for IPv4 pivots, `AAAA` for IPv6, and `CNAME` when the hostname may front a CDN or tracking host.
- `CNAME` returns alias target names, not the final A/AAAA answers. Query the returned target again if you need backing IPs.
- CNAME queries return `NoAnswer` for apex domains — apex domains use A/AAAA, not CNAME.
- AAAA queries may return `NoAnswer` if the domain has no IPv6 records or the resolver environment doesn't forward IPv6 (observed in Docker environments).
- `NXDOMAIN` is itself a useful signal: newly registered or non-existent domain.

---

## reverse_lookup

Resolve an IP address to hostname(s) via PTR records. Works with both IPv4 and IPv6.

**Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `ip` | string | yes | IPv4 or IPv6 address (e.g., `8.8.8.8`) |

**Raw success response:**

```json
{
  "status": "success",
  "ip": "8.8.8.8",
  "domains": ["dns.google"],
  "primary_domain": "dns.google",
  "dns_server": "127.0.0.11"
}
```

- `domains` — array of all PTR record values.
- `primary_domain` — first domain in the list (convenience field, not a trust verdict).

**Cy example:**

```cy
try {
    result = app::global_dns::reverse_lookup(ip=alert["src_ip"])
    alert["enrichments"]["reverse_dns"] = {
        "hostname": result["primary_domain"],
        "all_hostnames": result["domains"]
    }
} catch e {
    alert["enrichments"]["reverse_dns"] = {"error": str(e)}
}
```

**Interpretation and edge cases:**

- Treat PTR output as a pivot source: forward-confirm the hostname with `resolve_domain` and compare with the original IP before trusting it for attribution.
- Many IPs have no PTR record — `NXDOMAIN` is normal for cloud VMs, residential IPs, and some CDNs. Absence of PTR is not inherently malicious but is a data point.
- RFC 5737 test ranges (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24) always return `NXDOMAIN`.
- If the alert field contains a URL, hostname, or CIDR instead of a bare IP, normalize it first — see the PTR input normalization snippet in `references/investigation-patterns.md`.

---

## get_mx_records

Get mail exchange (MX) records for a domain, sorted by priority (lowest number = highest priority).

**Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `domain` | string | yes | Domain to query |

**Raw success response:**

```json
{
  "status": "success",
  "domain": "google.com",
  "mx_records": [
    {"priority": 10, "exchange": "smtp.google.com"}
  ],
  "count": 1,
  "dns_server": "127.0.0.11"
}
```

- `mx_records` — array of objects with `priority` (int) and `exchange` (string), sorted ascending by priority.

**Cy example:**

```cy
try {
    result = app::global_dns::get_mx_records(domain=alert["sender_domain"])
    mail_hosts = []
    for mx in result["mx_records"] {
        mail_hosts = mail_hosts + [mx["exchange"]]
    }
    alert["enrichments"]["mx_records"] = {
        "mail_servers": mail_hosts,
        "count": result["count"]
    }
} catch e {
    alert["enrichments"]["mx_records"] = {"error": str(e)}
}
```

**Investigation value:**

- Legitimate organizations use well-known mail providers (Google, Microsoft, Proofpoint). Suspicious domains often point to obscure or self-hosted mail servers.
- `NoAnswer` means the domain doesn't receive email — suspicious for a domain claiming to be a business.
- Compare `exchange` values against expected brand/provider. Unexpected exchangers are useful pivots but not automatic malice.

---

## get_txt_records

Get all TXT records for a domain or subdomain. The `domain` parameter accepts any owner name, so you can query apex domains, DMARC subdomains, and DKIM selector hostnames directly.

**Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `domain` | string | yes | Domain or subdomain to query (e.g., `example.com`, `_dmarc.example.com`, `selector1._domainkey.example.com`) |

**Common mail-auth owner names:**

| Goal | Query `domain` value | Derivation |
|---|---|---|
| Apex TXT / SPF / verification | `example.com` | Organizational domain or exact host |
| DMARC policy | `_dmarc.example.com` | `_dmarc.` prefix under the domain |
| DKIM key | `selector._domainkey.example.com` | `s=` tag for selector, `d=` tag for domain from `DKIM-Signature` header |

**Raw success response (apex):**

```json
{
  "status": "success",
  "domain": "google.com",
  "txt_records": [
    "v=spf1 include:_spf.google.com ~all",
    "facebook-domain-verification=22rm551cu4k0ab0bxsw536tlds4h95",
    "google-site-verification=wD8N7i1JTNTkezJ49swvWW48f8_9xveREV4oB-0Hf5o",
    "MS=E4A68B9AB2BB9670BCE15412F62916164C0B20BB"
  ],
  "count": 13,
  "dns_server": "127.0.0.11"
}
```

**Raw success response (DMARC query on `_dmarc.google.com`):**

```json
{
  "status": "success",
  "domain": "_dmarc.google.com",
  "txt_records": [
    "v=DMARC1; p=reject; rua=mailto:mailauth-reports@google.com"
  ],
  "count": 1,
  "dns_server": "127.0.0.11"
}
```

- `txt_records` — flat array of strings, one per TXT record. Multi-string TXT fragments are concatenated; original chunk boundaries are not preserved.

**Cy example — SPF + DMARC check:**

```cy
domain = alert["sender_domain"]
email_auth = {}

// Get SPF from apex TXT records
try {
    txt_result = app::global_dns::get_txt_records(domain=domain)
    email_auth["spf"] = "NOT_FOUND"
    for record in txt_result["txt_records"] {
        if "v=spf1" in record {
            email_auth["spf"] = record
        }
    }
} catch e {
    email_auth["spf"] = "ERROR: " + str(e)
}

// Get DMARC from _dmarc subdomain
try {
    dmarc_result = app::global_dns::get_txt_records(domain="_dmarc." + domain)
    email_auth["dmarc"] = "NOT_FOUND"
    for record in dmarc_result["txt_records"] {
        if "v=DMARC1" in record {
            email_auth["dmarc"] = record
        }
    }
} catch e {
    email_auth["dmarc"] = "NOT_FOUND"
}

alert["enrichments"]["email_authentication"] = email_auth
```

For DKIM verification, see `references/investigation-patterns.md` § Pattern 5.

**Investigation value:**

- `v=spf1 ... -all` (hard fail) is stricter than `~all` (soft fail). Missing SPF entirely is a red flag for phishing domains.
- DMARC `p=reject` means the domain owner actively blocks spoofed mail. `p=none` means monitoring only. Missing DMARC makes spoofing easier.
- Domain verification tokens (Google, Facebook, Microsoft) indicate the domain is used by real services — less likely to be throwaway phishing infra.
- TXT presence alone is weak legitimacy evidence; phishing infrastructure can publish SPF, DMARC, and verification strings quickly.

---

## get_ns_records

Get authoritative nameserver records for a domain.

**Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `domain` | string | yes | Domain to query |

**Raw success response:**

```json
{
  "status": "success",
  "domain": "google.com",
  "nameservers": ["ns1.google.com", "ns2.google.com", "ns3.google.com", "ns4.google.com"],
  "count": 4,
  "dns_server": "127.0.0.11"
}
```

- `nameservers` — array of NS hostnames. Tells you who is authoritative for the zone, not where the web or mail host resolves.

**Cy example:**

```cy
try {
    result = app::global_dns::get_ns_records(domain=alert["domain"])
    alert["enrichments"]["nameservers"] = {
        "ns_list": result["nameservers"],
        "count": result["count"]
    }
} catch e {
    alert["enrichments"]["nameservers"] = {"error": str(e)}
}
```

**Investigation value:**

- Free/bulletproof hosting nameservers are a red flag.
- Legitimate enterprises use major DNS providers (Cloudflare, AWS Route53, Google Cloud DNS, Akamai).
- Single nameserver (count=1) is unusual for production domains — may indicate disposable infrastructure.
- Shared NS values across multiple suspicious domains are useful campaign-clustering evidence.

---

## get_soa_record

Get Start of Authority record for a domain zone. Provides zone metadata — does not contain domain creation or registration dates.

**Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `domain` | string | yes | Domain to query |

**Raw success response:**

```json
{
  "status": "success",
  "domain": "google.com",
  "soa_record": {
    "mname": "ns1.google.com",
    "rname": "dns-admin.google.com",
    "serial": 883926585,
    "refresh": 900,
    "retry": 900,
    "expire": 1800,
    "minimum": 60
  },
  "dns_server": "127.0.0.11"
}
```

**Field meanings:**

| Field | Type | Description |
|---|---|---|
| `mname` | string | Primary nameserver for the zone |
| `rname` | string | Responsible party email in DNS mailbox notation (dot-notation: `dns-admin.google.com` = `dns-admin@google.com`). Not normalized to email format. |
| `serial` | int | Zone version counter (RFC 1035) — increments on zone changes, **not** a timestamp or creation date. Use WHOIS for registration dates. |
| `refresh` | int | Seconds between secondary NS refresh checks |
| `retry` | int | Seconds between retry after failed refresh |
| `expire` | int | Seconds before secondary NS stops serving stale data |
| `minimum` | int | Negative-cache TTL in seconds (RFC 2308) — how long resolvers cache NXDOMAIN responses |

All timing fields are raw integers; the integration does not label or normalize them further.

**Cy example:**

```cy
try {
    result = app::global_dns::get_soa_record(domain=alert["domain"])
    soa = result["soa_record"]
    alert["enrichments"]["soa"] = {
        "primary_ns": soa["mname"],
        "admin_contact": soa["rname"],
        "serial": soa["serial"],
        "minimum_ttl": soa["minimum"]
    }
} catch e {
    alert["enrichments"]["soa"] = {"error": str(e)}
}
```

**Investigation value:**

- Very low `minimum` TTL (e.g., ≤60s) can indicate fast-flux infrastructure where attackers want NXDOMAIN answers to expire quickly from caches.
- `rname` reveals the administrative contact — useful for attribution and correlating domains under common ownership.
- `serial` is useful for comparing across repeated runs or lookalike domains to spot shared zone management or recent zone changes.
- Stable, high `refresh`/`expire` values suggest established infrastructure.

---

## health_check Connector Action

This action exists for integration monitoring, not Cy task logic. It is a `connector` action, not callable via `app::global_dns::health_check(...)` in Cy.

**Raw success response:**

```json
{
  "status": "success",
  "message": "DNS resolution is working",
  "data": {
    "healthy": true,
    "dns_server": "192.0.2.53",
    "test_query": "google.com",
    "resolved_ips": ["142.250.185.14"]
  }
}
```

Use when debugging whether the integration runtime can reach DNS at all. Do not build Cy task logic around it.

---

## Known Limitations

- **`dns_server` setting is informational only** — the code always uses the runtime's default resolver configuration regardless of what is configured.
- **`resolve_domain` supports only `A`, `AAAA`, and `CNAME`** — use the dedicated MX/TXT/NS/SOA actions for other record types.
- **TXT fragments are concatenated** — multi-string TXT RR data is joined into one string; original chunk boundaries are not preserved.
- **SOA `rname` is not normalized** — returned in DNS mailbox dot-notation, not converted to `user@example.com`. Preserve raw strings in enrichments.
- **No TTLs, DNSSEC state, or authority/additional-section data** — actions return answer-section data only.
- **No wildcard queries** — you cannot query `*.example.com`; resolve specific subdomains individually.
- **CNAME at apex** — querying CNAME on an apex domain always returns `NoAnswer` (correct DNS behavior). Query subdomains like `www.example.com` for CNAME records.
- **No DKIM selector discovery** — `get_txt_records` queries specific hostnames; it cannot enumerate DKIM selectors. Extract `s=` from the email's `DKIM-Signature` header first.
- **AAAA in Docker** — AAAA queries may return `NoAnswer` even for domains with IPv6 records when running inside Docker, because the Docker DNS proxy may not forward IPv6 queries.
- **`health_check` is connector-only** — not available as a tool action in Cy.
