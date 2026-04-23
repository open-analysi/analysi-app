# Microsoft Teams Integration

This integration allows you to interact with Microsoft Teams to send messages, manage channels, create meetings, and collaborate with teams using the Microsoft Graph API.

## Features

- **Health Check**: Test connectivity to Microsoft Teams
- **List Users**: List all users in your organization
- **List Groups**: List all groups
- **List Teams**: List all teams
- **List Channels**: List channels in a team
- **Send Channel Message**: Send messages to team channels
- **List Chats**: List chats with optional filters
- **Send Chat Message**: Send messages to specific chats
- **Send Direct Message**: Send direct messages to users
- **Create Meeting**: Create online meetings
- **Get Channel Message**: Retrieve channel messages
- **Get Chat Message**: Retrieve chat messages

## Configuration

### Credentials

- **tenant_id** (required): Your Azure AD Tenant ID
- **client_id** (required): Application (client) ID from Azure AD app registration
- **client_secret** (required): Client secret from Azure AD app registration
- **access_token** (required): Microsoft Graph API access token obtained via OAuth 2.0

### Settings

- **timeout** (optional): Request timeout in seconds (default: 30)
- **timezone** (optional): Timezone for calendar events, e.g., 'UTC', 'America/New_York' (default: UTC)

## Setup

### Azure AD App Registration

1. Register an application in Azure AD
2. Configure API permissions for Microsoft Graph:
   - `User.Read.All`
   - `Group.Read.All`
   - `Chat.ReadWrite`
   - `Channel.ReadBasic.All`
   - `OnlineMeetings.ReadWrite`
3. Generate a client secret
4. Obtain an access token using OAuth 2.0 authorization code flow

### OAuth 2.0 Token Flow

```python
# Token endpoint
https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token

# Required parameters
{
    "grant_type": "authorization_code",
    "client_id": "{client_id}",
    "client_secret": "{client_secret}",
    "code": "{authorization_code}",
    "redirect_uri": "{redirect_uri}",
    "scope": "https://graph.microsoft.com/.default"
}
```

## Actions

### Communication Archetype Mappings

This integration implements the **Communication** archetype with the following mappings:

- `send_message` → `send_channel_message`
- `post_to_channel` → `send_channel_message`
- `create_channel` → `list_channels`

## Example Usage

### Send a Channel Message

```python
result = await send_channel_message.execute(
    group_id="team-group-id",
    channel_id="channel-id",
    message="Hello from the integration!"
)
```

### Create an Online Meeting

```python
result = await create_meeting.execute(
    subject="Security Review Meeting",
    add_calendar_event=True,
    start_time="2024-01-15T10:00:00Z",
    end_time="2024-01-15T11:00:00Z",
    attendees="user1@example.com,user2@example.com"
)
```

### Send a Direct Message

```python
result = await send_direct_message.execute(
    user_id="user-azure-ad-id",
    message="Important security alert!"
)
```

## Implementation Notes

1. **Async Implementation**: All actions use `httpx.AsyncClient` for async HTTP requests
2. **OAuth Handling**: OAuth flow is handled externally; integration expects a valid access token
3. **Standardized Error Handling**: Uses consistent error types and response format
4. **Microsoft Graph API**: Uses Microsoft Graph API v1.0 endpoints
5. **No Bot Framework**: Does not depend on Bot Framework Adapter

## Known Limitations

- The `ask_question` action is not supported as it requires Bot Framework integration
- Token refresh must be handled externally; integration expects a valid access token
- Admin consent workflow must be completed separately in Azure AD portal

## API Reference

- [Microsoft Graph API Documentation](https://docs.microsoft.com/en-us/graph/api/overview)
- [Teams API Reference](https://docs.microsoft.com/en-us/graph/api/resources/teams-api-overview)
- [Chat API Reference](https://docs.microsoft.com/en-us/graph/api/resources/chat)
