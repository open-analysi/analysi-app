# JIRA Integration

Naxos integration for JIRA ticketing system, supporting both JIRA Cloud and JIRA On-Premise instances.

## Overview

This integration provides comprehensive JIRA ticket management capabilities including creating, updating, retrieving, and deleting tickets, as well as managing projects and users.

**Archetype**: TicketingSystem

## Features

- Create, update, and delete tickets
- Retrieve ticket information
- Add comments to tickets
- Change ticket status via transitions
- List projects and tickets
- Search for users
- Support for both JIRA Cloud and On-Premise

## Configuration

### Credentials

- **JIRA URL** (required): Full URL to your JIRA instance
  - Cloud: `https://yourcompany.atlassian.net`
  - On-Prem: `https://jira.yourcompany.com:8080`
- **Username** (required): JIRA username or email address
- **Password/API Token** (required):
  - JIRA Cloud: Use API token (generate from Account Settings → Security → API tokens)
  - JIRA On-Prem: Use account password or Personal Access Token (PAT)
- **Verify SSL Certificate** (optional): Whether to verify SSL certificates (default: true)

### Settings

- **Request Timeout** (optional): HTTP request timeout in seconds (default: 60)

## Actions

### Health Check
Check connectivity to JIRA API and retrieve server information.

**Parameters**: None

**Returns**:
- Server version
- Current user information
- Server title

### Create Ticket
Create a new JIRA ticket (issue).

**Parameters**:
- `summary` (required): Ticket title/summary
- `project_key` (required): Project key (e.g., "PROJ")
- `issue_type` (required): Issue type (e.g., "Bug", "Task", "Story")
- `description` (optional): Detailed description
- `priority` (optional): Priority (e.g., "High", "Medium", "Low")
- `assignee` (optional): Assignee username
- `labels` (optional): Comma-separated labels
- `fields` (optional): Additional custom fields as JSON object

**Returns**:
- Ticket ID and key
- Ticket URL

### Get Ticket
Retrieve detailed information about a ticket.

**Parameters**:
- `ticket_id` (required): Ticket ID or key (e.g., "PROJ-123")

**Returns**:
- Complete ticket information including status, priority, assignee, etc.

### Update Ticket
Update an existing ticket.

**Parameters**:
- `ticket_id` (required): Ticket ID or key
- `summary` (optional): Updated summary
- `description` (optional): Updated description
- `priority` (optional): Updated priority
- `assignee` (optional): Updated assignee
- `labels` (optional): Updated labels
- `fields` (optional): Additional fields to update

### Add Comment
Add a comment to a ticket.

**Parameters**:
- `ticket_id` (required): Ticket ID or key
- `comment` (required): Comment text

### Set Ticket Status
Change ticket status via workflow transition.

**Parameters**:
- `ticket_id` (required): Ticket ID or key
- `status` (required): Target status name
- `comment` (optional): Comment to add with transition

**Note**: Status change uses JIRA transitions. The action will find the appropriate transition to reach the target status.

### Delete Ticket
Delete a ticket permanently.

**Parameters**:
- `ticket_id` (required): Ticket ID or key

### List Projects
List all accessible JIRA projects.

**Parameters**: None

**Returns**:
- List of projects with ID, key, name, and type

### List Tickets
List tickets using JQL (JIRA Query Language).

**Parameters**:
- `project_key` (optional): Filter by project
- `jql` (optional): Custom JQL query
- `max_results` (optional): Maximum results (default: 100)
- `start_index` (optional): Starting index for pagination (default: 0)

### Search Users
Search for JIRA users.

**Parameters**:
- `query` (required): Username or display name to search
- `max_results` (optional): Maximum results

## Archetype Mappings

This integration implements the `TicketingSystem` archetype with the following mappings:

- `create_ticket` → `create_ticket`
- `update_ticket` → `update_ticket`
- `get_ticket_status` → `get_ticket`
- `add_comment` → `add_comment`
- `close_ticket` → `set_ticket_status`
- `assign_ticket` → `update_ticket`

## Authentication

### JIRA Cloud
1. Generate an API token from your Atlassian account:
   - Go to https://id.atlassian.com/manage-profile/security/api-tokens
   - Click "Create API token"
   - Use your email as username and the API token as password

### JIRA On-Premise
- Use your JIRA username and password
- Or create a Personal Access Token (PAT) for better security

## Example Usage

```python
# Create a ticket
result = await jira.create_ticket(
    summary="Security incident - Suspicious activity detected",
    project_key="SEC",
    issue_type="Bug",
    description="Suspicious login attempts from IP 192.168.1.100",
    priority="High",
    labels="security,incident,urgent"
)
# Returns: {"status": "success", "ticket_key": "SEC-123", ...}

# Get ticket information
result = await jira.get_ticket(ticket_id="SEC-123")

# Add a comment
result = await jira.add_comment(
    ticket_id="SEC-123",
    comment="Investigation started. IP has been blocked."
)

# Update ticket status
result = await jira.set_ticket_status(
    ticket_id="SEC-123",
    status="In Progress",
    comment="Investigation in progress"
)

# List tickets in a project
result = await jira.list_tickets(
    project_key="SEC",
    max_results=50
)

# Search with custom JQL
result = await jira.list_tickets(
    jql="project = SEC AND status = Open AND priority = High"
)
```

## Error Handling

All actions return structured responses with proper error types:

- `ValidationError`: Missing or invalid parameters
- `ConfigurationError`: Missing or invalid credentials
- `HTTPError`: HTTP request failures
- `AuthenticationError`: Authentication failures
- `NotFoundError`: Resource not found

## Notes

- JQL (JIRA Query Language) is powerful but requires knowledge of JIRA field names and syntax
- Status transitions depend on your JIRA workflow configuration
- Custom fields vary by JIRA instance and project
- JIRA Cloud and On-Premise have slight API differences (mostly handled automatically)

## Migration Notes

This integration was adapted from the JIRA connector with the following improvements:

- Async/await support using httpx instead of synchronous requests
- Cleaner error handling and validation
- Better type hints and documentation
- Simplified credential management
- Archetype support for standardized ticketing operations
