"""Unit tests for Axonius integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.axonius.actions import (
    GetDeviceAction,
    GetDeviceByHostnameAction,
    GetDeviceByIpAction,
    GetUserAction,
    HealthCheckAction,
    SearchDevicesAction,
    SearchUsersAction,
)
from analysi.integrations.framework.integrations.axonius.constants import (
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP,
    ERROR_TYPE_TIMEOUT,
    ERROR_TYPE_VALIDATION,
    MSG_MISSING_BASE_URL,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_DEVICE_ID,
    MSG_MISSING_QUERY,
    MSG_MISSING_USER_ID,
    MSG_SERVER_CONNECTION,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

# ============================================================================
# DEFAULT FIXTURES
# ============================================================================

DEFAULT_SETTINGS = {
    "base_url": "https://myco.axonius.com",
    "timeout": 30,
}

DEFAULT_CREDENTIALS = {
    "api_key": "test-api-key-123",
    "api_secret": "test-api-secret-456",
}


# ============================================================================
# ACTION FIXTURES
# ============================================================================


@pytest.fixture
def health_check_action():
    """Create HealthCheckAction with valid config."""
    return HealthCheckAction(
        integration_id="axonius",
        action_id="health_check",
        settings=DEFAULT_SETTINGS,
        credentials=DEFAULT_CREDENTIALS,
    )


@pytest.fixture
def get_device_action():
    """Create GetDeviceAction with valid config."""
    return GetDeviceAction(
        integration_id="axonius",
        action_id="get_device",
        settings=DEFAULT_SETTINGS,
        credentials=DEFAULT_CREDENTIALS,
    )


@pytest.fixture
def search_devices_action():
    """Create SearchDevicesAction with valid config."""
    return SearchDevicesAction(
        integration_id="axonius",
        action_id="search_devices",
        settings=DEFAULT_SETTINGS,
        credentials=DEFAULT_CREDENTIALS,
    )


@pytest.fixture
def get_user_action():
    """Create GetUserAction with valid config."""
    return GetUserAction(
        integration_id="axonius",
        action_id="get_user",
        settings=DEFAULT_SETTINGS,
        credentials=DEFAULT_CREDENTIALS,
    )


@pytest.fixture
def search_users_action():
    """Create SearchUsersAction with valid config."""
    return SearchUsersAction(
        integration_id="axonius",
        action_id="search_users",
        settings=DEFAULT_SETTINGS,
        credentials=DEFAULT_CREDENTIALS,
    )


@pytest.fixture
def get_device_by_hostname_action():
    """Create GetDeviceByHostnameAction with valid config."""
    return GetDeviceByHostnameAction(
        integration_id="axonius",
        action_id="get_device_by_hostname",
        settings=DEFAULT_SETTINGS,
        credentials=DEFAULT_CREDENTIALS,
    )


@pytest.fixture
def get_device_by_ip_action():
    """Create GetDeviceByIpAction with valid config."""
    return GetDeviceByIpAction(
        integration_id="axonius",
        action_id="get_device_by_ip",
        settings=DEFAULT_SETTINGS,
        credentials=DEFAULT_CREDENTIALS,
    )


# ============================================================================
# MOCK HELPERS
# ============================================================================


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock httpx.Response with given JSON data."""
    response = MagicMock(spec=httpx.Response)
    response.json.return_value = json_data
    response.status_code = status_code
    response.text = str(json_data)
    return response


