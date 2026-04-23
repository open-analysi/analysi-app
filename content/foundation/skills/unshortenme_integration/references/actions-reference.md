# unshorten.me Actions Reference

## Integration Overview

- **Integration type**: `unshortenme`
- **Integration ID (instance)**: `unshortenme`
- **Authentication**: API token required — managed at the Analysi integration connection level (transparent to Cy scripts; no auth parameters in action calls)
- **Rate limit**: 10 calls/hour for new URLs; cached (previously-resolved) URLs are unlimited
- **Actions**: 2 — `health_check`, `unshorten_url`

<!-- EVIDENCE: Rate limit verified via https://unshorten.me/api and https://help.logichub.com/docs/unshortenme — "10 requests per hour for new short URLs" -->

---

## Action: `unshorten_url`

Expand a shortened URL to its final destination by following the full redirect chain.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `url` | string | Yes | Shortened URL to expand (e.g., `https://bit.ly/abc123`) |

### Cy Calling Convention

```cy
result = app::unshortenme::unshorten_url(url="https://tinyurl.com/y6abc123")
```

### Success Response Schema

<!-- EVIDENCE: MCP live test — run_integration_tool("unshortenme", "unshorten_url", {"url": "https://tinyurl.com/y6abc123"}) -->

```json
{
  "status": "success",
  "url": "https://tinyurl.com/y6abc123",
  "resolved_url": "https://www.washingtontimes.com/news/2019/feb/17/...",
  "requested_url": "tinyurl.com/y6abc123",
  "success": true,
  "usage_count": 0,
  "remaining_calls": 10
}
```

| Field | Type | Description |
|---|---|---|
| `status` | string | `"success"` on successful resolution |
| `url` | string | The original URL as submitted (with scheme) |
| `resolved_url` | string | **The final destination URL after all redirects** — this is the field you need |
| `requested_url` | string | The URL as submitted to the upstream API (scheme may be stripped) |
| `success` | boolean | `true` if resolution completed |
| `usage_count` | integer | Number of API calls used in current period |
| `remaining_calls` | integer | Remaining API calls in the current hourly window. **Monitor this field.** |

### Error Response Schema

<!-- EVIDENCE: MCP live test — run_integration_tool("unshortenme", "unshorten_url", {"url": "not-a-url"}) -->

On failure, the action **raises an exception** (Cy catch block fires). The error object contains:

```json
{
  "status": "error",
  "error": "API returned error: Invalid Short URL",
  "error_type": "APIError",
  "url": "not-a-url"
}
```

| Field | Type | Description |
|---|---|---|
| `status` | string | `"error"` |
| `error` | string | Human-readable error message |
| `error_type` | string | Error category: `"APIError"` or `"ValidationError"` |
| `url` | string | The URL that was submitted |

### Error Types Observed

<!-- EVIDENCE: MCP live tests with various inputs -->

| Input | Error Type | Error Message | Triage Guidance |
|---|---|---|---|
| `""` (empty) | `ValidationError` | `Missing required parameter: url` | Validate before calling — skip if no URL IOC present |
| `"not-a-url"` | `APIError` | `Invalid Short URL` | Malformed input — log and move on |
| Non-existent short URL (e.g., expired bit.ly) | `APIError` | `Unknown Error!` | URL format is valid but can't be resolved. In phishing triage, treat as suspicious — the link may have been taken down after abuse reports or is deliberately evasive |

### Cy Call-and-Handle Snippet

This is the minimal pattern for calling `unshorten_url` with error handling. For complete task templates with LLM analysis, shortener pre-filtering, and `enrich_alert()`, see `investigation-patterns.md`.

```cy
resolved_url = url
expansion_error = ""
try {
    result = app::unshortenme::unshorten_url(url=url)
    resolved_url = result.resolved_url ?? url
    remaining = result.remaining_calls ?? 0
    if (remaining <= 2) {
        log("WARNING: Only ${remaining} unshorten.me calls remaining this hour")
    }
} catch (e) {
    expansion_error = "${e}"
    log("unshorten.me failed for ${url}: ${e}")
}
```

---

## Rate Limit Management

The unshorten.me free API allows **10 calls per hour** for URLs being resolved for the first time. Previously-resolved URLs are served from cache and do not count against this limit.

<!-- EVIDENCE: https://unshorten.me/api — "limited to specific requests per hour for new short URLs"; https://help.logichub.com/docs/unshortenme — "10 requests per hour for new short URLs. If the URL is already shortened by service, then the result is stored in the database and the API request is unlimited for those URLs." -->

The `remaining_calls` field in each successful `unshorten_url` response tracks how many calls remain in the current hourly window. When the limit is exhausted, subsequent calls for new URLs are expected to fail (the exact error response is undocumented by the API vendor — handle with a catch block like any other API error).

### Rate Limit Conservation: Shortener Domain Pre-filter

Only expand URLs from known shortener domains. Passing a regular URL (e.g., `https://google.com`) works but wastes a rate-limited call — it just resolves to itself. Use this canonical list to pre-filter:

```cy
# Canonical shortener domain list — use regex_match() against the URL
shortener_domains = [
    "bit.ly", "tinyurl.com", "t.co", "goo.gl",
    "ow.ly", "is.gd", "buff.ly", "rebrand.ly",
    "short.io", "cutt.ly", "rb.gy", "t.ly",
    "surl.li", "tiny.cc", "shorturl.at"
]
```

### Conservation Best Practices

1. **Pre-filter** — only expand URLs matching the shortener domain list above
2. **Prioritize** — in batch triage, expand URLs from highest-severity alerts first
3. **Monitor `remaining_calls`** — stop expansion and log a warning when approaching 0
4. **Leverage caching** — if the same short URL appears across multiple alerts, the API caches previous resolutions at no cost

---

## Action: `health_check`

Test connectivity to the unshorten.me API. Internally resolves a known URL to verify the service is reachable.

### Parameters

None.

### Cy Calling Convention

```cy
result = app::unshortenme::health_check()
```

### Success Response Schema

<!-- EVIDENCE: MCP live test — run_integration_tool("unshortenme", "health_check", {}) -->

```json
{
  "status": "success",
  "message": "unshorten.me API is accessible",
  "healthy": true,
  "resolved_url": "https://unshorten.me/"
}
```

| Field | Type | Description |
|---|---|---|
| `status` | string | `"success"` if API is reachable |
| `message` | string | Human-readable status message |
| `healthy` | boolean | `true` if the API responded correctly |
| `resolved_url` | string | The URL resolved during the health check probe |

### Cy Example

```cy
try {
    check = app::unshortenme::health_check()
    if (check.healthy ?? False) {
        log("unshorten.me is available")
    } else {
        log("unshorten.me health check returned unhealthy")
    }
} catch (e) {
    log("unshorten.me is unreachable: ${e}")
}
```

**When to use:** Call `health_check` before a batch of URL expansions to verify the service is up. Since it internally resolves a URL, it may consume one API call against the hourly rate limit — avoid calling it repeatedly.

<!-- Note: The health_check response does not include a remaining_calls field, so we cannot confirm whether it counts against the rate limit. The claim above is a reasonable inference since the health check internally performs a URL resolution. -->
