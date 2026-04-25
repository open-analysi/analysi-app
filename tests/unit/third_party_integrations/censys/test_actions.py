"""Unit tests for Censys integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.censys.actions import (
    HealthCheckAction,
    LookupCertificateAction,
    LookupIpAction,
    QueryCertificateAction,
    QueryIpAction,
    _is_valid_ip,
)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

DEFAULT_CREDENTIALS = {"api_id": "test-api-id", "secret": "test-secret"}
DEFAULT_SETTINGS = {
    "base_url": "https://search.censys.io",
    "timeout": 30,
}


def _make_action(cls, credentials=None, settings=None):
    """Create an action instance for testing."""
    return cls(
        integration_id="censys",
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
# HELPER: _is_valid_ip
# ============================================================================


class TestIsValidIp:
    def test_valid_ipv4(self):
        assert _is_valid_ip("1.2.3.4") is True

    def test_valid_ipv6(self):
        assert _is_valid_ip("2001:db8::1") is True

    def test_invalid(self):
        assert _is_valid_ip("not-an-ip") is False

    def test_empty_string(self):
        assert _is_valid_ip("") is False


# ============================================================================
# BASE CLASS
# ============================================================================


class TestCensysActionBase:
    def test_base_url_strips_trailing_slash(self):
        action = _make_action(
            HealthCheckAction,
            settings={**DEFAULT_SETTINGS, "base_url": "https://search.censys.io/"},
        )
        assert action.base_url == "https://search.censys.io"

    def test_base_url_no_trailing_slash(self):
        action = _make_action(HealthCheckAction)
        assert action.base_url == "https://search.censys.io"


# ============================================================================
# HEALTH CHECK
# ============================================================================


class TestHealthCheckAction:
    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        mock_resp = _mock_response({"email": "user@example.com", "login": "user"})
        action.http_request = AsyncMock(return_value=mock_resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert "integration_id" in result
        action.http_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(HealthCheckAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "api_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_partial_credentials(self):
        action = _make_action(HealthCheckAction, credentials={"api_id": "id-only"})
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
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_connection_error(self, action):
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        result = await action.execute()

        assert result["status"] == "error"


# ============================================================================
# LOOKUP IP
# ============================================================================


class TestLookupIpAction:
    @pytest.fixture
    def action(self):
        return _make_action(LookupIpAction)

    @pytest.mark.asyncio
    async def test_success_with_services(self, action):
        api_response = {
            "code": 200,
            "result": {
                "ip": "8.8.8.8",
                "services": [
                    {"port": 53, "service_name": "DNS", "transport_protocol": "UDP"},
                    {"port": 443, "service_name": "HTTPS", "transport_protocol": "TCP"},
                ],
                "autonomous_system": {
                    "asn": 15169,
                    "name": "GOOGLE",
                    "country_code": "US",
                },
                "location": {
                    "country": "United States",
                    "country_code": "US",
                    "continent": "North America",
                },
            },
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_response))

        result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "success"
        assert result["data"]["result"]["ip"] == "8.8.8.8"
        assert len(result["data"]["result"]["services"]) == 2
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_success_no_services(self, action):
        api_response = {
            "code": 200,
            "result": {"ip": "192.0.2.1", "services": []},
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_response))

        result = await action.execute(ip="192.0.2.1")

        assert result["status"] == "success"
        assert result["message"] is not None

    @pytest.mark.asyncio
    async def test_missing_ip(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ip" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_ip(self, action):
        result = await action.execute(ip="not-an-ip-address")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_ipv6_address(self, action):
        api_response = {
            "code": 200,
            "result": {
                "ip": "2001:4860:4860::8888",
                "services": [{"port": 53, "service_name": "DNS"}],
            },
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_response))

        result = await action.execute(ip="2001:4860:4860::8888")

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(LookupIpAction, credentials={})
        result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))

        result = await action.execute(ip="198.51.100.1")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["ip"] == "198.51.100.1"

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Server Error")
        )

        result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_auth_passes_basic_auth(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response(
                {"result": {"ip": "1.1.1.1", "services": [{"port": 80}]}}
            )
        )

        await action.execute(ip="1.1.1.1")

        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["auth"] == ("test-api-id", "test-secret")


# ============================================================================
# LOOKUP CERTIFICATE
# ============================================================================


class TestLookupCertificateAction:
    @pytest.fixture
    def action(self):
        return _make_action(LookupCertificateAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_response = {
            "fingerprint_sha256": "abcd1234" * 8,
            "parsed": {
                "issuer_dn": "C=US, O=DigiCert",
                "subject_dn": "CN=example.com",
                "validity": {"start": "2026-04-26", "end": "2026-12-31"},
            },
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_response))

        result = await action.execute(sha256="abcd1234" * 8)

        assert result["status"] == "success"
        assert "parsed" in result["data"]
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_sha256(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "sha256" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(LookupCertificateAction, credentials={})
        result = await action.execute(sha256="abc123")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        sha = "deadbeef" * 8

        result = await action.execute(sha256=sha)

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["sha256"] == sha

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))

        result = await action.execute(sha256="abc")

        assert result["status"] == "error"


# ============================================================================
# QUERY IP
# ============================================================================


class TestQueryIpAction:
    @pytest.fixture
    def action(self):
        return _make_action(QueryIpAction)

    @pytest.mark.asyncio
    async def test_success_single_page(self, action):
        api_response = {
            "result": {
                "hits": [
                    {"ip": "1.2.3.4", "services": [{"port": 22}]},
                    {"ip": "5.6.7.8", "services": [{"port": 80}]},
                ],
                "total": 2,
                "links": {"next": ""},
            },
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_response))

        result = await action.execute(query="services.port=22")

        assert result["status"] == "success"
        assert result["data"]["total_records_fetched"] == 2
        assert result["data"]["total_available_records"] == 2
        assert len(result["data"]["hits"]) == 2
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_pagination(self, action):
        page1 = {
            "result": {
                "hits": [{"ip": f"10.0.0.{i}"} for i in range(3)],
                "total": 5,
                "links": {"next": "cursor-page-2"},
            },
        }
        page2 = {
            "result": {
                "hits": [{"ip": f"10.0.1.{i}"} for i in range(2)],
                "total": 5,
                "links": {"next": ""},
            },
        }
        action.http_request = AsyncMock(
            side_effect=[_mock_response(page1), _mock_response(page2)]
        )

        result = await action.execute(query="services.port=80", limit=10)

        assert result["status"] == "success"
        assert result["data"]["total_records_fetched"] == 5
        assert action.http_request.call_count == 2

    @pytest.mark.asyncio
    async def test_missing_query(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "query" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_limit_string(self, action):
        result = await action.execute(query="test", limit="abc")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_limit_zero(self, action):
        result = await action.execute(query="test", limit=0)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_limit_negative(self, action):
        result = await action.execute(query="test", limit=-5)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(QueryIpAction, credentials={})
        result = await action.execute(query="test")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))

        result = await action.execute(query="test")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_limit_caps_results(self, action):
        """When limit < results on first page, no second page is fetched."""
        page1 = {
            "result": {
                "hits": [{"ip": f"10.0.0.{i}"} for i in range(5)],
                "total": 100,
                "links": {"next": "cursor-page-2"},
            },
        }
        action.http_request = AsyncMock(return_value=_mock_response(page1))

        # Limit is 3, but first page returns 5 hits: pagination loop sees
        # data_left = 3 - 5 = -2, so no second request is made.
        result = await action.execute(query="test", limit=3)

        assert result["status"] == "success"
        assert action.http_request.call_count == 1


# ============================================================================
# QUERY CERTIFICATE
# ============================================================================


class TestQueryCertificateAction:
    @pytest.fixture
    def action(self):
        return _make_action(QueryCertificateAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_response = {
            "result": {
                "hits": [
                    {
                        "fingerprint_sha256": "aabb" * 16,
                        "parsed": {
                            "issuer_dn": "CN=Test CA",
                            "subject_dn": "CN=test.com",
                        },
                    },
                ],
                "total": 1,
                "links": {"next": ""},
            },
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_response))

        result = await action.execute(query="parsed.issuer.organization:DigiCert")

        assert result["status"] == "success"
        assert result["data"]["total_records_fetched"] == 1
        assert len(result["data"]["hits"]) == 1
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_pagination(self, action):
        page1 = {
            "result": {
                "hits": [{"fp": "a"}],
                "total": 3,
                "links": {"next": "cursor2"},
            },
        }
        page2 = {
            "result": {
                "hits": [{"fp": "b"}, {"fp": "c"}],
                "total": 3,
                "links": {"next": ""},
            },
        }
        action.http_request = AsyncMock(
            side_effect=[_mock_response(page1), _mock_response(page2)]
        )

        result = await action.execute(query="test", limit=10)

        assert result["status"] == "success"
        assert result["data"]["total_records_fetched"] == 3
        assert action.http_request.call_count == 2

    @pytest.mark.asyncio
    async def test_missing_query(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(QueryCertificateAction, credentials={})
        result = await action.execute(query="test")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))

        result = await action.execute(query="test")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_invalid_limit(self, action):
        result = await action.execute(query="test", limit="not-a-number")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
