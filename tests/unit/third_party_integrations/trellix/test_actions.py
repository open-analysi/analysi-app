"""Unit tests for Trellix EDR integration actions.

All actions use the base-class ``http_request()`` helper which applies
``integration_retry_policy`` automatically. Tests mock at the
``IntegrationAction.http_request`` level so retry behaviour is transparent.

Auth flow: Each action first GETs /hx/api/v3/token with basic auth, receives
the token in the x-feapi-token response header, then makes the real API call.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.trellix.actions import (
    AddIocAction,
    GetAlertAction,
    GetEndpointAction,
    GetFileAcquisitionAction,
    HealthCheckAction,
    ListAlertsAction,
    ListEndpointsAction,
    QuarantineEndpointAction,
    SearchIocsAction,
    UnquarantineEndpointAction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_BASE_URL = "https://hx.test.com"
TEST_PORT = 3000
AUTH_TOKEN = "test-feapi-token-abc123"


def _default_settings() -> dict:
    return {"base_url": TEST_BASE_URL, "port": TEST_PORT}


def _default_credentials() -> dict:
    return {"username": "admin", "password": "secret"}


def _auth_response() -> MagicMock:
    """Build a mock auth response (204 with token in header)."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 204
    resp.headers = {"x-feapi-token": AUTH_TOKEN}
    resp.text = ""
    return resp


