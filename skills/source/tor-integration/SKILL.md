---
name: tor-integration
description: Tor exit node lookups for SOC investigations via Analysi. Use when triaging alerts involving suspicious IPs, anonymous access, credential stuffing, or brute-force attacks to determine if source IPs are Tor exit nodes.
version: 0.1.0
---

# Tor Integration for Analysi SOC

Check whether IP addresses are Tor exit nodes using the Tor Project's public exit node list. No authentication required — the integration queries `check.torproject.org/exit-addresses` directly.

## Reference Loading Guide

| Reference | Read when | Consult for |
|---|---|---|
| `references/actions-reference.md` | Calling any Tor action | Parameters, return schemas, Cy examples, edge cases, known limitations |
| `references/investigation-patterns.md` | Building triage workflows | Decision trees, multi-source corroboration with Splunk/AbuseIPDB/WHOIS, Cy task templates |

## Quick Decision Path

1. **Single IP check** — call `app::tor::lookup_ip(ip=the_ip)`, read `result.results[0].is_exit_node`
2. **Batch check** — pass comma-separated IPs in one call; iterate `result.results`
3. **Tor + context** — combine Tor status with AbuseIPDB score, WHOIS data, and Splunk event logs to determine TP/FP
4. **Health/availability** — call `app::tor::health_check()` before batch jobs to confirm the exit-node list is reachable

## Guardrails

- **Current list only, no history** — see `actions-reference.md` § Known Limitations for details on data freshness, IPv6 gaps, and input validation caveats.
- **Boolean result only** — Tor lookup returns `is_exit_node: true/false`. Pair with WHOIS RDAP or GeoIP for network ownership, ASN, or geolocation context.
