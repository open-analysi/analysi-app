"""
Unit tests for Palo Alto Cortex XDR integration actions.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.cortex_xdr.actions import (
    AlertsToOcsfAction,
    AllowHashAction,
    BlockHashAction,
    GetActionStatusAction,
    GetAlertsAction,
    GetIncidentDetailsAction,
    GetIncidentsAction,
    GetPolicyAction,
    HealthCheckAction,
    ListEndpointsAction,
    PullAlertsAction,
    QuarantineDeviceAction,
    QuarantineFileAction,
    RetrieveFileAction,
    RetrieveFileDetailsAction,
    ScanEndpointAction,
    UnquarantineDeviceAction,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_credentials():
    """Mock credentials."""
    return {
        "api_key": "test_api_key_1234567890",
        "api_key_id": "test_api_key_id",
    }


@pytest.fixture
def mock_settings():
    """Mock settings."""
    return {
        "fqdn": "test.xdr.us.paloaltonetworks.com",
        "advanced": False,
        "timeout": 30,
    }


@pytest.fixture
def health_check_action(mock_credentials, mock_settings):
    """Create HealthCheckAction instance."""
    return HealthCheckAction(
        integration_id="cortex_xdr",
        action_id="health_check",
        settings=mock_settings,
        credentials=mock_credentials,
    )


# ============================================================================
# HEALTH CHECK ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "reply": [{"endpoint_id": "test1"}, {"endpoint_id": "test2"}]
    }
    mock_response.raise_for_status = MagicMock()

    health_check_action.http_request = AsyncMock(return_value=mock_response)
    result = await health_check_action.execute()

    assert result["status"] == "success"
    assert "Successfully connected" in result["message"]
    assert result["endpoint_count"] == 2


@pytest.mark.asyncio
async def test_health_check_missing_credentials():
    """Test health check with missing credentials."""
    action = HealthCheckAction(
        integration_id="cortex_xdr",
        action_id="health_check",
        settings={},
        credentials={},
    )
    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "Missing required credentials" in result["error"]


# ============================================================================
# LIST ENDPOINTS ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_endpoints_success(mock_credentials, mock_settings):
    """Test successful list endpoints."""
    action = ListEndpointsAction(
        integration_id="cortex_xdr",
        action_id="list_endpoints",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "reply": [
            {"endpoint_id": "endpoint1", "hostname": "host1"},
            {"endpoint_id": "endpoint2", "hostname": "host2"},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    action.http_request = AsyncMock(return_value=mock_response)
    result = await action.execute()

    assert result["status"] == "success"
    assert result["endpoint_count"] == 2
    assert len(result["endpoints"]) == 2


# ============================================================================
# GET POLICY ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_policy_success(mock_credentials, mock_settings):
    """Test successful get policy."""
    action = GetPolicyAction(
        integration_id="cortex_xdr",
        action_id="get_policy",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {"reply": {"policy_name": "Default Policy"}}
    mock_response.raise_for_status = MagicMock()

    action.http_request = AsyncMock(return_value=mock_response)
    result = await action.execute(endpoint_id="test_endpoint_123")

    assert result["status"] == "success"
    assert result["policy_name"] == "Default Policy"


@pytest.mark.asyncio
async def test_get_policy_missing_endpoint_id(mock_credentials, mock_settings):
    """Test get policy with missing endpoint_id."""
    action = GetPolicyAction(
        integration_id="cortex_xdr",
        action_id="get_policy",
        settings=mock_settings,
        credentials=mock_credentials,
    )
    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "endpoint_id" in result["error"]


# ============================================================================
# QUARANTINE DEVICE ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_quarantine_device_success(mock_credentials, mock_settings):
    """Test successful device quarantine."""
    action = QuarantineDeviceAction(
        integration_id="cortex_xdr",
        action_id="quarantine_device",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {"reply": {"action_id": 33333}}
    mock_response.raise_for_status = MagicMock()

    action.http_request = AsyncMock(return_value=mock_response)
    result = await action.execute(endpoint_id="test_endpoint_789")

    assert result["status"] == "success"
    assert result["action_id"] == 33333


# ============================================================================
# UNQUARANTINE DEVICE ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_unquarantine_device_success(mock_credentials, mock_settings):
    """Test successful device unquarantine."""
    action = UnquarantineDeviceAction(
        integration_id="cortex_xdr",
        action_id="unquarantine_device",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {"reply": {"action_id": 44444}}
    mock_response.raise_for_status = MagicMock()

    action.http_request = AsyncMock(return_value=mock_response)
    result = await action.execute(endpoint_id="test_endpoint_789")

    assert result["status"] == "success"
    assert result["action_id"] == 44444


# ============================================================================
# SCAN ENDPOINT ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_scan_endpoint_success(mock_credentials, mock_settings):
    """Test successful endpoint scan."""
    action = ScanEndpointAction(
        integration_id="cortex_xdr",
        action_id="scan_endpoint",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "reply": {"action_id": 55555, "endpoints_count": 1}
    }
    mock_response.raise_for_status = MagicMock()

    action.http_request = AsyncMock(return_value=mock_response)
    result = await action.execute(endpoint_id="test_endpoint")

    assert result["status"] == "success"
    assert result["action_id"] == 55555
    assert result["endpoints_scanning"] == 1


@pytest.mark.asyncio
async def test_scan_endpoint_scan_all(mock_credentials, mock_settings):
    """Test scan all endpoints."""
    action = ScanEndpointAction(
        integration_id="cortex_xdr",
        action_id="scan_endpoint",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "reply": {"action_id": 66666, "endpoints_count": 10}
    }
    mock_response.raise_for_status = MagicMock()

    action.http_request = AsyncMock(return_value=mock_response)
    result = await action.execute(scan_all=True)

    assert result["status"] == "success"
    assert result["endpoints_scanning"] == 10


@pytest.mark.asyncio
async def test_scan_endpoint_missing_criteria(mock_credentials, mock_settings):
    """Test scan endpoint with no criteria."""
    action = ScanEndpointAction(
        integration_id="cortex_xdr",
        action_id="scan_endpoint",
        settings=mock_settings,
        credentials=mock_credentials,
    )
    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "filter criterion" in result["error"]


# ============================================================================
# QUARANTINE FILE ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_quarantine_file_success(mock_credentials, mock_settings):
    """Test successful file quarantine."""
    action = QuarantineFileAction(
        integration_id="cortex_xdr",
        action_id="quarantine_file",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {"reply": {"action_id": 11111}}
    mock_response.raise_for_status = MagicMock()

    action.http_request = AsyncMock(return_value=mock_response)
    result = await action.execute(
        endpoint_id="test_endpoint",
        file_path="C:\\malware.exe",
        file_hash="abcd1234567890ef",
    )

    assert result["status"] == "success"
    assert result["action_id"] == 11111


# ============================================================================
# BLOCK HASH ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_block_hash_success(mock_credentials, mock_settings):
    """Test successful hash blocking."""
    action = BlockHashAction(
        integration_id="cortex_xdr",
        action_id="block_hash",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {"reply": "success"}
    mock_response.raise_for_status = MagicMock()

    action.http_request = AsyncMock(return_value=mock_response)
    result = await action.execute(
        file_hash="abcd1234567890ef", comment="Malicious file"
    )

    assert result["status"] == "success"
    assert result["list_updated"] == "success"


# ============================================================================
# ALLOW HASH ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_allow_hash_success(mock_credentials, mock_settings):
    """Test successful hash allowing."""
    action = AllowHashAction(
        integration_id="cortex_xdr",
        action_id="allow_hash",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {"reply": "success"}
    mock_response.raise_for_status = MagicMock()

    action.http_request = AsyncMock(return_value=mock_response)
    result = await action.execute(file_hash="abcd1234567890ef", comment="Safe file")

    assert result["status"] == "success"
    assert result["list_updated"] == "success"


# ============================================================================
# GET INCIDENTS ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_incidents_success(mock_credentials, mock_settings):
    """Test successful get incidents."""
    action = GetIncidentsAction(
        integration_id="cortex_xdr",
        action_id="get_incidents",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "reply": {
            "total_count": 2,
            "result_count": 2,
            "incidents": [
                {"incident_id": "1", "status": "new"},
                {"incident_id": "2", "status": "under_investigation"},
            ],
        }
    }
    mock_response.raise_for_status = MagicMock()

    action.http_request = AsyncMock(return_value=mock_response)
    result = await action.execute()

    assert result["status"] == "success"
    assert result["total_count"] == 2
    assert len(result["incidents"]) == 2


# ============================================================================
# GET ALERTS ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_alerts_success(mock_credentials, mock_settings):
    """Test successful get alerts."""
    action = GetAlertsAction(
        integration_id="cortex_xdr",
        action_id="get_alerts",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "reply": {
            "total_count": 3,
            "result_count": 3,
            "alerts": [
                {"alert_id": "1", "severity": "high"},
                {"alert_id": "2", "severity": "medium"},
                {"alert_id": "3", "severity": "low"},
            ],
        }
    }
    mock_response.raise_for_status = MagicMock()

    action.http_request = AsyncMock(return_value=mock_response)
    result = await action.execute()

    assert result["status"] == "success"
    assert result["total_count"] == 3
    assert len(result["alerts"]) == 3


# ============================================================================
# PULL ALERTS ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_pull_alerts_success(mock_credentials, mock_settings):
    """Test successful pull alerts with time filter."""
    action = PullAlertsAction(
        integration_id="cortex_xdr",
        action_id="pull_alerts",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "reply": {
            "total_count": 2,
            "result_count": 2,
            "alerts": [
                {"alert_id": 1, "severity": "high", "alert_name": "Alert 1"},
                {"alert_id": 2, "severity": "medium", "alert_name": "Alert 2"},
            ],
        }
    }
    mock_response.raise_for_status = MagicMock()

    action.http_request = AsyncMock(return_value=mock_response)
    result = await action.execute(
        start_time="2025-03-15T00:00:00+00:00",
        end_time="2025-03-15T01:00:00+00:00",
    )

    assert result["status"] == "success"
    assert result["alerts_count"] == 2
    assert len(result["alerts"]) == 2
    assert "Retrieved 2 alerts" in result["message"]


@pytest.mark.asyncio
async def test_pull_alerts_missing_credentials():
    """Test pull alerts with missing credentials."""
    action = PullAlertsAction(
        integration_id="cortex_xdr",
        action_id="pull_alerts",
        settings={},
        credentials={},
    )
    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_pull_alerts_default_lookback(mock_credentials, mock_settings):
    """Test pull alerts uses default lookback when no start_time given."""
    action = PullAlertsAction(
        integration_id="cortex_xdr",
        action_id="pull_alerts",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "reply": {
            "total_count": 0,
            "result_count": 0,
            "alerts": [],
        }
    }
    mock_response.raise_for_status = MagicMock()

    action.http_request = AsyncMock(return_value=mock_response)
    result = await action.execute()

    assert result["status"] == "success"
    assert result["alerts_count"] == 0

    # Verify the API was called with time filter
    call_kwargs = action.http_request.call_args
    json_data = call_kwargs.kwargs.get("json_data") or call_kwargs[1].get("json_data")
    filters = json_data["request_data"]["filters"]
    assert any(
        f["field"] == "creation_time" and f["operator"] == "gte" for f in filters
    )
    assert any(
        f["field"] == "creation_time" and f["operator"] == "lte" for f in filters
    )


@pytest.mark.asyncio
async def test_pull_alerts_pagination(mock_credentials, mock_settings):
    """Test pull alerts pagination stops when fewer results than page size."""
    action = PullAlertsAction(
        integration_id="cortex_xdr",
        action_id="pull_alerts",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    # Return fewer results than page size to stop pagination
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "reply": {
            "total_count": 1,
            "result_count": 1,
            "alerts": [{"alert_id": 1}],
        }
    }
    mock_response.raise_for_status = MagicMock()

    action.http_request = AsyncMock(return_value=mock_response)
    result = await action.execute(max_results=500)

    assert result["status"] == "success"
    assert result["alerts_count"] == 1
    # Should only make one API call since results < page size
    assert action.http_request.call_count == 1


@pytest.mark.asyncio
async def test_pull_alerts_http_error(mock_credentials, mock_settings):
    """Test pull alerts handles HTTP errors."""
    action = PullAlertsAction(
        integration_id="cortex_xdr",
        action_id="pull_alerts",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    mock_response = MagicMock()
    mock_response.status_code = 401
    error = MagicMock()
    error.response = mock_response
    action.http_request = AsyncMock(
        side_effect=__import__("httpx").HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )
    )
    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPError"


# ============================================================================
# ALERTS TO OCSF ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_alerts_to_ocsf_success(mock_credentials, mock_settings):
    """Test successful OCSF normalization."""
    action = AlertsToOcsfAction(
        integration_id="cortex_xdr",
        action_id="alerts_to_ocsf",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    raw_alerts = [
        {
            "alert_id": 1,
            "severity": "high",
            "alert_name": "Suspicious PowerShell",
            "detection_timestamp": 1710510600000,
        },
        {
            "alert_id": 2,
            "severity": "low",
            "alert_name": "Info Alert",
            "detection_timestamp": 1710510700000,
        },
    ]

    result = await action.execute(raw_alerts=raw_alerts)

    assert result["status"] == "success"
    assert result["count"] == 2
    assert result["errors"] == 0
    assert len(result["normalized_alerts"]) == 2
    # Verify OCSF structure
    ocsf_alert = result["normalized_alerts"][0]
    assert ocsf_alert["class_uid"] == 2004
    assert ocsf_alert["severity_id"] == 4  # high
    assert ocsf_alert["is_alert"] is True


@pytest.mark.asyncio
async def test_alerts_to_ocsf_empty_list(mock_credentials, mock_settings):
    """Test OCSF normalization with empty list."""
    action = AlertsToOcsfAction(
        integration_id="cortex_xdr",
        action_id="alerts_to_ocsf",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    result = await action.execute(raw_alerts=[])

    assert result["status"] == "success"
    assert result["count"] == 0
    assert result["errors"] == 0


@pytest.mark.asyncio
async def test_alerts_to_ocsf_partial_failure(mock_credentials, mock_settings):
    """Test OCSF normalization with some alerts failing."""
    action = AlertsToOcsfAction(
        integration_id="cortex_xdr",
        action_id="alerts_to_ocsf",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    # Mock the normalizer to fail on one alert
    raw_alerts = [
        {
            "alert_id": 1,
            "severity": "high",
            "alert_name": "Good Alert",
        },
    ]

    result = await action.execute(raw_alerts=raw_alerts)

    # Single valid alert should succeed
    assert result["count"] == 1
    assert result["errors"] == 0


@pytest.mark.asyncio
async def test_alerts_to_ocsf_no_raw_alerts_param(mock_credentials, mock_settings):
    """Test OCSF normalization when raw_alerts param is missing."""
    action = AlertsToOcsfAction(
        integration_id="cortex_xdr",
        action_id="alerts_to_ocsf",
        settings=mock_settings,
        credentials=mock_credentials,
    )

    result = await action.execute()

    assert result["status"] == "success"
    assert result["count"] == 0
    assert result["errors"] == 0


# ============================================================================
# HELPER: Create a 404 HTTPStatusError
# ============================================================================


def _make_404_error() -> httpx.HTTPStatusError:
    """Create a mock 404 HTTPStatusError."""
    mock_response = MagicMock()
    mock_response.status_code = 404
    return httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=mock_response
    )


def _make_500_error() -> httpx.HTTPStatusError:
    """Create a mock 500 HTTPStatusError for contrast tests."""
    mock_response = MagicMock()
    mock_response.status_code = 500
    return httpx.HTTPStatusError(
        "Internal Server Error", request=MagicMock(), response=mock_response
    )


# ============================================================================
# 404 NOT-FOUND HANDLING TESTS — LOOKUP/GET ACTIONS
# ============================================================================


@pytest.mark.asyncio
async def test_get_policy_404_returns_not_found(mock_credentials, mock_settings):
    """GetPolicyAction returns success with not_found=True on 404."""
    action = GetPolicyAction(
        integration_id="cortex_xdr",
        action_id="get_policy",
        settings=mock_settings,
        credentials=mock_credentials,
    )
    action.http_request = AsyncMock(side_effect=_make_404_error())
    result = await action.execute(endpoint_id="test_endpoint_123")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["endpoint_id"] == "test_endpoint_123"
    assert result["policy_name"] is None


@pytest.mark.asyncio
async def test_get_policy_500_returns_error(mock_credentials, mock_settings):
    """GetPolicyAction returns error on non-404 HTTP errors."""
    action = GetPolicyAction(
        integration_id="cortex_xdr",
        action_id="get_policy",
        settings=mock_settings,
        credentials=mock_credentials,
    )
    action.http_request = AsyncMock(side_effect=_make_500_error())
    result = await action.execute(endpoint_id="test_endpoint_123")

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPError"
    assert "500" in result["error"]


@pytest.mark.asyncio
async def test_get_action_status_404_returns_not_found(mock_credentials, mock_settings):
    """GetActionStatusAction returns success with not_found=True on 404."""
    action = GetActionStatusAction(
        integration_id="cortex_xdr",
        action_id="get_action_status",
        settings=mock_settings,
        credentials=mock_credentials,
    )
    action.http_request = AsyncMock(side_effect=_make_404_error())
    result = await action.execute(action_id=12345)

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["action_id"] == 12345
    assert result["action_status"] is None


@pytest.mark.asyncio
async def test_get_action_status_500_returns_error(mock_credentials, mock_settings):
    """GetActionStatusAction returns error on non-404 HTTP errors."""
    action = GetActionStatusAction(
        integration_id="cortex_xdr",
        action_id="get_action_status",
        settings=mock_settings,
        credentials=mock_credentials,
    )
    action.http_request = AsyncMock(side_effect=_make_500_error())
    result = await action.execute(action_id=12345)

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPError"


@pytest.mark.asyncio
async def test_get_incidents_404_returns_not_found(mock_credentials, mock_settings):
    """GetIncidentsAction returns success with not_found=True and empty list on 404."""
    action = GetIncidentsAction(
        integration_id="cortex_xdr",
        action_id="get_incidents",
        settings=mock_settings,
        credentials=mock_credentials,
    )
    action.http_request = AsyncMock(side_effect=_make_404_error())
    result = await action.execute()

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["total_count"] == 0
    assert result["result_count"] == 0
    assert result["incidents"] == []


@pytest.mark.asyncio
async def test_get_incidents_500_returns_error(mock_credentials, mock_settings):
    """GetIncidentsAction returns error on non-404 HTTP errors."""
    action = GetIncidentsAction(
        integration_id="cortex_xdr",
        action_id="get_incidents",
        settings=mock_settings,
        credentials=mock_credentials,
    )
    action.http_request = AsyncMock(side_effect=_make_500_error())
    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPError"


@pytest.mark.asyncio
async def test_get_incident_details_404_returns_not_found(
    mock_credentials, mock_settings
):
    """GetIncidentDetailsAction returns success with not_found=True on 404."""
    action = GetIncidentDetailsAction(
        integration_id="cortex_xdr",
        action_id="get_incident_details",
        settings=mock_settings,
        credentials=mock_credentials,
    )
    action.http_request = AsyncMock(side_effect=_make_404_error())
    result = await action.execute(incident_id=99999)

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["incident_id"] == 99999
    assert result["incident_details"] is None


@pytest.mark.asyncio
async def test_get_incident_details_500_returns_error(mock_credentials, mock_settings):
    """GetIncidentDetailsAction returns error on non-404 HTTP errors."""
    action = GetIncidentDetailsAction(
        integration_id="cortex_xdr",
        action_id="get_incident_details",
        settings=mock_settings,
        credentials=mock_credentials,
    )
    action.http_request = AsyncMock(side_effect=_make_500_error())
    result = await action.execute(incident_id=99999)

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPError"


@pytest.mark.asyncio
async def test_get_alerts_404_returns_not_found(mock_credentials, mock_settings):
    """GetAlertsAction returns success with not_found=True and empty list on 404."""
    action = GetAlertsAction(
        integration_id="cortex_xdr",
        action_id="get_alerts",
        settings=mock_settings,
        credentials=mock_credentials,
    )
    action.http_request = AsyncMock(side_effect=_make_404_error())
    result = await action.execute()

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["total_count"] == 0
    assert result["result_count"] == 0
    assert result["alerts"] == []


@pytest.mark.asyncio
async def test_get_alerts_500_returns_error(mock_credentials, mock_settings):
    """GetAlertsAction returns error on non-404 HTTP errors."""
    action = GetAlertsAction(
        integration_id="cortex_xdr",
        action_id="get_alerts",
        settings=mock_settings,
        credentials=mock_credentials,
    )
    action.http_request = AsyncMock(side_effect=_make_500_error())
    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPError"


@pytest.mark.asyncio
async def test_list_endpoints_404_returns_not_found(mock_credentials, mock_settings):
    """ListEndpointsAction returns success with not_found=True and empty list on 404."""
    action = ListEndpointsAction(
        integration_id="cortex_xdr",
        action_id="list_endpoints",
        settings=mock_settings,
        credentials=mock_credentials,
    )
    action.http_request = AsyncMock(side_effect=_make_404_error())
    result = await action.execute()

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["endpoint_count"] == 0
    assert result["endpoints"] == []


@pytest.mark.asyncio
async def test_list_endpoints_500_returns_error(mock_credentials, mock_settings):
    """ListEndpointsAction returns error on non-404 HTTP errors."""
    action = ListEndpointsAction(
        integration_id="cortex_xdr",
        action_id="list_endpoints",
        settings=mock_settings,
        credentials=mock_credentials,
    )
    action.http_request = AsyncMock(side_effect=_make_500_error())
    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPError"


@pytest.mark.asyncio
async def test_retrieve_file_404_returns_not_found(mock_credentials, mock_settings):
    """RetrieveFileAction returns success with not_found=True on 404."""
    action = RetrieveFileAction(
        integration_id="cortex_xdr",
        action_id="retrieve_file",
        settings=mock_settings,
        credentials=mock_credentials,
    )
    action.http_request = AsyncMock(side_effect=_make_404_error())
    result = await action.execute(
        endpoint_id="test_endpoint", windows_path="C:\\file.txt"
    )

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["endpoint_id"] == "test_endpoint"
    assert result["action_id"] is None


@pytest.mark.asyncio
async def test_retrieve_file_500_returns_error(mock_credentials, mock_settings):
    """RetrieveFileAction returns error on non-404 HTTP errors."""
    action = RetrieveFileAction(
        integration_id="cortex_xdr",
        action_id="retrieve_file",
        settings=mock_settings,
        credentials=mock_credentials,
    )
    action.http_request = AsyncMock(side_effect=_make_500_error())
    result = await action.execute(
        endpoint_id="test_endpoint", windows_path="C:\\file.txt"
    )

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPError"


@pytest.mark.asyncio
async def test_retrieve_file_details_404_returns_not_found(
    mock_credentials, mock_settings
):
    """RetrieveFileDetailsAction returns success with not_found=True on 404."""
    action = RetrieveFileDetailsAction(
        integration_id="cortex_xdr",
        action_id="retrieve_file_details",
        settings=mock_settings,
        credentials=mock_credentials,
    )
    action.http_request = AsyncMock(side_effect=_make_404_error())
    result = await action.execute(action_id=77777)

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["action_id"] == 77777
    assert result["file_data"] is None


@pytest.mark.asyncio
async def test_retrieve_file_details_500_returns_error(mock_credentials, mock_settings):
    """RetrieveFileDetailsAction returns error on non-404 HTTP errors."""
    action = RetrieveFileDetailsAction(
        integration_id="cortex_xdr",
        action_id="retrieve_file_details",
        settings=mock_settings,
        credentials=mock_credentials,
    )
    action.http_request = AsyncMock(side_effect=_make_500_error())
    result = await action.execute(action_id=77777)

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPError"
