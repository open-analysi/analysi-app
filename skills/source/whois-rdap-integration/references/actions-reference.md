# WHOIS RDAP Actions Reference

<!-- EVIDENCE: MCP live query — list_integration_tools(integration_type="whois_rdap") -->

Two actions available: `health_check` and `whois_ip`.

---

## `health_check`

**Purpose:** Verify RDAP connectivity by querying 8.8.8.8 (Google DNS).

**Parameters:** None.

**Cy Usage:**
```cy
try {
    status = app::whois_rdap::health_check()
} catch (e) {
    log("WHOIS RDAP health check failed: ${e}")
    return enrich_alert(input, {"whois_healthy": False, "error": "${e}"})
}
# status.healthy == True means RDAP is reachable
```

<!-- EVIDENCE: MCP live test — run_integration_tool("whois-rdap", "health_check", {}) -->

**Response shape:**
```json
{
  "healthy": true,
  "test_ip": "8.8.8.8",
  "asn": "15169",
  "asn_registry": "arin"
}
```

| Field | Type | Description |
|---|---|---|
| `healthy` | boolean | `true` if RDAP responded successfully |
| `test_ip` | string | Always `"8.8.8.8"` |
| `asn` | string | ASN number as string (e.g., `"15169"`) |
| `asn_registry` | string | RIR that owns this block (`"arin"`, `"ripencc"`, `"apnic"`, `"afrinic"`, `"lacnic"`) |

**Typical latency:** ~900ms.

---

## `whois_ip`

**Purpose:** Look up WHOIS registration data for an IPv4 or IPv6 address via RDAP.

**Parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `ip` | string | Yes | IPv4 or IPv6 address (e.g., `"8.8.8.8"` or `"2001:4860:4860::8888"`) |

### Standard IP Extraction and Call Pattern

This is the canonical pattern for calling `whois_ip` in any Cy task. All investigation patterns in `investigation-patterns.md` follow this structure:

```cy
# Standard IP extraction — always use these fallbacks
ip = input.primary_ioc_value ?? input.network_info.src_ip ?? "0.0.0.0"

# Guard: skip when no usable IP
if (ip == "0.0.0.0") {
    return enrich_alert(input, {"whois_result": "no_ip_available"})
}

# Call with try/catch — RDAP errors should not crash triage
try {
    rdap = app::whois_rdap::whois_ip(ip=ip)
} catch (e) {
    log("WHOIS RDAP lookup failed for ${ip}: ${e}")
    return enrich_alert(input, {"whois_error": "${e}", "ip": ip})
}

# Handle null return (private/reserved IPs — see Edge Cases below)
if (rdap == null) {
    return enrich_alert(input, {"whois_result": "private_or_reserved", "ip": ip})
}

# Extract key fields
org = rdap.asn_description ?? "unknown"
cidr = rdap.asn_cidr ?? "unknown"
country = rdap.asn_country_code ?? "unknown"
asn = rdap.asn ?? "unknown"
netblock_name = rdap.network.name ?? "unknown"
```

### IPv6 Support

IPv6 addresses produce the same response schema as IPv4 — all field names and nesting are identical. The only differences:
- `network.ip_version` will be `"v6"` instead of `"v4"`
- CIDR blocks will be larger (e.g., `/48` or `/32` rather than `/24`)
- IPv6 blocks are predominantly served by RIPE and APNIC, which tend to have faster response times

No special handling is needed — use the same extraction pattern for both address families.

### Response Schema

<!-- EVIDENCE: MCP live test — run_integration_tool("whois-rdap", "whois_ip", {"ip": "8.8.8.8"}) -->
<!-- EVIDENCE: MCP live test — run_integration_tool("whois-rdap", "whois_ip", {"ip": "185.220.101.45"}) -->

#### Top-Level Fields

