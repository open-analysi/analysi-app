---
name: unshortenme-integration
description: Expand shortened URLs via unshorten.me during phishing triage and URL-based alert investigations. Use when investigating suspicious links, bit.ly/tinyurl/t.co URLs in alerts, or building URL expansion workflows in Cy.
version: 0.1.0
---

# unshorten.me Integration for Analysi SOC

Expand shortened URLs to reveal final destinations during phishing triage. Authentication is managed at the Analysi integration connection level (API token configured once, transparent to Cy scripts). Rate-limited to **10 calls/hour** for new URLs (previously-resolved URLs are cached and unlimited). Pre-filter to known shortener domains to conserve quota — see `actions-reference.md` § Rate Limit Management for the canonical domain list.

## Reference Loading Guide

| Reference | Read when | Consult for |
|---|---|---|
| `references/actions-reference.md` | Calling any unshortenme action | Parameters, return schemas, Cy call snippets, error types, rate limit rules, shortener domain list |
| `references/investigation-patterns.md` | Building phishing triage workflows | Decision trees, multi-source corroboration, complete Cy task templates, TP/FP signal tables |

## Quick Decision Path

1. Extract URLs from alert IOCs
2. Filter to known shortener domains (see `actions-reference.md` § Rate Limit Management)
3. Call `app::unshortenme::unshorten_url(url=short_url)` with try/catch
4. Feed `resolved_url` into downstream enrichment (Global DNS, WHOIS RDAP)
5. Use LLM reasoning to assess suspicion in the alert context

## Core Cy Pattern

```cy
try {
    result = app::unshortenme::unshorten_url(url=url)
    resolved = result.resolved_url ?? url
} catch (e) { resolved = url }
```

For complete task templates with LLM analysis and enrichment, see `investigation-patterns.md`.

## Constraints

- **10 calls/hour for new URLs** — cached URLs are unlimited; monitor `remaining_calls` in responses (see `actions-reference.md` § Rate Limit Management)
- No bulk endpoint — each URL is a separate API call
- No domain reputation, screenshot, or content analysis — use Global DNS and WHOIS RDAP downstream
- Resolves the full redirect chain, not just one hop — `resolved_url` is the final destination
