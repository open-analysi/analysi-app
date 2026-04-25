# Proofpoint TAP Integration

Email security integration with Proofpoint Targeted Attack Protection (TAP) for investigating campaigns, analyzing threat forensics, and decoding Proofpoint-rewritten URLs.

## Configuration

### Credentials
| Field | Required | Description |
|-------|----------|-------------|
| `username` | Yes | Service Principal for TAP API |
| `password` | Yes | Secret for TAP API |

### Settings
| Field | Default | Description |
|-------|---------|-------------|
| `timeout` | 30 | HTTP request timeout in seconds |

## Actions

### health_check
Test connectivity to the Proofpoint TAP API by querying the SIEM endpoint.

### get_campaign_data
Fetch detailed campaign information (deprecated alias for get_campaign_details).

| Param | Required | Description |
|-------|----------|-------------|
| `campaign_id` | Yes | Proofpoint campaign ID |

### get_campaign_details
Fetch detailed campaign information including actors, threats, malware families, and techniques.

| Param | Required | Description |
|-------|----------|-------------|
| `campaign_id` | Yes | Proofpoint campaign ID |

### get_forensic_data
Fetch forensic information for a threat or campaign (deprecated alias).

| Param | Required | Description |
|-------|----------|-------------|
| `campaign_id` | One of campaign_id/threat_id | Campaign ID |
| `threat_id` | One of campaign_id/threat_id | Threat ID |
| `include_campaign_forensics` | No (default: false) | Include campaign forensics for threat queries |

### get_forensic_data_by_campaign
Fetch forensic information for a threat or campaign (current version).

Same parameters as get_forensic_data.

### decode_url
Decode Proofpoint-rewritten URLs back to their original form.

| Param | Required | Description |
|-------|----------|-------------|
| `url` | Yes | Comma-separated list of URLs to decode |

## Archetype Mappings

**EmailSecurity**:
- `get_email_trace` -> `get_forensic_data_by_campaign`

## Migration Notes

- Adapted from `proofpoint_connector.py`
- Skipped `on_poll` action (ingestion not applicable to Naxos framework)
- Uses HTTP Basic Auth via `self.http_request(auth=...)` matching upstream's `requests.get(auth=...)` pattern
- 404 responses on lookup actions return `success_result(not_found=True)` instead of errors
- upstream's deprecated actions (`get_campaign_details`/`get_campaign_data` and `get_forensic_data`/`get_forensic`) are preserved as separate Naxos actions for backward compatibility
