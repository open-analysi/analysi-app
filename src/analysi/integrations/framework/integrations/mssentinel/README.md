# Microsoft Sentinel Integration

Microsoft Sentinel is Azure's cloud-native SIEM (Security Information and Event Management) and XDR (Extended Detection and Response) platform for security operations.

## Overview

This integration provides comprehensive incident management, threat hunting, and security analytics capabilities through the Microsoft Sentinel API.

**Archetype**: SIEM
**Integration Type**: REST API (Azure Management API + Log Analytics API)
**Authentication**: Azure AD OAuth 2.0 (Client Credentials Flow)

## Features

### Incident Management
- **List Incidents**: Retrieve incidents with optional filtering
- **Get Incident**: Get detailed information about a specific incident
- **Update Incident**: Modify incident properties (severity, status, classification, etc.)
- **Add Comment**: Add comments to incidents for collaboration

### Investigation & Analysis
- **Get Incident Entities**: Retrieve all entities associated with an incident
- **Get Incident Alerts**: Get alerts that triggered an incident
- **Run KQL Query**: Execute Kusto Query Language queries against Log Analytics workspace

### Health Monitoring
- **Health Check**: Verify connectivity to Microsoft Sentinel

## Configuration

### Credentials

- **Tenant ID**: Azure AD tenant ID (GUID format)
- **Client ID**: Azure AD application (client) ID
- **Client Secret**: Azure AD application secret

### Settings

- **Subscription ID**: Azure subscription ID
- **Resource Group Name**: Azure resource group containing the workspace
- **Workspace Name**: Sentinel workspace name
- **Workspace ID**: Workspace ID for Log Analytics queries (GUID format)
- **Timeout**: HTTP request timeout in seconds (default: 30)

## Archetype Mappings

Maps to the **SIEM** archetype with the following action mappings:

| Archetype Action | Integration Action | Description |
|-----------------|-------------------|-------------|
| `get_alert_details` | `get_incident` | Get incident details |
| `query_events` | `run_query` | Execute KQL query |
| `update_alert_status` | `update_incident` | Update incident status |
| `get_alerts` | `list_incidents` | List all incidents |

## Actions

### list_incidents

Retrieve incidents from the Sentinel workspace.

**Parameters**:
- `limit` (required): Maximum number of incidents (default: 100)
- `filter` (optional): OData filter expression (e.g., `properties/severity eq 'High'`)

**Returns**: List of incidents with metadata

### get_incident

Get detailed information about a specific incident.

**Parameters**:
- `incident_name` (required): Incident ID/name (GUID)

**Returns**: Complete incident details including properties, entities, and alerts

### update_incident

Update properties of an existing incident.

**Parameters**:
- `incident_name` (required): Incident ID/name
- `severity` (optional): High, Medium, Low, or Informational
- `status` (optional): New, Active, or Closed
- `title` (optional): Updated title
- `description` (optional): Updated description
- `owner_upn` (optional): Owner's user principal name
- `classification` (optional): BenignPositive, FalsePositive, TruePositive, Undetermined
- `classification_comment` (optional): Comment for classification
- `classification_reason` (optional): Reason for classification

**Returns**: Updated incident data

### add_incident_comment

Add a comment to an incident.

**Parameters**:
- `incident_name` (required): Incident ID/name
- `message` (required): Comment text

**Returns**: Created comment object

### get_incident_entities

Retrieve all entities (accounts, hosts, IPs, etc.) associated with an incident.

**Parameters**:
- `incident_name` (required): Incident ID/name

**Returns**: List of entities with kind and properties

### get_incident_alerts

Get all alerts that contributed to an incident.

**Parameters**:
- `incident_name` (required): Incident ID/name

**Returns**: List of security alerts

### run_query

Execute a KQL (Kusto Query Language) query against the Log Analytics workspace.

**Parameters**:
- `query` (required): KQL query string (e.g., `SecurityIncident | limit 10`)
- `timespan` (optional): ISO 8601 duration (e.g., `P7D` for 7 days)
- `max_rows` (required): Maximum rows to return (default: 3000)

**Returns**: Query results as rows with column data

## Azure AD App Registration

To use this integration, you must register an Azure AD application with the following:

1. **API Permissions**:
   - `https://management.azure.com/.default` (for Sentinel API)
   - `https://api.loganalytics.io/.default` (for Log Analytics queries)

2. **RBAC Roles** (on the Sentinel workspace):
   - **Microsoft Sentinel Contributor** (for incident management)
   - **Log Analytics Reader** (for KQL queries)

3. **Client Secret**: Generate a client secret and store securely

## Example Usage

```python
# List high-severity incidents
result = await list_incidents_action.execute(
    limit=50,
    filter="properties/severity eq 'High'"
)

# Update incident status
result = await update_incident_action.execute(
    incident_name="incident-guid",
    status="Active",
    severity="High",
    owner_upn="analyst@corp.example"
)

# Run KQL query for threat hunting
result = await run_query_action.execute(
    query="SecurityIncident | where TimeGenerated > ago(7d) | summarize count() by Severity",
    max_rows=1000
)
```

## Migration Notes

### Key Changes:
- Uses async `httpx.AsyncClient` instead of sync `requests`
- All actions return standardized response format with `status` field
- OAuth token management handled automatically per request
- Simplified error handling with typed exceptions
- Full KQL query support through Log Analytics API

### Upstream Compatibility:
- Parameter names and behavior preserved
- Response format enhanced with additional metadata

## Dependencies

- `httpx` - Async HTTP client for Azure API calls
- No additional dependencies required

## References

- [Microsoft Sentinel REST API](https://learn.microsoft.com/en-us/rest/api/securityinsights/)
- [Azure Log Analytics API](https://learn.microsoft.com/en-us/rest/api/loganalytics/)
- [Kusto Query Language (KQL)](https://learn.microsoft.com/en-us/azure/data-explorer/kusto/query/)
