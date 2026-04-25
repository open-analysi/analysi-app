"""Unit tests for Netskope integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.netskope.actions import (
    AddHashToListAction,
    AddUrlToListAction,
    GetFileAction,
    HealthCheckAction,
    RemoveHashFromListAction,
    RemoveUrlFromListAction,
    RunQueryAction,
    UpdateUrlListAction,
    _validate_epoch_time,
)

# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================


class TestValidateEpochTime:
    """Test epoch time validation helper."""

    def test_valid_integer(self):
        valid, msg, val = _validate_epoch_time(1700000000, "start_time")
        assert valid is True
        assert val == 1700000000

    def test_valid_float(self):
        valid, msg, val = _validate_epoch_time(1700000000.5, "start_time")
        assert valid is True
        assert val == 1700000000

    def test_valid_string_integer(self):
        valid, msg, val = _validate_epoch_time("1700000000", "end_time")
        assert valid is True
        assert val == 1700000000

    def test_none_returns_valid(self):
        valid, msg, val = _validate_epoch_time(None, "start_time")
        assert valid is True
        assert val is None

    def test_invalid_string(self):
        valid, msg, val = _validate_epoch_time("not_a_number", "start_time")
        assert valid is False
        assert "start_time" in msg
        assert val is None

    def test_negative_value(self):
        valid, msg, val = _validate_epoch_time(-100, "end_time")
        assert valid is False
        assert "negative" in msg.lower()
        assert val is None

    def test_invalid_end_time_string(self):
        valid, msg, val = _validate_epoch_time("abc", "end_time")
        assert valid is False
        assert "end_time" in msg


# ============================================================================
# FIXTURES
# ============================================================================


def _make_action(action_cls, credentials=None, settings=None):
    """Create an action instance with defaults."""
    return action_cls(
        integration_id="netskope",
        action_id=action_cls.__name__,
        settings=settings
        or {
            "server_url": "https://tenant.goskope.com",
            "timeout": 30,
            "list_name": "test_list",
        },
        credentials=credentials
        or {
            "api_key": "v1-test-key",
            "v2_api_key": "v2-test-key",
        },
    )


def _mock_response(json_data=None, status_code=200, text=""):
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = json_data or {}
    resp.status_code = status_code
    resp.text = text or ""
    return resp


def _http_status_error(status_code: int = 404) -> httpx.HTTPStatusError:
    """Create an httpx.HTTPStatusError with the given status code."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    request = MagicMock(spec=httpx.Request)
    return httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=request,
        response=response,
    )


# ============================================================================
# HEALTH CHECK
# ============================================================================


