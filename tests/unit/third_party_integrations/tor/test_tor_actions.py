"""Unit tests for Tor integration actions.

All tests use mocked httpx to avoid real HTTP requests.
Tests should run in <0.1s per test.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.tor.actions import (
    HealthCheckAction,
    LookupIpAction,
    _parse_bulk_exit_list,
    _parse_exit_addresses,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def default_settings():
    return {"timeout": 30}


@pytest.fixture
def health_check_action(default_settings):
    return HealthCheckAction(
        integration_id="tor",
        action_id="health_check",
        settings=default_settings,
        credentials={},
    )


@pytest.fixture
def lookup_ip_action(default_settings):
    return LookupIpAction(
        integration_id="tor",
        action_id="lookup_ip",
        settings=default_settings,
        credentials={},
    )


# ============================================================================
# Helper function tests
# ============================================================================


def test_parse_exit_addresses_basic():
    """Test parsing ExitAddress lines from the exit-addresses file."""
    text = (
        "# Tor exit node list\n"
        "ExitAddress 195.154.251.25 2026-04-26 12:00:00\n"
        "ExitAddress 84.105.18.164 2026-04-26 13:00:00\n"
        "SomeOtherLine ignored\n"
    )
    result = _parse_exit_addresses(text)
    assert result == ["195.154.251.25", "84.105.18.164"]


def test_parse_exit_addresses_empty():
    """Test parsing empty or comment-only file."""
    text = "# No exit nodes here\n"
    result = _parse_exit_addresses(text)
    assert result == []


def test_parse_exit_addresses_malformed_line():
    """Test that malformed ExitAddress lines without an IP are skipped."""
    text = "ExitAddress\nExitAddress 1.2.3.4 2026-04-26\n"
    result = _parse_exit_addresses(text)
    assert result == ["1.2.3.4"]


def test_parse_bulk_exit_list_basic():
    """Test parsing the TorBulkExitList response (one IP per line)."""
    text = "# This is a list of all Tor exit nodes\n1.2.3.4\n5.6.7.8\n\n9.10.11.12\n"
    result = _parse_bulk_exit_list(text)
    assert result == ["1.2.3.4", "5.6.7.8", "9.10.11.12"]


def test_parse_bulk_exit_list_empty():
    """Test parsing empty response."""
    result = _parse_bulk_exit_list("")
    assert result == []


# ============================================================================
# HealthCheckAction tests
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check returns healthy=True and exit node count."""
    exit_list_text = (
        "ExitAddress 1.2.3.4 2026-04-26 12:00:00\n"
        "ExitAddress 5.6.7.8 2026-04-26 13:00:00\n"
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = exit_list_text
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["healthy"] is True
    assert result["data"]["healthy"] is True
    assert result["data"]["exit_node_count"] == 2


@pytest.mark.asyncio
async def test_health_check_http_error(health_check_action):
    """Test health check returns error on HTTP 5xx response."""
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_response.text = "Service Unavailable"

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "503", request=MagicMock(), response=mock_response
        )
    )

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"
    assert result["healthy"] is False
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_timeout(health_check_action):
    """Test health check returns error on request timeout."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"
    assert result["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_connection_error(health_check_action):
    """Test health check returns error on connection failure."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConnectionError"
    assert result["healthy"] is False


# ============================================================================
# LookupIpAction tests
# ============================================================================


@pytest.mark.asyncio
async def test_lookup_ip_missing_param(lookup_ip_action):
    """Test that missing 'ip' parameter returns a ValidationError."""
    result = await lookup_ip_action.execute()
    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "ip" in result["error"]


@pytest.mark.asyncio
async def test_lookup_ip_empty_string(lookup_ip_action):
    """Test that empty IP string returns a ValidationError."""
    result = await lookup_ip_action.execute(ip="   ")
    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_lookup_ip_is_exit_node(lookup_ip_action):
    """Test that a known exit node IP is correctly identified."""
    exit_list_text = "ExitAddress 1.2.3.4 2026-04-26 12:00:00\n"

    # Primary list response
    primary_response = MagicMock()
    primary_response.status_code = 200
    primary_response.text = exit_list_text
    primary_response.raise_for_status = MagicMock()

    # Bulk list response (no additional IPs)
    bulk_response = MagicMock()
    bulk_response.status_code = 200
    bulk_response.text = "# no extra nodes\n"

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=[primary_response, bulk_response])

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await lookup_ip_action.execute(ip="1.2.3.4")

    assert result["status"] == "success"
    assert result["num_exit_nodes"] == 1
    assert len(result["results"]) == 1
    assert result["results"][0]["ip"] == "1.2.3.4"
    assert result["results"][0]["is_exit_node"] is True


