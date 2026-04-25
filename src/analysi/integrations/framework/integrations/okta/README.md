# Okta Integration

Identity and Access Management integration for Okta, supporting user lifecycle, authentication, group management, MFA, and role assignment.

## Overview

Okta is a leading cloud-based identity and access management platform. This integration provides comprehensive IAM capabilities including user management, group management, MFA push notifications, role assignment, and identity provider configuration.

**Archetype**: `IdentityProvider`

**Priority**: 70

## Features

### User Management
- **List Users**: Query users with filters
- **Get User**: Retrieve user details by ID/email/username
- **Disable User**: Suspend user account
- **Enable User**: Unsuspend user account
- **Reset Password**: Initiate password reset with email or UI link
- **Set Password**: Directly set user password
- **Clear User Sessions**: Revoke all active user sessions

### Group Management
- **List Groups**: Query groups with filters
- **Get Group**: Retrieve group details
- **Add Group**: Create new group
- **Get User Groups**: List groups a user belongs to
- **Add User to Group**: Add user to group membership
- **Remove User from Group**: Remove user from group

### Role Management
- **List Roles**: List roles assigned to a user
- **Assign Role**: Assign administrative role to user
- **Unassign Role**: Remove role from user

### Identity Providers
- **List Providers**: List configured identity providers (SAML2, GOOGLE, etc.)

### Multi-Factor Authentication
- **Send Push Notification**: Send MFA push notification for user verification

## Configuration

### Credentials

- **base_url**: Your Okta organization URL (e.g., `https://your-org.okta.com`)
- **api_token**: Okta API token (SSWS authentication)

### Settings

- **timeout**: HTTP request timeout in seconds (default: 30)
- **verify_ssl**: Verify SSL certificates (default: true)

## Authentication

Uses Okta SSWS (Single Sign-On Web Services) token authentication via the `Authorization` header.

## Archetype Mappings

Maps to the `IdentityProvider` archetype:

- `disable_user` → `disable_user`
- `enable_user` → `enable_user`
- `reset_password` → `reset_password`
- `get_user_details` → `get_user`
- `add_to_group` → `add_group_user`
- `revoke_sessions` → `clear_user_sessions`
- `enable_mfa` → `send_push_notification`

## Usage Examples

### Disable a compromised user account
```python
result = await okta.disable_user(id="user123")
```

### Reset user password
```python
result = await okta.reset_password(
    user_id="user@example.com",
    receive_type="Email"
)
```

### Add user to security group
```python
result = await okta.add_group_user(
    user_id="user123",
    group_id="group456"
)
```

### Send MFA push notification
```python
result = await okta.send_push_notification(
    email="user@example.com",
    factortype="push"
)
```

## Error Handling

The integration handles common Okta API errors:
- **401 Unauthorized**: Invalid API token
- **404 Not Found**: Resource (user/group/role) not found
- **429 Rate Limit**: API rate limit exceeded
- **400 Bad Request**: Validation errors (invalid role type, user already disabled, etc.)

## API Reference

Uses Okta REST API v1:
- Base URL: `https://your-org.okta.com/api/v1`
- Documentation: https://developer.okta.com/docs/reference/

## Supported Role Types

- `SUPER_ADMIN`
- `ORG_ADMIN`
- `API_ACCESS_MANAGEMENT_ADMIN`
- `APP_ADMIN`
- `USER_ADMIN`
- `MOBILE_ADMIN`
- `READ_ONLY_ADMIN`
- `HELP_DESK_ADMIN`
- `GROUP_MEMBERSHIP_ADMIN`
- `REPORT_ADMIN`

## Supported Identity Provider Types

- `SAML2`
- `FACEBOOK`
- `GOOGLE`
- `LINKEDIN`
- `MICROSOFT`

## Pagination

The integration automatically handles pagination for list operations:
- Default page size: 200 items
- Supports `limit` parameter to cap results
- Uses Okta's `after` cursor pagination

## MFA Factor Types

- `push`: Okta Verify push notification
- `sms`: SMS one-time password (partial support)
- `token:software:totp`: Software TOTP (partial support)

## Testing

Comprehensive unit tests cover all 19 actions with success cases, error handling, and edge cases.

```bash
poetry run pytest tests/unit/third_party_integrations/okta/ -v
```

## Dependencies

- `httpx`: Async HTTP client
- Standard library: `asyncio`, `logging`, `urllib.parse`

## Migration Notes

- Adapted from the upstream maintaining full compatibility
- Added proper async/await support using httpx
- Enhanced error handling with detailed error types
- Improved pagination handling
- Added archetype mappings for IdentityProvider
