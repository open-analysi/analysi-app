"""Unit tests for PassiveTotal integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.passivetotal.actions import (
    GetHostComponentsAction,
    GetHostPairsAction,
    HealthCheckAction,
    LookupCertificateAction,
    LookupCertificateHashAction,
    LookupDomainAction,
    LookupIpAction,
    WhoisDomainAction,
    WhoisIpAction,
    _is_valid_date,
    _is_valid_ip,
    _validate_date_range,
)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

DEFAULT_CREDENTIALS = {"username": "test-pt-user", "api_key": "test-pt-key"}
DEFAULT_SETTINGS = {
    "base_url": "https://api.riskiq.net/pt/v2",
    "timeout": 30,
}


def _make_action(cls, credentials=None, settings=None):
    """Create an action instance for testing."""
    return cls(
        integration_id="passivetotal",
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
# HELPERS
# ============================================================================


class TestHelpers:
    def test_is_valid_ip_v4(self):
        assert _is_valid_ip("1.2.3.4") is True

    def test_is_valid_ip_v6(self):
        assert _is_valid_ip("2001:db8::1") is True

    def test_is_valid_ip_invalid(self):
        assert _is_valid_ip("not-an-ip") is False

    def test_is_valid_ip_empty(self):
        assert _is_valid_ip("") is False

    def test_is_valid_date_good(self):
        assert _is_valid_date("2026-05-10") is True

    def test_is_valid_date_bad(self):
        assert _is_valid_date("05-10-2026") is False

    def test_validate_date_range_valid(self):
        assert _validate_date_range("2026-04-26", "2026-05-26") is None

    def test_validate_date_range_reversed(self):
        result = _validate_date_range("2026-06-26", "2026-04-26")
        assert result is not None
        assert "after" in result

    def test_validate_date_range_bad_from(self):
        result = _validate_date_range("bad-date", "2026-04-26")
        assert result is not None

    def test_validate_date_range_none(self):
        assert _validate_date_range(None, None) is None


# ============================================================================
# BASE CLASS
# ============================================================================


class TestPassiveTotalBase:
    def test_base_url_strips_trailing_slash(self):
        action = _make_action(
            HealthCheckAction,
            settings={**DEFAULT_SETTINGS, "base_url": "https://api.riskiq.net/pt/v2/"},
        )
        assert action.base_url == "https://api.riskiq.net/pt/v2"

    def test_auth_returns_tuple(self):
        action = _make_action(HealthCheckAction)
        assert action._auth == ("test-pt-user", "test-pt-key")

    def test_auth_returns_none_when_missing(self):
        action = _make_action(HealthCheckAction, credentials={})
        assert action._auth is None

    def test_require_credentials_passes(self):
        action = _make_action(HealthCheckAction)
        assert action._require_credentials() is None

    def test_require_credentials_fails(self):
        action = _make_action(HealthCheckAction, credentials={})
        result = action._require_credentials()
        assert result is not None
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# HEALTH CHECK
# ============================================================================


class TestHealthCheckAction:
    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        mock_resp = _mock_response(
            {"queryValue": "passivetotal.org", "queryType": "domain"}
        )
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert "integration_id" in result
        action.http_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_basic_auth(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response({"queryValue": "x"})
        )
        await action.execute()
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["auth"] == ("test-pt-user", "test-pt-key")

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(HealthCheckAction, credentials={})
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(401, "Unauthorized")
        )
        result = await action.execute()
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_connection_error(self, action):
        action.http_request = AsyncMock(side_effect=httpx.ConnectError("refused"))
        result = await action.execute()
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
        enrichment_resp = _mock_response(
            {"queryValue": "example.com", "everCompromised": False}
        )
        passive_resp = _mock_response({"firstSeen": "2026-04-26", "results": []})
        classification_resp = _mock_response({"classification": "benign"})

        action.http_request = AsyncMock(
            side_effect=[enrichment_resp, passive_resp, classification_resp]
        )

        result = await action.execute(domain="example.com")

        assert result["status"] == "success"
        assert result["data"]["query"] == "example.com"
        assert "metadata" in result["data"]
        assert "passive" in result["data"]
        assert "classification" in result["data"]
        assert "integration_id" in result
        assert action.http_request.call_count == 3

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
    async def test_invalid_from_date(self, action):
        result = await action.execute(domain="example.com", **{"from": "bad-date"})
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_reversed_date_range(self, action):
        result = await action.execute(
            domain="example.com", **{"from": "2026-09-26", "to": "2026-04-26"}
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(domain="nonexistent.xyz")
        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["domain"] == "nonexistent.xyz"

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))
        result = await action.execute(domain="example.com")
        assert result["status"] == "error"


# ============================================================================
# LOOKUP IP
# ============================================================================


class TestLookupIpAction:
    @pytest.fixture
    def action(self):
        return _make_action(LookupIpAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        enrichment_resp = _mock_response({"queryValue": "8.8.8.8", "country": "US"})
        passive_resp = _mock_response({"firstSeen": "2026-04-26", "results": []})
        classification_resp = _mock_response({"classification": "benign"})
        ssl_resp = _mock_response(
            {"results": [{"sha1": "abc123", "firstSeen": "2026-04-26"}]}
        )

        action.http_request = AsyncMock(
            side_effect=[enrichment_resp, passive_resp, classification_resp, ssl_resp]
        )

        result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "success"
        assert result["data"]["query"] == "8.8.8.8"
        assert "metadata" in result["data"]
        assert "passive" in result["data"]
        assert "ssl_certificates" in result["data"]
        assert "integration_id" in result
        assert action.http_request.call_count == 4

    @pytest.mark.asyncio
    async def test_success_no_ssl_certs(self, action):
        """When SSL endpoint returns empty results, key is omitted."""
        enrichment_resp = _mock_response({"queryValue": "1.2.3.4"})
        passive_resp = _mock_response({"results": []})
        classification_resp = _mock_response({"classification": ""})
        ssl_resp = _mock_response({"results": []})

        action.http_request = AsyncMock(
            side_effect=[enrichment_resp, passive_resp, classification_resp, ssl_resp]
        )

        result = await action.execute(ip="1.2.3.4")

        assert result["status"] == "success"
        assert "ssl_certificates" not in result["data"]

    @pytest.mark.asyncio
    async def test_missing_ip(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ip" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_ip(self, action):
        result = await action.execute(ip="not-an-ip")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_ipv6(self, action):
        enrichment_resp = _mock_response({"queryValue": "2001:db8::1"})
        passive_resp = _mock_response({"results": []})
        classification_resp = _mock_response({"classification": ""})
        ssl_resp = _mock_response({"results": []})

        action.http_request = AsyncMock(
            side_effect=[enrichment_resp, passive_resp, classification_resp, ssl_resp]
        )

        result = await action.execute(ip="2001:db8::1")
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(LookupIpAction, credentials={})
        result = await action.execute(ip="8.8.8.8")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_invalid_date(self, action):
        result = await action.execute(ip="8.8.8.8", **{"from": "not-a-date"})
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(ip="198.51.100.1")
        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["ip"] == "198.51.100.1"

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))
        result = await action.execute(ip="8.8.8.8")
        assert result["status"] == "error"


# ============================================================================
# WHOIS IP
# ============================================================================


class TestWhoisIpAction:
    @pytest.fixture
    def action(self):
        return _make_action(WhoisIpAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        whois_data = {
            "registrant": {
                "city": "San Francisco",
                "country": "US",
                "organization": "Acme Inc.",
            },
            "domain": "1.1.1.0",
            "contactEmail": "abuse@example.com",
        }
        action.http_request = AsyncMock(return_value=_mock_response(whois_data))

        result = await action.execute(ip="1.1.1.1")

        assert result["status"] == "success"
        assert result["data"]["registrant"]["city"] == "San Francisco"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_empty_response(self, action):
        """Empty API response returns success with message."""
        action.http_request = AsyncMock(return_value=_mock_response({}))

        result = await action.execute(ip="192.0.2.1")

        assert result["status"] == "success"
        assert "No registrant info found" in result["data"].get("message", "")

    @pytest.mark.asyncio
    async def test_missing_ip(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_ip(self, action):
        result = await action.execute(ip="invalid")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(WhoisIpAction, credentials={})
        result = await action.execute(ip="8.8.8.8")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(ip="198.51.100.1")
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))
        result = await action.execute(ip="8.8.8.8")
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
            "registrant": {
                "city": "San Francisco",
                "country": "us",
                "organization": "Acme, Inc.",
            },
            "domain": "example.com",
            "registrar": "TestMonitor Inc.",
        }
        action.http_request = AsyncMock(return_value=_mock_response(whois_data))

        result = await action.execute(domain="example.com")

        assert result["status"] == "success"
        assert result["data"]["domain"] == "example.com"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_empty_response(self, action):
        action.http_request = AsyncMock(return_value=_mock_response({}))
        result = await action.execute(domain="empty.com")
        assert result["status"] == "success"
        assert "No registrant info found" in result["data"].get("message", "")

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
    async def test_404_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(domain="nonexistent.xyz")
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))
        result = await action.execute(domain="example.com")
        assert result["status"] == "error"


# ============================================================================
# LOOKUP CERTIFICATE HASH
# ============================================================================


class TestLookupCertificateHashAction:
    @pytest.fixture
    def action(self):
        return _make_action(LookupCertificateHashAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        cert_resp = _mock_response(
            {"results": [{"sha1": "abc123", "issuerCommonName": "Let's Encrypt"}]}
        )
        hist_resp = _mock_response(
            {"results": [{"sha1": "abc123", "firstSeen": "2026-04-26"}]}
        )

        action.http_request = AsyncMock(side_effect=[cert_resp, hist_resp])

        result = await action.execute(query="abc123def456")

        assert result["status"] == "success"
        assert result["data"]["total_records"] == 1
        assert len(result["data"]["ssl_certificate"]) == 1
        assert len(result["data"]["ssl_certificate_history"]) == 1
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_query(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "query" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(LookupCertificateHashAction, credentials={})
        result = await action.execute(query="abc123")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(query="deadbeef")
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))
        result = await action.execute(query="abc123")
        assert result["status"] == "error"


# ============================================================================
# LOOKUP CERTIFICATE (SEARCH)
# ============================================================================


class TestLookupCertificateAction:
    @pytest.fixture
    def action(self):
        return _make_action(LookupCertificateAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_resp = _mock_response(
            {
                "results": [
                    {"sha1": "aaa111", "issuerCommonName": "DigiCert"},
                    {"sha1": "bbb222", "issuerCommonName": "DigiCert"},
                ]
            }
        )
        action.http_request = AsyncMock(return_value=api_resp)

        result = await action.execute(query="DigiCert", field="issuerCommonName")

        assert result["status"] == "success"
        assert result["data"]["total_records"] == 2
        assert len(result["data"]["ssl_certificates"]) == 2
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_query(self, action):
        result = await action.execute(field="issuerCommonName")
        assert result["status"] == "error"
        assert "query" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_field(self, action):
        result = await action.execute(query="test")
        assert result["status"] == "error"
        assert "field" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_field(self, action):
        result = await action.execute(query="test", field="invalidField")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(LookupCertificateAction, credentials={})
        result = await action.execute(query="test", field="issuerCommonName")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(query="nonexistent", field="issuerCommonName")
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))
        result = await action.execute(query="test", field="issuerCommonName")
        assert result["status"] == "error"


# ============================================================================
# GET HOST COMPONENTS
# ============================================================================


class TestGetHostComponentsAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetHostComponentsAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_resp = _mock_response(
            {
                "results": [
                    {"label": "CloudFlare", "category": "CDN", "version": "1.7.0"},
                    {"label": "nginx", "category": "Server", "version": "1.14.0"},
                ],
                "totalRecords": 2,
            }
        )
        action.http_request = AsyncMock(return_value=api_resp)

        result = await action.execute(query="example.com")

        assert result["status"] == "success"
        assert result["data"]["total_records"] == 2
        assert len(result["data"]["components"]) == 2
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_with_pagination(self, action):
        api_resp = _mock_response({"results": [], "totalRecords": 100})
        action.http_request = AsyncMock(return_value=api_resp)

        result = await action.execute(query="example.com", page=2)

        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["params"]["page"] == 2

    @pytest.mark.asyncio
    async def test_with_date_range(self, action):
        api_resp = _mock_response({"results": [], "totalRecords": 0})
        action.http_request = AsyncMock(return_value=api_resp)

        result = await action.execute(
            query="example.com", **{"from": "2026-04-26", "to": "2026-09-26"}
        )

        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["params"]["start"] == "2026-04-26"
        assert call_kwargs["params"]["end"] == "2026-09-26"

    @pytest.mark.asyncio
    async def test_missing_query(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert "query" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_page(self, action):
        result = await action.execute(query="example.com", page=-1)
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_page_string(self, action):
        result = await action.execute(query="example.com", page="abc")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_date(self, action):
        result = await action.execute(query="example.com", **{"from": "bad"})
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetHostComponentsAction, credentials={})
        result = await action.execute(query="example.com")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(query="nonexistent.xyz")
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))
        result = await action.execute(query="example.com")
        assert result["status"] == "error"


# ============================================================================
# GET HOST PAIRS
# ============================================================================


class TestGetHostPairsAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetHostPairsAction)

    @pytest.mark.asyncio
    async def test_success_children(self, action):
        api_resp = _mock_response(
            {
                "results": [
                    {
                        "parent": "example.com",
                        "child": "cdn.example.com",
                        "cause": "redirect",
                    },
                ],
                "totalRecords": 1,
            }
        )
        action.http_request = AsyncMock(return_value=api_resp)

        result = await action.execute(query="example.com", direction="children")

        assert result["status"] == "success"
        assert result["data"]["total_records"] == 1
        assert len(result["data"]["pairs"]) == 1
        assert result["data"]["direction"] == "children"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_success_parents(self, action):
        api_resp = _mock_response({"results": [], "totalRecords": 0})
        action.http_request = AsyncMock(return_value=api_resp)

        result = await action.execute(query="cdn.example.com", direction="parents")

        assert result["status"] == "success"
        assert result["data"]["direction"] == "parents"

    @pytest.mark.asyncio
    async def test_missing_query(self, action):
        result = await action.execute(direction="children")
        assert result["status"] == "error"
        assert "query" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_direction(self, action):
        result = await action.execute(query="example.com")
        assert result["status"] == "error"
        assert "direction" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_direction(self, action):
        result = await action.execute(query="example.com", direction="sideways")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_page(self, action):
        result = await action.execute(
            query="example.com", direction="children", page=-5
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_date(self, action):
        result = await action.execute(
            query="example.com", direction="children", **{"to": "nope"}
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetHostPairsAction, credentials={})
        result = await action.execute(query="example.com", direction="children")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(query="example.com", direction="children")
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))
        result = await action.execute(query="example.com", direction="children")
        assert result["status"] == "error"