def _mock_http_error(status_code: int, text: str = "") -> httpx.HTTPStatusError:
    """Create a mock HTTPStatusError."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.text = text or f"HTTP {status_code}"
    return httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=MagicMock(),
        response=mock_response,
    )


# ============================================================================
# HEALTH CHECK ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check returns healthy status."""
    mock_resp = _mock_response(
        {
            "Build Version": "6.0.1",
            "Customer Name": "MyCompany",
        }
    )

    health_check_action.http_request = AsyncMock(return_value=mock_resp)

    result = await health_check_action.execute()

    assert result["status"] == STATUS_SUCCESS
    assert result["healthy"] is True
    assert result["data"]["healthy"] is True
    assert result["data"]["version"] == "6.0.1"
    assert result["data"]["instance_name"] == "MyCompany"
    health_check_action.http_request.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_missing_credentials():
    """Test health check fails with missing API key."""
    action = HealthCheckAction(
        integration_id="axonius",
        action_id="health_check",
        settings=DEFAULT_SETTINGS,
        credentials={},
    )

    result = await action.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_CREDENTIALS
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_missing_api_secret():
    """Test health check fails with missing API secret."""
    action = HealthCheckAction(
        integration_id="axonius",
        action_id="health_check",
        settings=DEFAULT_SETTINGS,
        credentials={"api_key": "key-only"},
    )

    result = await action.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_CREDENTIALS
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION


@pytest.mark.asyncio
async def test_health_check_missing_base_url():
    """Test health check fails with missing base_url."""
    action = HealthCheckAction(
        integration_id="axonius",
        action_id="health_check",
        settings={"timeout": 30},
        credentials=DEFAULT_CREDENTIALS,
    )

    result = await action.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_BASE_URL
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION


@pytest.mark.asyncio
async def test_health_check_timeout(health_check_action):
    """Test health check handles timeout."""
    health_check_action.http_request = AsyncMock(
        side_effect=httpx.TimeoutException("Request timed out")
    )

    result = await health_check_action.execute()

    assert result["status"] == STATUS_ERROR
    assert "timed out" in result["error"].lower()
    assert result["error_type"] == ERROR_TYPE_TIMEOUT
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_connection_error(health_check_action):
    """Test health check handles connection error."""
    health_check_action.http_request = AsyncMock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    result = await health_check_action.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_SERVER_CONNECTION
    assert result["error_type"] == ERROR_TYPE_HTTP
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_http_401(health_check_action):
    """Test health check handles 401 Unauthorized."""
    health_check_action.http_request = AsyncMock(
        side_effect=_mock_http_error(401, "Unauthorized")
    )

    result = await health_check_action.execute()

    assert result["status"] == STATUS_ERROR
    assert result["data"]["healthy"] is False


@pytest.mark.asyncio
async def test_health_check_correct_url(health_check_action):
    """Test health check calls the correct API endpoint."""
    mock_resp = _mock_response({"Build Version": "6.0.1"})
    health_check_action.http_request = AsyncMock(return_value=mock_resp)

    await health_check_action.execute()

    call_args = health_check_action.http_request.call_args
    url = call_args[0][0]
    assert url == "https://myco.axonius.com/api/v2/system/meta/about"


@pytest.mark.asyncio
async def test_health_check_sends_auth_headers(health_check_action):
    """Test health check sends correct authentication headers."""
    mock_resp = _mock_response({"Build Version": "6.0.1"})
    health_check_action.http_request = AsyncMock(return_value=mock_resp)

    await health_check_action.execute()

    call_kwargs = health_check_action.http_request.call_args[1]
    headers = call_kwargs["headers"]
    assert headers["api-key"] == "test-api-key-123"
    assert headers["api-secret"] == "test-api-secret-456"
    assert headers["Content-Type"] == "application/json"


# ============================================================================
# GET DEVICE ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_device_success(get_device_action):
    """Test successful device lookup by ID."""
    device_data = {
        "internal_axon_id": "abc123",
        "adapters": ["active_directory", "crowdstrike"],
        "specific_data": {"data": {"hostname": "workstation-01"}},
    }
    mock_resp = _mock_response(device_data)
    get_device_action.http_request = AsyncMock(return_value=mock_resp)

    result = await get_device_action.execute(internal_axon_id="abc123")

    assert result["status"] == STATUS_SUCCESS
    assert result["internal_axon_id"] == "abc123"
    assert result["data"]["internal_axon_id"] == "abc123"


