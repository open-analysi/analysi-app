"""Unit tests for Rapid7 InsightVM integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.rapid7.actions import (
    GetAssetAction,
    GetScanAction,
    GetVulnerabilitiesAction,
    GetVulnerabilityAction,
    HealthCheckAction,
    ListScansAction,
    SearchAssetsAction,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def credentials():
    """Fixture for Rapid7 credentials."""
    return {
        "api_key": "test-rapid7-key",
    }


@pytest.fixture
def settings():
    """Fixture for Rapid7 settings."""
    return {
        "base_url": "https://us.api.insight.rapid7.com/vm",
        "timeout": 30,
    }


@pytest.fixture
def health_check_action(credentials, settings):
    """Fixture for HealthCheckAction."""
    return HealthCheckAction(
        integration_id="rapid7",
        action_id="health_check",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def get_asset_action(credentials, settings):
    """Fixture for GetAssetAction."""
    return GetAssetAction(
        integration_id="rapid7",
        action_id="get_asset",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def search_assets_action(credentials, settings):
    """Fixture for SearchAssetsAction."""
    return SearchAssetsAction(
        integration_id="rapid7",
        action_id="search_assets",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def get_vulnerabilities_action(credentials, settings):
    """Fixture for GetVulnerabilitiesAction."""
    return GetVulnerabilitiesAction(
        integration_id="rapid7",
        action_id="get_vulnerabilities",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def get_vulnerability_action(credentials, settings):
    """Fixture for GetVulnerabilityAction."""
    return GetVulnerabilityAction(
        integration_id="rapid7",
        action_id="get_vulnerability",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def list_scans_action(credentials, settings):
    """Fixture for ListScansAction."""
    return ListScansAction(
        integration_id="rapid7",
        action_id="list_scans",
        settings=settings,
        credentials=credentials,
    )


@pytest.fixture
def get_scan_action(credentials, settings):
    """Fixture for GetScanAction."""
    return GetScanAction(
        integration_id="rapid7",
        action_id="get_scan",
        settings=settings,
        credentials=credentials,
    )


def _mock_response(data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock httpx.Response."""
    mock = MagicMock(spec=httpx.Response)
    mock.json.return_value = data
    mock.status_code = status_code
    mock.text = str(data)
    return mock


