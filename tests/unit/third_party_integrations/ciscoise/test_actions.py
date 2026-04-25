"""Unit tests for Cisco ISE integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.ciscoise.actions import (
    GetActiveSessionsAction,
    GetEndpointByMacAction,
    HealthCheckAction,
    ListEndpointsAction,
    QuarantineEndpointAction,
    ReleaseEndpointAction,
    _detect_address_type,
    _get_ers_auth,
    _get_server,
    _xml_to_dict,
)

# ============================================================================
# HELPER TESTS
# ============================================================================


class TestHelpers:
    """Test helper functions."""

    def test_get_server_with_hostname(self):
        assert _get_server({"server": "10.1.1.1"}) == "https://10.1.1.1"

    def test_get_server_with_https_prefix(self):
        assert _get_server({"server": "https://ise.corp.com"}) == "https://ise.corp.com"

    def test_get_server_missing(self):
        assert _get_server({}) is None

    def test_get_server_empty(self):
        assert _get_server({"server": ""}) is None

    def test_get_ers_auth_with_ers_creds(self):
        creds = {
            "username": "admin",
            "password": "pass",
            "ers_username": "ers_admin",
            "ers_password": "ers_pass",
        }
        assert _get_ers_auth(creds) == ("ers_admin", "ers_pass")

    def test_get_ers_auth_fallback_to_primary(self):
        creds = {"username": "admin", "password": "pass"}
        assert _get_ers_auth(creds) == ("admin", "pass")

    def test_get_ers_auth_no_creds(self):
        assert _get_ers_auth({}) is None

    def test_detect_address_type_mac_colon(self):
        assert _detect_address_type("AA:BB:CC:DD:EE:FF") == "macAddress"

    def test_detect_address_type_mac_dash(self):
        assert _detect_address_type("AA-BB-CC-DD-EE-FF") == "macAddress"

    def test_detect_address_type_ip(self):
        assert _detect_address_type("10.1.1.1") == "ipAddress"

    def test_detect_address_type_ambiguous_defaults_to_mac(self):
        assert _detect_address_type("unknown_value") == "macAddress"

    def test_xml_to_dict_simple(self):
        xml = "<root><child>value</child></root>"
        result = _xml_to_dict(xml)
        assert result == {"root": {"child": "value"}}

    def test_xml_to_dict_nested(self):
        xml = "<root><parent><child>val</child></parent></root>"
        result = _xml_to_dict(xml)
        assert result == {"root": {"parent": {"child": "val"}}}

    def test_xml_to_dict_repeated_tags(self):
        xml = "<root><item>a</item><item>b</item></root>"
        result = _xml_to_dict(xml)
        assert result == {"root": {"item": ["a", "b"]}}

    def test_xml_to_dict_empty_element(self):
        xml = "<root><child></child></root>"
        result = _xml_to_dict(xml)
        assert result == {"root": {"child": ""}}


# ============================================================================
# FIXTURES
# ============================================================================


DEFAULT_SETTINGS = {"server": "10.1.1.1", "verify_ssl": False, "timeout": 30}
DEFAULT_CREDENTIALS = {"username": "admin", "password": "secret"}
ERS_CREDENTIALS = {
    "username": "admin",
    "password": "secret",
    "ers_username": "ers_admin",
    "ers_password": "ers_secret",
}


def _make_action(cls, settings=None, credentials=None):
    """Create an action instance with sane defaults.

    Pass ``settings={}`` or ``credentials={}`` explicitly to simulate
    missing configuration.  ``None`` (the default) gets replaced by
    the default fixtures.
    """
    return cls(
        integration_id="ciscoise",
        action_id=cls.__name__.replace("Action", "").lower(),
        settings=DEFAULT_SETTINGS.copy() if settings is None else settings,
        credentials=DEFAULT_CREDENTIALS.copy() if credentials is None else credentials,
    )


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


class TestHealthCheckAction:
    """Test the health_check action."""

    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["healthy"] is True
        assert result["data"]["healthy"] is True
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_server(self):
        action = _make_action(HealthCheckAction, settings={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "server" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(HealthCheckAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "credentials" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        mock_response = MagicMock()
        mock_response.status_code = 401
        error = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "CiscoISEAPIError"

    @pytest.mark.asyncio
    async def test_connection_error(self, action):
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert "ConnectError" in result["error_type"]


# ============================================================================
# GET ACTIVE SESSIONS TESTS
# ============================================================================


class TestGetActiveSessionsAction:
    """Test the get_active_sessions action."""

    @pytest.fixture
    def action(self):
        return _make_action(GetActiveSessionsAction)

    @pytest.mark.asyncio
    async def test_success_with_sessions(self, action):
        sessions_xml = (
            "<activeList>"
            "<activeSession>"
            "<calling_station_id>AA:BB:CC:DD:EE:FF</calling_station_id>"
            "<user_name>testuser</user_name>"
            "</activeSession>"
            "</activeList>"
        )
        quarantine_xml = "<EPS_RESULT><userData>true</userData></EPS_RESULT>"

        mock_session_resp = MagicMock()
        mock_session_resp.text = sessions_xml

        mock_quarantine_resp = MagicMock()
        mock_quarantine_resp.text = quarantine_xml

        # First call returns sessions, second call returns quarantine status
        action.http_request = AsyncMock(
            side_effect=[mock_session_resp, mock_quarantine_resp]
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["sessions_found"] == 1
        assert result["data"]["sessions"][0]["is_quarantined"] == "Yes"
        assert (
            result["data"]["sessions"][0]["calling_station_id"] == "AA:BB:CC:DD:EE:FF"
        )

    @pytest.mark.asyncio
    async def test_success_no_sessions(self, action):
        empty_xml = "<activeList></activeList>"
        mock_resp = MagicMock()
        mock_resp.text = empty_xml
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["sessions_found"] == 0
        assert result["data"]["sessions"] == []

    @pytest.mark.asyncio
    async def test_quarantine_check_failure_is_non_fatal(self, action):
        sessions_xml = (
            "<activeList>"
            "<activeSession>"
            "<calling_station_id>AA:BB:CC:DD:EE:FF</calling_station_id>"
            "</activeSession>"
            "</activeList>"
        )
        mock_session_resp = MagicMock()
        mock_session_resp.text = sessions_xml

        # Session list succeeds, quarantine check fails
        action.http_request = AsyncMock(
            side_effect=[mock_session_resp, httpx.ConnectError("timeout")]
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["sessions"][0]["is_quarantined"] == "Unknown"

    @pytest.mark.asyncio
    async def test_missing_server(self):
        action = _make_action(GetActiveSessionsAction, settings={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetActiveSessionsAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# LIST ENDPOINTS TESTS
# ============================================================================


class TestListEndpointsAction:
    """Test the list_endpoints action."""

    @pytest.fixture
    def action(self):
        return _make_action(ListEndpointsAction, credentials=ERS_CREDENTIALS)

    @pytest.mark.asyncio
    async def test_success(self, action):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "SearchResult": {
                "total": 2,
                "resources": [
                    {"id": "abc-123", "name": "AA:BB:CC:DD:EE:FF"},
                    {"id": "def-456", "name": "11:22:33:44:55:66"},
                ],
            }
        }
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["endpoints_found"] == 2
        assert result["data"]["search_result"]["total"] == 2
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_with_mac_filter(self, action):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "SearchResult": {"total": 1, "resources": [{"id": "abc-123"}]}
        }
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(mac_address="AA:BB:CC:DD:EE:FF")

        assert result["status"] == "success"
        # Verify filter was passed in URL
        call_args = action.http_request.call_args
        assert "filter=mac.EQ.AA:BB:CC:DD:EE:FF" in call_args.kwargs["url"]

    @pytest.mark.asyncio
    async def test_missing_ers_credentials(self):
        action = _make_action(ListEndpointsAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "ERS" in result["error"]


# ============================================================================
# GET ENDPOINT BY MAC TESTS
# ============================================================================


class TestGetEndpointByMacAction:
    """Test the get_endpoint_by_mac action."""

    @pytest.fixture
    def action(self):
        return _make_action(GetEndpointByMacAction, credentials=ERS_CREDENTIALS)

    @pytest.mark.asyncio
    async def test_success(self, action):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "ERSEndPoint": {
                "id": "abc-123",
                "mac": "AA:BB:CC:DD:EE:FF",
                "name": "AA:BB:CC:DD:EE:FF",
                "groupId": "group-1",
            }
        }
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(endpoint_id="abc-123")

        assert result["status"] == "success"
        assert result["data"]["ERSEndPoint"]["mac"] == "AA:BB:CC:DD:EE:FF"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_not_found_returns_success(self, action):
        mock_response = MagicMock()
        mock_response.status_code = 404
        error = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute(endpoint_id="nonexistent-id")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["endpoint_id"] == "nonexistent-id"

    @pytest.mark.asyncio
    async def test_missing_endpoint_id(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "endpoint_id" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_http_error_non_404(self, action):
        mock_response = MagicMock()
        mock_response.status_code = 500
        error = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_response
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute(endpoint_id="abc-123")

        assert result["status"] == "error"
        assert result["error_type"] == "CiscoISEAPIError"


# ============================================================================
# QUARANTINE ENDPOINT TESTS
# ============================================================================


class TestQuarantineEndpointAction:
    """Test the quarantine_endpoint action."""

    @pytest.fixture
    def action(self):
        return _make_action(QuarantineEndpointAction, credentials=ERS_CREDENTIALS)

    @pytest.mark.asyncio
    async def test_success_with_mac(self, action):
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(
            ip_mac_address="AA:BB:CC:DD:EE:FF",
            policy_name="quarantine",
        )

        assert result["status"] == "success"
        assert result["data"]["policy_name"] == "quarantine"
        assert result["data"]["ip_mac_address"] == "AA:BB:CC:DD:EE:FF"
        assert "integration_id" in result

        # Verify macAddress was used in the payload
        call_args = action.http_request.call_args
        payload = call_args.kwargs["json_data"]
        addr_entry = payload["OperationAdditionalData"]["additionalData"][0]
        assert addr_entry["name"] == "macAddress"

    @pytest.mark.asyncio
    async def test_success_with_ip(self, action):
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(
            ip_mac_address="10.1.1.100",
            policy_name="quarantine",
        )

        assert result["status"] == "success"

        # Verify ipAddress was used in the payload
        call_args = action.http_request.call_args
        payload = call_args.kwargs["json_data"]
        addr_entry = payload["OperationAdditionalData"]["additionalData"][0]
        assert addr_entry["name"] == "ipAddress"

    @pytest.mark.asyncio
    async def test_missing_ip_mac_address(self, action):
        result = await action.execute(policy_name="quarantine")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_policy_name(self, action):
        result = await action.execute(ip_mac_address="AA:BB:CC:DD:EE:FF")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(QuarantineEndpointAction, credentials={})
        result = await action.execute(
            ip_mac_address="AA:BB:CC:DD:EE:FF", policy_name="q"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        mock_response = MagicMock()
        mock_response.status_code = 500
        error = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_response
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute(
            ip_mac_address="AA:BB:CC:DD:EE:FF",
            policy_name="quarantine",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "CiscoISEAPIError"


# ============================================================================
# RELEASE ENDPOINT TESTS
# ============================================================================


class TestReleaseEndpointAction:
    """Test the release_endpoint action."""

    @pytest.fixture
    def action(self):
        return _make_action(ReleaseEndpointAction, credentials=ERS_CREDENTIALS)

    @pytest.mark.asyncio
    async def test_success_with_mac(self, action):
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(
            ip_mac_address="AA:BB:CC:DD:EE:FF",
            policy_name="quarantine",
        )

        assert result["status"] == "success"
        assert result["data"]["message"] == "Policy cleared"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_success_with_ip(self, action):
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(
            ip_mac_address="192.168.1.50",
            policy_name="quarantine",
        )

        assert result["status"] == "success"

        call_args = action.http_request.call_args
        payload = call_args.kwargs["json_data"]
        addr_entry = payload["OperationAdditionalData"]["additionalData"][0]
        assert addr_entry["name"] == "ipAddress"

    @pytest.mark.asyncio
    async def test_missing_ip_mac_address(self, action):
        result = await action.execute(policy_name="quarantine")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_policy_name(self, action):
        result = await action.execute(ip_mac_address="AA:BB:CC:DD:EE:FF")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ReleaseEndpointAction, credentials={})
        result = await action.execute(
            ip_mac_address="AA:BB:CC:DD:EE:FF", policy_name="q"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        mock_response = MagicMock()
        mock_response.status_code = 403
        error = httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_response
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute(
            ip_mac_address="AA:BB:CC:DD:EE:FF",
            policy_name="quarantine",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "CiscoISEAPIError"
