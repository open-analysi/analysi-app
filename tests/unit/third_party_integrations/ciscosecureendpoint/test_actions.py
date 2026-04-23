"""Unit tests for Cisco Secure Endpoint integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.ciscosecureendpoint.actions import (
    GetComputerAction,
    GetFileAnalysisAction,
    HealthCheckAction,
    IsolateHostAction,
    ListEventsAction,
    UnisolateHostAction,
    _build_auth_header,
    _build_base_url,
    _validate_uuid4,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

VALID_GUID = "71841cfb-1892-46b5-b7d7-b18d068246b4"
INVALID_GUID = "not-a-valid-uuid"

VALID_CREDENTIALS = {"api_client_id": "test-client-id", "api_key": "test-api-key"}
VALID_SETTINGS = {"base_url": "https://api.amp.cisco.com", "timeout": 30}


_SENTINEL = object()


def _make_action(cls, *, credentials=_SENTINEL, settings=_SENTINEL):
    """Helper to instantiate an action with test defaults."""
    return cls(
        integration_id="ciscosecureendpoint",
        action_id=cls.__name__.replace("Action", "").lower(),
        settings=VALID_SETTINGS.copy() if settings is _SENTINEL else settings,
        credentials=VALID_CREDENTIALS.copy()
        if credentials is _SENTINEL
        else credentials,
    )


def _mock_response(json_data=None, status_code=200):
    """Create a mock httpx response."""
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = json_data or {}
    resp.status_code = status_code
    resp.text = str(json_data)
    return resp


def _mock_http_status_error(status_code: int):
    """Create a mock httpx.HTTPStatusError."""
    request = MagicMock(spec=httpx.Request)
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    return httpx.HTTPStatusError(
        f"HTTP {status_code}", request=request, response=response
    )


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    """Test helper functions."""

    def test_build_base_url_default(self):
        """Test default base URL is used when not configured."""
        assert _build_base_url({}) == "https://api.amp.cisco.com"

    def test_build_base_url_custom(self):
        """Test custom base URL with trailing slash stripped."""
        assert (
            _build_base_url({"base_url": "https://custom.api.com/"})
            == "https://custom.api.com"
        )

    def test_build_auth_header(self):
        """Test Basic Auth header is constructed correctly."""
        headers = _build_auth_header({"api_client_id": "myid", "api_key": "mykey"})
        # base64("myid:mykey") = "bXlpZDpteWtleQ=="
        assert headers["Authorization"] == "Basic bXlpZDpteWtleQ=="
        assert headers["Accept"] == "application/json"
        assert headers["Content-Type"] == "application/json"

    def test_validate_uuid4_valid(self):
        """Test valid UUID4 passes validation."""
        assert _validate_uuid4(VALID_GUID) is True

    def test_validate_uuid4_invalid(self):
        """Test invalid string fails UUID4 validation."""
        assert _validate_uuid4(INVALID_GUID) is False

    def test_validate_uuid4_none(self):
        """Test None fails UUID4 validation."""
        assert _validate_uuid4(None) is False


# ---------------------------------------------------------------------------
# HealthCheckAction
# ---------------------------------------------------------------------------


class TestHealthCheckAction:
    """Test health check action."""

    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Test successful health check returns healthy data."""
        action.http_request = AsyncMock(return_value=_mock_response({"version": "v1"}))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert result["data"]["api_version"] == "v1"
        assert "integration_id" in result
        action.http_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Test health check fails gracefully with missing credentials."""
        action = _make_action(HealthCheckAction, credentials={})

        result = await action.execute()

        assert result["status"] == "error"
        assert "credentials" in result["error"].lower()
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_missing_client_id_only(self):
        """Test health check fails when only api_key is provided."""
        action = _make_action(HealthCheckAction, credentials={"api_key": "key"})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        """Test health check handles API errors."""
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(500))

        result = await action.execute()

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_connection_error(self, action):
        """Test health check handles connection errors."""
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection failed")
        )

        result = await action.execute()

        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# IsolateHostAction
# ---------------------------------------------------------------------------


class TestIsolateHostAction:
    """Test isolate host action."""

    @pytest.fixture
    def action(self):
        return _make_action(IsolateHostAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Test successful host isolation."""
        action.http_request = AsyncMock(
            return_value=_mock_response(
                {"data": {"status": "pending_start"}, "version": "v1.2.0"}
            )
        )

        result = await action.execute(connector_guid=VALID_GUID)

        assert result["status"] == "success"
        assert "integration_id" in result
        assert result["data"]["data"]["status"] == "pending_start"
        action.http_request.assert_called_once()
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["method"] == "PUT"
        assert "/isolation" in call_kwargs["url"]

    @pytest.mark.asyncio
    async def test_missing_connector_guid(self, action):
        """Test isolation fails with missing connector_guid."""
        result = await action.execute()

        assert result["status"] == "error"
        assert "connector_guid" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_connector_guid(self, action):
        """Test isolation fails with invalid UUID."""
        result = await action.execute(connector_guid=INVALID_GUID)

        assert result["status"] == "error"
        assert "validation" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Test isolation fails with missing credentials."""
        action = _make_action(IsolateHostAction, credentials={})

        result = await action.execute(connector_guid=VALID_GUID)

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_not_found_returns_success(self, action):
        """Test 404 returns success with not_found flag."""
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(404))

        result = await action.execute(connector_guid=VALID_GUID)

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["connector_guid"] == VALID_GUID

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        """Test 500 returns error."""
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(500))

        result = await action.execute(connector_guid=VALID_GUID)

        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# UnisolateHostAction
# ---------------------------------------------------------------------------


class TestUnisolateHostAction:
    """Test unisolate host action."""

    @pytest.fixture
    def action(self):
        return _make_action(UnisolateHostAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Test successful host unisolation."""
        action.http_request = AsyncMock(
            return_value=_mock_response(
                {"data": {"status": "pending_stop"}, "version": "v1.2.0"}
            )
        )

        result = await action.execute(connector_guid=VALID_GUID)

        assert result["status"] == "success"
        assert "integration_id" in result
        assert result["data"]["data"]["status"] == "pending_stop"
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["method"] == "DELETE"

    @pytest.mark.asyncio
    async def test_missing_connector_guid(self, action):
        """Test unisolation fails with missing connector_guid."""
        result = await action.execute()

        assert result["status"] == "error"
        assert "connector_guid" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_connector_guid(self, action):
        """Test unisolation fails with invalid UUID."""
        result = await action.execute(connector_guid=INVALID_GUID)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Test unisolation fails with missing credentials."""
        action = _make_action(UnisolateHostAction, credentials={})

        result = await action.execute(connector_guid=VALID_GUID)

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_not_found_returns_success(self, action):
        """Test 404 returns success with not_found flag."""
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(404))

        result = await action.execute(connector_guid=VALID_GUID)

        assert result["status"] == "success"
        assert result["not_found"] is True


# ---------------------------------------------------------------------------
# GetComputerAction
# ---------------------------------------------------------------------------


class TestGetComputerAction:
    """Test get computer action."""

    @pytest.fixture
    def action(self):
        return _make_action(GetComputerAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Test successful computer info retrieval."""
        api_data = {
            "data": {
                "active": True,
                "connector_guid": VALID_GUID,
                "hostname": "test-host",
                "external_ip": "1.2.3.4",
                "operating_system": "Windows 10",
                "isolation": {"status": "not_isolated"},
            },
            "metadata": {"links": {"self": "https://api.amp.cisco.com/..."}},
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_data))

        result = await action.execute(connector_guid=VALID_GUID)

        assert result["status"] == "success"
        assert "integration_id" in result
        assert result["data"]["data"]["hostname"] == "test-host"
        assert result["data"]["data"]["active"] is True

    @pytest.mark.asyncio
    async def test_missing_connector_guid(self, action):
        """Test get_computer fails with missing connector_guid."""
        result = await action.execute()

        assert result["status"] == "error"
        assert "connector_guid" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_connector_guid(self, action):
        """Test get_computer fails with invalid UUID."""
        result = await action.execute(connector_guid=INVALID_GUID)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Test get_computer fails with missing credentials."""
        action = _make_action(GetComputerAction, credentials={})

        result = await action.execute(connector_guid=VALID_GUID)

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_not_found_returns_success(self, action):
        """Test 404 returns success with not_found flag."""
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(404))

        result = await action.execute(connector_guid=VALID_GUID)

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["connector_guid"] == VALID_GUID

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        """Test 500 returns error."""
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(500))

        result = await action.execute(connector_guid=VALID_GUID)

        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# ListEventsAction
# ---------------------------------------------------------------------------


class TestListEventsAction:
    """Test list events action."""

    @pytest.fixture
    def action(self):
        return _make_action(ListEventsAction)

    @pytest.mark.asyncio
    async def test_success_no_filters(self, action):
        """Test list events with no filters returns all events."""
        api_data = {
            "data": [
                {"id": 1, "event_type": "Threat Detected"},
                {"id": 2, "event_type": "File Created"},
            ],
            "metadata": {"results": {"total": 2}},
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_data))

        result = await action.execute()

        assert result["status"] == "success"
        assert "integration_id" in result
        assert result["data"]["total_events"] == 2
        assert len(result["data"]["events"]) == 2

    @pytest.mark.asyncio
    async def test_success_with_filters(self, action):
        """Test list events passes query filters correctly."""
        api_data = {"data": [{"id": 1}], "metadata": {}}
        action.http_request = AsyncMock(return_value=_mock_response(api_data))

        result = await action.execute(
            connector_guid=VALID_GUID,
            event_type="Threat Detected",
            limit=10,
        )

        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["params"]["connector_guid"] == VALID_GUID
        assert call_kwargs["params"]["event_type"] == "Threat Detected"
        assert call_kwargs["params"]["limit"] == 10

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Test list events fails with missing credentials."""
        action = _make_action(ListEventsAction, credentials={})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        """Test list events handles API errors."""
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(500))

        result = await action.execute()

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_empty_results(self, action):
        """Test list events with no matching events."""
        api_data = {"data": [], "metadata": {"results": {"total": 0}}}
        action.http_request = AsyncMock(return_value=_mock_response(api_data))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_events"] == 0
        assert result["data"]["events"] == []


