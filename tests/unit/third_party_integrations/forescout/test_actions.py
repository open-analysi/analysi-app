"""Unit tests for Forescout integration actions.

Tests cover the Web API (REST/JSON) actions migrated from the
upstream forescoutcounteract connector. All HTTP calls are mocked via
action.http_request (AsyncMock).
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.forescout.actions import (
    GetActiveSessionsAction,
    GetHostAction,
    HealthCheckAction,
    ListHostsAction,
    ListPoliciesAction,
)
from analysi.integrations.framework.integrations.forescout.constants import (
    ERROR_TYPE_AUTHENTICATION,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    MSG_HOST_IDENTIFIER_REQUIRED,
    MSG_MISSING_BASE_URL,
    MSG_MISSING_CREDENTIALS,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def credentials():
    """Valid Forescout Web API credentials."""
    return {
        "username": "admin",
        "password": "secret123",
    }


@pytest.fixture
def settings():
    """Valid Forescout settings."""
    return {
        "base_url": "https://forescout.example.com",
        "timeout": 30,
        "verify_ssl": True,
    }


@pytest.fixture
def health_check_action(credentials, settings):
    """Create HealthCheckAction instance."""
    return HealthCheckAction("forescout", "health_check", settings, credentials)


@pytest.fixture
def list_hosts_action(credentials, settings):
    """Create ListHostsAction instance."""
    return ListHostsAction("forescout", "list_hosts", settings, credentials)


@pytest.fixture
def get_host_action(credentials, settings):
    """Create GetHostAction instance."""
    return GetHostAction("forescout", "get_host", settings, credentials)


@pytest.fixture
def list_policies_action(credentials, settings):
    """Create ListPoliciesAction instance."""
    return ListPoliciesAction("forescout", "list_policies", settings, credentials)


@pytest.fixture
def get_active_sessions_action(credentials, settings):
    """Create GetActiveSessionsAction instance."""
    return GetActiveSessionsAction(
        "forescout", "get_active_sessions", settings, credentials
    )


def _mock_login_response(token: str = "jwt-test-token-123") -> MagicMock:
    """Create a mock response for the /api/login call."""
    resp = MagicMock(spec=httpx.Response)
    resp.text = token
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    return resp


def _mock_json_response(data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock JSON response for a Web API call."""
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = data
    resp.text = str(data)
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    return resp


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_health_check_success(health_check_action):
    """Test successful health check -- login + hosts endpoint."""
    login_resp = _mock_login_response()
    hosts_resp = _mock_json_response({"hosts": [{"ip": "10.0.0.1"}]})

    health_check_action.http_request = AsyncMock(side_effect=[login_resp, hosts_resp])

    result = await health_check_action.execute()

    assert result["status"] == "success"
    assert result["healthy"] is True
    assert "integration_id" in result
    assert result["integration_id"] == "forescout"
    assert result["action_id"] == "health_check"
    assert health_check_action.http_request.call_count == 2


@pytest.mark.asyncio
async def test_health_check_missing_credentials(settings):
    """Test health check with missing credentials."""
    action = HealthCheckAction("forescout", "health_check", settings, {})

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION
    assert "username" in result["error"]
    assert "password" in result["error"]


@pytest.mark.asyncio
async def test_health_check_missing_username(settings):
    """Test health check with only password, no username."""
    action = HealthCheckAction(
        "forescout", "health_check", settings, {"password": "pass"}
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION


@pytest.mark.asyncio
async def test_health_check_missing_base_url(credentials):
    """Test health check with missing base_url."""
    action = HealthCheckAction("forescout", "health_check", {}, credentials)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION
    assert MSG_MISSING_BASE_URL in result["error"]


@pytest.mark.asyncio
async def test_health_check_login_failure(health_check_action):
    """Test health check when JWT login fails."""
    health_check_action.http_request = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "Unauthorized",
            request=MagicMock(),
            response=MagicMock(status_code=401, text="Unauthorized"),
        )
    )

    result = await health_check_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_AUTHENTICATION


@pytest.mark.asyncio
async def test_health_check_api_error(health_check_action):
    """Test health check when hosts endpoint fails after login."""
    login_resp = _mock_login_response()

    error_response = MagicMock(status_code=500, text="Internal Server Error")
    health_check_action.http_request = AsyncMock(
        side_effect=[
            login_resp,
            httpx.HTTPStatusError(
                "Server Error",
                request=MagicMock(),
                response=error_response,
            ),
        ]
    )

    result = await health_check_action.execute()

    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_health_check_empty_token(health_check_action):
    """Test health check when login returns empty token."""
    empty_token_resp = MagicMock(spec=httpx.Response)
    empty_token_resp.text = ""
    empty_token_resp.status_code = 200
    empty_token_resp.raise_for_status = MagicMock()

    health_check_action.http_request = AsyncMock(return_value=empty_token_resp)

    result = await health_check_action.execute()

    assert result["status"] == "error"


