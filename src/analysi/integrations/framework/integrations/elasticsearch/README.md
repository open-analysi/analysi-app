# Elasticsearch Integration

This integration connects to Elasticsearch clusters for event querying, index management, and security operations.

## Overview

Elasticsearch is a distributed search and analytics engine used as a SIEM backend for security event storage and analysis. This integration provides actions for:

- **Health monitoring**: Check cluster connectivity and health
- **Event querying**: Execute Elasticsearch DSL queries across indices
- **Index management**: List and inspect index configuration

## Configuration

### Credentials

- **username** (required): Elasticsearch username for authentication
- **password** (required): Elasticsearch password

### Settings

- **url** (required): Device URL including the port (e.g., `https://myelastic.enterprise.com:9200`)
- **verify_server_cert** (optional): Verify SSL/TLS server certificate (default: false)

## Actions

### health_check (Connector)

Test connectivity to the Elasticsearch cluster.

**Purpose**: `health_monitoring`

**Returns**:
- Cluster health status (green/yellow/red)
- Connection timestamp

### run_query (Tool)

Run a search query using Elasticsearch DSL.

**Parameters**:
- `index` (required): Comma-separated list of indexes to query
- `query` (optional): Elasticsearch DSL query in JSON format
- `routing` (optional): Shard routing value

**Example Query**:
```json
{
  "query": {
    "match_all": {}
  },
  "_source": ["id", "name"]
}
```

**Returns**:
- Query results with hits
- Summary with total hits and timeout status

### get_config (Tool)

List all indices and their configuration.

**Returns**:
- List of indices with:
  - Index name
  - Health status
  - Document count
  - Store size

## Archetype Mappings

This integration implements the **SIEM** archetype:

- `query_events` → `run_query`
- `get_alerts` → `run_query`

## Usage Examples

### Query Events
```python
# Search for security events in the last hour
result = await run_query(
    index="security-events-*",
    query='''{
        "query": {
            "range": {
                "@timestamp": {
                    "gte": "now-1h"
                }
            }
        }
    }'''
)
```

### List Indices
```python
# Get all index information
result = await get_config()
print(f"Found {result['summary']['total_indices']} indices")
```

## Notes

- The integration uses basic authentication
- All API calls are made via HTTP REST endpoints
- Query parameter must be valid Elasticsearch DSL JSON
- Multiple indices can be queried simultaneously using comma-separated names
- SSL certificate verification can be disabled for self-signed certificates

## Migration Notes

This integration was adapted from the Elasticsearch connector. The following prior actions were migrated:

- `test_asset_connectivity` → `health_check`
- `run_query` → `run_query`
- `get_config` → `get_config`
- `on_poll` → Not migrated (upstream-specific ingestion action)
