"""Unit tests for RSA Security Analytics integration actions."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.integrations.framework.integrations.rsa_security_analytics import (
    constants as consts,
)
from analysi.integrations.framework.integrations.rsa_security_analytics.actions import (
    HealthCheckAction,
    ListAlertsAction,
    ListDevicesAction,
    ListEventsAction,
    ListIncidentsAction,
)


@pytest.fixture
def credentials():
    """Fixture for valid credentials."""
    return {
        "username": "testuser",
        "password": "testpass",
    }


@pytest.fixture
def settings():
    """Fixture for valid settings."""
    return {
        "url": "https://rsa-sa.company.com",
        "incident_manager": "Test Incident Manager",
        "verify_ssl": False,
        "timeout": 30,
    }


@pytest.fixture
def health_check_action(credentials, settings):
    """Fixture for HealthCheckAction instance."""
    action = HealthCheckAction(
        integration_id="test-rsa",
        action_id="health_check",
        settings=settings,
        credentials=credentials,
        ctx={"tenant_id": "test-tenant"},
    )
    return action


@pytest.fixture
def list_incidents_action(credentials, settings):
    """Fixture for ListIncidentsAction instance."""
    action = ListIncidentsAction(
        integration_id="test-rsa",
        action_id="list_incidents",
        settings=settings,
        credentials=credentials,
        ctx={"tenant_id": "test-tenant"},
    )
    return action


@pytest.fixture
def list_alerts_action(credentials, settings):
    """Fixture for ListAlertsAction instance."""
    action = ListAlertsAction(
        integration_id="test-rsa",
        action_id="list_alerts",
        settings=settings,
        credentials=credentials,
        ctx={"tenant_id": "test-tenant"},
    )
    return action


@pytest.fixture
def list_events_action(credentials, settings):
    """Fixture for ListEventsAction instance."""
    action = ListEventsAction(
        integration_id="test-rsa",
        action_id="list_events",
        settings=settings,
        credentials=credentials,
        ctx={"tenant_id": "test-tenant"},
    )
    return action


@pytest.fixture
def list_devices_action(credentials, settings):
    """Fixture for ListDevicesAction instance."""
    action = ListDevicesAction(
        integration_id="test-rsa",
        action_id="list_devices",
        settings=settings,
        credentials=credentials,
        ctx={"tenant_id": "test-tenant"},
    )
    return action


def _login_response():
    """Create a mock login response with CSRF token and session ID."""
    resp = MagicMock()
    resp.text = (
        '<meta name="csrf-token" content="abc123-csrf-token-xyz789012345678901234">'
    )
    resp.cookies.get.return_value = "test-session-id"
    resp.raise_for_status = MagicMock()
    return resp


def _devices_response():
    """Create a mock devices response with incident manager."""
    resp = MagicMock()
    resp.json.return_value = {
        "success": True,
        "data": [{"displayName": "Test Incident Manager", "id": "12345"}],
    }
    resp.raise_for_status = MagicMock()
    return resp


def _logout_response():
    """Create a mock logout response."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    return resp


