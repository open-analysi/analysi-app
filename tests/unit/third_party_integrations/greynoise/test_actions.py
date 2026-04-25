"""Unit tests for GreyNoise integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.greynoise.actions import (
    GetCveDetailsAction,
    GnqlQueryAction,
    HealthCheckAction,
    IpReputationAction,
    LookupIpAction,
    LookupIpsAction,
    LookupIpTimelineAction,
    _add_visualization,
    _enrich_trust_level,
    _validate_ip,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

DEFAULT_CREDENTIALS = {"api_key": "test-gn-key"}
DEFAULT_SETTINGS = {
    "base_url": "https://api.greynoise.io",
    "timeout": 30,
}


def _make_action(cls, credentials=None, settings=None):
    """Create an action instance for testing."""
    return cls(
        integration_id="greynoise",
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
# HELPER FUNCTIONS
# ============================================================================


class TestValidateIp:
    """Test the _validate_ip helper."""

    def test_valid_public_ip(self):
        valid, err = _validate_ip("8.8.8.8")
        assert valid is True
        assert err is None

    def test_private_ip_rejected(self):
        valid, err = _validate_ip("192.168.1.1")
        assert valid is False
        assert "private" in err.lower()

    def test_invalid_ip_rejected(self):
        valid, err = _validate_ip("not-an-ip")
        assert valid is False
        assert "Invalid" in err

    def test_ip_with_interface(self):
        valid, err = _validate_ip("8.8.8.8%eth0")
        assert valid is True

    def test_loopback_rejected(self):
        valid, err = _validate_ip("127.0.0.1")
        assert valid is False


class TestEnrichTrustLevel:
    """Test the _enrich_trust_level helper."""

    def test_adds_readable_trust_level(self):
        data = {"business_service_intelligence": {"trust_level": "1"}}
        _enrich_trust_level(data)
        assert data["trust_level"] == "1 - Reasonably Ignore"

    def test_unknown_trust_level_passthrough(self):
        data = {"business_service_intelligence": {"trust_level": "99"}}
        _enrich_trust_level(data)
        assert data["trust_level"] == "99"

    def test_no_bsi_no_error(self):
        data = {}
        _enrich_trust_level(data)
        assert "trust_level" not in data


class TestAddVisualization:
    """Test the _add_visualization helper."""

    def test_adds_viz_url(self):
        data = {"ip": "1.2.3.4"}
        _add_visualization(data)
        assert data["visualization"] == "https://viz.greynoise.io/ip/1.2.3.4"

    def test_no_ip_no_viz(self):
        data = {}
        _add_visualization(data)
        assert "visualization" not in data


# ============================================================================
# HEALTH CHECK
# ============================================================================


class TestHealthCheckAction:
    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        ping_resp = _mock_response({"message": "pong"})
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


# ============================================================================
# LOOKUP IP
# ============================================================================


class TestLookupIpAction:
    @pytest.fixture
    def action(self):
        return _make_action(LookupIpAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_data = [
            {
                "ip": "8.8.8.8",
                "business_service_intelligence": {"found": True, "trust_level": "1"},
                "internet_scanner_intelligence": {
                    "found": False,
                    "classification": "benign",
                },
            }
        ]
        action.http_request = AsyncMock(return_value=_mock_response(api_data))

        result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "success"
        assert isinstance(result["data"], list)
        assert result["data"][0]["ip"] == "8.8.8.8"
        assert result["data"][0]["trust_level"] == "1 - Reasonably Ignore"
        assert "visualization" in result["data"][0]
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_ip(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ip" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(LookupIpAction, credentials={})
        result = await action.execute(ip="8.8.8.8")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_private_ip_rejected(self, action):
        result = await action.execute(ip="10.0.0.1")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "private" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_invalid_ip_rejected(self, action):
        result = await action.execute(ip="not-an-ip")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404, "Not Found"))
        result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["ip"] == "8.8.8.8"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Internal Server Error")
        )
        result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "error"


# ============================================================================
# LOOKUP IPS
# ============================================================================


class TestLookupIpsAction:
    @pytest.fixture
    def action(self):
        return _make_action(LookupIpsAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_data = [
            {
                "ip": "8.8.8.8",
                "business_service_intelligence": {"found": True, "trust_level": "1"},
                "internet_scanner_intelligence": {"found": False},
            },
            {
                "ip": "1.1.1.1",
                "business_service_intelligence": {"found": True, "trust_level": "2"},
                "internet_scanner_intelligence": {"found": False},
            },
        ]
        action.http_request = AsyncMock(return_value=_mock_response(api_data))

        result = await action.execute(ips="8.8.8.8,1.1.1.1")

        assert result["status"] == "success"
        assert len(result["data"]) == 2
        assert result["data"][0]["trust_level"] == "1 - Reasonably Ignore"
        assert result["data"][1]["trust_level"] == "2 - Commonly Seen"

    @pytest.mark.asyncio
    async def test_missing_ips(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ips" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(LookupIpsAction, credentials={})
        result = await action.execute(ips="8.8.8.8")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_private_ip_in_list_rejected(self, action):
        result = await action.execute(ips="8.8.8.8,192.168.1.1")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_empty_after_split_rejected(self, action):
        result = await action.execute(ips="  ,  ,  ")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_sends_ip_list_to_api(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response([{"ip": "8.8.8.8"}, {"ip": "1.1.1.1"}])
        )

        await action.execute(ips="8.8.8.8, 1.1.1.1")

        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["json_data"]["ips"] == ["8.8.8.8", "1.1.1.1"]


# ============================================================================
# IP REPUTATION (Full Context)
# ============================================================================


class TestIpReputationAction:
    @pytest.fixture
    def action(self):
        return _make_action(IpReputationAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_data = {
            "ip": "8.8.8.8",
            "business_service_intelligence": {"found": True, "trust_level": "1"},
            "internet_scanner_intelligence": {
                "found": True,
                "classification": "benign",
                "metadata": {
                    "asn": "AS15169",
                    "organization": "Google LLC",
                    "source_country": "United States",
                },
                "tags": [{"name": "Google DNS", "category": "service"}],
            },
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_data))

        result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "success"
        assert result["data"]["ip"] == "8.8.8.8"
        assert result["data"]["unseen_rep"] is False
        assert result["data"]["trust_level"] == "1 - Reasonably Ignore"
        assert "visualization" in result["data"]
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_unseen_ip(self, action):
        api_data = {
            "ip": "4.4.4.4",
            "business_service_intelligence": {"found": False},
            "internet_scanner_intelligence": {"found": False},
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_data))

        result = await action.execute(ip="4.4.4.4")

        assert result["status"] == "success"
        assert result["data"]["unseen_rep"] is True

    @pytest.mark.asyncio
    async def test_missing_ip(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(IpReputationAction, credentials={})
        result = await action.execute(ip="8.8.8.8")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_private_ip_rejected(self, action):
        result = await action.execute(ip="10.0.0.1")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["ip"] == "8.8.8.8"
        assert result["data"]["unseen_rep"] is True

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))
        result = await action.execute(ip="8.8.8.8")
        assert result["status"] == "error"


# ============================================================================
# GNQL QUERY
# ============================================================================


class TestGnqlQueryAction:
    @pytest.fixture
    def action(self):
        return _make_action(GnqlQueryAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_resp = {
            "data": [
                {
                    "ip": "1.2.3.4",
                    "business_service_intelligence": {"trust_level": "1"},
                },
            ],
            "request_metadata": {"count": 1},
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_resp))

        result = await action.execute(query="classification:malicious", size=10)

        assert result["status"] == "success"
        assert len(result["data"]["data"]) == 1
        assert result["data"]["data"][0]["trust_level"] == "1 - Reasonably Ignore"
        assert "visualization" in result["data"]["data"][0]

    @pytest.mark.asyncio
    async def test_missing_query(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "query" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GnqlQueryAction, credentials={})
        result = await action.execute(query="classification:malicious")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_invalid_size(self, action):
        result = await action.execute(query="classification:malicious", size=-1)
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "size" in result["error"]

    @pytest.mark.asyncio
    async def test_non_integer_size(self, action):
        result = await action.execute(query="classification:malicious", size="abc")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_pagination_stops_on_no_scroll(self, action):
        """Verify pagination stops when no scroll token is returned."""
        api_resp = {
            "data": [{"ip": "1.2.3.4"}],
            "request_metadata": {"count": 1},
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_resp))

        result = await action.execute(query="test", size=2000)

        assert result["status"] == "success"
        # Only one call since no scroll token in response
        action.http_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_pagination_follows_scroll(self, action):
        """Verify pagination follows scroll tokens."""
        page1 = _mock_response(
            {
                "data": [{"ip": f"1.0.0.{i}"} for i in range(100)],
                "request_metadata": {"count": 200, "scroll": "token123"},
            }
        )
        page2 = _mock_response(
            {
                "data": [{"ip": f"2.0.0.{i}"} for i in range(100)],
                "request_metadata": {"count": 200},
            }
        )
        action.http_request = AsyncMock(side_effect=[page1, page2])

        result = await action.execute(query="test", size=200)

        assert result["status"] == "success"
        assert len(result["data"]["data"]) == 200
        assert action.http_request.call_count == 2

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))
        result = await action.execute(query="classification:malicious")
        assert result["status"] == "error"


# ============================================================================
# IP TIMELINE
# ============================================================================


class TestLookupIpTimelineAction:
    @pytest.fixture
    def action(self):
        return _make_action(LookupIpTimelineAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_data = {
            "ip": "8.8.8.8",
            "metadata": {
                "ip": "8.8.8.8",
                "field": "classification",
                "start": "2025-01-01T00:00:00Z",
                "end": "2025-01-31T00:00:00Z",
                "granularity": "1d",
            },
            "results": [
                {"timestamp": "2025-01-01T00:00:00Z", "label": "benign", "data": 1},
            ],
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_data))

        result = await action.execute(ip="8.8.8.8", field="classification", days=30)

        assert result["status"] == "success"
        assert result["data"]["ip"] == "8.8.8.8"
        assert len(result["data"]["results"]) == 1
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_ip(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ip" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(LookupIpTimelineAction, credentials={})
        result = await action.execute(ip="8.8.8.8")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_invalid_field(self, action):
        result = await action.execute(ip="8.8.8.8", field="invalid_field")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "Must be one of" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_days(self, action):
        result = await action.execute(ip="8.8.8.8", days=-5)
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_default_field(self, action):
        """Verify default field 'classification' is used."""
        action.http_request = AsyncMock(
            return_value=_mock_response({"ip": "8.8.8.8", "results": []})
        )

        result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "success"
        call_url = action.http_request.call_args.kwargs["url"]
        assert "/classification" in call_url

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["results"] == []

    @pytest.mark.asyncio
    async def test_custom_granularity(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response({"ip": "8.8.8.8", "results": []})
        )

        await action.execute(ip="8.8.8.8", granularity="1h")

        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["params"]["granularity"] == "1h"


# ============================================================================
# CVE DETAILS
# ============================================================================


class TestGetCveDetailsAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetCveDetailsAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_data = {
            "id": "CVE-2024-12345",
            "details": {
                "vendor": "Fortinet",
                "product": "FortiOS",
                "cve_cvss_score": 9.8,
                "vulnerability_name": "Auth Bypass",
                "vulnerability_description": "An auth bypass vulnerability...",
            },
            "timeline": {
                "cve_published_date": "2026-04-26T00:00:00Z",
            },
            "exploitation_stats": {
                "number_of_available_exploits": 5,
            },
            "exploitation_details": {
                "epss_score": 0.95,
                "attack_vector": "NETWORK",
                "exploit_found": True,
            },
            "exploitation_activity": {
                "activity_seen": True,
                "threat_ip_count_1d": 10,
            },
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_data))

        result = await action.execute(cve_id="CVE-2024-12345")

        assert result["status"] == "success"
        assert result["data"]["id"] == "CVE-2024-12345"
        assert result["data"]["details"]["cve_cvss_score"] == 9.8
        assert result["data"]["exploitation_details"]["epss_score"] == 0.95
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_cve_id(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "cve_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetCveDetailsAction, credentials={})
        result = await action.execute(cve_id="CVE-2024-12345")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(cve_id="CVE-9999-99999")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["id"] == "CVE-9999-99999"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))
        result = await action.execute(cve_id="CVE-2024-12345")
        assert result["status"] == "error"


# ============================================================================
# AUTH HEADER INJECTION
# ============================================================================


class TestAuthHeaders:
    """Verify get_http_headers injects the key header."""

    def test_headers_with_api_key(self):
        action = _make_action(HealthCheckAction)
        headers = action.get_http_headers()
        assert headers == {"key": "test-gn-key"}

    def test_headers_without_api_key(self):
        action = _make_action(HealthCheckAction, credentials={})
        headers = action.get_http_headers()
        assert headers == {}

    def test_base_url_from_settings(self):
        action = _make_action(HealthCheckAction)
        assert action.base_url == "https://api.greynoise.io"

    def test_base_url_custom(self):
        action = _make_action(
            HealthCheckAction,
            settings={"base_url": "https://custom.greynoise.example/"},
        )
        assert action.base_url == "https://custom.greynoise.example"

    def test_timeout_default(self):
        action = _make_action(HealthCheckAction, settings={})
        assert action.get_timeout() == 30

    def test_timeout_custom(self):
        action = _make_action(HealthCheckAction, settings={"timeout": 60})
        assert action.get_timeout() == 60
