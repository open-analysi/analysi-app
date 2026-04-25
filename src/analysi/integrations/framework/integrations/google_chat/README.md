# Google Chat Integration

Integrate with Google Chat to send and manage messages in Chat spaces.

## Overview

This integration allows you to interact with Google Chat spaces programmatically. It uses OAuth 2.0 authentication with refresh tokens to maintain secure access to the Google Chat API.

## Authentication

The integration uses OAuth 2.0 authentication with the following credentials:

- **Client ID**: OAuth application Client ID from Google Cloud Console
- **Client Secret**: OAuth application Client Secret from Google Cloud Console
- **Refresh Token**: OAuth refresh token obtained from the authorization flow

### Obtaining Credentials

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the Google Chat API
3. Create OAuth 2.0 credentials (Client ID and Client Secret)
4. Configure OAuth consent screen
5. Obtain a refresh token through the OAuth authorization flow
   - Use the authorization code grant type
   - Required scopes: `https://www.googleapis.com/auth/chat.messages`

## Actions

### Health Check

Tests connectivity with the Google Chat API by refreshing the access token.

**Parameters:** None

### Create Message

Creates a message in a Google Chat space.

**Parameters:**
- `parent_space` (required): Resource name of the space (e.g., `spaces/SPACE_ID`)
- `text_message` (required): Message content
- `requestid` (optional): Unique request ID for idempotency
- `messagereplyoption` (optional): Reply option (`MESSAGE_REPLY_OPTION_UNSPECIFIED`, `REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD`, or `REPLY_MESSAGE_OR_FAIL`)
- `messageid` (optional): Custom message ID

**Example:**
```python
result = await action.execute(
    parent_space="spaces/AAAAxxxxxxx",
    text_message="Hello from the integration!",
    requestid="unique-request-123"
)
```

### Read Message

Returns details about a message in a Google Chat space.

**Parameters:**
- `name` (required): Resource name of the message (e.g., `spaces/SPACE_ID/messages/MESSAGE_ID`)

**Example:**
```python
result = await action.execute(
    name="spaces/AAAAxxxxxxx/messages/yyyy.yyyy-yyyy"
)
```

## Archetype Mappings

This integration implements the **Communication** archetype with the following mappings:

- `send_message` → `create_message`
- `post_to_channel` → `create_message`

## Settings

- `timeout` (optional): Request timeout in seconds (default: 30)

## Error Handling

The integration handles various error types:

- `ValidationError`: Missing or invalid parameters
- `ConfigurationError`: Missing or invalid credentials
- `AuthenticationError`: Failed to refresh access token
- `HTTPStatusError`: HTTP errors from the Google Chat API
- `RequestError`: Network or connection errors
- `TimeoutException`: Request timeout errors

## Implementation Notes

- Async/await pattern using httpx
- OAuth flow using refresh tokens only
- Standardized error handling and response format
- Archetype support for Communication workflows
