"""Unit tests for Shodan integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.shodan.actions import (
    DomainLookupAction,
    HealthCheckAction,
    IpLookupAction,
)
from analysi.integrations.framework.integrations.shodan.constants import (
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP,
    ERROR_TYPE_TIMEOUT,
    ERROR_TYPE_VALIDATION,
    MSG_INVALID_DOMAIN,
    MSG_INVALID_IP,
    MSG_INVALID_JSON,
    MSG_MISSING_API_KEY,
    MSG_SERVER_CONNECTION,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def health_check_action():
    """Create HealthCheckAction instance with mocked credentials."""
    return HealthCheckAction(
        integration_id="shodan",
        action_id="health_check",
        settings={"timeout": 30},
        credentials={"api_key": "test_api_key_123"},
    )


@pytest.fixture
def ip_lookup_action():
    """Create IpLookupAction instance with mocked credentials."""
    return IpLookupAction(
        integration_id="shodan",
        action_id="ip_lookup",
        settings={"timeout": 30},
        credentials={"api_key": "test_api_key_123"},
    )


@pytest.fixture
def domain_lookup_action():
    """Create DomainLookupAction instance with mocked credentials."""
    return DomainLookupAction(
        integration_id="shodan",
        action_id="domain_lookup",
        settings={"timeout": 30},
        credentials={"api_key": "test_api_key_123"},
    )


# ============================================================================
# HEALTH CHECK ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    mock_response = {
        "plan": "oss",
        "https": True,
        "unlocked": True,
    }

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = mock_response

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await health_check_action.execute()

    assert result["status"] == STATUS_SUCCESS
    assert result["data"]["healthy"] is True
    assert "api_info" in result["data"]


@pytest.mark.asyncio
async def test_health_check_missing_api_key():
    """Test health check with missing API key."""
    action = HealthCheckAction(
        integration_id="shodan",
        action_id="health_check",
        settings={"timeout": 30},
        credentials={},
    )

    result = await action.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_API_KEY
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_invalid_api_key(health_check_action):
    """Test health check with invalid API key."""
    import httpx

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = {"error": "Invalid API key"}
    mock_http_response.status_code = 401

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_http_response
        ),
    ):
        result = await health_check_action.execute()

    assert result["status"] == STATUS_ERROR
    assert "Invalid API key" in result["error"]
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_timeout(health_check_action):
    """Test health check with timeout."""
    import httpx

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Request timed out"),
    ):
        result = await health_check_action.execute()

    assert result["status"] == STATUS_ERROR
    assert "timed out" in result["error"].lower()
    assert result["error_type"] == ERROR_TYPE_TIMEOUT
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_connection_error(health_check_action):
    """Test health check with connection error."""
    import httpx

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.RequestError("Connection failed"),
    ):
        result = await health_check_action.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_SERVER_CONNECTION
    assert result["error_type"] == ERROR_TYPE_HTTP
    assert result["data"]["healthy"] is False


# ============================================================================
# IP LOOKUP ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_ip_lookup_success(ip_lookup_action):
    """Test successful IP lookup."""
    mock_response = {
        "ip_str": "8.8.8.8",
        "country_name": "United States",
        "ports": [53, 443],
        "hostnames": ["dns.google"],
        "data": [
            {
                "port": 53,
                "transport": "udp",
                "product": "Google DNS",
            }
        ],
    }

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = mock_response

    with patch.object(
        ip_lookup_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await ip_lookup_action.execute(ip="8.8.8.8")

    assert result["status"] == STATUS_SUCCESS
    assert result["ip_address"] == "8.8.8.8"
    assert result["summary"]["results"] == 1
    assert result["summary"]["country"] == "United States"
    assert "53, 443" in result["summary"]["open_ports"]
    assert len(result["services"]) == 1


@pytest.mark.asyncio
async def test_ip_lookup_ipv6(ip_lookup_action):
    """Test IP lookup with IPv6 address."""
    mock_response = {
        "ip_str": "2001:4860:4860::8888",
        "country_name": "United States",
        "ports": [53],
        "hostnames": [],
        "data": [],
    }

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = mock_response

    with patch.object(
        ip_lookup_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await ip_lookup_action.execute(ip="2001:4860:4860::8888")

    assert result["status"] == STATUS_SUCCESS
    assert result["ip_address"] == "2001:4860:4860::8888"


@pytest.mark.asyncio
async def test_ip_lookup_missing_ip(ip_lookup_action):
    """Test IP lookup with missing IP parameter."""
    result = await ip_lookup_action.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_INVALID_IP
    assert result["error_type"] == ERROR_TYPE_VALIDATION


@pytest.mark.asyncio
async def test_ip_lookup_invalid_ip(ip_lookup_action):
    """Test IP lookup with invalid IP format."""
    result = await ip_lookup_action.execute(ip="invalid_ip")

    assert result["status"] == STATUS_ERROR
    assert "Invalid IP address format" in result["error"]
    assert result["error_type"] == ERROR_TYPE_VALIDATION


@pytest.mark.asyncio
async def test_ip_lookup_missing_api_key():
    """Test IP lookup with missing API key."""
    action = IpLookupAction(
        integration_id="shodan",
        action_id="ip_lookup",
        settings={"timeout": 30},
        credentials={},
    )

    result = await action.execute(ip="8.8.8.8")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_API_KEY
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION


@pytest.mark.asyncio
async def test_ip_lookup_not_found(ip_lookup_action):
    """Test IP lookup with not found error returns success with not_found flag."""
    import httpx

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = {"error": "No information available"}
    mock_http_response.status_code = 404
    mock_http_response.text = "Not found"

    with patch.object(
        ip_lookup_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_http_response
        ),
    ):
        result = await ip_lookup_action.execute(ip="192.0.2.1")

    assert result["status"] == STATUS_SUCCESS
    assert result["not_found"] is True
    assert result["summary"]["results"] == 0


@pytest.mark.asyncio
async def test_ip_lookup_rate_limit(ip_lookup_action):
    """Test IP lookup with rate limit error."""
    import httpx

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = {"error": "Rate limit exceeded"}
    mock_http_response.status_code = 429
    mock_http_response.text = "Too many requests"

    with patch.object(
        ip_lookup_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_http_response
        ),
    ):
        result = await ip_lookup_action.execute(ip="8.8.8.8")

    assert result["status"] == STATUS_ERROR
    assert "Rate limit exceeded" in result["error"]
    assert result["error_type"] == ERROR_TYPE_HTTP


@pytest.mark.asyncio
async def test_ip_lookup_timeout(ip_lookup_action):
    """Test IP lookup with timeout."""
    import httpx

    with patch.object(
        ip_lookup_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Request timed out"),
    ):
        result = await ip_lookup_action.execute(ip="8.8.8.8")

    assert result["status"] == STATUS_ERROR
    assert "timed out" in result["error"].lower()
    assert result["error_type"] == ERROR_TYPE_TIMEOUT


@pytest.mark.asyncio
async def test_ip_lookup_invalid_json(ip_lookup_action):
    """Test IP lookup with invalid JSON response."""
    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.side_effect = Exception("Invalid JSON")

    with patch.object(
        ip_lookup_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await ip_lookup_action.execute(ip="8.8.8.8")

    assert result["status"] == STATUS_ERROR
    assert MSG_INVALID_JSON in result["error"]


# ============================================================================
# DOMAIN LOOKUP ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_domain_lookup_success(domain_lookup_action):
    """Test successful domain lookup."""
    mock_response = {
        "matches": [
            {
                "ip_str": "192.0.2.1",
                "port": 443,
                "hostnames": ["example.com"],
            }
        ],
        "total": 1,
    }

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = mock_response

    with patch.object(
        domain_lookup_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await domain_lookup_action.execute(domain="example.com")

    assert result["status"] == STATUS_SUCCESS
    assert result["domain"] == "example.com"
    assert result["summary"]["results"] == 1
    assert len(result["matches"]) == 1


@pytest.mark.asyncio
async def test_domain_lookup_fallback_search(domain_lookup_action):
    """Test domain lookup with fallback to general search."""
    # First response with no hostname matches
    mock_response_1 = {"matches": [], "total": 0}

    # Second response with general search results
    mock_response_2 = {
        "matches": [
            {
                "ip_str": "192.0.2.1",
                "port": 80,
            }
        ],
        "total": 1,
    }

    mock_http_response_1 = MagicMock(spec=httpx.Response)
    mock_http_response_1.json.return_value = mock_response_1

    mock_http_response_2 = MagicMock(spec=httpx.Response)
    mock_http_response_2.json.return_value = mock_response_2

    with patch.object(
        domain_lookup_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=[mock_http_response_1, mock_http_response_2],
    ):
        result = await domain_lookup_action.execute(domain="example.com")

    assert result["status"] == STATUS_SUCCESS
    assert result["domain"] == "example.com"
    assert result["summary"]["results"] == 1
    assert len(result["matches"]) == 1


@pytest.mark.asyncio
async def test_domain_lookup_missing_domain(domain_lookup_action):
    """Test domain lookup with missing domain parameter."""
    result = await domain_lookup_action.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_INVALID_DOMAIN
    assert result["error_type"] == ERROR_TYPE_VALIDATION


@pytest.mark.asyncio
async def test_domain_lookup_invalid_domain(domain_lookup_action):
    """Test domain lookup with invalid domain format."""
    result = await domain_lookup_action.execute(domain="not a domain!")

    assert result["status"] == STATUS_ERROR
    assert "Invalid domain format" in result["error"]
    assert result["error_type"] == ERROR_TYPE_VALIDATION


@pytest.mark.asyncio
async def test_domain_lookup_missing_api_key():
    """Test domain lookup with missing API key."""
    action = DomainLookupAction(
        integration_id="shodan",
        action_id="domain_lookup",
        settings={"timeout": 30},
        credentials={},
    )

    result = await action.execute(domain="example.com")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_API_KEY
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION


@pytest.mark.asyncio
async def test_domain_lookup_empty_results(domain_lookup_action):
    """Test domain lookup with empty results after both searches."""
    mock_response = {"matches": [], "total": 0}

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = mock_response

    with patch.object(
        domain_lookup_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await domain_lookup_action.execute(domain="nonexistent.example")

    assert result["status"] == STATUS_SUCCESS
    assert result["summary"]["results"] == 0
    assert len(result["matches"]) == 0


@pytest.mark.asyncio
async def test_domain_lookup_timeout(domain_lookup_action):
    """Test domain lookup with timeout."""
    import httpx

    with patch.object(
        domain_lookup_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Request timed out"),
    ):
        result = await domain_lookup_action.execute(domain="example.com")

    assert result["status"] == STATUS_ERROR
    assert "timed out" in result["error"].lower()
    assert result["error_type"] == ERROR_TYPE_TIMEOUT


@pytest.mark.asyncio
async def test_domain_lookup_http_error(domain_lookup_action):
    """Test domain lookup with HTTP error."""
    import httpx

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = {"error": "Service unavailable"}
    mock_http_response.status_code = 503
    mock_http_response.text = "Service Unavailable"

    with patch.object(
        domain_lookup_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Service Unavailable", request=MagicMock(), response=mock_http_response
        ),
    ):
        result = await domain_lookup_action.execute(domain="example.com")

    assert result["status"] == STATUS_ERROR
    assert result["error_type"] == ERROR_TYPE_HTTP
