# Google BigQuery Integration

Google BigQuery integration for data warehouse operations, including SQL query execution and table management.

## Overview

BigQuery is Google Cloud's serverless, highly scalable data warehouse designed for business agility. This integration provides:

- SQL query execution with timeout support
- Table listing across datasets
- Asynchronous job management for long-running queries
- Service account authentication

## Archetype

**Lakehouse** - Data warehouse/analytics platform for storing and querying large datasets.

## Authentication

Uses Google Cloud service account JSON credentials:

```json
{
  "type": "service_account",
  "project_id": "your-project-id",
  "private_key_id": "key-id",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "service-account@project.iam.gserviceaccount.com",
  "client_id": "123456789",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token"
}
```

## Actions

### Health Check
Test connectivity to BigQuery API.

**Parameters:** None

**Returns:**
- `healthy`: Boolean indicating if BigQuery is accessible
- `message`: Status message

### List Tables
List tables in BigQuery datasets.

**Parameters:**
- `dataset` (optional): Filter to specific dataset. Lists all tables across all datasets if not provided.

**Returns:**
- `tables`: Array of table objects with:
  - `table_id`: Table name
  - `dataset_id`: Dataset name
  - `project_id`: Project ID
  - `full_table_id`: Fully qualified table ID
- `total_tables`: Number of tables found

### Run Query
Execute a SQL query in BigQuery.

**Parameters:**
- `query` (required): SQL query to execute
- `timeout` (optional): Query timeout in seconds (uses default if not provided)

**Returns:**
- `job_id`: BigQuery job ID for retrieving results later
- `rows`: Query results (if completed within timeout)
- `num_rows`: Number of rows returned
- `timed_out`: Boolean indicating if query timed out

### Get Results
Retrieve results from a previously started query job.

**Parameters:**
- `job_id` (required): BigQuery job ID from run_query
- `timeout` (optional): Timeout in seconds to wait for results

**Returns:**
- `job_id`: BigQuery job ID
- `rows`: Query results (if completed)
- `num_rows`: Number of rows returned
- `timed_out`: Boolean indicating if query timed out

## Configuration

### Settings
- `project_id` (optional): Override project ID from service account
- `default_timeout`: Default query timeout in seconds (default: 30)

## Example Usage

### Run a Query
```python
result = await bigquery.run_query(
    query="SELECT * FROM `project.dataset.table` LIMIT 100"
)

if result["data"].get("timed_out"):
    # Query timed out, retrieve later
    job_id = result["data"]["job_id"]
    results = await bigquery.get_results(job_id=job_id, timeout=60)
else:
    # Query completed
    rows = result["data"]["rows"]
```

### List Tables
```python
# List all tables
result = await bigquery.list_tables()

# List tables in specific dataset
result = await bigquery.list_tables(dataset="my_dataset")

tables = result["data"]["tables"]
```

## Migration Notes

1. **Async Implementation**: All BigQuery client operations wrapped with `asyncio.to_thread()` for non-blocking execution
2. **Timeout Handling**: Uses Python's `concurrent.futures.TimeoutError` for query timeouts
3. **Error Types**: Standardized error types (ValidationError, ConfigurationError, QueryError, TimeoutError)
4. **Archetype**: Classified as "Lakehouse" archetype for data warehouse operations

## Dependencies

- `google-cloud-bigquery>=3.19.0`: Google Cloud BigQuery client library
- `google-auth`: Google authentication library

## Testing

Comprehensive unit tests cover:
- Successful operations for all actions
- Missing/invalid credentials
- Invalid parameters
- Query timeouts
- Error handling
