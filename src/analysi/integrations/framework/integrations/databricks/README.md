# Databricks Integration

This integration provides actions for interacting with the Databricks analytics and data platform.

## Overview

Databricks is a unified analytics platform that enables collaborative data science, engineering, and business analytics. This integration supports SQL queries, alert management, job execution, and workspace operations.

## Credentials

The integration supports two authentication methods:

1. **Personal Access Token** (recommended):
   - `host`: Databricks workspace URL (e.g., `https://example.cloud.databricks.com`)
   - `token`: Personal access token

2. **Username/Password**:
   - `host`: Databricks workspace URL
   - `username`: Username
   - `password`: Password

## Actions

### SQL Operations
- **perform_query**: Execute SQL queries on warehouses
- **get_query_status**: Check query execution status
- **cancel_query**: Cancel running queries

### Alert Management
- **list_alerts**: List all SQL alerts
- **create_alert**: Create new SQL alerts
- **delete_alert**: Delete alerts

### Infrastructure
- **list_clusters**: List compute clusters
- **list_warehouses**: List SQL warehouses

### Job Operations
- **get_job_run**: Get job run details
- **get_job_output**: Retrieve job outputs
- **execute_notebook**: Execute Databricks notebooks

## Archetype

This integration implements the **SIEM** archetype with the following mappings:
- `query_events` → `perform_query`
- `create_alert` → `create_alert`
- `get_alerts` → `list_alerts`

## Migration Notes

## Dependencies

- `databricks-sdk>=0.67.0`
