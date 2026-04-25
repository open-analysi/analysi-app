"""Unit tests for ANY.RUN sandbox integration actions.

All actions use ``self.http_request()`` which applies
``integration_retry_policy`` automatically. Tests mock at the
``IntegrationAction.http_request`` level.
"""

import base64
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.anyrun.actions import (
    DetonateFileAction,
    DetonateUrlAction,
    GetReportAction,
    HealthCheckAction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json_response(data: dict, status_code: int = 200) -> MagicMock:
    """Build a fake httpx.Response for http_request mock."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    resp.text = str(data)
    return resp


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Build a fake HTTPStatusError with the given status code."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.text = f"Error {status_code}"
    mock_request = MagicMock(spec=httpx.Request)
    return httpx.HTTPStatusError(
        message=f"HTTP {status_code}",
        request=mock_request,
        response=mock_response,
    )


def _make_action(action_class, credentials=None, settings=None):
    """Create an action instance with default test values."""
    return action_class(
        integration_id="anyrun",
        action_id=action_class.__name__.lower().replace("action", ""),
        settings=settings if settings is not None else {},
        credentials=credentials
        if credentials is not None
        else {"api_key": "test-api-key-123"},
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
        mock_resp = _json_response({"data": {"tasks_total": 42}})
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert result["data"]["total_analyses"] == 42
        assert "integration_id" in result
        assert "timestamp" in result
        action.http_request.assert_called_once()

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
        assert result["error_type"] == "HTTPStatusError"

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
            settings={"base_url": "https://custom.any.run/v1"},
        )
        mock_resp = _json_response({"data": {"tasks_total": 10}})
        action.http_request = AsyncMock(return_value=mock_resp)

        await action.execute()

        call_kwargs = action.http_request.call_args
        assert "custom.any.run" in call_kwargs.kwargs["url"]

    @pytest.mark.asyncio
    async def test_auth_header_present(self):
        action = _make_action(HealthCheckAction)
        headers = action.get_http_headers()
        assert "Authorization" in headers
        assert headers["Authorization"] == "API-Key test-api-key-123"

    @pytest.mark.asyncio
    async def test_auth_header_empty_when_no_key(self):
        action = _make_action(HealthCheckAction, credentials={})
        headers = action.get_http_headers()
        assert headers == {}


# ===========================================================================
# DetonateUrlAction
# ===========================================================================


class TestDetonateUrlAction:
    @pytest.fixture
    def action(self):
        return _make_action(DetonateUrlAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        mock_resp = _json_response({"data": {"taskid": "abc-123-def-456"}})
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(url="https://example.com/malware")

        assert result["status"] == "success"
        assert result["data"]["analysis_id"] == "abc-123-def-456"
        assert "app.any.run/tasks/abc-123-def-456" in result["data"]["analysis_url"]
        assert result["data"]["submitted_url"] == "https://example.com/malware"
        assert "integration_id" in result

        # Verify POST method was used
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["method"] == "POST"
        assert "obj_url" in call_kwargs["data"]
        assert call_kwargs["data"]["obj_url"] == "https://example.com/malware"

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
    async def test_custom_os_and_options(self, action):
        mock_resp = _json_response({"data": {"taskid": "task-linux-1"}})
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(
            url="https://example.com",
            os_type="linux",
            env_type="clean",
            opt_privacy_type="public",
            opt_timeout=60,
        )

        assert result["status"] == "success"
        call_data = action.http_request.call_args.kwargs["data"]
        assert call_data["env_os"] == "linux"
        assert call_data["env_type"] == "clean"
        assert call_data["opt_privacy_type"] == "public"
        assert call_data["opt_timeout"] == 60

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(403))
        result = await action.execute(url="https://example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_default_parameters(self, action):
        mock_resp = _json_response({"data": {"taskid": "task-default"}})
        action.http_request = AsyncMock(return_value=mock_resp)

        await action.execute(url="https://example.com")

        call_data = action.http_request.call_args.kwargs["data"]
        assert call_data["env_os"] == "windows"
        assert call_data["env_type"] == "complete"
        assert call_data["env_bitness"] == 64
        assert call_data["env_version"] == "10"
        assert call_data["env_locale"] == "en-US"
        assert call_data["opt_network_connect"] is True
        assert call_data["opt_privacy_type"] == "bylink"
        assert call_data["opt_timeout"] == 120
        assert call_data["user_tags"] == "analysi-sandbox"


# ===========================================================================
# DetonateFileAction
# ===========================================================================


class TestDetonateFileAction:
    @pytest.fixture
    def action(self):
        return _make_action(DetonateFileAction)

    @pytest.fixture
    def sample_b64_content(self):
        return base64.b64encode(b"MZ\x90\x00\x03\x00\x00\x00").decode()

    @pytest.mark.asyncio
    async def test_success(self, action, sample_b64_content):
        mock_resp = _json_response({"data": {"taskid": "file-task-789"}})
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(
            file_content=sample_b64_content,
            filename="malware.exe",
        )

        assert result["status"] == "success"
        assert result["data"]["analysis_id"] == "file-task-789"
        assert result["data"]["filename"] == "malware.exe"
        assert "app.any.run/tasks/file-task-789" in result["data"]["analysis_url"]
        assert "integration_id" in result

        # Verify POST with content (multipart body)
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["method"] == "POST"
        assert call_kwargs["content"] is not None
        assert b"malware.exe" in call_kwargs["content"]

    @pytest.mark.asyncio
    async def test_missing_file_content(self, action):
        result = await action.execute(filename="test.exe")

        assert result["status"] == "error"
        assert "file_content" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_filename(self, action, sample_b64_content):
        result = await action.execute(file_content=sample_b64_content)

        assert result["status"] == "error"
        assert "filename" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self, sample_b64_content):
        action = _make_action(DetonateFileAction, credentials={})
        result = await action.execute(
            file_content=sample_b64_content,
            filename="test.exe",
        )

        assert result["status"] == "error"
        assert "api_key" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_invalid_base64(self, action):
        result = await action.execute(
            file_content="not-valid-base64!!!",
            filename="test.exe",
        )

        assert result["status"] == "error"
        assert "base64" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_http_error(self, action, sample_b64_content):
        action.http_request = AsyncMock(side_effect=_http_status_error(429))
        result = await action.execute(
            file_content=sample_b64_content,
            filename="test.exe",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_custom_sandbox_options(self, action, sample_b64_content):
        mock_resp = _json_response({"data": {"taskid": "custom-task"}})
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(
            file_content=sample_b64_content,
            filename="test.apk",
            os_type="android",
            opt_privacy_type="owner",
            opt_timeout=300,
        )

        assert result["status"] == "success"
        # Verify options are in the multipart body
        body = action.http_request.call_args.kwargs["content"]
        assert b"android" in body
        assert b"owner" in body
        assert b"300" in body


# ===========================================================================
# GetReportAction
# ===========================================================================


class TestGetReportAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetReportAction)

    @pytest.fixture
    def sample_report_response(self):
        return {
            "data": {
                "analysis": {
                    "content": {
                        "mainObject": {
                            "type": "url",
                            "url": "https://evil.example.com",
                            "filename": "",
                        }
                    },
                    "scores": {
                        "verdict": {
                            "threatLevel": 2,
                            "threatLevelText": "Malicious activity",
                        }
                    },
                    "tags": [
                        {"tag": "phishing"},
                        {"tag": "credential-theft"},
                    ],
                }
            }
        }

    @pytest.mark.asyncio
    async def test_success_url_analysis(self, action, sample_report_response):
        mock_resp = _json_response(sample_report_response)
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(analysis_id="abc-123")

        assert result["status"] == "success"
        assert result["data"]["analysis_id"] == "abc-123"
        assert result["data"]["object_type"] == "url"
        assert result["data"]["object_value"] == "https://evil.example.com"
        assert result["data"]["verdict"] == "Malicious activity"
        assert "phishing" in result["data"]["tags"]
        assert "credential-theft" in result["data"]["tags"]
        assert "app.any.run/tasks/abc-123" in result["data"]["analysis_url"]
        assert "report" in result["data"]
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_success_file_analysis(self, action):
        report = {
            "data": {
                "analysis": {
                    "content": {
                        "mainObject": {
                            "type": "file",
                            "url": "",
                            "filename": "trojan.exe",
                        }
                    },
                    "scores": {
                        "verdict": {
                            "threatLevel": 1,
                            "threatLevelText": "Suspicious activity",
                        }
                    },
                    "tags": [],
                }
            }
        }
        mock_resp = _json_response(report)
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(analysis_id="file-456")

        assert result["status"] == "success"
        assert result["data"]["object_type"] == "file"
        assert result["data"]["object_value"] == "trojan.exe"
        assert result["data"]["verdict"] == "Suspicious activity"
        assert result["data"]["tags"] == "No info"

    @pytest.mark.asyncio
    async def test_missing_analysis_id(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "analysis_id" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(GetReportAction, credentials={})
        result = await action.execute(analysis_id="abc-123")

        assert result["status"] == "error"
        assert "api_key" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_not_found_returns_success(self, action):
        """404 must return success with not_found=True (not crash Cy scripts)."""
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(analysis_id="nonexistent-id")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["analysis_id"] == "nonexistent-id"
        assert result["data"]["verdict"] == "No info"

    @pytest.mark.asyncio
    async def test_http_error_non_404(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        result = await action.execute(analysis_id="abc-123")

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_network_error(self, action):
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await action.execute(analysis_id="abc-123")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_verdict_fallback_to_map(self, action):
        """When threatLevelText is empty, fall back to VERDICT_MAP."""
        report = {
            "data": {
                "analysis": {
                    "content": {
                        "mainObject": {
                            "type": "url",
                            "url": "https://clean.example.com",
                        }
                    },
                    "scores": {
                        "verdict": {
                            "threatLevel": 0,
                            "threatLevelText": "",
                        }
                    },
                    "tags": None,
                }
            }
        }
        mock_resp = _json_response(report)
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(analysis_id="clean-task")

        assert result["status"] == "success"
        assert result["data"]["verdict"] == "No threats detected"
