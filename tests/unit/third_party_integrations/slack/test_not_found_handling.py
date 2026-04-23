"""
Unit tests for 404/not-found handling in Slack lookup/get actions.

Tests that GetUserAction, GetResponseAction, and GetHistoryAction
return {"status": "success", "not_found": True} for both HTTP 404
responses and Slack API-level not-found errors (ok=false with
error codes like "user_not_found", "channel_not_found", etc.).
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.slack.actions import (
    GetHistoryAction,
    GetResponseAction,
    GetUserAction,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def get_user_action():
    """Create GetUserAction instance for testing."""
    return GetUserAction(
        integration_id="test-slack",
        action_id="get_user",
        credentials={"bot_token": "xoxb-test-token"},
        settings={"timeout": 30},
    )


@pytest.fixture
def get_response_action():
    """Create GetResponseAction instance for testing."""
    return GetResponseAction(
        integration_id="test-slack",
        action_id="get_response",
        credentials={"bot_token": "xoxb-test-token"},
        settings={"timeout": 30},
    )


@pytest.fixture
def get_history_action():
    """Create GetHistoryAction instance for testing."""
    return GetHistoryAction(
        integration_id="test-slack",
        action_id="get_history",
        credentials={"bot_token": "xoxb-test-token"},
        settings={"timeout": 30},
    )


# ---------------------------------------------------------------------------
# GetUserAction not-found tests
# ---------------------------------------------------------------------------


class TestGetUserNotFound:
    """Tests for GetUserAction not-found handling."""

    @pytest.mark.asyncio
    async def test_slack_api_user_not_found_by_id(self, get_user_action):
        """Slack returns ok=false with error='user_not_found' for invalid user ID."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": False, "error": "user_not_found"}
        mock_response.raise_for_status = MagicMock()

        get_user_action.http_request = AsyncMock(return_value=mock_response)
        result = await get_user_action.execute(user_id="U000NONEXISTENT")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["query_type"] == "user_id"
        assert result["user_id"] == "U000NONEXISTENT"
        assert result["error_code"] == "user_not_found"

    @pytest.mark.asyncio
    async def test_slack_api_users_not_found_by_email(self, get_user_action):
        """Slack returns ok=false with error='users_not_found' for unknown email."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": False, "error": "users_not_found"}
        mock_response.raise_for_status = MagicMock()

        get_user_action.http_request = AsyncMock(return_value=mock_response)
        result = await get_user_action.execute(email_address="nobody@example.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["query_type"] == "email_address"
        assert result["email"] == "nobody@example.com"
        assert result["error_code"] == "users_not_found"

    @pytest.mark.asyncio
    async def test_http_404_returns_not_found(self, get_user_action):
        """HTTP 404 status should return success with not_found=True."""
        get_user_action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "HTTP 404",
                request=MagicMock(),
                response=MagicMock(status_code=404),
            )
        )
        result = await get_user_action.execute(user_id="U000MISSING")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["query_type"] == "user_id"
        assert result["user_id"] == "U000MISSING"

    @pytest.mark.asyncio
    async def test_http_404_returns_not_found_email_lookup(self, get_user_action):
        """HTTP 404 on email lookup should return success with not_found=True."""
        get_user_action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "HTTP 404",
                request=MagicMock(),
                response=MagicMock(status_code=404),
            )
        )
        result = await get_user_action.execute(email_address="gone@example.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["query_type"] == "email_address"
        assert result["email"] == "gone@example.com"

    @pytest.mark.asyncio
    async def test_http_500_still_returns_error(self, get_user_action):
        """Non-404 HTTP errors should still return status=error."""
        get_user_action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "HTTP 500",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )
        )
        result = await get_user_action.execute(user_id="U000VALID")

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_slack_api_other_error_still_returns_error(self, get_user_action):
        """Non-not-found Slack API errors should still return status=error."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": False, "error": "token_revoked"}
        mock_response.raise_for_status = MagicMock()

        get_user_action.http_request = AsyncMock(return_value=mock_response)
        result = await get_user_action.execute(user_id="U000VALID")

        assert result["status"] == "error"
        assert result["error_type"] == "SlackAPIError"

    @pytest.mark.asyncio
    async def test_empty_user_in_response_returns_not_found(self, get_user_action):
        """When Slack returns ok=true but user field is missing/None, treat as not found."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "user": None}
        mock_response.raise_for_status = MagicMock()

        get_user_action.http_request = AsyncMock(return_value=mock_response)
        result = await get_user_action.execute(user_id="U000EMPTY")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_successful_user_lookup_has_no_not_found_key(self, get_user_action):
        """A successful lookup should not have a not_found key."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "user": {
                "id": "U123",
                "name": "testuser",
                "real_name": "Test User",
                "team_id": "T123",
                "tz": "UTC",
                "deleted": False,
                "is_bot": False,
                "profile": {
                    "email": "test@example.com",
                    "display_name": "tester",
                },
            },
        }
        mock_response.raise_for_status = MagicMock()

        get_user_action.http_request = AsyncMock(return_value=mock_response)
        result = await get_user_action.execute(user_id="U123")

        assert result["status"] == "success"
        assert "not_found" not in result
        assert result["user_id"] == "U123"


# ---------------------------------------------------------------------------
# GetResponseAction not-found tests
# ---------------------------------------------------------------------------


