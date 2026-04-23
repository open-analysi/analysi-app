"""Unit tests for urlscan.io integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.integrations.framework.integrations.urlscan.actions import (
    DetonateUrlAction,
    GetReportAction,
    GetScreenshotAction,
    HealthCheckAction,
    HuntDomainAction,
    HuntIpAction,
)


@pytest.fixture
def credentials():
    """Fixture for test credentials."""
    return {"api_key": "test-api-key"}


@pytest.fixture
def settings():
    """Fixture for test settings."""
    return {"timeout": 120}


@pytest.fixture
def health_check_action(credentials, settings):
    """Fixture for HealthCheckAction instance."""
    return HealthCheckAction("urlscan-test", "health_check", settings, credentials)


@pytest.fixture
def get_report_action(credentials, settings):
    """Fixture for GetReportAction instance."""
    return GetReportAction("urlscan-test", "get_report", settings, credentials)


@pytest.fixture
def hunt_domain_action(credentials, settings):
    """Fixture for HuntDomainAction instance."""
    return HuntDomainAction("urlscan-test", "hunt_domain", settings, credentials)


@pytest.fixture
def hunt_ip_action(credentials, settings):
    """Fixture for HuntIpAction instance."""
    return HuntIpAction("urlscan-test", "hunt_ip", settings, credentials)


@pytest.fixture
def detonate_url_action(credentials, settings):
    """Fixture for DetonateUrlAction instance."""
    return DetonateUrlAction("urlscan-test", "detonate_url", settings, credentials)


@pytest.fixture
def get_screenshot_action(credentials, settings):
    """Fixture for GetScreenshotAction instance."""
    return GetScreenshotAction("urlscan-test", "get_screenshot", settings, credentials)


# ============================================================================
# HealthCheckAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    health_check_action.http_request = AsyncMock(return_value=mock_response)
    result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True


@pytest.mark.asyncio
async def test_health_check_http_error(health_check_action):
    """Test health check with HTTP error."""
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"

    health_check_action.http_request = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "401 Unauthorized", request=MagicMock(), response=mock_response
        )
    )
    result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_timeout(health_check_action):
    """Test health check timeout."""
    import httpx

    health_check_action.http_request = AsyncMock(
        side_effect=httpx.TimeoutException("Timeout")
    )
    result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"
    assert result["data"]["healthy"] is False


# ============================================================================
# GetReportAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_report_success(get_report_action):
    """Test successful report retrieval."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "task": {"uuid": "test-uuid", "url": "https://example.com"},
        "stats": {"malicious": 0},
    }

    get_report_action.http_request = AsyncMock(return_value=mock_response)
    result = await get_report_action.execute(id="test-uuid")

    assert result["status"] == "success"
    assert result["report_id"] == "test-uuid"
    assert "data" in result


@pytest.mark.asyncio
async def test_get_report_missing_id(get_report_action):
    """Test get report with missing ID."""
    result = await get_report_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Report ID" in result["error"]


@pytest.mark.asyncio
async def test_get_report_still_processing(get_report_action):
    """Test get report when scan is still processing."""
    mock_response = MagicMock()
    mock_response.status_code = 404

    get_report_action.http_request = AsyncMock(return_value=mock_response)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await get_report_action.execute(id="test-uuid")

    assert result["status"] == "success"
    assert "processing" in result["data"]
    assert result["data"]["processing"] is True


@pytest.mark.asyncio
async def test_get_report_http_error(get_report_action):
    """Test get report with HTTP error."""
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    get_report_action.http_request = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "500 Error", request=MagicMock(), response=mock_response
        )
    )
    result = await get_report_action.execute(id="test-uuid")

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# HuntDomainAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_hunt_domain_success(hunt_domain_action):
    """Test successful domain hunt."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "results": [
            {"task": {"uuid": "uuid1", "domain": "example.com"}},
            {"task": {"uuid": "uuid2", "domain": "example.com"}},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    hunt_domain_action.http_request = AsyncMock(return_value=mock_response)
    result = await hunt_domain_action.execute(domain="example.com")

    assert result["status"] == "success"
    assert result["domain"] == "example.com"
    assert result["results_count"] == 2


@pytest.mark.asyncio
async def test_hunt_domain_no_results(hunt_domain_action):
    """Test domain hunt with no results."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"results": []}
    mock_response.raise_for_status = MagicMock()

    hunt_domain_action.http_request = AsyncMock(return_value=mock_response)
    result = await hunt_domain_action.execute(domain="example.com")

    assert result["status"] == "success"
    assert result["results_count"] == 0
    assert "No data found" in result["message"]


@pytest.mark.asyncio
async def test_hunt_domain_missing_domain(hunt_domain_action):
    """Test hunt domain with missing domain parameter."""
    result = await hunt_domain_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Domain" in result["error"]


@pytest.mark.asyncio
async def test_hunt_domain_missing_api_key(hunt_domain_action):
    """Test hunt domain with missing API key."""
    hunt_domain_action.credentials = {}
    result = await hunt_domain_action.execute(domain="example.com")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "API key" in result["error"]