# ---------------------------------------------------------------------------
# GetFileAnalysisAction
# ---------------------------------------------------------------------------


class TestGetFileAnalysisAction:
    """Test get file analysis action."""

    SAMPLE_HASH = "abc123def456" * 6  # Fake sha256

    @pytest.fixture
    def action(self):
        return _make_action(GetFileAnalysisAction)

    @pytest.mark.asyncio
    async def test_success_basic(self, action):
        """Test successful file analysis without execution check."""
        api_data = {
            "data": [
                {"connector_guid": VALID_GUID, "hostname": "host1"},
            ],
            "metadata": {"results": {"total": 1}},
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_data))

        result = await action.execute(hash=self.SAMPLE_HASH)

        assert result["status"] == "success"
        assert "integration_id" in result
        assert result["data"]["device_count"] == 1
        assert result["data"]["hash"] == self.SAMPLE_HASH
        assert len(result["data"]["endpoints"]) == 1

    @pytest.mark.asyncio
    async def test_success_with_execution_check(self, action):
        """Test file analysis with execution check enabled."""
        activity_data = {
            "data": [{"connector_guid": VALID_GUID, "hostname": "host1"}],
            "metadata": {},
        }
        trajectory_data = {
            "data": {
                "events": [
                    {
                        "event_type": "Executed by",
                        "file": {
                            "identity": {"sha256": self.SAMPLE_HASH},
                            "file_name": "malware.exe",
                            "file_path": "C:\\temp\\malware.exe",
                        },
                    }
                ]
            }
        }

        # First call: activity search, second call: trajectory
        action.http_request = AsyncMock(
            side_effect=[
                _mock_response(activity_data),
                _mock_response(trajectory_data),
            ]
        )

        result = await action.execute(hash=self.SAMPLE_HASH, check_execution=True)

        assert result["status"] == "success"
        endpoint = result["data"]["endpoints"][0]
        assert endpoint["file_execution_details"]["executed"] is True
        assert endpoint["file_execution_details"]["file_name"] == "malware.exe"

    @pytest.mark.asyncio
    async def test_success_file_not_executed(self, action):
        """Test file analysis when file was seen but not executed."""
        activity_data = {
            "data": [{"connector_guid": VALID_GUID}],
            "metadata": {},
        }
        trajectory_data = {"data": {"events": []}}

        action.http_request = AsyncMock(
            side_effect=[
                _mock_response(activity_data),
                _mock_response(trajectory_data),
            ]
        )

        result = await action.execute(hash=self.SAMPLE_HASH, check_execution=True)

        assert result["status"] == "success"
        endpoint = result["data"]["endpoints"][0]
        assert endpoint["file_execution_details"]["executed"] is False
        assert endpoint["file_execution_details"]["message"] == "File not executed"

    @pytest.mark.asyncio
    async def test_missing_hash(self, action):
        """Test file analysis fails with missing hash."""
        result = await action.execute()

        assert result["status"] == "error"
        assert "hash" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Test file analysis fails with missing credentials."""
        action = _make_action(GetFileAnalysisAction, credentials={})

        result = await action.execute(hash="abc123")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_not_found_returns_success(self, action):
        """Test 404 returns success with not_found flag."""
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(404))

        result = await action.execute(hash=self.SAMPLE_HASH)

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["hash"] == self.SAMPLE_HASH
        assert result["data"]["device_count"] == 0

    @pytest.mark.asyncio
    async def test_no_endpoints_found(self, action):
        """Test empty result when no endpoints have seen the hash."""
        api_data = {"data": [], "metadata": {"results": {"total": 0}}}
        action.http_request = AsyncMock(return_value=_mock_response(api_data))

        result = await action.execute(hash=self.SAMPLE_HASH)

        assert result["status"] == "success"
        assert result["data"]["device_count"] == 0

    @pytest.mark.asyncio
    async def test_trajectory_error_handled_gracefully(self, action):
        """Test that trajectory errors don't fail the whole action."""
        activity_data = {
            "data": [{"connector_guid": VALID_GUID}],
            "metadata": {},
        }

        action.http_request = AsyncMock(
            side_effect=[
                _mock_response(activity_data),
                Exception("Trajectory API error"),
            ]
        )

        result = await action.execute(hash=self.SAMPLE_HASH, check_execution=True)

        assert result["status"] == "success"
        endpoint = result["data"]["endpoints"][0]
        assert endpoint["file_execution_details"]["executed"] is False
        assert "Unable to retrieve" in endpoint["file_execution_details"]["message"]
