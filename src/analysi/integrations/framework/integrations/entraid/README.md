# Microsoft Entra ID Integration

Cloud identity provider via Microsoft Graph REST API. Uses OAuth2 client credentials flow for authentication.

## Actions

| Action | Description | Key Params |
|--------|-------------|------------|
| `health_check` | Verify API connectivity | - |
| `get_user` | Look up user by UPN/email/ID | `user_id` |
| `disable_user` | Block user sign-in | `user_id` |
| `enable_user` | Re-enable user sign-in | `user_id` |
| `reset_password` | Force password reset | `user_id`, `temp_password?`, `force_change?` |
| `list_groups` | List groups a user belongs to | `user_id` |
| `get_group_members` | List members of a group | `group_id` |
| `revoke_sessions` | Revoke all active sessions | `user_id` |
| `list_sign_ins` | Get recent sign-in activity | `user_id`, `top?` |

## Configuration

**Credentials** (all required):
- `tenant_id` - Azure AD directory (tenant) ID
- `client_id` - Application (client) ID from App Registration
- `client_secret` - Client secret value

**Settings**:
- `base_url` - Graph API URL (default: `https://graph.microsoft.com/v1.0`, change for sovereign clouds)
- `timeout` - Request timeout in seconds (default: 30)

## Azure App Registration

Required Microsoft Graph **application** permissions:
- `User.ReadWrite.All` - Read/write user profiles, disable/enable accounts, reset passwords
- `Group.Read.All` - Read group memberships
- `AuditLog.Read.All` - Read sign-in logs
- `Directory.ReadWrite.All` - Revoke sign-in sessions

Grant admin consent after adding permissions.

## Archetype Mappings

| Abstract Action | Concrete Action |
|-----------------|-----------------|
| `get_user_details` | `get_user` |
| `disable_user` | `disable_user` |
| `enable_user` | `enable_user` |
| `reset_password` | `reset_password` |
| `revoke_sessions` | `revoke_sessions` |
| `get_authentication_logs` | `list_sign_ins` |

## Migration Notes
- Uses `self.http_request()` with framework retry instead of raw `requests`
- Token acquisition happens per-action call (no persistent state)
- 404 on `get_user` returns `success_result(not_found=True)` instead of error (safe for Cy scripts)
- Pagination uses `@odata.nextLink` following (same as upstream)
- `list_groups` filters `memberOf` to `#microsoft.graph.group` objects only