@pytest.mark.asyncio
async def test_get_device_missing_id(get_device_action):
    """Test get device fails with missing internal_axon_id."""
    result = await get_device_action.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_DEVICE_ID
    assert result["error_type"] == ERROR_TYPE_VALIDATION


@pytest.mark.asyncio
async def test_get_device_empty_id(get_device_action):
    """Test get device fails with empty internal_axon_id."""
    result = await get_device_action.execute(internal_axon_id="")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_DEVICE_ID
    assert result["error_type"] == ERROR_TYPE_VALIDATION


@pytest.mark.asyncio
async def test_get_device_missing_credentials():
    """Test get device fails with missing credentials."""
    action = GetDeviceAction(
        integration_id="axonius",
        action_id="get_device",
        settings=DEFAULT_SETTINGS,
        credentials={},
    )

    result = await action.execute(internal_axon_id="abc123")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_CREDENTIALS
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION


@pytest.mark.asyncio
async def test_get_device_missing_base_url():
    """Test get device fails with missing base_url."""
    action = GetDeviceAction(
        integration_id="axonius",
        action_id="get_device",
        settings={},
        credentials=DEFAULT_CREDENTIALS,
    )

    result = await action.execute(internal_axon_id="abc123")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_BASE_URL
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION


@pytest.mark.asyncio
async def test_get_device_not_found(get_device_action):
    """Test get device returns success with not_found for 404."""
    get_device_action.http_request = AsyncMock(
        side_effect=_mock_http_error(404, "Not Found")
    )

    result = await get_device_action.execute(internal_axon_id="nonexistent")

    assert result["status"] == STATUS_SUCCESS
    assert result["not_found"] is True
    assert result["internal_axon_id"] == "nonexistent"
    assert result["data"] == {}


@pytest.mark.asyncio
async def test_get_device_http_error(get_device_action):
    """Test get device handles non-404 HTTP errors."""
    get_device_action.http_request = AsyncMock(
        side_effect=_mock_http_error(500, "Internal Server Error")
    )

    result = await get_device_action.execute(internal_axon_id="abc123")

    assert result["status"] == STATUS_ERROR
    assert result["error_type"] == ERROR_TYPE_HTTP


@pytest.mark.asyncio
async def test_get_device_timeout(get_device_action):
    """Test get device handles timeout."""
    get_device_action.http_request = AsyncMock(
        side_effect=httpx.TimeoutException("Request timed out")
    )

    result = await get_device_action.execute(internal_axon_id="abc123")

    assert result["status"] == STATUS_ERROR
    assert "timed out" in result["error"].lower()
    assert result["error_type"] == ERROR_TYPE_TIMEOUT


@pytest.mark.asyncio
async def test_get_device_connection_error(get_device_action):
    """Test get device handles connection error."""
    get_device_action.http_request = AsyncMock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    result = await get_device_action.execute(internal_axon_id="abc123")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_SERVER_CONNECTION
    assert result["error_type"] == ERROR_TYPE_HTTP


@pytest.mark.asyncio
async def test_get_device_correct_url(get_device_action):
    """Test get device calls the correct URL with device ID."""
    mock_resp = _mock_response({"internal_axon_id": "abc123"})
    get_device_action.http_request = AsyncMock(return_value=mock_resp)

    await get_device_action.execute(internal_axon_id="abc123")

    url = get_device_action.http_request.call_args[0][0]
    assert url == "https://myco.axonius.com/api/v2/devices/abc123"


