"""Unit tests for ThreatConnect integration actions.

ThreatConnect uses HMAC-SHA256 request signing. Tests mock self.http_request()
since the framework handles retry/logging/SSL via integration_retry_policy.

All tests target < 0.1s -- no real network calls or sleeps.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.threatconnect.actions import (
    CreateIndicatorAction,
    HealthCheckAction,
    ListOwnersAction,
    LookupDomainAction,
    LookupEmailAction,
    LookupHashAction,
    LookupIpAction,
    LookupUrlAction,
    _build_auth_headers,
    _build_request_path,
    _sign_request,
    _validate_hash,
    _validate_ip,
    _validate_non_empty,
)

# ---------------------------------------------------------------------------
# Shared test credentials/settings
# ---------------------------------------------------------------------------

TEST_ACCESS_ID = "test-access-id"
TEST_SECRET_KEY = "test-secret-key-for-hmac"
TEST_CREDENTIALS = {"access_id": TEST_ACCESS_ID, "secret_key": TEST_SECRET_KEY}
TEST_SETTINGS = {"base_url": "https://api.threatconnect.com", "timeout": 30}


def _json_response(data: dict, status_code: int = 200) -> MagicMock:
    """Build a fake httpx.Response for http_request mock."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    return resp


def _http_error(status_code: int, message: str = "Error") -> httpx.HTTPStatusError:
    """Build an httpx.HTTPStatusError for testing error paths."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = message
    request = MagicMock(spec=httpx.Request)
    return httpx.HTTPStatusError(message, request=request, response=response)


# ===========================================================================
# HMAC SIGNING TESTS
# ===========================================================================


class TestSignRequest:
    """Test HMAC-SHA256 signing logic."""

    def test_sign_request_produces_base64_string(self):
        """Signature must be a valid base64 string."""
        sig, ts = _sign_request(
            "my-secret", "/v3/indicators", "GET", timestamp=1700000000
        )
        assert isinstance(sig, str)
        assert ts == 1700000000
        # base64 chars only
        import base64

        decoded = base64.b64decode(sig)
        assert len(decoded) == 32  # SHA-256 = 32 bytes

    def test_sign_request_deterministic(self):
        """Same inputs must produce same signature."""
        sig1, _ = _sign_request("secret", "/v3/owners", "GET", timestamp=1234567890)
        sig2, _ = _sign_request("secret", "/v3/owners", "GET", timestamp=1234567890)
        assert sig1 == sig2

    def test_sign_request_different_methods_differ(self):
        """GET and POST signatures must differ for same path."""
        sig_get, _ = _sign_request("secret", "/v3/indicators", "GET", timestamp=100)
        sig_post, _ = _sign_request("secret", "/v3/indicators", "POST", timestamp=100)
        assert sig_get != sig_post

    def test_sign_request_different_paths_differ(self):
        """Different paths must produce different signatures."""
        sig1, _ = _sign_request("secret", "/v3/indicators", "GET", timestamp=100)
        sig2, _ = _sign_request("secret", "/v3/owners", "GET", timestamp=100)
        assert sig1 != sig2

    def test_sign_request_different_timestamps_differ(self):
        """Different timestamps must produce different signatures."""
        sig1, _ = _sign_request("secret", "/v3/indicators", "GET", timestamp=100)
        sig2, _ = _sign_request("secret", "/v3/indicators", "GET", timestamp=200)
        assert sig1 != sig2

    def test_sign_request_different_keys_differ(self):
        """Different secret keys must produce different signatures."""
        sig1, _ = _sign_request("key-a", "/v3/indicators", "GET", timestamp=100)
        sig2, _ = _sign_request("key-b", "/v3/indicators", "GET", timestamp=100)
        assert sig1 != sig2

    def test_sign_request_method_uppercased(self):
        """Method should be treated case-insensitively (uppercased internally)."""
        sig_lower, _ = _sign_request("secret", "/v3/test", "get", timestamp=100)
        sig_upper, _ = _sign_request("secret", "/v3/test", "GET", timestamp=100)
        assert sig_lower == sig_upper

    def test_sign_request_auto_timestamp(self):
        """When timestamp is None, should use current time."""
        sig, ts = _sign_request("secret", "/v3/test", "GET")
        assert ts > 0
        assert isinstance(sig, str)

    def test_sign_request_known_value(self):
        """Verify against a hand-computed HMAC-SHA256 value."""
        import base64
        import hashlib
        import hmac

        secret = "my-secret-key"
        path = "/v3/indicators"
        method = "GET"
        timestamp = 1700000000
        message = f"{path}:{method}:{timestamp}"

        expected_bytes = hmac.new(
            secret.encode("utf-8"),
            message.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        expected_sig = base64.b64encode(expected_bytes).decode("utf-8")

        actual_sig, _ = _sign_request(secret, path, method, timestamp=timestamp)
        assert actual_sig == expected_sig


class TestBuildAuthHeaders:
    """Test header construction."""

    def test_headers_contain_required_fields(self):
        headers = _build_auth_headers(
            "my-id", "my-secret", "/v3/test", "GET", timestamp=100
        )
        assert "Authorization" in headers
        assert "Timestamp" in headers
        assert "Content-Type" in headers
        assert headers["Authorization"].startswith("TC my-id:")
        assert headers["Timestamp"] == "100"
        assert headers["Content-Type"] == "application/json"

    def test_authorization_format(self):
        headers = _build_auth_headers(
            "access-123", "secret-abc", "/v3/test", "GET", timestamp=100
        )
        auth = headers["Authorization"]
        assert auth.startswith("TC access-123:")
        # Signature portion after the colon
        sig = auth.split(":")[1]
        assert len(sig) > 0


class TestBuildRequestPath:
    """Test path construction for signing."""

    def test_simple_path_no_params(self):
        path = _build_request_path("https://api.threatconnect.com/v3", "indicators")
        assert path == "/v3/indicators"

    def test_path_with_params(self):
        path = _build_request_path(
            "https://api.threatconnect.com/v3",
            "indicators",
            {"tql": "typeName IN ('Address')"},
        )
        assert "/v3/indicators?" in path
        assert "tql=" in path

    def test_sandbox_path(self):
        path = _build_request_path(
            "https://sandbox.threatconnect.com/api/v3", "security/owners"
        )
        assert path == "/api/v3/security/owners"


# ===========================================================================
# VALIDATION TESTS
# ===========================================================================


class TestValidateIp:
    def test_valid_ipv4(self):
        is_valid, err = _validate_ip("192.168.1.1")
        assert is_valid is True
        assert err == ""

    def test_valid_ipv6(self):
        is_valid, err = _validate_ip("2001:db8::1")
        assert is_valid is True
        assert err == ""

    def test_invalid_ip(self):
        is_valid, err = _validate_ip("not-an-ip")
        assert is_valid is False
        assert "Invalid" in err

    def test_empty_ip(self):
        is_valid, err = _validate_ip("")
        assert is_valid is False

    def test_none_ip(self):
        is_valid, err = _validate_ip(None)
        assert is_valid is False


class TestValidateHash:
    def test_valid_md5(self):
        is_valid, err = _validate_hash("d41d8cd98f00b204e9800998ecf8427e")
        assert is_valid is True

    def test_valid_sha1(self):
        is_valid, err = _validate_hash("da39a3ee5e6b4b0d3255bfef95601890afd80709")
        assert is_valid is True

    def test_valid_sha256(self):
        is_valid, err = _validate_hash(
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )
        assert is_valid is True

    def test_invalid_length(self):
        is_valid, err = _validate_hash("abc123")
        assert is_valid is False
        assert "Invalid hash length" in err

    def test_non_hex_characters(self):
        is_valid, err = _validate_hash("zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz")
        assert is_valid is False
        assert "hexadecimal" in err

    def test_empty(self):
        is_valid, err = _validate_hash("")
        assert is_valid is False

    def test_none(self):
        is_valid, err = _validate_hash(None)
        assert is_valid is False


class TestValidateNonEmpty:
    def test_valid_string(self):
        is_valid, err = _validate_non_empty("hello", "field")
        assert is_valid is True

    def test_empty_string(self):
        is_valid, err = _validate_non_empty("", "field")
        assert is_valid is False
        assert "field is required" in err

    def test_whitespace_only(self):
        is_valid, err = _validate_non_empty("   ", "field")
        assert is_valid is False

    def test_none(self):
        is_valid, err = _validate_non_empty(None, "field")
        assert is_valid is False


# ===========================================================================
# HEALTH CHECK
# ===========================================================================


class TestHealthCheckAction:
    @pytest.fixture
    def action(self):
        return HealthCheckAction(
            integration_id="threatconnect",
            action_id="health_check",
            settings=TEST_SETTINGS,
            credentials=TEST_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        mock_resp = _json_response(
            {"status": "Success", "count": 3, "data": [{"id": 1}, {"id": 2}, {"id": 3}]}
        )
        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await action.execute()

        assert result["status"] == "success"
        assert result["healthy"] is True
        assert result["data"]["owner_count"] == 3

    @pytest.mark.asyncio
    async def test_missing_access_id(self):
        action = HealthCheckAction(
            integration_id="threatconnect",
            action_id="health_check",
            settings=TEST_SETTINGS,
            credentials={"secret_key": TEST_SECRET_KEY},
        )
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_missing_secret_key(self):
        action = HealthCheckAction(
            integration_id="threatconnect",
            action_id="health_check",
            settings=TEST_SETTINGS,
            credentials={"access_id": TEST_ACCESS_ID},
        )
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_empty_credentials(self):
        action = HealthCheckAction(
            integration_id="threatconnect",
            action_id="health_check",
            settings=TEST_SETTINGS,
            credentials={},
        )
        result = await action.execute()
        assert result["status"] == "error"
        assert "credentials" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_api_returns_failure(self, action):
        mock_resp = _json_response({"status": "Failure", "message": "Auth failed"})
        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "APIError"
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_network_error(self, action):
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Connection refused"),
        ):
            result = await action.execute()

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]
        assert result["healthy"] is False


# ===========================================================================
# LOOKUP IP
# ===========================================================================


class TestLookupIpAction:
    @pytest.fixture
    def action(self):
        return LookupIpAction(
            integration_id="threatconnect",
            action_id="lookup_ip",
            settings=TEST_SETTINGS,
            credentials=TEST_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_response = {
            "status": "Success",
            "data": [
                {
                    "id": 12345,
                    "ip": "192.168.1.100",
                    "type": "Address",
                    "rating": 3,
                    "confidence": 80,
                    "ownerName": "TestOrg",
                    "dateAdded": "2025-03-08T09:35:46Z",
                }
            ],
            "count": 1,
        }
        mock_resp = _json_response(api_response)
        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await action.execute(ip="192.168.1.100")

        assert result["status"] == "success"
        assert result["total_objects"] == 1
        assert result["data"]["data"][0]["ip"] == "192.168.1.100"

    @pytest.mark.asyncio
    async def test_success_with_owner_filter(self, action):
        api_response = {"status": "Success", "data": [], "count": 0}
        mock_resp = _json_response(api_response)
        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            result = await action.execute(ip="10.0.0.1", owner="OrgA, OrgB")

        assert result["status"] == "success"
        # Verify the TQL contains owner filter
        call_kwargs = mock_req.call_args.kwargs
        assert "ownerName" in call_kwargs["params"]["tql"]

    @pytest.mark.asyncio
    async def test_not_found_404(self, action):
        with patch.object(
            action, "http_request", new_callable=AsyncMock, side_effect=_http_error(404)
        ):
            result = await action.execute(ip="10.0.0.1")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["total_objects"] == 0

    @pytest.mark.asyncio
    async def test_missing_ip_param(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_ip(self, action):
        result = await action.execute(ip="not-an-ip")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = LookupIpAction(
            integration_id="threatconnect",
            action_id="lookup_ip",
            settings=TEST_SETTINGS,
            credentials={},
        )
        result = await action.execute(ip="192.168.1.1")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_failure_response(self, action):
        mock_resp = _json_response({"status": "Failure", "message": "TQL syntax error"})
        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await action.execute(ip="192.168.1.1")

        assert result["status"] == "error"
        assert result["error_type"] == "APIError"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_http_error(500, "Server Error"),
        ):
            result = await action.execute(ip="192.168.1.1")

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_auth_headers_signed(self, action):
        """Verify that requests include HMAC auth headers."""
        mock_resp = _json_response({"status": "Success", "data": [], "count": 0})
        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            await action.execute(ip="10.0.0.1")

        call_kwargs = mock_req.call_args.kwargs
        headers = call_kwargs["headers"]
        assert headers["Authorization"].startswith(f"TC {TEST_ACCESS_ID}:")
        assert "Timestamp" in headers


# ===========================================================================
# LOOKUP DOMAIN
# ===========================================================================


class TestLookupDomainAction:
    @pytest.fixture
    def action(self):
        return LookupDomainAction(
            integration_id="threatconnect",
            action_id="lookup_domain",
            settings=TEST_SETTINGS,
            credentials=TEST_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_response = {
            "status": "Success",
            "data": [
                {
                    "id": 67890,
                    "hostName": "evil.example.com",
                    "type": "Host",
                    "ownerName": "TestOrg",
                }
            ],
            "count": 1,
        }
        mock_resp = _json_response(api_response)
        # Patch on the _delegated_ LookupIpAction's http_request - but since
        # LookupDomainAction creates a new LookupIpAction, we patch the class method
        with patch(
            "analysi.integrations.framework.integrations.threatconnect.actions.LookupIpAction.http_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await action.execute(domain="evil.example.com")

        assert result["status"] == "success"
        assert result["total_objects"] == 1

    @pytest.mark.asyncio
    async def test_missing_domain(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_empty_domain(self, action):
        result = await action.execute(domain="")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = LookupDomainAction(
            integration_id="threatconnect",
            action_id="lookup_domain",
            settings=TEST_SETTINGS,
            credentials={},
        )
        result = await action.execute(domain="example.com")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# LOOKUP HASH
# ===========================================================================


class TestLookupHashAction:
    @pytest.fixture
    def action(self):
        return LookupHashAction(
            integration_id="threatconnect",
            action_id="lookup_hash",
            settings=TEST_SETTINGS,
            credentials=TEST_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success_md5(self, action):
        api_response = {
            "status": "Success",
            "data": [
                {
                    "id": 111,
                    "md5": "d41d8cd98f00b204e9800998ecf8427e",
                    "type": "File",
                }
            ],
            "count": 1,
        }
        mock_resp = _json_response(api_response)
        with patch(
            "analysi.integrations.framework.integrations.threatconnect.actions.LookupIpAction.http_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await action.execute(hash="d41d8cd98f00b204e9800998ecf8427e")

        assert result["status"] == "success"
        assert result["total_objects"] == 1

    @pytest.mark.asyncio
    async def test_missing_hash(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_hash_length(self, action):
        result = await action.execute(hash="abc123")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "Invalid hash length" in result["error"]

    @pytest.mark.asyncio
    async def test_non_hex_hash(self, action):
        result = await action.execute(hash="zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz")
        assert result["status"] == "error"
        assert "hexadecimal" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = LookupHashAction(
            integration_id="threatconnect",
            action_id="lookup_hash",
            settings=TEST_SETTINGS,
            credentials={},
        )
        result = await action.execute(hash="d41d8cd98f00b204e9800998ecf8427e")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# LOOKUP URL
# ===========================================================================


class TestLookupUrlAction:
    @pytest.fixture
    def action(self):
        return LookupUrlAction(
            integration_id="threatconnect",
            action_id="lookup_url",
            settings=TEST_SETTINGS,
            credentials=TEST_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_response = {
            "status": "Success",
            "data": [{"id": 222, "text": "http://evil.com", "type": "URL"}],
            "count": 1,
        }
        mock_resp = _json_response(api_response)
        with patch(
            "analysi.integrations.framework.integrations.threatconnect.actions.LookupIpAction.http_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await action.execute(url="http://evil.com")

        assert result["status"] == "success"
        assert result["total_objects"] == 1

    @pytest.mark.asyncio
    async def test_missing_url(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = LookupUrlAction(
            integration_id="threatconnect",
            action_id="lookup_url",
            settings=TEST_SETTINGS,
            credentials={},
        )
        result = await action.execute(url="http://test.com")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# LOOKUP EMAIL
# ===========================================================================


class TestLookupEmailAction:
    @pytest.fixture
    def action(self):
        return LookupEmailAction(
            integration_id="threatconnect",
            action_id="lookup_email",
            settings=TEST_SETTINGS,
            credentials=TEST_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_response = {
            "status": "Success",
            "data": [{"id": 333, "address": "bad@evil.com", "type": "EmailAddress"}],
            "count": 1,
        }
        mock_resp = _json_response(api_response)
        with patch(
            "analysi.integrations.framework.integrations.threatconnect.actions.LookupIpAction.http_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await action.execute(email="bad@evil.com")

        assert result["status"] == "success"
        assert result["total_objects"] == 1

    @pytest.mark.asyncio
    async def test_missing_email(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = LookupEmailAction(
            integration_id="threatconnect",
            action_id="lookup_email",
            settings=TEST_SETTINGS,
            credentials={},
        )
        result = await action.execute(email="bad@evil.com")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# CREATE INDICATOR
# ===========================================================================


class TestCreateIndicatorAction:
    @pytest.fixture
    def action(self):
        return CreateIndicatorAction(
            integration_id="threatconnect",
            action_id="create_indicator",
            settings=TEST_SETTINGS,
            credentials=TEST_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_create_ip_indicator(self, action):
        api_response = {
            "status": "Success",
            "data": {"id": 444, "ip": "10.0.0.1", "type": "Address"},
            "message": "Created",
        }
        mock_resp = _json_response(api_response)
        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            result = await action.execute(
                indicator_value="10.0.0.1", indicator_type="ip"
            )

        assert result["status"] == "success"
        assert "Created" in result["message"] or "created" in result["message"].lower()

        # Verify POST body
        call_kwargs = mock_req.call_args.kwargs
        assert call_kwargs["json"]["type"] == "Address"
        assert call_kwargs["json"]["ip"] == "10.0.0.1"

    @pytest.mark.asyncio
    async def test_create_domain_indicator(self, action):
        api_response = {
            "status": "Success",
            "data": {"id": 555, "hostName": "evil.com", "type": "Host"},
            "message": "Created",
        }
        mock_resp = _json_response(api_response)
        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            result = await action.execute(
                indicator_value="evil.com", indicator_type="domain"
            )

        assert result["status"] == "success"
        assert mock_req.call_args.kwargs["json"]["hostName"] == "evil.com"

    @pytest.mark.asyncio
    async def test_create_hash_indicator(self, action):
        md5_hash = "d41d8cd98f00b204e9800998ecf8427e"
        api_response = {
            "status": "Success",
            "data": {"id": 666, "md5": md5_hash, "type": "File"},
        }
        mock_resp = _json_response(api_response)
        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            result = await action.execute(
                indicator_value=md5_hash, indicator_type="hash"
            )

        assert result["status"] == "success"
        assert mock_req.call_args.kwargs["json"]["md5"] == md5_hash

    @pytest.mark.asyncio
    async def test_create_url_indicator(self, action):
        api_response = {
            "status": "Success",
            "data": {"id": 777, "text": "http://evil.com"},
        }
        mock_resp = _json_response(api_response)
        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            result = await action.execute(
                indicator_value="http://evil.com", indicator_type="url"
            )

        assert result["status"] == "success"
        assert mock_req.call_args.kwargs["json"]["text"] == "http://evil.com"

    @pytest.mark.asyncio
    async def test_create_email_indicator(self, action):
        api_response = {
            "status": "Success",
            "data": {"id": 888, "address": "bad@evil.com"},
        }
        mock_resp = _json_response(api_response)
        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            result = await action.execute(
                indicator_value="bad@evil.com", indicator_type="email"
            )

        assert result["status"] == "success"
        assert mock_req.call_args.kwargs["json"]["address"] == "bad@evil.com"

    @pytest.mark.asyncio
    async def test_create_with_rating_and_confidence(self, action):
        api_response = {
            "status": "Success",
            "data": {"id": 999, "ip": "1.2.3.4", "rating": 4, "confidence": 90},
        }
        mock_resp = _json_response(api_response)
        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            result = await action.execute(
                indicator_value="1.2.3.4", indicator_type="ip", rating=4, confidence=90
            )

        assert result["status"] == "success"
        body = mock_req.call_args.kwargs["json"]
        assert body["rating"] == 4
        assert body["confidence"] == 90

    @pytest.mark.asyncio
    async def test_invalid_indicator_type(self, action):
        result = await action.execute(
            indicator_value="test", indicator_type="invalid_type"
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_indicator_value(self, action):
        result = await action.execute(indicator_type="ip")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_indicator_type(self, action):
        result = await action.execute(indicator_value="1.2.3.4")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = CreateIndicatorAction(
            integration_id="threatconnect",
            action_id="create_indicator",
            settings=TEST_SETTINGS,
            credentials={},
        )
        result = await action.execute(indicator_value="1.2.3.4", indicator_type="ip")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_http_error(403, "Forbidden"),
        ):
            result = await action.execute(
                indicator_value="1.2.3.4", indicator_type="ip"
            )

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_post_uses_hmac_headers(self, action):
        """Verify POST requests include HMAC auth headers."""
        mock_resp = _json_response({"status": "Success", "data": {"id": 1}})
        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            await action.execute(indicator_value="1.2.3.4", indicator_type="ip")

        call_kwargs = mock_req.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"].startswith(
            f"TC {TEST_ACCESS_ID}:"
        )
        assert call_kwargs["method"] == "POST"


# ===========================================================================
# LIST OWNERS
# ===========================================================================


class TestListOwnersAction:
    @pytest.fixture
    def action(self):
        return ListOwnersAction(
            integration_id="threatconnect",
            action_id="list_owners",
            settings=TEST_SETTINGS,
            credentials=TEST_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_response = {
            "status": "Success",
            "count": 2,
            "data": [
                {"id": 1, "name": "OrgA", "type": "Organization"},
                {"id": 2, "name": "OrgB", "type": "Community"},
            ],
        }
        mock_resp = _json_response(api_response)
        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await action.execute()

        assert result["status"] == "success"
        assert result["num_owners"] == 2
        assert result["data"]["data"][0]["name"] == "OrgA"

    @pytest.mark.asyncio
    async def test_api_failure_status(self, action):
        mock_resp = _json_response({"status": "Failure", "message": "Auth error"})
        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ):
            result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "APIError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = ListOwnersAction(
            integration_id="threatconnect",
            action_id="list_owners",
            settings=TEST_SETTINGS,
            credentials={},
        )
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_network_error(self, action):
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Timeout"),
        ):
            result = await action.execute()

        assert result["status"] == "error"
        assert "Timeout" in result["error"]


# ===========================================================================
# SANDBOX URL HANDLING
# ===========================================================================


class TestSandboxUrl:
    """Test sandbox.threatconnect.com URL handling."""

    @pytest.mark.asyncio
    async def test_sandbox_url_uses_api_prefix(self):
        action = HealthCheckAction(
            integration_id="threatconnect",
            action_id="health_check",
            settings={"base_url": "https://sandbox.threatconnect.com", "timeout": 10},
            credentials=TEST_CREDENTIALS,
        )
        mock_resp = _json_response(
            {"status": "Success", "count": 1, "data": [{"id": 1}]}
        )
        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            await action.execute()

        call_url = mock_req.call_args.kwargs["url"]
        assert "/api/v3/" in call_url

    @pytest.mark.asyncio
    async def test_standard_url_no_api_prefix(self):
        action = HealthCheckAction(
            integration_id="threatconnect",
            action_id="health_check",
            settings={"base_url": "https://api.threatconnect.com", "timeout": 10},
            credentials=TEST_CREDENTIALS,
        )
        mock_resp = _json_response(
            {"status": "Success", "count": 1, "data": [{"id": 1}]}
        )
        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            await action.execute()

        call_url = mock_req.call_args.kwargs["url"]
        assert call_url.startswith("https://api.threatconnect.com/v3/")
        assert "/api/v3/" not in call_url
