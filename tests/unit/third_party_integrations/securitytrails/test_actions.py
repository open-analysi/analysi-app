"""Unit tests for SecurityTrails integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.securitytrails.actions import (
    DomainCategoryAction,
    DomainHistoryAction,
    DomainSearcherAction,
    DomainSubdomainAction,
    HealthCheckAction,
    LookupDomainAction,
    WhoisDomainAction,
    WhoisHistoryAction,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

DEFAULT_CREDENTIALS = {"api_key": "test-st-key"}
DEFAULT_SETTINGS = {
    "base_url": "https://api.securitytrails.com/v1",
    "timeout": 30,
}


def _make_action(cls, credentials=None, settings=None):
    """Create an action instance for testing."""
    return cls(
        integration_id="securitytrails",
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
    """Verify get_http_headers injects the APIKEY header."""

    def test_headers_with_key(self):
        action = _make_action(HealthCheckAction)
        headers = action.get_http_headers()
        assert headers == {"APIKEY": "test-st-key"}

    def test_headers_without_key(self):
        action = _make_action(HealthCheckAction, credentials={})
        headers = action.get_http_headers()
        assert headers == {}

    def test_base_url_from_settings(self):
        action = _make_action(HealthCheckAction)
        assert action.base_url == "https://api.securitytrails.com/v1"

    def test_base_url_trailing_slash_stripped(self):
        action = _make_action(
            HealthCheckAction,
            settings={"base_url": "https://api.securitytrails.com/v1/"},
        )
        assert action.base_url == "https://api.securitytrails.com/v1"

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
        ping_resp = _mock_response({"success": True})
        action.http_request = AsyncMock(return_value=ping_resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert "integration_id" in result
        action.http_request.assert_called_once()

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
# LOOKUP DOMAIN
# ============================================================================


class TestLookupDomainAction:
    @pytest.fixture
    def action(self):
        return _make_action(LookupDomainAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_data = {
            "hostname": "example.com",
            "alexa_rank": 42,
            "current_dns": {
                "a": {"values": [{"ip": "93.184.216.34"}]},
                "aaaa": {"values": [{"ipv6": "2606:2800:220:1::248"}]},
            },
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_data))

        result = await action.execute(domain="example.com")

        assert result["status"] == "success"
        assert result["data"]["hostname"] == "example.com"
        assert result["data"]["alexa_rank"] == 42
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_domain(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "domain" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(LookupDomainAction, credentials={})
        result = await action.execute(domain="example.com")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404, "Not Found"))
        result = await action.execute(domain="nonexistent.example")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["domain"] == "nonexistent.example"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Internal Server Error")
        )
        result = await action.execute(domain="example.com")
        assert result["status"] == "error"


# ============================================================================
# WHOIS DOMAIN
# ============================================================================


class TestWhoisDomainAction:
    @pytest.fixture
    def action(self):
        return _make_action(WhoisDomainAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        whois_data = {
            "contacts": [
                {
                    "type": "registrant",
                    "organization": "Example Inc",
                    "email": "admin@example.com",
                    "city": "Los Angeles",
                    "countryCode": "US",
                }
            ],
            "createdDate": "2000-01-01",
            "updatedDate": "2024-01-01",
        }
        action.http_request = AsyncMock(return_value=_mock_response(whois_data))

        result = await action.execute(domain="example.com")

        assert result["status"] == "success"
        assert result["data"]["contacts"][0]["organization"] == "Example Inc"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_domain(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(WhoisDomainAction, credentials={})
        result = await action.execute(domain="example.com")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(domain="unknown.example")
        assert result["status"] == "success"
        assert result["not_found"] is True


# ============================================================================
# WHOIS HISTORY
# ============================================================================


class TestWhoisHistoryAction:
    @pytest.fixture
    def action(self):
        return _make_action(WhoisHistoryAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        history_data = {
            "result": {
                "items": [
                    {"contact": [{"type": "registrant", "organization": "Old Corp"}]}
                ]
            },
            "pages": 1,
        }
        action.http_request = AsyncMock(return_value=_mock_response(history_data))

        result = await action.execute(domain="example.com")

        assert result["status"] == "success"
        assert "result" in result["data"]
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_domain(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(WhoisHistoryAction, credentials={})
        result = await action.execute(domain="example.com")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(domain="unknown.example")
        assert result["status"] == "success"
        assert result["not_found"] is True


# ============================================================================
# DOMAIN SEARCHER
# ============================================================================


class TestDomainSearcherAction:
    @pytest.fixture
    def action(self):
        return _make_action(DomainSearcherAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        search_data = {
            "records": [
                {"hostname": "example.com", "alexa_rank": 42},
                {"hostname": "sub.example.com", "alexa_rank": 100},
            ],
            "record_count": 2,
        }
        action.http_request = AsyncMock(return_value=_mock_response(search_data))

        result = await action.execute(filter="apex_domain", filterstring="example.com")

        assert result["status"] == "success"
        assert len(result["data"]["records"]) == 2
        assert "integration_id" in result

        # Verify POST payload
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["json_data"] == {"filter": {"apex_domain": "example.com"}}

    @pytest.mark.asyncio
    async def test_with_keyword(self, action):
        search_data = {"records": [], "record_count": 0}
        action.http_request = AsyncMock(return_value=_mock_response(search_data))

        result = await action.execute(
            filter="mx",
            filterstring="alt4.aspmx.l.google.com",
            keyword="stackover",
        )

        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["json_data"] == {
            "filter": {
                "mx": "alt4.aspmx.l.google.com",
                "keyword": "stackover",
            }
        }

    @pytest.mark.asyncio
    async def test_missing_filter(self, action):
        result = await action.execute(filterstring="value")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "filter" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_filterstring(self, action):
        result = await action.execute(filter="ipv4")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "filterstring" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_filter(self, action):
        result = await action.execute(filter="invalid_type", filterstring="value")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "invalid_type" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(DomainSearcherAction, credentials={})
        result = await action.execute(filter="ipv4", filterstring="1.2.3.4")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Internal Server Error")
        )
        result = await action.execute(filter="ipv4", filterstring="1.2.3.4")
        assert result["status"] == "error"


# ============================================================================
# DOMAIN CATEGORY
# ============================================================================


class TestDomainCategoryAction:
    @pytest.fixture
    def action(self):
        return _make_action(DomainCategoryAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        tag_data = {"tags": ["technology", "news"]}
        action.http_request = AsyncMock(return_value=_mock_response(tag_data))

        result = await action.execute(domain="example.com")

        assert result["status"] == "success"
        assert result["data"]["tags"] == ["technology", "news"]
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_empty_tags(self, action):
        tag_data = {"tags": []}
        action.http_request = AsyncMock(return_value=_mock_response(tag_data))

        result = await action.execute(domain="obscure.example")
        assert result["status"] == "success"
        assert result["data"]["tags"] == []

    @pytest.mark.asyncio
    async def test_missing_domain(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(DomainCategoryAction, credentials={})
        result = await action.execute(domain="example.com")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(domain="unknown.example")
        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["tags"] == []


# ============================================================================
# DOMAIN SUBDOMAIN
# ============================================================================


class TestDomainSubdomainAction:
    @pytest.fixture
    def action(self):
        return _make_action(DomainSubdomainAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        sub_data = {"subdomains": ["www", "mail", "api"]}
        action.http_request = AsyncMock(return_value=_mock_response(sub_data))

        result = await action.execute(domain="example.com")

        assert result["status"] == "success"
        assert result["data"]["subdomain_count"] == 3
        assert result["data"]["subdomains"] == [
            {"domain": "www.example.com"},
            {"domain": "mail.example.com"},
            {"domain": "api.example.com"},
        ]
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_empty_subdomains(self, action):
        sub_data = {"subdomains": []}
        action.http_request = AsyncMock(return_value=_mock_response(sub_data))

        result = await action.execute(domain="obscure.example")
        assert result["status"] == "success"
        assert result["data"]["subdomain_count"] == 0
        assert result["data"]["subdomains"] == []

    @pytest.mark.asyncio
    async def test_missing_domain(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(DomainSubdomainAction, credentials={})
        result = await action.execute(domain="example.com")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(domain="unknown.example")
        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["subdomain_count"] == 0


# ============================================================================
# DOMAIN HISTORY
# ============================================================================


class TestDomainHistoryAction:
    @pytest.fixture
    def action(self):
        return _make_action(DomainHistoryAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        history_data = {
            "records": [
                {
                    "values": [{"ip": "93.184.216.34"}],
                    "organizations": ["Edgecast"],
                    "first_seen": "2014-01-01",
                    "last_seen": "2024-01-01",
                }
            ],
            "pages": 1,
        }
        action.http_request = AsyncMock(return_value=_mock_response(history_data))

        result = await action.execute(domain="example.com", record_type="a")

        assert result["status"] == "success"
        assert len(result["data"]["records"]) == 1
        assert result["data"]["records"][0]["first_seen"] == "2014-01-01"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_default_record_type(self, action):
        history_data = {"records": [], "pages": 1}
        action.http_request = AsyncMock(return_value=_mock_response(history_data))

        result = await action.execute(domain="example.com")

        assert result["status"] == "success"
        # Verify the URL used 'a' as default record type
        call_kwargs = action.http_request.call_args.kwargs
        assert "/dns/a" in call_kwargs["url"]

    @pytest.mark.asyncio
    async def test_aaaa_record_type(self, action):
        history_data = {"records": [], "pages": 1}
        action.http_request = AsyncMock(return_value=_mock_response(history_data))

        result = await action.execute(domain="example.com", record_type="aaaa")

        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args.kwargs
        assert "/dns/aaaa" in call_kwargs["url"]

    @pytest.mark.asyncio
    async def test_invalid_record_type(self, action):
        result = await action.execute(domain="example.com", record_type="ptr")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ptr" in result["error"]

    @pytest.mark.asyncio
    async def test_case_insensitive_record_type(self, action):
        history_data = {"records": [], "pages": 1}
        action.http_request = AsyncMock(return_value=_mock_response(history_data))

        result = await action.execute(domain="example.com", record_type="MX")

        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args.kwargs
        assert "/dns/mx" in call_kwargs["url"]

    @pytest.mark.asyncio
    async def test_missing_domain(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "domain" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(DomainHistoryAction, credentials={})
        result = await action.execute(domain="example.com")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(domain="unknown.example", record_type="a")
        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["records"] == []

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Internal Server Error")
        )
        result = await action.execute(domain="example.com", record_type="a")
        assert result["status"] == "error"
