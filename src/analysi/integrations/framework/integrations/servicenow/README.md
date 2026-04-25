# ServiceNow Integration

ServiceNow ticketing system integration for the Naxos framework.

## Overview

This integration provides connectivity to ServiceNow instances for managing incidents, tickets, and users through the ServiceNow REST API.

**Archetype**: TicketingSystem
**Library**: httpx (REST API)
**Authentication**: Basic Auth or OAuth

## Configuration

### Credentials

- **url** (required): ServiceNow instance URL (e.g., `https://your-instance.service-now.com`)
- **username**: Username for basic authentication
- **password**: Password for basic authentication
- **client_id**: OAuth client ID (alternative to basic auth)
- **client_secret**: OAuth client secret (alternative to basic auth)

### Settings

- **timeout**: Request timeout in seconds (default: 30)
- **max_results**: Default maximum number of results for list operations (default: 100)

## Actions

### Health Check
Test connectivity to ServiceNow instance.

**Parameters**: None

### Create Ticket
Create a new ticket in ServiceNow.

**Parameters**:
- `table` (string, optional): Table to create ticket in (default: "incident")
- `short_description` (string): Short description of the ticket
- `description` (string): Detailed description
- `fields` (string): JSON string of additional fields

### Get Ticket
Retrieve details of a specific ticket.

**Parameters**:
- `id` (string, required): Ticket ID (number) or sys_id
- `table` (string, optional): Table to query (default: "incident")
- `is_sys_id` (boolean, optional): Whether the ID is a sys_id

### Update Ticket
Update an existing ticket in ServiceNow.

**Parameters**:
- `id` (string, required): Ticket ID (number) or sys_id
- `table` (string, optional): Table name (default: "incident")
- `is_sys_id` (boolean, optional): Whether the ID is a sys_id
- `fields` (string, required): JSON string of fields to update

### List Tickets
List tickets from ServiceNow.

**Parameters**:
- `table` (string, optional): Table to query (default: "incident")
- `query` (string): ServiceNow query string to filter results
- `max_results` (integer): Maximum number of results to return

### Add Comment
Add a comment to a ServiceNow ticket.

**Parameters**:
- `id` (string, required): Ticket ID (number) or sys_id
- `table` (string, optional): Table name (default: "incident")
- `is_sys_id` (boolean, optional): Whether the ID is a sys_id
- `comment` (string, required): Comment text to add

### Query Users
Query users in the ServiceNow system.

**Parameters**:
- `query` (string): Query string to filter users
- `max_results` (integer): Maximum number of results to return

## Migration Notes
- Used httpx for async HTTP requests (upstream used requests)
- All actions properly handle async/await patterns
- Credentials and settings accessed via framework properties
- Archetype mappings configured for TicketingSystem archetype
- Comprehensive error handling with library-specific exceptions

## Example Usage

```python
# Create a ticket
result = await create_ticket_action.execute(
    short_description="Security incident detected",
    description="Suspicious login attempt from unknown IP",
    fields='{"priority": "1", "urgency": "1"}'
)

# Get ticket status
result = await get_ticket_action.execute(
    id="INC0001234",
    is_sys_id=False
)

# Update ticket
result = await update_ticket_action.execute(
    id="INC0001234",
    is_sys_id=False,
    fields='{"state": "2", "assigned_to": "user@example.com"}'
)

# Add comment
result = await add_comment_action.execute(
    id="INC0001234",
    comment="Investigating the incident"
)
```
