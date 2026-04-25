"""
Unit tests for ListChannelsAction.

Tests covering success cases, error handling, and validation.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.slack.actions import (
    ListChannelsAction,
)


@pytest.fixture
def list_channels_action():
    """Create ListChannelsAction instance for testing."""
    credentials = {"bot_token": "test_bot_token"}
    settings = {"timeout": 30}
    return ListChannelsAction(
        integration_id="test-slack",
        action_id="list_channels",
        credentials=credentials,
        settings=settings,
    )


class TestListChannelsAction:
    """Tests for ListChannelsAction."""

    @pytest.mark.asyncio
    async def test_list_channels_success(self, list_channels_action):
        """Test successful execution of list_channels."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "channels": [
                {"id": "C123", "name": "general", "is_private": False},
                {"id": "C456", "name": "random", "is_private": False},
                {"id": "C789", "name": "watercooler", "is_private": False},
            ],
            "response_metadata": {"next_cursor": ""},
        }
        mock_response.raise_for_status = MagicMock()

        list_channels_action.http_request = AsyncMock(return_value=mock_response)
        result = await list_channels_action.execute(limit=100)

        assert result["status"] == "success"
        assert "channels" in result
        channels = result["channels"]
        assert isinstance(channels, list)
        assert len(channels) == 3
        # Action adds "#" prefix to all channel names
        assert channels[0]["name"] == "#general"
        assert channels[1]["name"] == "#random"
        assert channels[2]["name"] == "#watercooler"
        assert result["num_public_channels"] == 3

    @pytest.mark.asyncio
    async def test_list_channels_missing_credentials(self):
        """Test error when credentials are missing."""
        action = ListChannelsAction(
            integration_id="test-integration",
            action_id="list_channels",
            credentials={},  # Empty credentials
            settings={},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert "error_type" in result

    @pytest.mark.asyncio
    async def test_list_channels_http_401(self, list_channels_action):
        """Test handling of HTTP 401 error."""
        list_channels_action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "HTTP 401", request=MagicMock(), response=MagicMock(status_code=401)
            )
        )
        result = await list_channels_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_list_channels_http_403(self, list_channels_action):
        """Test handling of HTTP 403 error."""
        list_channels_action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "HTTP 403", request=MagicMock(), response=MagicMock(status_code=403)
            )
        )
        result = await list_channels_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_list_channels_http_404(self, list_channels_action):
        """Test handling of HTTP 404 error."""
        list_channels_action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "HTTP 404", request=MagicMock(), response=MagicMock(status_code=404)
            )
        )
        result = await list_channels_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_list_channels_http_429(self, list_channels_action):
        """Test handling of HTTP 429 error."""
        list_channels_action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "HTTP 429", request=MagicMock(), response=MagicMock(status_code=429)
            )
        )
        result = await list_channels_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_list_channels_http_500(self, list_channels_action):
        """Test handling of HTTP 500 error."""
        list_channels_action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "HTTP 500", request=MagicMock(), response=MagicMock(status_code=500)
            )
        )
        result = await list_channels_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_list_channels_timeout_error(self, list_channels_action):
        """Test handling of timeout errors.

        Note: TimeoutException is a subclass of RequestError in httpx.
        The action's except clauses have RequestError before TimeoutException,
        so TimeoutException gets caught by the RequestError handler.
        """
        list_channels_action.http_request = AsyncMock(
            side_effect=httpx.TimeoutException("Request timed out")
        )
        result = await list_channels_action.execute()

        assert result["status"] == "error"
        # TimeoutException is caught by RequestError handler (comes first in exception chain)
        assert result["error_type"] == "RequestError"

    @pytest.mark.asyncio
    async def test_list_channels_network_error(self, list_channels_action):
        """Test handling of network/connection errors."""
        list_channels_action.http_request = AsyncMock(
            side_effect=httpx.RequestError("Connection failed")
        )
        result = await list_channels_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "RequestError"

    @pytest.mark.asyncio
    async def test_list_channels_missing_limit(self, list_channels_action):
        """Test that limit parameter is optional and defaults to 100."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "channels": [],
            "response_metadata": {"next_cursor": ""},
        }
        mock_response.raise_for_status = MagicMock()

        list_channels_action.http_request = AsyncMock(return_value=mock_response)
        # Execute without limit - should succeed with default limit=100
        result = await list_channels_action.execute()

        assert result["status"] == "success"