# ============================================================================
# SEARCH DEVICES ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_search_devices_success(search_devices_action):
    """Test successful device search."""
    search_response = {
        "assets": [
            {
                "internal_axon_id": "dev1",
                "specific_data": {"data": {"hostname": "ws-01"}},
            },
            {
                "internal_axon_id": "dev2",
                "specific_data": {"data": {"hostname": "ws-02"}},
            },
        ],
        "page": {"totalResources": 2},
    }
    mock_resp = _mock_response(search_response)
    search_devices_action.http_request = AsyncMock(return_value=mock_resp)

    result = await search_devices_action.execute(
        query='(specific_data.data.hostname == "ws-01")'
    )

    assert result["status"] == STATUS_SUCCESS
    assert result["summary"]["total_results"] == 2
    assert result["summary"]["returned"] == 2
    assert len(result["devices"]) == 2


@pytest.mark.asyncio
async def test_search_devices_empty_results(search_devices_action):
    """Test device search with no matches."""
    mock_resp = _mock_response({"assets": [], "page": {"totalResources": 0}})
    search_devices_action.http_request = AsyncMock(return_value=mock_resp)

    result = await search_devices_action.execute(query="(hostname == 'nonexistent')")

    assert result["status"] == STATUS_SUCCESS
    assert result["summary"]["total_results"] == 0
    assert result["summary"]["returned"] == 0
    assert len(result["devices"]) == 0


@pytest.mark.asyncio
async def test_search_devices_missing_query(search_devices_action):
    """Test search devices fails with missing query."""
    result = await search_devices_action.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_QUERY
    assert result["error_type"] == ERROR_TYPE_VALIDATION


@pytest.mark.asyncio
async def test_search_devices_empty_query(search_devices_action):
    """Test search devices fails with empty query string."""
    result = await search_devices_action.execute(query="")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_QUERY
    assert result["error_type"] == ERROR_TYPE_VALIDATION


@pytest.mark.asyncio
async def test_search_devices_missing_credentials():
    """Test search devices fails with missing credentials."""
    action = SearchDevicesAction(
        integration_id="axonius",
        action_id="search_devices",
        settings=DEFAULT_SETTINGS,
        credentials={},
    )

    result = await action.execute(query="(hostname == 'test')")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_CREDENTIALS
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION


@pytest.mark.asyncio
async def test_search_devices_uses_post(search_devices_action):
    """Test search devices uses POST method with correct body."""
    mock_resp = _mock_response({"assets": [], "page": {}})
    search_devices_action.http_request = AsyncMock(return_value=mock_resp)

    await search_devices_action.execute(query="(hostname == 'test')", max_rows=10)

    call_kwargs = search_devices_action.http_request.call_args[1]
    assert (
        call_kwargs.get("method") == "POST"
        or search_devices_action.http_request.call_args[0] == ()
    )

    # Verify the json_data body
    body = call_kwargs["json_data"]
    assert body["filter"] == "(hostname == 'test')"
    assert body["page_size"] == 10
    assert body["row_start"] == 0


@pytest.mark.asyncio
async def test_search_devices_timeout(search_devices_action):
    """Test search devices handles timeout."""
    search_devices_action.http_request = AsyncMock(
        side_effect=httpx.TimeoutException("Request timed out")
    )

    result = await search_devices_action.execute(query="(hostname == 'test')")

    assert result["status"] == STATUS_ERROR
    assert "timed out" in result["error"].lower()
    assert result["error_type"] == ERROR_TYPE_TIMEOUT


@pytest.mark.asyncio
async def test_search_devices_http_error(search_devices_action):
    """Test search devices handles HTTP error."""
    search_devices_action.http_request = AsyncMock(
        side_effect=_mock_http_error(500, "Internal Server Error")
    )

    result = await search_devices_action.execute(query="(hostname == 'test')")

    assert result["status"] == STATUS_ERROR
    assert result["error_type"] == ERROR_TYPE_HTTP


@pytest.mark.asyncio
async def test_search_devices_connection_error(search_devices_action):
    """Test search devices handles connection error."""
    search_devices_action.http_request = AsyncMock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    result = await search_devices_action.execute(query="(hostname == 'test')")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_SERVER_CONNECTION
    assert result["error_type"] == ERROR_TYPE_HTTP


