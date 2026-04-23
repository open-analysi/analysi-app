# AlienVault OTX Integration

AlienVault Open Threat Exchange (OTX) integration for threat intelligence lookups.

## Overview

This integration connects to AlienVault OTX to perform threat intelligence lookups for:
- Domain reputation
- IP address reputation (IPv4 and IPv6)
- File hash reputation (MD5, SHA1, SHA256)
- URL reputation
- Pulse retrieval

## Migration from upstream

**Migration Date:** 2025-10-10

**Actions Migrated:**
- `test_connectivity` → `health_check`
- `domain_reputation` → `domain_reputation`
- `ip_reputation` → `ip_reputation`
- `file_reputation` → `file_reputation`
- `url_reputation` → `url_reputation`
- `get_pulses` → `get_pulse`

## Configuration

### Credentials
- `api_key` (required): AlienVault OTX API Key

### Settings
- `timeout` (optional, default: 120): Request timeout in seconds
- `verify_server_cert` (optional, default: true): Verify SSL certificate

## Actions

### health_check
Test connectivity to AlienVault OTX API.

### domain_reputation
Query domain reputation information.

**Parameters:**
- `domain` (required): Domain to query
- `response_type` (optional, default: "general"): Type of response data
  - Valid types: general, geo, malware, url_list, passive_dns, whois, http_scans

### ip_reputation
Query IP address reputation (supports both IPv4 and IPv6).

**Parameters:**
- `ip` (required): IP address to query
- `response_type` (optional, default: "general"): Type of response data
  - IPv4 types: general, reputation, geo, malware, url_list, passive_dns, http_scans
  - IPv6 types: general, reputation, geo, malware, url_list, passive_dns

### file_reputation
Query file hash reputation (MD5, SHA1, SHA256).

**Parameters:**
- `hash` (required): File hash to query
- `response_type` (optional, default: "general"): Type of response data
  - Valid types: general, analysis

### url_reputation
Query URL reputation information.

**Parameters:**
- `url` (required): URL to query
- `response_type` (optional, default: "general"): Type of response data
  - Valid types: general, url_list

### get_pulse
Get details of a specific pulse by ID.

**Parameters:**
- `pulse_id` (required): Pulse ID to retrieve

## Example Usage

```python
# Health check
result = await health_check_action.execute()

# Domain reputation
result = await domain_reputation_action.execute(
    domain="malware.com",
    response_type="general"
)

# IP reputation
result = await ip_reputation_action.execute(
    ip="8.8.8.8",
    response_type="general"
)

# File reputation
result = await file_reputation_action.execute(
    hash="d41d8cd98f00b204e9800998ecf8427e",
    response_type="general"
)

# URL reputation
result = await url_reputation_action.execute(
    url="https://malicious.com",
    response_type="general"
)

# Get pulse
result = await get_pulse_action.execute(
    pulse_id="123abc"
)
```

## Response Format

All actions return a dictionary with:
- `status`: "success" or "error"
- `error` (if status is "error"): Error message
- `error_type` (if status is "error"): Error type (ValidationError, ConfigurationError, etc.)
- `data`: Action-specific response data

## Test Coverage

- 45 unit tests covering:
  - Validation helpers (IP, domain, hash, URL, response types)
  - API client helper (success, errors, retries)
  - All 6 actions (success, validation errors, API errors)
  - Edge cases (missing parameters, invalid formats, API failures)

## Dependencies

- `httpx`: Async HTTP client
- `validators`: Input validation
- `tenacity`: Retry logic with exponential backoff
