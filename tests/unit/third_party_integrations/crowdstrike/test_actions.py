"""Unit tests for CrowdStrike Falcon integration actions."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.crowdstrike.actions import (
    AlertsToOcsfAction,
    CheckDetonationStatusAction,
    CreateSessionAction,
    DeleteIndicatorAction,
    DetonateFileAction,
    DetonateUrlAction,
    FileReputationAction,
    GetDetectionDetailsAction,
    GetDeviceDetailsAction,
    GetIncidentDetailsAction,
    GetSessionFileAction,
    GetSystemInfoAction,
    HealthCheckAction,
    HuntDomainAction,
    HuntFileAction,
    HuntIpAction,
    ListAlertsAction,
    ListDetectionsAction,
    ListGroupsAction,
    ListIncidentsAction,
    ListProcessesAction,
    ListSessionsAction,
    PullAlertsAction,
    QuarantineDeviceAction,
    QueryDeviceAction,
    UnquarantineDeviceAction,
    UpdateDetectionsAction,
    UploadIndicatorAction,
    UrlReputationAction,
)


@pytest.fixture
def mock_credentials():
    """Mock CrowdStrike credentials."""
    return {
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
    }


@pytest.fixture
def mock_settings():
    """Mock integration settings."""
    return {
        "base_url": "https://api.crowdstrike.com",
        "timeout": 30,
    }


def create_action(
    action_class, action_id="test_action", credentials=None, settings=None
):
    """Helper to create action instances with required parameters."""
    return action_class(
        integration_id="crowdstrike",
        action_id=action_id,
        credentials=credentials or {},
        settings=settings or {},
    )


# ============================================================================
# HealthCheckAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(mock_credentials, mock_settings):
    """Test successful health check."""
    action = create_action(
        HealthCheckAction, "health_check", mock_credentials, mock_settings
    )

    # Mock token response (POST for OAuth2)
    token_response = MagicMock()
    token_response.status_code = 200
    token_response.json.return_value = {"access_token": "test_token"}
    token_response.raise_for_status = MagicMock()

    # Mock devices query response (GET for device query)
    devices_response = MagicMock()
    devices_response.status_code = 200
    devices_response.json.return_value = {"resources": []}
    devices_response.raise_for_status = MagicMock()

    action.http_request = AsyncMock(side_effect=[token_response, devices_response])
    result = await action.execute()

    assert result["status"] == "success"
    assert result["healthy"] is True


@pytest.mark.asyncio
async def test_health_check_missing_credentials():
    """Test health check with missing credentials."""
    action = create_action(HealthCheckAction, "health_check")

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "AuthenticationError"


# ============================================================================
# QueryDeviceAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_query_device_success(mock_credentials, mock_settings):
    """Test successful device query."""
    action = create_action(
        QueryDeviceAction, "QueryDevice", mock_credentials, mock_settings
    )

    mock_response = {"resources": ["device_id_1", "device_id_2"]}

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(action, "_make_api_request", return_value=mock_response):
            result = await action.execute(filter="hostname:'TEST-*'", limit=10)

    assert result["status"] == "success"
    assert len(result["device_ids"]) == 2
    assert result["count"] == 2


# ============================================================================
# GetDeviceDetailsAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_device_details_success(mock_credentials, mock_settings):
    """Test successful device details retrieval."""
    action = create_action(
        GetDeviceDetailsAction, "GetDeviceDetails", mock_credentials, mock_settings
    )

    mock_response = {
        "resources": [
            {
                "device_id": "device_1",
                "hostname": "TEST-HOST-01",
                "os_version": "Windows 10",
            }
        ]
    }

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(action, "_make_api_request", return_value=mock_response):
            result = await action.execute(device_ids=["device_1"])

    assert result["status"] == "success"
    assert len(result["devices"]) == 1
    assert result["devices"][0]["hostname"] == "TEST-HOST-01"


@pytest.mark.asyncio
async def test_get_device_details_missing_device_ids(mock_credentials, mock_settings):
    """Test device details with missing device_ids."""
    action = create_action(
        GetDeviceDetailsAction, "GetDeviceDetails", mock_credentials, mock_settings
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


# ============================================================================
# QuarantineDeviceAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_quarantine_device_success(mock_credentials, mock_settings):
    """Test successful device quarantine."""
    action = create_action(
        QuarantineDeviceAction, "QuarantineDevice", mock_credentials, mock_settings
    )

    mock_response = {"resources": [{"id": "device_1"}]}

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(action, "_make_api_request", return_value=mock_response):
            result = await action.execute(device_id="device_1")

    assert result["status"] == "success"
    assert "quarantined successfully" in result["message"]


@pytest.mark.asyncio
async def test_quarantine_device_by_hostname(mock_credentials, mock_settings):
    """Test device quarantine by hostname."""
    action = create_action(
        QuarantineDeviceAction, "QuarantineDevice", mock_credentials, mock_settings
    )

    mock_query_response = {"resources": ["device_1"]}
    mock_action_response = {"resources": [{"id": "device_1"}]}

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_make_api_request",
            side_effect=[mock_query_response, mock_action_response],
        ):
            result = await action.execute(hostname="TEST-HOST-01")

    assert result["status"] == "success"


# ============================================================================
# UnquarantineDeviceAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_unquarantine_device_success(mock_credentials, mock_settings):
    """Test successful device unquarantine."""
    action = create_action(
        UnquarantineDeviceAction, "UnquarantineDevice", mock_credentials, mock_settings
    )

    mock_response = {"resources": [{"id": "device_1"}]}

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(action, "_make_api_request", return_value=mock_response):
            result = await action.execute(device_id="device_1")

    assert result["status"] == "success"
    assert "unquarantined successfully" in result["message"]


# ============================================================================
# ListDetectionsAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_detections_success(mock_credentials, mock_settings):
    """Test successful detections listing."""
    action = create_action(
        ListDetectionsAction, "ListDetections", mock_credentials, mock_settings
    )

    mock_ids_response = {"resources": ["detection_1", "detection_2"]}
    mock_details_response = {
        "resources": [
            {"detection_id": "detection_1", "severity": "high"},
            {"detection_id": "detection_2", "severity": "medium"},
        ]
    }

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_make_api_request",
            side_effect=[mock_ids_response, mock_details_response],
        ):
            result = await action.execute(limit=10)

    assert result["status"] == "success"
    assert len(result["detections"]) == 2


# ============================================================================
# UpdateDetectionsAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_update_detections_success(mock_credentials, mock_settings):
    """Test successful detection update."""
    action = create_action(
        UpdateDetectionsAction, "UpdateDetections", mock_credentials, mock_settings
    )

    mock_response = {"resources": [{"id": "detection_1"}]}

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(action, "_make_api_request", return_value=mock_response):
            result = await action.execute(
                detection_ids=["detection_1"], status="in_progress"
            )

    assert result["status"] == "success"
    assert "updated successfully" in result["message"]


# ============================================================================
# CreateSessionAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_session_success(mock_credentials, mock_settings):
    """Test successful RTR session creation."""
    action = create_action(
        CreateSessionAction, "CreateSession", mock_credentials, mock_settings
    )

    mock_response = {
        "resources": [{"session_id": "session_1", "device_id": "device_1"}]
    }

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(action, "_make_api_request", return_value=mock_response):
            result = await action.execute(device_id="device_1")

    assert result["status"] == "success"
    assert result["session_id"] == "session_1"


# ============================================================================
# HuntFileAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_hunt_file_success(mock_credentials, mock_settings):
    """Test successful file hash hunting."""
    action = create_action(HuntFileAction, "HuntFile", mock_credentials, mock_settings)

    mock_response = {"resources": ["device_1", "device_2"]}

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(action, "_make_api_request", return_value=mock_response):
            result = await action.execute(hash="abc123")

    assert result["status"] == "success"
    assert len(result["device_ids"]) == 2


# ============================================================================
# HuntDomainAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_hunt_domain_success(mock_credentials, mock_settings):
    """Test successful domain hunting."""
    action = create_action(
        HuntDomainAction, "HuntDomain", mock_credentials, mock_settings
    )

    mock_response = {"resources": ["device_1"]}

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(action, "_make_api_request", return_value=mock_response):
            result = await action.execute(domain="malicious.com")

    assert result["status"] == "success"
    assert result["domain"] == "malicious.com"


# ============================================================================
# HuntIpAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_hunt_ip_success(mock_credentials, mock_settings):
    """Test successful IP hunting."""
    action = create_action(HuntIpAction, "HuntIp", mock_credentials, mock_settings)

    mock_response = {"resources": ["device_1", "device_2", "device_3"]}

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(action, "_make_api_request", return_value=mock_response):
            result = await action.execute(ip="192.168.1.100")

    assert result["status"] == "success"
    assert len(result["device_ids"]) == 3


# ============================================================================
# UploadIndicatorAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_upload_indicator_success(mock_credentials, mock_settings):
    """Test successful IOC upload."""
    action = create_action(
        UploadIndicatorAction, "UploadIndicator", mock_credentials, mock_settings
    )

    mock_response = {"resources": [{"id": "indicator_1"}]}

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(action, "_make_api_request", return_value=mock_response):
            result = await action.execute(
                type="domain", value="malicious.com", policy="detect", severity="high"
            )

    assert result["status"] == "success"
    assert "uploaded successfully" in result["message"]


# ============================================================================
# DeleteIndicatorAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_delete_indicator_success(mock_credentials, mock_settings):
    """Test successful IOC deletion."""
    action = create_action(
        DeleteIndicatorAction, "DeleteIndicator", mock_credentials, mock_settings
    )

    mock_response = {"status": "success"}

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(action, "_make_api_request", return_value=mock_response):
            result = await action.execute(ids=["indicator_1"])

    assert result["status"] == "success"
    assert "deleted successfully" in result["message"]


# ============================================================================
# FileReputationAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_file_reputation_found(mock_credentials, mock_settings):
    """Test file reputation when hash is found."""
    action = create_action(
        FileReputationAction, "FileReputation", mock_credentials, mock_settings
    )

    mock_response = {
        "resources": [{"id": "indicator_1", "value": "abc123", "severity": "high"}]
    }

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(action, "_make_api_request", return_value=mock_response):
            result = await action.execute(hash="abc123")

    assert result["status"] == "success"
    assert result["found"] is True


@pytest.mark.asyncio
async def test_file_reputation_not_found(mock_credentials, mock_settings):
    """Test file reputation when hash is not found."""
    action = create_action(
        FileReputationAction, "FileReputation", mock_credentials, mock_settings
    )

    mock_response = {"resources": []}

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(action, "_make_api_request", return_value=mock_response):
            result = await action.execute(hash="abc123")

    assert result["status"] == "success"
    assert result["found"] is False


# ============================================================================
# DetonateFileAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_detonate_file_success(mock_credentials, mock_settings):
    """Test successful file detonation."""
    action = create_action(
        DetonateFileAction, "DetonateFile", mock_credentials, mock_settings
    )

    mock_response = {"resources": [{"id": "submission_1", "state": "submitted"}]}

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(action, "_make_api_request", return_value=mock_response):
            result = await action.execute(sha256="abc123", environment_id=160)

    assert result["status"] == "success"
    assert result["submission_id"] == "submission_1"


# ============================================================================
# DetonateUrlAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_detonate_url_success(mock_credentials, mock_settings):
    """Test successful URL detonation."""
    action = create_action(
        DetonateUrlAction, "DetonateUrl", mock_credentials, mock_settings
    )

    mock_response = {"resources": [{"id": "submission_2", "state": "submitted"}]}

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(action, "_make_api_request", return_value=mock_response):
            result = await action.execute(url="https://example.com", environment_id=160)

    assert result["status"] == "success"
    assert result["submission_id"] == "submission_2"


# ============================================================================
# CheckDetonationStatusAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_check_detonation_status_success(mock_credentials, mock_settings):
    """Test successful detonation status check."""
    action = create_action(
        CheckDetonationStatusAction,
        "CheckDetonationStatus",
        mock_credentials,
        mock_settings,
    )

    mock_response = {
        "resources": [
            {"id": "submission_1", "verdict": "malicious", "threat_score": 95}
        ]
    }

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(action, "_make_api_request", return_value=mock_response):
            result = await action.execute(submission_ids=["submission_1"])

    assert result["status"] == "success"
    assert len(result["reports"]) == 1


# ============================================================================
# PullAlertsAction Tests
# ============================================================================


@pytest.fixture
def pull_alerts_action(mock_credentials, mock_settings):
    """Create PullAlertsAction instance."""
    return create_action(
        PullAlertsAction, "pull_alerts", mock_credentials, mock_settings
    )


@pytest.mark.asyncio
async def test_pull_alerts_success(pull_alerts_action):
    """Test successful alert pull with results."""
    now = datetime.now(UTC)
    ids_response = {"resources": ["cs:alert:001", "cs:alert:002"]}
    details_response = {
        "resources": [
            {"composite_id": "cs:alert:001", "severity": 4, "display_name": "Alert 1"},
            {"composite_id": "cs:alert:002", "severity": 3, "display_name": "Alert 2"},
        ]
    }

    with patch.object(
        pull_alerts_action, "_get_access_token", return_value="test_token"
    ):
        with patch.object(
            pull_alerts_action,
            "_make_api_request",
            side_effect=[ids_response, details_response, {"resources": []}],
        ):
            result = await pull_alerts_action.execute(
                start_time=now - timedelta(hours=1),
                end_time=now,
            )

    assert result["status"] == "success"
    assert result["alerts_count"] == 2
    assert len(result["alerts"]) == 2
    assert "Retrieved 2 alerts" in result["message"]


@pytest.mark.asyncio
async def test_pull_alerts_empty(pull_alerts_action):
    """Test alert pull with no matching alerts."""
    now = datetime.now(UTC)
    ids_response = {"resources": []}

    with patch.object(
        pull_alerts_action, "_get_access_token", return_value="test_token"
    ):
        with patch.object(
            pull_alerts_action,
            "_make_api_request",
            return_value=ids_response,
        ):
            result = await pull_alerts_action.execute(
                start_time=now - timedelta(hours=1),
                end_time=now,
            )

    assert result["status"] == "success"
    assert result["alerts_count"] == 0
    assert result["alerts"] == []


@pytest.mark.asyncio
async def test_pull_alerts_missing_credentials():
    """Test alert pull with missing credentials."""
    action = create_action(PullAlertsAction, "pull_alerts")

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "Missing required credentials" in result["error"]


@pytest.mark.asyncio
async def test_pull_alerts_default_lookback(pull_alerts_action):
    """Test that default lookback is applied when no time params given."""
    ids_response = {"resources": []}

    with patch.object(
        pull_alerts_action, "_get_access_token", return_value="test_token"
    ):
        with patch.object(
            pull_alerts_action,
            "_make_api_request",
            return_value=ids_response,
        ) as mock_request:
            result = await pull_alerts_action.execute()

    assert result["status"] == "success"

    # Verify the FQL filter was constructed with a time range
    call_kwargs = mock_request.call_args
    fql_filter = call_kwargs.kwargs.get("params", {}).get("filter", "")
    assert "created_timestamp:>=" in fql_filter
    assert "created_timestamp:<=" in fql_filter


@pytest.mark.asyncio
async def test_pull_alerts_pagination(pull_alerts_action):
    """Test pagination across multiple pages of alert IDs."""
    now = datetime.now(UTC)

    # Page 1: 500 IDs (full page), page 2: 100 IDs (partial, stops)
    page1_ids = {"resources": [f"cs:alert:{i:04d}" for i in range(500)]}
    page1_details = {
        "resources": [
            {"composite_id": f"cs:alert:{i:04d}", "severity": 3} for i in range(500)
        ]
    }
    page2_ids = {"resources": [f"cs:alert:{i:04d}" for i in range(500, 600)]}
    page2_details = {
        "resources": [
            {"composite_id": f"cs:alert:{i:04d}", "severity": 3}
            for i in range(500, 600)
        ]
    }

    with patch.object(
        pull_alerts_action, "_get_access_token", return_value="test_token"
    ):
        with patch.object(
            pull_alerts_action,
            "_make_api_request",
            side_effect=[
                page1_ids,
                page1_details,
                page2_ids,
                page2_details,
            ],
        ):
            result = await pull_alerts_action.execute(
                start_time=now - timedelta(hours=1),
                end_time=now,
            )

    assert result["status"] == "success"
    assert result["alerts_count"] == 600


@pytest.mark.asyncio
async def test_pull_alerts_iso_string_times(pull_alerts_action):
    """Test that ISO string time parameters are parsed correctly."""
    ids_response = {"resources": []}

    with patch.object(
        pull_alerts_action, "_get_access_token", return_value="test_token"
    ):
        with patch.object(
            pull_alerts_action,
            "_make_api_request",
            return_value=ids_response,
        ):
            result = await pull_alerts_action.execute(
                start_time="2025-03-15T10:00:00+00:00",
                end_time="2025-03-15T11:00:00+00:00",
            )

    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_pull_alerts_respects_max_results(mock_credentials, mock_settings):
    """Test that max_results limits the number of alerts retrieved."""
    action = create_action(
        PullAlertsAction, "pull_alerts", mock_credentials, mock_settings
    )
    now = datetime.now(UTC)

    # Return 10 IDs, but max_results is 5
    ids_response = {"resources": [f"cs:alert:{i}" for i in range(5)]}
    details_response = {
        "resources": [
            {"composite_id": f"cs:alert:{i}", "severity": 3} for i in range(5)
        ]
    }

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action,
            "_make_api_request",
            side_effect=[ids_response, details_response],
        ):
            result = await action.execute(
                start_time=now - timedelta(hours=1),
                end_time=now,
                max_results=5,
            )

    assert result["status"] == "success"
    assert result["alerts_count"] == 5


# ============================================================================
# AlertsToOcsfAction Tests
# ============================================================================


@pytest.fixture
def alerts_to_ocsf_action():
    """Create AlertsToOcsfAction instance."""
    return AlertsToOcsfAction(
        integration_id="crowdstrike",
        action_id="alerts_to_ocsf",
        settings={},
        credentials={},
    )


@pytest.mark.asyncio
async def test_alerts_to_ocsf_success(alerts_to_ocsf_action):
    """Test successful OCSF normalization."""
    raw_alerts = [
        {"composite_id": "cs:alert:001", "severity": 4, "display_name": "Alert 1"},
        {"composite_id": "cs:alert:002", "severity": 3, "display_name": "Alert 2"},
    ]
    ocsf_doc_1 = {"class_uid": 2004, "finding_info": {"uid": "cs:alert:001"}}
    ocsf_doc_2 = {"class_uid": 2004, "finding_info": {"uid": "cs:alert:002"}}

    mock_normalizer = MagicMock()
    mock_normalizer.to_ocsf.side_effect = [ocsf_doc_1, ocsf_doc_2]

    with patch.dict(
        "sys.modules",
        {
            "alert_normalizer": MagicMock(),
            "alert_normalizer.crowdstrike_ocsf": MagicMock(),
        },
    ):
        with patch(
            "alert_normalizer.crowdstrike_ocsf.CrowdStrikeOCSFNormalizer",
            return_value=mock_normalizer,
        ):
            result = await alerts_to_ocsf_action.execute(raw_alerts=raw_alerts)

    assert result["status"] == "success"
    assert result["count"] == 2
    assert result["errors"] == 0
    assert len(result["normalized_alerts"]) == 2
    assert result["normalized_alerts"][0]["class_uid"] == 2004


@pytest.mark.asyncio
async def test_alerts_to_ocsf_empty(alerts_to_ocsf_action):
    """Test OCSF normalization with empty input."""
    mock_normalizer = MagicMock()

    with patch.dict(
        "sys.modules",
        {
            "alert_normalizer": MagicMock(),
            "alert_normalizer.crowdstrike_ocsf": MagicMock(),
        },
    ):
        with patch(
            "alert_normalizer.crowdstrike_ocsf.CrowdStrikeOCSFNormalizer",
            return_value=mock_normalizer,
        ):
            result = await alerts_to_ocsf_action.execute(raw_alerts=[])

    assert result["status"] == "success"
    assert result["count"] == 0
    assert result["errors"] == 0
    assert result["normalized_alerts"] == []


@pytest.mark.asyncio
async def test_alerts_to_ocsf_partial_failure(alerts_to_ocsf_action):
    """Test OCSF normalization where one alert fails."""
    raw_alerts = [
        {"composite_id": "cs:alert:001", "severity": 4, "display_name": "Alert 1"},
        {"composite_id": "cs:alert:002", "severity": 3, "display_name": "Alert 2"},
        {"composite_id": "cs:alert:003", "severity": 5, "display_name": "Alert 3"},
    ]
    ocsf_good = {"class_uid": 2004, "finding_info": {"uid": "ok"}}

    mock_normalizer = MagicMock()
    mock_normalizer.to_ocsf.side_effect = [
        ocsf_good,
        ValueError("bad alert"),
        ocsf_good,
    ]

    with patch.dict(
        "sys.modules",
        {
            "alert_normalizer": MagicMock(),
            "alert_normalizer.crowdstrike_ocsf": MagicMock(),
        },
    ):
        with patch(
            "alert_normalizer.crowdstrike_ocsf.CrowdStrikeOCSFNormalizer",
            return_value=mock_normalizer,
        ):
            result = await alerts_to_ocsf_action.execute(raw_alerts=raw_alerts)

    assert result["status"] == "partial"
    assert result["count"] == 2
    assert result["errors"] == 1


# ============================================================================
# 404 Not-Found Handling Tests
# ============================================================================


def _make_http_404_error():
    """Create an httpx.HTTPStatusError with status 404."""
    response = MagicMock()
    response.status_code = 404
    response.headers = {}
    response.text = "Not Found"
    request = MagicMock()
    return httpx.HTTPStatusError("Not Found", request=request, response=response)


@pytest.mark.asyncio
async def test_query_device_404_returns_not_found(mock_credentials, mock_settings):
    """Test QueryDeviceAction returns not_found on 404."""
    action = create_action(
        QueryDeviceAction, "QueryDevice", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action, "_make_api_request", side_effect=_make_http_404_error()
        ):
            result = await action.execute(filter="hostname:'NONEXISTENT'")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["device_ids"] == []
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_get_device_details_404_returns_not_found(
    mock_credentials, mock_settings
):
    """Test GetDeviceDetailsAction returns not_found on 404."""
    action = create_action(
        GetDeviceDetailsAction, "GetDeviceDetails", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action, "_make_api_request", side_effect=_make_http_404_error()
        ):
            result = await action.execute(device_ids=["nonexistent_id"])

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["devices"] == []
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_list_groups_404_returns_not_found(mock_credentials, mock_settings):
    """Test ListGroupsAction returns not_found on 404."""
    action = create_action(
        ListGroupsAction, "ListGroups", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action, "_make_api_request", side_effect=_make_http_404_error()
        ):
            result = await action.execute(filter="name:'nonexistent'")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["groups"] == []
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_list_detections_404_returns_not_found(mock_credentials, mock_settings):
    """Test ListDetectionsAction returns not_found on 404."""
    action = create_action(
        ListDetectionsAction, "ListDetections", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action, "_make_api_request", side_effect=_make_http_404_error()
        ):
            result = await action.execute(filter="status:'new'")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["detections"] == []
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_get_detection_details_404_returns_not_found(
    mock_credentials, mock_settings
):
    """Test GetDetectionDetailsAction returns not_found on 404."""
    action = create_action(
        GetDetectionDetailsAction,
        "GetDetectionDetails",
        mock_credentials,
        mock_settings,
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action, "_make_api_request", side_effect=_make_http_404_error()
        ):
            result = await action.execute(detection_ids=["nonexistent_det"])

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["detections"] == []
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_list_alerts_404_returns_not_found(mock_credentials, mock_settings):
    """Test ListAlertsAction returns not_found on 404."""
    action = create_action(
        ListAlertsAction, "ListAlerts", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action, "_make_api_request", side_effect=_make_http_404_error()
        ):
            result = await action.execute(filter="severity:>3")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["alerts"] == []
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_list_sessions_404_returns_not_found(mock_credentials, mock_settings):
    """Test ListSessionsAction returns not_found on 404."""
    action = create_action(
        ListSessionsAction, "ListSessions", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action, "_make_api_request", side_effect=_make_http_404_error()
        ):
            result = await action.execute()

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["sessions"] == []
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_get_incident_details_404_returns_not_found(
    mock_credentials, mock_settings
):
    """Test GetIncidentDetailsAction returns not_found on 404."""
    action = create_action(
        GetIncidentDetailsAction,
        "GetIncidentDetails",
        mock_credentials,
        mock_settings,
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action, "_make_api_request", side_effect=_make_http_404_error()
        ):
            result = await action.execute(incident_ids=["nonexistent_inc"])

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["incidents"] == []
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_list_incidents_404_returns_not_found(mock_credentials, mock_settings):
    """Test ListIncidentsAction returns not_found on 404."""
    action = create_action(
        ListIncidentsAction, "ListIncidents", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action, "_make_api_request", side_effect=_make_http_404_error()
        ):
            result = await action.execute(filter="status:'new'")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["incidents"] == []
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_get_session_file_404_returns_not_found(mock_credentials, mock_settings):
    """Test GetSessionFileAction returns not_found on 404."""
    action = create_action(
        GetSessionFileAction, "GetSessionFile", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action, "_make_api_request", side_effect=_make_http_404_error()
        ):
            result = await action.execute(session_id="sess_123", sha256="abc123def456")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["session_id"] == "sess_123"
    assert result["sha256"] == "abc123def456"


@pytest.mark.asyncio
async def test_get_system_info_404_returns_not_found(mock_credentials, mock_settings):
    """Test GetSystemInfoAction returns not_found on 404."""
    action = create_action(
        GetSystemInfoAction, "GetSystemInfo", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action, "_make_api_request", side_effect=_make_http_404_error()
        ):
            result = await action.execute(device_id="nonexistent_device")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["device_id"] == "nonexistent_device"


@pytest.mark.asyncio
async def test_hunt_file_404_returns_not_found(mock_credentials, mock_settings):
    """Test HuntFileAction returns not_found on 404."""
    action = create_action(HuntFileAction, "HuntFile", mock_credentials, mock_settings)

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action, "_make_api_request", side_effect=_make_http_404_error()
        ):
            result = await action.execute(hash="deadbeef1234")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["hash"] == "deadbeef1234"
    assert result["device_ids"] == []
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_hunt_domain_404_returns_not_found(mock_credentials, mock_settings):
    """Test HuntDomainAction returns not_found on 404."""
    action = create_action(
        HuntDomainAction, "HuntDomain", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action, "_make_api_request", side_effect=_make_http_404_error()
        ):
            result = await action.execute(domain="nonexistent.example.com")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["domain"] == "nonexistent.example.com"
    assert result["device_ids"] == []
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_hunt_ip_404_returns_not_found(mock_credentials, mock_settings):
    """Test HuntIpAction returns not_found on 404."""
    action = create_action(HuntIpAction, "HuntIp", mock_credentials, mock_settings)

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action, "_make_api_request", side_effect=_make_http_404_error()
        ):
            result = await action.execute(ip="192.0.2.1")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["ip"] == "192.0.2.1"
    assert result["device_ids"] == []
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_list_processes_404_returns_not_found(mock_credentials, mock_settings):
    """Test ListProcessesAction returns not_found on 404."""
    action = create_action(
        ListProcessesAction, "ListProcesses", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action, "_make_api_request", side_effect=_make_http_404_error()
        ):
            result = await action.execute(type="sha256", value="deadbeef")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["process_ids"] == []
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_file_reputation_404_returns_not_found(mock_credentials, mock_settings):
    """Test FileReputationAction returns not_found on 404."""
    action = create_action(
        FileReputationAction, "FileReputation", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action, "_make_api_request", side_effect=_make_http_404_error()
        ):
            result = await action.execute(hash="deadbeef5678")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["hash"] == "deadbeef5678"
    assert result["found"] is False


@pytest.mark.asyncio
async def test_url_reputation_404_returns_not_found(mock_credentials, mock_settings):
    """Test UrlReputationAction returns not_found on 404."""
    action = create_action(
        UrlReputationAction, "UrlReputation", mock_credentials, mock_settings
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action, "_make_api_request", side_effect=_make_http_404_error()
        ):
            result = await action.execute(url="https://nonexistent.example.com")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["url"] == "https://nonexistent.example.com"
    assert result["found"] is False


@pytest.mark.asyncio
async def test_check_detonation_status_404_returns_not_found(
    mock_credentials, mock_settings
):
    """Test CheckDetonationStatusAction returns not_found on 404."""
    action = create_action(
        CheckDetonationStatusAction,
        "CheckDetonationStatus",
        mock_credentials,
        mock_settings,
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(
            action, "_make_api_request", side_effect=_make_http_404_error()
        ):
            result = await action.execute(submission_ids=["nonexistent_sub"])

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["reports"] == []
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_non_404_http_error_still_returns_error(mock_credentials, mock_settings):
    """Test that non-404 HTTP errors still return error status."""
    action = create_action(
        QueryDeviceAction, "QueryDevice", mock_credentials, mock_settings
    )

    response = MagicMock()
    response.status_code = 500
    response.headers = {}
    response.text = "Internal Server Error"
    request = MagicMock()
    error = httpx.HTTPStatusError(
        "Internal Server Error", request=request, response=response
    )

    with patch.object(action, "_get_access_token", return_value="test_token"):
        with patch.object(action, "_make_api_request", side_effect=error):
            result = await action.execute(filter="hostname:'TEST'")

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPError"
    assert "not_found" not in result