@pytest.mark.asyncio
async def test_search_devices_custom_fields(search_devices_action):
    """Test search devices with custom fields parameter."""
    mock_resp = _mock_response({"assets": [], "page": {}})
    search_devices_action.http_request = AsyncMock(return_value=mock_resp)

    custom_fields = ["internal_axon_id", "specific_data.data.hostname"]
    await search_devices_action.execute(
        query="(hostname == 'test')", fields=custom_fields
    )

    call_kwargs = search_devices_action.http_request.call_args[1]
    body = call_kwargs["json_data"]
    assert body["fields"] == custom_fields


@pytest.mark.asyncio
async def test_search_devices_correct_url(search_devices_action):
    """Test search devices calls the correct URL."""
    mock_resp = _mock_response({"assets": [], "page": {}})
    search_devices_action.http_request = AsyncMock(return_value=mock_resp)

    await search_devices_action.execute(query="(hostname == 'test')")

    url = search_devices_action.http_request.call_args[0][0]
    assert url == "https://myco.axonius.com/api/v2/devices"


# ============================================================================
# GET USER ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_user_success(get_user_action):
    """Test successful user lookup by ID."""
    user_data = {
        "internal_axon_id": "user123",
        "adapters": ["active_directory"],
        "specific_data": {"data": {"username": "jdoe", "mail": "jdoe@example.com"}},
    }
    mock_resp = _mock_response(user_data)
    get_user_action.http_request = AsyncMock(return_value=mock_resp)

    result = await get_user_action.execute(internal_axon_id="user123")

    assert result["status"] == STATUS_SUCCESS
    assert result["internal_axon_id"] == "user123"
    assert result["data"]["specific_data"]["data"]["username"] == "jdoe"


@pytest.mark.asyncio
async def test_get_user_missing_id(get_user_action):
    """Test get user fails with missing internal_axon_id."""
    result = await get_user_action.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_USER_ID
    assert result["error_type"] == ERROR_TYPE_VALIDATION


@pytest.mark.asyncio
async def test_get_user_empty_id(get_user_action):
    """Test get user fails with empty internal_axon_id."""
    result = await get_user_action.execute(internal_axon_id="")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_USER_ID
    assert result["error_type"] == ERROR_TYPE_VALIDATION


@pytest.mark.asyncio
async def test_get_user_missing_credentials():
    """Test get user fails with missing credentials."""
    action = GetUserAction(
        integration_id="axonius",
        action_id="get_user",
        settings=DEFAULT_SETTINGS,
        credentials={},
    )

    result = await action.execute(internal_axon_id="user123")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_CREDENTIALS
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION


@pytest.mark.asyncio
async def test_get_user_not_found(get_user_action):
    """Test get user returns success with not_found for 404."""
    get_user_action.http_request = AsyncMock(
        side_effect=_mock_http_error(404, "Not Found")
    )

    result = await get_user_action.execute(internal_axon_id="nonexistent")

    assert result["status"] == STATUS_SUCCESS
    assert result["not_found"] is True
    assert result["internal_axon_id"] == "nonexistent"
    assert result["data"] == {}


@pytest.mark.asyncio
async def test_get_user_http_error(get_user_action):
    """Test get user handles non-404 HTTP errors."""
    get_user_action.http_request = AsyncMock(
        side_effect=_mock_http_error(500, "Internal Server Error")
    )

    result = await get_user_action.execute(internal_axon_id="user123")

    assert result["status"] == STATUS_ERROR
    assert result["error_type"] == ERROR_TYPE_HTTP