@pytest.mark.asyncio
async def test_hunt_domain_http_error(hunt_domain_action):
    """Test hunt domain with HTTP error."""
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.text = "Rate limit exceeded"

    hunt_domain_action.http_request = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "429 Error", request=MagicMock(), response=mock_response
        )
    )
    result = await hunt_domain_action.execute(domain="example.com")

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# HuntIpAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_hunt_ip_success(hunt_ip_action):
    """Test successful IP hunt."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "results": [{"task": {"uuid": "uuid1", "url": "https://1.2.3.4"}}]
    }
    mock_response.raise_for_status = MagicMock()

    hunt_ip_action.http_request = AsyncMock(return_value=mock_response)
    result = await hunt_ip_action.execute(ip="1.2.3.4")

    assert result["status"] == "success"
    assert result["ip"] == "1.2.3.4"
    assert result["results_count"] == 1


@pytest.mark.asyncio
async def test_hunt_ip_invalid_ip(hunt_ip_action):
    """Test hunt IP with invalid IP address."""
    result = await hunt_ip_action.execute(ip="invalid-ip")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Invalid IP" in result["error"]


@pytest.mark.asyncio
async def test_hunt_ip_missing_ip(hunt_ip_action):
    """Test hunt IP with missing IP parameter."""
    result = await hunt_ip_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "IP address" in result["error"]


@pytest.mark.asyncio
async def test_hunt_ip_missing_api_key(hunt_ip_action):
    """Test hunt IP with missing API key."""
    hunt_ip_action.credentials = {}
    result = await hunt_ip_action.execute(ip="1.2.3.4")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "API key" in result["error"]


@pytest.mark.asyncio
async def test_hunt_ip_no_results(hunt_ip_action):
    """Test IP hunt with no results."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"results": []}
    mock_response.raise_for_status = MagicMock()

    hunt_ip_action.http_request = AsyncMock(return_value=mock_response)
    result = await hunt_ip_action.execute(ip="1.2.3.4")

    assert result["status"] == "success"
    assert result["results_count"] == 0
    assert "No data found" in result["message"]


# ============================================================================
# DetonateUrlAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_detonate_url_success_no_wait(detonate_url_action):
    """Test successful URL detonation without waiting for results."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "uuid": "test-uuid",
        "api": "https://urlscan.io/api/v1/result/test-uuid/",
    }
    mock_response.raise_for_status = MagicMock()

    detonate_url_action.http_request = AsyncMock(return_value=mock_response)
    result = await detonate_url_action.execute(
        url="https://example.com", get_result=False
    )

    assert result["status"] == "success"
    assert result["url"] == "https://example.com"
    assert result["uuid"] == "test-uuid"


@pytest.mark.asyncio
async def test_detonate_url_missing_url(detonate_url_action):
    """Test detonate URL with missing URL parameter."""
    result = await detonate_url_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "URL" in result["error"]


@pytest.mark.asyncio
async def test_detonate_url_missing_api_key(detonate_url_action):
    """Test detonate URL with missing API key."""
    detonate_url_action.credentials = {}
    result = await detonate_url_action.execute(url="https://example.com")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "API key" in result["error"]


@pytest.mark.asyncio
async def test_detonate_url_with_tags(detonate_url_action):
    """Test URL detonation with tags."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"uuid": "test-uuid"}
    mock_response.raise_for_status = MagicMock()

    detonate_url_action.http_request = AsyncMock(return_value=mock_response)
    result = await detonate_url_action.execute(
        url="https://example.com", tags="phishing,malware", get_result=False
    )

    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_detonate_url_too_many_tags(detonate_url_action):
    """Test URL detonation with too many tags."""
    tags = ",".join([f"tag{i}" for i in range(15)])
    result = await detonate_url_action.execute(
        url="https://example.com", tags=tags, get_result=False
    )

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "tags" in result["error"]


@pytest.mark.asyncio
async def test_detonate_url_bad_request(detonate_url_action):
    """Test URL detonation with bad request response."""
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {
        "message": "Invalid URL",
        "description": "URL is not accessible",
    }

    detonate_url_action.http_request = AsyncMock(return_value=mock_response)
    result = await detonate_url_action.execute(
        url="https://example.com", get_result=False
    )

    assert result["status"] == "success"
    assert "Bad request" in result["message"]


@pytest.mark.asyncio
async def test_detonate_url_http_error(detonate_url_action):
    """Test URL detonation with HTTP error."""
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    detonate_url_action.http_request = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "500 Error", request=MagicMock(), response=mock_response
        )
    )
    result = await detonate_url_action.execute(
        url="https://example.com", get_result=False
    )

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# GetScreenshotAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_screenshot_success(get_screenshot_action):
    """Test successful screenshot retrieval."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"fake-png-data"
    mock_response.headers = {"content-type": "image/png"}

    get_screenshot_action.http_request = AsyncMock(return_value=mock_response)
    result = await get_screenshot_action.execute(report_id="test-uuid")

    assert result["status"] == "success"
    assert result["report_id"] == "test-uuid"
    assert "screenshot" in result
    assert result["content_type"] == "image/png"
    assert result["size"] > 0


@pytest.mark.asyncio
async def test_get_screenshot_missing_report_id(get_screenshot_action):
    """Test get screenshot with missing report ID."""
    result = await get_screenshot_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "Report ID" in result["error"]


@pytest.mark.asyncio
async def test_get_screenshot_not_available(get_screenshot_action):
    """Test get screenshot when screenshot is not available."""
    mock_response = MagicMock()
    mock_response.status_code = 404

    get_screenshot_action.http_request = AsyncMock(return_value=mock_response)
    result = await get_screenshot_action.execute(report_id="test-uuid")

    assert result["status"] == "error"
    assert "not available" in result["error"]


@pytest.mark.asyncio
async def test_get_screenshot_timeout(get_screenshot_action):
    """Test get screenshot with timeout."""
    import httpx

    get_screenshot_action.http_request = AsyncMock(
        side_effect=httpx.TimeoutException("Timeout")
    )
    result = await get_screenshot_action.execute(report_id="test-uuid")

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"
