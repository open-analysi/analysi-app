"""Unit tests for the unshorten.me integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.unshortenme.actions import (
    HealthCheckAction,
    UnshortenUrlAction,
    _strip_scheme,
)

# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


def _make_action(cls, settings=None, credentials=None):
    """Instantiate an action with sensible defaults."""
    return cls(
        integration_id="unshortenme",
        action_id=cls.__name__.lower(),
        settings=settings or {},
        credentials=credentials or {},
    )


def _mock_response(json_data, status_code=200):
    """Build a mock httpx.Response whose .json() returns json_data."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = json_data
    mock_resp.status_code = status_code
    return mock_resp


# ---------------------------------------------------------------------------
# _strip_scheme helper
# ---------------------------------------------------------------------------


class TestStripScheme:
    """Tests for the _strip_scheme URL normalisation helper."""

    def test_strips_https(self):
        assert _strip_scheme("https://bit.ly/abc") == "bit.ly/abc"

    def test_strips_http(self):
        assert _strip_scheme("http://bit.ly/abc") == "bit.ly/abc"

    def test_no_scheme_unchanged(self):
        assert _strip_scheme("bit.ly/abc") == "bit.ly/abc"

    def test_empty_string(self):
        assert _strip_scheme("") == ""

    def test_preserves_path(self):
        assert _strip_scheme("https://t.co/XYZ1234") == "t.co/XYZ1234"


# ---------------------------------------------------------------------------
# HealthCheckAction
# ---------------------------------------------------------------------------