@pytest.mark.asyncio
async def test_lookup_ip_not_exit_node(lookup_ip_action):
    """Test that a non-exit-node IP is correctly identified as not an exit node."""
    exit_list_text = "ExitAddress 1.2.3.4 2026-04-26 12:00:00\n"

    primary_response = MagicMock()
    primary_response.status_code = 200
    primary_response.text = exit_list_text
    primary_response.raise_for_status = MagicMock()

    bulk_response = MagicMock()
    bulk_response.status_code = 200
    bulk_response.text = "# empty\n"

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=[primary_response, bulk_response])

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await lookup_ip_action.execute(ip="9.9.9.9")

    assert result["status"] == "success"
    assert result["num_exit_nodes"] == 0
    assert result["results"][0]["ip"] == "9.9.9.9"
    assert result["results"][0]["is_exit_node"] is False


@pytest.mark.asyncio
async def test_lookup_ip_multiple_ips(lookup_ip_action):
    """Test comma-separated list of IPs — some exit nodes, some not."""
    exit_list_text = (
        "ExitAddress 1.2.3.4 2026-04-26 12:00:00\n"
        "ExitAddress 5.6.7.8 2026-04-26 13:00:00\n"
    )

    primary_response = MagicMock()
    primary_response.status_code = 200
    primary_response.text = exit_list_text
    primary_response.raise_for_status = MagicMock()

    # Two bulk responses (one per IP in the list)
    bulk_response = MagicMock()
    bulk_response.status_code = 200
    bulk_response.text = "# empty\n"

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(
        side_effect=[primary_response, bulk_response, bulk_response, bulk_response]
    )

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await lookup_ip_action.execute(ip="1.2.3.4,9.9.9.9,5.6.7.8")

    assert result["status"] == "success"
    assert result["num_exit_nodes"] == 2
    assert len(result["results"]) == 3

    # Build a dict for easy assertion
    by_ip = {r["ip"]: r["is_exit_node"] for r in result["results"]}
    assert by_ip["1.2.3.4"] is True
    assert by_ip["9.9.9.9"] is False
    assert by_ip["5.6.7.8"] is True


@pytest.mark.asyncio
async def test_lookup_ip_bulk_exit_list_adds_ip(lookup_ip_action):
    """Test that the TorBulkExitList endpoint can add IPs not in the primary list."""
    # Primary list does NOT include 9.9.9.9
    primary_response = MagicMock()
    primary_response.status_code = 200
    primary_response.text = "ExitAddress 1.2.3.4 2026-04-26 12:00:00\n"
    primary_response.raise_for_status = MagicMock()

    # Bulk list DOES include 9.9.9.9 (exit within past 16 hours)
    bulk_response = MagicMock()
    bulk_response.status_code = 200
    bulk_response.text = "9.9.9.9\n"

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=[primary_response, bulk_response])

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await lookup_ip_action.execute(ip="9.9.9.9")

    assert result["status"] == "success"
    assert result["results"][0]["is_exit_node"] is True
    assert result["num_exit_nodes"] == 1


@pytest.mark.asyncio
async def test_lookup_ip_http_error(lookup_ip_action):
    """Test that an HTTP error from the Tor Project is returned as an error."""
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_response.text = "Service Unavailable"

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "503", request=MagicMock(), response=mock_response
        )
    )

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await lookup_ip_action.execute(ip="1.2.3.4")

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


@pytest.mark.asyncio
async def test_lookup_ip_timeout_error(lookup_ip_action):
    """Test that a timeout returns an appropriate error."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await lookup_ip_action.execute(ip="1.2.3.4")

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"


@pytest.mark.asyncio
async def test_lookup_ip_connection_error(lookup_ip_action):
    """Test that a connection error is returned gracefully."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await lookup_ip_action.execute(ip="1.2.3.4")

    assert result["status"] == "error"
    assert result["error_type"] == "ConnectionError"


@pytest.mark.asyncio
async def test_lookup_ip_uses_settings_timeout(default_settings):
    """Test that the action uses the timeout from settings."""
    action = LookupIpAction(
        integration_id="tor",
        action_id="lookup_ip",
        settings={"timeout": 10},
        credentials={},
    )

    primary_response = MagicMock()
    primary_response.status_code = 200
    primary_response.text = ""
    primary_response.raise_for_status = MagicMock()

    bulk_response = MagicMock()
    bulk_response.status_code = 200
    bulk_response.text = ""

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=[primary_response, bulk_response])

    with patch("httpx.AsyncClient") as mock_async_client_cls:
        mock_async_client_cls.return_value = mock_client
        await action.execute(ip="1.2.3.4")
        # Verify AsyncClient was instantiated with timeout=10
        mock_async_client_cls.assert_called_once_with(timeout=10)


@pytest.mark.asyncio
async def test_lookup_ip_bulk_request_failure_continues(lookup_ip_action):
    """Test that a failed bulk exit list request is silently ignored."""
    primary_response = MagicMock()
    primary_response.status_code = 200
    primary_response.text = "ExitAddress 1.2.3.4 2026-04-26 12:00:00\n"
    primary_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    # Primary succeeds, bulk fails with a RequestError
    mock_client.get = AsyncMock(
        side_effect=[
            primary_response,
            httpx.ConnectError("bulk endpoint down"),
        ]
    )

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await lookup_ip_action.execute(ip="1.2.3.4")

    # Should still succeed using only the primary list
    assert result["status"] == "success"
    assert result["results"][0]["is_exit_node"] is True