# ============================================================================
# LIST HOSTS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_hosts_success(list_hosts_action):
    """Test successful host listing."""
    login_resp = _mock_login_response()
    hosts_data = {
        "hosts": [
            {"hostId": 167841953, "ip": "10.0.0.1", "mac": "00:50:56:8b:00"},
            {"hostId": 167841954, "ip": "10.0.0.2", "mac": "00:50:56:8b:01"},
        ]
    }
    hosts_resp = _mock_json_response(hosts_data)

    list_hosts_action.http_request = AsyncMock(side_effect=[login_resp, hosts_resp])

    result = await list_hosts_action.execute()

    assert result["status"] == "success"
    assert result["data"]["num_hosts"] == 2
    assert len(result["data"]["hosts"]) == 2
    assert result["data"]["hosts"][0]["ip"] == "10.0.0.1"
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_list_hosts_empty(list_hosts_action):
    """Test listing hosts when none are found."""
    login_resp = _mock_login_response()
    hosts_resp = _mock_json_response({"hosts": []})

    list_hosts_action.http_request = AsyncMock(side_effect=[login_resp, hosts_resp])

    result = await list_hosts_action.execute()

    assert result["status"] == "success"
    assert result["data"]["num_hosts"] == 0
    assert result["data"]["hosts"] == []


@pytest.mark.asyncio
async def test_list_hosts_missing_credentials(settings):
    """Test list hosts with missing credentials."""
    action = ListHostsAction("forescout", "list_hosts", settings, {})

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION
    assert MSG_MISSING_CREDENTIALS in result["error"]


@pytest.mark.asyncio
async def test_list_hosts_missing_base_url(credentials):
    """Test list hosts with missing base_url."""
    action = ListHostsAction("forescout", "list_hosts", {}, credentials)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION


@pytest.mark.asyncio
async def test_list_hosts_connection_error(list_hosts_action):
    """Test list hosts with connection error."""
    list_hosts_action.http_request = AsyncMock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    result = await list_hosts_action.execute()

    assert result["status"] == "error"


# ============================================================================
# GET HOST TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_host_by_id(get_host_action):
    """Test getting host by numeric ID."""
    login_resp = _mock_login_response()
    host_data = {
        "host": {
            "id": 167841953,
            "ip": "10.0.0.1",
            "mac": "00:50:56:8b:00",
            "fields": {
                "online": {"value": "true", "timestamp": 1537315647},
                "cl_type": {"value": "Managed(CounterACT)", "timestamp": 1537297213},
            },
        }
    }
    host_resp = _mock_json_response(host_data)

    get_host_action.http_request = AsyncMock(side_effect=[login_resp, host_resp])

    result = await get_host_action.execute(host_id=167841953)

    assert result["status"] == "success"
    assert result["data"]["host"]["ip"] == "10.0.0.1"
    assert result["data"]["host_ip"] == "10.0.0.1"
    assert result["data"]["host_mac"] == "00:50:56:8b:00"
    assert result["data"]["host_id"] == 167841953
    assert "integration_id" in result

    # Verify the endpoint URL includes the host_id
    second_call = get_host_action.http_request.call_args_list[1]
    assert "/api/hosts/167841953" in second_call.kwargs.get("url", "")


@pytest.mark.asyncio
async def test_get_host_by_ip(get_host_action):
    """Test getting host by IP address."""
    login_resp = _mock_login_response()
    host_data = {
        "host": {
            "id": 167841953,
            "ip": "10.0.0.1",
            "mac": "00:50:56:8b:00",
        }
    }
    host_resp = _mock_json_response(host_data)

    get_host_action.http_request = AsyncMock(side_effect=[login_resp, host_resp])

    result = await get_host_action.execute(host_ip="10.0.0.1")

    assert result["status"] == "success"
    assert result["data"]["host"]["ip"] == "10.0.0.1"

    # Verify the endpoint URL uses the IP path
    second_call = get_host_action.http_request.call_args_list[1]
    assert "/api/hosts/ip/10.0.0.1" in second_call.kwargs.get("url", "")


