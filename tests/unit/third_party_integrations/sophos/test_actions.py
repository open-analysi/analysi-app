"""
Unit tests for Sophos Central EDR integration actions.

Tests cover all 10 actions: health_check, get_endpoint, list_endpoints,
isolate_endpoint, unisolate_endpoint, scan_endpoint, list_alerts,
get_alert, block_item, unblock_item.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.sophos.actions import (
    BlockItemAction,
    GetAlertAction,
    GetEndpointAction,
    HealthCheckAction,
    IsolateEndpointAction,
    ListAlertsAction,
    ListEndpointsAction,
    ScanEndpointAction,
    UnblockItemAction,
    UnisolateEndpointAction,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_credentials():
    """Mock Sophos Central credentials."""
    return {
        "client_id": "test-client-id-abc123",
        "client_secret": "test-client-secret-xyz789",
    }


@pytest.fixture
def mock_settings():
    """Mock integration settings."""
    return {
        "base_url": "https://api.central.sophos.com",
        "timeout": 30,
    }


def _build_action(action_cls, mock_credentials, mock_settings, action_id="test"):
    """Build an action instance with mocked auth helper responses."""
    return action_cls(
        integration_id="sophos",
        action_id=action_id,
        settings=mock_settings,
        credentials=mock_credentials,
    )


def _mock_token_response():
    """Create a mock OAuth token response."""
    resp = MagicMock()
    resp.json.return_value = {"access_token": "test-jwt-token"}
    resp.raise_for_status = MagicMock()
    return resp


def _mock_whoami_response(id_type="tenant"):
    """Create a mock whoami response."""
    resp = MagicMock()
    resp.json.return_value = {
        "id": "test-tenant-id-999",
        "idType": id_type,
        "apiHosts": {
            "dataRegion": "https://api-us03.central.sophos.com",
            "global": "https://api.central.sophos.com",
        },
    }
    resp.raise_for_status = MagicMock()
    return resp


def _mock_api_response(json_data, status_code=200):
    """Create a mock API response."""
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


# Standard side_effect for the 3-step auth + API call pattern
def _auth_then_api(api_response_data, api_status=200):
    """Return side_effect list: [token, whoami, api_response]."""
    return [
        _mock_token_response(),
        _mock_whoami_response(),
        _mock_api_response(api_response_data, api_status),
    ]


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


@pytest.fixture
def health_check_action(mock_credentials, mock_settings):
    """Create HealthCheckAction instance."""
    return _build_action(
        HealthCheckAction, mock_credentials, mock_settings, "health_check"
    )


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check with valid credentials."""
    health_check_action.http_request = AsyncMock(
        side_effect=_auth_then_api({"items": [{"id": "ep1"}], "pages": {"items": 42}})
    )

    result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True
    assert result["data"]["tenant_id"] == "test-tenant-id-999"
    assert result["data"]["endpoint_count"] == 42
    assert "integration_id" in result
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_health_check_missing_credentials():
    """Test health check with missing credentials."""
    action = HealthCheckAction(
        integration_id="sophos",
        action_id="health_check",
        settings={"timeout": 30},
        credentials={},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "client_id" in result["error"]
    assert result["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_missing_client_secret():
    """Test health check with missing client_secret."""
    action = HealthCheckAction(
        integration_id="sophos",
        action_id="health_check",
        settings={"timeout": 30},
        credentials={"client_id": "abc"},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_health_check_auth_failure(health_check_action):
    """Test health check with authentication failure."""
    health_check_action.http_request = AsyncMock(
        side_effect=Exception("OAuth token acquisition failed")
    )

    result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_http_error(health_check_action):
    """Test health check with HTTP status error."""
    mock_request = MagicMock(spec=httpx.Request)
    mock_request.url = "https://id.sophos.com/api/v2/oauth2/token"
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 401

    health_check_action.http_request = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "401 Unauthorized",
            request=mock_request,
            response=mock_response,
        )
    )

    result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["healthy"] is False


# ============================================================================
# GET ENDPOINT TESTS
# ============================================================================


@pytest.fixture
def get_endpoint_action(mock_credentials, mock_settings):
    """Create GetEndpointAction instance."""
    return _build_action(
        GetEndpointAction, mock_credentials, mock_settings, "get_endpoint"
    )


@pytest.mark.asyncio
async def test_get_endpoint_success(get_endpoint_action):
    """Test successful endpoint lookup."""
    endpoint_data = {
        "id": "ep-123",
        "hostname": "WORKSTATION-01",
        "health": {"overall": "good"},
        "os": {"name": "Windows 10"},
    }
    get_endpoint_action.http_request = AsyncMock(
        side_effect=_auth_then_api(endpoint_data)
    )

    result = await get_endpoint_action.execute(endpoint_id="ep-123")

    assert result["status"] == "success"
    assert result["data"]["id"] == "ep-123"
    assert result["data"]["hostname"] == "WORKSTATION-01"


@pytest.mark.asyncio
async def test_get_endpoint_missing_param(get_endpoint_action):
    """Test get endpoint without endpoint_id."""
    result = await get_endpoint_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "endpoint_id" in result["error"]


@pytest.mark.asyncio
async def test_get_endpoint_not_found(get_endpoint_action):
    """Test get endpoint with 404 response."""
    mock_request = MagicMock(spec=httpx.Request)
    mock_request.url = (
        "https://api-us03.central.sophos.com/endpoint/v1/endpoints/bad-id"
    )
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404

    get_endpoint_action.http_request = AsyncMock(
        side_effect=[
            _mock_token_response(),
            _mock_whoami_response(),
            httpx.HTTPStatusError(
                "404 Not Found", request=mock_request, response=mock_response
            ),
        ]
    )

    result = await get_endpoint_action.execute(endpoint_id="bad-id")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["endpoint_id"] == "bad-id"


@pytest.mark.asyncio
async def test_get_endpoint_missing_credentials():
    """Test get endpoint with empty credentials."""
    action = GetEndpointAction(
        integration_id="sophos",
        action_id="get_endpoint",
        settings={"timeout": 30},
        credentials={},
    )

    result = await action.execute(endpoint_id="ep-123")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


# ============================================================================
# LIST ENDPOINTS TESTS
# ============================================================================


@pytest.fixture
def list_endpoints_action(mock_credentials, mock_settings):
    """Create ListEndpointsAction instance."""
    return _build_action(
        ListEndpointsAction, mock_credentials, mock_settings, "list_endpoints"
    )


@pytest.mark.asyncio
async def test_list_endpoints_success(list_endpoints_action):
    """Test successful endpoint listing."""
    api_data = {
        "items": [
            {"id": "ep-1", "hostname": "WS-01"},
            {"id": "ep-2", "hostname": "WS-02"},
        ],
        "pages": {"items": 2, "size": 50, "total": 1},
    }
    list_endpoints_action.http_request = AsyncMock(side_effect=_auth_then_api(api_data))

    result = await list_endpoints_action.execute()

    assert result["status"] == "success"
    assert len(result["data"]["items"]) == 2
    assert result["data"]["total"] == 2


@pytest.mark.asyncio
async def test_list_endpoints_with_filters(list_endpoints_action):
    """Test endpoint listing with filter parameters."""
    api_data = {
        "items": [{"id": "ep-1", "hostname": "SERVER-01"}],
        "pages": {"items": 1},
    }
    list_endpoints_action.http_request = AsyncMock(side_effect=_auth_then_api(api_data))

    result = await list_endpoints_action.execute(
        health_status="good", type="server", page_size=10
    )

    assert result["status"] == "success"
    assert len(result["data"]["items"]) == 1

    # Verify filter params were passed in the API call (3rd call)
    api_call = list_endpoints_action.http_request.call_args_list[2]
    assert api_call.kwargs.get("params", {}).get("healthStatus") == "good"
    assert api_call.kwargs.get("params", {}).get("type") == "server"
    assert api_call.kwargs.get("params", {}).get("pageSize") == 10


@pytest.mark.asyncio
async def test_list_endpoints_auth_failure(list_endpoints_action):
    """Test endpoint listing with authentication failure."""
    list_endpoints_action.http_request = AsyncMock(
        side_effect=Exception("Token request failed")
    )

    result = await list_endpoints_action.execute()

    assert result["status"] == "error"


# ============================================================================
# ISOLATE ENDPOINT TESTS
# ============================================================================


@pytest.fixture
def isolate_action(mock_credentials, mock_settings):
    """Create IsolateEndpointAction instance."""
    return _build_action(
        IsolateEndpointAction, mock_credentials, mock_settings, "isolate_endpoint"
    )


@pytest.mark.asyncio
async def test_isolate_endpoint_success(isolate_action):
    """Test successful endpoint isolation."""
    api_data = {
        "items": [
            {"id": "ep-1", "isolation": {"enabled": True, "status": "isolated"}},
        ],
    }
    isolate_action.http_request = AsyncMock(side_effect=_auth_then_api(api_data))

    result = await isolate_action.execute(ids="ep-1", comment="Suspicious activity")

    assert result["status"] == "success"
    assert result["data"]["count"] == 1
    assert result["data"]["items"][0]["isolation"]["enabled"] is True


@pytest.mark.asyncio
async def test_isolate_endpoint_multiple_ids(isolate_action):
    """Test isolating multiple endpoints via comma-separated string."""
    api_data = {
        "items": [
            {"id": "ep-1", "isolation": {"enabled": True}},
            {"id": "ep-2", "isolation": {"enabled": True}},
        ],
    }
    isolate_action.http_request = AsyncMock(side_effect=_auth_then_api(api_data))

    result = await isolate_action.execute(ids="ep-1,ep-2", comment="Containment")

    assert result["status"] == "success"
    assert result["data"]["count"] == 2

    # Verify the JSON body contains the parsed IDs
    api_call = isolate_action.http_request.call_args_list[2]
    json_body = api_call.kwargs.get("json_data", {})
    assert json_body["ids"] == ["ep-1", "ep-2"]
    assert json_body["enabled"] is True


@pytest.mark.asyncio
async def test_isolate_endpoint_list_ids(isolate_action):
    """Test isolating endpoints with list of IDs."""
    api_data = {"items": [{"id": "ep-1"}]}
    isolate_action.http_request = AsyncMock(side_effect=_auth_then_api(api_data))

    result = await isolate_action.execute(ids=["ep-1", "ep-2"])

    assert result["status"] == "success"

    api_call = isolate_action.http_request.call_args_list[2]
    json_body = api_call.kwargs.get("json_data", {})
    assert json_body["ids"] == ["ep-1", "ep-2"]


@pytest.mark.asyncio
async def test_isolate_endpoint_missing_ids(isolate_action):
    """Test isolation without ids parameter."""
    result = await isolate_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "ids" in result["error"]


# ============================================================================
# UNISOLATE ENDPOINT TESTS
# ============================================================================


@pytest.fixture
def unisolate_action(mock_credentials, mock_settings):
    """Create UnisolateEndpointAction instance."""
    return _build_action(
        UnisolateEndpointAction, mock_credentials, mock_settings, "unisolate_endpoint"
    )


@pytest.mark.asyncio
async def test_unisolate_endpoint_success(unisolate_action):
    """Test successful endpoint unisolation."""
    api_data = {
        "items": [
            {"id": "ep-1", "isolation": {"enabled": False, "status": "notIsolated"}},
        ],
    }
    unisolate_action.http_request = AsyncMock(side_effect=_auth_then_api(api_data))

    result = await unisolate_action.execute(ids="ep-1")

    assert result["status"] == "success"
    assert result["data"]["count"] == 1

    # Verify enabled=False in the body
    api_call = unisolate_action.http_request.call_args_list[2]
    json_body = api_call.kwargs.get("json_data", {})
    assert json_body["enabled"] is False


@pytest.mark.asyncio
async def test_unisolate_endpoint_missing_ids(unisolate_action):
    """Test unisolation without ids parameter."""
    result = await unisolate_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


# ============================================================================
# SCAN ENDPOINT TESTS
# ============================================================================


@pytest.fixture
def scan_action(mock_credentials, mock_settings):
    """Create ScanEndpointAction instance."""
    return _build_action(
        ScanEndpointAction, mock_credentials, mock_settings, "scan_endpoint"
    )


@pytest.mark.asyncio
async def test_scan_endpoint_success(scan_action):
    """Test successful endpoint scan trigger."""
    scan_data = {
        "id": "scan-001",
        "status": "requested",
    }
    scan_action.http_request = AsyncMock(side_effect=_auth_then_api(scan_data))

    result = await scan_action.execute(endpoint_id="ep-123")

    assert result["status"] == "success"
    assert result["data"]["endpoint_id"] == "ep-123"
    assert result["data"]["scan_initiated"] is True


@pytest.mark.asyncio
async def test_scan_endpoint_missing_param(scan_action):
    """Test scan without endpoint_id."""
    result = await scan_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "endpoint_id" in result["error"]


@pytest.mark.asyncio
async def test_scan_endpoint_not_found(scan_action):
    """Test scan for non-existent endpoint."""
    mock_request = MagicMock(spec=httpx.Request)
    mock_request.url = (
        "https://api-us03.central.sophos.com/endpoint/v1/endpoints/bad-id/scans"
    )
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404

    scan_action.http_request = AsyncMock(
        side_effect=[
            _mock_token_response(),
            _mock_whoami_response(),
            httpx.HTTPStatusError(
                "404 Not Found", request=mock_request, response=mock_response
            ),
        ]
    )

    result = await scan_action.execute(endpoint_id="bad-id")

    assert result["status"] == "success"
    assert result["not_found"] is True


# ============================================================================
# LIST ALERTS TESTS
# ============================================================================


@pytest.fixture
def list_alerts_action(mock_credentials, mock_settings):
    """Create ListAlertsAction instance."""
    return _build_action(
        ListAlertsAction, mock_credentials, mock_settings, "list_alerts"
    )


@pytest.mark.asyncio
async def test_list_alerts_success(list_alerts_action):
    """Test successful alert listing."""
    api_data = {
        "items": [
            {"id": "alert-1", "severity": "high", "category": "malware"},
            {"id": "alert-2", "severity": "medium", "category": "pua"},
        ],
        "pages": {"items": 2},
    }
    list_alerts_action.http_request = AsyncMock(side_effect=_auth_then_api(api_data))

    result = await list_alerts_action.execute()

    assert result["status"] == "success"
    assert len(result["data"]["items"]) == 2
    assert result["data"]["total"] == 2


@pytest.mark.asyncio
async def test_list_alerts_with_filters(list_alerts_action):
    """Test listing alerts with filter parameters."""
    api_data = {"items": [], "pages": {"items": 0}}
    list_alerts_action.http_request = AsyncMock(side_effect=_auth_then_api(api_data))

    result = await list_alerts_action.execute(severity="high", limit=10)

    assert result["status"] == "success"

    api_call = list_alerts_action.http_request.call_args_list[2]
    assert api_call.kwargs.get("params", {}).get("severity") == "high"
    assert api_call.kwargs.get("params", {}).get("pageSize") == 10


@pytest.mark.asyncio
async def test_list_alerts_empty(list_alerts_action):
    """Test listing alerts when none exist."""
    api_data = {"items": [], "pages": {"items": 0}}
    list_alerts_action.http_request = AsyncMock(side_effect=_auth_then_api(api_data))

    result = await list_alerts_action.execute()

    assert result["status"] == "success"
    assert len(result["data"]["items"]) == 0
    assert result["data"]["total"] == 0


# ============================================================================
# GET ALERT TESTS
# ============================================================================


@pytest.fixture
def get_alert_action(mock_credentials, mock_settings):
    """Create GetAlertAction instance."""
    return _build_action(GetAlertAction, mock_credentials, mock_settings, "get_alert")


@pytest.mark.asyncio
async def test_get_alert_success(get_alert_action):
    """Test successful alert lookup."""
    alert_data = {
        "id": "alert-42",
        "severity": "high",
        "category": "malware",
        "description": "Malware detected on endpoint",
        "managedAgent": {"id": "ep-1"},
    }
    get_alert_action.http_request = AsyncMock(side_effect=_auth_then_api(alert_data))

    result = await get_alert_action.execute(alert_id="alert-42")

    assert result["status"] == "success"
    assert result["data"]["id"] == "alert-42"
    assert result["data"]["severity"] == "high"


@pytest.mark.asyncio
async def test_get_alert_missing_param(get_alert_action):
    """Test get alert without alert_id."""
    result = await get_alert_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "alert_id" in result["error"]


@pytest.mark.asyncio
async def test_get_alert_not_found(get_alert_action):
    """Test get alert with 404 response."""
    mock_request = MagicMock(spec=httpx.Request)
    mock_request.url = "https://api-us03.central.sophos.com/common/v1/alerts/bad-id"
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404

    get_alert_action.http_request = AsyncMock(
        side_effect=[
            _mock_token_response(),
            _mock_whoami_response(),
            httpx.HTTPStatusError(
                "404 Not Found", request=mock_request, response=mock_response
            ),
        ]
    )

    result = await get_alert_action.execute(alert_id="bad-id")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["alert_id"] == "bad-id"


# ============================================================================
# BLOCK ITEM TESTS
# ============================================================================


@pytest.fixture
def block_item_action(mock_credentials, mock_settings):
    """Create BlockItemAction instance."""
    return _build_action(BlockItemAction, mock_credentials, mock_settings, "block_item")


@pytest.mark.asyncio
async def test_block_item_success(block_item_action):
    """Test successful hash block."""
    api_data = {
        "id": "blocked-item-1",
        "type": "sha256",
        "properties": {"sha256": "abc123def456"},
        "comment": "Malware hash",
    }
    block_item_action.http_request = AsyncMock(side_effect=_auth_then_api(api_data))

    result = await block_item_action.execute(
        sha256="abc123def456", comment="Malware hash"
    )

    assert result["status"] == "success"
    assert result["data"]["id"] == "blocked-item-1"
    assert result["data"]["type"] == "sha256"

    # Verify the JSON body
    api_call = block_item_action.http_request.call_args_list[2]
    json_body = api_call.kwargs.get("json_data", {})
    assert json_body["type"] == "sha256"
    assert json_body["properties"]["sha256"] == "abc123def456"
    assert json_body["comment"] == "Malware hash"


@pytest.mark.asyncio
async def test_block_item_missing_sha256(block_item_action):
    """Test block item without sha256."""
    result = await block_item_action.execute(comment="Test")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "sha256" in result["error"]


@pytest.mark.asyncio
async def test_block_item_default_comment(block_item_action):
    """Test block item uses default comment when not provided."""
    api_data = {"id": "blocked-2", "type": "sha256"}
    block_item_action.http_request = AsyncMock(side_effect=_auth_then_api(api_data))

    result = await block_item_action.execute(sha256="abc123")

    assert result["status"] == "success"

    api_call = block_item_action.http_request.call_args_list[2]
    json_body = api_call.kwargs.get("json_data", {})
    assert "Analysi" in json_body["comment"]


# ============================================================================
# UNBLOCK ITEM TESTS
# ============================================================================


@pytest.fixture
def unblock_item_action(mock_credentials, mock_settings):
    """Create UnblockItemAction instance."""
    return _build_action(
        UnblockItemAction, mock_credentials, mock_settings, "unblock_item"
    )


@pytest.mark.asyncio
async def test_unblock_item_success(unblock_item_action):
    """Test successful item unblock."""
    api_data = {"deleted": True}
    unblock_item_action.http_request = AsyncMock(side_effect=_auth_then_api(api_data))

    result = await unblock_item_action.execute(item_id="blocked-item-1")

    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_unblock_item_204_response(unblock_item_action):
    """Test unblock item with 204 No Content response."""
    mock_204_response = MagicMock()
    mock_204_response.status_code = 204
    mock_204_response.raise_for_status = MagicMock()

    unblock_item_action.http_request = AsyncMock(
        side_effect=[
            _mock_token_response(),
            _mock_whoami_response(),
            mock_204_response,
        ]
    )

    result = await unblock_item_action.execute(item_id="blocked-item-1")

    assert result["status"] == "success"
    assert result["data"]["deleted"] is True


@pytest.mark.asyncio
async def test_unblock_item_missing_param(unblock_item_action):
    """Test unblock without item_id."""
    result = await unblock_item_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "item_id" in result["error"]


@pytest.mark.asyncio
async def test_unblock_item_not_found(unblock_item_action):
    """Test unblock for non-existent item."""
    mock_request = MagicMock(spec=httpx.Request)
    mock_request.url = (
        "https://api-us03.central.sophos.com/endpoint/v1/settings/blocked-items/bad-id"
    )
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404

    unblock_item_action.http_request = AsyncMock(
        side_effect=[
            _mock_token_response(),
            _mock_whoami_response(),
            httpx.HTTPStatusError(
                "404 Not Found", request=mock_request, response=mock_response
            ),
        ]
    )

    result = await unblock_item_action.execute(item_id="bad-id")

    assert result["status"] == "success"
    assert result["not_found"] is True


# ============================================================================
# AUTHENTICATION HELPER TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_auth_token_failure_propagates(get_endpoint_action):
    """Test that OAuth token failure propagates to action result."""
    get_endpoint_action.http_request = AsyncMock(
        side_effect=Exception("Connection refused")
    )

    result = await get_endpoint_action.execute(endpoint_id="ep-1")

    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_auth_whoami_failure_propagates(get_endpoint_action):
    """Test that whoami failure propagates to action result."""
    bad_whoami = MagicMock()
    bad_whoami.json.return_value = {}  # Missing 'id' field
    bad_whoami.raise_for_status = MagicMock()

    get_endpoint_action.http_request = AsyncMock(
        side_effect=[
            _mock_token_response(),
            bad_whoami,
        ]
    )

    result = await get_endpoint_action.execute(endpoint_id="ep-1")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_whoami_organization_type():
    """Test that organization id type uses global URL."""
    action = GetEndpointAction(
        integration_id="sophos",
        action_id="get_endpoint",
        settings={"timeout": 30},
        credentials={
            "client_id": "test-id",
            "client_secret": "test-secret",
        },
    )

    org_whoami = MagicMock()
    org_whoami.json.return_value = {
        "id": "org-id-123",
        "idType": "organization",
        "apiHosts": {
            "dataRegion": "https://api-us03.central.sophos.com",
            "global": "https://api.central.sophos.com",
        },
    }
    org_whoami.raise_for_status = MagicMock()

    endpoint_data = {
        "id": "ep-1",
        "hostname": "WS-01",
    }

    action.http_request = AsyncMock(
        side_effect=[
            _mock_token_response(),
            org_whoami,
            _mock_api_response(endpoint_data),
        ]
    )

    result = await action.execute(endpoint_id="ep-1")

    assert result["status"] == "success"

    # Verify the API call used the global URL and X-Organization-ID header
    api_call = action.http_request.call_args_list[2]
    url = api_call.args[0] if api_call.args else api_call.kwargs.get("url", "")
    assert "api.central.sophos.com" in url

    headers = api_call.kwargs.get("headers", {})
    assert "X-Organization-ID" in headers
    assert headers["X-Organization-ID"] == "org-id-123"


# ============================================================================
# RESULT ENVELOPE TESTS (verify success_result/error_result used)
# ============================================================================


@pytest.mark.asyncio
async def test_success_result_envelope(list_endpoints_action):
    """Verify success results include standard envelope fields."""
    api_data = {"items": [], "pages": {"items": 0}}
    list_endpoints_action.http_request = AsyncMock(side_effect=_auth_then_api(api_data))

    result = await list_endpoints_action.execute()

    assert "status" in result
    assert "timestamp" in result
    assert "integration_id" in result
    assert "action_id" in result
    assert "data" in result
    assert result["integration_id"] == "sophos"


@pytest.mark.asyncio
async def test_error_result_envelope():
    """Verify error results include standard envelope fields."""
    action = BlockItemAction(
        integration_id="sophos",
        action_id="block_item",
        settings={"timeout": 30},
        credentials={},
    )

    result = await action.execute(sha256="abc123")

    assert "status" in result
    assert "timestamp" in result
    assert "integration_id" in result
    assert "action_id" in result
    assert "error" in result
    assert "error_type" in result
    assert result["integration_id"] == "sophos"
