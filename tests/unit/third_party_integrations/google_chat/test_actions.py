"""Unit tests for Google Chat integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.google_chat.actions import (
    CreateMessageAction,
    HealthCheckAction,
    ReadMessageAction,
)


@pytest.fixture
def integration_id():
    """Integration ID for testing."""
    return "test-google-chat-integration"


@pytest.fixture
def credentials():
    """Test credentials."""
    return {
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "refresh_token": "test_refresh_token",
    }


@pytest.fixture
def settings():
    """Test settings."""
    return {"timeout": 30}


@pytest.fixture
def health_check_action(integration_id, credentials, settings):
    """Create a HealthCheckAction instance for testing."""
    return HealthCheckAction(integration_id, "health_check", settings, credentials)


@pytest.fixture
def create_message_action(integration_id, credentials, settings):
    """Create a CreateMessageAction instance for testing."""
    return CreateMessageAction(integration_id, "create_message", settings, credentials)


@pytest.fixture
def read_message_action(integration_id, credentials, settings):
    """Create a ReadMessageAction instance for testing."""
    return ReadMessageAction(integration_id, "read_message", settings, credentials)


# HealthCheckAction Tests


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {"access_token": "test_access_token"}

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True
    assert "Successfully authenticated" in result["message"]


@pytest.mark.asyncio
async def test_health_check_missing_credentials(integration_id, settings):
    """Test health check with missing credentials."""
    incomplete_credentials = {}
    action = HealthCheckAction(
        integration_id, "health_check", settings, incomplete_credentials
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "Missing required credentials" in result["error"]


@pytest.mark.asyncio
async def test_health_check_token_refresh_failed(health_check_action):
    """Test health check when token refresh fails."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {"error": "invalid_grant"}

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "AuthenticationError"


@pytest.mark.asyncio
async def test_health_check_http_error(health_check_action):
    """Test health check with HTTP error."""

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=Exception("Connection error"),
    ):
        with pytest.raises(Exception, match="Connection error"):
            await health_check_action.execute()


# CreateMessageAction Tests


@pytest.mark.asyncio
async def test_create_message_success(create_message_action):
    """Test successful message creation."""
    # Mock token refresh
    mock_token_response = MagicMock(spec=httpx.Response)
    mock_token_response.json.return_value = {"access_token": "test_access_token"}

    # Mock message creation
    mock_message_response = MagicMock(spec=httpx.Response)
    mock_message_response.json.return_value = {
        "name": "spaces/SPACE123/messages/MSG123",
        "text": "Test message",
        "createTime": "2024-01-01T00:00:00Z",
    }

    with patch.object(
        create_message_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=[mock_token_response, mock_message_response],
    ):
        result = await create_message_action.execute(
            parent_space="spaces/SPACE123", text_message="Test message"
        )

    assert result["status"] == "success"
    assert "Message sent" in result["message"]
    assert result["data"]["name"] == "spaces/SPACE123/messages/MSG123"


@pytest.mark.asyncio
async def test_create_message_missing_parent_space(create_message_action):
    """Test create message with missing parent_space parameter."""
    result = await create_message_action.execute(text_message="Test message")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "parent_space" in result["error"]


@pytest.mark.asyncio
async def test_create_message_missing_text_message(create_message_action):
    """Test create message with missing text_message parameter."""
    result = await create_message_action.execute(parent_space="spaces/SPACE123")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "text_message" in result["error"]


@pytest.mark.asyncio
async def test_create_message_missing_credentials(integration_id, settings):
    """Test create message with missing credentials."""
    incomplete_credentials = {}
    action = CreateMessageAction(
        integration_id, "create_message", settings, incomplete_credentials
    )

    result = await action.execute(
        parent_space="spaces/SPACE123", text_message="Test message"
    )

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "Missing required credentials" in result["error"]


@pytest.mark.asyncio
async def test_create_message_with_optional_params(create_message_action):
    """Test create message with optional parameters."""
    # Mock token refresh
    mock_token_response = MagicMock(spec=httpx.Response)
    mock_token_response.json.return_value = {"access_token": "test_access_token"}

    # Mock message creation
    mock_message_response = MagicMock(spec=httpx.Response)
    mock_message_response.json.return_value = {
        "name": "spaces/SPACE123/messages/MSG123",
        "text": "Test message",
        "createTime": "2024-01-01T00:00:00Z",
    }

    with patch.object(
        create_message_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=[mock_token_response, mock_message_response],
    ):
        result = await create_message_action.execute(
            parent_space="spaces/SPACE123",
            text_message="Test message",
            requestid="unique-request-id",
            messagereplyoption="REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD",
            messageid="custom-message-id",
        )

    assert result["status"] == "success"
    assert "Message sent" in result["message"]


