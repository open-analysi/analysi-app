"""Unit tests for Cisco Talos Intelligence integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.ciscotalosintelligence.actions import (
    DomainReputationAction,
    HealthCheckAction,
    IpReputationAction,
    UrlReputationAction,
    _parse_reputation_response,
    _validate_domain,
    _validate_ip,
    _validate_url,
)

# ============================================================================
# TAXONOMY TEST FIXTURE (reusable across reputation action tests)
# ============================================================================

MOCK_TAXONOMY = {
    "taxonomies": {
        "1": {
            "is_avail": True,
            "name": {"en-us": {"text": "Threat Levels"}},
            "entries": {
                "10": {
                    "name": {"en-us": {"text": "Favorable"}},
                    "description": {"en-us": {"text": "Low risk"}},
                }
            },
        },
        "2": {
            "is_avail": True,
            "name": {"en-us": {"text": "Threat Categories"}},
            "entries": {
                "20": {
                    "name": {"en-us": {"text": "Malware"}},
                    "description": {"en-us": {"text": "Known malware distribution"}},
                }
            },
        },
        "3": {
            "is_avail": True,
            "name": {"en-us": {"text": "Acceptable Use Policy Categories"}},
            "entries": {
                "30": {
                    "name": {"en-us": {"text": "Search Engines"}},
                    "description": {"en-us": {"text": "Web search engines"}},
                }
            },
        },
    }
}

MOCK_REPUTATION_RESPONSE = {
    "taxonomy_map_version": 1,
    "results": [
        {
            "results": [
                {
                    "context_tags": [
                        {"taxonomy_id": 1, "taxonomy_entry_id": 10},
                        {"taxonomy_id": 3, "taxonomy_entry_id": 30},
                    ]
                }
            ]
        }
    ],
}

MOCK_TAXONOMY_API_RESPONSE = {
    "version": 1,
    "catalogs": {"2": MOCK_TAXONOMY},
}


# ============================================================================
# VALIDATION HELPER TESTS
# ============================================================================


class TestValidateIp:
    """Test IP address validation helper."""

    def test_valid_ipv4(self):
        for ip in ["8.8.8.8", "192.168.1.1", "127.0.0.1", "10.0.0.1"]:
            is_valid, error = _validate_ip(ip)
            assert is_valid is True, f"Expected {ip} to be valid"
            assert error == ""

    def test_valid_ipv6(self):
        for ip in ["2001:4860:4860::8888", "::1", "fe80::1"]:
            is_valid, error = _validate_ip(ip)
            assert is_valid is True, f"Expected {ip} to be valid"
            assert error == ""

    def test_invalid_format(self):
        for ip in ["not.an.ip", "999.999.999.999", "192.168.1", "invalid"]:
            is_valid, error = _validate_ip(ip)
            assert is_valid is False, f"Expected {ip} to be invalid"
            assert "Invalid IP address format" in error

    def test_none_or_empty(self):
        for value in [None, "", "   "]:
            is_valid, error = _validate_ip(value)
            assert is_valid is False
            assert "IP address is required" in error


class TestValidateDomain:
    """Test domain validation helper."""

    def test_valid_domains(self):
        for domain in ["example.com", "sub.example.com", "cisco.com", "my-site.co.uk"]:
            is_valid, error = _validate_domain(domain)
            assert is_valid is True, f"Expected {domain} to be valid"
            assert error == ""

    def test_invalid_domains(self):
        for domain in ["-bad.com", "bad-.com", ".com", "a" * 64 + ".com"]:
            is_valid, error = _validate_domain(domain)
            assert is_valid is False, f"Expected {domain} to be invalid"
            assert "Invalid domain name format" in error

    def test_none_or_empty(self):
        for value in [None, "", "   "]:
            is_valid, error = _validate_domain(value)
            assert is_valid is False
            assert "Domain is required" in error


class TestValidateUrl:
    """Test URL validation helper."""

    def test_valid_urls(self):
        for url in [
            "https://example.com",
            "http://example.com/path",
            "https://sub.example.com/a?b=1",
        ]:
            is_valid, error = _validate_url(url)
            assert is_valid is True, f"Expected {url} to be valid"
            assert error == ""

    def test_invalid_urls(self):
        for url in ["example.com", "just-a-string", "/path/only"]:
            is_valid, error = _validate_url(url)
            assert is_valid is False, f"Expected {url} to be invalid"
            assert "Invalid URL format" in error

    def test_none_or_empty(self):
        for value in [None, "", "   "]:
            is_valid, error = _validate_url(value)
            assert is_valid is False
            assert "URL is required" in error


# ============================================================================
# RESPONSE PARSER TESTS
# ============================================================================


class TestParseReputationResponse:
    """Test reputation response parsing with taxonomy mapping."""

    def test_parses_threat_level(self):
        result = _parse_reputation_response(
            MOCK_REPUTATION_RESPONSE, MOCK_TAXONOMY, "8.8.8.8"
        )
        assert result["threat_level"] == "Favorable"

    def test_parses_aup_categories(self):
        result = _parse_reputation_response(
            MOCK_REPUTATION_RESPONSE, MOCK_TAXONOMY, "8.8.8.8"
        )
        assert "Search Engines" in result["aup_categories"]

    def test_includes_observable(self):
        result = _parse_reputation_response(
            MOCK_REPUTATION_RESPONSE, MOCK_TAXONOMY, "8.8.8.8"
        )
        assert result["observable"] == "8.8.8.8"

    def test_empty_results(self):
        empty_response = {"results": []}
        result = _parse_reputation_response(empty_response, MOCK_TAXONOMY, "8.8.8.8")
        assert result["threat_level"] == ""
        assert result["threat_categories"] == ""
        assert result["aup_categories"] == ""

    def test_skips_unavailable_taxonomies(self):
        taxonomy = {
            "taxonomies": {
                "1": {
                    "is_avail": False,
                    "name": {"en-us": {"text": "Threat Levels"}},
                    "entries": {
                        "10": {
                            "name": {"en-us": {"text": "Favorable"}},
                            "description": {"en-us": {"text": "Low risk"}},
                        }
                    },
                }
            }
        }
        result = _parse_reputation_response(
            MOCK_REPUTATION_RESPONSE, taxonomy, "8.8.8.8"
        )
        assert result["threat_level"] == ""

    def test_skips_unknown_taxonomy_ids(self):
        response = {
            "results": [
                {
                    "results": [
                        {
                            "context_tags": [
                                {"taxonomy_id": 999, "taxonomy_entry_id": 1},
                            ]
                        }
                    ]
                }
            ]
        }
        result = _parse_reputation_response(response, MOCK_TAXONOMY, "8.8.8.8")
        assert result["threat_level"] == ""

    def test_parses_threat_categories(self):
        response = {
            "results": [
                {
                    "results": [
                        {
                            "context_tags": [
                                {"taxonomy_id": 2, "taxonomy_entry_id": 20},
                            ]
                        }
                    ]
                }
            ]
        }
        result = _parse_reputation_response(response, MOCK_TAXONOMY, "8.8.8.8")
        assert "Malware" in result["threat_categories"]
        assert "Malware" in result["threat_category_details"]
        assert (
            result["threat_category_details"]["Malware"] == "Known malware distribution"
        )


# ============================================================================
# HEALTH CHECK ACTION TESTS
# ============================================================================


class TestHealthCheckAction:
    """Test Talos health check action."""

    @pytest.fixture
    def health_check_action(self):
        return HealthCheckAction(
            integration_id="cisco-talos",
            action_id="health_check",
            settings={"base_url": "https://soar-api.talos.cisco.com"},
            credentials={"certificate": "test-cert", "key": "test-key"},
        )

    @pytest.mark.asyncio
    async def test_health_check_success(self, health_check_action):
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}

        with patch.object(
            health_check_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await health_check_action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_health_check_uses_cisco_dot_com(self, health_check_action):
        """Verify health check queries cisco.com as a safe test target."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}

        with patch.object(
            health_check_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_request:
            await health_check_action.execute()

            call_args = mock_request.call_args
            payload = call_args[1].get("json_data", {})
            assert payload["urls"] == [{"raw_url": "cisco.com"}]
            assert payload["app_info"]["perf_testing"] is True

    @pytest.mark.asyncio
    async def test_health_check_missing_credentials(self):
        action = HealthCheckAction(
            integration_id="cisco-talos",
            action_id="health_check",
            settings={},
            credentials={},
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert "Missing required credentials" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_health_check_missing_key(self):
        action = HealthCheckAction(
            integration_id="cisco-talos",
            action_id="health_check",
            settings={},
            credentials={"certificate": "test-cert"},
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert "Missing required credentials" in result["error"]

    @pytest.mark.asyncio
    async def test_health_check_api_error(self, health_check_action):
        with patch.object(
            health_check_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Connection refused"),
        ):
            result = await health_check_action.execute()

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]


# ============================================================================
# IP REPUTATION ACTION TESTS
# ============================================================================


class TestIpReputationAction:
    """Test Talos IP reputation action."""

    @pytest.fixture
    def ip_action(self):
        return IpReputationAction(
            integration_id="cisco-talos",
            action_id="ip_reputation",
            settings={"base_url": "https://soar-api.talos.cisco.com"},
            credentials={"certificate": "test-cert", "key": "test-key"},
        )

    @pytest.mark.asyncio
    async def test_ip_reputation_success(self, ip_action):
        """Test successful IP reputation lookup with taxonomy parsing."""
        mock_taxonomy_response = MagicMock()
        mock_taxonomy_response.json.return_value = MOCK_TAXONOMY_API_RESPONSE

        mock_reputation_response = MagicMock()
        mock_reputation_response.json.return_value = MOCK_REPUTATION_RESPONSE

        with patch.object(
            ip_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=[mock_taxonomy_response, mock_reputation_response],
        ):
            result = await ip_action.execute(ip="72.163.4.185")

        assert result["status"] == "success"
        assert result["data"]["observable"] == "72.163.4.185"
        assert result["data"]["threat_level"] == "Favorable"
        assert "Search Engines" in result["data"]["aup_categories"]
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_ip_reputation_ipv6(self, ip_action):
        """Test IPv6 address is accepted."""
        mock_taxonomy_response = MagicMock()
        mock_taxonomy_response.json.return_value = MOCK_TAXONOMY_API_RESPONSE

        mock_reputation_response = MagicMock()
        mock_reputation_response.json.return_value = MOCK_REPUTATION_RESPONSE

        with patch.object(
            ip_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=[mock_taxonomy_response, mock_reputation_response],
        ):
            result = await ip_action.execute(ip="2001:4860:4860::8888")

        assert result["status"] == "success"
        assert result["data"]["observable"] == "2001:4860:4860::8888"

    @pytest.mark.asyncio
    async def test_ip_reputation_sends_correct_payload(self, ip_action):
        """Verify IP is formatted correctly in the request payload."""
        mock_taxonomy_response = MagicMock()
        mock_taxonomy_response.json.return_value = MOCK_TAXONOMY_API_RESPONSE

        mock_reputation_response = MagicMock()
        mock_reputation_response.json.return_value = MOCK_REPUTATION_RESPONSE

        with patch.object(
            ip_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=[mock_taxonomy_response, mock_reputation_response],
        ) as mock_request:
            await ip_action.execute(ip="8.8.8.8")

            # Second call is the reputation query
            reputation_call = mock_request.call_args_list[1]
            payload = reputation_call[1].get("json_data", {})
            # 8.8.8.8 as integer is 134744072
            assert payload["urls"]["endpoint"][0]["ipv4_addr"] == 134744072

    @pytest.mark.asyncio
    async def test_ip_reputation_missing_ip(self, ip_action):
        result = await ip_action.execute()
        assert result["status"] == "error"
        assert "IP address is required" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_ip_reputation_invalid_ip(self, ip_action):
        result = await ip_action.execute(ip="not-an-ip")
        assert result["status"] == "error"
        assert "Invalid IP address format" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_ip_reputation_missing_credentials(self):
        action = IpReputationAction(
            integration_id="cisco-talos",
            action_id="ip_reputation",
            settings={},
            credentials={},
        )
        result = await action.execute(ip="8.8.8.8")
        assert result["status"] == "error"
        assert "Missing required credentials" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_ip_reputation_404_returns_not_found(self, ip_action):
        """Test that 404 returns success with not_found=True."""
        mock_taxonomy_response = MagicMock()
        mock_taxonomy_response.json.return_value = MOCK_TAXONOMY_API_RESPONSE

        mock_404_response = MagicMock(spec=httpx.Response)
        mock_404_response.status_code = 404
        mock_404_response.request = MagicMock()

        http_error = httpx.HTTPStatusError(
            "Not Found", request=mock_404_response.request, response=mock_404_response
        )

        with patch.object(
            ip_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=[mock_taxonomy_response, http_error],
        ):
            result = await ip_action.execute(ip="8.8.8.8")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["observable"] == "8.8.8.8"

    @pytest.mark.asyncio
    async def test_ip_reputation_api_error(self, ip_action):
        """Test generic API error is handled."""
        with patch.object(
            ip_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Connection timeout"),
        ):
            result = await ip_action.execute(ip="8.8.8.8")

        assert result["status"] == "error"
        assert "Connection timeout" in result["error"]

    @pytest.mark.asyncio
    async def test_ip_reputation_summary_message(self, ip_action):
        """Test result includes summary message with threat level."""
        mock_taxonomy_response = MagicMock()
        mock_taxonomy_response.json.return_value = MOCK_TAXONOMY_API_RESPONSE

        mock_reputation_response = MagicMock()
        mock_reputation_response.json.return_value = MOCK_REPUTATION_RESPONSE

        with patch.object(
            ip_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=[mock_taxonomy_response, mock_reputation_response],
        ):
            result = await ip_action.execute(ip="72.163.4.185")

        assert "message" in result
        assert "Favorable" in result["message"]
        assert "72.163.4.185" in result["message"]


# ============================================================================
# DOMAIN REPUTATION ACTION TESTS
# ============================================================================


class TestDomainReputationAction:
    """Test Talos domain reputation action."""

    @pytest.fixture
    def domain_action(self):
        return DomainReputationAction(
            integration_id="cisco-talos",
            action_id="domain_reputation",
            settings={"base_url": "https://soar-api.talos.cisco.com"},
            credentials={"certificate": "test-cert", "key": "test-key"},
        )

    @pytest.mark.asyncio
    async def test_domain_reputation_success(self, domain_action):
        mock_taxonomy_response = MagicMock()
        mock_taxonomy_response.json.return_value = MOCK_TAXONOMY_API_RESPONSE

        mock_reputation_response = MagicMock()
        mock_reputation_response.json.return_value = MOCK_REPUTATION_RESPONSE

        with patch.object(
            domain_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=[mock_taxonomy_response, mock_reputation_response],
        ):
            result = await domain_action.execute(domain="cisco.com")

        assert result["status"] == "success"
        assert result["data"]["observable"] == "cisco.com"
        assert result["data"]["threat_level"] == "Favorable"

    @pytest.mark.asyncio
    async def test_domain_reputation_sends_raw_url(self, domain_action):
        """Verify domain is sent as raw_url in the payload."""
        mock_taxonomy_response = MagicMock()
        mock_taxonomy_response.json.return_value = MOCK_TAXONOMY_API_RESPONSE

        mock_reputation_response = MagicMock()
        mock_reputation_response.json.return_value = MOCK_REPUTATION_RESPONSE

        with patch.object(
            domain_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=[mock_taxonomy_response, mock_reputation_response],
        ) as mock_request:
            await domain_action.execute(domain="splunk.com")

            reputation_call = mock_request.call_args_list[1]
            payload = reputation_call[1].get("json_data", {})
            assert payload["urls"] == [{"raw_url": "splunk.com"}]

    @pytest.mark.asyncio
    async def test_domain_reputation_missing_domain(self, domain_action):
        result = await domain_action.execute()
        assert result["status"] == "error"
        assert "Domain is required" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_domain_reputation_invalid_domain(self, domain_action):
        result = await domain_action.execute(domain="-invalid.com")
        assert result["status"] == "error"
        assert "Invalid domain name format" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_domain_reputation_missing_credentials(self):
        action = DomainReputationAction(
            integration_id="cisco-talos",
            action_id="domain_reputation",
            settings={},
            credentials={},
        )
        result = await action.execute(domain="cisco.com")
        assert result["status"] == "error"
        assert "Missing required credentials" in result["error"]

    @pytest.mark.asyncio
    async def test_domain_reputation_404_returns_not_found(self, domain_action):
        mock_taxonomy_response = MagicMock()
        mock_taxonomy_response.json.return_value = MOCK_TAXONOMY_API_RESPONSE

        mock_404_response = MagicMock(spec=httpx.Response)
        mock_404_response.status_code = 404
        mock_404_response.request = MagicMock()

        http_error = httpx.HTTPStatusError(
            "Not Found", request=mock_404_response.request, response=mock_404_response
        )

        with patch.object(
            domain_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=[mock_taxonomy_response, http_error],
        ):
            result = await domain_action.execute(domain="unknown-domain.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["observable"] == "unknown-domain.com"

    @pytest.mark.asyncio
    async def test_domain_reputation_api_error(self, domain_action):
        with patch.object(
            domain_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Server error"),
        ):
            result = await domain_action.execute(domain="cisco.com")

        assert result["status"] == "error"
        assert "Server error" in result["error"]


# ============================================================================
# URL REPUTATION ACTION TESTS
# ============================================================================


class TestUrlReputationAction:
    """Test Talos URL reputation action."""

    @pytest.fixture
    def url_action(self):
        return UrlReputationAction(
            integration_id="cisco-talos",
            action_id="url_reputation",
            settings={"base_url": "https://soar-api.talos.cisco.com"},
            credentials={"certificate": "test-cert", "key": "test-key"},
        )

    @pytest.mark.asyncio
    async def test_url_reputation_success(self, url_action):
        mock_taxonomy_response = MagicMock()
        mock_taxonomy_response.json.return_value = MOCK_TAXONOMY_API_RESPONSE

        mock_reputation_response = MagicMock()
        mock_reputation_response.json.return_value = MOCK_REPUTATION_RESPONSE

        with patch.object(
            url_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=[mock_taxonomy_response, mock_reputation_response],
        ):
            result = await url_action.execute(url="https://cisco.com")

        assert result["status"] == "success"
        assert result["data"]["observable"] == "https://cisco.com"
        assert result["data"]["threat_level"] == "Favorable"

    @pytest.mark.asyncio
    async def test_url_reputation_sends_raw_url(self, url_action):
        mock_taxonomy_response = MagicMock()
        mock_taxonomy_response.json.return_value = MOCK_TAXONOMY_API_RESPONSE

        mock_reputation_response = MagicMock()
        mock_reputation_response.json.return_value = MOCK_REPUTATION_RESPONSE

        with patch.object(
            url_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=[mock_taxonomy_response, mock_reputation_response],
        ) as mock_request:
            await url_action.execute(url="https://splunk.com/path?q=1")

            reputation_call = mock_request.call_args_list[1]
            payload = reputation_call[1].get("json_data", {})
            assert payload["urls"] == [{"raw_url": "https://splunk.com/path?q=1"}]

    @pytest.mark.asyncio
    async def test_url_reputation_missing_url(self, url_action):
        result = await url_action.execute()
        assert result["status"] == "error"
        assert "URL is required" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_url_reputation_invalid_url_no_scheme(self, url_action):
        result = await url_action.execute(url="example.com")
        assert result["status"] == "error"
        assert "Invalid URL format" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_url_reputation_missing_credentials(self):
        action = UrlReputationAction(
            integration_id="cisco-talos",
            action_id="url_reputation",
            settings={},
            credentials={},
        )
        result = await action.execute(url="https://example.com")
        assert result["status"] == "error"
        assert "Missing required credentials" in result["error"]

    @pytest.mark.asyncio
    async def test_url_reputation_404_returns_not_found(self, url_action):
        mock_taxonomy_response = MagicMock()
        mock_taxonomy_response.json.return_value = MOCK_TAXONOMY_API_RESPONSE

        mock_404_response = MagicMock(spec=httpx.Response)
        mock_404_response.status_code = 404
        mock_404_response.request = MagicMock()

        http_error = httpx.HTTPStatusError(
            "Not Found", request=mock_404_response.request, response=mock_404_response
        )

        with patch.object(
            url_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=[mock_taxonomy_response, http_error],
        ):
            result = await url_action.execute(url="https://unknown.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["observable"] == "https://unknown.com"

    @pytest.mark.asyncio
    async def test_url_reputation_api_error(self, url_action):
        with patch.object(
            url_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=Exception("Timeout"),
        ):
            result = await url_action.execute(url="https://cisco.com")

        assert result["status"] == "error"
        assert "Timeout" in result["error"]
