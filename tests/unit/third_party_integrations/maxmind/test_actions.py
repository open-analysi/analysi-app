"""Unit tests for MaxMind integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.maxmind.actions import (
    GeolocateIpAction,
    HealthCheckAction,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def health_check_action():
    """Create a HealthCheckAction instance for testing."""
    return HealthCheckAction(
        integration_id="maxmind",
        action_id="health_check",
        settings={"account_id": "test_account", "timeout": 30, "test_ip": "8.8.8.8"},
        credentials={
            "license_key": "test_license_key",
        },
    )


@pytest.fixture
def geolocate_ip_action():
    """Create a GeolocateIpAction instance for testing."""
    return GeolocateIpAction(
        integration_id="maxmind",
        action_id="geolocate_ip",
        settings={"account_id": "test_account", "timeout": 30},
        credentials={
            "license_key": "test_license_key",
        },
    )


@pytest.fixture
def mock_maxmind_city_response():
    """Mock MaxMind GeoIP2 City API response."""
    return {
        "city": {"names": {"en": "Mountain View"}},
        "subdivisions": [{"names": {"en": "California"}, "iso_code": "CA"}],
        "country": {"names": {"en": "United States"}, "iso_code": "US"},
        "continent": {"names": {"en": "North America"}},
        "location": {
            "latitude": 37.386,
            "longitude": -122.0838,
            "time_zone": "America/Los_Angeles",
        },
        "postal": {"code": "94035"},
        "traits": {
            "autonomous_system_number": 15169,
            "autonomous_system_organization": "Google LLC",
            "domain": "google.com",
        },
    }


# ============================================================================
# HEALTH CHECK ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action, mock_maxmind_city_response):
    """Test successful health check."""
    mock_response = MagicMock()
    mock_response.json.return_value = mock_maxmind_city_response

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["healthy"] is True
    assert "MaxMind API is accessible" in result["message"]


@pytest.mark.asyncio
async def test_health_check_missing_credentials():
    """Test health check with missing credentials."""
    action = HealthCheckAction(
        integration_id="maxmind",
        action_id="health_check",
        settings={},
        credentials={},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False
    assert "account_id" in result["error"]
    assert "license_key" in result["error"]
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_health_check_invalid_credentials(health_check_action):
    """Test health check with invalid credentials."""
    mock_resp = MagicMock(status_code=401)
    error = httpx.HTTPStatusError(
        "Unauthorized", request=MagicMock(), response=mock_resp
    )

    with patch.object(
        health_check_action, "http_request", new_callable=AsyncMock, side_effect=error
    ):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False
    assert result["status"] == "error"  # HTTPStatusError propagated


@pytest.mark.asyncio
async def test_health_check_timeout(health_check_action):
    """Test health check with timeout."""
    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Request timed out"),
    ):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False
    assert (
        "timed out" in result["error"].lower() or "timeout" in result["error"].lower()
    )


# ============================================================================
# GEOLOCATE IP ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_geolocate_ip_success(geolocate_ip_action, mock_maxmind_city_response):
    """Test successful IP geolocation."""
    mock_response = MagicMock()
    mock_response.json.return_value = mock_maxmind_city_response

    with patch.object(
        geolocate_ip_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await geolocate_ip_action.execute(ip="8.8.8.8")

    assert result["status"] == "success"
    assert result["ip_address"] == "8.8.8.8"
    assert result["city_name"] == "Mountain View"
    assert result["state_name"] == "California"
    assert result["state_iso_code"] == "CA"
    assert result["country_name"] == "United States"
    assert result["country_iso_code"] == "US"
    assert result["continent_name"] == "North America"
    assert result["latitude"] == 37.386
    assert result["longitude"] == -122.0838
    assert result["time_zone"] == "America/Los_Angeles"
    assert result["postal_code"] == "94035"
    assert result["as_number"] == 15169
    assert result["as_org"] == "Google LLC"
    assert result["domain"] == "google.com"
    assert "full_data" in result


@pytest.mark.asyncio
async def test_geolocate_ip_ipv6(geolocate_ip_action, mock_maxmind_city_response):
    """Test IPv6 address geolocation."""
    mock_response = MagicMock()
    mock_response.json.return_value = mock_maxmind_city_response

    with patch.object(
        geolocate_ip_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await geolocate_ip_action.execute(ip="2001:4860:4860::8888")

    assert result["status"] == "success"
    assert result["ip_address"] == "2001:4860:4860::8888"


@pytest.mark.asyncio
async def test_geolocate_ip_missing_ip(geolocate_ip_action):
    """Test geolocation with missing IP parameter."""
    result = await geolocate_ip_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Invalid IP address" in result["error"]


@pytest.mark.asyncio
async def test_geolocate_ip_invalid_ip(geolocate_ip_action):
    """Test geolocation with invalid IP address."""
    result = await geolocate_ip_action.execute(ip="not-an-ip")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Invalid IP address" in result["error"]


@pytest.mark.asyncio
async def test_geolocate_ip_empty_ip(geolocate_ip_action):
    """Test geolocation with empty IP address."""
    result = await geolocate_ip_action.execute(ip="")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Invalid IP address" in result["error"]


@pytest.mark.asyncio
async def test_geolocate_ip_missing_credentials():
    """Test geolocation with missing credentials."""
    action = GeolocateIpAction(
        integration_id="maxmind",
        action_id="geolocate_ip",
        settings={},
        credentials={},
    )

    result = await action.execute(ip="8.8.8.8")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "license_key" in result["error"]


@pytest.mark.asyncio
async def test_geolocate_ip_not_found(geolocate_ip_action):
    """Test not-found returns success with not_found flag (not error)."""
    error = httpx.HTTPStatusError(
        "Not found", request=MagicMock(), response=MagicMock(status_code=404)
    )

    with patch.object(
        geolocate_ip_action, "http_request", new_callable=AsyncMock, side_effect=error
    ):
        result = await geolocate_ip_action.execute(ip="192.0.2.1")

    assert result["status"] == "success"
    assert result["not_found"] is True


@pytest.mark.asyncio
async def test_geolocate_ip_invalid_credentials(geolocate_ip_action):
    """Test geolocation with invalid credentials."""
    error = httpx.HTTPStatusError(
        "Unauthorized", request=MagicMock(), response=MagicMock(status_code=401)
    )

    with patch.object(
        geolocate_ip_action, "http_request", new_callable=AsyncMock, side_effect=error
    ):
        result = await geolocate_ip_action.execute(ip="8.8.8.8")

    assert result["status"] == "error"
    assert result["status"] == "error"  # HTTPStatusError propagated


@pytest.mark.asyncio
async def test_geolocate_ip_rate_limit(geolocate_ip_action):
    """Test geolocation with rate limit exceeded."""
    error = httpx.HTTPStatusError(
        "Rate limit", request=MagicMock(), response=MagicMock(status_code=429)
    )

    with patch.object(
        geolocate_ip_action, "http_request", new_callable=AsyncMock, side_effect=error
    ):
        result = await geolocate_ip_action.execute(ip="8.8.8.8")

    assert result["status"] == "error"
    assert result["status"] == "error"  # HTTPStatusError propagated


@pytest.mark.asyncio
async def test_geolocate_ip_minimal_response(geolocate_ip_action):
    """Test geolocation with minimal response (missing optional fields)."""
    minimal_response = {
        "country": {"names": {"en": "United States"}, "iso_code": "US"},
        "location": {},
        "traits": {},
    }

    mock_response = MagicMock()
    mock_response.json.return_value = minimal_response

    with patch.object(
        geolocate_ip_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await geolocate_ip_action.execute(ip="8.8.8.8")

    assert result["status"] == "success"
    assert result["country_name"] == "United States"
    assert result["country_iso_code"] == "US"
    # Optional fields should not be present if missing from API
    assert "city_name" not in result
    assert "latitude" not in result


@pytest.mark.asyncio
async def test_geolocate_ip_timeout(geolocate_ip_action):
    """Test geolocation with timeout."""
    with patch.object(
        geolocate_ip_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Request timed out"),
    ):
        result = await geolocate_ip_action.execute(ip="8.8.8.8")

    assert result["status"] == "error"
    assert "timed out" in result["error"]
