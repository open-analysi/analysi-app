"""Unit tests for Microsoft Defender for Endpoint integration actions."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.integrations.framework.integrations.defender_endpoint.actions import (
    HealthCheckAction,
    IsolateDeviceAction,
    ListAlertsAction,
    ListDevicesAction,
    QuarantineFileAction,
    ReleaseDeviceAction,
    RunAdvancedQueryAction,
    ScanDeviceAction,
)


@pytest.fixture
def mock_credentials():
    """Mock credentials for Defender API."""
    return {
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
    }


@pytest.fixture
def mock_settings():
    """Mock settings for Defender integration."""
    return {
        "tenant_id": "test-tenant-id",
        "timeout": 30,
        "environment": "Public",
    }


@pytest.fixture
def health_check_action(mock_credentials, mock_settings):
    """Create HealthCheckAction instance."""
    return HealthCheckAction(
        integration_id="defender_endpoint",
        action_id="health_check",
        settings=mock_settings,
        credentials=mock_credentials,
    )


@pytest.fixture
def isolate_device_action(mock_credentials, mock_settings):
    """Create IsolateDeviceAction instance."""
    return IsolateDeviceAction(
        integration_id="defender_endpoint",
        action_id="isolate_device",
        settings=mock_settings,
        credentials=mock_credentials,
    )


@pytest.fixture
def release_device_action(mock_credentials, mock_settings):
    """Create ReleaseDeviceAction instance."""
    return ReleaseDeviceAction(
        integration_id="defender_endpoint",
        action_id="release_device",
        settings=mock_settings,
        credentials=mock_credentials,
    )


@pytest.fixture
def scan_device_action(mock_credentials, mock_settings):
    """Create ScanDeviceAction instance."""
    return ScanDeviceAction(
        integration_id="defender_endpoint",
        action_id="scan_device",
        settings=mock_settings,
        credentials=mock_credentials,
    )


@pytest.fixture
def quarantine_file_action(mock_credentials, mock_settings):
    """Create QuarantineFileAction instance."""
    return QuarantineFileAction(
        integration_id="defender_endpoint",
        action_id="quarantine_file",
        settings=mock_settings,
        credentials=mock_credentials,
    )


@pytest.fixture
def list_devices_action(mock_credentials, mock_settings):
    """Create ListDevicesAction instance."""
    return ListDevicesAction(
        integration_id="defender_endpoint",
        action_id="list_devices",
        settings=mock_settings,
        credentials=mock_credentials,
    )


@pytest.fixture
def list_alerts_action(mock_credentials, mock_settings):
    """Create ListAlertsAction instance."""
    return ListAlertsAction(
        integration_id="defender_endpoint",
        action_id="list_alerts",
        settings=mock_settings,
        credentials=mock_credentials,
    )


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    mock_token_response = MagicMock()
    mock_token_response.json.return_value = {"access_token": "test-token"}
    mock_token_response.raise_for_status = MagicMock()

    mock_api_response = MagicMock()
    mock_api_response.json.return_value = {"value": [{"id": "device1"}]}
    mock_api_response.raise_for_status = MagicMock()

    health_check_action.http_request = AsyncMock(
        side_effect=[mock_token_response, mock_api_response]
    )
    result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["data"]["healthy"] is True
    assert result["data"]["environment"] == "Public"


@pytest.mark.asyncio
async def test_health_check_missing_credentials():
    """Test health check with missing credentials."""
    action = HealthCheckAction(
        integration_id="defender_endpoint",
        action_id="health_check",
        settings={"timeout": 30},
        credentials={},
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert "Missing required credentials" in result["error"]
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_health_check_token_failure(health_check_action):
    """Test health check with token acquisition failure."""
    health_check_action.http_request = AsyncMock(side_effect=Exception("Token failed"))
    result = await health_check_action.execute()

    assert result["status"] == "error"
    assert "Failed to acquire access token" in result["error"]


# ============================================================================
# ISOLATE DEVICE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_isolate_device_success(isolate_device_action):
    """Test successful device isolation."""
    mock_token_response = MagicMock()
    mock_token_response.json.return_value = {"access_token": "test-token"}
    mock_token_response.raise_for_status = MagicMock()

    mock_api_response = MagicMock()
    mock_api_response.json.return_value = {
        "id": "action-123",
        "status": "Pending",
        "type": "Isolate",
    }
    mock_api_response.raise_for_status = MagicMock()

    isolate_device_action.http_request = AsyncMock(
        side_effect=[mock_token_response, mock_api_response]
    )
    result = await isolate_device_action.execute(
        device_id="device-123", comment="Test isolation", isolation_type="Full"
    )

    assert result["status"] == "success"
    assert result["device_id"] == "device-123"
    assert result["action_id"] == "action-123"
    assert result["isolation_type"] == "Full"


@pytest.mark.asyncio
async def test_isolate_device_missing_device_id(isolate_device_action):
    """Test device isolation with missing device_id."""
    result = await isolate_device_action.execute(comment="Test")

    assert result["status"] == "error"
    assert "Missing required parameter 'device_id'" in result["error"]
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_isolate_device_missing_comment(isolate_device_action):
    """Test device isolation with missing comment."""
    result = await isolate_device_action.execute(device_id="device-123")

    assert result["status"] == "error"
    assert "Missing required parameter 'comment'" in result["error"]
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_isolate_device_invalid_isolation_type(isolate_device_action):
    """Test device isolation with invalid isolation type."""
    result = await isolate_device_action.execute(
        device_id="device-123", comment="Test", isolation_type="Invalid"
    )

    assert result["status"] == "error"
    assert "Invalid isolation_type" in result["error"]
    assert result["error_type"] == "ValidationError"


# ============================================================================
# RELEASE DEVICE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_release_device_success(release_device_action):
    """Test successful device release."""
    mock_token_response = MagicMock()
    mock_token_response.json.return_value = {"access_token": "test-token"}
    mock_token_response.raise_for_status = MagicMock()

    mock_api_response = MagicMock()
    mock_api_response.json.return_value = {
        "id": "action-456",
        "status": "Pending",
        "type": "Unisolate",
    }
    mock_api_response.raise_for_status = MagicMock()

    release_device_action.http_request = AsyncMock(
        side_effect=[mock_token_response, mock_api_response]
    )
    result = await release_device_action.execute(
        device_id="device-123", comment="Test release"
    )

    assert result["status"] == "success"
    assert result["device_id"] == "device-123"
    assert result["action_id"] == "action-456"


# ============================================================================
# SCAN DEVICE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_scan_device_success(scan_device_action):
    """Test successful device scan."""
    mock_token_response = MagicMock()
    mock_token_response.json.return_value = {"access_token": "test-token"}
    mock_token_response.raise_for_status = MagicMock()

    mock_api_response = MagicMock()
    mock_api_response.json.return_value = {
        "id": "action-789",
        "status": "Pending",
        "type": "RunAntiVirusScan",
    }
    mock_api_response.raise_for_status = MagicMock()

    scan_device_action.http_request = AsyncMock(
        side_effect=[mock_token_response, mock_api_response]
    )
    result = await scan_device_action.execute(
        device_id="device-123", comment="Test scan", scan_type="Quick"
    )

    assert result["status"] == "success"
    assert result["device_id"] == "device-123"
    assert result["action_id"] == "action-789"
    assert result["scan_type"] == "Quick"


@pytest.mark.asyncio
async def test_scan_device_invalid_scan_type(scan_device_action):
    """Test device scan with invalid scan type."""
    result = await scan_device_action.execute(
        device_id="device-123", comment="Test", scan_type="Invalid"
    )

    assert result["status"] == "error"
    assert "Invalid scan_type" in result["error"]
    assert result["error_type"] == "ValidationError"


# ============================================================================
# QUARANTINE FILE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_quarantine_file_success(quarantine_file_action):
    """Test successful file quarantine."""
    mock_token_response = MagicMock()
    mock_token_response.json.return_value = {"access_token": "test-token"}
    mock_token_response.raise_for_status = MagicMock()

    mock_api_response = MagicMock()
    mock_api_response.json.return_value = {
        "id": "action-999",
        "status": "Pending",
        "type": "StopAndQuarantineFile",
    }
    mock_api_response.raise_for_status = MagicMock()

    quarantine_file_action.http_request = AsyncMock(
        side_effect=[mock_token_response, mock_api_response]
    )
    result = await quarantine_file_action.execute(
        device_id="device-123",
        file_hash="abc123def456",
        comment="Test quarantine",
    )

    assert result["status"] == "success"
    assert result["device_id"] == "device-123"
    assert result["file_hash"] == "abc123def456"
    assert result["action_id"] == "action-999"


@pytest.mark.asyncio
async def test_quarantine_file_missing_file_hash(quarantine_file_action):
    """Test file quarantine with missing file hash."""
    result = await quarantine_file_action.execute(
        device_id="device-123", comment="Test"
    )

    assert result["status"] == "error"
    assert "Missing required parameter 'file_hash'" in result["error"]
    assert result["error_type"] == "ValidationError"


# ============================================================================
# LIST DEVICES TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_devices_success(list_devices_action):
    """Test successful device listing."""
    mock_token_response = MagicMock()
    mock_token_response.json.return_value = {"access_token": "test-token"}
    mock_token_response.raise_for_status = MagicMock()

    mock_api_response = MagicMock()
    mock_api_response.json.return_value = {
        "value": [
            {"id": "device1", "computerDnsName": "computer1"},
            {"id": "device2", "computerDnsName": "computer2"},
        ]
    }
    mock_api_response.raise_for_status = MagicMock()

    list_devices_action.http_request = AsyncMock(
        side_effect=[mock_token_response, mock_api_response]
    )
    result = await list_devices_action.execute(limit=2)

    assert result["status"] == "success"
    assert result["device_count"] == 2
    assert len(result["devices"]) == 2
    assert result["devices"][0]["id"] == "device1"


# ============================================================================
# LIST ALERTS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_alerts_success(list_alerts_action):
    """Test successful alert listing."""
    mock_token_response = MagicMock()
    mock_token_response.json.return_value = {"access_token": "test-token"}
    mock_token_response.raise_for_status = MagicMock()

    mock_api_response = MagicMock()
    mock_api_response.json.return_value = {
        "value": [
            {"id": "alert1", "status": "New", "severity": "High"},
            {"id": "alert2", "status": "InProgress", "severity": "Medium"},
        ]
    }
    mock_api_response.raise_for_status = MagicMock()

    list_alerts_action.http_request = AsyncMock(
        side_effect=[mock_token_response, mock_api_response]
    )
    result = await list_alerts_action.execute(limit=2)

    assert result["status"] == "success"
    assert result["alert_count"] == 2
    assert len(result["alerts"]) == 2
    assert result["alerts"][0]["id"] == "alert1"


@pytest.mark.asyncio
async def test_list_alerts_with_status_filter(list_alerts_action):
    """Test alert listing with status filter."""
    mock_token_response = MagicMock()
    mock_token_response.json.return_value = {"access_token": "test-token"}
    mock_token_response.raise_for_status = MagicMock()

    mock_api_response = MagicMock()
    mock_api_response.json.return_value = {
        "value": [{"id": "alert1", "status": "New", "severity": "High"}]
    }
    mock_api_response.raise_for_status = MagicMock()

    list_alerts_action.http_request = AsyncMock(
        side_effect=[mock_token_response, mock_api_response]
    )
    result = await list_alerts_action.execute(limit=10, status="New")

    assert result["status"] == "success"
    assert result["alert_count"] == 1


@pytest.mark.asyncio
async def test_list_alerts_invalid_status(list_alerts_action):
    """Test alert listing with invalid status."""
    result = await list_alerts_action.execute(status="InvalidStatus")

    assert result["status"] == "error"
    assert "Invalid status" in result["error"]
    assert result["error_type"] == "ValidationError"


# ============================================================================
# ADVANCED QUERY TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_run_advanced_query_success():
    """Test successful advanced query execution."""
    action = RunAdvancedQueryAction(
        integration_id="defender_endpoint",
        action_id="run_advanced_query",
        settings={"tenant_id": "test-tenant", "timeout": 30, "environment": "Public"},
        credentials={
            "client_id": "test-client",
            "client_secret": "test-secret",
        },
    )

    mock_token_response = MagicMock()
    mock_token_response.json.return_value = {"access_token": "test-token"}
    mock_token_response.raise_for_status = MagicMock()

    mock_api_response = MagicMock()
    mock_api_response.json.return_value = {
        "Results": [{"DeviceName": "device1", "EventCount": 10}]
    }
    mock_api_response.raise_for_status = MagicMock()

    action.http_request = AsyncMock(
        side_effect=[mock_token_response, mock_api_response]
    )
    result = await action.execute(
        query="DeviceEvents | where Timestamp > ago(1h) | summarize count() by DeviceName"
    )

    assert result["status"] == "success"
    assert result["result_count"] == 1
    assert len(result["results"]) == 1


@pytest.mark.asyncio
async def test_run_advanced_query_missing_query():
    """Test advanced query with missing query parameter."""
    action = RunAdvancedQueryAction(
        integration_id="defender_endpoint",
        action_id="run_advanced_query",
        settings={"tenant_id": "test-tenant", "timeout": 30},
        credentials={
            "client_id": "test-client",
            "client_secret": "test-secret",
        },
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert "Missing required parameter 'query'" in result["error"]
    assert result["error_type"] == "ValidationError"


# ============================================================================
# HTTP ERROR TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_isolate_device_http_error(isolate_device_action):
    """Test device isolation with HTTP error."""
    import httpx

    mock_token_response = MagicMock()
    mock_token_response.json.return_value = {"access_token": "test-token"}
    mock_token_response.raise_for_status = MagicMock()

    mock_error_response = MagicMock()
    mock_error_response.status_code = 403
    mock_error_response.text = "Forbidden"

    isolate_device_action.http_request = AsyncMock(
        side_effect=[
            mock_token_response,
            httpx.HTTPStatusError(
                "Forbidden", request=MagicMock(), response=mock_error_response
            ),
        ]
    )
    result = await isolate_device_action.execute(device_id="device-123", comment="Test")

    assert result["status"] == "error"
    assert "Access forbidden" in result["error"]
