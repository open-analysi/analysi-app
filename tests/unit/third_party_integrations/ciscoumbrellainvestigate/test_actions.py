"""Unit tests for Cisco Umbrella Investigate integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.ciscoumbrellainvestigate.actions import (
    DnsHistoryAction,
    DomainSecurityInfoAction,
    DomainWhoisAction,
    HealthCheckAction,
    LookupDomainAction,
    LookupIpAction,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def credentials():
    """Sample Cisco Umbrella Investigate credentials."""
    return {"access_token": "test-investigate-token"}


@pytest.fixture
def settings():
    """Sample Cisco Umbrella Investigate settings."""
    return {"timeout": 30}


@pytest.fixture
def health_check_action(credentials, settings):
    """Create HealthCheckAction instance."""
    return HealthCheckAction(
        "ciscoumbrellainvestigate", "health_check", settings, credentials
    )


@pytest.fixture
def lookup_domain_action(credentials, settings):
    """Create LookupDomainAction instance."""
    return LookupDomainAction(
        "ciscoumbrellainvestigate", "lookup_domain", settings, credentials
    )


@pytest.fixture
def lookup_ip_action(credentials, settings):
    """Create LookupIpAction instance."""
    return LookupIpAction(
        "ciscoumbrellainvestigate", "lookup_ip", settings, credentials
    )


@pytest.fixture
def domain_whois_action(credentials, settings):
    """Create DomainWhoisAction instance."""
    return DomainWhoisAction(
        "ciscoumbrellainvestigate", "domain_whois", settings, credentials
    )


@pytest.fixture
def domain_security_info_action(credentials, settings):
    """Create DomainSecurityInfoAction instance."""
    return DomainSecurityInfoAction(
        "ciscoumbrellainvestigate", "domain_security_info", settings, credentials
    )


@pytest.fixture
def dns_history_action(credentials, settings):
    """Create DnsHistoryAction instance."""
    return DnsHistoryAction(
        "ciscoumbrellainvestigate", "dns_history", settings, credentials
    )


def _mock_response(json_data=None, status_code=200, text=None):
    """Helper to create a mock httpx.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data or {}
    mock.text = text or str(json_data or {})
    mock.headers = {"Content-Type": "application/json"}
    return mock


def _mock_http_error(status_code=500, message="Server Error"):
    """Helper to create an HTTPStatusError."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.text = message
    mock_response.headers = {}
    mock_response.request = MagicMock()
    return httpx.HTTPStatusError(
        f"{status_code} {message}",
        request=mock_response.request,
        response=mock_response,
    )


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================


class TestHealthCheck:
    """Tests for HealthCheckAction."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, health_check_action):
        """Test successful health check."""
        mock_resp = _mock_response(
            {
                "phantomcyber.com": {
                    "status": 1,
                    "content_categories": [],
                    "security_categories": [],
                }
            }
        )
        health_check_action.http_request = AsyncMock(return_value=mock_resp)

        result = await health_check_action.execute()

        assert result["status"] == "success"
        assert result["integration_id"] == "ciscoumbrellainvestigate"
        assert result["action_id"] == "health_check"
        assert result["data"]["healthy"] is True
        health_check_action.http_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_sends_bearer_token(self, health_check_action):
        """Test that Bearer token is sent via get_http_headers."""
        headers = health_check_action.get_http_headers()
        assert headers["Authorization"] == "Bearer test-investigate-token"

    @pytest.mark.asyncio
    async def test_health_check_missing_credentials(self, settings):
        """Test health check with missing access token."""
        action = HealthCheckAction(
            "ciscoumbrellainvestigate", "health_check", settings, {}
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "access_token" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_health_check_http_error(self, health_check_action):
        """Test health check with HTTP error response."""
        health_check_action.http_request = AsyncMock(
            side_effect=_mock_http_error(401, "Unauthorized")
        )

        result = await health_check_action.execute()

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self, health_check_action):
        """Test health check with connection failure."""
        health_check_action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await health_check_action.execute()

        assert result["status"] == "error"
        assert "ConnectError" in result["error_type"]


# ============================================================================
# LOOKUP DOMAIN TESTS
# ============================================================================


