# Palo Alto Cortex XDR Integration

Enterprise XDR (Extended Detection and Response) platform integration for Palo Alto Cortex XDR.

## Archetype

**EDR** (Endpoint Detection and Response)

## Overview

Cortex XDR provides comprehensive endpoint security, incident management, threat hunting, and response capabilities. This integration supports both standard and advanced authentication modes.

## Authentication

### Standard Authentication
- **API Key**: Your Cortex XDR API key
- **API Key ID**: Your API key identifier
- **FQDN**: Your Cortex XDR server FQDN (e.g., `acme.xdr.us.paloaltonetworks.com`)

### Advanced Authentication
Enable advanced authentication in settings to use nonce + timestamp hashing for enhanced security.

## Supported Actions

### Endpoint Management (5 actions)
- **list_endpoints**: List all managed endpoints
- **get_policy**: Get policy applied to an endpoint
- **quarantine_device**: Isolate endpoint from network
- **unquarantine_device**: Release endpoint from isolation
- **scan_endpoint**: Run security scan on endpoint

### File Operations (4 actions)
- **retrieve_file**: Retrieve files from endpoint for forensic analysis
- **retrieve_file_details**: Get details of retrieved files
- **quarantine_file**: Quarantine malicious file on endpoint
- **unquarantine_file**: Restore quarantined file

### IOC Management (2 actions)
- **block_hash**: Add file hash to blocklist
- **allow_hash**: Add file hash to allowlist

### Incident Management (3 actions)
- **get_incidents**: List security incidents with filters
- **get_incident_details**: Get detailed incident information
- **get_alerts**: List security alerts with filters

### Utilities (2 actions)
- **get_action_status**: Check status of async actions
- **cancel_scan_endpoint**: Cancel running endpoint scan

### Monitoring (1 action)
- **health_check**: Test API connectivity

## Archetype Mappings

| Abstract Action | Cortex XDR Action |
|----------------|-------------------|
| `isolate_host` | `quarantine_device` |
| `release_host` | `unquarantine_device` |
| `scan_host` | `scan_endpoint` |
| `get_host_details` | `list_endpoints` |
| `quarantine_file` | `quarantine_file` |
| `collect_forensics` | `retrieve_file` |

## Dependencies

- `httpx`: Async HTTP client for API requests
- Standard library: `hashlib`, `secrets`, `datetime`

## Settings

- **timeout**: Request timeout in seconds (default: 30)
- **advanced**: Enable advanced authentication with nonce/timestamp hashing (default: false)

## Notes

- All actions return structured responses with `status`, `error_type`, and relevant data fields
- Advanced authentication generates SHA256 hashes with nonce and timestamp for enhanced security
- File operations support Windows, Linux, and macOS path specifications
- Incident and alert queries support flexible filtering by time, ID, status, and severity
