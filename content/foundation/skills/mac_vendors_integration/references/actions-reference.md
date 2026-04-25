# MAC Vendors — Actions Reference

## Integration Overview

- **Integration type**: `mac_vendors`
- **Instance ID**: `mac-vendors`
- **Cy namespace**: `app::mac_vendors::`
- **Auth**: Works without credentials (free tier). Optional API key for higher rate limits.
- **Rate limit**: 1,000 requests/day (free tier). See SKILL.md § Guardrails for full constraint details.

---

## Action: `lookup_mac`

Resolve a MAC address to its registered manufacturer via OUI prefix lookup.

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `mac` | string | Yes | MAC address in any standard format |

**Accepted formats** (all resolve correctly):
- Colon-separated: `d0:a6:37:aa:bb:cc`
- Dash-separated: `00-0C-29-BB-47-4D`
- Raw OUI prefix: `D0A637` (first 3 octets only)

### Response Schema

<!-- EVIDENCE: MCP live test — run_integration_tool("lookup_mac", {mac: "d0:a6:37:aa:bb:cc"}) -->

**Successful lookup (vendor found):**
```json
{
  "status": "success",
  "vendor_found": true,
  "mac": "d0:a6:37:aa:bb:cc",
  "vendor": "Apple, Inc."
}
```

**Successful lookup (vendor NOT found):**
```json
{
  "status": "success",
  "vendor_found": false,
  "not_found": true,
  "mac": "FF:FF:FF:FF:FF:FF",
  "vendor": null
}
```

<!-- EVIDENCE: MCP live test — run_integration_tool("lookup_mac", {mac: ""}) -->

**Validation error (empty string):**
Raises an exception with `error_type: "ValidationError"` and message `"Missing required parameter: mac"`.

### Response Fields

| Field | Type | Present | Description |
|---|---|---|---|
| `status` | string | Always | `"success"` or `"error"` |
| `vendor_found` | boolean | On success | `true` if OUI maps to a registered vendor |
| `mac` | string | On success | The MAC address as submitted (not normalized) |
| `vendor` | string or null | On success | Manufacturer name, or `null` if not found |
| `not_found` | boolean | Sometimes | Present and `true` only when vendor is not found |

### Key Behaviors

<!-- EVIDENCE: MCP live test — tested all formats below -->

- **Format flexibility**: Accepts colon (`:`), dash (`-`), and raw hex formats. Case-insensitive.
- **Return format preserved**: The API echoes back the MAC in the format you submitted — it does not normalize. If you need consistent format for downstream comparison, normalize before storing (see § MAC Format Normalization below).
- **Invalid MAC strings**: Do NOT throw errors. The API returns `vendor_found: false` with `vendor: null` (e.g., `"invalid-mac"` returns gracefully).
- **Empty string**: Throws a `ValidationError` exception — always validate input before calling.
- **Broadcast address** (`FF:FF:FF:FF:FF:FF`): Returns `vendor_found: false` — not mapped to a vendor.
- **All-zeros** (`00:00:00:00:00:00`): Returns `vendor_found: true`, vendor `"XEROX CORPORATION"` (historical OUI assignment).
- **Locally administered MACs**: Addresses with the locally-administered bit set (second hex digit is 2, 6, A, or E, e.g., `x2:xx:xx:...`) return `vendor_found: false`. This is the expected behavior for randomized MACs (iOS 14+, Android 10+, Windows 10+) — see `investigation-patterns.md` § MAC Address Randomization for triage guidance.

### MAC Format Normalization

The API echoes the MAC in whatever format you send. If your workflow compares MACs across enrichments from different sources (e.g., alert source uses dashes, DHCP logs use colons), normalize to a canonical format before storing:

```cy
# Normalize MAC to lowercase colon-separated format
# Input: any of "D0:A6:37:AA:BB:CC", "D0-A6-37-AA-BB-CC", "D0A637AABBCC"
raw_mac = input.network_info.src_mac ?? ""
normalized = lowercase(replace(replace(raw_mac, "-", ":"), ".", ":"))
# Result: "d0:a6:37:aa:bb:cc"
```

Use this before storing MAC values in enrichment dicts so downstream tasks can reliably compare them with `==`.

### Cy Example — Single MAC Lookup (Canonical Pattern)

This is the base lookup pattern. Investigation patterns in `investigation-patterns.md` extend this with LLM reasoning, Splunk corroboration, etc.

```cy
mac_addr = input.network_info.src_mac ?? ""

if (mac_addr == "") {
    return enrich_alert(input, {
        "status": "skipped",
        "reason": "no MAC address available",
        "ai_analysis": "No MAC address found in alert — skipping vendor lookup."
    })
}

try {
    result = app::mac_vendors::lookup_mac(mac=mac_addr)
} catch (e) {
    return enrich_alert(input, {
        "status": "error",
        "error": "${e}",
        "ai_analysis": "MAC vendor lookup failed: ${e}"
    })
}

vendor = result.vendor ?? "unknown"
found = result.vendor_found ?? False

enrichment = {
    "mac": mac_addr,
    "vendor": vendor,
    "vendor_found": found,
    "ai_analysis": if (found) {
        "MAC ${mac_addr} belongs to ${vendor}."
    } else {
        "MAC ${mac_addr} has no registered OUI vendor — may be a randomized or locally administered address."
    }
}

return enrich_alert(input, enrichment)
```

### Cy Example — Batch MAC Lookup

```cy
# Extract multiple MACs from alert (adapt field path to your NAS schema)
mac_list = input.network_info.mac_addresses ?? []

results = []
errors = []

for (mac_addr in mac_list) {
    try {
        result = app::mac_vendors::lookup_mac(mac=mac_addr)
        results = results + [{
            "mac": mac_addr,
            "vendor": result.vendor ?? "unknown",
            "vendor_found": result.vendor_found ?? False
        }]
    } catch (e) {
        errors = errors + [{"mac": mac_addr, "error": "${e}"}]
    }
}

enrichment = {
    "lookups": results,
    "errors": errors,
    "total": len(mac_list),
    "resolved": len(results),
    "ai_analysis": "Resolved ${len(results)}/${len(mac_list)} MAC addresses to vendors."
}

return enrich_alert(input, enrichment)
```

**Rate limit note**: The for-in loop auto-parallelizes. For large MAC lists, deduplicate by OUI prefix first — see `investigation-patterns.md` § Rate Limit Management for the dedup pattern.

---

## Action: `health_check`

Verify connectivity to the MAC Vendors API. Queries a known MAC (VMware OUI) and checks for a valid response.

### Parameters

None.

### Response Schema

<!-- EVIDENCE: MCP live test — run_integration_tool("health_check", {}) -->

```json
{
  "vendor": "VMware, Inc."
}
```

**Note**: The health_check response schema differs from `lookup_mac` — it returns only a `vendor` string field, not the full `status`/`vendor_found`/`mac` structure.

### Cy Example — Health Check

```cy
try {
    hc = app::mac_vendors::health_check()
    healthy = (hc.vendor ?? "") != ""
} catch (e) {
    healthy = False
}

return {"healthy": healthy}
```

Use this before batch operations to confirm the API is reachable and responding.
