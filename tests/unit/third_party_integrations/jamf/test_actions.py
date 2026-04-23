"""Unit tests for Jamf Pro integration actions.

Tests cover all 8 actions:
  - HealthCheckAction
  - GetDeviceAction
  - ListDevicesAction
  - GetMobileDeviceAction
  - ListMobileDevicesAction
  - LockDeviceAction
  - WipeDeviceAction
  - GetUserAction

Each action is tested for:
  1. Success case
  2. Missing required parameters (ValidationError)
  3. Missing credentials (ConfigurationError)
  4. HTTP errors (404 not-found, general failures)
  5. Token auth retry on 401
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.jamf.actions import (
    GetDeviceAction,
    GetMobileDeviceAction,
    GetUserAction,
    HealthCheckAction,
    ListDevicesAction,
    ListMobileDevicesAction,
    LockDeviceAction,
    WipeDeviceAction,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_credentials():
    """Valid Jamf Pro credentials."""
    return {
        "username": "admin",
        "password": "secret",
    }


@pytest.fixture
def mock_settings():
    """Valid Jamf Pro settings."""
    return {
        "base_url": "https://test.jamfcloud.com",
        "timeout": 30,
    }


def create_action(
    action_class,
    action_id="test_action",
    credentials=None,
    settings=None,
):
    """Helper to create action instances with required parameters."""
    return action_class(
        integration_id="jamf",
        action_id=action_id,
        credentials=credentials or {},
        settings=settings or {},
    )


def make_mock_response(json_data=None, status_code=200):
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    resp.text = str(json_data)
    return resp


def make_token_response():
    """Create a mock token response for Jamf Pro auth."""
    return make_mock_response(
        json_data={"token": "test-bearer-token", "expires": "2025-12-31T23:59:59Z"},
    )


def make_http_status_error(status_code, message="Error"):
    """Create a mock httpx.HTTPStatusError."""
    request = MagicMock(spec=httpx.Request)
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = message
    return httpx.HTTPStatusError(
        message=message,
        request=request,
        response=response,
    )


# ============================================================================
# HealthCheckAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(mock_credentials, mock_settings):
    """Test successful health check with valid credentials."""
    action = create_action(
        HealthCheckAction, "health_check", mock_credentials, mock_settings
    )

    token_resp = make_token_response()
    accounts_resp = make_mock_response(json_data={"accounts": {"users": []}})

    action.http_request = AsyncMock(side_effect=[token_resp, accounts_resp])

    result = await action.execute()

    assert result["status"] == "success"
    assert result["integration_id"] == "jamf"
    assert result["action_id"] == "health_check"
    assert result["data"]["healthy"] is True
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_health_check_missing_credentials(mock_settings):
    """Test health check with no credentials."""
    action = create_action(HealthCheckAction, "health_check", {}, mock_settings)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert (
        "credentials" in result["error"].lower()
        or "username" in result["error"].lower()
    )


@pytest.mark.asyncio
async def test_health_check_missing_base_url(mock_credentials):
    """Test health check with no base_url in settings."""
    action = create_action(HealthCheckAction, "health_check", mock_credentials, {})

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"
    assert "base_url" in result["error"]


@pytest.mark.asyncio
async def test_health_check_auth_failure(mock_credentials, mock_settings):
    """Test health check when authentication fails (401)."""
    action = create_action(
        HealthCheckAction, "health_check", mock_credentials, mock_settings
    )

    error = make_http_status_error(401, "Unauthorized")
    action.http_request = AsyncMock(side_effect=error)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "AuthenticationError"


@pytest.mark.asyncio
async def test_health_check_server_error(mock_credentials, mock_settings):
    """Test health check when server returns 500."""
    action = create_action(
        HealthCheckAction, "health_check", mock_credentials, mock_settings
    )

    error = make_http_status_error(500, "Internal Server Error")
    action.http_request = AsyncMock(side_effect=error)

    result = await action.execute()

    assert result["status"] == "error"


# ============================================================================
# GetDeviceAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_device_success(mock_credentials, mock_settings):
    """Test successful device lookup."""
    action = create_action(
        GetDeviceAction, "get_device", mock_credentials, mock_settings
    )

    token_resp = make_token_response()
    device_resp = make_mock_response(
        json_data={
            "computer": {
                "general": {
                    "id": 42,
                    "name": "MacBook-Pro-42",
                    "mac_address": "AA:BB:CC:DD:EE:FF",
                    "platform": "Mac",
                }
            }
        }
    )

    action.http_request = AsyncMock(side_effect=[token_resp, device_resp])

    result = await action.execute(id=42)

    assert result["status"] == "success"
    assert result["integration_id"] == "jamf"
    assert "computer" in result["data"]
    assert result["data"]["computer"]["general"]["id"] == 42


@pytest.mark.asyncio
async def test_get_device_missing_id(mock_credentials, mock_settings):
    """Test get_device with no ID parameter."""
    action = create_action(
        GetDeviceAction, "get_device", mock_credentials, mock_settings
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "id" in result["error"]


@pytest.mark.asyncio
async def test_get_device_invalid_id(mock_credentials, mock_settings):
    """Test get_device with invalid ID (non-integer)."""
    action = create_action(
        GetDeviceAction, "get_device", mock_credentials, mock_settings
    )

    result = await action.execute(id="not-a-number")

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "integer" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_device_negative_id(mock_credentials, mock_settings):
    """Test get_device with negative ID."""
    action = create_action(
        GetDeviceAction, "get_device", mock_credentials, mock_settings
    )

    result = await action.execute(id=-1)

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_get_device_not_found(mock_credentials, mock_settings):
    """Test get_device when device does not exist (404 returns success with not_found)."""
    action = create_action(
        GetDeviceAction, "get_device", mock_credentials, mock_settings
    )

    token_resp = make_token_response()
    error_404 = make_http_status_error(404, "Not Found")

    action.http_request = AsyncMock(side_effect=[token_resp, error_404])

    result = await action.execute(id=99999)

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["id"] == 99999


@pytest.mark.asyncio
async def test_get_device_missing_credentials(mock_settings):
    """Test get_device with no credentials."""
    action = create_action(GetDeviceAction, "get_device", {}, mock_settings)

    result = await action.execute(id=1)

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_get_device_token_refresh_on_401(mock_credentials, mock_settings):
    """Test that 401 triggers token refresh and retries the request."""
    action = create_action(
        GetDeviceAction, "get_device", mock_credentials, mock_settings
    )

    token_resp_1 = make_token_response()
    error_401 = make_http_status_error(401, "Unauthorized")
    token_resp_2 = make_token_response()
    device_resp = make_mock_response(
        json_data={"computer": {"general": {"id": 42, "name": "MacBook"}}}
    )

    # Flow: token -> 401 on API call -> new token -> successful API call
    action.http_request = AsyncMock(
        side_effect=[token_resp_1, error_401, token_resp_2, device_resp]
    )

    result = await action.execute(id=42)

    assert result["status"] == "success"
    assert result["data"]["computer"]["general"]["id"] == 42
    assert action.http_request.call_count == 4


# ============================================================================
# ListDevicesAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_devices_success(mock_credentials, mock_settings):
    """Test listing all computers."""
    action = create_action(
        ListDevicesAction, "list_devices", mock_credentials, mock_settings
    )

    token_resp = make_token_response()
    list_resp = make_mock_response(
        json_data={
            "computers": [
                {"id": 1, "name": "Mac-1"},
                {"id": 2, "name": "Mac-2"},
            ]
        }
    )

    action.http_request = AsyncMock(side_effect=[token_resp, list_resp])

    result = await action.execute()

    assert result["status"] == "success"
    assert "computers" in result["data"]
    assert len(result["data"]["computers"]) == 2


@pytest.mark.asyncio
async def test_list_devices_with_query(mock_credentials, mock_settings):
    """Test searching computers with a match query."""
    action = create_action(
        ListDevicesAction, "list_devices", mock_credentials, mock_settings
    )

    token_resp = make_token_response()
    list_resp = make_mock_response(
        json_data={"computers": [{"id": 1, "name": "MacBook-Pro"}]}
    )

    action.http_request = AsyncMock(side_effect=[token_resp, list_resp])

    result = await action.execute(query="MacBook")

    assert result["status"] == "success"
    # Verify the URL includes the match path
    call_args = action.http_request.call_args_list
    api_call_url = call_args[1][0][0]  # second call, first positional arg
    assert "/match/MacBook" in api_call_url


@pytest.mark.asyncio
async def test_list_devices_missing_credentials(mock_settings):
    """Test listing devices without credentials."""
    action = create_action(ListDevicesAction, "list_devices", {}, mock_settings)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_list_devices_http_error(mock_credentials, mock_settings):
    """Test listing devices when server returns error."""
    action = create_action(
        ListDevicesAction, "list_devices", mock_credentials, mock_settings
    )

    token_resp = make_token_response()
    error_500 = make_http_status_error(500, "Internal Server Error")

    action.http_request = AsyncMock(side_effect=[token_resp, error_500])

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# GetMobileDeviceAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_mobile_device_success(mock_credentials, mock_settings):
    """Test successful mobile device lookup."""
    action = create_action(
        GetMobileDeviceAction, "get_mobile_device", mock_credentials, mock_settings
    )

    token_resp = make_token_response()
    device_resp = make_mock_response(
        json_data={
            "mobile_device": {
                "general": {
                    "id": 10,
                    "name": "iPad-Sales-01",
                    "model": "iPad Air",
                }
            }
        }
    )

    action.http_request = AsyncMock(side_effect=[token_resp, device_resp])

    result = await action.execute(id=10)

    assert result["status"] == "success"
    assert "mobile_device" in result["data"]


@pytest.mark.asyncio
async def test_get_mobile_device_missing_id(mock_credentials, mock_settings):
    """Test get_mobile_device with no ID."""
    action = create_action(
        GetMobileDeviceAction, "get_mobile_device", mock_credentials, mock_settings
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_get_mobile_device_not_found(mock_credentials, mock_settings):
    """Test get_mobile_device when device does not exist."""
    action = create_action(
        GetMobileDeviceAction, "get_mobile_device", mock_credentials, mock_settings
    )

    token_resp = make_token_response()
    error_404 = make_http_status_error(404, "Not Found")

    action.http_request = AsyncMock(side_effect=[token_resp, error_404])

    result = await action.execute(id=99999)

    assert result["status"] == "success"
    assert result["not_found"] is True


# ============================================================================
# ListMobileDevicesAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_mobile_devices_success(mock_credentials, mock_settings):
    """Test listing all mobile devices."""
    action = create_action(
        ListMobileDevicesAction,
        "list_mobile_devices",
        mock_credentials,
        mock_settings,
    )

    token_resp = make_token_response()
    list_resp = make_mock_response(
        json_data={
            "mobile_devices": [
                {"id": 1, "name": "iPad-1"},
                {"id": 2, "name": "iPhone-1"},
            ]
        }
    )

    action.http_request = AsyncMock(side_effect=[token_resp, list_resp])

    result = await action.execute()

    assert result["status"] == "success"
    assert "mobile_devices" in result["data"]
    assert len(result["data"]["mobile_devices"]) == 2


@pytest.mark.asyncio
async def test_list_mobile_devices_missing_credentials(mock_settings):
    """Test listing mobile devices without credentials."""
    action = create_action(
        ListMobileDevicesAction, "list_mobile_devices", {}, mock_settings
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


# ============================================================================
# LockDeviceAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_lock_device_success(mock_credentials, mock_settings):
    """Test successful device lock."""
    action = create_action(
        LockDeviceAction, "lock_device", mock_credentials, mock_settings
    )

    token_resp = make_token_response()
    lock_resp = make_mock_response(
        json_data={"command": {"id": 100, "status": "Pending"}}
    )

    action.http_request = AsyncMock(side_effect=[token_resp, lock_resp])

    result = await action.execute(id=42)

    assert result["status"] == "success"
    assert result["data"]["device_id"] == 42
    assert result["data"]["command"] == "DeviceLock"


@pytest.mark.asyncio
async def test_lock_device_with_passcode(mock_credentials, mock_settings):
    """Test device lock with custom passcode."""
    action = create_action(
        LockDeviceAction, "lock_device", mock_credentials, mock_settings
    )

    token_resp = make_token_response()
    lock_resp = make_mock_response(json_data={"command": {"status": "Pending"}})

    action.http_request = AsyncMock(side_effect=[token_resp, lock_resp])

    result = await action.execute(id=42, passcode="123456")

    assert result["status"] == "success"
    # Verify passcode was passed as param
    api_call = action.http_request.call_args_list[1]
    assert api_call.kwargs.get("params", {}).get("passcode") == "123456"


@pytest.mark.asyncio
async def test_lock_device_missing_id(mock_credentials, mock_settings):
    """Test lock device with no ID."""
    action = create_action(
        LockDeviceAction, "lock_device", mock_credentials, mock_settings
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_lock_device_not_found(mock_credentials, mock_settings):
    """Test lock device when device does not exist."""
    action = create_action(
        LockDeviceAction, "lock_device", mock_credentials, mock_settings
    )

    token_resp = make_token_response()
    error_404 = make_http_status_error(404, "Not Found")

    action.http_request = AsyncMock(side_effect=[token_resp, error_404])

    result = await action.execute(id=99999)

    assert result["status"] == "success"
    assert result["not_found"] is True


@pytest.mark.asyncio
async def test_lock_device_invalid_id(mock_credentials, mock_settings):
    """Test lock device with zero ID."""
    action = create_action(
        LockDeviceAction, "lock_device", mock_credentials, mock_settings
    )

    result = await action.execute(id=0)

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


# ============================================================================
# WipeDeviceAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_wipe_device_success(mock_credentials, mock_settings):
    """Test successful device wipe."""
    action = create_action(
        WipeDeviceAction, "wipe_device", mock_credentials, mock_settings
    )

    token_resp = make_token_response()
    wipe_resp = make_mock_response(
        json_data={"command": {"id": 101, "status": "Pending"}}
    )

    action.http_request = AsyncMock(side_effect=[token_resp, wipe_resp])

    result = await action.execute(id=42)

    assert result["status"] == "success"
    assert result["data"]["device_id"] == 42
    assert result["data"]["command"] == "EraseDevice"


@pytest.mark.asyncio
async def test_wipe_device_missing_id(mock_credentials, mock_settings):
    """Test wipe device with no ID."""
    action = create_action(
        WipeDeviceAction, "wipe_device", mock_credentials, mock_settings
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"


@pytest.mark.asyncio
async def test_wipe_device_not_found(mock_credentials, mock_settings):
    """Test wipe device when device does not exist."""
    action = create_action(
        WipeDeviceAction, "wipe_device", mock_credentials, mock_settings
    )

    token_resp = make_token_response()
    error_404 = make_http_status_error(404, "Not Found")

    action.http_request = AsyncMock(side_effect=[token_resp, error_404])

    result = await action.execute(id=99999)

    assert result["status"] == "success"
    assert result["not_found"] is True


@pytest.mark.asyncio
async def test_wipe_device_missing_credentials(mock_settings):
    """Test wipe device without credentials."""
    action = create_action(WipeDeviceAction, "wipe_device", {}, mock_settings)

    result = await action.execute(id=1)

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


# ============================================================================
# GetUserAction Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_user_success(mock_credentials, mock_settings):
    """Test successful user lookup."""
    action = create_action(GetUserAction, "get_user", mock_credentials, mock_settings)

    token_resp = make_token_response()
    user_resp = make_mock_response(
        json_data={
            "user": {
                "id": 1,
                "name": "jdoe",
                "full_name": "John Doe",
                "email": "jdoe@example.com",
            }
        }
    )

    action.http_request = AsyncMock(side_effect=[token_resp, user_resp])

    result = await action.execute(username="jdoe")

    assert result["status"] == "success"
    assert result["integration_id"] == "jamf"
    assert "user" in result["data"]
    assert result["data"]["user"]["name"] == "jdoe"


@pytest.mark.asyncio
async def test_get_user_missing_username(mock_credentials, mock_settings):
    """Test get_user with no username parameter."""
    action = create_action(GetUserAction, "get_user", mock_credentials, mock_settings)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == "ValidationError"
    assert "username" in result["error"]


@pytest.mark.asyncio
async def test_get_user_not_found(mock_credentials, mock_settings):
    """Test get_user when user does not exist (404 returns success with not_found)."""
    action = create_action(GetUserAction, "get_user", mock_credentials, mock_settings)

    token_resp = make_token_response()
    error_404 = make_http_status_error(404, "Not Found")

    action.http_request = AsyncMock(side_effect=[token_resp, error_404])

    result = await action.execute(username="nonexistent")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["username"] == "nonexistent"


@pytest.mark.asyncio
async def test_get_user_missing_credentials(mock_settings):
    """Test get_user without credentials."""
    action = create_action(GetUserAction, "get_user", {}, mock_settings)

    result = await action.execute(username="jdoe")

    assert result["status"] == "error"
    assert result["error_type"] == "ConfigurationError"


@pytest.mark.asyncio
async def test_get_user_http_error(mock_credentials, mock_settings):
    """Test get_user when server returns 500."""
    action = create_action(GetUserAction, "get_user", mock_credentials, mock_settings)

    token_resp = make_token_response()
    error_500 = make_http_status_error(500, "Server Error")

    action.http_request = AsyncMock(side_effect=[token_resp, error_500])

    result = await action.execute(username="jdoe")

    assert result["status"] == "error"
    assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# Result Envelope Tests
# ============================================================================


@pytest.mark.asyncio
async def test_success_result_envelope(mock_credentials, mock_settings):
    """Verify success results include all envelope fields."""
    action = create_action(
        ListMobileDevicesAction,
        "list_mobile_devices",
        mock_credentials,
        mock_settings,
    )

    token_resp = make_token_response()
    list_resp = make_mock_response(json_data={"mobile_devices": []})

    action.http_request = AsyncMock(side_effect=[token_resp, list_resp])

    result = await action.execute()

    assert "status" in result
    assert "timestamp" in result
    assert "integration_id" in result
    assert "action_id" in result
    assert "data" in result
    assert result["integration_id"] == "jamf"
    assert result["action_id"] == "list_mobile_devices"


@pytest.mark.asyncio
async def test_error_result_envelope(mock_settings):
    """Verify error results include all envelope fields."""
    action = create_action(GetDeviceAction, "get_device", {}, mock_settings)

    result = await action.execute(id=1)

    assert "status" in result
    assert "timestamp" in result
    assert "integration_id" in result
    assert "action_id" in result
    assert "error" in result
    assert "error_type" in result
    assert result["integration_id"] == "jamf"


# ============================================================================
# _validate_device_id Tests
# ============================================================================


def test_validate_device_id_valid():
    """Test _validate_device_id with valid inputs."""
    from analysi.integrations.framework.integrations.jamf.actions import (
        _validate_device_id,
    )

    assert _validate_device_id(42) == 42
    assert _validate_device_id("42") == 42
    assert _validate_device_id(1) == 1


def test_validate_device_id_invalid():
    """Test _validate_device_id with invalid inputs."""
    from analysi.integrations.framework.integrations.jamf.actions import (
        _validate_device_id,
    )

    assert _validate_device_id(None) is None
    assert _validate_device_id(0) is None
    assert _validate_device_id(-1) is None
    assert _validate_device_id("abc") is None
    assert _validate_device_id("") is None