class TestLookupDomain:
    """Tests for LookupDomainAction."""

    @pytest.mark.asyncio
    async def test_lookup_domain_success(self, lookup_domain_action):
        """Test successful domain lookup with all sub-calls succeeding."""
        call_count = 0

        async def mock_http_request(**kwargs):
            nonlocal call_count
            call_count += 1
            url = kwargs.get("url", "")

            if "/domains/categorization/" in url:
                return _mock_response(
                    {
                        "testdomain.com": {
                            "status": 1,
                            "content_categories": ["Search Engines"],
                            "security_categories": [],
                        }
                    }
                )
            if "/recommendations/name/" in url:
                return _mock_response({"pfs2": [["related.com", 0.5]]})
            if "/links/name/" in url:
                return _mock_response({"tb1": [["linked.com", 100]]})
            if "/security/name/" in url:
                return _mock_response(
                    {
                        "dga_score": 0,
                        "perplexity": 0.18,
                        "entropy": 1.92,
                        "pagerank": 60.33,
                    }
                )
            if "/timeline/" in url:
                return _mock_response(
                    [
                        {
                            "categories": ["Malware"],
                            "attacks": ["Rig"],
                            "timestamp": 1428593707849,
                        }
                    ]
                )
            if "/domains/risk-score/" in url:
                return _mock_response(
                    {
                        "risk_score": 6,
                        "indicators": [
                            {"indicator": "Geo Popularity Score", "score": -3.61}
                        ],
                    }
                )
            return _mock_response({})

        lookup_domain_action.http_request = mock_http_request

        result = await lookup_domain_action.execute(domain="testdomain.com")

        assert result["status"] == "success"
        assert result["integration_id"] == "ciscoumbrellainvestigate"
        assert result["data"]["status_desc"] == "NON MALICIOUS"
        assert result["data"]["category"] == "Search Engines"
        assert result["data"]["summary"]["domain_status"] == "NON MALICIOUS"
        assert result["data"]["summary"]["total_co_occurances"] == 1
        assert result["data"]["summary"]["total_relative_links"] == 1
        assert result["data"]["summary"]["total_tag_info"] == 1
        assert result["data"]["summary"]["risk_score"] == 6
        assert result["data"]["risk_score"] == 6
        assert len(result["data"]["indicators"]) == 1
        assert call_count == 6

    @pytest.mark.asyncio
    async def test_lookup_domain_malicious(self, lookup_domain_action):
        """Test domain lookup for a malicious domain."""

        async def mock_http_request(**kwargs):
            url = kwargs.get("url", "")
            if "/domains/categorization/" in url:
                return _mock_response(
                    {
                        "evil.com": {
                            "status": -1,
                            "content_categories": [],
                            "security_categories": ["Malware"],
                        }
                    }
                )
            return _mock_response({})

        lookup_domain_action.http_request = mock_http_request

        result = await lookup_domain_action.execute(domain="evil.com")

        assert result["status"] == "success"
        assert result["data"]["status_desc"] == "MALICIOUS"
        assert result["data"]["category"] == "Malware"

    @pytest.mark.asyncio
    async def test_lookup_domain_missing_domain(self, lookup_domain_action):
        """Test lookup domain with missing domain parameter."""
        result = await lookup_domain_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "domain" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_lookup_domain_missing_credentials(self, settings):
        """Test lookup domain with missing access token."""
        action = LookupDomainAction(
            "ciscoumbrellainvestigate", "lookup_domain", settings, {}
        )

        result = await action.execute(domain="test.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_lookup_domain_404_returns_not_found(self, lookup_domain_action):
        """Test 404 on primary category call returns success with not_found."""
        lookup_domain_action.http_request = AsyncMock(
            side_effect=_mock_http_error(404, "Not Found")
        )

        result = await lookup_domain_action.execute(domain="nonexistent.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["domain"] == "nonexistent.com"

    @pytest.mark.asyncio
    async def test_lookup_domain_http_error(self, lookup_domain_action):
        """Test lookup domain with non-404 HTTP error."""
        lookup_domain_action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Internal Server Error")
        )

        result = await lookup_domain_action.execute(domain="test.com")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_lookup_domain_partial_failure_continues(self, lookup_domain_action):
        """Test that failure in secondary sub-calls does not break the action."""
        call_count = 0

        async def mock_http_request(**kwargs):
            nonlocal call_count
            call_count += 1
            url = kwargs.get("url", "")

            if "/domains/categorization/" in url:
                return _mock_response(
                    {
                        "testdomain.com": {
                            "status": 1,
                            "content_categories": [],
                            "security_categories": [],
                        }
                    }
                )
            # All other sub-calls fail with 500
            raise _mock_http_error(500, "Internal Server Error")

        lookup_domain_action.http_request = mock_http_request

        result = await lookup_domain_action.execute(domain="testdomain.com")

        # Primary call succeeded, so result should be success
        assert result["status"] == "success"
        assert result["data"]["status_desc"] == "NON MALICIOUS"
        # Secondary calls failed gracefully
        assert result["data"]["summary"]["total_co_occurances"] == 0
        assert result["data"]["summary"]["total_relative_links"] == 0
        assert result["data"]["summary"]["total_tag_info"] == 0


# ============================================================================
# LOOKUP IP TESTS
# ============================================================================


class TestLookupIp:
    """Tests for LookupIpAction."""

    @pytest.mark.asyncio
    async def test_lookup_ip_with_domains(self, lookup_ip_action):
        """Test IP lookup that returns associated domains (malicious)."""
        mock_resp = _mock_response(
            [
                {"id": 84626522, "name": "evil-domain.net"},
                {"id": 84626523, "name": "bad-site.com"},
            ]
        )
        lookup_ip_action.http_request = AsyncMock(return_value=mock_resp)

        result = await lookup_ip_action.execute(ip="22.22.22.22")

        assert result["status"] == "success"
        assert result["integration_id"] == "ciscoumbrellainvestigate"
        assert result["data"]["ip"] == "22.22.22.22"
        assert result["data"]["ip_status"] == "MALICIOUS"
        assert result["data"]["total_blocked_domains"] == 2
        assert len(result["data"]["domains"]) == 2

    @pytest.mark.asyncio
    async def test_lookup_ip_no_domains(self, lookup_ip_action):
        """Test IP lookup with no associated domains (non-malicious)."""
        mock_resp = _mock_response([])
        lookup_ip_action.http_request = AsyncMock(return_value=mock_resp)

        result = await lookup_ip_action.execute(ip="8.8.8.8")

        assert result["status"] == "success"
        assert result["data"]["ip_status"] == "NON MALICIOUS"
        assert result["data"]["total_blocked_domains"] == 0

    @pytest.mark.asyncio
    async def test_lookup_ip_204_no_data(self, lookup_ip_action):
        """Test IP lookup with 204 No Content (no data)."""
        mock_resp = _mock_response(status_code=204)
        lookup_ip_action.http_request = AsyncMock(return_value=mock_resp)

        result = await lookup_ip_action.execute(ip="10.0.0.1")

        assert result["status"] == "success"
        assert result["data"]["ip_status"] == "NO STATUS"
        assert result["data"]["total_blocked_domains"] == 0

    @pytest.mark.asyncio
    async def test_lookup_ip_missing_ip(self, lookup_ip_action):
        """Test lookup IP with missing ip parameter."""
        result = await lookup_ip_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ip" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_lookup_ip_missing_credentials(self, settings):
        """Test lookup IP with missing access token."""
        action = LookupIpAction("ciscoumbrellainvestigate", "lookup_ip", settings, {})

        result = await action.execute(ip="1.2.3.4")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_lookup_ip_404_returns_not_found(self, lookup_ip_action):
        """Test 404 returns success with not_found."""
        lookup_ip_action.http_request = AsyncMock(
            side_effect=_mock_http_error(404, "Not Found")
        )

        result = await lookup_ip_action.execute(ip="99.99.99.99")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["ip"] == "99.99.99.99"

    @pytest.mark.asyncio
    async def test_lookup_ip_http_error(self, lookup_ip_action):
        """Test lookup IP with server error."""
        lookup_ip_action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Internal Server Error")
        )

        result = await lookup_ip_action.execute(ip="1.2.3.4")

        assert result["status"] == "error"