@pytest.mark.asyncio
async def test_create_message_http_error(create_message_action):
    """Test create message with HTTP error."""
    # Mock token refresh success
    mock_token_response = MagicMock(spec=httpx.Response)
    mock_token_response.json.return_value = {"access_token": "test_access_token"}

    # Mock message creation failure
    mock_error_response = MagicMock(spec=httpx.Response)
    mock_error_response.status_code = 404
    mock_error_response.json.return_value = {
        "error": {"message": "Space not found", "code": 404}
    }

    with patch.object(
        create_message_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=[
            mock_token_response,
            httpx.HTTPStatusError(
                "Not Found", request=MagicMock(), response=mock_error_response
            ),
        ],
    ):
        result = await create_message_action.execute(
            parent_space="spaces/INVALID", text_message="Test message"
        )

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


# ReadMessageAction Tests


@pytest.mark.asyncio
async def test_read_message_success(read_message_action):
    """Test successful message reading."""
    # Mock token refresh
    mock_token_response = MagicMock(spec=httpx.Response)
    mock_token_response.json.return_value = {"access_token": "test_access_token"}

    # Mock message retrieval
    mock_message_response = MagicMock(spec=httpx.Response)
    mock_message_response.json.return_value = {
        "name": "spaces/SPACE123/messages/MSG123",
        "text": "Test message",
        "createTime": "2024-01-01T00:00:00Z",
        "sender": {"name": "users/USER123", "type": "HUMAN"},
    }

    with patch.object(
        read_message_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=[mock_token_response, mock_message_response],
    ):
        result = await read_message_action.execute(
            name="spaces/SPACE123/messages/MSG123"
        )

    assert result["status"] == "success"
    assert "Reading message" in result["message"]
    assert result["data"]["name"] == "spaces/SPACE123/messages/MSG123"
    assert result["data"]["text"] == "Test message"


@pytest.mark.asyncio
async def test_read_message_missing_name(read_message_action):
    """Test read message with missing name parameter."""
    result = await read_message_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "name" in result["error"]


@pytest.mark.asyncio
async def test_read_message_missing_credentials(integration_id, settings):
    """Test read message with missing credentials."""
    incomplete_credentials = {}
    action = ReadMessageAction(
        integration_id, "read_message", settings, incomplete_credentials
    )

    result = await action.execute(name="spaces/SPACE123/messages/MSG123")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "Missing required credentials" in result["error"]


@pytest.mark.asyncio
async def test_read_message_http_error(read_message_action):
    """Test read message with HTTP error."""
    # Mock token refresh success
    mock_token_response = MagicMock(spec=httpx.Response)
    mock_token_response.json.return_value = {"access_token": "test_access_token"}

    # Mock message retrieval failure
    mock_error_response = MagicMock(spec=httpx.Response)
    mock_error_response.status_code = 404
    mock_error_response.json.return_value = {
        "error": {"message": "Message not found", "code": 404}
    }

    with patch.object(
        read_message_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=[
            mock_token_response,
            httpx.HTTPStatusError(
                "Not Found", request=MagicMock(), response=mock_error_response
            ),
        ],
    ):
        result = await read_message_action.execute(
            name="spaces/SPACE123/messages/INVALID"
        )

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


@pytest.mark.asyncio
async def test_read_message_request_error(read_message_action):
    """Test read message with request error."""
    # Mock token refresh success
    mock_token_response = MagicMock(spec=httpx.Response)
    mock_token_response.json.return_value = {"access_token": "test_access_token"}

    # Mock request error
    with patch.object(
        read_message_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=[
            mock_token_response,
            httpx.RequestError("Connection error"),
        ],
    ):
        result = await read_message_action.execute(
            name="spaces/SPACE123/messages/MSG123"
        )

    assert result["status"] == "error"
    assert result["error_type"] == "RequestError"
    assert "error" in result["error"].lower()
