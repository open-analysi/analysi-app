---
name: nistnvd-integration
description: NIST NVD CVE lookups via Analysi for SOC alert triage. Use when investigating vulnerability-related alerts, checking CVE severity and CVSS scores, correlating exploit attempts with known vulnerabilities, assessing patch urgency, or enriching alerts with affected product details and CISA KEV status.
version: 0.1.0
---

# NIST NVD CVE Lookup — Analysi Integration

Query NIST National Vulnerability Database for CVE details during alert triage. One action available: `cve_lookup`. Public API, no credentials required (optional API key for higher rate limits).

## Reference Loading Guide

| Reference | Read when | Consult for |
|---|---|---|
| `references/actions-reference.md` | Calling `cve_lookup` or interpreting results | Parameters, response schema, field tables, CVSS/CISA KEV access, safe lookup pattern, error handling, rate limits |
| `references/investigation-patterns.md` | Building CVE enrichment tasks or workflows | Cy task templates, multi-source correlation, severity decision trees, CVSS disposition heuristics, data samples |

## Decision Path

- **Alert contains a CVE ID** → Extract from IOCs, `primary_ioc_value`, or rule name; call `cve_lookup`; assess severity via CVSS and CISA KEV
- **CVSS ≥ 9.0 or CISA KEV present** → Flag as urgent, recommend immediate patching
- **Exploit attempt detected** → Look up targeted CVE, check CISA KEV for active exploitation, correlate CVSS attack vector with observed traffic
- **Multiple CVEs in alert** → Loop through each; prioritize CISA KEV entries first, then by CVSS score
- **CVE not found in NVD** → Recently reserved or rejected; flag for manual review
- **No CVE ID in alert** → This integration cannot help; pivot to threat intel (VirusTotal, AbuseIPDB) or SIEM (Splunk)

## Quick Reference

Call syntax: `app::nistnvd::cve_lookup(cve="CVE-2021-44228")` — always wrap in `try/catch` and check `result.not_found` (see `actions-reference.md` § Safe Lookup Pattern). CVSS data: `result.cvss_metrics.base_score` / `.base_severity`. CISA KEV: `result.cisa_kev` (`null` when not in catalog).

## Guardrails

- **Single action only** — `cve_lookup` by exact CVE ID. No keyword search, no CPE/product search, no bulk query endpoint.
- **Rate limit** — 5 req/30s without API key; 50 with key. Built-in retry (3 attempts, exponential backoff 2–10s) handles 429s.
- **Response size** — `full_data` field contains the entire raw NVD API response (100KB+). Never pass to LLM — use extracted top-level fields.
- **CVSS version** — Returns CVSS v3.1 when available, falls back to v2 for older CVEs. CVSS v4.0 is present in NVD but not extracted.
- **Older CVEs** — CVSS v2 has fewer fields and no `CRITICAL` severity; see `actions-reference.md` § CVSS v2 Fallback.
- **CISA KEV** — `cisa_kev` is `null` unless the CVE is in the Known Exploited Vulnerabilities catalog. The `due_date` field may also be `null`.
