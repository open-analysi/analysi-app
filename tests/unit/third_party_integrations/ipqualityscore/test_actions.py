"""Unit tests for IPQualityScore integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.ipqualityscore.actions import (
    DarkWebLeakLookupAction,
    EmailValidationAction,
    HealthCheckAction,
    IpReputationAction,
    PhoneValidationAction,
    UrlCheckerAction,
    _build_api_url,
    _build_optional_params,
    _validate_email,
    _validate_non_negative_int,
    _validate_strictness,
)
from analysi.integrations.framework.integrations.ipqualityscore.constants import (
    MSG_INVALID_STRICTNESS,
    MSG_MISSING_API_KEY,
)

# ============================================================================
# VALIDATION HELPER TESTS
# ============================================================================


class TestValidateStrictness:
    """Test strictness parameter validation."""

    def test_valid_values(self):
        for val in [0, 1, 2]:
            is_valid, err = _validate_strictness(val)
            assert is_valid is True
            assert err == ""

    def test_none_is_valid(self):
        """None means parameter not provided, which is allowed."""
        is_valid, err = _validate_strictness(None)
        assert is_valid is True

    def test_invalid_out_of_range(self):
        for val in [3, -1, 10]:
            is_valid, err = _validate_strictness(val)
            assert is_valid is False
            assert MSG_INVALID_STRICTNESS in err

    def test_invalid_non_integer(self):
        is_valid, err = _validate_strictness("abc")
        assert is_valid is False


class TestValidateNonNegativeInt:
    """Test non-negative integer validation."""

    def test_valid_values(self):
        for val in [0, 1, 5, 100]:
            is_valid, _ = _validate_non_negative_int(val, "error")
            assert is_valid is True

    def test_none_is_valid(self):
        is_valid, _ = _validate_non_negative_int(None, "error")
        assert is_valid is True

    def test_negative_value(self):
        is_valid, err = _validate_non_negative_int(-1, "must be non-negative")
        assert is_valid is False
        assert "must be non-negative" in err

    def test_non_integer_string(self):
        is_valid, err = _validate_non_negative_int("abc", "must be integer")
        assert is_valid is False


class TestValidateEmail:
    """Test email validation."""

    def test_valid_email(self):
        is_valid, _ = _validate_email("test@example.com")
        assert is_valid is True

    def test_invalid_email(self):
        is_valid, _ = _validate_email("not-an-email")
        assert is_valid is False

    def test_empty_email(self):
        is_valid, _ = _validate_email("")
        assert is_valid is False

    def test_none_email(self):
        is_valid, _ = _validate_email(None)
        assert is_valid is False


class TestBuildApiUrl:
    """Test API URL construction."""

    def test_ip_url(self):
        url = _build_api_url("ip", "test-key", "8.8.8.8")
        assert url == "https://ipqualityscore.com/api/json/ip/test-key/8.8.8.8"

    def test_email_url(self):
        url = _build_api_url("email", "test-key", "user@example.com")
        assert (
            url == "https://ipqualityscore.com/api/json/email/test-key/user@example.com"
        )


class TestBuildOptionalParams:
    """Test optional parameter dict construction."""

    def test_filters_none_values(self):
        result = _build_optional_params(a=1, b=None, c="test")
        assert result == {"a": 1, "c": "test"}

    def test_converts_booleans(self):
        result = _build_optional_params(fast=True, mobile=False)
        assert result == {"fast": "true", "mobile": "false"}

    def test_empty_when_all_none(self):
        result = _build_optional_params(a=None, b=None)
        assert result == {}


# ============================================================================
# HEALTH CHECK ACTION TESTS
# ============================================================================


class TestHealthCheckAction:
    """Test IPQualityScore health check action."""

    @pytest.fixture
    def action(self):
        return HealthCheckAction(
            integration_id="ipqualityscore",
            action_id="health_check",
            settings={},
            credentials={"api_key": "test-key"},
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Test successful health check returns healthy status."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "message": "Success"}

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await action.execute()

        assert result["status"] == "success"
        assert result["healthy"] is True
        assert "integration_id" in result
        assert result["integration_id"] == "ipqualityscore"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test health check fails when API key missing."""
        action = HealthCheckAction(
            integration_id="ipqualityscore",
            action_id="health_check",
            settings={},
            credentials={},
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert MSG_MISSING_API_KEY in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_returns_failure(self, action):
        """Test health check handles API returning success=false."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": False, "message": "Invalid key"}

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await action.execute()

        assert result["status"] == "error"
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_rate_limit_509(self, action):
        """Test health check handles 509 rate limit."""
        mock_request = MagicMock()
        mock_request.url = "https://ipqualityscore.com/api/json/ip/key/8.8.8.8"
        mock_resp = MagicMock()
        mock_resp.status_code = 509
        error = httpx.HTTPStatusError(
            "Rate limited", request=mock_request, response=mock_resp
        )

        with patch.object(
            action, "http_request", new_callable=AsyncMock, side_effect=error
        ):
            result = await action.execute()

        assert result["status"] == "error"
        assert result["healthy"] is False
        assert "rate limit" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_connection_error(self, action):
        """Test health check handles connection errors."""
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Connection refused"),
        ):
            result = await action.execute()

        assert result["status"] == "error"
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_uses_8888_for_connectivity(self, action):
        """Test health check queries 8.8.8.8 (known safe IP)."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ) as mock_req:
            await action.execute()

        call_args = mock_req.call_args
        assert "8.8.8.8" in call_args.kwargs.get(
            "url", call_args.args[0] if call_args.args else ""
        )


# ============================================================================
# IP REPUTATION ACTION TESTS
# ============================================================================


class TestIpReputationAction:
    """Test IPQualityScore IP reputation action."""

    @pytest.fixture
    def action(self):
        return IpReputationAction(
            integration_id="ipqualityscore",
            action_id="ip_reputation",
            settings={},
            credentials={"api_key": "test-key"},
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Test successful IP reputation lookup returns full API response."""
        api_response = {
            "success": True,
            "message": "Success",
            "fraud_score": 75,
            "country_code": "US",
            "city": "Atlanta",
            "ISP": "Comcast",
            "proxy": True,
            "vpn": False,
            "tor": False,
            "active_vpn": False,
            "active_tor": False,
            "bot_status": False,
            "recent_abuse": True,
            "request_id": "abc123",
        }
        mock_response = MagicMock()
        mock_response.json.return_value = api_response

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await action.execute(ip="1.2.3.4")

        assert result["status"] == "success"
        assert result["data"]["fraud_score"] == 75
        assert result["data"]["proxy"] is True
        assert result["data"]["vpn"] is False
        assert result["data"]["request_id"] == "abc123"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_ip(self, action):
        """Test error when IP parameter missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert "ip" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test error when API key missing."""
        action = IpReputationAction(
            integration_id="ipqualityscore",
            action_id="ip_reputation",
            settings={},
            credentials={},
        )
        result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_invalid_strictness(self, action):
        """Test validation rejects invalid strictness value."""
        result = await action.execute(ip="8.8.8.8", strictness=5)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "strictness" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_invalid_transaction_strictness(self, action):
        """Test validation rejects invalid transaction_strictness."""
        result = await action.execute(ip="8.8.8.8", transaction_strictness=-1)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_optional_params_forwarded(self, action):
        """Test optional parameters are forwarded as query params."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "fraud_score": 0}

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ) as mock_req:
            await action.execute(ip="8.8.8.8", strictness=1, fast=True, mobile=False)

        call_kwargs = mock_req.call_args.kwargs
        params = call_kwargs.get("params", {})
        assert params["strictness"] == 1
        assert params["fast"] == "true"
        assert params["mobile"] == "false"

    @pytest.mark.asyncio
    async def test_api_success_false_returns_error(self, action):
        """Test that API returning success=false maps to error result."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": False,
            "message": "Invalid request",
        }

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "error"
        assert result["error_type"] == "APIError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        """Test 404 returns success with not_found flag (does not crash Cy scripts)."""
        mock_request = MagicMock()
        mock_request.url = "https://ipqualityscore.com/api/json/ip/key/0.0.0.0"
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        error = httpx.HTTPStatusError(
            "Not Found", request=mock_request, response=mock_resp
        )

        with patch.object(
            action, "http_request", new_callable=AsyncMock, side_effect=error
        ):
            result = await action.execute(ip="0.0.0.0")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_509_rate_limit(self, action):
        """Test 509 rate limit returns error."""
        mock_request = MagicMock()
        mock_request.url = "https://ipqualityscore.com/api/json/ip/key/8.8.8.8"
        mock_resp = MagicMock()
        mock_resp.status_code = 509
        error = httpx.HTTPStatusError(
            "Rate limited", request=mock_request, response=mock_resp
        )

        with patch.object(
            action, "http_request", new_callable=AsyncMock, side_effect=error
        ):
            result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "error"
        assert "rate limit" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_generic_exception(self, action):
        """Test generic exception is handled."""
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Timeout"),
        ):
            result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "error"
        assert "Timeout" in result["error"]


# ============================================================================
# EMAIL VALIDATION ACTION TESTS
# ============================================================================


class TestEmailValidationAction:
    """Test IPQualityScore email validation action."""

    @pytest.fixture
    def action(self):
        return EmailValidationAction(
            integration_id="ipqualityscore",
            action_id="email_validation",
            settings={},
            credentials={"api_key": "test-key"},
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Test successful email validation returns full API data."""
        api_response = {
            "success": True,
            "message": "Success",
            "valid": True,
            "disposable": False,
            "smtp_score": 3,
            "overall_score": 4,
            "fraud_score": 10,
            "deliverability": "high",
            "honeypot": False,
            "recent_abuse": False,
            "leaked": False,
            "dns_valid": True,
            "request_id": "req-123",
        }
        mock_response = MagicMock()
        mock_response.json.return_value = api_response

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await action.execute(email="test@example.com")

        assert result["status"] == "success"
        assert result["data"]["valid"] is True
        assert result["data"]["fraud_score"] == 10
        assert result["data"]["deliverability"] == "high"

    @pytest.mark.asyncio
    async def test_missing_email(self, action):
        """Test error when email parameter missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert "email" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test error when API key missing."""
        action = EmailValidationAction(
            integration_id="ipqualityscore",
            action_id="email_validation",
            settings={},
            credentials={},
        )
        result = await action.execute(email="test@example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_invalid_strictness(self, action):
        """Test validation rejects invalid strictness."""
        result = await action.execute(email="test@example.com", strictness=99)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_timeout(self, action):
        """Test validation rejects negative timeout."""
        result = await action.execute(email="test@example.com", timeout=-5)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_abuse_strictness(self, action):
        """Test validation rejects invalid abuse_strictness."""
        result = await action.execute(email="test@example.com", abuse_strictness=-1)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_optional_params_forwarded(self, action):
        """Test optional params are forwarded correctly."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "valid": True,
            "fraud_score": 0,
        }

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ) as mock_req:
            await action.execute(
                email="test@example.com", fast=True, suggest_domain=True, strictness=1
            )

        params = mock_req.call_args.kwargs.get("params", {})
        assert params["fast"] == "true"
        assert params["suggest_domain"] == "true"
        assert params["strictness"] == 1

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        """Test 404 returns success with not_found flag."""
        mock_request = MagicMock()
        mock_request.url = (
            "https://ipqualityscore.com/api/json/email/key/test@example.com"
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        error = httpx.HTTPStatusError(
            "Not Found", request=mock_request, response=mock_resp
        )

        with patch.object(
            action, "http_request", new_callable=AsyncMock, side_effect=error
        ):
            result = await action.execute(email="test@example.com")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_api_failure(self, action):
        """Test API returning success=false is handled."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": False, "message": "Bad key"}

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await action.execute(email="test@example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "APIError"


# ============================================================================
# URL CHECKER ACTION TESTS
# ============================================================================


class TestUrlCheckerAction:
    """Test IPQualityScore URL checker action."""

    @pytest.fixture
    def action(self):
        return UrlCheckerAction(
            integration_id="ipqualityscore",
            action_id="url_checker",
            settings={},
            credentials={"api_key": "test-key"},
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Test successful URL check returns full API data."""
        api_response = {
            "success": True,
            "message": "Success",
            "status_code": 200,
            "unsafe": False,
            "domain": "example.com",
            "risk_score": 5,
            "malware": False,
            "phishing": False,
            "suspicious": False,
            "request_id": "url-req-123",
        }
        mock_response = MagicMock()
        mock_response.json.return_value = api_response

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await action.execute(url="https://example.com")

        assert result["status"] == "success"
        assert result["data"]["risk_score"] == 5
        assert result["data"]["malware"] is False

    @pytest.mark.asyncio
    async def test_missing_url(self, action):
        """Test error when URL parameter missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert "url" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test error when API key missing."""
        action = UrlCheckerAction(
            integration_id="ipqualityscore",
            action_id="url_checker",
            settings={},
            credentials={},
        )
        result = await action.execute(url="https://example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_url_is_encoded_in_path(self, action):
        """Test that the URL is URL-encoded in the API path."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "status_code": 200,
            "risk_score": 0,
        }

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ) as mock_req:
            await action.execute(url="https://example.com/path?q=test")

        call_url = mock_req.call_args.kwargs.get("url", "")
        # The target URL should be URL-encoded in the path
        assert "https%3A%2F%2Fexample.com%2Fpath%3Fq%3Dtest" in call_url

    @pytest.mark.asyncio
    async def test_invalid_strictness(self, action):
        """Test validation rejects invalid strictness."""
        result = await action.execute(url="https://example.com", strictness=5)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_api_status_code_not_200(self, action):
        """Test handling of API returning non-200 status_code in body."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": False,
            "message": "URL unreachable",
            "status_code": 400,
        }

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await action.execute(url="https://example.com")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        """Test 404 returns success with not_found flag."""
        mock_request = MagicMock()
        mock_request.url = "https://ipqualityscore.com/api/json/url/key/test"
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        error = httpx.HTTPStatusError(
            "Not Found", request=mock_request, response=mock_resp
        )

        with patch.object(
            action, "http_request", new_callable=AsyncMock, side_effect=error
        ):
            result = await action.execute(url="https://example.com")

        assert result["status"] == "success"
        assert result["not_found"] is True


# ============================================================================
# PHONE VALIDATION ACTION TESTS
# ============================================================================


class TestPhoneValidationAction:
    """Test IPQualityScore phone validation action."""

    @pytest.fixture
    def action(self):
        return PhoneValidationAction(
            integration_id="ipqualityscore",
            action_id="phone_validation",
            settings={},
            credentials={"api_key": "test-key"},
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Test successful phone validation returns full API data."""
        api_response = {
            "success": True,
            "message": "Phone is valid.",
            "formatted": "+18005551234",
            "local_format": "(800) 555-1234",
            "valid": True,
            "fraud_score": 0,
            "recent_abuse": False,
            "VOIP": False,
            "prepaid": False,
            "risky": False,
            "active": True,
            "carrier": "AT&T",
            "line_type": "Wireless",
            "country": "US",
            "request_id": "phone-123",
        }
        mock_response = MagicMock()
        mock_response.json.return_value = api_response

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await action.execute(phone="18005551234")

        assert result["status"] == "success"
        assert result["data"]["valid"] is True
        assert result["data"]["carrier"] == "AT&T"
        assert result["data"]["fraud_score"] == 0

    @pytest.mark.asyncio
    async def test_missing_phone(self, action):
        """Test error when phone parameter missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert "phone" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test error when API key missing."""
        action = PhoneValidationAction(
            integration_id="ipqualityscore",
            action_id="phone_validation",
            settings={},
            credentials={},
        )
        result = await action.execute(phone="18005551234")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_invalid_strictness(self, action):
        """Test validation rejects invalid strictness."""
        result = await action.execute(phone="18005551234", strictness=10)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_country_param_forwarded(self, action):
        """Test country parameter is forwarded."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "valid": True,
            "fraud_score": 0,
        }

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ) as mock_req:
            await action.execute(phone="18005551234", country="US,CA")

        params = mock_req.call_args.kwargs.get("params", {})
        assert params["country"] == "US,CA"

    @pytest.mark.asyncio
    async def test_api_failure(self, action):
        """Test API returning success=false."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": False, "message": "Invalid phone"}

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await action.execute(phone="000")

        assert result["status"] == "error"
        assert result["error_type"] == "APIError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        """Test 404 returns success with not_found flag."""
        mock_request = MagicMock()
        mock_request.url = "https://ipqualityscore.com/api/json/phone/key/000"
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        error = httpx.HTTPStatusError(
            "Not Found", request=mock_request, response=mock_resp
        )

        with patch.object(
            action, "http_request", new_callable=AsyncMock, side_effect=error
        ):
            result = await action.execute(phone="000")

        assert result["status"] == "success"
        assert result["not_found"] is True


# ============================================================================
# DARK WEB LEAK LOOKUP ACTION TESTS
# ============================================================================


class TestDarkWebLeakLookupAction:
    """Test IPQualityScore dark web leak lookup action."""

    @pytest.fixture
    def action(self):
        return DarkWebLeakLookupAction(
            integration_id="ipqualityscore",
            action_id="dark_web_leak_lookup",
            settings={},
            credentials={"api_key": "test-key"},
        )

    @pytest.mark.asyncio
    async def test_success_email_lookup(self, action):
        """Test successful dark web leak lookup for email."""
        api_response = {
            "success": True,
            "message": "Success",
            "exposed": True,
            "source": "Exploit Antipublic",
            "first_seen": {"human": "2 years ago", "timestamp": 1609459200},
            "plain_text_password": False,
            "request_id": "leak-123",
        }
        mock_response = MagicMock()
        mock_response.json.return_value = api_response

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await action.execute(type="email", value="test@example.com")

        assert result["status"] == "success"
        assert result["data"]["exposed"] is True
        assert result["data"]["source"] == "Exploit Antipublic"

    @pytest.mark.asyncio
    async def test_success_username_lookup(self, action):
        """Test successful dark web leak lookup for username."""
        api_response = {
            "success": True,
            "message": "Success",
            "exposed": False,
            "request_id": "leak-456",
        }
        mock_response = MagicMock()
        mock_response.json.return_value = api_response

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await action.execute(type="username", value="testuser")

        assert result["status"] == "success"
        assert result["data"]["exposed"] is False

    @pytest.mark.asyncio
    async def test_success_password_lookup(self, action):
        """Test dark web leak lookup for password type."""
        api_response = {
            "success": True,
            "message": "Success",
            "exposed": True,
            "request_id": "leak-789",
        }
        mock_response = MagicMock()
        mock_response.json.return_value = api_response

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await action.execute(type="password", value="p@ssword123")

        assert result["status"] == "success"
        assert result["data"]["exposed"] is True

    @pytest.mark.asyncio
    async def test_missing_type(self, action):
        """Test error when type parameter missing."""
        result = await action.execute(value="test@example.com")

        assert result["status"] == "error"
        assert "type" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_type(self, action):
        """Test error when type is not a valid value."""
        result = await action.execute(type="invalid", value="test")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_value(self, action):
        """Test error when value parameter missing."""
        result = await action.execute(type="email")

        assert result["status"] == "error"
        assert "value" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_email_type_validates_email_format(self, action):
        """Test that email type validates the email format."""
        result = await action.execute(type="email", value="not-an-email")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "email" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_password_type_skips_email_validation(self, action):
        """Test that password type does not validate as email."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "exposed": False}

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await action.execute(type="password", value="not-an-email")

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test error when API key missing."""
        action = DarkWebLeakLookupAction(
            integration_id="ipqualityscore",
            action_id="dark_web_leak_lookup",
            settings={},
            credentials={},
        )
        result = await action.execute(type="email", value="test@example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_url_contains_leak_type_in_path(self, action):
        """Test that the API URL uses the correct leak type path."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "exposed": False}

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ) as mock_req:
            await action.execute(type="username", value="testuser")

        call_url = mock_req.call_args.kwargs.get("url", "")
        assert "/leaked/username/" in call_url

    @pytest.mark.asyncio
    async def test_value_is_url_encoded(self, action):
        """Test that the value is URL-encoded in the API path."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "exposed": False}

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ) as mock_req:
            await action.execute(type="email", value="test+user@example.com")

        call_url = mock_req.call_args.kwargs.get("url", "")
        assert "test%2Buser%40example.com" in call_url

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        """Test 404 returns success with not_found flag."""
        mock_request = MagicMock()
        mock_request.url = "https://ipqualityscore.com/api/json/leaked/email/key/test"
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        error = httpx.HTTPStatusError(
            "Not Found", request=mock_request, response=mock_resp
        )

        with patch.object(
            action, "http_request", new_callable=AsyncMock, side_effect=error
        ):
            result = await action.execute(type="email", value="test@example.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["exposed"] is False

    @pytest.mark.asyncio
    async def test_api_failure(self, action):
        """Test API returning success=false."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": False, "message": "Bad request"}

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await action.execute(type="email", value="test@example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "APIError"

    @pytest.mark.asyncio
    async def test_generic_exception(self, action):
        """Test generic exception is handled."""
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Timeout"),
        ):
            result = await action.execute(type="email", value="test@example.com")

        assert result["status"] == "error"
        assert "Timeout" in result["error"]