# ============================================================================
# DOMAIN WHOIS TESTS
# ============================================================================


class TestDomainWhois:
    """Tests for DomainWhoisAction."""

    @pytest.mark.asyncio
    async def test_whois_success(self, domain_whois_action):
        """Test successful WHOIS lookup."""
        whois_data = {
            "domainName": "google.com",
            "registrantOrganization": "Google LLC",
            "registrantCity": "Mountain View",
            "registrantCountry": "UNITED STATES",
            "registrantEmail": "dns-admin@google.com",
            "registrarName": "MarkMonitor, Inc.",
            "created": "1997-09-15",
            "expires": "2028-09-14",
            "nameServers": ["ns1.google.com", "ns2.google.com"],
        }
        mock_resp = _mock_response(whois_data)
        domain_whois_action.http_request = AsyncMock(return_value=mock_resp)

        result = await domain_whois_action.execute(domain="google.com")

        assert result["status"] == "success"
        assert result["integration_id"] == "ciscoumbrellainvestigate"
        assert result["data"]["whois"]["registrantOrganization"] == "Google LLC"
        assert result["data"]["summary"]["organization"] == "Google LLC"
        assert result["data"]["summary"]["city"] == "Mountain View"
        assert result["data"]["summary"]["country"] == "UNITED STATES"

    @pytest.mark.asyncio
    async def test_whois_url_cleaning(self, domain_whois_action):
        """Test that URLs are cleaned to extract the domain."""
        mock_resp = _mock_response({"domainName": "example.com"})
        domain_whois_action.http_request = AsyncMock(return_value=mock_resp)

        await domain_whois_action.execute(domain="https://example.com/path/page")

        call_kwargs = domain_whois_action.http_request.call_args.kwargs
        # URL should contain just 'example.com', not the full URL
        assert "example.com" in call_kwargs["url"]
        assert "/path/page" not in call_kwargs["url"]

    @pytest.mark.asyncio
    async def test_whois_missing_domain(self, domain_whois_action):
        """Test WHOIS with missing domain parameter."""
        result = await domain_whois_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "domain" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_whois_missing_credentials(self, settings):
        """Test WHOIS with missing access token."""
        action = DomainWhoisAction(
            "ciscoumbrellainvestigate", "domain_whois", settings, {}
        )

        result = await action.execute(domain="test.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_whois_404_returns_not_found(self, domain_whois_action):
        """Test 404 returns success with not_found."""
        domain_whois_action.http_request = AsyncMock(
            side_effect=_mock_http_error(404, "Not Found")
        )

        result = await domain_whois_action.execute(domain="nonexistent.xyz")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["domain"] == "nonexistent.xyz"
        assert result["data"]["whois"] == {}

    @pytest.mark.asyncio
    async def test_whois_http_error(self, domain_whois_action):
        """Test WHOIS with server error."""
        domain_whois_action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Internal Server Error")
        )

        result = await domain_whois_action.execute(domain="test.com")

        assert result["status"] == "error"


