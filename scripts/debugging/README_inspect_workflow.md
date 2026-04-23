# Workflow Execution Inspector

A diagnostic tool for inspecting workflow executions, showing input/output data flow through each node.

## Features

- Lists recent workflow executions
- Shows complete data flow through workflow nodes
- Displays input and output for each node
- Automatically configures database connection from `.env`
- Handles both local and Docker environments

## Usage

### List Recent Workflows
```bash
poetry run python scripts/debugging/inspect_workflow_execution.py --list
poetry run python scripts/debugging/inspect_workflow_execution.py --list --limit 5
```

### Inspect Specific Workflow
```bash
# Inspect the most recent workflow
poetry run python scripts/debugging/inspect_workflow_execution.py

# Inspect a specific workflow by ID
poetry run python scripts/debugging/inspect_workflow_execution.py --run-id 80761f8d-be08-4f1f-9386-5775c9314d4e
```

### Show Configuration
```bash
poetry run python scripts/debugging/inspect_workflow_execution.py --show-config
```

## Database Configuration

The script automatically:
1. Reads database settings from `.env` file
2. Detects if running locally vs in Docker
3. Adjusts connection (uses localhost:5434 when running locally)

No manual configuration needed!

## Output Format

The inspection shows:
- Workflow metadata (ID, status, timestamps)
- Workflow input data
- For each node:
  - Node details (name, type, status)
  - Input data (if stored)
  - Output data
  - Error messages (if any)
- Final workflow output

## Example Output

```
================================================================================
🔍 WORKFLOW EXECUTION INSPECTION
================================================================================
Run ID:      80761f8d-be08-4f1f-9386-5775c9314d4e
Status:      completed
Created:     2025-09-12 00:52:36.306109+00:00
Workflow:    Alert Analysis with Context Workflow

================================================================================
WORKFLOW INPUT
================================================================================
{
  "title": "Brute Force Attack Detected",
  "alert_id": "ALERT-2025-001",
  ...
}

================================================================================
NODE EXECUTIONS (9 nodes)
================================================================================

Node 1: preserve_alert
────────────────────────────────────────
Name:        Preserve Alert Data
Type:        transformation
Status:      completed

📥 INPUT:
  (No input stored)

📤 OUTPUT:
{
  "node_id": "transformation",
  "result": { ... }
}
...
```

## Troubleshooting

If you get connection errors:
1. Ensure PostgreSQL is running: `docker ps | grep postgres`
2. Check `.env` has correct database credentials
3. Verify port 5434 is exposed for local connections
