# Tor Integration — Actions Reference

## Integration Metadata

| Field | Value |
|---|---|
| Integration ID (instance) | `tor` |
| Integration type (for Cy) | `tor` |
| Authentication | None required |
| Data source | Tor Project public exit node list (`check.torproject.org/exit-addresses`) |
| Rate limits | None enforced by the integration; subject to Tor Project endpoint availability |
| Typical response time | ~800ms per call (single or batch) |

<!-- EVIDENCE: MCP live query — list_integration_tools({integration_type: "tor"}) -->

---

## Action: `lookup_ip`

Check whether one or more IPs appear on the current Tor exit node list.

<!-- EVIDENCE: MCP live test — run_integration_tool("tor", "lookup_ip", {ip: "185.220.101.45"}) -->
<!-- EVIDENCE: MCP live test — run_integration_tool("tor", "lookup_ip", {ip: "8.8.8.8"}) -->
<!-- EVIDENCE: MCP live test — run_integration_tool("tor", "lookup_ip", {ip: "not-an-ip"}) -->

### Parameters

| Name | Type | Required | Description |
|---|---|---|---|
| `ip` | string | Yes | Single IPv4 address or comma-separated list (e.g., `"1.2.3.4,5.6.7.8"`) |

### Response Schema

```json
{
  "status": "success",
  "results": [
    {
      "ip": "185.220.101.45",
      "is_exit_node": true
    }
  ],
  "num_exit_nodes": 1
}
```

| Field | Type | Description |
|---|---|---|
| `status` | string | `"success"` on normal return |
| `results` | array | One entry per queried IP |
| `results[].ip` | string | The IP that was checked |
| `results[].is_exit_node` | boolean | `true` if IP is a current Tor exit node |
| `num_exit_nodes` | integer | Count of IPs in `results` where `is_exit_node == true` |

### Cy Examples

**Minimal single-IP call** (use this as the base pattern; see `investigation-patterns.md` for full task templates with LLM reasoning):

```cy
ip = input.primary_ioc_value ?? input.network_info.src_ip ?? "0.0.0.0"

tor_result = {}
try {
    tor_result = app::tor::lookup_ip(ip=ip)
} catch (e) {
    log("Tor lookup failed: ${e}")
    tor_result = {"results": [], "num_exit_nodes": 0}
}

is_tor = False
if (len(tor_result.results ?? []) > 0) {
    is_tor = (tor_result.results[0].is_exit_node) ?? False
}
```

**Batch lookup** (comma-separated IPs in a single call):

```cy
src_ip = input.network_info.src_ip ?? ""
dst_ip = input.network_info.dst_ip ?? ""

ip_list = ""
if (src_ip != "" and dst_ip != "") {
    ip_list = src_ip + "," + dst_ip
} elif (src_ip != "") {
    ip_list = src_ip
} elif (dst_ip != "") {
    ip_list = dst_ip
}

tor_result = {}
try {
    tor_result = app::tor::lookup_ip(ip=ip_list)
} catch (e) {
    log("Tor batch lookup failed: ${e}")
    tor_result = {"results": [], "num_exit_nodes": 0}
}

tor_ips = [r.ip for(r in (tor_result.results ?? [])) if(r.is_exit_node == True)]
```

### Edge Cases

<!-- EVIDENCE: MCP live test — run_integration_tool("tor", "lookup_ip", {ip: ""}) -->
<!-- EVIDENCE: MCP live test — run_integration_tool("tor", "lookup_ip", {ip: "not-an-ip"}) -->

| Input | Behavior |
|---|---|
| Valid Tor exit node IP | `is_exit_node: true` |
| Valid non-Tor IP (e.g., `8.8.8.8`) | `is_exit_node: false` |
| Comma-separated list | Returns one result per IP; `num_exit_nodes` counts matches |
| Empty string `""` | Throws exception: `"Missing required parameter: ip"` |
| Invalid string (e.g., `"not-an-ip"`) | Returns `is_exit_node: false` — **no validation error**. Indistinguishable from a legitimate non-Tor IP. Use `is_ipv4(ip)` before calling if precision matters. |
| IPv6 address | Returns `is_exit_node: false` — the exit list is IPv4 only. See Known Limitations. |

---

## Action: `health_check`

Verify that the Tor exit node list endpoint is reachable and report the current node count.

<!-- EVIDENCE: MCP live test — run_integration_tool("tor", "health_check", {}) -->

### Parameters

None.

### Response Schema

```json
{
  "healthy": true,
  "exit_node_count": 3093,
  "source_url": "https://check.torproject.org/exit-addresses"
}
```

| Field | Type | Description |
|---|---|---|
| `healthy` | boolean | `true` if the endpoint responded and the list was parsed |
| `exit_node_count` | integer | Number of unique exit node IPs currently in the list |
| `source_url` | string | URL of the Tor Project exit address list |

### Cy Example

```cy
health = {}
try {
    health = app::tor::health_check()
} catch (e) {
    log("Tor health check failed: ${e}")
    return enrich_alert(input, {"tor_available": False, "ai_analysis": ""})
}

tor_available = health.healthy ?? False
node_count = health.exit_node_count ?? 0
log("Tor integration healthy=${tor_available}, exit_nodes=${node_count}")
```

### When to Use

- Before batch-processing many alerts to confirm the data source is live.
- As a pre-flight check in workflows where Tor status is critical to disposition — if the list is down, skip Tor enrichment rather than fail the pipeline. See `investigation-patterns.md` § Pattern 4 for the full pre-flight pattern.
- The `exit_node_count` field (typically 3,000–4,500 — fluctuates as relays rotate) provides a sanity check: if it drops to 0, the data source is likely broken.

<!-- EVIDENCE: MCP live test returned exit_node_count: 3093. Tor Metrics (metrics.torproject.org) reports the count fluctuates between ~3,000 and ~4,500 depending on relay churn. -->

---

## Known Limitations

This is the canonical location for all behavioral caveats. SKILL.md and investigation-patterns.md reference this section rather than restating these facts.

- **Current state only** — the list reflects exit nodes active *right now*. Tor nodes rotate frequently (hours to days), so an IP that was an exit node during the alert timeframe may already have rotated off. For historical Tor attribution, correlate with Splunk logs or third-party threat intel feeds that archive Tor node history.
- **IPv4 only** — the Tor Project exit address list covers IPv4 exclusively. IPv6 Tor exit nodes (rare but possible) are not covered. When an alert contains an IPv6 source IP, skip the Tor check for that IP and log a note — don't pass it to `lookup_ip` (it will silently return `false`, which is misleading). See `investigation-patterns.md` § IPv6 Handling for a Cy pattern.
- **No input validation** — invalid IP formats (e.g., `"not-an-ip"`) silently return `is_exit_node: false` rather than raising an error. This is indistinguishable from a legitimate non-Tor IP. Validate with `is_ipv4(ip)` in Cy before calling if your logic needs to differentiate "not Tor" from "bad input."
- **No relay type distinction** — the list covers exit nodes only. Guard relays, middle relays, and bridges are not included. For outbound-to-Tor detection (internal host connecting to Tor), you need a different data source that tracks entry/guard nodes.
- **Bulk API alternative** — the Tor Project also offers a structured bulk endpoint at `check.torproject.org/api/bulk`. This integration uses the `exit-addresses` flat file, not the bulk API. The practical difference is minimal for per-IP lookups — the integration caches and parses the list internally.