class TestHealthCheckAction:
    """Test Netskope health check action."""

    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    @pytest.mark.asyncio
    async def test_health_check_both_keys_success(self, action):
        """Test health check passes when both v1 and v2 APIs respond."""
        action.http_request = AsyncMock(return_value=_mock_response({"status": "ok"}))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert result["data"]["v1_api"] == "connected"
        assert result["data"]["v2_api"] == "connected"
        assert "integration_id" in result
        assert result["integration_id"] == "netskope"

    @pytest.mark.asyncio
    async def test_health_check_v1_only(self):
        """Test health check with only v1 API key."""
        action = _make_action(
            HealthCheckAction,
            credentials={
                "api_key": "v1-test-key",
            },
        )
        action.http_request = AsyncMock(return_value=_mock_response({"status": "ok"}))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["v1_api"] == "connected"
        assert "v2_api" not in result["data"]

    @pytest.mark.asyncio
    async def test_health_check_v2_only(self):
        """Test health check with only v2 API key."""
        action = _make_action(
            HealthCheckAction,
            credentials={
                "v2_api_key": "v2-test-key",
            },
        )
        action.http_request = AsyncMock(return_value=_mock_response({"status": "ok"}))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["v2_api"] == "connected"
        assert "v1_api" not in result["data"]

    @pytest.mark.asyncio
    async def test_health_check_missing_server_url(self):
        """Test health check fails without server URL."""
        action = _make_action(
            HealthCheckAction,
            credentials={
                "api_key": "v1-test-key",
            },
            settings={"timeout": 30, "list_name": "test_list"},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert "server_url" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_health_check_missing_all_keys(self):
        """Test health check fails without any API keys."""
        action = _make_action(
            HealthCheckAction,
            credentials={"_placeholder": True},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_health_check_both_fail(self):
        """Test health check returns error when both APIs fail."""
        action = _make_action(HealthCheckAction)
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert "failed" in result["data"]["v1_api"]
        assert "failed" in result["data"]["v2_api"]

    @pytest.mark.asyncio
    async def test_health_check_v1_fails_v2_succeeds(self):
        """Test health check succeeds if at least one API connects."""
        action = _make_action(HealthCheckAction)

        call_count = 0

        async def mock_request(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("Connection refused")
            return _mock_response({"status": "ok"})

        action.http_request = mock_request

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True


# ============================================================================
# ADD URL TO LIST
# ============================================================================


class TestAddUrlToListAction:
    """Test add URL to list action."""

    @pytest.fixture
    def action(self):
        return _make_action(AddUrlToListAction)

    @pytest.mark.asyncio
    async def test_add_url_success(self, action):
        """Test successfully adding a URL to the list."""
        # Mock: 1) list lookup, 2) get list data, 3) patch replace, 4) deploy
        responses = [
            _mock_response([{"id": 42, "name": "test_list"}]),  # list lookup
            _mock_response(
                {"data": {"urls": ["existing.com"], "type": "exact"}}
            ),  # get list
            _mock_response({"status": "ok"}),  # patch replace
            _mock_response({"status": "ok"}),  # deploy
        ]
        action.http_request = AsyncMock(side_effect=responses)

        result = await action.execute(url="malicious.com")

        assert result["status"] == "success"
        assert result["data"]["total_urls"] == 2
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_add_url_already_exists(self, action):
        """Test adding a URL that already exists."""
        responses = [
            _mock_response([{"id": 42, "name": "test_list"}]),
            _mock_response({"data": {"urls": ["malicious.com"], "type": "exact"}}),
        ]
        action.http_request = AsyncMock(side_effect=responses)

        result = await action.execute(url="malicious.com")

        assert result["status"] == "success"
        assert "already exists" in result["data"]["message"]

    @pytest.mark.asyncio
    async def test_add_url_missing_param(self, action):
        """Test add URL fails without URL parameter."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_add_url_missing_credentials(self):
        """Test add URL fails without v2 API key."""
        action = _make_action(
            AddUrlToListAction,
            credentials={"api_key": "v1-only"},
        )

        result = await action.execute(url="malicious.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_add_url_list_not_found(self, action):
        """Test add URL fails when list name doesn't exist."""
        action.http_request = AsyncMock(
            return_value=_mock_response([{"id": 99, "name": "other_list"}])
        )

        result = await action.execute(url="malicious.com")

        assert result["status"] == "error"
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_add_url_http_error(self, action):
        """Test add URL handles HTTP errors."""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Server error", request=MagicMock(), response=mock_resp
            )
        )

        result = await action.execute(url="malicious.com")

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_add_url_404_returns_not_found(self, action):
        """Test add URL returns not_found on 404 (e.g., list deleted mid-request)."""
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(url="malicious.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["url"] == "malicious.com"


# ============================================================================
# REMOVE URL FROM LIST
# ============================================================================


class TestRemoveUrlFromListAction:
    """Test remove URL from list action."""

    @pytest.fixture
    def action(self):
        return _make_action(RemoveUrlFromListAction)

    @pytest.mark.asyncio
    async def test_remove_url_success(self, action):
        """Test successfully removing a URL from the list."""
        responses = [
            _mock_response([{"id": 42, "name": "test_list"}]),
            _mock_response(
                {"data": {"urls": ["malicious.com", "safe.com"], "type": "exact"}}
            ),
            _mock_response({"status": "ok"}),
            _mock_response({"status": "ok"}),
        ]
        action.http_request = AsyncMock(side_effect=responses)

        result = await action.execute(url="malicious.com")

        assert result["status"] == "success"
        assert result["data"]["total_urls"] == 1
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_remove_url_not_in_list(self, action):
        """Test removing a URL that doesn't exist in the list."""
        responses = [
            _mock_response([{"id": 42, "name": "test_list"}]),
            _mock_response({"data": {"urls": ["other.com"], "type": "exact"}}),
        ]
        action.http_request = AsyncMock(side_effect=responses)

        result = await action.execute(url="malicious.com")

        assert result["status"] == "success"
        assert "does not exist" in result["data"]["message"]

    @pytest.mark.asyncio
    async def test_remove_url_missing_param(self, action):
        """Test remove URL fails without URL parameter."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_remove_url_404_returns_not_found(self, action):
        """Test remove URL returns not_found on 404."""
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(url="malicious.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["url"] == "malicious.com"


# ============================================================================
# UPDATE URL LIST
# ============================================================================


class TestUpdateUrlListAction:
    """Test update URL list action."""

    @pytest.fixture
    def action(self):
        return _make_action(UpdateUrlListAction)

    @pytest.mark.asyncio
    async def test_update_url_list_success(self, action):
        """Test successfully replacing the entire URL list."""
        responses = [
            _mock_response([{"id": 42, "name": "test_list"}]),
            _mock_response({"data": {"urls": ["old.com"], "type": "exact"}}),
            _mock_response({"status": "ok"}),  # replace
            _mock_response({"status": "ok"}),  # deploy
        ]
        action.http_request = AsyncMock(side_effect=responses)

        result = await action.execute(urls="new1.com,new2.com")

        assert result["status"] == "success"
        assert result["data"]["total_updated_urls"] == 2
        assert result["data"]["invalid_urls"] == []

    @pytest.mark.asyncio
    async def test_update_url_list_with_list_input(self, action):
        """Test update URL list with list input instead of string."""
        responses = [
            _mock_response([{"id": 42, "name": "test_list"}]),
            _mock_response({"data": {"urls": [], "type": "exact"}}),
            _mock_response({"status": "ok"}),
            _mock_response({"status": "ok"}),
        ]
        action.http_request = AsyncMock(side_effect=responses)

        result = await action.execute(urls=["url1.com", "url2.com", "url3.com"])

        assert result["status"] == "success"
        assert result["data"]["total_updated_urls"] == 3

    @pytest.mark.asyncio
    async def test_update_url_list_missing_param(self, action):
        """Test update URL list fails without URLs."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_update_url_list_empty_string(self, action):
        """Test update URL list fails with empty string."""
        result = await action.execute(urls="")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_update_url_list_404_returns_not_found(self, action):
        """Test update URL list returns not_found on 404."""
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(urls="new1.com,new2.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["list_name"] == "test_list"


# ============================================================================
# ADD HASH TO LIST
# ============================================================================


class TestAddHashToListAction:
    """Test add hash to list action."""

    @pytest.fixture
    def action(self):
        return _make_action(AddHashToListAction)

    @pytest.mark.asyncio
    async def test_add_hash_success(self, action):
        """Test successfully adding a hash to the list."""
        action.http_request = AsyncMock(return_value=_mock_response({"status": "ok"}))

        result = await action.execute(hash="abc123def456")

        assert result["status"] == "success"
        assert result["data"]["hash"] == "abc123def456"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_add_hash_missing_param(self, action):
        """Test add hash fails without hash parameter."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_add_hash_missing_v1_key(self):
        """Test add hash fails without v1 API key."""
        action = _make_action(
            AddHashToListAction,
            credentials={
                "v2_api_key": "v2-key",
            },
        )

        result = await action.execute(hash="abc123")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_add_hash_http_error(self, action):
        """Test add hash handles HTTP errors."""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Unauthorized", request=MagicMock(), response=mock_resp
            )
        )

        result = await action.execute(hash="abc123")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_add_hash_404_returns_not_found(self, action):
        """Test add hash returns not_found on 404 (e.g., hash list doesn't exist)."""
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(hash="abc123def456")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["hash"] == "abc123def456"
        assert result["data"]["list_name"] == "test_list"


# ============================================================================
# REMOVE HASH FROM LIST
# ============================================================================


class TestRemoveHashFromListAction:
    """Test remove hash from list action."""

    @pytest.fixture
    def action(self):
        return _make_action(RemoveHashFromListAction)

    @pytest.mark.asyncio
    async def test_remove_hash_success(self, action):
        """Test successfully removing a hash from the list."""
        action.http_request = AsyncMock(return_value=_mock_response({"status": "ok"}))

        result = await action.execute(hash="abc123def456")

        assert result["status"] == "success"
        assert result["data"]["hash"] == "abc123def456"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_remove_hash_missing_param(self, action):
        """Test remove hash fails without hash parameter."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_remove_hash_missing_v1_key(self):
        """Test remove hash fails without v1 API key."""
        action = _make_action(
            RemoveHashFromListAction,
            credentials={"v2_api_key": "v2-only"},
        )

        result = await action.execute(hash="abc123")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_remove_hash_404_returns_not_found(self):
        """Test remove hash returns not_found on 404."""
        action = _make_action(RemoveHashFromListAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(hash="abc123def456")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["hash"] == "abc123def456"
        assert result["data"]["list_name"] == "test_list"


# ============================================================================
# GET FILE (QUARANTINE)
# ============================================================================


class TestGetFileAction:
    """Test get file from quarantine action."""

    @pytest.fixture
    def action(self):
        return _make_action(GetFileAction)

    @pytest.mark.asyncio
    async def test_get_file_success(self, action):
        """Test successfully finding a quarantined file."""
        quarantine_response = {
            "data": {
                "quarantined": [
                    {
                        "quarantine_profile_id": "profile-1",
                        "quarantine_profile_name": "Default Profile",
                        "files": [
                            {
                                "file_id": "file-123",
                                "quarantined_file_name": "malware.exe",
                            }
                        ],
                    }
                ]
            }
        }
        action.http_request = AsyncMock(
            return_value=_mock_response(quarantine_response)
        )

        result = await action.execute(file="file-123", profile="profile-1")

        assert result["status"] == "success"
        assert result["data"]["file_id"] == "file-123"
        assert result["data"]["file_name"] == "malware.exe"
        assert result["data"]["profile_id"] == "profile-1"

    @pytest.mark.asyncio
    async def test_get_file_by_name(self, action):
        """Test finding file by name instead of ID."""
        quarantine_response = {
            "data": {
                "quarantined": [
                    {
                        "quarantine_profile_id": "p1",
                        "quarantine_profile_name": "Test Profile",
                        "files": [
                            {
                                "file_id": "f1",
                                "quarantined_file_name": "eicar.com",
                            }
                        ],
                    }
                ]
            }
        }
        action.http_request = AsyncMock(
            return_value=_mock_response(quarantine_response)
        )

        result = await action.execute(file="eicar.com", profile="Test Profile")

        assert result["status"] == "success"
        assert result["data"]["file_id"] == "f1"

    @pytest.mark.asyncio
    async def test_get_file_not_found(self, action):
        """Test file not found returns success with not_found flag."""
        quarantine_response = {"data": {"quarantined": []}}
        action.http_request = AsyncMock(
            return_value=_mock_response(quarantine_response)
        )

        result = await action.execute(file="nonexistent", profile="profile-1")

        assert result["status"] == "success"
        assert result.get("not_found") is True

    @pytest.mark.asyncio
    async def test_get_file_no_profile_match(self, action):
        """Test file not found when profile doesn't match."""
        quarantine_response = {
            "data": {
                "quarantined": [
                    {
                        "quarantine_profile_id": "other-profile",
                        "quarantine_profile_name": "Other",
                        "files": [
                            {"file_id": "f1", "quarantined_file_name": "test.exe"}
                        ],
                    }
                ]
            }
        }
        action.http_request = AsyncMock(
            return_value=_mock_response(quarantine_response)
        )

        result = await action.execute(file="f1", profile="nonexistent-profile")

        assert result["status"] == "success"
        assert result.get("not_found") is True

    @pytest.mark.asyncio
    async def test_get_file_missing_params(self, action):
        """Test get file fails without required parameters."""
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

        result = await action.execute(file="f1")
        assert result["status"] == "error"

        result = await action.execute(profile="p1")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_get_file_missing_v1_key(self):
        """Test get file fails without v1 API key."""
        action = _make_action(
            GetFileAction,
            credentials={
                "v2_api_key": "v2-key",
            },
        )

        result = await action.execute(file="f1", profile="p1")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_get_file_404_returns_not_found(self, action):
        """Test get file returns not_found on HTTP 404."""
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(file="file-123", profile="profile-1")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["file"] == "file-123"
        assert result["data"]["profile"] == "profile-1"


# ============================================================================
# RUN QUERY
# ============================================================================


class TestRunQueryAction:
    """Test run query action."""

    @pytest.fixture
    def action(self):
        return _make_action(RunQueryAction)

    @pytest.mark.asyncio
    async def test_run_query_success(self, action):
        """Test successfully querying events by IP."""
        # Two calls: page events, application events
        page_response = _mock_response({"result": [{"event": "page1"}]})
        app_response = _mock_response({"result": [{"event": "app1"}]})
        # Second call for each returns empty to end pagination
        empty_response = _mock_response({"result": []})

        action.http_request = AsyncMock(
            side_effect=[page_response, empty_response, app_response, empty_response]
        )

        result = await action.execute(
            ip="10.0.0.1", start_time=1700000000, end_time=1700086400
        )

        assert result["status"] == "success"
        assert result["data"]["total_page_events"] == 1
        assert result["data"]["total_application_events"] == 1
        assert result["data"]["ip"] == "10.0.0.1"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_run_query_no_events(self, action):
        """Test query returns not_found when no events exist."""
        empty_response = _mock_response({"result": []})
        action.http_request = AsyncMock(return_value=empty_response)

        result = await action.execute(
            ip="192.168.1.1", start_time=1700000000, end_time=1700086400
        )

        assert result["status"] == "success"
        assert result.get("not_found") is True
        assert result["data"]["total_page_events"] == 0
        assert result["data"]["total_application_events"] == 0

    @pytest.mark.asyncio
    async def test_run_query_missing_ip(self, action):
        """Test query fails without IP parameter."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_run_query_invalid_start_time(self, action):
        """Test query fails with invalid start time."""
        result = await action.execute(ip="10.0.0.1", start_time="invalid")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_run_query_invalid_time_range(self, action):
        """Test query fails when start_time >= end_time."""
        result = await action.execute(
            ip="10.0.0.1", start_time=2000000000, end_time=1000000000
        )

        assert result["status"] == "error"
        assert "time range" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_run_query_negative_time(self, action):
        """Test query fails with negative time value."""
        result = await action.execute(
            ip="10.0.0.1", start_time=-100, end_time=1700000000
        )

        assert result["status"] == "error"
        assert "negative" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_run_query_missing_v2_key(self):
        """Test query fails without v2 API key."""
        action = _make_action(
            RunQueryAction,
            credentials={
                "api_key": "v1-key",
            },
        )

        result = await action.execute(ip="10.0.0.1")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_run_query_default_time_range(self, action):
        """Test query uses default 24h time range when start_time is not provided."""
        empty_response = _mock_response({"result": []})
        action.http_request = AsyncMock(return_value=empty_response)

        result = await action.execute(ip="10.0.0.1")

        # Should not fail — start_time defaults to end_time - 24h
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_run_query_http_error(self, action):
        """Test query handles HTTP errors."""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"
        action.http_request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Forbidden", request=MagicMock(), response=mock_resp
            )
        )

        result = await action.execute(
            ip="10.0.0.1", start_time=1700000000, end_time=1700086400
        )

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_run_query_404_returns_not_found(self, action):
        """Test query returns not_found on HTTP 404."""
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(
            ip="10.0.0.1", start_time=1700000000, end_time=1700086400
        )

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["ip"] == "10.0.0.1"