@pytest.mark.asyncio
async def test_get_host_by_mac(get_host_action):
    """Test getting host by MAC address."""
    login_resp = _mock_login_response()
    host_data = {
        "host": {
            "id": 167841953,
            "ip": "10.0.0.1",
            "mac": "00:50:56:8b:00",
        }
    }
    host_resp = _mock_json_response(host_data)

    get_host_action.http_request = AsyncMock(side_effect=[login_resp, host_resp])

    result = await get_host_action.execute(host_mac="00:50:56:8b:00")

    assert result["status"] == "success"

    # Verify the endpoint URL uses the MAC path
    second_call = get_host_action.http_request.call_args_list[1]
    assert "/api/hosts/mac/00:50:56:8b:00" in second_call.kwargs.get("url", "")


@pytest.mark.asyncio
async def test_get_host_priority_order(get_host_action):
    """Test that host_id takes priority over host_ip and host_mac."""
    login_resp = _mock_login_response()
    host_data = {"host": {"id": 123, "ip": "10.0.0.1", "mac": "aa:bb:cc"}}
    host_resp = _mock_json_response(host_data)

    get_host_action.http_request = AsyncMock(side_effect=[login_resp, host_resp])

    # Provide all three identifiers; host_id should win
    result = await get_host_action.execute(
        host_id=123, host_ip="10.0.0.1", host_mac="aa:bb:cc"
    )

    assert result["status"] == "success"
    second_call = get_host_action.http_request.call_args_list[1]
    assert "/api/hosts/123" in second_call.kwargs.get("url", "")


@pytest.mark.asyncio
async def test_get_host_no_identifier(get_host_action):
    """Test get host with no identifier provided."""
    result = await get_host_action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_VALIDATION
    assert MSG_HOST_IDENTIFIER_REQUIRED in result["error"]


@pytest.mark.asyncio
async def test_get_host_invalid_host_id_string(get_host_action):
    """Test get host with non-integer host_id."""
    result = await get_host_action.execute(host_id="not_a_number")

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_VALIDATION
    assert "integer" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_host_invalid_host_id_negative(get_host_action):
    """Test get host with negative host_id."""
    result = await get_host_action.execute(host_id=-5)

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_VALIDATION
    assert "positive" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_host_invalid_host_id_zero(get_host_action):
    """Test get host with zero host_id."""
    result = await get_host_action.execute(host_id=0)

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_VALIDATION


@pytest.mark.asyncio
async def test_get_host_not_found(get_host_action):
    """Test get host when host does not exist (404)."""
    login_resp = _mock_login_response()

    error_response = MagicMock(status_code=404, text="Not Found")
    get_host_action.http_request = AsyncMock(
        side_effect=[
            login_resp,
            httpx.HTTPStatusError(
                "Not Found",
                request=MagicMock(),
                response=error_response,
            ),
        ]
    )

    result = await get_host_action.execute(host_ip="192.168.1.99")

    assert result["status"] == "success"
    assert result["not_found"] is True
    assert result["data"]["host_ip"] == "192.168.1.99"


@pytest.mark.asyncio
async def test_get_host_missing_credentials(settings):
    """Test get host with missing credentials."""
    action = GetHostAction("forescout", "get_host", settings, {})

    result = await action.execute(host_ip="10.0.0.1")

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION


@pytest.mark.asyncio
async def test_get_host_string_host_id(get_host_action):
    """Test get host with string host_id that is a valid number."""
    login_resp = _mock_login_response()
    host_data = {"host": {"id": 42, "ip": "10.0.0.1", "mac": "aa:bb:cc"}}
    host_resp = _mock_json_response(host_data)

    get_host_action.http_request = AsyncMock(side_effect=[login_resp, host_resp])

    result = await get_host_action.execute(host_id="42")

    assert result["status"] == "success"
    second_call = get_host_action.http_request.call_args_list[1]
    assert "/api/hosts/42" in second_call.kwargs.get("url", "")


# ============================================================================
# LIST POLICIES TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_list_policies_success(list_policies_action):
    """Test successful policy listing."""
    login_resp = _mock_login_response()
    policies_data = {
        "policies": [
            {
                "policyId": -6488799636120036097,
                "name": "Asset Classification",
                "description": "Classify hosts into groups",
                "rules": [
                    {
                        "ruleId": 1822401057983693948,
                        "name": "NAT Devices",
                        "description": "NAT detection rule",
                    }
                ],
            },
            {
                "policyId": 7042988451856611698,
                "name": "Compliance Check",
                "description": "Check endpoint compliance",
            },
        ]
    }
    policies_resp = _mock_json_response(policies_data)

    list_policies_action.http_request = AsyncMock(
        side_effect=[login_resp, policies_resp]
    )

    result = await list_policies_action.execute()

    assert result["status"] == "success"
    assert result["data"]["num_policies"] == 2
    assert len(result["data"]["policies"]) == 2
    assert result["data"]["policies"][0]["name"] == "Asset Classification"
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_list_policies_empty(list_policies_action):
    """Test listing policies when none exist."""
    login_resp = _mock_login_response()
    policies_resp = _mock_json_response({"policies": []})

    list_policies_action.http_request = AsyncMock(
        side_effect=[login_resp, policies_resp]
    )

    result = await list_policies_action.execute()

    assert result["status"] == "success"
    assert result["data"]["num_policies"] == 0
    assert result["data"]["policies"] == []


