# CrowdStrike Falcon EDR Integration

Comprehensive integration with CrowdStrike Falcon EDR/XDR platform for endpoint security, threat hunting, incident response, and threat intelligence.

## Overview

This integration provides access to CrowdStrike Falcon's extensive EDR capabilities through OAuth2 client credentials authentication. It implements 32 core actions covering device management, detection/alert handling, threat hunting, IOC management, and sandbox analysis.
**Migration Strategy**: Prioritized core EDR functionality - implemented 32 most critical actions
**Archetypes**: EDR, Sandbox, ThreatIntel
**Priority**: 70 (high - critical security platform)

## Features

### Device Management
- Query and search devices using Falcon Query Language (FQL)
- Get detailed device information
- Quarantine/unquarantine devices (network containment)
- Manage host groups
- System information retrieval

### Real-Time Response (RTR)
- Create and manage RTR sessions
- Execute commands on endpoints
- Collect forensic data
- Retrieve session files

### Detection & Alert Management
- List and query detections/alerts
- Get detection details
- Update detection status
- Filter by severity, state, and custom criteria

### Incident Management
- List and query security incidents
- Get incident details with behaviors
- Update incident status and assignments
- Track incident timelines

### Threat Hunting
- Hunt for file hashes across all endpoints
- Hunt for domains accessed by hosts
- Hunt for IP addresses contacted
- List processes associated with IOCs

### IOC Management
- Upload custom indicators (hash, domain, IP, URL)
- Delete custom indicators
- File reputation lookups
- URL reputation lookups

### Sandbox Analysis (Falcon Sandbox)
- Detonate files for malware analysis
- Detonate URLs for analysis
- Check detonation analysis status
- Support for multiple sandbox environments

## Authentication

Uses OAuth2 client credentials flow:

```json
{
  "base_url": "https://api.crowdstrike.com",
  "client_id": "YOUR_CLIENT_ID",
  "client_secret": "YOUR_CLIENT_SECRET"
}
```

**Regional Endpoints**:
- US-1: `https://api.crowdstrike.com`
- US-2: `https://api.us-2.crowdstrike.com`
- EU-1: `https://api.eu-1.crowdstrike.com`
- US-GOV-1: `https://api.laggar.gcw.crowdstrike.com`

## Archetype Mappings

### EDR Archetype
- `isolate_host` → `quarantine_device`
- `release_host` → `unquarantine_device`
- `scan_host` → `query_device`
- `get_host_details` → `get_device_details`
- `kill_process` → `run_command`
- `collect_forensics` → `get_session_file`
- `run_script` → `run_command`

### Sandbox Archetype
- `submit_file` → `detonate_file`
- `submit_url` → `detonate_url`
- `get_analysis_status` → `check_detonation_status`
- `get_analysis_report` → `check_detonation_status`

### ThreatIntel Archetype
- `lookup_file_hash` → `file_reputation`
- `lookup_url` → `url_reputation`
- `submit_ioc` → `upload_indicator`

## Key Actions

### quarantine_device
Network isolate a device to prevent lateral movement.
```json
{
  "device_id": "abc123...",
  // OR
  "hostname": "DESKTOP-EXAMPLE"
}
```

### hunt_file
Search for file hash across all managed endpoints.
```json
{
  "hash": "5d41402abc4b2a76b9719d911017c592"
}
```

### list_detections
Query security detections with FQL filtering.
```json
{
  "filter": "severity:'high'+status:'new'",
  "limit": 100,
  "sort": "first_behavior|desc"
}
```

### upload_indicator
Upload custom IOC to CrowdStrike threat intelligence.
```json
{
  "type": "domain",
  "value": "malicious.example.com",
  "policy": "prevent",
  "severity": "critical",
  "description": "Known C2 domain"
}
```

### detonate_file
Submit file for sandbox analysis.
```json
{
  "sha256": "2c26b46b68ffc68ff99b453c1d...",
  "environment_id": 160  // Windows 10 64-bit
}
```

## FQL (Falcon Query Language)

CrowdStrike uses FQL for filtering queries. Examples:

**Device Queries**:
- `hostname:'DESKTOP-*'` - Hostname wildcard
- `platform_name:'Windows'+os_version:'10'` - Multiple criteria
- `last_seen:>'2024-01-01T00:00:00Z'` - Date comparison

**Detection Queries**:
- `severity:'high'` - High severity only
- `status:'new'+max_severity:'critical'` - New critical detections
- `device.hostname:'DESKTOP-01'` - By specific host

## Sandbox Environments

Available sandbox environment IDs:
- **160**: Windows 10, 64-bit (default)
- **110**: Windows 7, 64-bit
- **100**: Windows 7, 32-bit
- **300**: Linux Ubuntu 16.04, 64-bit
- **200**: Android (static analysis)

## Error Handling

All actions return standardized error responses:

```json
{
  "status": "error",
  "error_type": "HTTPError",
  "error": "HTTP 404: Device not found"
}
```

**Common Error Types**:
- `ValidationError`: Missing or invalid parameters
- `ConfigurationError`: Missing credentials
- `AuthenticationError`: Invalid OAuth2 credentials
- `HTTPError`: API request failures
- `NotFoundError`: Resource not found

## Rate Limits

CrowdStrike API rate limits vary by endpoint:
- Most endpoints: 6,000 requests/minute
- Detection endpoints: 300 requests/minute
- OAuth token endpoint: 50 requests/minute

The integration handles token refresh automatically.

## Migration Notes

**Upstream actions covered:**

**Implemented Core Actions**:
- All device management actions
- All detection/alert management
- All threat hunting actions
- Core RTR functionality
- IOC management
- Sandbox detonation

**Not Migrated** (lower priority/specialized):
- User management actions
- Role management
- Zero Trust Assessment
- Advanced IOA rule management
- Custom RTR script uploads
- Crowdscore queries

These can be added in future releases if needed.

## Testing

Comprehensive unit tests cover:
- OAuth2 authentication flow
- Device operations (quarantine/unquarantine)
- Detection management
- Threat hunting
- IOC operations
- Sandbox analysis
- Error handling

Run tests:
```bash
poetry run pytest tests/unit/third_party_integrations/crowdstrike/ -v
```

## Dependencies

- `httpx`: Async HTTP client
- Standard library: `logging`, `typing`

## References

- [CrowdStrike Falcon API Documentation](https://falcon.crowdstrike.com/documentation)
- [OAuth2 API Authentication](https://falcon.crowdstrike.com/documentation/46/crowdstrike-oauth2-based-apis)
- [Falcon Query Language (FQL)](https://falcon.crowdstrike.com/documentation/45/falcon-query-language-fql)
