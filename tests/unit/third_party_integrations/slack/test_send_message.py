"""
Unit tests for SendMessageAction.

Tests covering success cases, error handling, and validation.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.slack.actions import (
    SendMessageAction,
)


@pytest.fixture
def send_message_action():
    """Create SendMessageAction instance for testing."""
    credentials = {"bot_token": "test_bot_token"}
    settings = {"timeout": 30}
    return SendMessageAction(
        integration_id="test-slack",
        action_id="send_message",
        credentials=credentials,
        settings=settings,
    )


class TestSendMessageAction:
    """Tests for SendMessageAction."""

    @pytest.mark.asyncio
    async def test_send_message_success(self, send_message_action):
        """Test successful execution of send_message."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "channel": "C12345678",
            "ts": "1503435956.000247",
            "message": {
                "type": "message",
                "subtype": "bot_message",
                "text": "test_message",
                "ts": "1503435956.000247",
                "username": "bot",
                "bot_id": "B12345678",
            },
        }
        mock_response.raise_for_status = MagicMock()

        send_message_action.http_request = AsyncMock(return_value=mock_response)
        result = await send_message_action.execute(
            destination="test_destination", message="test_message"
        )

        # Verify success
        assert result["status"] == "success"
        assert result["channel"] == "C12345678"
        assert result["ts"] == "1503435956.000247"
        assert isinstance(result["message"], dict)
        assert result["message"]["text"] == "test_message"
        assert "full_data" in result
        assert result["full_data"]["ok"] is True

    @pytest.mark.asyncio
    async def test_send_message_missing_credentials(self):
        """Test error when credentials are missing."""
        action = SendMessageAction(
            integration_id="test-integration",
            action_id="send_message",
            credentials={},  # Empty credentials
            settings={},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert "error_type" in result

    @pytest.mark.asyncio
    async def test_send_message_http_401(self, send_message_action):
        """Test handling of HTTP 401 error."""
        send_message_action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "HTTP 401", request=MagicMock(), response=MagicMock(status_code=401)
            )
        )
        result = await send_message_action.execute(
            destination="test_dest", message="test"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_send_message_http_403(self, send_message_action):
        """Test handling of HTTP 403 error."""
        send_message_action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "HTTP 403", request=MagicMock(), response=MagicMock(status_code=403)
            )
        )
        result = await send_message_action.execute(
            destination="test_dest", message="test"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_send_message_http_404(self, send_message_action):
        """Test handling of HTTP 404 error."""
        send_message_action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "HTTP 404", request=MagicMock(), response=MagicMock(status_code=404)
            )
        )
        result = await send_message_action.execute(
            destination="test_dest", message="test"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_send_message_http_429(self, send_message_action):
        """Test handling of HTTP 429 error."""
        send_message_action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "HTTP 429", request=MagicMock(), response=MagicMock(status_code=429)
            )
        )
        result = await send_message_action.execute(
            destination="test_dest", message="test"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_send_message_http_500(self, send_message_action):
        """Test handling of HTTP 500 error."""
        send_message_action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "HTTP 500", request=MagicMock(), response=MagicMock(status_code=500)
            )
        )
        result = await send_message_action.execute(
            destination="test_dest", message="test"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_send_message_timeout_error(self, send_message_action):
        """Test handling of timeout errors.

        Note: TimeoutException is a subclass of RequestError in httpx.
        The action's except clauses have RequestError before TimeoutException,
        so TimeoutException gets caught by the RequestError handler.
        """
        send_message_action.http_request = AsyncMock(
            side_effect=httpx.TimeoutException("Request timed out")
        )
        result = await send_message_action.execute(
            destination="test_dest", message="test"
        )

        assert result["status"] == "error"
        # TimeoutException is caught by RequestError handler (comes first in exception chain)
        assert result["error_type"] == "RequestError"

    @pytest.mark.asyncio
    async def test_send_message_network_error(self, send_message_action):
        """Test handling of network/connection errors."""
        send_message_action.http_request = AsyncMock(
            side_effect=httpx.RequestError("Connection failed")
        )
        result = await send_message_action.execute(
            destination="test_dest", message="test"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "RequestError"

    @pytest.mark.asyncio
    async def test_send_message_missing_destination(self, send_message_action):
        """Test error when required parameter 'destination' is missing."""
        result = await send_message_action.execute()

        assert result["status"] == "error"
        assert "destination" in result.get("error", "").lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_send_message_missing_message_and_blocks(self, send_message_action):
        """Test error when both 'message' and 'blocks' are missing (either/or validation)."""
        result = await send_message_action.execute(destination="test_dest")

        assert result["status"] == "error"
        assert (
            "message" in result.get("error", "").lower()
            or "blocks" in result.get("error", "").lower()
        )
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_send_message_with_message_only(self, send_message_action):
        """Test that message parameter alone (without blocks) is sufficient."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "channel": "C12345",
            "ts": "123.456",
            "message": {"text": "test"},
        }
        mock_response.raise_for_status = MagicMock()

        send_message_action.http_request = AsyncMock(return_value=mock_response)
        result = await send_message_action.execute(
            destination="test_dest", message="test"
        )

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_send_message_with_blocks_only(self, send_message_action):
        """Test that blocks parameter alone (without message) is sufficient."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "channel": "C12345",
            "ts": "123.456",
            "message": {"blocks": []},
        }
        mock_response.raise_for_status = MagicMock()

        send_message_action.http_request = AsyncMock(return_value=mock_response)
        result = await send_message_action.execute(destination="test_dest", blocks="[]")

        assert result["status"] == "success"
