# Echo EDR Actions Reference

Complete reference for all Echo EDR integration actions. Covers parameters, return schemas, Cy usage examples, and known limitations.

<!-- EVIDENCE: MCP live query — list_integration_tools(echo_edr) -->
<!-- EVIDENCE: MCP live test — run_integration_tool for all 8 actions -->
<!-- EVIDENCE: Source code — src/analysi/integrations/framework/integrations/echo_edr/actions.py -->

## Table of Contents

- [Data Collection Actions](#data-collection-actions)
- [Host Management Actions](#host-management-actions)
- [Common Response Patterns](#common-response-patterns)
- [Known Limitations](#known-limitations)

---

## Data Collection Actions

All four data collection actions (`pull_processes`, `pull_network_connections`, `pull_browser_history`, `pull_terminal_history`) share the same parameter signature and return shape.

**Shared characteristics:**
- **Required param**: `ip` (string) -- endpoint IP address
- **Optional params**: `start_time`, `end_time` (ISO 8601 strings, e.g. `"2025-01-15T10:00:00Z"`)
- **Return shape**: `{records: [...], count: N, ip: "..."}` -- when no data exists, `records` is `[]` and `count` is `0`, with an optional `message` field
- **Retry logic**: 3 attempts with exponential backoff (2-10 seconds)
- **Timeout**: 30 seconds per request
- **404 handling**: Returns empty results with success status (not an error)
- **API path**: `/echo_edr/devices/ip/{ip}/{endpoint}`

**Parameters (all four actions):**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `ip` | string | Yes | IP address of the endpoint |
| `start_time` | string | No | ISO 8601 start time filter |
| `end_time` | string | No | ISO 8601 end time filter |

### Canonical Cy Example (applies to all four pull actions)

This pattern works identically for `pull_processes`, `pull_network_connections`, `pull_browser_history`, and `pull_terminal_history`. Substitute the action name and adjust enrichment field names as needed. For IP extraction logic, see `investigation-patterns.md` section "IP Extraction Patterns".

```cy
ip = input.primary_ioc_value ?? input.network_info.src_ip ?? ""

if (ip == "") {
    return enrich_alert(input, {"status": "skipped", "reason": "no IP available"})
}

try {
    result = app::echo_edr::pull_processes(ip=ip)
    records = result.records ?? []
    record_count = result.count ?? 0
} catch (e) {
    log("Echo EDR pull_processes failed: ${e}")
    return enrich_alert(input, {"status": "error", "reason": "${e}"})
}

enrichment = {
    "target_ip": ip,
    "record_count": record_count,
    "records": records
}
return enrich_alert(input, enrichment)
```

**Time-filtered variant:**
```cy
trigger_time = input.triggering_event_time ?? now()
start = format_timestamp(subtract_duration(trigger_time, "30m"), "iso")
end = format_timestamp(add_duration(trigger_time, "30m"), "iso")

try {
    result = app::echo_edr::pull_processes(ip=ip, start_time=start, end_time=end)
} catch (e) {
    log("Echo EDR pull_processes failed: ${e}")
    result = {"records": [], "count": 0}
}
```

### pull_processes

Retrieve process execution data from an endpoint.

<!-- EVIDENCE: MCP live test — run_integration_tool(pull_processes, {ip: "192.168.1.100"}) returned {records: [], count: 0, ip: "192.168.1.100", message: "No process data found for IP 192.168.1.100"} -->

**Return schema:**
```json
{
  "records": [
    {
      "timestamp": "2025-01-15T10:30:00Z",
      "process_name": "powershell.exe",
      "pid": 1234,
      "parent_process": "explorer.exe",
      "command_line": "powershell.exe -encodedCommand ...",
      "user": "DOMAIN\\john.doe"
    }
  ],
  "count": 1,
  "ip": "192.168.1.100"
}
```

**Time filter field:** `timestamp`

### pull_network_connections

Retrieve network connection records from an endpoint.

<!-- EVIDENCE: MCP live test — run_integration_tool(pull_network_connections, {ip: "192.168.1.100"}) returned {records: [], count: 0} -->

**Return schema:**
```json
{
  "records": [
    {
      "timestamp": "2025-01-15T10:30:00Z",
      "source_ip": "192.168.1.100",
      "dest_ip": "203.0.113.50",
      "dest_port": 443,
      "protocol": "TCP",
      "bytes_sent": 15000,
      "bytes_received": 250000
    }
  ],
  "count": 1,
  "ip": "192.168.1.100"
}
```

**Time filter field:** `timestamp`

### pull_browser_history

Retrieve browser visit history from an endpoint.

<!-- EVIDENCE: MCP live test — run_integration_tool(pull_browser_history, {ip: "192.168.1.100"}) returned {records: [], count: 0} -->

**Return schema:**
```json
{
  "records": [
    {
      "visit_time": "2025-01-15T10:25:00Z",
      "url": "https://malicious-site.example.com/payload",
      "title": "Login Page",
      "browser": "Chrome"
    }
  ],
  "count": 1,
  "ip": "192.168.1.100"
}
```

**Time filter field:** `visit_time` (not `timestamp` -- this is the only pull action that uses a different field)

### pull_terminal_history

Retrieve terminal/command execution history from an endpoint.

<!-- EVIDENCE: MCP live test — run_integration_tool(pull_terminal_history, {ip: "192.168.1.100"}) returned {records: [], count: 0} -->

**Return schema:**
```json
{
  "records": [
    {
      "timestamp": "2025-01-15T10:28:00Z",
      "command": "whoami /all",
      "user": "DOMAIN\\john.doe",
      "working_directory": "C:\\Users\\john.doe",
      "exit_code": 0
    }
  ],
  "count": 1,
  "ip": "192.168.1.100"
}
```

**Time filter field:** `timestamp`

---

## Host Management Actions

These actions operate on hostnames (not IPs). All four are **mock implementations** that return hardcoded responses regardless of input. They exist for workflow scaffolding and will be connected to the real Echo EDR API in a future release.

### get_host_details

Retrieve detailed information about a host. **STATUS: MOCK** -- returns hardcoded data (always `ip_address: "192.168.1.100"`, `os: "Windows 10 Enterprise"`, `risk_level: "low"`) regardless of input hostname.

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `hostname` | string | Yes | Hostname or identifier of the host |

**Return schema (mock):**
```json
{
  "status": "success",
  "hostname": "WORKSTATION-01",
  "ip_address": "192.168.1.100",
  "os": "Windows 10 Enterprise",
  "os_version": "10.0.19044",
  "agent_version": "1.2.3",
  "last_seen": "2026-03-17T21:51:23+00:00",
  "risk_level": "low",
  "timestamp": "2026-03-17T21:51:23+00:00"
}
```

<!-- EVIDENCE: MCP live test — run_integration_tool(get_host_details, {hostname: "WORKSTATION-01"}) returned hardcoded mock with ip_address always "192.168.1.100" -->
<!-- EVIDENCE: Source code confirms: # TODO: Implement actual host details retrieval via Echo EDR API -->

**Cy example:**
```cy
# Derive hostname from username (strip @domain)
username = input.user_info.username ?? ""
hostname_parts = str::split(username, "@")
hostname = hostname_parts[0] ?? ""

if (hostname == "") {
    return enrich_alert(input, {
        "status": "skipped",
        "reason": "no hostname derivable from alert",
        "ai_analysis": {"verdict": "unknown", "reason": "insufficient data"}
    })
}

try {
    host_result = app::echo_edr::get_host_details(hostname=hostname)
} catch (e) {
    log("Echo EDR get_host_details failed: ${e}")
    return enrich_alert(input, {
        "status": "error",
        "reason": "${e}",
        "ai_analysis": {"verdict": "unknown", "reason": "EDR query failed"}
    })
}

# Note: host_result is currently mock data -- interpret accordingly
enrichment = {
    "status": "completed",
    "hostname_checked": hostname,
    "host_details": host_result,
    "mock_warning": "get_host_details returns mock data -- do not use for disposition"
}
return enrich_alert(input, enrichment)
```

### isolate_host

Isolate a host from the network. **STATUS: MOCK** -- returns success message but takes no real action.

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `hostname` | string | Yes | Hostname or identifier to isolate |

**Return schema (mock):**
```json
{
  "status": "success",
  "message": "Host WORKSTATION-01 isolated (mock implementation)",
  "hostname": "WORKSTATION-01",
  "timestamp": "2026-03-17T21:51:52+00:00"
}
```

<!-- EVIDENCE: MCP live test — run_integration_tool(isolate_host, {hostname: "WORKSTATION-01"}) returned mock success -->

**Cy example:**
```cy
# CAUTION: Mock action -- log intent but do not rely on actual isolation
hostname = input.network_info.hostname ?? "unknown_host"

try {
    result = app::echo_edr::isolate_host(hostname=hostname)
    log("Isolation request sent for ${hostname} (mock)")
} catch (e) {
    log("Echo EDR isolate_host failed: ${e}")
    result = {"status": "error", "message": "${e}"}
}

enrichment = {
    "action": "isolate_host",
    "hostname": hostname,
    "result": result,
    "mock_warning": "isolation is mock -- escalate to human operator for real containment"
}
return enrich_alert(input, enrichment)
```

### release_host

Release a host from network isolation. **STATUS: MOCK** -- same mock behavior as `isolate_host`.

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `hostname` | string | Yes | Hostname or identifier to release |

Cy usage is identical to `isolate_host` -- substitute `app::echo_edr::release_host(hostname=hostname)`.

### scan_host

Initiate a security scan on a host. **STATUS: MOCK** -- returns a scan ID but does not trigger a real scan.

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `hostname` | string | Yes | Hostname or identifier to scan |
| `scan_type` | string | No | Type of scan: `"full"` (default), `"quick"`, or `"custom"` |

**Return schema (mock):**
```json
{
  "status": "success",
  "message": "Full scan initiated on WORKSTATION-01 (mock implementation)",
  "hostname": "WORKSTATION-01",
  "scan_type": "full",
  "scan_id": "scan-1773784305.190836",
  "timestamp": "2026-03-17T21:51:45+00:00"
}
```

<!-- EVIDENCE: MCP live test — run_integration_tool(scan_host, {hostname: "WORKSTATION-01", scan_type: "quick"}) returned mock scan_id -->

**Cy example:**
```cy
hostname = input.network_info.hostname ?? "unknown_host"

try {
    scan_result = app::echo_edr::scan_host(hostname=hostname, scan_type="quick")
    scan_id = scan_result.scan_id ?? "none"
    log("Scan initiated: ${scan_id} (mock)")
} catch (e) {
    log("Echo EDR scan_host failed: ${e}")
    scan_result = {"status": "error", "message": "${e}"}
}
```

---

## Common Response Patterns

### Empty results (no data for IP)

All `pull_*` actions return this when the Echo EDR server has no data for the queried IP (HTTP 404 from server, surfaced as success with empty records):

```json
{
  "records": [],
  "count": 0,
  "ip": "192.168.1.100",
  "message": "No process data found for IP 192.168.1.100"
}
```

This is a success response, not an error. The `message` field is present only when records are empty. An empty result often means the IP is external or unmonitored -- itself a useful finding during triage.

### Error responses

Errors raise exceptions in Cy. The integration handles three error classes internally:
- **TimeoutError**: 30-second timeout exceeded (after 3 retries)
- **ConnectionError**: Echo EDR server unreachable
- **HTTPError**: Non-200/404 response codes

Always wrap calls in `try/catch`. See the canonical example above and `investigation-patterns.md` for full error-handling patterns.

---

## Known Limitations

- **Mock host management actions**: `get_host_details`, `isolate_host`, `release_host`, `scan_host` return hardcoded data. Do not use their output for TP/FP disposition decisions. Use them for workflow scaffolding only.
- **No hostname-based telemetry**: All `pull_*` actions require an IP address. To get telemetry for a hostname, resolve it to an IP first (e.g., via DNS or AD LDAP lookup).
- **Client-side time filtering**: Time range filtering on `pull_*` actions fetches all records first, then filters locally. For endpoints with high activity volumes, expect higher latency and memory use.
- **Browser history time field differs**: `pull_browser_history` filters on `visit_time`; all other pull actions filter on `timestamp`. If your records lack the expected field, all records pass through the filter unfiltered.
- **No pagination**: Pull actions return all matching records in a single response. There is no offset/limit parameter. For high-volume endpoints, truncate records before passing to `llm_run()` to avoid context-window overflow (see `investigation-patterns.md` section "Large Result Sets").
- **Retry overhead**: Each action retries up to 3 times with exponential backoff (2-10s). A single failed call can take up to ~50 seconds (30s timeout x 3 retries with waits) before the exception surfaces.