@pytest.mark.asyncio
async def test_get_user_timeout(get_user_action):
    """Test get user handles timeout."""
    get_user_action.http_request = AsyncMock(
        side_effect=httpx.TimeoutException("Request timed out")
    )

    result = await get_user_action.execute(internal_axon_id="user123")

    assert result["status"] == STATUS_ERROR
    assert "timed out" in result["error"].lower()
    assert result["error_type"] == ERROR_TYPE_TIMEOUT


@pytest.mark.asyncio
async def test_get_user_correct_url(get_user_action):
    """Test get user calls the correct URL with user ID."""
    mock_resp = _mock_response({"internal_axon_id": "user123"})
    get_user_action.http_request = AsyncMock(return_value=mock_resp)

    await get_user_action.execute(internal_axon_id="user123")

    url = get_user_action.http_request.call_args[0][0]
    assert url == "https://myco.axonius.com/api/v2/users/user123"


# ============================================================================
# SEARCH USERS ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_search_users_success(search_users_action):
    """Test successful user search."""
    search_response = {
        "assets": [
            {
                "internal_axon_id": "u1",
                "specific_data": {"data": {"username": "alice"}},
            },
        ],
        "page": {"totalResources": 1},
    }
    mock_resp = _mock_response(search_response)
    search_users_action.http_request = AsyncMock(return_value=mock_resp)

    result = await search_users_action.execute(
        query='(specific_data.data.mail == "alice@example.com")'
    )

    assert result["status"] == STATUS_SUCCESS
    assert result["summary"]["total_results"] == 1
    assert result["summary"]["returned"] == 1
    assert len(result["users"]) == 1


@pytest.mark.asyncio
async def test_search_users_empty_results(search_users_action):
    """Test user search with no matches."""
    mock_resp = _mock_response({"assets": [], "page": {"totalResources": 0}})
    search_users_action.http_request = AsyncMock(return_value=mock_resp)

    result = await search_users_action.execute(query="(username == 'nonexistent')")

    assert result["status"] == STATUS_SUCCESS
    assert result["summary"]["total_results"] == 0
    assert len(result["users"]) == 0


@pytest.mark.asyncio
async def test_search_users_missing_query(search_users_action):
    """Test search users fails with missing query."""
    result = await search_users_action.execute()

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_QUERY
    assert result["error_type"] == ERROR_TYPE_VALIDATION


@pytest.mark.asyncio
async def test_search_users_missing_credentials():
    """Test search users fails with missing credentials."""
    action = SearchUsersAction(
        integration_id="axonius",
        action_id="search_users",
        settings=DEFAULT_SETTINGS,
        credentials={},
    )

    result = await action.execute(query="(username == 'test')")

    assert result["status"] == STATUS_ERROR
    assert result["error"] == MSG_MISSING_CREDENTIALS
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION


@pytest.mark.asyncio
async def test_search_users_uses_post(search_users_action):
    """Test search users uses POST method with correct body."""
    mock_resp = _mock_response({"assets": [], "page": {}})
    search_users_action.http_request = AsyncMock(return_value=mock_resp)

    await search_users_action.execute(query="(username == 'test')", max_rows=25)

    call_kwargs = search_users_action.http_request.call_args[1]
    body = call_kwargs["json_data"]
    assert body["filter"] == "(username == 'test')"
    assert body["page_size"] == 25


@pytest.mark.asyncio
async def test_search_users_timeout(search_users_action):
    """Test search users handles timeout."""
    search_users_action.http_request = AsyncMock(
        side_effect=httpx.TimeoutException("Request timed out")
    )

    result = await search_users_action.execute(query="(username == 'test')")

    assert result["status"] == STATUS_ERROR
    assert "timed out" in result["error"].lower()
    assert result["error_type"] == ERROR_TYPE_TIMEOUT


@pytest.mark.asyncio
async def test_search_users_correct_url(search_users_action):
    """Test search users calls the correct URL."""
    mock_resp = _mock_response({"assets": [], "page": {}})
    search_users_action.http_request = AsyncMock(return_value=mock_resp)

    await search_users_action.execute(query="(username == 'test')")

    url = search_users_action.http_request.call_args[0][0]
    assert url == "https://myco.axonius.com/api/v2/users"


