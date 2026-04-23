# Task REST API Reference

## Overview

The Analysi platform provides a RESTful API for managing Tasks. This reference covers all task-related endpoints, including create, read, update, execute, and list operations.

**Base URL:** `http://localhost:8001` (development) or your deployed instance URL

**Authentication:** Depends on deployment configuration (typically Bearer token or API key)

## Endpoints

### 1. Create Task

Create a new Task with Cy script and configuration.

**Endpoint:** `POST /v1/{tenant}/tasks`

**Path Parameters:**
- `tenant` (string, required) - Tenant ID (e.g., "default")

**Request Body:**
```json
{
  "name": "IP Reputation Enrichment",
  "cy_name": "ip_reputation_enrichment",
  "description": "Enriches alerts with IP reputation from VirusTotal and AbuseIPDB",
  "script": "# Cy script here\nreturn {...}",
  "function": "enrichment",
  "scope": "processing",
  "categories": ["threat_intel", "enrichment"],
  "data_samples": [
    {"observables": [{"value": "185.220.101.45", "type": "IP Address"}], "enrichments": {}}
  ],
  "directive": "You are a threat intelligence analyst...",
  "llm_config": {
    "model": "gpt-4",
    "temperature": 0.7,
    "max_tokens": 2000
  },
  "app": "default",
  "status": "enabled",
  "visible": false,
  "authored_by": "security_team"
}
```

**Required Fields:**
- `name` - Task name (1-255 characters)
- `script` - Cy language script
- `data_samples` - At least one sample input

**Optional Fields:**
- `cy_name` - Auto-generated from name if not provided
- `function` - Task function type (enrichment, reasoning, etc.)
- `scope` - Pipeline position (input, processing, output)
- `categories` - Array of tags
- `directive` - System message for LLM calls
- `llm_config` - LLM configuration object
- `app` - App namespace (default: "default")
- `status` - enabled | disabled (default: "enabled")
- `visible` - Show in UI (default: false)
- `authored_by` - Creator username

**Response:** `201 Created`
```json
{
  "id": "14ee7282-3910-4ef7-b378-c2c8371fef37",
  "name": "IP Reputation Enrichment",
  "cy_name": "ip_reputation_enrichment",
  "description": "Enriches alerts with IP reputation from VirusTotal and AbuseIPDB",
  "script": "# Cy script here\nreturn {...}",
  "function": "enrichment",
  "scope": "processing",
  "categories": ["threat_intel", "enrichment"],
  "data_samples": [{"observables": [{"value": "185.220.101.45", "type": "IP Address"}], "enrichments": {}}],
  "status": "enabled",
  "visible": false,
  "app": "default",
  "tenant": "default",
  "authored_by": "security_team",
  "created_at": "2025-01-20T10:30:00Z",
  "updated_at": "2025-01-20T10:30:00Z"
}
```

**Error Responses:**
- `400 Bad Request` - Validation error (missing required fields, invalid Cy syntax, missing output statement)
- `409 Conflict` - Task with same cy_name already exists

### 2. List Tasks

Retrieve all tasks for a tenant with optional filtering.

**Endpoint:** `GET /v1/{tenant}/tasks`

**Path Parameters:**
- `tenant` (string, required) - Tenant ID

**Query Parameters:**
- `function` (string, optional) - Filter by function type
- `scope` (string, optional) - Filter by scope
- `status` (string, optional) - Filter by status (enabled/disabled)
- `app` (string, optional) - Filter by app namespace
- `limit` (integer, optional) - Max results to return (default: 100)
- `offset` (integer, optional) - Pagination offset (default: 0)

**Example Request:**
```
GET /v1/default/tasks?function=enrichment&scope=processing&limit=20
```