class TestGetResponseNotFound:
    """Tests for GetResponseAction not-found handling."""

    @pytest.mark.asyncio
    async def test_http_404_returns_not_found(self, get_response_action):
        """HTTP 404 should return success with not_found=True."""
        get_response_action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "HTTP 404",
                request=MagicMock(),
                response=MagicMock(status_code=404),
            )
        )
        result = await get_response_action.execute(question_id="q-missing-123")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["question_id"] == "q-missing-123"

    @pytest.mark.asyncio
    async def test_http_500_still_returns_error(self, get_response_action):
        """Non-404 HTTP errors should still return status=error."""
        get_response_action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "HTTP 500",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )
        )
        result = await get_response_action.execute(question_id="q-123")

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_successful_response_has_no_not_found_key(self, get_response_action):
        """A successful response fetch should not have a not_found key."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "response": "Yes",
                "response_received": True,
            }
        }
        mock_response.raise_for_status = MagicMock()

        get_response_action.http_request = AsyncMock(return_value=mock_response)
        result = await get_response_action.execute(question_id="q-valid-456")

        assert result["status"] == "success"
        assert "not_found" not in result
        assert result["response"] == "Yes"


# ---------------------------------------------------------------------------
# GetHistoryAction not-found tests
# ---------------------------------------------------------------------------


class TestGetHistoryNotFound:
    """Tests for GetHistoryAction not-found handling."""

    @pytest.mark.asyncio
    async def test_slack_api_channel_not_found_without_message_ts(
        self, get_history_action
    ):
        """Slack returns ok=false with error='channel_not_found' for channel history."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": False,
            "error": "channel_not_found",
        }
        mock_response.raise_for_status = MagicMock()

        get_history_action.http_request = AsyncMock(return_value=mock_response)
        result = await get_history_action.execute(channel_id="C000MISSING")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["channel_id"] == "C000MISSING"
        assert result["error_code"] == "channel_not_found"

    @pytest.mark.asyncio
    async def test_slack_api_channel_not_found_with_message_ts(
        self, get_history_action
    ):
        """Slack returns channel_not_found when fetching specific thread."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": False,
            "error": "channel_not_found",
        }
        mock_response.raise_for_status = MagicMock()

        get_history_action.http_request = AsyncMock(return_value=mock_response)
        result = await get_history_action.execute(
            channel_id="C000MISSING", message_ts="1234567890.123456"
        )

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["channel_id"] == "C000MISSING"
        assert result["message_ts"] == "1234567890.123456"
        assert result["error_code"] == "channel_not_found"

    @pytest.mark.asyncio
    async def test_slack_api_thread_not_found_with_message_ts(self, get_history_action):
        """Slack returns thread_not_found when fetching nonexistent thread."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": False,
            "error": "thread_not_found",
        }
        mock_response.raise_for_status = MagicMock()

        get_history_action.http_request = AsyncMock(return_value=mock_response)
        result = await get_history_action.execute(
            channel_id="C123VALID", message_ts="0000000000.000000"
        )

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["channel_id"] == "C123VALID"
        assert result["message_ts"] == "0000000000.000000"
        assert result["error_code"] == "thread_not_found"

    @pytest.mark.asyncio
    async def test_http_404_returns_not_found(self, get_history_action):
        """HTTP 404 should return success with not_found=True."""
        get_history_action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "HTTP 404",
                request=MagicMock(),
                response=MagicMock(status_code=404),
            )
        )
        result = await get_history_action.execute(
            channel_id="C000GONE", message_ts="1234567890.123456"
        )

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["channel_id"] == "C000GONE"
        assert result["message_ts"] == "1234567890.123456"

    @pytest.mark.asyncio
    async def test_http_500_still_returns_error(self, get_history_action):
        """Non-404 HTTP errors should still return status=error."""
        get_history_action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "HTTP 500",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )
        )
        result = await get_history_action.execute(channel_id="C123")

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_slack_api_other_error_still_returns_error(self, get_history_action):
        """Non-not-found Slack API errors should still return status=error."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": False,
            "error": "not_authed",
        }
        mock_response.raise_for_status = MagicMock()

        get_history_action.http_request = AsyncMock(return_value=mock_response)
        result = await get_history_action.execute(channel_id="C123")

        assert result["status"] == "error"
        assert result["error_type"] == "SlackAPIError"

    @pytest.mark.asyncio
    async def test_slack_api_thread_not_found_in_reply_loop(self, get_history_action):
        """When fetching replies for a thread fails with thread_not_found during
        channel history enumeration, return not_found."""
        # First call returns channel history with one message
        history_response = MagicMock()
        history_response.json.return_value = {
            "ok": True,
            "messages": [{"ts": "111.222", "text": "hello"}],
        }
        history_response.raise_for_status = MagicMock()

        # Second call (replies for that message) returns thread_not_found
        replies_response = MagicMock()
        replies_response.json.return_value = {
            "ok": False,
            "error": "thread_not_found",
        }
        replies_response.raise_for_status = MagicMock()

        get_history_action.http_request = AsyncMock(
            side_effect=[history_response, replies_response]
        )
        result = await get_history_action.execute(channel_id="C123VALID")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["error_code"] == "thread_not_found"

    @pytest.mark.asyncio
    async def test_successful_history_has_no_not_found_key(self, get_history_action):
        """A successful history fetch should not have a not_found key."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "messages": [
                {"ts": "111.222", "text": "hello", "user": "U123"},
            ],
        }
        mock_response.raise_for_status = MagicMock()

        # First call: conversations.history, second: conversations.replies
        replies_response = MagicMock()
        replies_response.json.return_value = {
            "ok": True,
            "messages": [
                {"ts": "111.222", "text": "hello", "user": "U123"},
            ],
        }
        replies_response.raise_for_status = MagicMock()

        get_history_action.http_request = AsyncMock(
            side_effect=[mock_response, replies_response]
        )
        result = await get_history_action.execute(channel_id="C123VALID")

        assert result["status"] == "success"
        assert "not_found" not in result
        assert result["num_messages"] == 1
