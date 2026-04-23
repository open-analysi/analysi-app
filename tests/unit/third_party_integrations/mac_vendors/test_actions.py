"""Unit tests for MAC Vendors integration actions.

All tests mock self.http_request on the action instance to avoid real HTTP calls.
Tests should run in <0.1s per test.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.mac_vendors.actions import (
    HealthCheckAction,
    LookupMacAction,
)
from analysi.integrations.framework.integrations.mac_vendors.constants import (
    HEALTH_CHECK_MAC,
    MAC_VENDORS_BASE_URL,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def health_check_action():
    """Create HealthCheckAction instance with default settings."""
    return HealthCheckAction(
        integration_id="mac-vendors",
        action_id="health_check",
        settings={},
        credentials={},
    )


@pytest.fixture
def lookup_mac_action():
    """Create LookupMacAction instance with default settings."""
    return LookupMacAction(
        integration_id="mac-vendors",
        action_id="lookup_mac",
        settings={},
        credentials={},
    )


def _make_text_response(text: str, status_code: int = 200) -> MagicMock:
    """Build a mock httpx Response that returns plain text."""
    mock_resp = MagicMock()
    mock_resp.text = text
    mock_resp.status_code = status_code
    return mock_resp


def _make_http_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Build an httpx.HTTPStatusError for the given status code."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    return httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=MagicMock(),
        response=mock_resp,
    )


# ============================================================================
# HealthCheckAction Tests
# ============================================================================


class TestHealthCheckAction:
    """Tests for the MAC Vendors health check action."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, health_check_action):
        """Test successful health check returns healthy=True."""
        mock_response = _make_text_response("VMware, Inc.")

        with patch.object(
            health_check_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await health_check_action.execute()

        assert result["status"] == "success"
        assert result["healthy"] is True
        assert "message" in result
        assert result["data"]["vendor"] == "VMware, Inc."

    @pytest.mark.asyncio
    async def test_health_check_calls_correct_url(self, health_check_action):
        """Test health check queries the HEALTH_CHECK_MAC address."""
        mock_response = _make_text_response("VMware, Inc.")

        with patch.object(
            health_check_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_request:
            await health_check_action.execute()

        called_url = mock_request.call_args[0][0]
        assert HEALTH_CHECK_MAC in called_url
        assert MAC_VENDORS_BASE_URL in called_url

    @pytest.mark.asyncio
    async def test_health_check_uses_timeout_from_settings(self):
        """Test health check honours the timeout setting."""
        action = HealthCheckAction(
            integration_id="mac-vendors",
            action_id="health_check",
            settings={"timeout": 10},
            credentials={},
        )
        mock_response = _make_text_response("VMware, Inc.")

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_request:
            await action.execute()

        assert mock_request.call_args.kwargs.get("timeout") == 10

    @pytest.mark.asyncio
    async def test_health_check_http_error(self, health_check_action):
        """Test health check returns error on HTTP failure."""
        with patch.object(
            health_check_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_http_status_error(503),
        ):
            result = await health_check_action.execute()

        assert result["status"] == "error"
        assert result["healthy"] is False
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self, health_check_action):
        """Test health check returns error on connection failure."""
        with patch.object(
            health_check_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            result = await health_check_action.execute()

        assert result["status"] == "error"
        assert result["healthy"] is False
        assert result["error_type"] == "ConnectError"


# ============================================================================
# LookupMacAction Tests
# ============================================================================


class TestLookupMacAction:
    """Tests for the MAC Vendors lookup_mac action."""

    @pytest.mark.asyncio
    async def test_lookup_mac_success(self, lookup_mac_action):
        """Test successful vendor lookup returns vendor name."""
        mock_response = _make_text_response("Apple, Inc.")

        with patch.object(
            lookup_mac_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await lookup_mac_action.execute(mac="d0:a6:37:aa:bb:cc")

        assert result["status"] == "success"
        assert result["vendor_found"] is True
        assert result["vendor"] == "Apple, Inc."
        assert result["mac"] == "d0:a6:37:aa:bb:cc"
        assert result.get("not_found") is None  # Should not be set

    @pytest.mark.asyncio
    async def test_lookup_mac_vendor_not_found_text(self, lookup_mac_action):
        """Test that 'vendor not found' text response returns not_found=True (success)."""
        mock_response = _make_text_response("vendor not found")

        with patch.object(
            lookup_mac_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await lookup_mac_action.execute(mac="aa:bb:cc:dd:ee:ff")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["vendor_found"] is False
        assert result["vendor"] is None
        assert result["mac"] == "aa:bb:cc:dd:ee:ff"

    @pytest.mark.asyncio
    async def test_lookup_mac_vendor_not_found_404(self, lookup_mac_action):
        """Test that a 404 HTTP response returns not_found=True (success)."""
        with patch.object(
            lookup_mac_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_http_status_error(404),
        ):
            result = await lookup_mac_action.execute(mac="aa:bb:cc:dd:ee:ff")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["vendor_found"] is False
        assert result["vendor"] is None

    @pytest.mark.asyncio
    async def test_lookup_mac_missing_parameter(self, lookup_mac_action):
        """Test that missing 'mac' parameter returns a validation error."""
        result = await lookup_mac_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "mac" in result["error"]

    @pytest.mark.asyncio
    async def test_lookup_mac_rate_limit(self, lookup_mac_action):
        """Test that a 429 response returns a RateLimitError."""
        with patch.object(
            lookup_mac_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_http_status_error(429),
        ):
            result = await lookup_mac_action.execute(mac="d0:a6:37:aa:bb:cc")

        assert result["status"] == "error"
        assert result["error_type"] == "RateLimitError"
        assert "rate limit" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_lookup_mac_http_error(self, lookup_mac_action):
        """Test that a generic HTTP error (5xx) returns status=error."""
        with patch.object(
            lookup_mac_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_http_status_error(503),
        ):
            result = await lookup_mac_action.execute(mac="d0:a6:37:aa:bb:cc")

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"
        assert result["mac"] == "d0:a6:37:aa:bb:cc"

    @pytest.mark.asyncio
    async def test_lookup_mac_connection_error(self, lookup_mac_action):
        """Test that a connection error returns status=error."""
        with patch.object(
            lookup_mac_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            result = await lookup_mac_action.execute(mac="d0:a6:37:aa:bb:cc")

        assert result["status"] == "error"
        assert result["mac"] == "d0:a6:37:aa:bb:cc"

    @pytest.mark.asyncio
    async def test_lookup_mac_strips_whitespace_from_input(self, lookup_mac_action):
        """Test that leading/trailing whitespace in the mac param is stripped."""
        mock_response = _make_text_response("Apple, Inc.")

        with patch.object(
            lookup_mac_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_request:
            await lookup_mac_action.execute(mac="  d0:a6:37:aa:bb:cc  ")

        called_url = mock_request.call_args[0][0]
        # URL should contain the stripped MAC, not the padded version
        assert "  " not in called_url
        assert "d0:a6:37:aa:bb:cc" in called_url

    @pytest.mark.asyncio
    async def test_lookup_mac_calls_correct_url(self, lookup_mac_action):
        """Test that the action builds the correct API URL."""
        mock_response = _make_text_response("Apple, Inc.")
        test_mac = "d0:a6:37:aa:bb:cc"

        with patch.object(
            lookup_mac_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_request:
            await lookup_mac_action.execute(mac=test_mac)

        called_url = mock_request.call_args[0][0]
        assert called_url == f"{MAC_VENDORS_BASE_URL}/{test_mac}"

    @pytest.mark.asyncio
    async def test_lookup_mac_uses_timeout_from_settings(self):
        """Test that the action uses the timeout from settings."""
        action = LookupMacAction(
            integration_id="mac-vendors",
            action_id="lookup_mac",
            settings={"timeout": 15},
            credentials={},
        )
        mock_response = _make_text_response("Apple, Inc.")

        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_request:
            await action.execute(mac="d0:a6:37:aa:bb:cc")

        assert mock_request.call_args.kwargs.get("timeout") == 15

    @pytest.mark.asyncio
    async def test_lookup_mac_vendor_not_found_case_insensitive(
        self, lookup_mac_action
    ):
        """Test that vendor-not-found detection is case-insensitive."""
        mock_response = _make_text_response("Vendor Not Found")

        with patch.object(
            lookup_mac_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await lookup_mac_action.execute(mac="aa:bb:cc:dd:ee:ff")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["vendor_found"] is False