# HealthCheckAction Tests


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check."""
    # Health check: login -> get_incident_manager_id (devices) -> logout
    health_check_action.http_request = AsyncMock(
        side_effect=[_login_response(), _devices_response(), _logout_response()]
    )
    result = await health_check_action.execute()

    assert result["status"] == consts.STATUS_SUCCESS
    assert "successful" in result["message"].lower()


@pytest.mark.asyncio
async def test_health_check_missing_credentials(health_check_action):
    """Test health check with missing credentials."""
    health_check_action.credentials = {}

    result = await health_check_action.execute()

    assert result["status"] == consts.STATUS_ERROR
    assert result["error_type"] == consts.ERROR_TYPE_CONFIGURATION
    assert consts.MSG_MISSING_CREDENTIALS in result["error"]


@pytest.mark.asyncio
async def test_health_check_missing_incident_manager(health_check_action):
    """Test health check with missing incident manager setting."""
    health_check_action.settings = {
        "url": "https://rsa-sa.company.com",
        "verify_ssl": False,
    }

    result = await health_check_action.execute()

    assert result["status"] == consts.STATUS_ERROR
    assert result["error_type"] == consts.ERROR_TYPE_CONFIGURATION
    assert consts.MSG_MISSING_INCIDENT_MANAGER in result["error"]


@pytest.mark.asyncio
async def test_health_check_csrf_token_not_found(health_check_action):
    """Test health check when CSRF token not found."""
    mock_login_response = MagicMock()
    mock_login_response.text = "<html>No CSRF token here</html>"
    mock_login_response.cookies.get.return_value = "test-session-id"
    mock_login_response.raise_for_status = MagicMock()

    health_check_action.http_request = AsyncMock(return_value=mock_login_response)
    result = await health_check_action.execute()

    assert result["status"] == consts.STATUS_ERROR
    assert consts.MSG_CSRF_TOKEN_NOT_FOUND in result["error"]


@pytest.mark.asyncio
async def test_health_check_session_id_missing(health_check_action):
    """Test health check when session ID cookie is missing."""
    mock_login_response = MagicMock()
    mock_login_response.text = (
        '<meta name="csrf-token" content="abc123-csrf-token-xyz789012345678901234">'
    )
    mock_login_response.cookies.get.return_value = None  # No session ID
    mock_login_response.raise_for_status = MagicMock()

    health_check_action.http_request = AsyncMock(return_value=mock_login_response)
    result = await health_check_action.execute()

    assert result["status"] == consts.STATUS_ERROR
    assert consts.MSG_SESSION_ID_MISSING in result["error"]


# ListIncidentsAction Tests


@pytest.mark.asyncio
async def test_list_incidents_success(list_incidents_action):
    """Test successful list incidents."""
    mock_incidents_response = MagicMock()
    mock_incidents_response.json.return_value = {
        "success": True,
        "data": [
            {"id": "INC-001", "name": "Security Incident 1", "status": "Open"},
            {"id": "INC-002", "name": "Security Incident 2", "status": "Closed"},
        ],
    }
    mock_incidents_response.raise_for_status = MagicMock()

    # Sequence: login -> get_devices -> get_incidents -> logout
    list_incidents_action.http_request = AsyncMock(
        side_effect=[
            _login_response(),
            _devices_response(),
            mock_incidents_response,
            _logout_response(),
        ]
    )
    result = await list_incidents_action.execute(limit=100)

    assert result["status"] == consts.STATUS_SUCCESS
    assert result["num_incidents"] == 2
    assert len(result["incidents"]) == 2
    assert result["incidents"][0]["id"] == "INC-001"


@pytest.mark.asyncio
async def test_list_incidents_missing_credentials(list_incidents_action):
    """Test list incidents with missing credentials."""
    list_incidents_action.credentials = {}

    result = await list_incidents_action.execute()

    assert result["status"] == consts.STATUS_ERROR
    assert result["error_type"] == consts.ERROR_TYPE_CONFIGURATION


@pytest.mark.asyncio
async def test_list_incidents_invalid_time_format(list_incidents_action):
    """Test list incidents with invalid time format."""
    # login is called before time validation fails for RSA
    list_incidents_action.http_request = AsyncMock(return_value=_login_response())
    result = await list_incidents_action.execute(start_time="invalid-format")

    assert result["status"] == consts.STATUS_ERROR
    assert result["error_type"] == consts.ERROR_TYPE_VALIDATION


# ListAlertsAction Tests


@pytest.mark.asyncio
async def test_list_alerts_success(list_alerts_action):
    """Test successful list alerts."""
    mock_alerts_response = MagicMock()
    mock_alerts_response.json.return_value = {
        "success": True,
        "total": 2,
        "data": [
            {"id": "ALERT-001", "name": "Malware Detected", "severity": 8},
            {"id": "ALERT-002", "name": "Suspicious Login", "severity": 6},
        ],
    }
    mock_alerts_response.raise_for_status = MagicMock()

    # Sequence: login -> get_devices -> get_alerts -> logout
    list_alerts_action.http_request = AsyncMock(
        side_effect=[
            _login_response(),
            _devices_response(),
            mock_alerts_response,
            _logout_response(),
        ]
    )
    result = await list_alerts_action.execute(id="INC-001", limit=100)

    assert result["status"] == consts.STATUS_SUCCESS
    assert result["num_alerts"] == 2
    assert len(result["alerts"]) == 2
    assert result["alerts"][0]["id"] == "ALERT-001"


@pytest.mark.asyncio
async def test_list_alerts_missing_credentials(list_alerts_action):
    """Test list alerts with missing credentials."""
    list_alerts_action.credentials = {}

    result = await list_alerts_action.execute()

    assert result["status"] == consts.STATUS_ERROR
    assert result["error_type"] == consts.ERROR_TYPE_CONFIGURATION


# ListEventsAction Tests


@pytest.mark.asyncio
async def test_list_events_success(list_events_action):
    """Test successful list events."""
    mock_events_response = MagicMock()
    mock_events_response.json.return_value = {
        "success": True,
        "total": 2,
        "data": [
            {"id": "EVENT-001", "type": "network", "timestamp": "2026-04-26T12:00:00Z"},
            {"id": "EVENT-002", "type": "process", "timestamp": "2026-04-26T12:01:00Z"},
        ],
    }
    mock_events_response.raise_for_status = MagicMock()

    # Sequence: login -> get_devices -> get_events -> logout
    list_events_action.http_request = AsyncMock(
        side_effect=[
            _login_response(),
            _devices_response(),
            mock_events_response,
            _logout_response(),
        ]
    )
    result = await list_events_action.execute(id="ALERT-001", limit=100)

    assert result["status"] == consts.STATUS_SUCCESS
    assert result["num_events"] == 2
    assert len(result["events"]) == 2
    assert result["events"][0]["id"] == "EVENT-001"


@pytest.mark.asyncio
async def test_list_events_missing_alert_id(list_events_action):
    """Test list events with missing alert ID."""
    result = await list_events_action.execute()

    assert result["status"] == consts.STATUS_ERROR
    assert result["error_type"] == consts.ERROR_TYPE_VALIDATION
    assert "id" in result["error"].lower()


@pytest.mark.asyncio
async def test_list_events_missing_credentials(list_events_action):
    """Test list events with missing credentials."""
    list_events_action.credentials = {}

    result = await list_events_action.execute(id="ALERT-001")

    assert result["status"] == consts.STATUS_ERROR
    assert result["error_type"] == consts.ERROR_TYPE_CONFIGURATION


# ListDevicesAction Tests


@pytest.mark.asyncio
async def test_list_devices_success(list_devices_action):
    """Test successful list devices."""
    mock_devices_response = MagicMock()
    mock_devices_response.json.return_value = {
        "success": True,
        "data": [
            {"id": "1", "displayName": "Device 1", "deviceType": "BROKER"},
            {"id": "2", "displayName": "Device 2", "deviceType": "CONCENTRATOR"},
        ],
    }
    mock_devices_response.raise_for_status = MagicMock()

    # Sequence: login -> get_devices -> logout
    list_devices_action.http_request = AsyncMock(
        side_effect=[_login_response(), mock_devices_response, _logout_response()]
    )
    result = await list_devices_action.execute()

    assert result["status"] == consts.STATUS_SUCCESS
    assert result["num_devices"] == 2
    assert len(result["devices"]) == 2
    assert result["devices"][0]["displayName"] == "Device 1"


@pytest.mark.asyncio
async def test_list_devices_missing_credentials(list_devices_action):
    """Test list devices with missing credentials."""
    list_devices_action.credentials = {}

    result = await list_devices_action.execute()

    assert result["status"] == consts.STATUS_ERROR
    assert result["error_type"] == consts.ERROR_TYPE_CONFIGURATION


@pytest.mark.asyncio
async def test_list_devices_http_error(list_devices_action):
    """Test list devices with HTTP error."""
    from httpx import HTTPStatusError, Request, Response

    mock_response = MagicMock(spec=Response)
    mock_response.status_code = 500
    mock_request = MagicMock(spec=Request)

    # Login succeeds, then get_devices fails with HTTP error
    list_devices_action.http_request = AsyncMock(
        side_effect=[
            _login_response(),
            HTTPStatusError(
                "Server Error", request=mock_request, response=mock_response
            ),
        ]
    )
    result = await list_devices_action.execute()

    assert result["status"] == consts.STATUS_ERROR
    assert result["error_type"] == consts.ERROR_TYPE_HTTP