**Response:** `200 OK`
```json
{
  "tasks": [
    {
      "id": "14ee7282-3910-4ef7-b378-c2c8371fef37",
      "name": "IP Reputation Enrichment",
      "cy_name": "ip_reputation_enrichment",
      "description": "Enriches alerts with IP reputation",
      "function": "enrichment",
      "scope": "processing",
      "categories": ["threat_intel"],
      "status": "enabled",
      "created_at": "2025-01-20T10:30:00Z",
      "updated_at": "2025-01-20T10:30:00Z"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

### 3. Get Task by ID or cy_name

Retrieve a specific task's complete details.

**Endpoint:** `GET /v1/{tenant}/tasks/{task_identifier}`

**Path Parameters:**
- `tenant` (string, required) - Tenant ID
- `task_identifier` (string, required) - Task UUID or cy_name

**Example Requests:**
```
GET /v1/default/tasks/14ee7282-3910-4ef7-b378-c2c8371fef37
GET /v1/default/tasks/ip_reputation_enrichment
```

**Response:** `200 OK`
```json
{
  "id": "14ee7282-3910-4ef7-b378-c2c8371fef37",
  "name": "IP Reputation Enrichment",
  "cy_name": "ip_reputation_enrichment",
  "description": "Enriches alerts with IP reputation from VirusTotal and AbuseIPDB",
  "script": "ip = get_primary_observable_value(input) ?? get_src_ip(input) ?? \"0.0.0.0\"\n\nvt_result = app::virustotal::ip_reputation(ip=ip)\nabuse_result = app::abuseipdb::lookup_ip(ip=ip)\n\ninput[\"enrichments\"] = input[\"enrichments\"] ?? {}\ninput[\"enrichments\"][\"ip_reputation\"] = {\n    \"virustotal\": vt_result,\n    \"abuseipdb\": abuse_result\n}\n\nreturn input",
  "function": "enrichment",
  "scope": "processing",
  "categories": ["threat_intel", "enrichment"],
  "data_samples": [{"observables": [{"value": "185.220.101.45", "type": "IP Address"}], "enrichments": {}}],
  "directive": "You are a threat intelligence analyst...",
  "status": "enabled",
  "visible": false,
  "app": "default",
  "tenant": "default",
  "authored_by": "security_team",
  "created_at": "2025-01-20T10:30:00Z",
  "updated_at": "2025-01-20T10:30:00Z"
}
```

**Error Responses:**
- `404 Not Found` - Task not found

### 4. Update Task Script

Update an existing task's Cy script.

**Endpoint:** `PATCH /v1/{tenant}/tasks/{task_id}`

**Path Parameters:**
- `tenant` (string, required) - Tenant ID
- `task_id` (string, required) - Task UUID (cy_name not supported for updates)

**Request Body:**
```json
{
  "script": "# Updated Cy script\nreturn {...}"
}
```

**Response:** `200 OK`
```json
{
  "id": "14ee7282-3910-4ef7-b378-c2c8371fef37",
  "name": "IP Reputation Enrichment",
  "cy_name": "ip_reputation_enrichment",
  "script": "# Updated Cy script\nreturn {...}",
  "updated_at": "2025-01-20T11:00:00Z"
}
```

**Error Responses:**
- `400 Bad Request` - Invalid Cy syntax or missing output statement
- `404 Not Found` - Task not found

### 5. Execute Task

Execute a task with provided input data.

**Endpoint:** `POST /v1/{tenant}/tasks/{task_id}/execute`

**Path Parameters:**
- `tenant` (string, required) - Tenant ID
- `task_id` (string, required) - Task UUID or cy_name

**Request Body:**
```json
{
  "input_data": {
    "observables": [{"value": "185.220.101.45", "type": "IP Address"}],
    "enrichments": {}
  }
}
```

**Response:** `200 OK`
```json
{
  "status": "succeeded",
  "output": {
    "observables": [{"value": "185.220.101.45", "type": "IP Address"}],
    "enrichments": {
      "ip_reputation": {
      "virustotal": {
        "response_code": 1,
        "detected_urls": [],
        "reputation": 0
      },
      "abuseipdb": {
        "abuseConfidenceScore": 0,
        "totalReports": 0
      }
    }
  },
  "execution_time": 2.34,
  "task_run_id": "run-abc123"
}
```

**Error Responses:**
- `400 Bad Request` - Invalid input data (missing required fields)
- `404 Not Found` - Task not found
- `500 Internal Server Error` - Task execution failed

### 6. Delete Task

Delete a task permanently.

**Endpoint:** `DELETE /v1/{tenant}/tasks/{task_id}`

**Path Parameters:**
- `tenant` (string, required) - Tenant ID
- `task_id` (string, required) - Task UUID (cy_name not supported for deletion)

**Response:** `204 No Content`

**Error Responses:**
- `404 Not Found` - Task not found
- `409 Conflict` - Task is referenced by workflows (cannot delete)

## Task Validation

### Validation Rules

All task creation and updates are validated against these rules:

1. **Script Syntax**: Must be valid Cy language syntax
2. **Return Statement**: Must contain `return {...}` statement
3. **data_samples**: Must be non-empty list with at least one sample
4. **cy_name Pattern**: Must match `^[a-z][a-z0-9_]*$` (auto-generated if not provided)
5. **Function**: Must be one of: enrichment, summarization, extraction, reasoning, planning, data_conversion, visualization, search
6. **Scope**: Must be one of: input, processing, output

### Common Validation Errors

**Error: Script missing return statement**
```json
{
  "detail": "Script must contain 'return {...}' statement"
}
```

**Error: Invalid cy_name**
```json
{
  "detail": "cy_name must match pattern ^[a-z][a-z0-9_]*$"
}
```

**Error: Empty data_samples**
```json
{
  "detail": "data_samples must be a non-empty list of sample inputs"
}
```

## cURL Examples

### Create Task
```bash
curl -X POST http://localhost:8001/v1/default/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Task",
    "script": "return {\"result\": \"test\"}",
    "data_samples": [{"field": "value"}],
    "function": "enrichment",
    "scope": "processing"
  }'