def _mock_http_error(status_code: int, text: str = "Error") -> httpx.HTTPStatusError:
    """Create a mock HTTPStatusError."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.text = text
    return httpx.HTTPStatusError(text, request=MagicMock(), response=mock_response)


# ============================================================================
# HEALTH CHECK ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    mock_resp = _mock_response({"version": {"semantic": "6.6.145"}})
    health_check_action.http_request = AsyncMock(return_value=mock_resp)

    result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["healthy"] is True
    assert result["data"]["healthy"] is True
    assert result["data"]["version"] == "6.6.145"
    assert "Rapid7" in result["message"]
    assert "integration_id" in result
    assert "timestamp" in result
    health_check_action.http_request.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_missing_api_key(settings):
    """Test health check with missing API key."""
    action = HealthCheckAction(
        integration_id="rapid7",
        action_id="health_check",
        settings=settings,
        credentials={},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "api_key" in result["error"].lower()
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_http_error(health_check_action):
    """Test health check with HTTP error (401 unauthorized)."""
    health_check_action.http_request = AsyncMock(
        side_effect=_mock_http_error(401, "Unauthorized")
    )

    result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_connection_error(health_check_action):
    """Test health check with connection error."""
    health_check_action.http_request = AsyncMock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["data"]["healthy"] is False


# ============================================================================
# GET ASSET ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_asset_success(get_asset_action):
    """Test successful asset retrieval."""
    asset_data = {
        "id": 42,
        "ip": "10.1.10.10",
        "hostName": "server01",
        "riskScore": 119945.99,
        "vulnerabilities": {
            "critical": 36,
            "severe": 306,
            "moderate": 62,
            "total": 404,
        },
    }
    mock_resp = _mock_response(asset_data)
    get_asset_action.http_request = AsyncMock(return_value=mock_resp)

    result = await get_asset_action.execute(asset_id=42)

    assert result["status"] == "success"
    assert result["data"]["asset_id"] == 42
    assert result["data"]["ip"] == "10.1.10.10"
    assert result["data"]["hostName"] == "server01"
    get_asset_action.http_request.assert_called_once()


@pytest.mark.asyncio
async def test_get_asset_string_id(get_asset_action):
    """Test asset retrieval with string ID (should coerce to int)."""
    mock_resp = _mock_response({"id": 42, "ip": "10.1.10.10"})
    get_asset_action.http_request = AsyncMock(return_value=mock_resp)

    result = await get_asset_action.execute(asset_id="42")

    assert result["status"] == "success"
    assert result["data"]["asset_id"] == 42


@pytest.mark.asyncio
async def test_get_asset_missing_id(get_asset_action):
    """Test asset retrieval with missing ID."""
    result = await get_asset_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "asset_id" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_asset_invalid_id(get_asset_action):
    """Test asset retrieval with non-integer ID."""
    result = await get_asset_action.execute(asset_id="abc")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "positive integer" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_asset_zero_id(get_asset_action):
    """Test asset retrieval with zero ID."""
    result = await get_asset_action.execute(asset_id=0)

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_get_asset_negative_id(get_asset_action):
    """Test asset retrieval with negative ID."""
    result = await get_asset_action.execute(asset_id=-1)

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_get_asset_not_found(get_asset_action):
    """Test asset retrieval with 404 (not found returns success with not_found)."""
    get_asset_action.http_request = AsyncMock(
        side_effect=_mock_http_error(404, "Not Found")
    )

    result = await get_asset_action.execute(asset_id=99999)

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["asset_id"] == 99999


@pytest.mark.asyncio
async def test_get_asset_missing_credentials(settings):
    """Test asset retrieval with missing credentials."""
    action = GetAssetAction(
        integration_id="rapid7",
        action_id="get_asset",
        settings=settings,
        credentials={},
    )

    result = await action.execute(asset_id=42)

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_get_asset_server_error(get_asset_action):
    """Test asset retrieval with server error (500)."""
    get_asset_action.http_request = AsyncMock(
        side_effect=_mock_http_error(500, "Internal Server Error")
    )

    result = await get_asset_action.execute(asset_id=42)

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# SEARCH ASSETS ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_search_assets_by_ip(search_assets_action):
    """Test asset search by IP address."""
    api_response = {
        "resources": [
            {"id": 1, "ip": "10.1.10.10", "hostName": "server01"},
        ],
        "page": {"totalResources": 1},
    }
    mock_resp = _mock_response(api_response)
    search_assets_action.http_request = AsyncMock(return_value=mock_resp)

    result = await search_assets_action.execute(ip="10.1.10.10")

    assert result["status"] == "success"
    assert result["data"]["num_assets"] == 1
    assert result["data"]["assets"][0]["ip"] == "10.1.10.10"

    # Verify correct filter was sent
    call_kwargs = search_assets_action.http_request.call_args
    json_body = call_kwargs.kwargs.get("json_data") or call_kwargs.kwargs.get("json")
    assert json_body["filters"][0]["field"] == "ip-address"
    assert json_body["filters"][0]["value"] == "10.1.10.10"


@pytest.mark.asyncio
async def test_search_assets_by_hostname(search_assets_action):
    """Test asset search by hostname."""
    api_response = {
        "resources": [
            {"id": 1, "ip": "10.1.10.10", "hostName": "server01"},
            {"id": 2, "ip": "10.1.10.11", "hostName": "server02"},
        ],
        "page": {"totalResources": 2},
    }
    mock_resp = _mock_response(api_response)
    search_assets_action.http_request = AsyncMock(return_value=mock_resp)

    result = await search_assets_action.execute(hostname="server")

    assert result["status"] == "success"
    assert result["data"]["num_assets"] == 2

    call_kwargs = search_assets_action.http_request.call_args
    json_body = call_kwargs.kwargs.get("json_data") or call_kwargs.kwargs.get("json")
    assert json_body["filters"][0]["field"] == "host-name"
    assert json_body["filters"][0]["operator"] == "contains"


@pytest.mark.asyncio
async def test_search_assets_by_filters_json(search_assets_action):
    """Test asset search with custom JSON filters ."""
    api_response = {
        "resources": [{"id": 1, "riskScore": 100000}],
        "page": {"totalResources": 1},
    }
    mock_resp = _mock_response(api_response)
    search_assets_action.http_request = AsyncMock(return_value=mock_resp)

    filters = '[{"field": "risk-score", "operator": "is-less-than", "value": 200000}]'
    result = await search_assets_action.execute(filters=filters, match="any")

    assert result["status"] == "success"
    assert result["data"]["num_assets"] == 1


@pytest.mark.asyncio
async def test_search_assets_invalid_filters_json(search_assets_action):
    """Test asset search with invalid JSON filters."""
    result = await search_assets_action.execute(filters="not valid json")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "json" in result["error"].lower()


@pytest.mark.asyncio
async def test_search_assets_filters_not_array(search_assets_action):
    """Test asset search with non-array JSON filters."""
    result = await search_assets_action.execute(filters='{"field": "ip-address"}')

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "array" in result["error"].lower()


@pytest.mark.asyncio
async def test_search_assets_no_query(search_assets_action):
    """Test asset search with no query parameters."""
    result = await search_assets_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "ip" in result["error"].lower() or "hostname" in result["error"].lower()


@pytest.mark.asyncio
async def test_search_assets_invalid_match(search_assets_action):
    """Test asset search with invalid match operator."""
    result = await search_assets_action.execute(ip="10.1.10.10", match="invalid")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "match" in result["error"].lower()


@pytest.mark.asyncio
async def test_search_assets_missing_credentials(settings):
    """Test asset search with missing credentials."""
    action = SearchAssetsAction(
        integration_id="rapid7",
        action_id="search_assets",
        settings=settings,
        credentials={},
    )

    result = await action.execute(ip="10.1.10.10")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_search_assets_empty_results(search_assets_action):
    """Test asset search with no matching results."""
    api_response = {
        "resources": [],
        "page": {"totalResources": 0},
    }
    mock_resp = _mock_response(api_response)
    search_assets_action.http_request = AsyncMock(return_value=mock_resp)

    result = await search_assets_action.execute(ip="10.99.99.99")

    assert result["status"] == "success"
    assert result["data"]["num_assets"] == 0
    assert result["data"]["assets"] == []


@pytest.mark.asyncio
async def test_search_assets_combined_ip_and_hostname(search_assets_action):
    """Test asset search with both IP and hostname filters combined."""
    api_response = {
        "resources": [{"id": 1}],
        "page": {"totalResources": 1},
    }
    mock_resp = _mock_response(api_response)
    search_assets_action.http_request = AsyncMock(return_value=mock_resp)

    result = await search_assets_action.execute(ip="10.1.10.10", hostname="server01")

    assert result["status"] == "success"

    # Verify both filters were sent
    call_kwargs = search_assets_action.http_request.call_args
    json_body = call_kwargs.kwargs.get("json_data") or call_kwargs.kwargs.get("json")
    assert len(json_body["filters"]) == 2


@pytest.mark.asyncio
async def test_search_assets_list_filters(search_assets_action):
    """Test asset search with filters as a Python list (not JSON string)."""
    api_response = {
        "resources": [{"id": 1}],
        "page": {"totalResources": 1},
    }
    mock_resp = _mock_response(api_response)
    search_assets_action.http_request = AsyncMock(return_value=mock_resp)

    filters_list = [
        {"field": "risk-score", "operator": "is-less-than", "value": 200000}
    ]
    result = await search_assets_action.execute(filters=filters_list)

    assert result["status"] == "success"


# ============================================================================
# GET VULNERABILITIES ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_vulnerabilities_success(get_vulnerabilities_action):
    """Test successful vulnerability retrieval for an asset."""
    api_response = {
        "resources": [
            {
                "id": "apache-httpd-cve-2021-44228",
                "instances": 2,
                "status": "vulnerable",
                "since": "2022-03-10T11:25:22.979Z",
            },
            {
                "id": "ssh-weak-ciphers",
                "instances": 1,
                "status": "vulnerable",
                "since": "2022-03-10T11:25:22.979Z",
            },
        ],
        "page": {"totalResources": 2},
    }
    mock_resp = _mock_response(api_response)
    get_vulnerabilities_action.http_request = AsyncMock(return_value=mock_resp)

    result = await get_vulnerabilities_action.execute(asset_id=42)

    assert result["status"] == "success"
    assert result["data"]["asset_id"] == 42
    assert result["data"]["num_vulnerabilities"] == 2
    assert len(result["data"]["vulnerabilities"]) == 2
    assert result["data"]["vulnerabilities"][0]["id"] == "apache-httpd-cve-2021-44228"


@pytest.mark.asyncio
async def test_get_vulnerabilities_missing_asset_id(get_vulnerabilities_action):
    """Test vulnerability retrieval with missing asset ID."""
    result = await get_vulnerabilities_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "asset_id" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_vulnerabilities_invalid_asset_id(get_vulnerabilities_action):
    """Test vulnerability retrieval with invalid asset ID."""
    result = await get_vulnerabilities_action.execute(asset_id="abc")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_get_vulnerabilities_missing_credentials(settings):
    """Test vulnerability retrieval with missing credentials."""
    action = GetVulnerabilitiesAction(
        integration_id="rapid7",
        action_id="get_vulnerabilities",
        settings=settings,
        credentials={},
    )

    result = await action.execute(asset_id=42)

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_get_vulnerabilities_asset_not_found(get_vulnerabilities_action):
    """Test vulnerability retrieval when asset is not found (404)."""
    get_vulnerabilities_action.http_request = AsyncMock(
        side_effect=_mock_http_error(404, "Not Found")
    )

    result = await get_vulnerabilities_action.execute(asset_id=99999)

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["num_vulnerabilities"] == 0
    assert result["data"]["vulnerabilities"] == []


@pytest.mark.asyncio
async def test_get_vulnerabilities_http_error(get_vulnerabilities_action):
    """Test vulnerability retrieval with server error."""
    get_vulnerabilities_action.http_request = AsyncMock(
        side_effect=_mock_http_error(500, "Internal Server Error")
    )

    result = await get_vulnerabilities_action.execute(asset_id=42)

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# GET VULNERABILITY ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_vulnerability_success(get_vulnerability_action):
    """Test successful single vulnerability retrieval."""
    vuln_data = {
        "id": "apache-httpd-cve-2021-44228",
        "title": "Apache Log4j Remote Code Execution",
        "severity": "Critical",
        "cvss": {"v3": {"score": 10.0}},
        "description": {"text": "A critical vulnerability..."},
        "published": "2026-04-26",
    }
    mock_resp = _mock_response(vuln_data)
    get_vulnerability_action.http_request = AsyncMock(return_value=mock_resp)

    result = await get_vulnerability_action.execute(
        vulnerability_id="apache-httpd-cve-2021-44228"
    )

    assert result["status"] == "success"
    assert result["data"]["vulnerability_id"] == "apache-httpd-cve-2021-44228"
    assert result["data"]["severity"] == "Critical"
    assert result["data"]["cvss"]["v3"]["score"] == 10.0


@pytest.mark.asyncio
async def test_get_vulnerability_missing_id(get_vulnerability_action):
    """Test vulnerability retrieval with missing vulnerability ID."""
    result = await get_vulnerability_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "vulnerability_id" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_vulnerability_not_found(get_vulnerability_action):
    """Test vulnerability retrieval with 404."""
    get_vulnerability_action.http_request = AsyncMock(
        side_effect=_mock_http_error(404, "Not Found")
    )

    result = await get_vulnerability_action.execute(vulnerability_id="nonexistent-vuln")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["vulnerability_id"] == "nonexistent-vuln"


@pytest.mark.asyncio
async def test_get_vulnerability_missing_credentials(settings):
    """Test vulnerability retrieval with missing credentials."""
    action = GetVulnerabilityAction(
        integration_id="rapid7",
        action_id="get_vulnerability",
        settings=settings,
        credentials={},
    )

    result = await action.execute(vulnerability_id="test-vuln")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_get_vulnerability_server_error(get_vulnerability_action):
    """Test vulnerability retrieval with server error."""
    get_vulnerability_action.http_request = AsyncMock(
        side_effect=_mock_http_error(503, "Service Unavailable")
    )

    result = await get_vulnerability_action.execute(vulnerability_id="test-vuln")

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# LIST SCANS ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_scans_success(list_scans_action):
    """Test successful scan listing."""
    api_response = {
        "resources": [
            {
                "id": 1,
                "status": "finished",
                "startTime": "2022-03-10T10:00:00Z",
                "endTime": "2022-03-10T11:25:57Z",
                "vulnerabilities": {"total": 4037},
            },
            {
                "id": 2,
                "status": "running",
                "startTime": "2022-03-11T10:00:00Z",
            },
        ],
        "page": {"totalResources": 2},
    }
    mock_resp = _mock_response(api_response)
    list_scans_action.http_request = AsyncMock(return_value=mock_resp)

    result = await list_scans_action.execute()

    assert result["status"] == "success"
    assert result["data"]["num_scans"] == 2
    assert len(result["data"]["scans"]) == 2
    assert result["data"]["scans"][0]["id"] == 1


@pytest.mark.asyncio
async def test_list_scans_with_limit(list_scans_action):
    """Test scan listing with limit."""
    api_response = {
        "resources": [
            {"id": 1, "status": "finished"},
            {"id": 2, "status": "finished"},
            {"id": 3, "status": "finished"},
        ],
        "page": {"totalResources": 100},
    }
    mock_resp = _mock_response(api_response)
    list_scans_action.http_request = AsyncMock(return_value=mock_resp)

    result = await list_scans_action.execute(limit=2)

    assert result["status"] == "success"
    assert result["data"]["num_scans"] == 2


@pytest.mark.asyncio
async def test_list_scans_invalid_limit(list_scans_action):
    """Test scan listing with invalid limit."""
    result = await list_scans_action.execute(limit="abc")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_list_scans_missing_credentials(settings):
    """Test scan listing with missing credentials."""
    action = ListScansAction(
        integration_id="rapid7",
        action_id="list_scans",
        settings=settings,
        credentials={},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_list_scans_empty(list_scans_action):
    """Test scan listing with no scans."""
    api_response = {
        "resources": [],
        "page": {"totalResources": 0},
    }
    mock_resp = _mock_response(api_response)
    list_scans_action.http_request = AsyncMock(return_value=mock_resp)

    result = await list_scans_action.execute()

    assert result["status"] == "success"
    assert result["data"]["num_scans"] == 0
    assert result["data"]["scans"] == []


@pytest.mark.asyncio
async def test_list_scans_http_error(list_scans_action):
    """Test scan listing with HTTP error."""
    list_scans_action.http_request = AsyncMock(
        side_effect=_mock_http_error(500, "Server Error")
    )

    result = await list_scans_action.execute()

    assert result["status"] == "error"


# ============================================================================
# GET SCAN ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_scan_success(get_scan_action):
    """Test successful scan detail retrieval."""
    scan_data = {
        "id": 123,
        "status": "finished",
        "startTime": "2022-03-10T10:00:00Z",
        "endTime": "2022-03-10T11:25:57Z",
        "vulnerabilities": {
            "critical": 360,
            "severe": 3060,
            "moderate": 617,
            "total": 4037,
        },
    }
    mock_resp = _mock_response(scan_data)
    get_scan_action.http_request = AsyncMock(return_value=mock_resp)

    result = await get_scan_action.execute(scan_id=123)

    assert result["status"] == "success"
    assert result["data"]["scan_id"] == 123
    assert result["data"]["status"] == "finished"
    assert result["data"]["vulnerabilities"]["total"] == 4037


@pytest.mark.asyncio
async def test_get_scan_missing_id(get_scan_action):
    """Test scan retrieval with missing scan ID."""
    result = await get_scan_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "scan_id" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_scan_invalid_id(get_scan_action):
    """Test scan retrieval with invalid scan ID."""
    result = await get_scan_action.execute(scan_id="abc")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_get_scan_not_found(get_scan_action):
    """Test scan retrieval with 404."""
    get_scan_action.http_request = AsyncMock(
        side_effect=_mock_http_error(404, "Not Found")
    )

    result = await get_scan_action.execute(scan_id=99999)

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["scan_id"] == 99999


@pytest.mark.asyncio
async def test_get_scan_missing_credentials(settings):
    """Test scan retrieval with missing credentials."""
    action = GetScanAction(
        integration_id="rapid7",
        action_id="get_scan",
        settings=settings,
        credentials={},
    )

    result = await action.execute(scan_id=123)

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_get_scan_server_error(get_scan_action):
    """Test scan retrieval with server error."""
    get_scan_action.http_request = AsyncMock(
        side_effect=_mock_http_error(500, "Internal Server Error")
    )

    result = await get_scan_action.execute(scan_id=123)

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# PAGINATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_pagination_multiple_pages(search_assets_action):
    """Test pagination across multiple pages of results."""
    # First page: full page (500 results)
    page1_resources = [{"id": i} for i in range(500)]
    page1_response = _mock_response(
        {
            "resources": page1_resources,
            "page": {"totalResources": 750},
        }
    )

    # Second page: partial page (250 results)
    page2_resources = [{"id": i} for i in range(500, 750)]
    page2_response = _mock_response(
        {
            "resources": page2_resources,
            "page": {"totalResources": 750},
        }
    )

    search_assets_action.http_request = AsyncMock(
        side_effect=[page1_response, page2_response]
    )

    result = await search_assets_action.execute(ip="10.1.10.10")

    assert result["status"] == "success"
    assert result["data"]["num_assets"] == 750
    assert search_assets_action.http_request.call_count == 2


@pytest.mark.asyncio
async def test_pagination_single_page(search_assets_action):
    """Test pagination when all results fit on one page."""
    api_response = {
        "resources": [{"id": 1}, {"id": 2}],
        "page": {"totalResources": 2},
    }
    mock_resp = _mock_response(api_response)
    search_assets_action.http_request = AsyncMock(return_value=mock_resp)

    result = await search_assets_action.execute(ip="10.1.10.10")

    assert result["status"] == "success"
    assert result["data"]["num_assets"] == 2
    assert search_assets_action.http_request.call_count == 1


# ============================================================================
# EDGE CASES AND CROSS-CUTTING TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_default_base_url_used(credentials):
    """Test that default base URL is used when not configured."""
    action = HealthCheckAction(
        integration_id="rapid7",
        action_id="health_check",
        settings={},  # No base_url in settings
        credentials=credentials,
    )
    mock_resp = _mock_response({"version": {"semantic": "6.6.145"}})
    action.http_request = AsyncMock(return_value=mock_resp)

    await action.execute()

    call_args = action.http_request.call_args
    url = call_args.args[0] if call_args.args else call_args.kwargs.get("url")
    assert "us.api.insight.rapid7.com" in url


@pytest.mark.asyncio
async def test_custom_base_url_used(credentials):
    """Test that custom base URL from settings is used."""
    action = HealthCheckAction(
        integration_id="rapid7",
        action_id="health_check",
        settings={"base_url": "https://eu.api.insight.rapid7.com/vm"},
        credentials=credentials,
    )
    mock_resp = _mock_response({"version": {"semantic": "6.6.145"}})
    action.http_request = AsyncMock(return_value=mock_resp)

    await action.execute()

    call_args = action.http_request.call_args
    url = call_args.args[0] if call_args.args else call_args.kwargs.get("url")
    assert "eu.api.insight.rapid7.com" in url


@pytest.mark.asyncio
async def test_api_key_in_headers(get_asset_action):
    """Test that API key is passed in X-Api-Key header."""
    mock_resp = _mock_response({"id": 1})
    get_asset_action.http_request = AsyncMock(return_value=mock_resp)

    await get_asset_action.execute(asset_id=1)

    call_kwargs = get_asset_action.http_request.call_args.kwargs
    headers = call_kwargs.get("headers", {})
    assert headers.get("X-Api-Key") == "test-rapid7-key"


@pytest.mark.asyncio
async def test_timeout_from_settings(credentials):
    """Test that timeout from settings is used in requests."""
    action = GetAssetAction(
        integration_id="rapid7",
        action_id="get_asset",
        settings={"timeout": 60},
        credentials=credentials,
    )
    mock_resp = _mock_response({"id": 1})
    action.http_request = AsyncMock(return_value=mock_resp)

    await action.execute(asset_id=1)

    call_kwargs = action.http_request.call_args.kwargs
    assert call_kwargs.get("timeout") == 60
