# Microsoft Exchange On-Premises EWS Integration

Integration with Microsoft Exchange Server (on-premises) using Exchange Web Services (EWS) SOAP protocol.

## Overview

This integration provides email investigation and management capabilities for on-premises Exchange Server deployments via the EWS SOAP API.

## Architecture

- **Protocol**: SOAP over HTTPS
- **Library**: httpx (async HTTP) with lxml for SOAP message building
- **Authentication**: NTLM or Basic authentication
- **Supported Versions**: Exchange Server 2013, 2016

## Actions

### Connector Actions
- **health_check**: Test connectivity to Exchange server

### Tool Actions
- **lookup_email**: Resolve email address to get user details
- **run_query**: Search for emails in a mailbox
- **get_email**: Get full email details by Exchange item ID
- **delete_email**: Delete an email (hard delete)
- **move_email**: Move an email to a different folder
- **copy_email**: Copy an email to a different folder

## Configuration

### Credentials
- `url`: EWS endpoint URL (e.g., `https://mail.company.com/EWS/Exchange.asmx`)
- `username`: Username for authentication
- `password`: Password for authentication
- `version`: Exchange version (2013 or 2016)
- `verify_server_cert`: Whether to verify SSL certificate

### Settings
- `timeout`: Request timeout in seconds (default: 30)
- `use_impersonation`: Use Exchange impersonation for mailbox access

## Archetype Mapping

**EmailSecurity Archetype**:
- `search_emails` → run_query
- `get_email_details` → get_email
- `delete_email` → delete_email
- `quarantine_email` → move_email

## Testing

Run unit tests:
```bash
poetry run pytest tests/unit/third_party_integrations/exchange_onprem/ -v
```

All 21 tests pass, covering:
- Health check scenarios
- Email lookup and resolution
- Email search with various parameters
- Email retrieval
- Email deletion, moving, and copying
- Error handling for missing parameters and credentials

## Notes

- This integration does NOT use the exchangelib Python library
- It implements custom SOAP message building using lxml
- Supports impersonation for accessing other user mailboxes
- Email search supports folder specification and result pagination