| Field | Type | Description | Example |
|---|---|---|---|
| `query` | string | The IP that was looked up | `"8.8.8.8"` |
| `asn` | string | Autonomous System Number | `"15169"` |
| `asn_cidr` | string | CIDR block for the ASN allocation | `"8.8.8.0/24"` |
| `asn_country_code` | string | Two-letter country code of ASN registration | `"US"` |
| `asn_date` | string | Date ASN was allocated (YYYY-MM-DD). A very recent date can indicate freshly provisioned infrastructure — worth flagging during triage | `"2023-12-28"` |
| `asn_description` | string | ASN org name and country. See `investigation-patterns.md` § Field Interpretation Guide for SOC-specific interpretation | `"GOOGLE - Google LLC, US"` |
| `asn_registry` | string | Regional Internet Registry | `"arin"`, `"ripencc"`, `"apnic"` |
| `nir` | null/string | National Internet Registry (usually `null`) | `null` |
| `network` | object | Detailed netblock information | See below |
| `entities` | array[string] | Entity handles referenced | `["GOGL"]` |
| `objects` | array[object] | Full entity details (registrant, abuse, tech contacts) | See below |
| `raw` | null | Raw WHOIS text (always `null` for RDAP) | `null` |

#### `network` Object

| Field | Type | Description | Example |
|---|---|---|---|
| `handle` | string | Network registration handle | `"NET-8-8-8-0-2"` |
| `name` | string | Network name | `"GOGL"`, `"TOR-EXIT"` |
| `cidr` | string | Exact CIDR of this netblock | `"8.8.8.0/24"` |
| `start_address` | string | First IP in block | `"8.8.8.0"` |
| `end_address` | string | Last IP in block | `"8.8.8.255"` |
| `ip_version` | string | `"v4"` or `"v6"` | `"v4"` |
| `type` | string | Allocation type | `"DIRECT ALLOCATION"`, `"ASSIGNED PA"` |
| `country` | string/null | Country (often `null` for ARIN; populated for RIPE) | `"DE"` |
| `status` | array[string] | Registration status | `["active"]` |
| `parent_handle` | string | Parent netblock handle | `"NET-8-0-0-0-0"` |
| `remarks` | array/null | Free-text registrant remarks. Can contain SOC-relevant signals — Tor exit notices, abuse reporting info, VPN/proxy descriptions. See `investigation-patterns.md` § `network.remarks` Signals for interpretation guidance | |
| `events` | array[object] | Registration and last-changed timestamps | `[{"action": "registration", "timestamp": "..."}]` |
| `links` | array[string] | RDAP/WHOIS reference URLs | |

#### `objects` Array (Entity Details)

Each object represents a registrant, admin, tech, or abuse contact:

| Field | Type | Description |
|---|---|---|
| `handle` | string | Entity handle (e.g., `"GOGL"`, `"ABUSE5250-ARIN"`) |
| `roles` | array[string] | Entity roles: `"registrant"`, `"administrative"`, `"technical"`, `"abuse"`, `"noc"` |
| `contact.name` | string | Organization or person name |
| `contact.kind` | string | `"org"`, `"individual"`, or `"group"` |
| `contact.address` | array/null | Postal addresses |
| `contact.phone` | array/null | Phone numbers |
| `contact.email` | array/null | Email addresses (often populated for abuse contacts) |
| `remarks` | array/null | Registration comments (abuse reporting URLs, etc.) |
| `entities` | array/null | Sub-entity handles |

### Extracting Abuse Contact

The abuse contact email is buried in the `objects` array. Here's how to extract it:

```cy
# Find abuse contact from RDAP objects
abuse_email = ""
objects = rdap.objects ?? []
for (obj in objects) {
    roles = obj.roles ?? []
    found_abuse = False
    for (role in roles) {
        if (role == "abuse") {
            found_abuse = True
        }
    }
    if (found_abuse) {
        emails = obj.contact.email ?? []
        for (em in emails) {
            abuse_email = em.value ?? ""
        }
    }
}
```

### Extracting Registrant Organization

```cy
# Find the registrant org name
registrant_name = ""
objects = rdap.objects ?? []
for (obj in objects) {
    roles = obj.roles ?? []
    found_registrant = False
    for (role in roles) {
        if (role == "registrant") {
            found_registrant = True
        }
    }
    if (found_registrant and obj.contact.kind == "org") {
        registrant_name = obj.contact.name ?? ""
    }
}
# Falls back to asn_description if no org-type registrant found
registrant_name = if (registrant_name == "") { rdap.asn_description ?? "unknown" } else { registrant_name }
```

### Edge Cases and Error Behavior

