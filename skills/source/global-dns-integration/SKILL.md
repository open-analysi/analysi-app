---
name: global-dns-integration
version: 0.1.0
description: >-
  DNS resolution, reverse lookups, and mail/TXT/NS/SOA queries via Analysi's Global DNS for SOC triage. Use when investigating suspicious domains, resolving IPs to hostnames, checking SPF/DKIM/DMARC in phishing analysis, or correlating network indicators with domain infrastructure.
---

# Global DNS — SOC Investigation Guide

DNS is foundational to alert triage: every domain in an alert can be resolved, every IP can be reverse-looked-up, and email security records reveal whether a sender domain is legitimate. This integration provides free, unauthenticated DNS queries via the runtime's system resolver.

## Reference Loading Guide

| Reference | Read when | Consult for |
|---|---|---|
| `references/actions-reference.md` | Calling any Global DNS action | Integration config, parameters, return schemas, Cy examples, error types, runtime behavior, known limitations |
| `references/investigation-patterns.md` | Building triage workflows | Phishing domain analysis, DKIM verification, DMARC org-domain fallback, IP-to-hostname correlation, PTR input normalization, batch enrichment, corroboration chains, TP/FP signals, Cy task templates |

## Quick Decision Path

1. **Suspicious domain** → `resolve_domain` for IPs, `get_txt_records` for SPF/DMARC, `get_mx_records` for mail infra, `get_ns_records` for hosting provider
2. **Suspicious IP** → `reverse_lookup` for hostname, then `resolve_domain` on result for forward-reverse consistency (FCrDNS)
3. **Phishing alert** → Full email security: `get_txt_records` on domain + `_dmarc.{domain}`, DKIM via `{selector}._domainkey.{domain}` (selector from email header), plus MX and NS checks
4. **Lateral movement / C2** → `reverse_lookup` on destination IPs, compare hostnames against expected internal naming conventions
5. **Zone metadata** → `get_soa_record` for admin contact (`rname`), negative-cache TTL (`minimum`), and zone serial (version counter, not creation date)

## Available Actions

Six tool actions in Cy: `resolve_domain`, `reverse_lookup`, `get_mx_records`, `get_txt_records`, `get_ns_records`, `get_soa_record`. A `health_check` connector action exists for integration monitoring but is not callable in Cy.

## Not Available

- **DNSSEC validation** — not supported; use external tools for chain-of-trust verification
- **Bulk/batch DNS queries** — no batch action; loop in Cy with a cap (see investigation patterns for safe batch guidance)
- **Historical/passive DNS** — only live resolution; use VirusTotal or Splunk for historical records
- **WHOIS data** — not a DNS action; use a dedicated WHOIS integration
- **DKIM selector discovery** — DNS cannot enumerate selectors; extract `s=` from the email's `DKIM-Signature` header first
- **TTLs, authority/additional sections** — not returned by any action
- **Custom resolver selection** — `dns_server` setting is informational only; the runtime's system resolver is always used
