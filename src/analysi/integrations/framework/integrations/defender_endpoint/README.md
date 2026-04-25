# Microsoft Defender for Endpoint Integration

Naxos integration for Microsoft Defender for Endpoint EDR platform.

## Overview

This integration provides endpoint detection and response capabilities through Microsoft Defender for Endpoint's API, including device isolation, malware scanning, file quarantine, and advanced threat hunting.

## Archetype

- **EDR** (Endpoint Detection and Response)

## Credentials

The integration requires Azure AD application credentials with Microsoft Defender API permissions:

- `tenant_id` - Azure AD Tenant ID
- `client_id` - Application (Client) ID
- `client_secret` - Client Secret

### Required API Permissions

Configure the following Microsoft Graph API permissions for your Azure AD application:

- `Machine.Read.All` - Read device information
- `Machine.Isolate` - Isolate/release devices
- `Machine.Scan` - Run antivirus scans
- `Machine.StopAndQuarantine` - Quarantine files
- `Machine.RestrictExecution` - Restrict app execution
- `Alert.Read.All` - Read alerts
- `Alert.ReadWrite.All` - Update alerts
- `AdvancedQuery.Read.All` - Run advanced queries

## Settings

- `timeout` (integer, default: 30) - Request timeout in seconds
- `environment` (string, default: "Public") - Azure cloud environment:
  - `Public` - Azure Commercial Cloud
  - `GCC` - Azure Government Community Cloud
  - `GCC High` - Azure Government Community Cloud High

## Actions

### EDR Archetype Actions

| Action | Archetype Mapping | Description |
|--------|------------------|-------------|
| `isolate_device` | `isolate_host` | Isolate device from network |
| `release_device` | `release_host` | Release device from isolation |
| `scan_device` | `scan_host` | Run antivirus scan |
| `get_device_details` | `get_host_details` | Get device information |
| `quarantine_file` | `quarantine_file` | Quarantine malicious file |

### Additional Actions

- `health_check` - Test API connectivity and authentication
- `restrict_app_execution` - Restrict app execution to Microsoft-signed only
- `unrestrict_app_execution` - Remove app execution restriction
- `list_devices` - List all registered devices
- `list_alerts` - List security alerts with optional status filter
- `get_alert` - Get alert details by ID
- `update_alert` - Update alert status, assignment, or classification
- `run_advanced_query` - Execute KQL advanced hunting query

## Usage Examples

### Isolate Compromised Device

```python
result = await defender.isolate_device(
    device_id="abc123...",
    comment="Suspected ransomware infection",
    isolation_type="Full"
)
```

### Run Quick Scan

```python
result = await defender.scan_device(
    device_id="abc123...",
    comment="Routine security scan",
    scan_type="Quick"
)
```

### Quarantine Malicious File

```python
result = await defender.quarantine_file(
    device_id="abc123...",
    file_hash="275a021bbfb6489e54d471899f7db9d1663fc695",
    comment="File detected as malware by threat intel"
)
```

### Advanced Threat Hunting

```python
result = await defender.run_advanced_query(
    query="""
    DeviceEvents
    | where Timestamp > ago(24h)
    | where ActionType == "ProcessCreated"
    | summarize count() by DeviceName, FileName
    | order by count_ desc
    """
)
```

### List High-Severity Alerts

```python
result = await defender.list_alerts(
    limit=50,
    status="New"
)
```

## References

- [Microsoft Defender for Endpoint API Documentation](https://learn.microsoft.com/en-us/microsoft-365/security/defender-endpoint/api/apis-intro)
- [Advanced Hunting KQL Reference](https://learn.microsoft.com/en-us/microsoft-365/security/defender/advanced-hunting-query-language)
- [Azure AD App Registration Guide](https://learn.microsoft.com/en-us/azure/active-directory/develop/quickstart-register-app)
