# Tenable.io Integration

Tenable.io integration for vulnerability scanning and management.

## Overview

This integration provides vulnerability management capabilities through the Tenable.io API, enabling automated vulnerability scanning, policy management, and scan result retrieval.

## Configuration

### Credentials

- **access_key** (required): Tenable.io Access Key
- **secret_key** (required): Tenable.io Secret Key

### Settings

- **timeout** (optional): Request timeout in seconds (default: 60, range: 1-300)

## Actions

### Health Check
Test connectivity to Tenable.io API.

**Parameters:** None

**Returns:** API connectivity status and scan count

### List Scans
Retrieve list of configured vulnerability scans.

**Parameters:**
- `folder_id` (optional): Filter scans by folder ID
- `last_modified` (optional): Filter scans modified since timestamp (Unix timestamp or ISO datetime)

**Returns:** List of scans with metadata

### List Scanners
Retrieve list of scanners available to the user.

**Parameters:** None

**Returns:** List of available scanners

### List Policies
Retrieve list of configured scan policies.

**Parameters:** None

**Returns:** List of scan policies

### Scan Host
Scan a host or endpoint using specified scan policy.

**Parameters:**
- `target_to_scan` (required): Target to scan (IP address or hostname)
- `policy_id` (required): ID of the scan policy to use
- `scan_name` (optional): Name for the scan
- `scanner_id` (optional): Scanner or scanner group UUID or name
- `scan_timeout` (optional): Time to wait for scan completion in seconds (default: 3600, max: 14400)

**Returns:** Scan results with vulnerability counts by severity

### Delete Scan
Delete a vulnerability scan.

**Parameters:**
- `scan_id` (required): Unique identifier for the scan to delete

**Returns:** Deletion status

## Archetype Mappings

**VulnerabilityManagement:**
- `scan_assets` → `scan_host`
- `get_vulnerabilities` → `list_scans`

## Migration Notes

**Key Changes:**
- Replaced `pytenable` SDK with direct REST API calls using `httpx` for async support
- Implemented native async/await patterns
- Added comprehensive error handling and validation
- Standardized response format across all actions
- Added archetype support for VulnerabilityManagement workflows

**upstream Actions Migrated:**
- test_connectivity → health_check
- list_scans → list_scans
- list_scanners → list_scanners
- list_policies → list_policies
- scan_host → scan_host
- delete_scan → delete_scan

## API Reference

Tenable.io API Documentation: https://developer.tenable.com/reference/navigate
