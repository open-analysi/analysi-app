# Duo Security Integration

Multi-Factor Authentication (MFA) and identity verification integration using Duo's Auth API.

## Overview

Duo Security provides cloud-based MFA and user authentication. This integration enables:
- Health check / connectivity testing
- Duo Push notifications for action authorization
- Custom HMAC-SHA1 authentication

## Archetype

- **IdentityProvider**: MFA and authentication-related actions

## Configuration

### Credentials

- `api_host` (string, required): Duo Auth API endpoint (e.g., `api-xxxxxxxx.duosecurity.com`)
- `ikey` (string, required): Integration key from Duo Admin Panel
- `skey` (string, secret, required): Secret key from Duo Admin Panel

### Settings

- `timeout` (integer, default: 30): Request timeout in seconds
- `verify_server_cert` (boolean, default: true): Verify SSL/TLS certificate

## Actions

### Health Check (`health_check`)

Tests connectivity to the Duo Auth API.

**Parameters**: None

**Returns**:
```json
{
  "status": "success",
  "healthy": true,
  "message": "Duo API is accessible"
}
```

### Authorize (`authorize`)

Sends a Duo Push notification to a user's mobile device for approval.

**Parameters**:
- `user` (string, required): Username or email address
- `type` (string, optional): Request type shown in notification (default: "Analysi request")
- `info` (string, optional): Additional context shown in notification

**Returns** (on approval):
```json
{
  "status": "success",
  "result": "allow",
  "message": "Action authorized",
  "user": "user@example.com",
  "data": { ... }
}
```

**Returns** (on denial):
```json
{
  "status": "error",
  "result": "deny",
  "error": "Action not authorized: User denied or timeout",
  "error_type": "AuthorizationDenied",
  "user": "user@example.com"
}
```

## Authentication

Duo uses custom HMAC-SHA1 authentication:
1. Canonical string is created from: Date, Method, Host, Path, Parameters
2. Signed with secret key using HMAC-SHA1
3. Authorization header: `Basic base64(ikey:signature)`

## Error Handling

- **ConfigurationError**: Missing credentials (api_host, ikey, skey)
- **ValidationError**: Missing or invalid parameters
- **AuthorizationError**: User not permitted to authenticate
- **AuthorizationDenied**: User denied the push or timeout

## Example Usage

```python
# Test connectivity
result = await duo.health_check()

# Send authorization request
result = await duo.authorize(
    user="admin@corp.example",
    type="Critical Action",
    info="Approve firewall rule change"
)

if result["result"] == "allow":
    print("Action approved!")
else:
    print(f"Denied: {result['error']}")
```

## References

- [Duo Auth API Documentation](https://duo.com/docs/authapi)
- [Duo Admin Panel](https://admin.duosecurity.com/)
