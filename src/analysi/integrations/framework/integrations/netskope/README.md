# Netskope Integration

CASB/SSE platform integration for cloud security policy enforcement.

## Features

- URL blocklist management (add, remove, update, deploy)
- File hash blocklist management (add, remove)
- Event querying by IP address (page and application events)
- Quarantined file metadata retrieval
- Dual API key support (v1 for file/quarantine, v2 for URL lists/events)

## Configuration

### Credentials

| Field | Required | Description |
|-------|----------|-------------|
| `server_url` | Yes | Netskope tenant URL (e.g., `https://tenant.goskope.com`) |
| `v2_api_key` | Recommended | REST API v2 token for URL list and event operations |
| `api_key` | Optional | REST API v1 token for file hash and quarantine operations |

At least one API key (v1 or v2) must be provided.

### Settings

| Field | Default | Description |
|-------|---------|-------------|
| `list_name` | `phantom_list` | Name of the URL/hash list on Netskope |
| `timeout` | `30` | HTTP request timeout in seconds |

## Actions

| Action | API Version | Description |
|--------|------------|-------------|
| `health_check` | v1 + v2 | Test connectivity to Netskope tenant |
| `add_url_to_list` | v2 | Add URL to blocklist |
| `remove_url_from_list` | v2 | Remove URL from blocklist |
| `update_url_list` | v2 | Replace entire URL list and deploy |
| `add_hash_to_list` | v1 | Add file hash to blocklist |
| `remove_hash_from_list` | v1 | Remove file hash from blocklist |
| `get_file` | v1 | Retrieve quarantined file metadata |
| `run_query` | v2 | Query events by IP address |

## Archetype Mappings

**NetworkSecurity** archetype:
- `block_url` -> `add_url_to_list`
- `unblock_url` -> `remove_url_from_list`
- `update_policy` -> `update_url_list`

## Migration Notes

### Implemented (8 actions)
- `test_connectivity` -> `health_check`
- `add_url_list` -> `add_url_to_list`
- `remove_url_list` -> `remove_url_from_list`
- `update_url_list` -> `update_url_list`
- `add_file_list` -> `add_hash_to_list`
- `remove_file_list` -> `remove_hash_from_list`
- `get_file` -> `get_file`
- `run_query` -> `run_query`

### Not Implemented (deferred)
- `on_poll` - Alert ingestion (use AlertSource archetype separately)
- `list_files` - List quarantined files
- `update_file_list` - Push full hash list to Netskope
- SCIM user/group management (get/create users, get/create groups, user-to-group)

