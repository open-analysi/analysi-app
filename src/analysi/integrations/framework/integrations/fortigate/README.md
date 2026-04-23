# FortiGate Firewall Integration

Fortinet FortiGate Firewall integration for IP containment and firewall policy management via the FortiGate REST API v2.

## Features

- **Health Check**: Test connectivity by querying the banned IPs monitoring endpoint
- **Block IP**: Add IP to a deny policy (creates address objects automatically)
- **Unblock IP**: Remove IP from a deny policy (preserves address objects)
- **List Policies**: List IPv4 firewall policies with pagination

## Configuration

### Credentials

| Field | Required | Description |
|-------|----------|-------------|
| `url` | Yes | FortiGate device URL (e.g., `https://myforti.contoso.com`) |
| `api_key` | Yes | REST API key for Bearer token authentication |
| `verify_server_cert` | No | Verify SSL certificate (default: `false`) |

### Settings

| Field | Default | Description |
|-------|---------|-------------|
| `vdom` | (empty) | Default virtual domain for API requests |
| `timeout` | 30 | HTTP request timeout in seconds |

## Actions

### health_check

Tests connectivity to the FortiGate device.

### block_ip

Blocks an IP by adding it to a FortiGate deny policy.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `ip` | Yes | | IP to block (IP, CIDR, or IP+mask) |
| `policy` | Yes | | IPv4 deny policy name |
| `address_type` | No | `dstaddr` | `srcaddr` or `dstaddr` |
| `vdom` | No | settings default | Virtual domain override |

### unblock_ip

Removes an IP from a FortiGate deny policy.

Parameters are the same as `block_ip`.

### list_policies

Lists configured IPv4 firewall policies.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `vdom` | No | settings default | Virtual domain to query |
| `limit` | No | 100 | Maximum policies to return |

## Archetype Mappings

**NetworkSecurity**:
- `block_ip` -> `block_ip`
- `unblock_ip` -> `unblock_ip`

## Migration Notes

### Intentional changes from upstream

- **API key auth only**: Session-based auth (username/password with CSRF token) is not migrated. API key auth is the modern recommended approach for automation.
- **Pagination improvement**: Added early termination when page returns fewer results than page size, preventing redundant API calls.
- **IP validation**: Uses Python `ipaddress` module instead of custom regex.

### upstream credentials not migrated

The upstream connector supported `username` and `password` for session-based login. This migration uses `api_key` (Bearer token) only. If session-based auth is needed, it can be added as a future enhancement.

## References

- [FortiGate REST API Reference](https://docs.fortinet.com/document/fortigate/latest/administration-guide/940602/using-apis)
- [FortiGate API Key Authentication](https://docs.fortinet.com/document/fortigate/latest/administration-guide/399023/rest-api-administrator)
