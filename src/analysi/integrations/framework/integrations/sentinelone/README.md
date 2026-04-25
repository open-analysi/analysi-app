# SentinelOne Integration

SentinelOne Singularity platform integration for EDR/XDR operations including endpoint management, threat response, and forensics.

## Overview

This integration provides comprehensive EDR/XDR capabilities through the SentinelOne Singularity platform API v2.1. It supports endpoint isolation, threat mitigation, scanning, and threat analysis operations.

## Archetype

- **EDR (Endpoint Detection and Response)**

## Authentication

Requires SentinelOne API credentials:
- `console_url`: SentinelOne Console URL (e.g., https://your-mgmt.sentinelone.net)
- `api_token`: SentinelOne API Token

## Actions

### Endpoint Management
- **isolate_host**: Isolate/quarantine a device from the network
- **release_host**: Release a device from isolation/quarantine
- **scan_host**: Initiate a scan on an endpoint
- **abort_scan**: Abort a running scan on an endpoint
- **shutdown_endpoint**: Shutdown an endpoint remotely
- **get_host_details**: Get detailed information about an endpoint
- **broadcast_message**: Send a broadcast message to an endpoint

### Threat Response
- **block_hash**: Add a file hash to the global blocklist
- **unblock_hash**: Remove a file hash from the global blocklist
- **mitigate_threat**: Mitigate a threat (kill, quarantine, remediate, rollback, un-quarantine)

### Threat Analysis
- **get_threat_info**: Get detailed information about a threat
- **hash_reputation**: Get reputation information for a file hash
- **get_threat_notes**: Get notes associated with a threat
- **add_threat_note**: Add a note to one or more threats
- **update_threat_analyst_verdict**: Update the analyst verdict for a threat
- **update_threat_incident**: Update threat incident status and analyst verdict

## Archetype Mappings

The integration maps to the EDR archetype with the following abstract actions:

- `isolate_host` → SentinelOne isolate_host
- `release_host` → SentinelOne release_host
- `scan_host` → SentinelOne scan_host
- `get_host_details` → SentinelOne get_host_details
- `kill_process` → SentinelOne mitigate_threat (with action="kill")
- `quarantine_file` → SentinelOne block_hash
- `collect_forensics` → SentinelOne get_threat_info

## Configuration

### Settings
- `timeout`: Request timeout in seconds (default: 120, range: 30-300)

### Credentials
- `console_url`: SentinelOne Console URL (required)
- `api_token`: SentinelOne API Token (required, password format)

## Examples

### Isolate an Endpoint
```python
await isolate_host_action.execute(ip_hostname="192.168.1.100")
```

### Block a Malicious Hash
```python
await block_hash_action.execute(
    hash="abc123def456...",
    description="Blocked via security investigation",
    os_family="windows"
)
```

### Mitigate a Threat
```python
await mitigate_threat_action.execute(
    s1_threat_id="threat_12345",
    action="quarantine"
)
```

### Update Threat Verdict
```python
await update_threat_analyst_verdict_action.execute(
    s1_threat_id="threat_12345",
    analyst_verdict="true_positive"
)
```

## Migration Notes

- ✅ Endpoint isolation and release
- ✅ Scanning and scan management
- ✅ Threat mitigation (kill, quarantine, remediate)
- ✅ Hash blocking/unblocking
- ✅ Threat analysis and intelligence
- ✅ Endpoint information retrieval
- ✅ Threat notes and incident management

Actions not migrated (optional upstream-specific or deprecated):
- fetch_files (requires advanced file retrieval)
- fetch_firewall_rules/logs (use get_firewall_rules instead)
- get_applications, get_cves (application-specific queries)
- create_firewall_rule, get_firewall_rules (network security subset)
- export_threat_timeline, export_mitigation_report (export operations)
- fetch_threat_file, download_from_cloud (file operations)
- on_poll (upstream ingestion mechanism)

## Dependencies

- httpx (async HTTP client)
- tenacity (retry logic)

## API Version

SentinelOne API v2.1