class TestHealthCheckAction:
    """Tests for HealthCheckAction."""

    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Healthy when API returns expected resolved URL."""
        mock_resp = _mock_response({"resolved_url": "https://unshorten.me/"})

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await action.execute()

        assert result["status"] == "success"
        assert result["healthy"] is True
        assert result["resolved_url"] == "https://unshorten.me/"

    @pytest.mark.asyncio
    async def test_unexpected_resolved_url(self, action):
        """Returns error when resolved URL does not match expected value."""
        mock_resp = _mock_response({"resolved_url": "https://something-else.com/"})

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await action.execute()

        assert result["status"] == "error"
        assert result["healthy"] is False
        assert result["error_type"] == "UnexpectedResponse"

    @pytest.mark.asyncio
    async def test_api_error_field(self, action):
        """Returns error when API response contains an 'error' key."""
        mock_resp = _mock_response({"error": "too many requests"})

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await action.execute()

        assert result["status"] == "error"
        assert result["healthy"] is False
        assert result["error_type"] == "APIError"
        assert "too many requests" in result["error"]

    @pytest.mark.asyncio
    async def test_http_status_error(self, action):
        """Returns error on HTTP 5xx from the API."""
        mock_response = MagicMock()
        mock_response.status_code = 503

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "Service Unavailable", request=MagicMock(), response=mock_response
            ),
        ):
            result = await action.execute()

        assert result["status"] == "error"
        assert result["healthy"] is False
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_request_error(self, action):
        """Returns error on network-level failure."""
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("connection refused"),
        ):
            result = await action.execute()

        assert result["status"] == "error"
        assert result["healthy"] is False
        assert result["error_type"] == "RequestError"

    @pytest.mark.asyncio
    async def test_uses_timeout_from_settings(self, action):
        """Passes the configured timeout value to http_request."""
        action.settings["timeout"] = 15
        mock_resp = _mock_response({"resolved_url": "https://unshorten.me/"})

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            await action.execute()

        _, call_kwargs = mock_req.call_args
        assert call_kwargs["timeout"] == 15


# ---------------------------------------------------------------------------
# UnshortenUrlAction
# ---------------------------------------------------------------------------


class TestUnshortenUrlAction:
    """Tests for UnshortenUrlAction."""

    @pytest.fixture
    def action(self):
        return _make_action(UnshortenUrlAction)

    @pytest.mark.asyncio
    async def test_success_with_https_url(self, action):
        """Successfully expands a shortened URL that starts with https://."""
        api_data = {
            "resolved_url": "https://www.example.com/some/path",
            "requested_url": "bit.ly/abc123",
            "success": True,
            "usage_count": "42",
            "remaining_calls": 9,
        }
        mock_resp = _mock_response(api_data)

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await action.execute(url="https://bit.ly/abc123")

        assert result["status"] == "success"
        assert result["resolved_url"] == "https://www.example.com/some/path"
        assert result["requested_url"] == "bit.ly/abc123"
        assert result["success"] is True
        assert result["usage_count"] == "42"
        assert result["remaining_calls"] == 9
        assert result["url"] == "https://bit.ly/abc123"

    @pytest.mark.asyncio
    async def test_success_with_http_url(self, action):
        """Successfully expands a shortened URL that starts with http://."""
        api_data = {
            "resolved_url": "https://www.example.com/",
            "requested_url": "tinyurl.com/xyz",
            "success": True,
            "usage_count": "1",
            "remaining_calls": 8,
        }
        mock_resp = _mock_response(api_data)

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await action.execute(url="http://tinyurl.com/xyz")

        assert result["status"] == "success"
        assert result["resolved_url"] == "https://www.example.com/"

    @pytest.mark.asyncio
    async def test_success_url_without_scheme(self, action):
        """Accepts URLs supplied without a scheme prefix."""
        api_data = {
            "resolved_url": "https://www.example.com/",
            "requested_url": "t.co/abc",
            "success": True,
        }
        mock_resp = _mock_response(api_data)

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            result = await action.execute(url="t.co/abc")

        assert result["status"] == "success"
        # Verify no double-stripping occurred
        call_url = mock_req.call_args[0][0]
        assert "unshorten.me/json/t.co/abc" in call_url

    @pytest.mark.asyncio
    async def test_missing_url_parameter(self, action):
        """Returns ValidationError when url parameter is absent."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "url" in result["error"]

    @pytest.mark.asyncio
    async def test_empty_url_parameter(self, action):
        """Returns ValidationError when url is an empty string."""
        result = await action.execute(url="")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_whitespace_only_url(self, action):
        """Returns ValidationError when url contains only whitespace."""
        result = await action.execute(url="   ")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_api_returns_error_field(self, action):
        """Returns error when the API response contains an 'error' key."""
        mock_resp = _mock_response({"error": "Invalid URL"})

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await action.execute(url="https://bit.ly/bad")

        assert result["status"] == "error"
        assert result["error_type"] == "APIError"
        assert "Invalid URL" in result["error"]
        assert result["url"] == "https://bit.ly/bad"

    @pytest.mark.asyncio
    async def test_http_status_error(self, action):
        """Returns error on HTTP error status from the API."""
        mock_response = MagicMock()
        mock_response.status_code = 429

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "Too Many Requests", request=MagicMock(), response=mock_response
            ),
        ):
            result = await action.execute(url="https://bit.ly/abc")

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"
        assert result["url"] == "https://bit.ly/abc"

    @pytest.mark.asyncio
    async def test_request_error(self, action):
        """Returns error on network-level failure."""
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("network unreachable"),
        ):
            result = await action.execute(url="https://bit.ly/abc")

        assert result["status"] == "error"
        assert result["error_type"] == "RequestError"
        assert result["url"] == "https://bit.ly/abc"

    @pytest.mark.asyncio
    async def test_strips_https_before_api_call(self, action):
        """Verifies https:// is stripped when constructing the API request URL."""
        api_data = {
            "resolved_url": "https://example.com/",
            "requested_url": "bit.ly/abc",
            "success": True,
        }
        mock_resp = _mock_response(api_data)

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            await action.execute(url="https://bit.ly/abc")

        call_url = mock_req.call_args[0][0]
        # The API URL should contain the path without https://
        assert call_url == "https://unshorten.me/json/bit.ly/abc"

    @pytest.mark.asyncio
    async def test_strips_http_before_api_call(self, action):
        """Verifies http:// is stripped when constructing the API request URL."""
        api_data = {
            "resolved_url": "https://example.com/",
            "requested_url": "bit.ly/abc",
            "success": True,
        }
        mock_resp = _mock_response(api_data)

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            await action.execute(url="http://bit.ly/abc")

        call_url = mock_req.call_args[0][0]
        assert call_url == "https://unshorten.me/json/bit.ly/abc"

    @pytest.mark.asyncio
    async def test_whitespace_trimmed_from_url(self, action):
        """Whitespace around the URL is stripped before processing."""
        api_data = {
            "resolved_url": "https://example.com/",
            "requested_url": "bit.ly/abc",
            "success": True,
        }
        mock_resp = _mock_response(api_data)

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            result = await action.execute(url="  https://bit.ly/abc  ")

        assert result["status"] == "success"
        call_url = mock_req.call_args[0][0]
        assert call_url == "https://unshorten.me/json/bit.ly/abc"