@pytest.mark.asyncio
async def test_list_policies_missing_credentials(settings):
    """Test list policies with missing credentials."""
    action = ListPoliciesAction("forescout", "list_policies", settings, {})

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION


@pytest.mark.asyncio
async def test_list_policies_missing_base_url(credentials):
    """Test list policies with missing base_url."""
    action = ListPoliciesAction("forescout", "list_policies", {}, credentials)

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION


@pytest.mark.asyncio
async def test_list_policies_server_error(list_policies_action):
    """Test list policies with server error."""
    login_resp = _mock_login_response()
    error_response = MagicMock(status_code=500, text="Internal Server Error")
    list_policies_action.http_request = AsyncMock(
        side_effect=[
            login_resp,
            httpx.HTTPStatusError(
                "Server Error", request=MagicMock(), response=error_response
            ),
        ]
    )

    result = await list_policies_action.execute()

    assert result["status"] == "error"


# ============================================================================
# GET ACTIVE SESSIONS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_get_active_sessions_no_filters(get_active_sessions_action):
    """Test getting active sessions without any filters."""
    login_resp = _mock_login_response()
    sessions_data = {
        "hosts": [
            {"hostId": 167841793, "ip": "10.0.0.1", "mac": "00:50:56:8b:00"},
            {"hostId": 167841953, "ip": "10.0.0.2", "mac": "00:50:56:8b:01"},
        ]
    }
    sessions_resp = _mock_json_response(sessions_data)

    get_active_sessions_action.http_request = AsyncMock(
        side_effect=[login_resp, sessions_resp]
    )

    result = await get_active_sessions_action.execute()

    assert result["status"] == "success"
    assert result["data"]["num_active_sessions"] == 2
    assert len(result["data"]["hosts"]) == 2
    assert "integration_id" in result


@pytest.mark.asyncio
async def test_get_active_sessions_with_rule_id(get_active_sessions_action):
    """Test getting active sessions filtered by rule_id."""
    login_resp = _mock_login_response()
    sessions_data = {"hosts": [{"hostId": 167841793, "ip": "10.0.0.1"}]}
    sessions_resp = _mock_json_response(sessions_data)

    get_active_sessions_action.http_request = AsyncMock(
        side_effect=[login_resp, sessions_resp]
    )

    result = await get_active_sessions_action.execute(rule_id="7042988451856611698")

    assert result["status"] == "success"
    assert result["data"]["num_active_sessions"] == 1

    # Verify matchRuleId was passed as a query param
    second_call = get_active_sessions_action.http_request.call_args_list[1]
    params = second_call.kwargs.get("params", {})
    assert "matchRuleId" in params
    assert params["matchRuleId"] == "7042988451856611698"


@pytest.mark.asyncio
async def test_get_active_sessions_with_prop_val(get_active_sessions_action):
    """Test getting active sessions filtered by property values."""
    login_resp = _mock_login_response()
    sessions_data = {"hosts": [{"hostId": 167841953, "ip": "10.0.0.2"}]}
    sessions_resp = _mock_json_response(sessions_data)

    get_active_sessions_action.http_request = AsyncMock(
        side_effect=[login_resp, sessions_resp]
    )

    result = await get_active_sessions_action.execute(
        prop_val="Prop_String=Sales,Prop_Int=5"
    )

    assert result["status"] == "success"

    # Verify property values are passed as query params
    second_call = get_active_sessions_action.http_request.call_args_list[1]
    params = second_call.kwargs.get("params", {})
    assert params["Prop_String"] == "Sales"
    assert params["Prop_Int"] == "5"


@pytest.mark.asyncio
async def test_get_active_sessions_with_both_filters(get_active_sessions_action):
    """Test getting active sessions with both rule_id and prop_val filters."""
    login_resp = _mock_login_response()
    sessions_data = {"hosts": []}
    sessions_resp = _mock_json_response(sessions_data)

    get_active_sessions_action.http_request = AsyncMock(
        side_effect=[login_resp, sessions_resp]
    )

    result = await get_active_sessions_action.execute(
        rule_id="12345", prop_val="status=active"
    )

    assert result["status"] == "success"
    assert result["data"]["num_active_sessions"] == 0

    # Verify both filter types present
    second_call = get_active_sessions_action.http_request.call_args_list[1]
    params = second_call.kwargs.get("params", {})
    assert params["matchRuleId"] == "12345"
    assert params["status"] == "active"