# ============================================================================
# GET DEVICE BY HOSTNAME ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_device_by_hostname_success(get_device_by_hostname_action):
    """Test successful device lookup by hostname."""
    search_response = {
        "assets": [
            {
                "internal_axon_id": "dev1",
                "specific_data": {"data": {"hostname": "workstation-01"}},
            },
        ],
        "page": {"totalResources": 1},
    }
    mock_resp = _mock_response(search_response)

    # The convenience action delegates to SearchDevicesAction, which calls http_request.
    # We need to mock the delegated action's http_request. Since it creates a new
    # SearchDevicesAction internally, we patch http_request on the base class.
    from unittest.mock import patch

    with patch.object(
        SearchDevicesAction,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_resp,
    ):
        result = await get_device_by_hostname_action.execute(hostname="workstation-01")

    assert result["status"] == STATUS_SUCCESS
    assert result["hostname"] == "workstation-01"
    assert len(result["devices"]) == 1


@pytest.mark.asyncio
async def test_get_device_by_hostname_missing_hostname(get_device_by_hostname_action):
    """Test get device by hostname fails with missing hostname."""
    result = await get_device_by_hostname_action.execute()

    assert result["status"] == STATUS_ERROR
    assert "Hostname is required" in result["error"]
    assert result["error_type"] == ERROR_TYPE_VALIDATION


@pytest.mark.asyncio
async def test_get_device_by_hostname_empty_hostname(get_device_by_hostname_action):
    """Test get device by hostname fails with empty hostname."""
    result = await get_device_by_hostname_action.execute(hostname="")

    assert result["status"] == STATUS_ERROR
    assert "Hostname is required" in result["error"]
    assert result["error_type"] == ERROR_TYPE_VALIDATION


@pytest.mark.asyncio
async def test_get_device_by_hostname_builds_aql_query(get_device_by_hostname_action):
    """Test get device by hostname builds the correct AQL query."""
    mock_resp = _mock_response({"assets": [], "page": {}})

    from unittest.mock import patch

    with patch.object(
        SearchDevicesAction,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_resp,
    ) as mock_http:
        await get_device_by_hostname_action.execute(hostname="server-01")

        call_kwargs = mock_http.call_args[1]
        body = call_kwargs["json_data"]
        assert (
            'specific_data.data.hostname == regex("server-01", "i")' in body["filter"]
        )


# ============================================================================
# GET DEVICE BY IP ACTION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_device_by_ip_success(get_device_by_ip_action):
    """Test successful device lookup by IP."""
    search_response = {
        "assets": [
            {
                "internal_axon_id": "dev1",
                "specific_data": {"data": {"hostname": "ws-01"}},
            },
        ],
        "page": {"totalResources": 1},
    }
    mock_resp = _mock_response(search_response)

    from unittest.mock import patch

    with patch.object(
        SearchDevicesAction,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_resp,
    ):
        result = await get_device_by_ip_action.execute(ip="10.0.0.5")

    assert result["status"] == STATUS_SUCCESS
    assert result["ip_address"] == "10.0.0.5"
    assert len(result["devices"]) == 1


@pytest.mark.asyncio
async def test_get_device_by_ip_missing_ip(get_device_by_ip_action):
    """Test get device by IP fails with missing IP."""
    result = await get_device_by_ip_action.execute()

    assert result["status"] == STATUS_ERROR
    assert "IP address is required" in result["error"]
    assert result["error_type"] == ERROR_TYPE_VALIDATION


@pytest.mark.asyncio
async def test_get_device_by_ip_empty_ip(get_device_by_ip_action):
    """Test get device by IP fails with empty IP string."""
    result = await get_device_by_ip_action.execute(ip="")

    assert result["status"] == STATUS_ERROR
    assert "IP address is required" in result["error"]
    assert result["error_type"] == ERROR_TYPE_VALIDATION


