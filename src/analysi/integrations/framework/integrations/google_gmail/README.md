# Google Gmail Integration

This integration provides actions for interacting with Google Gmail using the Gmail API and Google Workspace Admin SDK.

## Overview

- **Integration ID**: `google_gmail`
- **Archetype**: EmailSecurity
- **Library**: Google API Python Client (synchronous, wrapped with asyncio.to_thread)

## Features

### Actions

1. **Health Check** - Test connectivity to Google Gmail API
2. **List Users** - Get the list of users from Google Workspace
3. **Run Query** - Search emails with query/filtering options
4. **Delete Email** - Delete emails from Gmail
5. **Get Email** - Retrieve email details via internet message id
6. **Get User** - Retrieve user details via email address
7. **Send Email** - Send emails via Gmail

## Configuration

### Credentials

- **login_email** (required): Login (Admin) email address for delegated access
- **key_json** (required, secret): Contents of Service Account JSON file from Google Cloud

### Settings

- **timeout** (optional): Request timeout in seconds (default: 30)
- **default_format** (optional): Default format for email retrieval - metadata, minimal, or raw (default: metadata)

## Setup

### Google Cloud Prerequisites

1. Create a Google Cloud project
2. Enable Gmail API and Admin SDK API
3. Create a service account
4. Download the service account JSON key file
5. Enable domain-wide delegation for the service account
6. Grant the service account appropriate OAuth scopes in Google Workspace Admin Console

### Required OAuth Scopes

- `https://www.googleapis.com/auth/gmail.readonly` - Read email messages
- `https://www.googleapis.com/auth/admin.directory.user.readonly` - Read user directory
- `https://mail.google.com/` - Full Gmail access (for deleting and sending emails)

## Usage Examples

### Health Check
```python
result = await health_check_action.execute()
# Returns: {"status": "success", "data": {"healthy": True, "domain": "example.com"}}
```

### List Users
```python
result = await list_users_action.execute(max_items=100)
# Returns: {"status": "success", "data": [...users...], "summary": {"total_users_returned": 100}}
```

### Run Query
```python
result = await run_query_action.execute(
    email="user@example.com",
    subject="Important",
    sender="boss@example.com",
    max_results=50
)
# Returns: {"status": "success", "data": [...messages...]}
```

### Delete Email
```python
result = await delete_email_action.execute(
    id="message_id_123,message_id_456",
    email="user@example.com"
)
# Returns: {"status": "success", "summary": {"deleted_emails": [...], "ignored_ids": [...]}}
```

### Get Email
```python
result = await get_email_action.execute(
    email="user@example.com",
    internet_message_id="<unique-id@mail.example.com>",
    format="metadata"
)
# Returns: {"status": "success", "data": [...email_details...]}
```

### Get User
```python
result = await get_user_action.execute(email="user@example.com")
# Returns: {"status": "success", "data": {"emailAddress": "user@example.com", ...}}
```

### Send Email
```python
result = await send_email_action.execute(
    to="recipient@example.com",
    subject="Test Email",
    body="This is a test email",
    cc="cc@example.com",
    from="sender@example.com"
)
# Returns: {"status": "success", "message": "Email sent with id sent123", "data": {...}}
```

## Archetype Mappings

This integration implements the following EmailSecurity archetype actions:

- `search_emails` → `run_query`
- `get_email_details` → `get_email`
- `delete_email` → `delete_email`
- `send_email` → `send_email`

## Technical Notes

- The Google API Python Client is a synchronous library, so all API calls are wrapped with `asyncio.to_thread()` to avoid blocking the event loop
- Service account credentials are used with domain-wide delegation to impersonate users
- The integration supports both Gmail API (for email operations) and Admin SDK (for user management)
- Email queries support Gmail's advanced search syntax

## Error Handling

Common error types:
- `ConfigurationError`: Missing or invalid credentials
- `ValidationError`: Missing or invalid parameters
- `GoogleAPIError`: Google API errors (authentication, quotas, etc.)

## Migration Notes
- prior actions migrated: 7 out of 8 (on_poll excluded as it's an ingestion action)
- All actions use proper async/await patterns with sync library wrapping
- Maintains compatibility with upstream parameter names and behavior
