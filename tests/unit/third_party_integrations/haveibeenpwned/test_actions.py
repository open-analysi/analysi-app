"""Unit tests for Have I Been Pwned integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.haveibeenpwned.actions import (
    HealthCheckAction,
    LookupDomainAction,
    LookupEmailAction,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

DEFAULT_CREDENTIALS = {"api_key": "test-hibp-key"}
DEFAULT_SETTINGS = {
    "base_url": "https://haveibeenpwned.com/api/v3",
    "timeout": 30,
}


def _make_action(cls, credentials=None, settings=None):
    """Create an action instance for testing."""
    return cls(
        integration_id="haveibeenpwned",
        action_id=cls.__name__,
        settings=DEFAULT_SETTINGS.copy() if settings is None else settings,
        credentials=DEFAULT_CREDENTIALS.copy() if credentials is None else credentials,
    )


def _mock_response(json_data, status_code=200):
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.text = str(json_data)
    return resp


def _mock_http_error(status_code, message="error"):
    """Create a mock httpx.HTTPStatusError."""
    request = MagicMock(spec=httpx.Request)
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = message
    return httpx.HTTPStatusError(message, request=request, response=response)


# ============================================================================
# AUTH HEADER INJECTION
# ============================================================================


class TestAuthHeaders:
    """Verify get_http_headers injects the hibp-api-key header."""

    def test_headers_with_api_key(self):
        action = _make_action(HealthCheckAction)
        headers = action.get_http_headers()
        assert headers == {"hibp-api-key": "test-hibp-key"}

    def test_headers_without_api_key(self):
        action = _make_action(HealthCheckAction, credentials={})
        headers = action.get_http_headers()
        assert headers == {}

    def test_base_url_from_settings(self):
        action = _make_action(HealthCheckAction)
        assert action.base_url == "https://haveibeenpwned.com/api/v3"

    def test_base_url_custom(self):
        action = _make_action(
            HealthCheckAction,
            settings={"base_url": "https://custom.hibp.example/api"},
        )
        assert action.base_url == "https://custom.hibp.example/api"

    def test_timeout_default(self):
        action = _make_action(HealthCheckAction, settings={})
        assert action.get_timeout() == 30

    def test_timeout_custom(self):
        action = _make_action(HealthCheckAction, settings={"timeout": 60})
        assert action.get_timeout() == 60


# ============================================================================
# HEALTH CHECK
# ============================================================================


class TestHealthCheckAction:
    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Health check passes when API returns breach data for test email."""
        action.http_request = AsyncMock(
            return_value=_mock_response([{"Name": "Adobe"}])
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert "integration_id" in result
        action.http_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_success_404_no_breaches(self, action):
        """Health check passes even when test email has no breaches (404)."""
        action.http_request = AsyncMock(side_effect=_mock_http_error(404, "Not Found"))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(HealthCheckAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "api_key" in result["error"]

    @pytest.mark.asyncio
    async def test_connection_error(self, action):
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_http_401_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(401, "Unauthorized")
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert "HTTPStatusError" in result["error_type"]


# ============================================================================
# LOOKUP EMAIL
# ============================================================================


class TestLookupEmailAction:
    @pytest.fixture
    def action(self):
        return _make_action(LookupEmailAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Successful lookup returns breach list and count."""
        breaches = [
            {
                "Name": "Adobe",
                "Domain": "adobe.com",
                "BreachDate": "2013-10-04",
                "PwnCount": 152445165,
                "DataClasses": ["Email addresses", "Password hints", "Passwords"],
                "IsVerified": True,
                "IsSensitive": False,
            },
            {
                "Name": "LinkedIn",
                "Domain": "linkedin.com",
                "BreachDate": "2012-05-05",
                "PwnCount": 164611595,
                "DataClasses": ["Email addresses", "Passwords"],
                "IsVerified": True,
                "IsSensitive": False,
            },
        ]
        action.http_request = AsyncMock(return_value=_mock_response(breaches))

        result = await action.execute(email="user@example.com")

        assert result["status"] == "success"
        assert result["data"]["email"] == "user@example.com"
        assert result["data"]["total_breaches"] == 2
        assert len(result["data"]["breaches"]) == 2
        assert result["data"]["breaches"][0]["Name"] == "Adobe"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_success_truncated(self, action):
        """Truncated lookup only sends truncateResponse when False."""
        action.http_request = AsyncMock(
            return_value=_mock_response([{"Name": "Adobe"}])
        )

        result = await action.execute(email="user@example.com", truncate=True)

        assert result["status"] == "success"
        # When truncate=True, no truncateResponse param should be sent
        call_kwargs = action.http_request.call_args.kwargs
        assert "truncateResponse" not in call_kwargs.get("params", {})

    @pytest.mark.asyncio
    async def test_not_truncated_sends_param(self, action):
        """Non-truncated lookup sends truncateResponse=false."""
        action.http_request = AsyncMock(
            return_value=_mock_response([{"Name": "Adobe"}])
        )

        result = await action.execute(email="user@example.com", truncate=False)

        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["params"]["truncateResponse"] == "false"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        """Email with no breaches returns not_found=True (not an error)."""
        action.http_request = AsyncMock(side_effect=_mock_http_error(404, "Not Found"))

        result = await action.execute(email="clean@example.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["email"] == "clean@example.com"
        assert result["data"]["total_breaches"] == 0
        assert result["data"]["breaches"] == []

    @pytest.mark.asyncio
    async def test_missing_email(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "email" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(LookupEmailAction, credentials={})
        result = await action.execute(email="user@example.com")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_429_rate_limit(self, action):
        """Rate limiting (429) is a real error, not not_found."""
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(429, "Rate limit exceeded")
        )
        result = await action.execute(email="user@example.com")

        assert result["status"] == "error"
        assert "HTTPStatusError" in result["error_type"]

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Internal Server Error")
        )
        result = await action.execute(email="user@example.com")

        assert result["status"] == "error"


# ============================================================================
# LOOKUP DOMAIN
# ============================================================================


class TestLookupDomainAction:
    @pytest.fixture
    def action(self):
        return _make_action(LookupDomainAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Successful domain lookup returns breach list and count."""
        breaches = [
            {
                "Name": "Adobe",
                "Domain": "adobe.com",
                "BreachDate": "2013-10-04",
                "PwnCount": 152445165,
                "DataClasses": ["Email addresses", "Password hints", "Passwords"],
                "IsVerified": True,
            },
        ]
        action.http_request = AsyncMock(return_value=_mock_response(breaches))

        result = await action.execute(domain="adobe.com")

        assert result["status"] == "success"
        assert result["data"]["domain"] == "adobe.com"
        assert result["data"]["total_breaches"] == 1
        assert result["data"]["breaches"][0]["Name"] == "Adobe"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_url_normalisation(self, action):
        """URL input is normalised to bare domain with www. stripped."""
        action.http_request = AsyncMock(return_value=_mock_response([]))

        result = await action.execute(domain="https://www.adobe.com/some/path")

        assert result["status"] == "success"
        # Verify the domain param sent to the API is the cleaned domain
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["params"]["domain"] == "adobe.com"

    @pytest.mark.asyncio
    async def test_www_prefix_stripped(self, action):
        """Plain www.domain input has www. stripped."""
        action.http_request = AsyncMock(return_value=_mock_response([]))

        result = await action.execute(domain="www.adobe.com")

        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["params"]["domain"] == "adobe.com"

    @pytest.mark.asyncio
    async def test_bare_domain_unchanged(self, action):
        """Bare domain without www. passes through unchanged."""
        action.http_request = AsyncMock(return_value=_mock_response([]))

        result = await action.execute(domain="adobe.com")

        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["params"]["domain"] == "adobe.com"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        """Domain with no breaches returns not_found=True."""
        action.http_request = AsyncMock(side_effect=_mock_http_error(404, "Not Found"))

        result = await action.execute(domain="clean-domain.example")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["domain"] == "clean-domain.example"
        assert result["data"]["total_breaches"] == 0
        assert result["data"]["breaches"] == []

    @pytest.mark.asyncio
    async def test_missing_domain(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "domain" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(LookupDomainAction, credentials={})
        result = await action.execute(domain="adobe.com")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Internal Server Error")
        )
        result = await action.execute(domain="adobe.com")

        assert result["status"] == "error"


# ============================================================================
# DOMAIN NORMALISATION UNIT TESTS
# ============================================================================


class TestDomainNormalisation:
    """Test the _normalise_domain static method directly."""

    def test_bare_domain(self):
        assert LookupDomainAction._normalise_domain("example.com") == "example.com"

    def test_www_prefix(self):
        assert LookupDomainAction._normalise_domain("www.example.com") == "example.com"

    def test_https_url(self):
        assert (
            LookupDomainAction._normalise_domain("https://example.com") == "example.com"
        )

    def test_https_url_with_www(self):
        assert (
            LookupDomainAction._normalise_domain("https://www.example.com/path")
            == "example.com"
        )

    def test_http_url(self):
        assert (
            LookupDomainAction._normalise_domain("http://example.com/path?q=1")
            == "example.com"
        )

    def test_subdomain_preserved(self):
        assert (
            LookupDomainAction._normalise_domain("sub.example.com") == "sub.example.com"
        )

    def test_subdomain_www_stripped(self):
        assert (
            LookupDomainAction._normalise_domain("www.sub.example.com")
            == "sub.example.com"
        )
