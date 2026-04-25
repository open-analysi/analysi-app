# Nessus Integration

Nessus vulnerability scanner integration for the Naxos framework.

## Overview

This integration connects to Tenable's Nessus vulnerability scanner to perform endpoint scanning and vulnerability management operations.

**Archetype**: VulnerabilityManagement
**Priority**: 70

## Credentials

- **server** (required): Nessus server IP address or hostname
- **port** (default: 8834): Nessus server port
- **access_key** (required): API access key from user's API settings
- **secret_key** (required): API secret key from user's API settings
- **verify_server_cert** (default: false): Whether to verify SSL/TLS certificate

## Settings

- **timeout** (default: 30): HTTP request timeout in seconds

## Actions

### Health Check
**ID**: `health_check`
**Type**: Connector
**Purpose**: Verify connectivity to Nessus API

**Parameters**: None

### List Policies
**ID**: `list_policies`
**Type**: Tool
**Categories**: investigation, vulnerability_management

List available scan policies configured in Nessus.

**Parameters**: None

**Returns**:
- `policies`: List of available scan policies
- `policy_count`: Number of policies found

### Scan Host
**ID**: `scan_host`
**Type**: Tool
**Categories**: investigation, vulnerability_management

Scan a host using a selected scan policy. The scan will run asynchronously and poll for completion.

**Parameters**:
- `target_to_scan` (required): IP address or hostname to scan
- `policy_id` (required): ID of the scan policy to use (from list_policies)

**Returns**:
- `scan_id`: ID of the created scan
- `hosts`: List of scanned hosts with vulnerability counts
- `total_vulnerabilities`: Total number of vulnerabilities found
- `summary`: Breakdown of vulnerabilities by severity (critical, high, medium, low, info)

**Note**: This action waits for scan completion, which may take 10-15 minutes depending on the target and policy.

### Get Host Vulnerabilities
**ID**: `get_host_vulnerabilities`
**Type**: Tool
**Categories**: investigation, vulnerability_management

Get detailed vulnerability information for a specific host from scan results.

**Parameters**:
- `scan_id` (required): Scan ID from scan_host
- `host_id` (required): Host ID from scan results

**Returns**:
- `vulnerabilities`: List of vulnerabilities for the host
- `vulnerability_count`: Number of vulnerabilities found

## Archetype Mappings

This integration implements the VulnerabilityManagement archetype:

- `scan_assets` → `scan_host`
- `get_asset_vulnerabilities` → `get_host_vulnerabilities`

## Usage Examples

### Cy Script
```python
# List available scan policies
policies = await nessus::list_policies()

# Scan a host
scan_result = await nessus::scan_host(
    target_to_scan="192.168.1.100",
    policy_id=policies["policies"][0]["id"]
)

# Get detailed vulnerabilities for a host
vulns = await nessus::get_host_vulnerabilities(
    scan_id=scan_result["scan_id"],
    host_id=scan_result["hosts"][0]["host_id"]
)
```

## Migration Notes

**Key Differences**:
- Uses async/await patterns with httpx instead of synchronous requests
- Credentials passed via credential_schema instead of configuration dict
- Actions return standardized result format with status/error fields
- Health check uses IntegrationAction base class

**upstream Action Mapping**:
- `test_asset_connectivity` → `health_check`
- `list_policies` → `list_policies`
- `scan_host` → `scan_host`
- (New) `get_host_vulnerabilities` - Enhanced action for detailed vulnerability retrieval