# ============================================================================
# DOMAIN SECURITY INFO TESTS
# ============================================================================


class TestDomainSecurityInfo:
    """Tests for DomainSecurityInfoAction."""

    @pytest.mark.asyncio
    async def test_security_info_success(self, domain_security_info_action):
        """Test successful security info lookup."""
        security_data = {
            "dga_score": -15.55,
            "perplexity": 1.12,
            "entropy": 2.75,
            "pagerank": 0,
            "asn_score": -0.03,
            "prefix_score": -0.11,
            "rip_score": -3.05,
            "popularity": 100,
            "fastflux": False,
            "geodiversity": [],
            "found": True,
        }
        mock_resp = _mock_response(security_data)
        domain_security_info_action.http_request = AsyncMock(return_value=mock_resp)

        result = await domain_security_info_action.execute(domain="suspicious.com")

        assert result["status"] == "success"
        assert result["integration_id"] == "ciscoumbrellainvestigate"
        assert result["data"]["domain"] == "suspicious.com"
        assert result["data"]["security_info"]["dga_score"] == -15.55
        assert result["data"]["security_info"]["found"] is True

    @pytest.mark.asyncio
    async def test_security_info_204_no_data(self, domain_security_info_action):
        """Test security info with 204 No Content."""
        mock_resp = _mock_response(status_code=204)
        domain_security_info_action.http_request = AsyncMock(return_value=mock_resp)

        result = await domain_security_info_action.execute(domain="new-domain.com")

        assert result["status"] == "success"
        assert result["data"]["security_info"] == {}
        assert "No security data" in result["data"]["message"]

    @pytest.mark.asyncio
    async def test_security_info_missing_domain(self, domain_security_info_action):
        """Test security info with missing domain parameter."""
        result = await domain_security_info_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_security_info_missing_credentials(self, settings):
        """Test security info with missing access token."""
        action = DomainSecurityInfoAction(
            "ciscoumbrellainvestigate", "domain_security_info", settings, {}
        )

        result = await action.execute(domain="test.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_security_info_404_returns_not_found(
        self, domain_security_info_action
    ):
        """Test 404 returns success with not_found."""
        domain_security_info_action.http_request = AsyncMock(
            side_effect=_mock_http_error(404, "Not Found")
        )

        result = await domain_security_info_action.execute(domain="nonexistent.com")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_security_info_http_error(self, domain_security_info_action):
        """Test security info with server error."""
        domain_security_info_action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Internal Server Error")
        )

        result = await domain_security_info_action.execute(domain="test.com")

        assert result["status"] == "error"


