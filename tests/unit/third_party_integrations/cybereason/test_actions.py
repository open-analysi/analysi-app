"""Unit tests for Cybereason EDR integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.cybereason.actions import (
    GetSensorStatusAction,
    HealthCheckAction,
    IsolateMachineAction,
    KillProcessAction,
    QuarantineDeviceAction,
    QueryMachinesAction,
    QueryProcessesAction,
    SetReputationAction,
    UnisolateMachineAction,
    UnquarantineDeviceAction,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_credentials():
    """Mock Cybereason credentials."""
    return {
        "username": "test_user",
        "password": "test_pass",
    }


@pytest.fixture
def mock_settings():
    """Mock integration settings."""
    return {
        "base_url": "https://cybereason.example.com:8443",
        "timeout": 60,
        "verify_ssl": False,
    }


def create_action(
    action_class,
    action_id="test_action",
    credentials=None,
    settings=None,
):
    """Helper to create action instances with required parameters."""
    return action_class(
        integration_id="cybereason",
        action_id=action_id,
        credentials=credentials or {},
        settings=settings or {},
    )


def _mock_login_response(session_id="test-session-id"):
    """Create a mock login response with JSESSIONID cookie."""
    resp = MagicMock()
    resp.status_code = 200
    resp.cookies = httpx.Cookies()
    resp.cookies.set("JSESSIONID", session_id)
    resp.raise_for_status = MagicMock()
    return resp


def _mock_json_response(data, status_code=200):
    """Create a mock JSON response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


# ============================================================================
# HealthCheckAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(mock_credentials, mock_settings):
    """Test successful health check with valid credentials."""
    action = create_action(
        HealthCheckAction, "health_check", mock_credentials, mock_settings
    )

    login_resp = _mock_login_response()
    action.http_request = AsyncMock(return_value=login_resp)

    result = await action.execute()

    assert result["status"] == "success"
    assert "integration_id" in result
    assert result["data"]["healthy"] is True
    assert result["data"]["session_established"] is True


@pytest.mark.asyncio
async def test_health_check_missing_credentials():
    """Test health check with missing credentials."""
    action = create_action(HealthCheckAction, "health_check")

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "integration_id" in result
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_auth_failure(mock_credentials, mock_settings):
    """Test health check when authentication fails (no session cookie)."""
    action = create_action(
        HealthCheckAction, "health_check", mock_credentials, mock_settings
    )

    # Login response without JSESSIONID cookie
    resp = MagicMock()
    resp.status_code = 200
    resp.cookies = httpx.Cookies()  # Empty cookies
    resp.raise_for_status = MagicMock()
    action.http_request = AsyncMock(return_value=resp)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "AuthenticationError"
    assert "integration_id" in result
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_connection_error(mock_credentials, mock_settings):
    """Test health check when connection fails."""
    action = create_action(
        HealthCheckAction, "health_check", mock_credentials, mock_settings
    )

    action.http_request = AsyncMock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    result = await action.execute()

    # Login returns None on exception -> auth failure
    assert result["status"] == "error"
    assert result["error_type"] == "AuthenticationError"
    assert "integration_id" in result


# ============================================================================
# IsolateMachineAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_isolate_machine_success(mock_credentials, mock_settings):
    """Test successful machine isolation by malop ID."""
    action = create_action(
        IsolateMachineAction, "isolate_machine", mock_credentials, mock_settings
    )

    login_resp = _mock_login_response()
    # Visual search returns machines with pylumId
    sensor_resp = _mock_json_response(
        {
            "data": {
                "resultIdToElementDataMap": {
                    "machine-1": {
                        "simpleValues": {
                            "pylumId": {"values": ["sensor-abc123"]},
                            "elementDisplayName": {"values": ["WORKSTATION-1"]},
                        },
                    }
                }
            }
        }
    )
    isolate_resp = _mock_json_response({})

    action.http_request = AsyncMock(side_effect=[login_resp, sensor_resp, isolate_resp])

    result = await action.execute(malop_id="malop-123")

    assert result["status"] == "success"
    assert "integration_id" in result
    assert result["data"]["malop_id"] == "malop-123"
    assert "sensor-abc123" in result["data"]["sensor_ids"]