@pytest.mark.asyncio
async def test_get_device_by_ip_builds_aql_query(get_device_by_ip_action):
    """Test get device by IP builds the correct AQL query."""
    mock_resp = _mock_response({"assets": [], "page": {}})

    from unittest.mock import patch

    with patch.object(
        SearchDevicesAction,
        "http_request",
        new_callable=AsyncMock,
        return_value=mock_resp,
    ) as mock_http:
        await get_device_by_ip_action.execute(ip="192.168.1.100")

        call_kwargs = mock_http.call_args[1]
        body = call_kwargs["json_data"]
        assert (
            body["filter"]
            == '(specific_data.data.network_interfaces.ips == "192.168.1.100")'
        )


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================


def test_get_api_url():
    """Test _get_api_url builds correct URLs."""
    from analysi.integrations.framework.integrations.axonius.actions import _get_api_url

    assert _get_api_url("https://myco.axonius.com", "system/meta/about") == (
        "https://myco.axonius.com/api/v2/system/meta/about"
    )


def test_get_api_url_strips_trailing_slash():
    """Test _get_api_url strips trailing slash from base URL."""
    from analysi.integrations.framework.integrations.axonius.actions import _get_api_url

    assert _get_api_url("https://myco.axonius.com/", "devices") == (
        "https://myco.axonius.com/api/v2/devices"
    )


def test_get_auth_headers():
    """Test _get_auth_headers builds correct headers."""
    from analysi.integrations.framework.integrations.axonius.actions import (
        _get_auth_headers,
    )

    headers = _get_auth_headers("my-key", "my-secret")
    assert headers["api-key"] == "my-key"
    assert headers["api-secret"] == "my-secret"
    assert headers["Content-Type"] == "application/json"


def test_validate_credentials_valid():
    """Test _validate_credentials with valid credentials."""
    from analysi.integrations.framework.integrations.axonius.actions import (
        _validate_credentials,
    )

    valid, error, key, secret = _validate_credentials(
        {"api_key": "k", "api_secret": "s"}
    )
    assert valid is True
    assert error == ""
    assert key == "k"
    assert secret == "s"


def test_validate_credentials_missing_key():
    """Test _validate_credentials with missing api_key."""
    from analysi.integrations.framework.integrations.axonius.actions import (
        _validate_credentials,
    )

    valid, error, key, secret = _validate_credentials({"api_secret": "s"})
    assert valid is False
    assert error == MSG_MISSING_CREDENTIALS


def test_validate_credentials_missing_secret():
    """Test _validate_credentials with missing api_secret."""
    from analysi.integrations.framework.integrations.axonius.actions import (
        _validate_credentials,
    )

    valid, error, key, secret = _validate_credentials({"api_key": "k"})
    assert valid is False
    assert error == MSG_MISSING_CREDENTIALS


def test_validate_credentials_empty():
    """Test _validate_credentials with empty credentials."""
    from analysi.integrations.framework.integrations.axonius.actions import (
        _validate_credentials,
    )

    valid, error, key, secret = _validate_credentials({})
    assert valid is False
    assert error == MSG_MISSING_CREDENTIALS


def test_validate_base_url_valid():
    """Test _validate_base_url with valid URL."""
    from analysi.integrations.framework.integrations.axonius.actions import (
        _validate_base_url,
    )

    valid, error, url = _validate_base_url({"base_url": "https://myco.axonius.com"})
    assert valid is True
    assert url == "https://myco.axonius.com"


def test_validate_base_url_missing():
    """Test _validate_base_url with missing base_url."""
    from analysi.integrations.framework.integrations.axonius.actions import (
        _validate_base_url,
    )

    valid, error, url = _validate_base_url({})
    assert valid is False
    assert error == MSG_MISSING_BASE_URL
