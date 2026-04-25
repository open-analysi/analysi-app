---
name: whois-rdap-integration
description: WHOIS RDAP lookups for IP ownership, ASN, and netblock attribution during SOC investigations. Use when triaging alerts involving external IPs to identify registrant organizations, autonomous systems, hosting context, or abuse contacts via RDAP query.
version: 0.1.0
---

# WHOIS RDAP Integration

Free, unauthenticated IP registration lookups via RDAP protocol. Returns ASN, netblock CIDR, registrant organization, country, and abuse contacts for any public IPv4 or IPv6 address. No API key required.

## Reference Loading Guide

| Reference | Read when | Consult for |
|---|---|---|
| `actions-reference.md` | Calling any WHOIS RDAP action | Parameters, return field schemas, Cy examples, edge case behavior, standard IP extraction pattern |
| `investigation-patterns.md` | Building triage workflows | IP attribution decision trees, multi-source corroboration, Cy task templates, field interpretation |

## Quick Decision Path

1. **Need IP ownership context during triage?** Call `app::whois_rdap::whois_ip(ip=target_ip)` — see `actions-reference.md` § Cy Usage for the standard call-and-extract pattern
2. **Building a multi-source enrichment task?** Combine WHOIS RDAP with Tor exit check, DNS, or other enrichment integrations — see `investigation-patterns.md`
3. **Need to verify integration health?** Call `app::whois_rdap::health_check()` — returns `healthy: true/false` in ~1 second
4. **Discover other available integrations** to combine with WHOIS — call `list_integrations(configured_only=True)` via MCP

## Guardrails

- **Private/reserved IPs** return `null` (not an error) — see `actions-reference.md` § Edge Cases for the full behavior table and handling pattern.
- **Domain WHOIS is not available** — this integration only handles IP addresses. For domain registration data, use a dedicated domain WHOIS integration.
- **No ASN-only lookups** — you cannot query by ASN number directly. Provide an IP address; ASN data comes as part of the response.
- **No bulk/batch endpoint** — loop over IPs individually. Keep batch sizes reasonable (< 50 per investigation) to avoid upstream RIR throttling.
- **Rate limits are upstream** — ARIN, RIPE, APNIC, etc. each enforce their own limits. If you get errors on high-volume lookups, add delays between calls.