```

### List Tasks
```bash
curl http://localhost:8001/v1/default/tasks?function=enrichment
```

### Get Task by cy_name
```bash
curl http://localhost:8001/v1/default/tasks/ip_reputation_enrichment
```

### Execute Task
```bash
curl -X POST http://localhost:8001/v1/default/tasks/ip_reputation_enrichment/execute \
  -H "Content-Type: application/json" \
  -d '{
    "input_data": {
      "observables": [{"value": "185.220.101.45", "type": "IP Address"}],
      "enrichments": {}
    }
  }'
```

### Update Task Script
```bash
curl -X PATCH http://localhost:8001/v1/default/tasks/14ee7282-3910-4ef7-b378-c2c8371fef37 \
  -H "Content-Type: application/json" \
  -d '{
    "script": "# Updated script\nreturn {\"updated\": true}"
  }'
```

### Delete Task
```bash
curl -X DELETE http://localhost:8001/v1/default/tasks/14ee7282-3910-4ef7-b378-c2c8371fef37
```

## Python Examples

### Using requests library

```python
import requests

BASE_URL = "http://localhost:8001"
TENANT = "default"

# Create Task
task_data = {
    "name": "IP Reputation Enrichment",
    "cy_name": "ip_reputation_enrichment",
    "script": """
ip = get_primary_observable_value(input) ?? get_src_ip(input) ?? "8.8.8.8"
vt_result = app::virustotal::ip_reputation(ip=ip)
input["enrichments"] = input["enrichments"] ?? {}
input["enrichments"]["ip_reputation"] = vt_result
return input
""",
    "data_samples": [{"observables": [{"value": "8.8.8.8", "type": "IP Address"}], "enrichments": {}}],
    "function": "enrichment",
    "scope": "processing"
}

response = requests.post(
    f"{BASE_URL}/v1/{TENANT}/tasks",
    json=task_data
)
task = response.json()
print(f"Created task: {task['id']}")

# Execute Task
input_data = {"observables": [{"value": "185.220.101.45", "type": "IP Address"}], "enrichments": {}}
response = requests.post(
    f"{BASE_URL}/v1/{TENANT}/tasks/{task['cy_name']}/execute",
    json={"input_data": input_data}
)
result = response.json()
print(f"Execution result: {result['output']}")
```

## Best Practices

1. **Use cy_name for retrieval**: Prefer `GET /tasks/ip_reputation_enrichment` over UUIDs for readability

2. **Test with execute endpoint**: Always test tasks with sample data before using in workflows

3. **Handle errors gracefully**: Check response status codes and handle validation errors

4. **Use data_samples effectively**: Provide realistic test data that matches your script's expected input

5. **Validate before creation**: Use the MCP `validate_cy_script` tool before sending to API

6. **Set appropriate function and scope**: Helps with task discovery and organization

7. **Use descriptive names**: Choose clear, specific task names that communicate purpose

## MCP Tools vs REST API

**When to use MCP tools:**
- Building tasks interactively in Claude
- Need validation feedback before creation
- Want integrated error handling
- Building automation with Claude Code

**When to use REST API:**
- Programmatic task creation from external systems
- Building custom UIs or dashboards
- Integrating with CI/CD pipelines
- Bulk task operations

Both interfaces provide the same functionality - choose based on your use case.
