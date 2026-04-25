# Mimecast Integration

Email security integration for Mimecast using the API v2 with OAuth2 client credentials authentication.

## Features

- URL Protection: decode rewritten URLs, list/add managed URLs
- Sender Management: block and unblock senders
- Message Tracking: search tracked emails by sender, recipient, subject, IP
- Message Details: retrieve full email details by Mimecast ID

## Configuration

### Credentials
| Field | Required | Description |
|-------|----------|-------------|
| client_id | Yes | OAuth2 Client ID from Mimecast API 2.0 Application |
| client_secret | Yes | OAuth2 Client Secret |

### Settings
| Field | Default | Description |
|-------|---------|-------------|
| base_url | `https://api.services.mimecast.com` | API base URL (varies by region) |
| timeout | 30 | HTTP request timeout in seconds |

Regional base URLs: `us-api.mimecast.com`, `eu-api.mimecast.com`, `de-api.mimecast.com`, `au-api.mimecast.com`, `za-api.mimecast.com`

## Actions

| Action | Description |
|--------|-------------|
| health_check | Test connectivity to the Mimecast API |
| decode_url | Decode Mimecast-rewritten URLs back to original |
| get_email | Get details of a specific email message |
| list_urls | List managed URLs from TTP URL Protection |
| block_sender | Add sender to block list |
| unblock_sender | Remove sender from block list |
| search_messages | Search tracked emails by various criteria |
| get_managed_url | Look up managed URL details by ID |
| add_managed_url | Add URL to managed URL list |

## Archetype Mappings

**EmailSecurity**:
- `block_sender` -> `block_sender`
- `unblock_sender` -> `unblock_sender`
- `get_email_trace` -> `search_messages`

## Migration Notes

- Adapted from `mimecast_connector.py`
- Auth upgraded from legacy app key/secret to OAuth2 client credentials
- prior actions `blocklist_url`, `unblocklist_url`, `allowlist_url`, `unallowlist_url` consolidated into `add_managed_url` (with action parameter)
- prior actions `add_member`, `remove_member`, `list_groups`, `list_members`, `find_member` (directory management) not migrated -- outside email security scope
- upstream `blocklist_sender` / `allowlist_sender` mapped to `block_sender` / `unblock_sender`
- upstream `run_query` mapped to `search_messages` with clearer parameter names
