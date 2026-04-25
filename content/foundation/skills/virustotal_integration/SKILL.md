---
name: virustotal-integration
description: VirusTotal threat intelligence lookups for SOC alert triage via Analysi. Use when checking IP, domain, URL, or file hash reputation, investigating malware indicators, correlating threat data across detection engines, or enriching alerts with crowd-sourced detection results.
version: 0.1.0
---

# VirusTotal Integration for SOC Investigations

Query VirusTotal's crowd-sourced threat intelligence database from Cy scripts to enrich alerts with IP, domain, URL, and file hash reputation data. The integration (`app::virustotal::`) provides 6 actions covering reputation lookups and on-demand URL analysis.

## Reference Loading Guide

| Reference | Read when | Consult for |
|---|---|---|
| `references/actions-reference.md` | Calling any VT action in Cy | Parameters, return schemas, response field meanings, detection thresholds, known limitations |
| `references/investigation-patterns.md` | Building investigation workflows | Decision trees, Cy task templates with LLM reasoning, multi-source corroboration, batch IOC analysis |

## Action Selection

- **IP address** — `app::virustotal::ip_reputation(ip=ip)` — detection stats + ASN/country
- **Domain** — `app::virustotal::domain_reputation(domain=domain)` — detection stats + categories
- **URL** — `app::virustotal::url_reputation(url=url)` — detection stats + submission history
- **File hash** (MD5/SHA1/SHA256) — `app::virustotal::file_reputation(file_hash=hash)` — detection stats + file metadata
- **On-demand URL scan** — `submit_url_analysis(url=url)` then `get_analysis_report(analysis_id=id)` — two-step submit-then-poll

## Key Response Pattern

All four reputation actions return a `reputation_summary` with fields `malicious`, `suspicious`, `harmless`, `undetected` (integer counts of engines). See `actions-reference.md` § Common Response Patterns for full schema and interpretation thresholds.

## Guardrails

- VT relationship/graph queries are not available — pivot via Splunk log queries instead
- File upload/submission is not supported — only hash lookups against existing VT database entries
- Rate limits apply (429 errors, auto-retry 3×). Free-tier keys: 4 req/min — batch IOC workflows may need throttling
- `submit_url_analysis` + `get_analysis_report` is a two-step async pattern — check `analysis_status == "completed"` before trusting stats
- The `not_found` flag appears when VT has no data — see `actions-reference.md` § The `not_found` Flag