<!-- EVIDENCE: MCP live test — run_integration_tool("whois-rdap", "whois_ip", {"ip": "192.168.1.1"}) -->
<!-- EVIDENCE: MCP live test — run_integration_tool("whois-rdap", "whois_ip", {"ip": "not-an-ip"}) -->
<!-- EVIDENCE: MCP live test — run_integration_tool("whois-rdap", "whois_ip", {"ip": ""}) -->

This is the canonical reference for how `whois_ip` handles non-standard inputs. Private/reserved IPs (10.x, 172.16-31.x, 192.168.x, 127.x) are the most common case — the action returns `null` without throwing, so always check before accessing fields.

| Input | Behavior | How to Handle |
|---|---|---|
| Valid public IPv4 (e.g., `8.8.8.8`) | Full RDAP response | Normal processing |
| Valid public IPv6 (e.g., `2001:4860:4860::8888`) | Full RDAP response (same schema) | Normal processing |
| Private/reserved IP (`192.168.1.1`, `10.0.0.1`, `127.0.0.1`) | Returns `null` (no error thrown) | Check `if (rdap == null)` before accessing fields |
| Invalid string (`"not-an-ip"`) | Throws error: `"Invalid IP address: not-an-ip"` | Caught by `try/catch` |
| Empty string (`""`) | Throws error: `"Missing required parameter: ip"` | Caught by `try/catch` |
| Default fallback IP (`"0.0.0.0"`) | May return `null` or minimal data | Treat same as private IP |

**Typical latency:** 400ms–1100ms depending on which RIR serves the response (RIPE tends to be faster than ARIN).

### Known Limitations

- **Country field inconsistency:** `network.country` is `null` for ARIN registrations but populated for RIPE. Always prefer `asn_country_code` (top-level) which is consistently populated across all RIRs.
- **Contact email redaction:** Many RIRs redact email/phone from RDAP responses. The abuse contact email is most reliably populated; registrant emails are often `null`. Don't rely on email presence for investigation logic.
- **No historical data:** RDAP returns current registration only. For historical WHOIS, use a dedicated historical WHOIS service (not available in this integration).

### Complete Enrichment Example

This full example combines the standard call pattern, remarks extraction, and abuse contact extraction into a production-ready task:

```cy
ip = input.primary_ioc_value ?? input.network_info.src_ip ?? "0.0.0.0"
alert_context = input.enrichments.alert_context_generation.ai_analysis ?? input.title ?? "unknown alert"

if (ip == "0.0.0.0") {
    return enrich_alert(input, {"whois_result": "no_ip_available"})
}

try {
    rdap = app::whois_rdap::whois_ip(ip=ip)
} catch (e) {
    log("WHOIS RDAP failed for ${ip}: ${e}")
    return enrich_alert(input, {"whois_error": "${e}", "ip": ip})
}

if (rdap == null) {
    return enrich_alert(input, {"whois_result": "private_or_reserved", "ip": ip})
}

# Extract network remarks for Tor/hosting signals
network_remarks = ""
remarks_list = rdap.network.remarks ?? []
for (remark in remarks_list) {
    network_remarks = network_remarks + (remark.description ?? "")
}

# Extract abuse email (see § Extracting Abuse Contact for the pattern)
abuse_email = ""
objects = rdap.objects ?? []
for (obj in objects) {
    roles = obj.roles ?? []
    is_abuse = False
    for (role in roles) {
        if (role == "abuse") {
            is_abuse = True
        }
    }
    if (is_abuse) {
        emails = obj.contact.email ?? []
        for (em in emails) {
            abuse_email = em.value ?? ""
        }
    }
}

enrichment = {
    "ip": ip,
    "asn": rdap.asn ?? "unknown",
    "asn_description": rdap.asn_description ?? "unknown",
    "asn_cidr": rdap.asn_cidr ?? "unknown",
    "asn_country_code": rdap.asn_country_code ?? "unknown",
    "asn_registry": rdap.asn_registry ?? "unknown",
    "network_name": rdap.network.name ?? "unknown",
    "network_cidr": rdap.network.cidr ?? "unknown",
    "network_type": rdap.network.type ?? "unknown",
    "network_remarks": network_remarks,
    "abuse_email": abuse_email
}

return enrich_alert(input, enrichment)
```