# ============================================================================
# DNS HISTORY TESTS
# ============================================================================


class TestDnsHistory:
    """Tests for DnsHistoryAction."""

    @pytest.mark.asyncio
    async def test_dns_history_success(self, dns_history_action):
        """Test successful DNS history lookup."""
        timeline_data = [
            {
                "categories": ["Malware"],
                "attacks": ["Rig"],
                "threatTypes": ["Exploit Kit"],
                "timestamp": 1428593707849,
            },
            {
                "categories": ["Phishing"],
                "attacks": [],
                "threatTypes": ["Phishing"],
                "timestamp": 1496547887014,
            },
        ]
        mock_resp = _mock_response(timeline_data)
        dns_history_action.http_request = AsyncMock(return_value=mock_resp)

        result = await dns_history_action.execute(domain="bad-history.com")

        assert result["status"] == "success"
        assert result["integration_id"] == "ciscoumbrellainvestigate"
        assert result["data"]["domain"] == "bad-history.com"
        assert result["data"]["total_entries"] == 2
        assert len(result["data"]["timeline"]) == 2
        assert result["data"]["timeline"][0]["categories"] == ["Malware"]

    @pytest.mark.asyncio
    async def test_dns_history_empty(self, dns_history_action):
        """Test DNS history with no entries."""
        mock_resp = _mock_response([])
        dns_history_action.http_request = AsyncMock(return_value=mock_resp)

        result = await dns_history_action.execute(domain="clean-domain.com")

        assert result["status"] == "success"
        assert result["data"]["total_entries"] == 0
        assert result["data"]["timeline"] == []

    @pytest.mark.asyncio
    async def test_dns_history_missing_domain(self, dns_history_action):
        """Test DNS history with missing domain parameter."""
        result = await dns_history_action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_dns_history_missing_credentials(self, settings):
        """Test DNS history with missing access token."""
        action = DnsHistoryAction(
            "ciscoumbrellainvestigate", "dns_history", settings, {}
        )

        result = await action.execute(domain="test.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_dns_history_404_returns_not_found(self, dns_history_action):
        """Test 404 returns success with not_found."""
        dns_history_action.http_request = AsyncMock(
            side_effect=_mock_http_error(404, "Not Found")
        )

        result = await dns_history_action.execute(domain="nonexistent.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["timeline"] == []

    @pytest.mark.asyncio
    async def test_dns_history_http_error(self, dns_history_action):
        """Test DNS history with server error."""
        dns_history_action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Internal Server Error")
        )

        result = await dns_history_action.execute(domain="test.com")

        assert result["status"] == "error"
