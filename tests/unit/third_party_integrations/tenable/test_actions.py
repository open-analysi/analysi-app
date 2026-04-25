"""Unit tests for Tenable.io integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.tenable.actions import (
    DeleteScanAction,
    HealthCheckAction,
    ListPoliciesAction,
    ListScannersAction,
    ListScansAction,
    ScanHostAction,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def health_check_action():
    """Create HealthCheckAction instance."""
    return HealthCheckAction(
        integration_id="tenable",
        action_id="health_check",
        settings={"timeout": 30},
        credentials={"access_key": "test-access-key", "secret_key": "test-secret-key"},
    )


@pytest.fixture
def list_scans_action():
    """Create ListScansAction instance."""
    return ListScansAction(
        integration_id="tenable",
        action_id="list_scans",
        settings={"timeout": 30},
        credentials={"access_key": "test-access-key", "secret_key": "test-secret-key"},
    )


@pytest.fixture
def list_scanners_action():
    """Create ListScannersAction instance."""
    return ListScannersAction(
        integration_id="tenable",
        action_id="list_scanners",
        settings={"timeout": 30},
        credentials={"access_key": "test-access-key", "secret_key": "test-secret-key"},
    )


@pytest.fixture
def list_policies_action():
    """Create ListPoliciesAction instance."""
    return ListPoliciesAction(
        integration_id="tenable",
        action_id="list_policies",
        settings={"timeout": 30},
        credentials={"access_key": "test-access-key", "secret_key": "test-secret-key"},
    )


@pytest.fixture
def scan_host_action():
    """Create ScanHostAction instance."""
    return ScanHostAction(
        integration_id="tenable",
        action_id="scan_host",
        settings={"timeout": 30},
        credentials={"access_key": "test-access-key", "secret_key": "test-secret-key"},
    )


@pytest.fixture
def delete_scan_action():
    """Create DeleteScanAction instance."""
    return DeleteScanAction(
        integration_id="tenable",
        action_id="delete_scan",
        settings={"timeout": 30},
        credentials={"access_key": "test-access-key", "secret_key": "test-secret-key"},
    )


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    mock_response = {
        "scans": [
            {"id": 1, "name": "Test Scan"},
            {"id": 2, "name": "Another Scan"},
        ]
    }

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = mock_response
    mock_http_response.content = b'{"scans": []}'

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True
    assert result["data"]["scan_count"] == 2


@pytest.mark.asyncio
async def test_health_check_missing_access_key():
    """Test health check with missing access key."""
    action = HealthCheckAction(
        integration_id="tenable",
        action_id="health_check",
        settings={"timeout": 30},
        credentials={"secret_key": "test-secret"},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "access key" in result["error"].lower()
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_missing_secret_key():
    """Test health check with missing secret key."""
    action = HealthCheckAction(
        integration_id="tenable",
        action_id="health_check",
        settings={"timeout": 30},
        credentials={"access_key": "test-access"},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "secret key" in result["error"].lower()
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_http_error(health_check_action):
    """Test health check with HTTP error."""

    import httpx

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Unauthorized",
            request=MagicMock(),
            response=mock_response,
        ),
    ):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPError"
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_timeout(health_check_action):
    """Test health check with timeout."""

    import httpx

    with patch.object(
        health_check_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Timed out"),
    ):
        result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "TimeoutError"
    assert result["data"]["healthy"] is False


# ============================================================================
# LIST SCANS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_scans_success(list_scans_action):
    """Test successful list scans."""
    mock_response = {
        "scans": [
            {"id": 1, "name": "Daily Scan", "status": "completed"},
            {"id": 2, "name": "Weekly Scan", "status": "running"},
        ]
    }

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = mock_response
    mock_http_response.content = b'{"scans": []}'

    with patch.object(
        list_scans_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await list_scans_action.execute()

    assert result["status"] == "success"
    assert result["summary"]["scan_count"] == 2
    assert len(result["scans"]) == 2


@pytest.mark.asyncio
async def test_list_scans_with_folder_filter(list_scans_action):
    """Test list scans with folder ID filter."""
    mock_response = {"scans": [{"id": 1, "name": "Scan", "folder_id": 4}]}

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = mock_response
    mock_http_response.content = b'{"scans": []}'

    with patch.object(
        list_scans_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await list_scans_action.execute(folder_id=4)

    assert result["status"] == "success"
    # Verify folder_id was passed in params


@pytest.mark.asyncio
async def test_list_scans_with_datetime_filter(list_scans_action):
    """Test list scans with datetime filter."""
    mock_response = {"scans": []}

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = mock_response
    mock_http_response.content = b'{"scans": []}'

    with patch.object(
        list_scans_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await list_scans_action.execute(last_modified="1648765291")

    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_list_scans_invalid_datetime(list_scans_action):
    """Test list scans with invalid datetime format."""
    result = await list_scans_action.execute(last_modified="invalid-date")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "datetime" in result["error"].lower()


@pytest.mark.asyncio
async def test_list_scans_missing_credentials():
    """Test list scans with missing credentials."""
    action = ListScansAction(
        integration_id="tenable",
        action_id="list_scans",
        settings={"timeout": 30},
        credentials={},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


# ============================================================================
# LIST SCANNERS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_scanners_success(list_scanners_action):
    """Test successful list scanners."""
    mock_response = {
        "scanners": [
            {"id": "uuid1", "name": "Cloud Scanner 1", "type": "pool"},
            {"id": "uuid2", "name": "Local Scanner", "type": "local"},
        ]
    }

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = mock_response
    mock_http_response.content = b'{"scanners": []}'

    with patch.object(
        list_scanners_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await list_scanners_action.execute()

    assert result["status"] == "success"
    assert result["summary"]["scanner_count"] == 2
    assert len(result["scanners"]) == 2


@pytest.mark.asyncio
async def test_list_scanners_missing_credentials():
    """Test list scanners with missing credentials."""
    action = ListScannersAction(
        integration_id="tenable",
        action_id="list_scanners",
        settings={"timeout": 30},
        credentials={"access_key": "test"},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


# ============================================================================
# LIST POLICIES TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_policies_success(list_policies_action):
    """Test successful list policies."""
    mock_response = {
        "policies": [
            {"id": 1, "name": "Basic Network Scan"},
            {"id": 2, "name": "Advanced Scan"},
        ]
    }

    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = mock_response
    mock_http_response.content = b'{"policies": []}'

    with patch.object(
        list_policies_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await list_policies_action.execute()

    assert result["status"] == "success"
    assert result["summary"]["policy_count"] == 2
    assert len(result["policies"]) == 2


@pytest.mark.asyncio
async def test_list_policies_http_error(list_policies_action):
    """Test list policies with HTTP error."""

    import httpx

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 403
    mock_response.text = "Forbidden"

    with patch.object(
        list_policies_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Forbidden",
            request=MagicMock(),
            response=mock_response,
        ),
    ):
        result = await list_policies_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPError"


# ============================================================================
# SCAN HOST TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_scan_host_success(scan_host_action):
    """Test successful scan host."""
    # Mock scan creation
    create_response = {"scan": {"id": 123}}

    # Mock scan status (completed)
    status_response = {"info": {"status": "completed"}}

    # Mock scan details
    details_response = {
        "hosts": [
            {
                "hostname": "192.168.1.100",
                "low": 2,
                "medium": 5,
                "high": 3,
                "critical": 1,
            }
        ]
    }

    # Mock responses
    create_mock = MagicMock()
    create_mock.json.return_value = create_response
    create_mock.raise_for_status = MagicMock()
    create_mock.content = b'{"scan": {"id": 123}}'

    launch_mock = MagicMock()
    launch_mock.json.return_value = {}
    launch_mock.raise_for_status = MagicMock()
    launch_mock.content = b"{}"

    status_mock = MagicMock()
    status_mock.json.return_value = status_response
    status_mock.raise_for_status = MagicMock()
    status_mock.content = b'{"info": {"status": "completed"}}'

    details_mock = MagicMock()
    details_mock.json.return_value = details_response
    details_mock.raise_for_status = MagicMock()
    details_mock.content = b'{"hosts": []}'

    # Set up side_effect for different calls:
    # 1. Create scan, 2. Launch scan, 3. Poll status, 4. Get details

    with patch.object(
        scan_host_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=[create_mock, launch_mock, status_mock, details_mock],
    ):
        # Also need to patch asyncio.sleep to avoid waiting
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await scan_host_action.execute(
                target_to_scan="192.168.1.100",
                policy_id=4,
                scan_timeout=120,
            )

    assert result["status"] == "success"
    assert result["summary"]["scan_id"] == 123
    assert result["summary"]["total_vulns"] == 11  # 2+5+3+1


@pytest.mark.asyncio
async def test_scan_host_missing_target(scan_host_action):
    """Test scan host with missing target."""
    result = await scan_host_action.execute(policy_id=4)

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "target" in result["error"].lower()


@pytest.mark.asyncio
async def test_scan_host_missing_policy_id(scan_host_action):
    """Test scan host with missing policy ID."""
    result = await scan_host_action.execute(target_to_scan="192.168.1.100")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "policy" in result["error"].lower()


@pytest.mark.asyncio
async def test_scan_host_invalid_timeout(scan_host_action):
    """Test scan host with invalid timeout value."""
    result = await scan_host_action.execute(
        target_to_scan="192.168.1.100",
        policy_id=4,
        scan_timeout=99999,  # Exceeds MAX_SCAN_TIMEOUT
    )

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "timeout" in result["error"].lower()


@pytest.mark.asyncio
async def test_scan_host_missing_credentials():
    """Test scan host with missing credentials."""
    action = ScanHostAction(
        integration_id="tenable",
        action_id="scan_host",
        settings={"timeout": 30},
        credentials={},
    )

    result = await action.execute(
        target_to_scan="192.168.1.100",
        policy_id=4,
    )

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


# ============================================================================
# DELETE SCAN TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_delete_scan_success(delete_scan_action):
    """Test successful delete scan."""
    mock_http_response = MagicMock(spec=httpx.Response)
    mock_http_response.json.return_value = {}
    mock_http_response.content = b""  # DELETE returns empty response

    with patch.object(
        delete_scan_action,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_http_response,
    ):
        result = await delete_scan_action.execute(scan_id=123)

    assert result["status"] == "success"
    assert result["summary"]["delete_status"] is True
    assert result["data"]["scan_id"] == 123


@pytest.mark.asyncio
async def test_delete_scan_missing_scan_id(delete_scan_action):
    """Test delete scan with missing scan ID."""
    result = await delete_scan_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "scan_id" in result["error"].lower()


@pytest.mark.asyncio
async def test_delete_scan_http_error(delete_scan_action):
    """Test delete scan with 404 returns success with not_found flag."""

    import httpx

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.text = "Not Found"

    with patch.object(
        delete_scan_action,
        "http_request",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError(
            "Not Found",
            request=MagicMock(),
            response=mock_response,
        ),
    ):
        result = await delete_scan_action.execute(scan_id=999)

    assert result["status"] == "success"
    assert result["not_found"] is True


@pytest.mark.asyncio
async def test_delete_scan_missing_credentials():
    """Test delete scan with missing credentials."""
    action = DeleteScanAction(
        integration_id="tenable",
        action_id="delete_scan",
        settings={"timeout": 30},
        credentials={"access_key": "test"},
    )

    result = await action.execute(scan_id=123)

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
