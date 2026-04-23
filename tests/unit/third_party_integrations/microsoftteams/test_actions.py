"""
Unit tests for Microsoft Teams integration actions.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.microsoftteams.actions import (
    CreateMeetingAction,
    GetChannelMessageAction,
    GetChatMessageAction,
    HealthCheckAction,
    ListChatsAction,
    ListUsersAction,
    SendChannelMessageAction,
    SendDirectMessageAction,
)


@pytest.fixture
def credentials():
    """Return test credentials."""
    return {
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "access_token": "test-access-token",
    }


@pytest.fixture
def settings():
    """Return test settings."""
    return {
        "tenant_id": "test-tenant-id",
        "timeout": 30,
        "timezone": "UTC",
    }


# Health Check Action Tests
@pytest.mark.asyncio
async def test_health_check_success(credentials, settings):
    """Test successful health check."""
    action = HealthCheckAction(
        integration_id="microsoftteams",
        action_id="health_check",
        credentials=credentials,
        settings=settings,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {
        "id": "user123",
        "userPrincipalName": "test@example.com",
        "displayName": "Test User",
        "mail": "test@example.com",
    }

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute()

    assert result["status"] == "success"
    assert result["data"]["user_id"] == "user123"
    assert result["data"]["user_principal_name"] == "test@example.com"


@pytest.mark.asyncio
async def test_health_check_missing_token(settings):
    """Test health check with missing access token."""
    credentials = {"tenant_id": "test", "client_id": "test", "client_secret": "test"}
    action = HealthCheckAction(
        integration_id="microsoftteams",
        action_id="health_check",
        credentials=credentials,
        settings=settings,
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "access_token" in result["error"]


@pytest.mark.asyncio
async def test_health_check_http_error(credentials, settings):
    """Test health check with HTTP error."""
    action = HealthCheckAction(
        integration_id="microsoftteams",
        action_id="health_check",
        credentials=credentials,
        settings=settings,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 401

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=__import__("httpx").HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        ),
    ):
        result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


# List Users Action Tests
@pytest.mark.asyncio
async def test_list_users_success(credentials, settings):
    """Test successful user listing."""
    action = ListUsersAction(
        integration_id="microsoftteams",
        action_id="list_users",
        credentials=credentials,
        settings=settings,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {
        "value": [
            {"id": "user1", "displayName": "User One"},
            {"id": "user2", "displayName": "User Two"},
        ]
    }

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute()

    assert result["status"] == "success"
    assert result["total_users"] == 2
    assert len(result["users"]) == 2


# Send Channel Message Action Tests
@pytest.mark.asyncio
async def test_send_channel_message_success(credentials, settings):
    """Test successful channel message sending."""
    action = SendChannelMessageAction(
        integration_id="microsoftteams",
        action_id="send_channel_message",
        credentials=credentials,
        settings=settings,
    )

    mock_verify_response = MagicMock(spec=httpx.Response)
    mock_verify_response.json.return_value = {
        "value": [{"id": "channel123", "displayName": "General"}]
    }

    mock_send_response = MagicMock(spec=httpx.Response)
    mock_send_response.json.return_value = {
        "id": "msg123",
        "body": {"content": "Test message"},
    }

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=[mock_verify_response, mock_send_response],
    ):
        result = await action.execute(
            group_id="group123", channel_id="channel123", message="Test message"
        )

    assert result["status"] == "success"
    assert "Message sent successfully" in result["message"]


@pytest.mark.asyncio
async def test_send_channel_message_missing_params(credentials, settings):
    """Test send message with missing parameters."""
    action = SendChannelMessageAction(
        integration_id="microsoftteams",
        action_id="send_channel_message",
        credentials=credentials,
        settings=settings,
    )

    result = await action.execute(group_id="group123")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


# Send Direct Message Action Tests
@pytest.mark.asyncio
async def test_send_direct_message_success(credentials, settings):
    """Test successful direct message sending."""
    action = SendDirectMessageAction(
        integration_id="microsoftteams",
        action_id="send_direct_message",
        credentials=credentials,
        settings=settings,
    )

    mock_me_response = MagicMock(spec=httpx.Response)
    mock_me_response.json.return_value = {"id": "current-user-id"}

    mock_chats_response = MagicMock(spec=httpx.Response)
    mock_chats_response.json.return_value = {
        "value": [
            {
                "id": "chat123",
                "chatType": "oneOnOne",
                "members": [
                    {"userId": "current-user-id"},
                    {"userId": "target-user-id"},
                ],
            }
        ]
    }

    mock_send_response = MagicMock(spec=httpx.Response)
    mock_send_response.json.return_value = {
        "id": "msg123",
        "body": {"content": "Test message"},
    }

    with patch.object(
        action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=[mock_me_response, mock_chats_response, mock_send_response],
    ):
        result = await action.execute(user_id="target-user-id", message="Test message")

    assert result["status"] == "success"
    assert "Direct message sent successfully" in result["message"]


# List Chats Action Tests
@pytest.mark.asyncio
async def test_list_chats_with_filter(credentials, settings):
    """Test chat listing with type filter."""
    action = ListChatsAction(
        integration_id="microsoftteams",
        action_id="list_chats",
        credentials=credentials,
        settings=settings,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {
        "value": [
            {"id": "chat1", "chatType": "oneOnOne"},
            {"id": "chat2", "chatType": "group"},
        ]
    }

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute(chat_type="oneOnOne")

    assert result["status"] == "success"
    assert result["total_chats"] == 1
    assert result["chats"][0]["chatType"] == "oneOnOne"


@pytest.mark.asyncio
async def test_list_chats_invalid_type(credentials, settings):
    """Test chat listing with invalid type."""
    action = ListChatsAction(
        integration_id="microsoftteams",
        action_id="list_chats",
        credentials=credentials,
        settings=settings,
    )

    result = await action.execute(chat_type="invalid")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


# Create Meeting Action Tests
@pytest.mark.asyncio
async def test_create_meeting_simple(credentials, settings):
    """Test simple meeting creation."""
    action = CreateMeetingAction(
        integration_id="microsoftteams",
        action_id="create_meeting",
        credentials=credentials,
        settings=settings,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {
        "id": "meeting123",
        "joinWebUrl": "https://teams.microsoft.com/l/meetup/...",
    }

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute(subject="Test Meeting")

    assert result["status"] == "success"
    assert "Meeting created successfully" in result["message"]


# Get Message Actions Tests
@pytest.mark.asyncio
async def test_get_channel_message_success(credentials, settings):
    """Test successful channel message retrieval."""
    action = GetChannelMessageAction(
        integration_id="microsoftteams",
        action_id="get_channel_message",
        credentials=credentials,
        settings=settings,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {
        "id": "msg123",
        "body": {"content": "Test message"},
        "from": {"user": {"displayName": "Test User"}},
    }

    with patch.object(
        action, "http_request", new_callable=AsyncMock, return_value=mock_response
    ):
        result = await action.execute(
            group_id="group123", channel_id="channel123", message_id="msg123"
        )

    assert result["status"] == "success"
    assert "Message retrieved successfully" in result["message"]


@pytest.mark.asyncio
async def test_get_chat_message_missing_params(credentials, settings):
    """Test get chat message with missing parameters."""
    action = GetChatMessageAction(
        integration_id="microsoftteams",
        action_id="get_chat_message",
        credentials=credentials,
        settings=settings,
    )

    result = await action.execute(chat_id="chat123")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "message_id" in result["error"]
