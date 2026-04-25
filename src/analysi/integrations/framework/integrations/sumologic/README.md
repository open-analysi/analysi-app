# Sumo Logic Integration

Cloud SIEM platform integration for log queries, search jobs, and event analysis.

## Overview

Sumo Logic is a cloud-native Security Information and Event Management (SIEM) platform that provides log management, security analytics, and monitoring capabilities.

## Actions

### Health Check
Tests connectivity to the Sumo Logic API by requesting a single collector.

### Run Query
Execute a search query on the Sumo Logic platform. Supports:
- Time range filtering (UNIX timestamps)
- Result limits (up to 10,000)
- Response types: messages or aggregated records
- Asynchronous polling for job completion

If the query doesn't complete within the polling timeout (60 seconds), a search_id is returned for later retrieval using Get Results.

### Get Results
Retrieve results from a previously created search job using its search_id.

### Delete Job
Delete a search job to free up resources on the Sumo Logic platform.

## Configuration

### Credentials
- **Access ID**: Sumo Logic Access ID
- **Access Key**: Sumo Logic Access Key (secure)

### Settings
- **Environment**: Sumo Logic environment pod (us1, us2, eu, au)
- **Timezone**: Timezone for search queries (default: UTC)

## Archetype Mapping

**SIEM Archetype**:
- `query_events` → `run_query`
- `get_alerts` → `run_query`

## Example Usage

```python
# Run a query for recent logs
result = await integration.run_query(
    query="_sourceCategory=security",
    from_time=1609459200,  # UNIX timestamp
    to_time=1609545600,
    limit=100,
    type="messages"
)

# Get results from a search job
result = await integration.get_results(
    search_id="177C7C195542A613"
)

# Delete a completed search job
result = await integration.delete_job(
    search_id="177C7C195542A613"
)
```

## Migration Notes
- Uses async httpx instead of custom sumologic SDK
- Simplified polling logic with exponential backoff
- Removed on_poll action (upstream-specific ingestion)
- Standardized error handling with proper error types
- Added comprehensive unit tests

## Dependencies

- httpx (async HTTP client)
- Standard library: asyncio, time, logging
