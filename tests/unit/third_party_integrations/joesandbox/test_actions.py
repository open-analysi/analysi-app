"""Unit tests for Joe Sandbox v2 integration actions.

All actions use ``self.http_request()`` (via ``_joe_api_call``) which applies
``integration_retry_policy`` automatically. Tests mock at the
``IntegrationAction.http_request`` level.

Joe Sandbox returns JSON responses, so mocked responses use ``.json()``.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.joesandbox.actions import (
    CheckStatusAction,
    DetonateUrlAction,
    FileReputationAction,
    GetCookbookAction,
    GetReportAction,
    HealthCheckAction,
    ListCookbooksAction,
    UrlReputationAction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json_response(data: dict, status_code: int = 200) -> MagicMock:
    """Build a fake httpx.Response with JSON body."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    resp.text = str(data)
    resp.headers = {"Content-Type": "application/json"}
    return resp


def _http_status_error(status_code: int, body: str = "") -> httpx.HTTPStatusError:
    """Build a fake HTTPStatusError with given status code."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.text = body or f"Error {status_code}"
    mock_request = MagicMock(spec=httpx.Request)
    return httpx.HTTPStatusError(
        message=f"HTTP {status_code}",
        request=mock_request,
        response=mock_response,
    )


def _make_action(action_class, credentials=None, settings=None):
    """Create an action instance with default test values."""
    return action_class(
        integration_id="joesandbox",
        action_id=action_class.__name__.lower().replace("action", ""),
        settings=settings if settings is not None else {},
        credentials=credentials
        if credentials is not None
        else {"api_key": "test-joe-key"},
    )


# ===========================================================================
# HealthCheckAction
# ===========================================================================


class TestHealthCheckAction:
    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        mock_resp = _json_response({"data": {"online": True}})
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert "integration_id" in result
        assert "timestamp" in result
        action.http_request.assert_called_once()

        # Verify POST with apikey in form data
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["method"] == "POST"
        assert call_kwargs["data"]["apikey"] == "test-joe-key"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(HealthCheckAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert "api_key" in result["error"]
        assert result["error_type"] == "ConfigurationError"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(401))
        result = await action.execute()

        assert result["status"] == "error"
        assert result["data"]["healthy"] is False

    @pytest.mark.asyncio
    async def test_network_error(self, action):
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert result["data"]["healthy"] is False

    @pytest.mark.asyncio
    async def test_custom_base_url(self):
        action = _make_action(
            HealthCheckAction,
            settings={"base_url": "https://custom.joesandbox.example.com"},
        )
        mock_resp = _json_response({"data": {"online": True}})
        action.http_request = AsyncMock(return_value=mock_resp)

        await action.execute()

        call_kwargs = action.http_request.call_args.kwargs
        assert (
            "custom.joesandbox.example.com/api/v2/server/online" in call_kwargs["url"]
        )


# ===========================================================================
# DetonateUrlAction
# ===========================================================================


class TestDetonateUrlAction:
    @pytest.fixture
    def action(self):
        return _make_action(DetonateUrlAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        mock_resp = _json_response(
            {
                "data": {
                    "webids": ["12345"],
                    "status": "submitted",
                }
            }
        )
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(url="https://example.com/malware")

        assert result["status"] == "success"
        assert result["data"]["url"] == "https://example.com/malware"
        assert result["data"]["webid"] == "12345"
        assert "integration_id" in result

        # Verify form data includes required fields
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["data"]["apikey"] == "test-joe-key"
        assert call_kwargs["data"]["url"] == "https://example.com/malware"
        assert call_kwargs["data"]["accept-tac"] == 1

    @pytest.mark.asyncio
    async def test_with_options(self, action):
        mock_resp = _json_response(
            {"data": {"webids": ["99999"], "status": "submitted"}}
        )
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(
            url="https://example.com",
            internet_access=True,
            report_cache=True,
        )

        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["data"]["internet-access"] == 1
        assert call_kwargs["data"]["report-cache"] == 1

    @pytest.mark.asyncio
    async def test_missing_url(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "url" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(DetonateUrlAction, credentials={})
        result = await action.execute(url="https://example.com")

        assert result["status"] == "error"
        assert "api_key" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(500))
        result = await action.execute(url="https://example.com")

        assert result["status"] == "error"


# ===========================================================================
# CheckStatusAction
# ===========================================================================


class TestCheckStatusAction:
    @pytest.fixture
    def action(self):
        return _make_action(CheckStatusAction)

    @pytest.mark.asyncio
    async def test_success_finished(self, action):
        mock_resp = _json_response(
            {
                "data": {
                    "webid": "12345",
                    "status": "finished",
                    "filename": "test.exe",
                    "runs": [{"detection": "malicious"}],
                }
            }
        )
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(webid="12345")

        assert result["status"] == "success"
        assert result["data"]["status"] == "finished"
        assert result["data"]["reputation_label"] == "malicious"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_success_pending(self, action):
        mock_resp = _json_response(
            {
                "data": {
                    "webid": "12345",
                    "status": "running",
                    "runs": [],
                }
            }
        )
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(webid="12345")

        assert result["status"] == "success"
        assert result["data"]["status"] == "running"
        assert result["data"]["reputation_label"] == "clean"

    @pytest.mark.asyncio
    async def test_missing_webid(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "webid" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(CheckStatusAction, credentials={})
        result = await action.execute(webid="12345")

        assert result["status"] == "error"
        assert "api_key" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(404))
        result = await action.execute(webid="nonexistent")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["webid"] == "nonexistent"

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(500))
        result = await action.execute(webid="12345")

        assert result["status"] == "error"


# ===========================================================================
# GetReportAction
# ===========================================================================


class TestGetReportAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetReportAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        # Two calls: info check then download
        info_resp = _json_response({"data": {"webid": "12345", "status": "finished"}})
        report_resp = _json_response(
            {
                "analysis": {
                    "generalinfo": {"target": {"sample": "test.exe"}},
                    "fileinfo": {"md5": "abc123", "sha256": "def456"},
                }
            }
        )
        action.http_request = AsyncMock(side_effect=[info_resp, report_resp])

        result = await action.execute(webid="12345")

        assert result["status"] == "success"
        assert result["data"]["webid"] == "12345"
        assert result["data"]["status"] == "finished"
        assert result["data"]["report"] is not None
        assert "integration_id" in result
        assert action.http_request.call_count == 2

    @pytest.mark.asyncio
    async def test_analysis_not_finished(self, action):
        info_resp = _json_response({"data": {"webid": "12345", "status": "running"}})
        action.http_request = AsyncMock(return_value=info_resp)

        result = await action.execute(webid="12345")

        assert result["status"] == "error"
        assert "not finished" in result["error"]
        assert result["error_type"] == "AnalysisPendingError"
        # Should only have called info, not download
        assert action.http_request.call_count == 1

    @pytest.mark.asyncio
    async def test_missing_webid(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "webid" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(GetReportAction, credentials={})
        result = await action.execute(webid="12345")

        assert result["status"] == "error"
        assert "api_key" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(404))
        result = await action.execute(webid="nonexistent")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["webid"] == "nonexistent"

    @pytest.mark.asyncio
    async def test_http_error_non_404(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(500))
        result = await action.execute(webid="12345")

        assert result["status"] == "error"


# ===========================================================================
# UrlReputationAction
# ===========================================================================


class TestUrlReputationAction:
    @pytest.fixture
    def action(self):
        return _make_action(UrlReputationAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        # Two calls: search then info
        search_resp = _json_response({"data": [{"webid": "77777"}]})
        info_resp = _json_response(
            {
                "data": {
                    "webid": "77777",
                    "status": "finished",
                    "runs": [{"detection": "malicious"}],
                }
            }
        )
        action.http_request = AsyncMock(side_effect=[search_resp, info_resp])

        result = await action.execute(url="https://evil.example.com")

        assert result["status"] == "success"
        assert result["data"]["reputation_label"] == "malicious"
        assert "integration_id" in result
        assert action.http_request.call_count == 2

        # Verify search call
        search_call = action.http_request.call_args_list[0].kwargs
        assert search_call["data"]["q"] == "https://evil.example.com"

    @pytest.mark.asyncio
    async def test_no_analysis_found(self, action):
        search_resp = _json_response({"data": []})
        action.http_request = AsyncMock(return_value=search_resp)

        result = await action.execute(url="https://unknown.example.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["url"] == "https://unknown.example.com"
        assert result["data"]["reputation_label"] == "clean"

    @pytest.mark.asyncio
    async def test_missing_url(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "url" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(UrlReputationAction, credentials={})
        result = await action.execute(url="https://example.com")

        assert result["status"] == "error"
        assert "api_key" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(404))
        result = await action.execute(url="https://missing.example.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["url"] == "https://missing.example.com"

    @pytest.mark.asyncio
    async def test_http_error_non_404(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(500))
        result = await action.execute(url="https://example.com")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_clean_reputation(self, action):
        search_resp = _json_response({"data": [{"webid": "88888"}]})
        info_resp = _json_response(
            {
                "data": {
                    "webid": "88888",
                    "status": "finished",
                    "runs": [{"detection": "clean"}],
                }
            }
        )
        action.http_request = AsyncMock(side_effect=[search_resp, info_resp])

        result = await action.execute(url="https://safe.example.com")

        assert result["status"] == "success"
        assert result["data"]["reputation_label"] == "clean"


# ===========================================================================
# FileReputationAction
# ===========================================================================


class TestFileReputationAction:
    @pytest.fixture
    def action(self):
        return _make_action(FileReputationAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        # Two calls: search then info
        search_resp = _json_response({"data": [{"webid": "55555"}]})
        info_resp = _json_response(
            {
                "data": {
                    "webid": "55555",
                    "status": "finished",
                    "filename": "malware.exe",
                    "runs": [{"detection": "malicious"}],
                }
            }
        )
        action.http_request = AsyncMock(side_effect=[search_resp, info_resp])

        result = await action.execute(hash="abc123def456")

        assert result["status"] == "success"
        assert result["data"]["reputation_label"] == "malicious"
        assert "integration_id" in result
        assert action.http_request.call_count == 2

        # Verify search call used the hash
        search_call = action.http_request.call_args_list[0].kwargs
        assert search_call["data"]["q"] == "abc123def456"

    @pytest.mark.asyncio
    async def test_no_analysis_found(self, action):
        search_resp = _json_response({"data": []})
        action.http_request = AsyncMock(return_value=search_resp)

        result = await action.execute(hash="unknown_hash_123")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["hash"] == "unknown_hash_123"
        assert result["data"]["reputation_label"] == "clean"

    @pytest.mark.asyncio
    async def test_missing_hash(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "hash" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(FileReputationAction, credentials={})
        result = await action.execute(hash="abc123")

        assert result["status"] == "error"
        assert "api_key" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(404))
        result = await action.execute(hash="missing_hash")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["hash"] == "missing_hash"

    @pytest.mark.asyncio
    async def test_http_error_non_404(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(500))
        result = await action.execute(hash="abc123")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_clean_file(self, action):
        search_resp = _json_response({"data": [{"webid": "66666"}]})
        info_resp = _json_response(
            {
                "data": {
                    "webid": "66666",
                    "status": "finished",
                    "runs": [],
                }
            }
        )
        action.http_request = AsyncMock(side_effect=[search_resp, info_resp])

        result = await action.execute(hash="clean_file_hash")

        assert result["status"] == "success"
        assert result["data"]["reputation_label"] == "clean"


# ===========================================================================
# ListCookbooksAction
# ===========================================================================


class TestListCookbooksAction:
    @pytest.fixture
    def action(self):
        return _make_action(ListCookbooksAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        mock_resp = _json_response(
            {
                "data": [
                    {"id": 1, "name": "Default Windows"},
                    {"id": 2, "name": "Default Linux"},
                    {"id": 3, "name": "Custom Office"},
                ]
            }
        )
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_cookbooks"] == 3
        assert len(result["data"]["cookbooks"]) == 3
        assert result["data"]["cookbooks"][0]["name"] == "Default Windows"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_empty_list(self, action):
        mock_resp = _json_response({"data": []})
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_cookbooks"] == 0
        assert result["data"]["cookbooks"] == []

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(ListCookbooksAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert "api_key" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(500))
        result = await action.execute()

        assert result["status"] == "error"


# ===========================================================================
# GetCookbookAction
# ===========================================================================


class TestGetCookbookAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetCookbookAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        mock_resp = _json_response(
            {
                "data": {
                    "id": 42,
                    "name": "Custom Analysis",
                    "code": "// cookbook script code here",
                }
            }
        )
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(cookbook_id="42")

        assert result["status"] == "success"
        assert result["data"]["name"] == "Custom Analysis"
        assert result["data"]["code"] == "// cookbook script code here"
        assert "integration_id" in result

        # Verify the cookbook ID was sent
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["data"]["id"] == "42"

    @pytest.mark.asyncio
    async def test_empty_response_returns_not_found(self, action):
        mock_resp = _json_response({"data": {}})
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(cookbook_id="999")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["cookbook_id"] == "999"

    @pytest.mark.asyncio
    async def test_missing_cookbook_id(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "cookbook_id" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(GetCookbookAction, credentials={})
        result = await action.execute(cookbook_id="42")

        assert result["status"] == "error"
        assert "api_key" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_404(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(404))
        result = await action.execute(cookbook_id="nonexistent")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["cookbook_id"] == "nonexistent"

    @pytest.mark.asyncio
    async def test_http_error_non_404(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(500))
        result = await action.execute(cookbook_id="42")

        assert result["status"] == "error"


# ===========================================================================
# Base class helper tests
# ===========================================================================


class TestJoeSandboxBaseHelpers:
    """Test shared helper methods on the base class."""

    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    def test_get_base_url_default(self, action):
        url = action._get_base_url()
        assert url == "https://jbxcloud.joesecurity.org"

    def test_get_base_url_custom(self):
        action = _make_action(
            HealthCheckAction,
            settings={"base_url": "https://my.joesandbox.com/"},
        )
        url = action._get_base_url()
        assert url == "https://my.joesandbox.com"

    def test_get_base_url_strips_trailing_slash(self):
        action = _make_action(
            HealthCheckAction,
            settings={"base_url": "https://joe.example.com///"},
        )
        url = action._get_base_url()
        assert url == "https://joe.example.com"

    def test_get_api_key(self, action):
        assert action._get_api_key() == "test-joe-key"

    def test_get_api_key_missing(self):
        action = _make_action(HealthCheckAction, credentials={})
        assert action._get_api_key() is None

    def test_get_request_timeout_default(self, action):
        assert action._get_request_timeout() == 30

    def test_get_request_timeout_custom(self):
        action = _make_action(HealthCheckAction, settings={"timeout": 60})
        assert action._get_request_timeout() == 60

    def test_get_analysis_time_default(self, action):
        assert action._get_analysis_time() == 120

    def test_get_analysis_time_custom(self):
        action = _make_action(HealthCheckAction, settings={"analysis_time": 200})
        assert action._get_analysis_time() == 200

    def test_extract_reputation_label_malicious(self):
        data = {"runs": [{"detection": "malicious"}]}
        assert HealthCheckAction._extract_reputation_label(data) == "malicious"

    def test_extract_reputation_label_clean(self):
        data = {"runs": [{"detection": "clean"}]}
        assert HealthCheckAction._extract_reputation_label(data) == "clean"

    def test_extract_reputation_label_no_runs(self):
        data = {"runs": []}
        assert HealthCheckAction._extract_reputation_label(data) == "clean"

    def test_extract_reputation_label_missing_key(self):
        data = {}
        assert HealthCheckAction._extract_reputation_label(data) == "clean"

    def test_extract_reputation_label_multiple_runs(self):
        """Last detection value wins ."""
        data = {"runs": [{"detection": "clean"}, {"detection": "suspicious"}]}
        assert HealthCheckAction._extract_reputation_label(data) == "suspicious"
