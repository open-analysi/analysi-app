---
name: abuseipdb-integration
description: AbuseIPDB IP reputation lookups for SOC alert triage via Analysi. Use when checking IP abuse confidence scores, investigating brute force or scanning activity, or enriching alerts with crowd-sourced threat intelligence.
version: 0.1.0
---

# AbuseIPDB Integration for Analysi Investigations

AbuseIPDB provides crowd-sourced IP abuse intelligence. The Analysi integration exposes two working actions: `lookup_ip` for reputation checks and `report_ip` for submitting abuse reports. Only IP-based lookups are supported — domain, URL, and file hash actions are stubs that return errors.

## Reference Loading Guide

| Reference | Read when | Consult for |
|---|---|---|
| `references/actions-reference.md` | Calling any AbuseIPDB action | Parameters, return fields, Cy examples, response interpretation, known limitations |
| `references/investigation-patterns.md` | Building triage workflows | Decision trees, multi-source corroboration with VirusTotal/Splunk, Cy task templates, category mappings |

## Quick Decision Path

- **Need IP abuse score?** → `app::abuseipdb::lookup_ip(ip=target_ip)` — returns `abuse_confidence_score` (0–100). See `actions-reference.md` § Cy Usage Pattern for the full extraction template.
- **Corroborating with VirusTotal?** → Call both in parallel, compare scores — see `investigation-patterns.md` § Pattern 2
- **Reporting confirmed abuse?** → `app::abuseipdb::report_ip(ip=ip, categories="18,22")` — use only after confirmed TP
- **Need domain/URL/hash lookup?** → Not available via AbuseIPDB — use VirusTotal instead

## Guardrails

- **No domain/URL/file hash lookups** — `lookup_domain`, `lookup_url`, `lookup_file_hash` are stubs that return `NotSupportedError`. Use VirusTotal for those IOC types.
- **`report_ip` is a write operation** — only use after a confirmed true positive disposition. Never call during automated triage without human approval.
- **Rate limits apply** — AbuseIPDB enforces per-key rate limits. The integration raises `"Rate limit exceeded"` on HTTP 429. Add try/catch around all calls.
- **Default lookback is 10 days** — the Analysi integration defaults to 10 days (the upstream AbuseIPDB API defaults to 30). Pass `days=90` for broader history when investigating persistent threats.
- **No `verbose` mode** — the integration does not expose the AbuseIPDB `verbose` flag, so individual report details are not available. Use `total_reports` and `num_distinct_users` for crowd-sourced signal strength.