def _json_response(data: dict, status_code: int = 200) -> MagicMock:
    """Build a fake httpx.Response for http_request mock."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    resp.text = '{"data": {}}'
    resp.headers = {"Content-Type": "application/json"}
    return resp


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Build a fake HTTPStatusError for testing error paths."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.text = f"Error {status_code}"
    mock_request = MagicMock(spec=httpx.Request)
    return httpx.HTTPStatusError(
        message=f"HTTP {status_code}",
        request=mock_request,
        response=mock_response,
    )


def _mock_auth_then_call(action, api_response):
    """Set up http_request to return auth response first, then API response.

    Most Trellix actions make two HTTP calls:
    1. GET /hx/api/v3/token (auth)
    2. The actual API call

    This helper makes http_request return the auth token on the first call
    and the provided api_response on the second call.
    """
    action.http_request = AsyncMock(side_effect=[_auth_response(), api_response])


def _mock_auth_then_error(action, error):
    """Set up http_request to auth successfully then raise error."""
    action.http_request = AsyncMock(side_effect=[_auth_response(), error])


def _mock_auth_failure(action, error):
    """Set up http_request to fail on auth."""
    action.http_request = AsyncMock(side_effect=error)


# ===========================================================================
# HealthCheckAction
# ===========================================================================


class TestHealthCheckAction:
    @pytest.fixture
    def action(self):
        return HealthCheckAction(
            integration_id="trellix",
            action_id="health_check",
            settings=_default_settings(),
            credentials=_default_credentials(),
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        action.http_request = AsyncMock(return_value=_auth_response())
        result = await action.execute()
        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = HealthCheckAction(
            integration_id="trellix",
            action_id="health_check",
            settings=_default_settings(),
            credentials={},
        )
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_missing_base_url(self):
        action = HealthCheckAction(
            integration_id="trellix",
            action_id="health_check",
            settings={},
            credentials=_default_credentials(),
        )
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_auth_failure_401(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(401))
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "AuthenticationError"

    @pytest.mark.asyncio
    async def test_no_token_in_response(self, action):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 204
        resp.headers = {}  # No token header
        resp.text = ""
        action.http_request = AsyncMock(return_value=resp)
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "AuthenticationError"

    @pytest.mark.asyncio
    async def test_connection_error(self, action):
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        result = await action.execute()
        assert result["status"] == "error"
        assert "integration_id" in result


# ===========================================================================
# GetEndpointAction
# ===========================================================================


class TestGetEndpointAction:
    @pytest.fixture
    def action(self):
        return GetEndpointAction(
            integration_id="trellix",
            action_id="get_endpoint",
            settings=_default_settings(),
            credentials=_default_credentials(),
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_resp = _json_response(
            {
                "data": {
                    "hostname": "workstation-01",
                    "primaryIpAddress": "10.0.1.5",
                    "OS": "Windows 10 Enterprise",
                    "domain": "corp.example.com",
                    "MAC": "aa-bb-cc-dd-ee-ff",
                }
            }
        )
        _mock_auth_then_call(action, api_resp)

        result = await action.execute(agent_id="AGENT123")
        assert result["status"] == "success"
        assert result["data"]["hostname"] == "workstation-01"
        assert result["data"]["primary_ip"] == "10.0.1.5"
        assert result["data"]["os"] == "Windows 10 Enterprise"
        assert result["data"]["agent_id"] == "AGENT123"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_agent_id(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "agent_id" in result["error"]

    @pytest.mark.asyncio
    async def test_not_found_404(self, action):
        _mock_auth_then_error(action, _http_status_error(404))
        result = await action.execute(agent_id="NONEXISTENT")
        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["agent_id"] == "NONEXISTENT"

    @pytest.mark.asyncio
    async def test_auth_failure(self, action):
        _mock_auth_failure(action, _http_status_error(401))
        result = await action.execute(agent_id="AGENT123")
        assert result["status"] == "error"
        assert result["error_type"] == "AuthenticationError"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        _mock_auth_then_error(action, _http_status_error(500))
        result = await action.execute(agent_id="AGENT123")
        assert result["status"] == "error"
        assert "integration_id" in result


# ===========================================================================
# ListEndpointsAction
# ===========================================================================


class TestListEndpointsAction:
    @pytest.fixture
    def action(self):
        return ListEndpointsAction(
            integration_id="trellix",
            action_id="list_endpoints",
            settings=_default_settings(),
            credentials=_default_credentials(),
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_resp = _json_response(
            {
                "data": {
                    "total": 2,
                    "entries": [
                        {"_id": "A1", "hostname": "host-a"},
                        {"_id": "A2", "hostname": "host-b"},
                    ],
                }
            }
        )
        _mock_auth_then_call(action, api_resp)

        result = await action.execute()
        assert result["status"] == "success"
        assert result["data"]["total"] == 2
        assert len(result["data"]["entries"]) == 2

    @pytest.mark.asyncio
    async def test_with_search(self, action):
        api_resp = _json_response({"data": {"total": 1, "entries": [{"_id": "A1"}]}})
        _mock_auth_then_call(action, api_resp)

        result = await action.execute(search="host-a")
        assert result["status"] == "success"
        # Verify search param was passed
        call_kwargs = action.http_request.call_args_list[1]
        assert "search" in call_kwargs.kwargs.get("params", {})

    @pytest.mark.asyncio
    async def test_invalid_limit(self, action):
        _mock_auth_then_call(action, _json_response({"data": {}}))
        result = await action.execute(limit="not-a-number")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_negative_limit(self, action):
        _mock_auth_then_call(action, _json_response({"data": {}}))
        result = await action.execute(limit=-5)
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = ListEndpointsAction(
            integration_id="trellix",
            action_id="list_endpoints",
            settings=_default_settings(),
            credentials={},
        )
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# QuarantineEndpointAction
# ===========================================================================


class TestQuarantineEndpointAction:
    @pytest.fixture
    def action(self):
        return QuarantineEndpointAction(
            integration_id="trellix",
            action_id="quarantine_endpoint",
            settings=_default_settings(),
            credentials=_default_credentials(),
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_resp = _json_response(
            {
                "message": "Accepted",
                "route": "/hx/api/v3/hosts/AGENT123/containment",
            }
        )
        _mock_auth_then_call(action, api_resp)

        result = await action.execute(agent_id="AGENT123")
        assert result["status"] == "success"
        assert result["data"]["agent_id"] == "AGENT123"
        assert result["data"]["message"] == "Accepted"

    @pytest.mark.asyncio
    async def test_missing_agent_id(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_already_contained_409(self, action):
        _mock_auth_then_error(action, _http_status_error(409))
        result = await action.execute(agent_id="AGENT123")
        assert result["status"] == "success"
        assert "already contained" in result["data"]["message"]

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        _mock_auth_then_error(action, _http_status_error(500))
        result = await action.execute(agent_id="AGENT123")
        assert result["status"] == "error"


# ===========================================================================
# UnquarantineEndpointAction
# ===========================================================================


class TestUnquarantineEndpointAction:
    @pytest.fixture
    def action(self):
        return UnquarantineEndpointAction(
            integration_id="trellix",
            action_id="unquarantine_endpoint",
            settings=_default_settings(),
            credentials=_default_credentials(),
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 204
        resp.text = ""
        resp.headers = {"Content-Type": "application/json"}
        _mock_auth_then_call(action, resp)

        result = await action.execute(agent_id="AGENT123")
        assert result["status"] == "success"
        assert result["data"]["agent_id"] == "AGENT123"

    @pytest.mark.asyncio
    async def test_missing_agent_id(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_not_contained_404(self, action):
        _mock_auth_then_error(action, _http_status_error(404))
        result = await action.execute(agent_id="AGENT123")
        assert result["status"] == "success"
        assert "not currently contained" in result["data"]["message"]


# ===========================================================================
# GetAlertAction
# ===========================================================================


class TestGetAlertAction:
    @pytest.fixture
    def action(self):
        return GetAlertAction(
            integration_id="trellix",
            action_id="get_alert",
            settings=_default_settings(),
            credentials=_default_credentials(),
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_resp = _json_response(
            {
                "data": {
                    "_id": 42,
                    "event_type": "malware",
                    "source": "IOC",
                    "agent": {"_id": "AGENT123", "hostname": "workstation-01"},
                }
            }
        )
        _mock_auth_then_call(action, api_resp)

        result = await action.execute(alert_id="42")
        assert result["status"] == "success"
        assert result["data"]["_id"] == 42
        assert result["data"]["event_type"] == "malware"

    @pytest.mark.asyncio
    async def test_missing_alert_id(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "alert_id" in result["error"]

    @pytest.mark.asyncio
    async def test_not_found_404(self, action):
        _mock_auth_then_error(action, _http_status_error(404))
        result = await action.execute(alert_id="99999")
        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["alert_id"] == "99999"


# ===========================================================================
# ListAlertsAction
# ===========================================================================


class TestListAlertsAction:
    @pytest.fixture
    def action(self):
        return ListAlertsAction(
            integration_id="trellix",
            action_id="list_alerts",
            settings=_default_settings(),
            credentials=_default_credentials(),
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_resp = _json_response(
            {
                "data": {
                    "total": 5,
                    "entries": [
                        {"_id": 1, "event_type": "malware"},
                        {"_id": 2, "event_type": "exploit"},
                    ],
                }
            }
        )
        _mock_auth_then_call(action, api_resp)

        result = await action.execute()
        assert result["status"] == "success"
        assert result["data"]["total"] == 5
        assert len(result["data"]["entries"]) == 2

    @pytest.mark.asyncio
    async def test_with_filters(self, action):
        api_resp = _json_response({"data": {"total": 1, "entries": []}})
        _mock_auth_then_call(action, api_resp)

        result = await action.execute(
            limit=10,
            offset=0,
            sort="reported_at+descending",
            agent_id="AGENT123",
        )
        assert result["status"] == "success"
        # Verify filter params were passed
        call_kwargs = action.http_request.call_args_list[1]
        params = call_kwargs.kwargs.get("params", {})
        assert params.get("limit") == 10
        assert params.get("sort") == "reported_at+descending"
        assert params.get("agent._id") == "AGENT123"

    @pytest.mark.asyncio
    async def test_invalid_limit(self, action):
        _mock_auth_then_call(action, _json_response({"data": {}}))
        result = await action.execute(limit="abc")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_offset(self, action):
        _mock_auth_then_call(action, _json_response({"data": {}}))
        result = await action.execute(offset="xyz")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# ===========================================================================
# SearchIocsAction
# ===========================================================================


class TestSearchIocsAction:
    @pytest.fixture
    def action(self):
        return SearchIocsAction(
            integration_id="trellix",
            action_id="search_iocs",
            settings=_default_settings(),
            credentials=_default_credentials(),
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_resp = _json_response(
            {
                "data": {
                    "total": 3,
                    "entries": [
                        {"name": "evil_domain", "category": "custom"},
                    ],
                }
            }
        )
        _mock_auth_then_call(action, api_resp)

        result = await action.execute(search="evil")
        assert result["status"] == "success"
        assert result["data"]["total"] == 3

    @pytest.mark.asyncio
    async def test_with_category_filter(self, action):
        api_resp = _json_response({"data": {"total": 0, "entries": []}})
        _mock_auth_then_call(action, api_resp)

        result = await action.execute(category="mandiant_unrestricted")
        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args_list[1]
        params = call_kwargs.kwargs.get("params", {})
        assert params.get("category") == "mandiant_unrestricted"

    @pytest.mark.asyncio
    async def test_connection_error(self, action):
        _mock_auth_then_error(action, httpx.ConnectError("Connection refused"))
        result = await action.execute()
        assert result["status"] == "error"


# ===========================================================================
# AddIocAction
# ===========================================================================


class TestAddIocAction:
    @pytest.fixture
    def action(self):
        return AddIocAction(
            integration_id="trellix",
            action_id="add_ioc",
            settings=_default_settings(),
            credentials=_default_credentials(),
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_resp = _json_response(
            {
                "data": {
                    "_id": 100,
                    "name": "test_indicator",
                    "category": "custom",
                }
            }
        )
        _mock_auth_then_call(action, api_resp)

        result = await action.execute(
            category="custom",
            name="test_indicator",
            description="A test IOC",
        )
        assert result["status"] == "success"
        assert result["data"]["category"] == "custom"
        assert result["data"]["name"] == "test_indicator"
        # Verify POST was used with json_data
        call_kwargs = action.http_request.call_args_list[1]
        assert call_kwargs.kwargs.get("method") == "POST"
        assert call_kwargs.kwargs.get("json_data", {}).get("name") == "test_indicator"

    @pytest.mark.asyncio
    async def test_missing_category(self, action):
        result = await action.execute(name="test")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "category" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_name(self, action):
        result = await action.execute(category="custom")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "name" in result["error"]


# ===========================================================================
# GetFileAcquisitionAction
# ===========================================================================


class TestGetFileAcquisitionAction:
    @pytest.fixture
    def action(self):
        return GetFileAcquisitionAction(
            integration_id="trellix",
            action_id="get_file_acquisition",
            settings=_default_settings(),
            credentials=_default_credentials(),
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_resp = _json_response(
            {
                "data": {
                    "_id": 555,
                    "state": "COMPLETE",
                    "host": {"_id": "AGENT123", "hostname": "workstation-01"},
                    "req_filename": "evil.exe",
                }
            }
        )
        _mock_auth_then_call(action, api_resp)

        result = await action.execute(acquisition_id="555")
        assert result["status"] == "success"
        assert result["data"]["_id"] == 555
        assert result["data"]["state"] == "COMPLETE"

    @pytest.mark.asyncio
    async def test_missing_acquisition_id(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "acquisition_id" in result["error"]

    @pytest.mark.asyncio
    async def test_not_found_404(self, action):
        _mock_auth_then_error(action, _http_status_error(404))
        result = await action.execute(acquisition_id="99999")
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_auth_failure(self, action):
        _mock_auth_failure(action, _http_status_error(403))
        result = await action.execute(acquisition_id="555")
        assert result["status"] == "error"
        assert result["error_type"] == "AuthenticationError"


# ===========================================================================
# Cross-cutting concerns
# ===========================================================================


class TestAuthMixin:
    """Test the shared auth mixin behaviour across actions."""

    @pytest.mark.asyncio
    async def test_token_header_set_on_api_call(self):
        """Verify the auth token is passed in x-feapi-token header."""
        action = GetEndpointAction(
            integration_id="trellix",
            action_id="get_endpoint",
            settings=_default_settings(),
            credentials=_default_credentials(),
        )
        api_resp = _json_response({"data": {"hostname": "test"}})
        _mock_auth_then_call(action, api_resp)

        await action.execute(agent_id="AGENT123")

        # Second call (API call) should have the auth token header
        call_args = action.http_request.call_args_list[1]
        headers = call_args.kwargs.get("headers", {})
        assert headers.get("x-feapi-token") == AUTH_TOKEN

    @pytest.mark.asyncio
    async def test_auth_uses_basic_auth(self):
        """Verify the auth call uses basic auth with username/password."""
        action = GetEndpointAction(
            integration_id="trellix",
            action_id="get_endpoint",
            settings=_default_settings(),
            credentials=_default_credentials(),
        )
        api_resp = _json_response({"data": {"hostname": "test"}})
        _mock_auth_then_call(action, api_resp)

        await action.execute(agent_id="AGENT123")

        # First call (auth) should have basic auth tuple
        call_args = action.http_request.call_args_list[0]
        assert call_args.kwargs.get("auth") == ("admin", "secret")


class TestBuildBaseUrl:
    """Test the _build_base_url helper."""

    def test_basic_url(self):
        from analysi.integrations.framework.integrations.trellix.actions import (
            _build_base_url,
        )

        result = _build_base_url({"base_url": "https://hx.test.com", "port": 3000})
        assert result == "https://hx.test.com:3000"

    def test_url_with_trailing_slash(self):
        from analysi.integrations.framework.integrations.trellix.actions import (
            _build_base_url,
        )

        result = _build_base_url({"base_url": "https://hx.test.com/", "port": 3000})
        assert result == "https://hx.test.com:3000"

    def test_url_already_has_port(self):
        from analysi.integrations.framework.integrations.trellix.actions import (
            _build_base_url,
        )

        result = _build_base_url({"base_url": "https://hx.test.com:3000"})
        assert result == "https://hx.test.com:3000"

    def test_missing_url(self):
        from analysi.integrations.framework.integrations.trellix.actions import (
            _build_base_url,
        )

        result = _build_base_url({})
        assert result is None