@pytest.mark.asyncio
async def test_isolate_machine_missing_malop_id(mock_credentials, mock_settings):
    """Test isolation with missing malop_id."""
    action = create_action(
        IsolateMachineAction, "isolate_machine", mock_credentials, mock_settings
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "malop_id" in result["error"]
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_isolate_machine_missing_credentials():
    """Test isolation with missing credentials."""
    action = create_action(IsolateMachineAction, "isolate_machine")

    result = await action.execute(malop_id="malop-123")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_isolate_machine_no_sensors(mock_credentials, mock_settings):
    """Test isolation when no sensors found for malop."""
    action = create_action(
        IsolateMachineAction, "isolate_machine", mock_credentials, mock_settings
    )

    login_resp = _mock_login_response()
    # Visual search returns empty machine map
    sensor_resp = _mock_json_response({"data": {"resultIdToElementDataMap": {}}})

    action.http_request = AsyncMock(side_effect=[login_resp, sensor_resp])

    result = await action.execute(malop_id="malop-999")

    assert result["status"] == "error"
    assert "No sensor IDs" in result["error"]
    assert "integration_id" in result


# ============================================================================
# UnisolateMachineAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_unisolate_machine_success(mock_credentials, mock_settings):
    """Test successful machine un-isolation by malop ID."""
    action = create_action(
        UnisolateMachineAction, "unisolate_machine", mock_credentials, mock_settings
    )

    login_resp = _mock_login_response()
    sensor_resp = _mock_json_response(
        {
            "data": {
                "resultIdToElementDataMap": {
                    "machine-1": {
                        "simpleValues": {
                            "pylumId": {"values": ["sensor-abc123"]},
                            "elementDisplayName": {"values": ["WORKSTATION-1"]},
                        },
                    }
                }
            }
        }
    )
    unisolate_resp = _mock_json_response({})

    action.http_request = AsyncMock(
        side_effect=[login_resp, sensor_resp, unisolate_resp]
    )

    result = await action.execute(malop_id="malop-123")

    assert result["status"] == "success"
    assert "integration_id" in result
    assert result["data"]["malop_id"] == "malop-123"


@pytest.mark.asyncio
async def test_unisolate_machine_missing_malop_id(mock_credentials, mock_settings):
    """Test un-isolation with missing malop_id."""
    action = create_action(
        UnisolateMachineAction, "unisolate_machine", mock_credentials, mock_settings
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "integration_id" in result


# ============================================================================
# QuarantineDeviceAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_quarantine_device_success(mock_credentials, mock_settings):
    """Test successful device quarantine by machine name/IP."""
    action = create_action(
        QuarantineDeviceAction,
        "quarantine_device",
        mock_credentials,
        mock_settings,
    )

    login_resp = _mock_login_response()
    # Sensor query by name returns a sensor
    sensor_by_name_resp = _mock_json_response(
        {
            "totalResults": 1,
            "sensors": [{"pylumId": "sensor-xyz789"}],
        }
    )
    # Sensor query by IP returns no results
    sensor_by_ip_resp = _mock_json_response({"totalResults": 0, "sensors": []})
    isolate_resp = _mock_json_response({"result": "ok"})

    action.http_request = AsyncMock(
        side_effect=[login_resp, sensor_by_name_resp, sensor_by_ip_resp, isolate_resp]
    )

    result = await action.execute(machine_name_or_ip="WORKSTATION-1")

    assert result["status"] == "success"
    assert "integration_id" in result
    assert result["data"]["machine_name_or_ip"] == "WORKSTATION-1"
    assert "sensor-xyz789" in result["data"]["sensor_ids"]


@pytest.mark.asyncio
async def test_quarantine_device_missing_param(mock_credentials, mock_settings):
    """Test quarantine with missing machine_name_or_ip."""
    action = create_action(
        QuarantineDeviceAction, "quarantine_device", mock_credentials, mock_settings
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "machine_name_or_ip" in result["error"]
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_quarantine_device_no_sensors(mock_credentials, mock_settings):
    """Test quarantine when no sensors found."""
    action = create_action(
        QuarantineDeviceAction,
        "quarantine_device",
        mock_credentials,
        mock_settings,
    )

    login_resp = _mock_login_response()
    sensor_by_name_resp = _mock_json_response({"totalResults": 0, "sensors": []})
    sensor_by_ip_resp = _mock_json_response({"totalResults": 0, "sensors": []})

    action.http_request = AsyncMock(
        side_effect=[login_resp, sensor_by_name_resp, sensor_by_ip_resp]
    )

    result = await action.execute(machine_name_or_ip="nonexistent")

    assert result["status"] == "error"
    assert "No sensor IDs" in result["error"]
    assert "integration_id" in result


# ============================================================================
# UnquarantineDeviceAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_unquarantine_device_success(mock_credentials, mock_settings):
    """Test successful device un-quarantine."""
    action = create_action(
        UnquarantineDeviceAction,
        "unquarantine_device",
        mock_credentials,
        mock_settings,
    )

    login_resp = _mock_login_response()
    sensor_by_name_resp = _mock_json_response(
        {"totalResults": 1, "sensors": [{"pylumId": "sensor-xyz789"}]}
    )
    sensor_by_ip_resp = _mock_json_response({"totalResults": 0, "sensors": []})
    unisolate_resp = _mock_json_response({"result": "ok"})

    action.http_request = AsyncMock(
        side_effect=[login_resp, sensor_by_name_resp, sensor_by_ip_resp, unisolate_resp]
    )

    result = await action.execute(machine_name_or_ip="WORKSTATION-1")

    assert result["status"] == "success"
    assert "integration_id" in result
    assert result["data"]["machine_name_or_ip"] == "WORKSTATION-1"


@pytest.mark.asyncio
async def test_unquarantine_device_missing_param(mock_credentials, mock_settings):
    """Test un-quarantine with missing parameter."""
    action = create_action(
        UnquarantineDeviceAction,
        "unquarantine_device",
        mock_credentials,
        mock_settings,
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "integration_id" in result


# ============================================================================
# QueryProcessesAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_query_processes_success(mock_credentials, mock_settings):
    """Test successful process query for a malop."""
    action = create_action(
        QueryProcessesAction,
        "query_processes",
        mock_credentials,
        mock_settings,
    )

    login_resp = _mock_login_response()
    search_resp = _mock_json_response(
        {
            "data": {
                "resultIdToElementDataMap": {
                    "proc-1": {
                        "simpleValues": {
                            "elementDisplayName": {"values": ["chrome.exe"]},
                        },
                        "elementValues": {
                            "ownerMachine": {
                                "elementValues": [
                                    {"guid": "machine-1", "name": "DESKTOP-ABC"}
                                ]
                            }
                        },
                    },
                    "proc-2": {
                        "simpleValues": {
                            "elementDisplayName": {"values": ["explorer.exe"]},
                        },
                        "elementValues": {},
                    },
                }
            }
        }
    )

    action.http_request = AsyncMock(side_effect=[login_resp, search_resp])

    result = await action.execute(malop_id="malop-123")

    assert result["status"] == "success"
    assert "integration_id" in result
    assert result["data"]["total_processes"] == 2
    assert len(result["data"]["processes"]) == 2
    assert result["data"]["processes"][0]["process_id"] == "proc-1"
    assert result["data"]["processes"][0]["process_name"] == "chrome.exe"
    assert result["data"]["processes"][0]["owner_machine_id"] == "machine-1"
    assert result["data"]["processes"][0]["owner_machine_name"] == "DESKTOP-ABC"


@pytest.mark.asyncio
async def test_query_processes_missing_malop_id(mock_credentials, mock_settings):
    """Test process query with missing malop_id."""
    action = create_action(
        QueryProcessesAction, "query_processes", mock_credentials, mock_settings
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "malop_id" in result["error"]
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_query_processes_empty_results(mock_credentials, mock_settings):
    """Test process query when no processes found."""
    action = create_action(
        QueryProcessesAction,
        "query_processes",
        mock_credentials,
        mock_settings,
    )

    login_resp = _mock_login_response()
    search_resp = _mock_json_response({"data": {"resultIdToElementDataMap": {}}})

    action.http_request = AsyncMock(side_effect=[login_resp, search_resp])

    result = await action.execute(malop_id="malop-empty")

    assert result["status"] == "success"
    assert "integration_id" in result
    assert result["data"]["total_processes"] == 0
    assert result["data"]["processes"] == []


# ============================================================================
# QueryMachinesAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_query_machines_success(mock_credentials, mock_settings):
    """Test successful machine query by name."""
    action = create_action(
        QueryMachinesAction,
        "query_machines",
        mock_credentials,
        mock_settings,
    )

    login_resp = _mock_login_response()
    search_resp = _mock_json_response(
        {
            "data": {
                "resultIdToElementDataMap": {
                    "machine-1": {
                        "simpleValues": {
                            "elementDisplayName": {"values": ["DESKTOP-ABC"]},
                            "osVersionType": {"values": ["Windows 10"]},
                            "platformArchitecture": {"values": ["x64"]},
                            "isActiveProbeConnected": {"values": ["true"]},
                        },
                        "elementValues": {},
                    }
                }
            }
        }
    )

    action.http_request = AsyncMock(side_effect=[login_resp, search_resp])

    result = await action.execute(name="DESKTOP*")

    assert result["status"] == "success"
    assert "integration_id" in result
    assert result["data"]["total_machines"] == 1
    assert result["data"]["machines"][0]["machine_name"] == "DESKTOP-ABC"
    assert result["data"]["machines"][0]["os_version"] == "Windows 10"
    assert result["data"]["machines"][0]["platform_architecture"] == "x64"
    assert result["data"]["machines"][0]["is_connected_to_cybereason"] == "true"


@pytest.mark.asyncio
async def test_query_machines_missing_name(mock_credentials, mock_settings):
    """Test machine query with missing name parameter."""
    action = create_action(
        QueryMachinesAction, "query_machines", mock_credentials, mock_settings
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "name" in result["error"]
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_query_machines_http_error(mock_credentials, mock_settings):
    """Test machine query with HTTP error."""
    action = create_action(
        QueryMachinesAction,
        "query_machines",
        mock_credentials,
        mock_settings,
    )

    login_resp = _mock_login_response()

    # Create a proper HTTPStatusError
    mock_request = MagicMock(spec=httpx.Request)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500

    action.http_request = AsyncMock(
        side_effect=[
            login_resp,
            httpx.HTTPStatusError(
                "Server Error", request=mock_request, response=mock_response
            ),
        ]
    )

    result = await action.execute(name="DESKTOP*")

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"
    assert "integration_id" in result


# ============================================================================
# GetSensorStatusAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_sensor_status_success(mock_credentials, mock_settings):
    """Test successful sensor status retrieval."""
    action = create_action(
        GetSensorStatusAction,
        "get_sensor_status",
        mock_credentials,
        mock_settings,
    )

    login_resp = _mock_login_response()
    search_resp = _mock_json_response(
        {
            "data": {
                "resultIdToElementDataMap": {
                    "machine-1": {
                        "simpleValues": {
                            "elementDisplayName": {"values": ["WORKSTATION-1"]},
                            "isConnected": {"values": ["true"]},
                        },
                    },
                    "machine-2": {
                        "simpleValues": {
                            "elementDisplayName": {"values": ["WORKSTATION-2"]},
                            "isConnected": {"values": ["false"]},
                        },
                    },
                }
            }
        }
    )

    action.http_request = AsyncMock(side_effect=[login_resp, search_resp])

    result = await action.execute(malop_id="malop-123")

    assert result["status"] == "success"
    assert "integration_id" in result
    assert result["data"]["total_sensors"] == 2
    assert result["data"]["sensors"][0]["status"] == "Online"
    assert result["data"]["sensors"][1]["status"] == "Offline"


@pytest.mark.asyncio
async def test_get_sensor_status_missing_malop_id(mock_credentials, mock_settings):
    """Test sensor status with missing malop_id."""
    action = create_action(
        GetSensorStatusAction, "get_sensor_status", mock_credentials, mock_settings
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "malop_id" in result["error"]
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_get_sensor_status_missing_credentials():
    """Test sensor status with missing credentials."""
    action = create_action(GetSensorStatusAction, "get_sensor_status")

    result = await action.execute(malop_id="malop-123")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "integration_id" in result


# ============================================================================
# KillProcessAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_kill_process_success(mock_credentials, mock_settings):
    """Test successful process kill."""
    action = create_action(
        KillProcessAction,
        "kill_process",
        mock_credentials,
        mock_settings,
    )

    login_resp = _mock_login_response()
    remediate_resp = _mock_json_response(
        {
            "remediationId": "rem-abc",
            "statusLog": [{"status": "PENDING"}],
        }
    )

    action.http_request = AsyncMock(side_effect=[login_resp, remediate_resp])

    result = await action.execute(
        malop_id="malop-123",
        machine_id="machine-1",
        process_id="proc-1",
        remediation_user="admin@company.com",
    )

    assert result["status"] == "success"
    assert "integration_id" in result
    assert result["data"]["remediation_id"] == "rem-abc"
    assert result["data"]["remediation_status"] == "PENDING"


@pytest.mark.asyncio
async def test_kill_process_missing_params(mock_credentials, mock_settings):
    """Test kill process with missing required parameters."""
    action = create_action(
        KillProcessAction, "kill_process", mock_credentials, mock_settings
    )

    result = await action.execute(malop_id="malop-123")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "machine_id" in result["error"]
    assert "process_id" in result["error"]
    assert "remediation_user" in result["error"]
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_kill_process_missing_credentials():
    """Test kill process with missing credentials."""
    action = create_action(KillProcessAction, "kill_process")

    result = await action.execute(
        malop_id="m",
        machine_id="m",
        process_id="p",
        remediation_user="u",
    )

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_kill_process_http_error(mock_credentials, mock_settings):
    """Test kill process with HTTP error from remediation API."""
    action = create_action(
        KillProcessAction, "kill_process", mock_credentials, mock_settings
    )

    login_resp = _mock_login_response()

    mock_request = MagicMock(spec=httpx.Request)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500

    action.http_request = AsyncMock(
        side_effect=[
            login_resp,
            httpx.HTTPStatusError(
                "Server Error", request=mock_request, response=mock_response
            ),
        ]
    )

    result = await action.execute(
        malop_id="malop-123",
        machine_id="m",
        process_id="p",
        remediation_user="u",
    )

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"
    assert "integration_id" in result


# ============================================================================
# SetReputationAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_set_reputation_blacklist_success(mock_credentials, mock_settings):
    """Test successful reputation blacklist."""
    action = create_action(
        SetReputationAction,
        "set_reputation",
        mock_credentials,
        mock_settings,
    )

    login_resp = _mock_login_response()
    update_resp = _mock_json_response({})

    action.http_request = AsyncMock(side_effect=[login_resp, update_resp])

    result = await action.execute(
        reputation_item_hash="abc123def456",
        custom_reputation="blacklist",
    )

    assert result["status"] == "success"
    assert "integration_id" in result
    assert result["data"]["reputation_item_hash"] == "abc123def456"
    assert result["data"]["custom_reputation"] == "blacklist"


@pytest.mark.asyncio
async def test_set_reputation_whitelist_success(mock_credentials, mock_settings):
    """Test successful reputation whitelist."""
    action = create_action(
        SetReputationAction,
        "set_reputation",
        mock_credentials,
        mock_settings,
    )

    login_resp = _mock_login_response()
    update_resp = _mock_json_response({})

    action.http_request = AsyncMock(side_effect=[login_resp, update_resp])

    result = await action.execute(
        reputation_item_hash="abc123def456",
        custom_reputation="whitelist",
    )

    assert result["status"] == "success"
    assert "integration_id" in result
    assert result["data"]["custom_reputation"] == "whitelist"


@pytest.mark.asyncio
async def test_set_reputation_remove_success(mock_credentials, mock_settings):
    """Test successful reputation removal."""
    action = create_action(
        SetReputationAction,
        "set_reputation",
        mock_credentials,
        mock_settings,
    )

    login_resp = _mock_login_response()
    update_resp = _mock_json_response({})

    action.http_request = AsyncMock(side_effect=[login_resp, update_resp])

    result = await action.execute(
        reputation_item_hash="abc123def456",
        custom_reputation="remove",
    )

    assert result["status"] == "success"
    assert "integration_id" in result
    assert result["data"]["custom_reputation"] == "remove"


@pytest.mark.asyncio
async def test_set_reputation_invalid_value(mock_credentials, mock_settings):
    """Test reputation with invalid custom_reputation value."""
    action = create_action(
        SetReputationAction,
        "set_reputation",
        mock_credentials,
        mock_settings,
    )

    result = await action.execute(
        reputation_item_hash="abc123",
        custom_reputation="invalid_value",
    )

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "custom_reputation" in result["error"]
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_set_reputation_missing_hash(mock_credentials, mock_settings):
    """Test reputation with missing hash."""
    action = create_action(
        SetReputationAction, "set_reputation", mock_credentials, mock_settings
    )

    result = await action.execute(custom_reputation="blacklist")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "reputation_item_hash" in result["error"]
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_set_reputation_missing_credentials():
    """Test reputation with missing credentials."""
    action = create_action(SetReputationAction, "set_reputation")

    result = await action.execute(
        reputation_item_hash="abc123",
        custom_reputation="blacklist",
    )

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "integration_id" in result
