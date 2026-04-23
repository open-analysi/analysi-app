# RSA Security Analytics Integration

This integration connects to RSA Security Analytics (now part of NetWitness Platform) SIEM to query security incidents, alerts, and events.

## Overview

RSA Security Analytics is a SIEM platform that collects and analyzes security events from across the network. This integration provides actions to query incidents, alerts, events, and connected devices.

**Archetype**: SIEM
**Protocol**: REST API with session-based authentication

## Configuration

### Credentials

- **url** (required): RSA Security Analytics URL (e.g., `https://rsa-sa.company.com`)
- **username** (required): Username for authentication
- **password** (required): Password for authentication

### Settings

- **incident_manager** (required): Name of the Incident Manager device
- **verify_ssl** (optional): Verify SSL certificate (default: `false`)
- **timeout** (optional): Request timeout in seconds (default: `30`)

## Actions

### health_check
Test connectivity to RSA Security Analytics.

**Type**: connector (health_monitoring)
**Parameters**: None

**Returns**:
```json
{
  "status": "success",
  "message": "RSA Security Analytics connection successful"
}
```

### list_incidents
List security incidents within a time frame.

**Type**: tool
**Categories**: investigation, siem

**Parameters**:
- `start_time` (optional): Start time in format YYYY-MM-DD HH:MM:SS (UTC)
- `end_time` (optional): End time in format YYYY-MM-DD HH:MM:SS (UTC)
- `limit` (optional): Maximum number of incidents to list (default: 100)

**Returns**:
```json
{
  "status": "success",
  "num_incidents": 2,
  "incidents": [
    {
      "id": "INC-001",
      "name": "Security Incident 1",
      "status": "Open",
      "riskScore": 85,
      "alertCount": 5
    }
  ]
}
```

### list_alerts
List security alerts for an incident or all recent alerts.

**Type**: tool
**Categories**: investigation, siem

**Parameters**:
- `id` (optional): Incident ID (if not provided, lists all alerts)
- `limit` (optional): Maximum number of alerts to list (default: 100)

**Returns**:
```json
{
  "status": "success",
  "num_alerts": 5,
  "alerts": [
    {
      "id": "ALERT-001",
      "name": "Malware Detected",
      "severity": 8,
      "numEvents": 10
    }
  ]
}
```

### list_events
List security events for a specific alert.

**Type**: tool
**Categories**: investigation, siem

**Parameters**:
- `id` (required): Alert ID
- `limit` (optional): Maximum number of events to list (default: 100)

**Returns**:
```json
{
  "status": "success",
  "num_events": 10,
  "events": [
    {
      "id": "SESSION-12345",
      "type": "network",
      "timestamp": "2024-01-01T12:00:00Z"
    }
  ]
}
```

### list_devices
List devices connected to RSA Security Analytics.

**Type**: tool
**Categories**: investigation, asset_discovery

**Parameters**: None

**Returns**:
```json
{
  "status": "success",
  "num_devices": 5,
  "devices": [
    {
      "id": "1",
      "displayName": "Concentrator-01",
      "deviceType": "CONCENTRATOR"
    }
  ]
}
```

## Archetype Mappings

This integration implements the SIEM archetype with the following mappings:

- `query_events` → `list_events`
- `get_alerts` → `list_alerts`

## Authentication Flow

RSA Security Analytics uses session-based authentication:

1. POST to `/j_spring_security_check` with username/password
2. Extract CSRF token from response HTML
3. Extract JSESSIONID cookie from response
4. Use session cookie for subsequent API calls
5. GET `/j_spring_security_logout` to logout (best effort)

## Error Handling

The integration handles the following error types:

- **ValidationError**: Invalid parameters (e.g., invalid time format, missing required parameter)
- **ConfigurationError**: Missing credentials or settings
- **AuthenticationError**: Authentication failed
- **HTTPError**: HTTP status errors from API
- **ConnectionError**: Network/connection errors

## Testing

Run unit tests:
```bash
poetry run pytest tests/unit/third_party_integrations/rsa_security_analytics/ -v
```

## Migration Notes

**Actions migrated**:
- `test_connectivity` → `health_check`
- `list_incidents` → `list_incidents`
- `list_alerts` → `list_alerts`
- `list_events` → `list_events`
- `list_devices` → `list_devices`

**Actions not migrated**:
- `restart_service` - Deprecated upstream
- `on_poll` - Internal polling mechanism, not needed in Naxos

**Key differences**:
- Uses async httpx instead of sync requests
- Simplified session management
- Standardized error handling
- Added proper typing and docstrings
