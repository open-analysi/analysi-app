# Chronicle Integration

Chronicle by Google Cloud is a cloud-native SIEM (Security Information and Event Management) platform that enables security teams to search, analyze, and investigate security events and threats at enterprise scale.

## Overview

This integration provides 10 actions for interacting with the Chronicle platform:

### SIEM Actions
- **List Events** - Query security events for specific assets within a time range
- **List Alerts** - Retrieve security alerts for assets and users
- **List Rules** - Get detection rules from the Chronicle Detection Engine
- **List Detections** - Query detections for specific rule IDs

### Threat Intelligence Actions
- **List IOC Details** - Get threat intelligence for domains or IPs
- **List IOCs** - Retrieve all indicators of compromise within a time range
- **Domain Reputation** - Check domain reputation (Malicious/Suspicious/Unknown)
- **IP Reputation** - Check IP address reputation (Malicious/Suspicious/Unknown)

### Investigation Actions
- **List Assets** - Find all assets that accessed an artifact
- **Health Check** - Test Chronicle API connectivity

## Authentication

Chronicle uses Google Cloud service account authentication with OAuth2.

### Required Credentials

1. **Service Account JSON** (`key_json`): Contents of your Google service account JSON file
   - Create a service account in Google Cloud Console
   - Grant the service account Chronicle API access
   - Download the JSON key file

2. **API Scopes** (`scopes`): OAuth2 scopes (default: `["https://www.googleapis.com/auth/chronicle-backstory"]`)

## Configuration

### Settings Schema

- **base_url**: Chronicle API base URL (default: `https://backstory.googleapis.com`)
- **timeout**: Request timeout in seconds (default: 30)
- **no_of_retries**: Number of retry attempts (default: 3)
- **wait_timeout_period**: Wait period between retries in seconds (default: 3)

## Archetypes

This integration implements two archetypes:

### SIEM Archetype
- `query_events` → `list_events`
- `get_alerts` → `list_alerts`
- `add_threat_intel` → `list_ioc_details`

### ThreatIntel Archetype
- `lookup_domain` → `domain_reputation`
- `lookup_ip` → `ip_reputation`

## Example Usage

### Query Security Events
```python
result = await list_events_action.execute(
    asset_identifier="hostname",
    asset_identifier_value="workstation-01",
    start_time="2024-01-01T00:00:00Z",
    end_time="2024-01-02T00:00:00Z"
)
```

### Check Domain Reputation
```python
result = await domain_reputation_action.execute(
    domain="suspicious-domain.com"
)
# Returns: {"reputation": "Malicious|Suspicious|Unknown", ...}
```

### List Security Alerts
```python
result = await list_alerts_action.execute(
    start_time="2024-01-01T00:00:00Z",
    end_time="2024-01-02T00:00:00Z",
    alert_type="All"  # or "Asset Alerts" or "User Alerts"
)
```

### Get IOC Threat Intelligence
```python
result = await list_ioc_details_action.execute(
    artifact_indicator="Domain Name",  # or "Destination IP Address"
    value="attacker.example"
)
```

## Action Parameters

### Time Parameters
All time parameters must be in ISO 8601 format: `YYYY-MM-DDTHH:MM:SSZ`

Example: `2024-01-15T14:30:00Z`

### Artifact Indicators
- **Domain Name**: For domain-based queries
- **Destination IP Address**: For IP-based queries
- **MD5/SHA1/SHA256**: For file hash-based queries (list_assets only)

### Alert Types
- **Asset Alerts**: Alerts associated with devices/assets
- **User Alerts**: Alerts associated with user accounts
- **All**: Both asset and user alerts

## Error Handling

The integration handles various error types:
- **ValidationError**: Invalid parameters or missing required fields
- **ConfigurationError**: Missing or invalid credentials
- **AuthenticationError**: Google OAuth2 authentication failures
- **HTTPStatusError**: Chronicle API HTTP errors (404, 429, etc.)
- **TimeoutError**: Request timeouts

## Limits

- Default page size: 10,000 results
- Configurable limit parameter for most actions
- Rate limiting handled with automatic retries

## Dependencies

- `httpx`: Async HTTP client
- `google-auth`: Google OAuth2 authentication
- `tenacity`: Retry logic with exponential backoff

## Migration Notes

| Upstream Action | Naxos Action |
|------------|--------------|
| test connectivity | health_check |
| list ioc details | list_ioc_details |
| list assets | list_assets |
| list events | list_events |
| list iocs | list_iocs |
| domain reputation | domain_reputation |
| ip reputation | ip_reputation |
| list alerts | list_alerts |
| list rules | list_rules |
| list detections | list_detections |

Note: The upstream `on poll` ingestion action is not migrated as Naxos uses a different ingestion architecture.
