"""Unit tests for Palo Alto WildFire sandbox integration actions.

All actions use ``self.http_request()`` which applies
``integration_retry_policy`` automatically.  Tests mock at the
``IntegrationAction.http_request`` level.

WildFire returns XML responses, so mocked responses use ``.text`` with
XML strings rather than ``.json()``.
"""

import base64
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.wildfire.actions import (
    DetonateFileAction,
    DetonateUrlAction,
    GetReportAction,
    GetUrlReputationAction,
    HealthCheckAction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Sample XML response bodies matching WildFire API format


VERDICT_XML_BENIGN = """<?xml version="1.0" encoding="UTF-8"?>
<wildfire>
  <get-verdict-info>
    <sha256>abc123</sha256>
    <md5>def456</md5>
    <verdict>0</verdict>
  </get-verdict-info>
</wildfire>"""

VERDICT_XML_MALWARE = """<?xml version="1.0" encoding="UTF-8"?>
<wildfire>
  <get-verdict-info>
    <sha256>abc123</sha256>
    <md5>def456</md5>
    <verdict>1</verdict>
  </get-verdict-info>
</wildfire>"""

VERDICT_XML_URL = """<?xml version="1.0" encoding="UTF-8"?>
<wildfire>
  <get-verdict-info>
    <url>https://example.com</url>
    <verdict>0</verdict>
    <analysis_time>2024-01-15T10:30:00Z</analysis_time>
    <valid>Yes</valid>
  </get-verdict-info>
</wildfire>"""

VERDICT_XML_URL_UNKNOWN = """<?xml version="1.0" encoding="UTF-8"?>
<wildfire>
  <get-verdict-info>
    <url>https://unknown.example.com</url>
    <verdict>-102</verdict>
  </get-verdict-info>
</wildfire>"""

SUBMIT_URL_XML = """<?xml version="1.0" encoding="UTF-8"?>
<wildfire>
  <submit-link-info>
    <sha256>aabbcc112233</sha256>
    <md5>ddeeff445566</md5>
    <url>https://example.com/file</url>
  </submit-link-info>
</wildfire>"""

SUBMIT_FILE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<wildfire>
  <upload-file-info>
    <sha256>file_sha256_hash</sha256>
    <md5>file_md5_hash</md5>
    <filetype>PE</filetype>
    <size>12345</size>
    <filename>malware.exe</filename>
  </upload-file-info>
</wildfire>"""

REPORT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<wildfire>
  <file_info>
    <filetype>PE</filetype>
    <sha256>abc123</sha256>
    <md5>def456</md5>
    <malware>yes</malware>
    <size>54321</size>
  </file_info>
  <task_info>
    <report>
      <platform>Windows XP</platform>
      <software>Adobe Reader</software>
    </report>
  </task_info>
</wildfire>"""

ERROR_XML_401 = """<?xml version="1.0" encoding="UTF-8"?>
<error>
  <error-message>Invalid API key</error-message>
</error>"""


def _xml_response(text: str, status_code: int = 200) -> MagicMock:
    """Build a fake httpx.Response with XML text body."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.headers = {"Content-Type": "application/xml"}
    return resp


def _http_status_error(status_code: int, body: str = "") -> httpx.HTTPStatusError:
    """Build a fake HTTPStatusError with given status code and body."""
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
        integration_id="wildfire",
        action_id=action_class.__name__.lower().replace("action", ""),
        settings=settings if settings is not None else {},
        credentials=credentials
        if credentials is not None
        else {"api_key": "test-wf-api-key"},
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
        mock_resp = _xml_response(VERDICT_XML_BENIGN)
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
        assert call_kwargs["data"]["apikey"] == "test-wf-api-key"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(HealthCheckAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert "api_key" in result["error"]
        assert result["error_type"] == "ConfigurationError"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_http_401_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_http_status_error(401, ERROR_XML_401)
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert result["data"]["healthy"] is False
        assert "Invalid API key" in result["error"]

    @pytest.mark.asyncio
    async def test_network_error(self, action):
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert result["data"]["healthy"] is False

    @pytest.mark.asyncio
    async def test_unparseable_xml(self, action):
        mock_resp = _xml_response("not xml at all")
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ParseError"

    @pytest.mark.asyncio
    async def test_custom_base_url(self):
        action = _make_action(
            HealthCheckAction,
            settings={"base_url": "https://custom.wildfire.example.com"},
        )
        mock_resp = _xml_response(VERDICT_XML_BENIGN)
        action.http_request = AsyncMock(return_value=mock_resp)

        await action.execute()

        call_kwargs = action.http_request.call_args.kwargs
        assert "custom.wildfire.example.com/publicapi" in call_kwargs["url"]


# ===========================================================================
# DetonateUrlAction
# ===========================================================================


class TestDetonateUrlAction:
    @pytest.fixture
    def action(self):
        return _make_action(DetonateUrlAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        # Two calls: submit URL, then get verdict
        submit_resp = _xml_response(SUBMIT_URL_XML)
        verdict_resp = _xml_response(VERDICT_XML_BENIGN)
        action.http_request = AsyncMock(side_effect=[submit_resp, verdict_resp])

        result = await action.execute(url="https://example.com/file")

        assert result["status"] == "success"
        assert result["data"]["url"] == "https://example.com/file"
        assert result["data"]["sha256"] == "aabbcc112233"
        assert result["data"]["md5"] == "ddeeff445566"
        assert result["data"]["verdict"] == "benign"
        assert result["data"]["verdict_code"] == 0
        assert "integration_id" in result
        assert action.http_request.call_count == 2

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
    async def test_submit_http_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_http_status_error(419, ERROR_XML_401)
        )
        result = await action.execute(url="https://example.com")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_malware_verdict(self, action):
        submit_resp = _xml_response(SUBMIT_URL_XML)
        verdict_resp = _xml_response(VERDICT_XML_MALWARE)
        action.http_request = AsyncMock(side_effect=[submit_resp, verdict_resp])

        result = await action.execute(url="https://evil.example.com")

        assert result["status"] == "success"
        assert result["data"]["verdict"] == "malware"
        assert result["data"]["verdict_code"] == 1

    @pytest.mark.asyncio
    async def test_unparseable_submit_response(self, action):
        mock_resp = _xml_response("garbage")
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(url="https://example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ParseError"


# ===========================================================================
# DetonateFileAction
# ===========================================================================


class TestDetonateFileAction:
    @pytest.fixture
    def action(self):
        return _make_action(DetonateFileAction)

    @pytest.fixture
    def sample_b64(self):
        return base64.b64encode(b"MZ\x90\x00\x03\x00\x00\x00").decode()

    @pytest.mark.asyncio
    async def test_success(self, action, sample_b64):
        mock_resp = _xml_response(SUBMIT_FILE_XML)
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(
            file_content=sample_b64,
            filename="malware.exe",
        )

        assert result["status"] == "success"
        assert result["data"]["filename"] == "malware.exe"
        assert result["data"]["sha256"] == "file_sha256_hash"
        assert result["data"]["md5"] == "file_md5_hash"
        assert result["data"]["filetype"] == "PE"
        assert result["data"]["size"] == "12345"
        assert "integration_id" in result

        # Verify multipart content was sent
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["method"] == "POST"
        assert call_kwargs["content"] is not None
        assert b"malware.exe" in call_kwargs["content"]
        assert b"test-wf-api-key" in call_kwargs["content"]

    @pytest.mark.asyncio
    async def test_missing_file_content(self, action):
        result = await action.execute(filename="test.exe")

        assert result["status"] == "error"
        assert "file_content" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_filename(self, action, sample_b64):
        result = await action.execute(file_content=sample_b64)

        assert result["status"] == "error"
        assert "filename" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self, sample_b64):
        action = _make_action(DetonateFileAction, credentials={})
        result = await action.execute(file_content=sample_b64, filename="test.exe")

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
    async def test_http_error_413(self, action, sample_b64):
        action.http_request = AsyncMock(side_effect=_http_status_error(413))
        result = await action.execute(file_content=sample_b64, filename="huge.bin")

        assert result["status"] == "error"
        assert "413" in result["error"]

    @pytest.mark.asyncio
    async def test_unparseable_xml_response(self, action, sample_b64):
        mock_resp = _xml_response("not xml")
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(file_content=sample_b64, filename="test.exe")

        assert result["status"] == "error"
        assert result["error_type"] == "ParseError"


# ===========================================================================
# GetReportAction
# ===========================================================================


class TestGetReportAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetReportAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        # Two calls: verdict then report
        verdict_resp = _xml_response(VERDICT_XML_MALWARE)
        report_resp = _xml_response(REPORT_XML)
        action.http_request = AsyncMock(side_effect=[verdict_resp, report_resp])

        result = await action.execute(hash="abc123sha256")

        assert result["status"] == "success"
        assert result["data"]["hash"] == "abc123sha256"
        assert result["data"]["verdict"] == "malware"
        assert result["data"]["verdict_code"] == 1
        assert result["data"]["file_info"]["filetype"] == "PE"
        assert result["data"]["file_info"]["malware"] == "yes"
        assert result["data"]["report"] is not None
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_hash(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "hash" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(GetReportAction, credentials={})
        result = await action.execute(hash="abc123")

        assert result["status"] == "error"
        assert "api_key" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_not_found_returns_success(self, action):
        """404 must return success with not_found=True (not crash Cy scripts)."""
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(hash="nonexistent_hash")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["hash"] == "nonexistent_hash"
        assert result["data"]["verdict"] == "unknown"
        assert result["data"]["verdict_code"] == -102

    @pytest.mark.asyncio
    async def test_http_error_non_404(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        result = await action.execute(hash="abc123")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_benign_verdict(self, action):
        verdict_resp = _xml_response(VERDICT_XML_BENIGN)
        report_resp = _xml_response(REPORT_XML)
        action.http_request = AsyncMock(side_effect=[verdict_resp, report_resp])

        result = await action.execute(hash="benign_hash")

        assert result["status"] == "success"
        assert result["data"]["verdict"] == "benign"
        assert result["data"]["verdict_code"] == 0


# ===========================================================================
# GetUrlReputationAction
# ===========================================================================


class TestGetUrlReputationAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetUrlReputationAction)

    @pytest.mark.asyncio
    async def test_success_benign(self, action):
        mock_resp = _xml_response(VERDICT_XML_URL)
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(url="https://example.com")

        assert result["status"] == "success"
        assert result["data"]["url"] == "https://example.com"
        assert result["data"]["verdict"] == "benign"
        assert result["data"]["verdict_code"] == 0
        assert result["data"]["analysis_time"] == "2024-01-15T10:30:00Z"
        assert result["data"]["valid"] == "Yes"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_unknown_url_returns_not_found(self, action):
        """URL not in WildFire DB should return not_found=True."""
        mock_resp = _xml_response(VERDICT_XML_URL_UNKNOWN)
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(url="https://unknown.example.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["url"] == "https://unknown.example.com"
        assert result["data"]["verdict"] == "unknown"
        assert result["data"]["verdict_code"] == -102

    @pytest.mark.asyncio
    async def test_missing_url(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "url" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(GetUrlReputationAction, credentials={})
        result = await action.execute(url="https://example.com")

        assert result["status"] == "error"
        assert "api_key" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_404_returns_not_found(self, action):
        """HTTP 404 must return success with not_found=True."""
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(url="https://missing.example.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["url"] == "https://missing.example.com"

    @pytest.mark.asyncio
    async def test_http_error_non_404(self, action):
        action.http_request = AsyncMock(
            side_effect=_http_status_error(401, ERROR_XML_401)
        )

        result = await action.execute(url="https://example.com")

        assert result["status"] == "error"
        assert "Invalid API key" in result["error"]

    @pytest.mark.asyncio
    async def test_unparseable_xml(self, action):
        mock_resp = _xml_response("not valid xml")
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute(url="https://example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ParseError"

    @pytest.mark.asyncio
    async def test_network_error(self, action):
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await action.execute(url="https://example.com")

        assert result["status"] == "error"


# ===========================================================================
# Base class helper tests
# ===========================================================================


class TestWildFireBaseHelpers:
    """Test shared helper methods on the base class."""

    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    def test_resolve_verdict_known_codes(self, action):
        assert action._resolve_verdict(0) == "benign"
        assert action._resolve_verdict(1) == "malware"
        assert action._resolve_verdict(2) == "grayware"
        assert action._resolve_verdict(4) == "phishing"
        assert action._resolve_verdict(-100) == "pending"
        assert action._resolve_verdict(-101) == "error"
        assert action._resolve_verdict(-102) == "unknown"
        assert action._resolve_verdict(-103) == "invalid hash value"

    def test_resolve_verdict_unknown_code(self, action):
        assert action._resolve_verdict(999) == "unknown verdict code"

    def test_get_base_url_default(self, action):
        url = action._get_base_url()
        assert url == "https://wildfire.paloaltonetworks.com/publicapi"

    def test_get_base_url_custom(self):
        action = _make_action(
            HealthCheckAction,
            settings={"base_url": "https://my.wildfire.com/"},
        )
        url = action._get_base_url()
        assert url == "https://my.wildfire.com/publicapi"

    def test_parse_xml_response_valid(self, action):
        data = action._parse_xml_response(VERDICT_XML_BENIGN)
        assert data is not None
        assert "get-verdict-info" in data
        assert data["get-verdict-info"]["verdict"] == "0"

    def test_parse_xml_response_invalid(self, action):
        data = action._parse_xml_response("this is not xml")
        assert data is None

    def test_parse_xml_response_invalid_logs_debug(self, action):
        """Ensure failed XML parsing emits a debug log with error details."""
        bad_xml = "this is not xml at all"
        # Patch log_debug to verify it's called
        action.log_debug = MagicMock()

        action._parse_xml_response(bad_xml)

        action.log_debug.assert_called_once()
        call_kwargs = action.log_debug.call_args
        assert call_kwargs[0][0] == "xml_parse_failed"
        assert "error" in call_kwargs[1]
        assert call_kwargs[1]["text_length"] == len(bad_xml)

    def test_parse_xml_response_no_wildfire_key(self, action):
        data = action._parse_xml_response("<other><data>1</data></other>")
        assert data is None

    def test_get_wildfire_error_detail_from_xml(self, action):
        detail = action._get_wildfire_error_detail(401, ERROR_XML_401, {})
        assert "Invalid API key" in detail
        assert "401" in detail

    def test_get_wildfire_error_detail_from_mapping(self, action):
        detail = action._get_wildfire_error_detail(
            419, "not xml", {419: "Quota exceeded"}
        )
        assert "Quota exceeded" in detail
        assert "419" in detail

    def test_get_wildfire_error_detail_fallback(self, action):
        detail = action._get_wildfire_error_detail(999, "not xml", {})
        assert "999" in detail

    def test_get_request_timeout_default(self, action):
        assert action._get_request_timeout() == 120

    def test_get_request_timeout_custom(self):
        action = _make_action(HealthCheckAction, settings={"timeout": 60})
        assert action._get_request_timeout() == 60