@pytest.mark.asyncio
async def test_get_active_sessions_invalid_rule_id(get_active_sessions_action):
    """Test get active sessions with invalid rule_id (empty comma segment)."""
    result = await get_active_sessions_action.execute(rule_id="123,,456")

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_VALIDATION
    assert "empty" in result["error"].lower()


@pytest.mark.asyncio
async def test_get_active_sessions_invalid_prop_val_empty(
    get_active_sessions_action,
):
    """Test get active sessions with empty prop_val segment."""
    result = await get_active_sessions_action.execute(prop_val="key=val,,other=x")

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_VALIDATION


@pytest.mark.asyncio
async def test_get_active_sessions_invalid_prop_val_no_equals(
    get_active_sessions_action,
):
    """Test get active sessions with prop_val missing = sign."""
    result = await get_active_sessions_action.execute(prop_val="no_equals_sign")

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_VALIDATION
    assert "key=value" in result["error"]


@pytest.mark.asyncio
async def test_get_active_sessions_missing_credentials(settings):
    """Test get active sessions with missing credentials."""
    action = GetActiveSessionsAction("forescout", "get_active_sessions", settings, {})

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION


@pytest.mark.asyncio
async def test_get_active_sessions_missing_base_url(credentials):
    """Test get active sessions with missing base_url."""
    action = GetActiveSessionsAction(
        "forescout", "get_active_sessions", {}, credentials
    )

    result = await action.execute()

    assert result["status"] == "error"
    assert result["error_type"] == ERROR_TYPE_CONFIGURATION


@pytest.mark.asyncio
async def test_get_active_sessions_multiple_rule_ids(get_active_sessions_action):
    """Test get active sessions with multiple comma-separated rule IDs."""
    login_resp = _mock_login_response()
    sessions_data = {"hosts": [{"hostId": 1, "ip": "10.0.0.1"}]}
    sessions_resp = _mock_json_response(sessions_data)

    get_active_sessions_action.http_request = AsyncMock(
        side_effect=[login_resp, sessions_resp]
    )

    result = await get_active_sessions_action.execute(rule_id="111, 222, 333")

    assert result["status"] == "success"

    second_call = get_active_sessions_action.http_request.call_args_list[1]
    params = second_call.kwargs.get("params", {})
    assert params["matchRuleId"] == "111,222,333"


# ============================================================================
# JWT AUTH EDGE CASES
# ============================================================================


@pytest.mark.asyncio
async def test_jwt_connection_timeout(list_hosts_action):
    """Test behavior when login request times out."""
    list_hosts_action.http_request = AsyncMock(
        side_effect=httpx.TimeoutException("Connection timed out")
    )

    result = await list_hosts_action.execute()

    assert result["status"] == "error"
    assert "timed out" in result["error"].lower()


@pytest.mark.asyncio
async def test_jwt_token_whitespace_stripped(list_hosts_action):
    """Test that JWT token whitespace is stripped."""
    login_resp = MagicMock(spec=httpx.Response)
    login_resp.text = "  jwt-token-with-whitespace  \n"
    login_resp.status_code = 200
    login_resp.raise_for_status = MagicMock()

    hosts_resp = _mock_json_response({"hosts": []})

    list_hosts_action.http_request = AsyncMock(side_effect=[login_resp, hosts_resp])

    result = await list_hosts_action.execute()

    assert result["status"] == "success"

    # Verify the Authorization header uses the stripped token
    second_call = list_hosts_action.http_request.call_args_list[1]
    headers = second_call.kwargs.get("headers", {})
    assert headers["Authorization"] == "jwt-token-with-whitespace"


@pytest.mark.asyncio
async def test_base_url_trailing_slash_stripped(credentials):
    """Test that trailing slash on base_url is handled."""
    settings = {
        "base_url": "https://forescout.example.com/",
        "timeout": 30,
    }
    action = ListHostsAction("forescout", "list_hosts", settings, credentials)

    login_resp = _mock_login_response()
    hosts_resp = _mock_json_response({"hosts": []})

    action.http_request = AsyncMock(side_effect=[login_resp, hosts_resp])

    result = await action.execute()

    assert result["status"] == "success"

    # Verify no double slash in URL
    first_call = action.http_request.call_args_list[0]
    login_url = first_call.kwargs.get("url", "")
    assert "//" not in login_url.replace("https://", "")
