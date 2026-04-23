# NetWitness Endpoint Integration

RSA NetWitness Endpoint is an EDR (Endpoint Detection and Response) platform for threat detection, investigation, and response.

## Overview

This integration provides endpoint management, scanning, IOC (Indicator of Compromise) tracking, and threat blocklisting capabilities through the NetWitness Endpoint REST API.

## Authentication

Uses HTTP Basic Authentication with username and password.

**Required Credentials:**
- `url`: NetWitness Endpoint server URL (e.g., https://netwitness.company.com)
- `username`: Username for authentication
- `password`: Password for authentication
- `verify_server_cert`: (Optional) Verify SSL certificate (default: false)

## Actions

### Health Check
- **ID**: `health_check`
- **Type**: Connector (health monitoring)
- **Description**: Tests connectivity to the NetWitness Endpoint API

### Blocklist Domain
- **ID**: `blocklist_domain`
- **Type**: Tool
- **Description**: Add a domain to the blocklist
- **Categories**: containment, network_security
- **Parameters**:
  - `domain` (required): Domain to blocklist

### Blocklist IP
- **ID**: `blocklist_ip`
- **Type**: Tool
- **Description**: Add an IP address to the blocklist
- **Categories**: containment, network_security
- **Parameters**:
  - `ip` (required): IP address to blocklist

### List Endpoints
- **ID**: `list_endpoints`
- **Type**: Tool
- **Description**: List all Windows endpoints configured on NetWitness Endpoint
- **Categories**: investigation, asset_management
- **Parameters**:
  - `ioc_score_gte` (optional): Minimum IOC score (default: 0)
  - `ioc_score_lte` (optional): Maximum IOC score (default: 1024)
  - `limit` (optional): Maximum number of endpoints (default: 50)

### Get System Info
- **ID**: `get_system_info`
- **Type**: Tool
- **Description**: Get detailed information about an endpoint
- **Categories**: investigation
- **Parameters**:
  - `guid` (required): Endpoint GUID

### Scan Endpoint
- **ID**: `scan_endpoint`
- **Type**: Tool
- **Description**: Initiate a scan on an endpoint
- **Categories**: investigation, threat_hunting
- **Parameters**:
  - `guid` (required): Endpoint GUID to scan
  - `cpu_max` (optional): Maximum CPU usage (default: 95)
  - `cpu_max_vm` (optional): Maximum CPU for VMs (default: 25)
  - `cpu_min` (optional): Minimum CPU usage (default: 20)
  - `scan_category` (optional): Scan category (default: "All")
  - `filter_hooks` (optional): Filter hook types
  - Various scan options (floating code, network, etc.)

### Get Scan Data
- **ID**: `get_scan_data`
- **Type**: Tool
- **Description**: Get scan data from an endpoint
- **Categories**: investigation, forensics
- **Parameters**:
  - `guid` (required): Endpoint GUID
  - `limit` (optional): Maximum items per category (default: 50)

### List IOCs
- **ID**: `list_ioc`
- **Type**: Tool
- **Description**: List available Indicators of Compromise
- **Categories**: investigation, threat_intel
- **Parameters**:
  - `machine_count` (optional): Minimum machine count (default: 0)
  - `module_count` (optional): Minimum module count (default: 0)
  - `ioc_level` (optional): Maximum IOC level (0=Critical, 1=High, 2=Medium, 3=Low)
  - `limit` (optional): Maximum IOCs to return (default: 50)

### Get IOC
- **ID**: `get_ioc`
- **Type**: Tool
- **Description**: Get detailed information about an IOC
- **Categories**: investigation, threat_intel
- **Parameters**:
  - `name` (required): IOC name

## Archetype Mappings

**EDR Archetype:**
- `scan_host` → `scan_endpoint`
- `get_host_details` → `get_system_info`
- `collect_forensics` → `get_scan_data`

## Migration Notes

**Upstream Actions Mapped:**
- `test connectivity` → `health_check`
- `blocklist domain` → `blocklist_domain`
- `blocklist ip` → `blocklist_ip`
- `list endpoints` → `list_endpoints`
- `get system info` → `get_system_info`
- `scan endpoint` → `scan_endpoint`
- `get scan data` → `get_scan_data`
- `list ioc` → `list_ioc`
- `get ioc` → `get_ioc`

**Key Changes:**
- HTTP Basic Auth instead of session-based auth
- Async/await pattern for all API calls
- Simplified parameter validation
- Windows-only endpoint filtering (upstream requirement)

## Dependencies

- `httpx`: Async HTTP client
- Python 3.13+

## Testing

Run unit tests:
```bash
poetry run pytest tests/unit/third_party_integrations/netwitness_endpoint/ -v
```

All tests validate:
- API connectivity and authentication
- Parameter validation
- HTTP error handling
- Missing credentials handling
- Success and failure scenarios

## Priority

**70** (Medium-High Priority) - EDR platform for endpoint security and threat response
