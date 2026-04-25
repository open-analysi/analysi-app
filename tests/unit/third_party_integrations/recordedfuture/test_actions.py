"""Unit tests for Recorded Future integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.recordedfuture.actions import (
    AlertSearchAction,
    DomainIntelligenceAction,
    DomainReputationAction,
    FileIntelligenceAction,
    FileReputationAction,
    HealthCheckAction,
    IpIntelligenceAction,
    IpReputationAction,
    ThreatAssessmentAction,
    UrlIntelligenceAction,
    UrlReputationAction,
    VulnerabilityLookupAction,
    _empty_intelligence_response,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

DEFAULT_CREDENTIALS = {"api_token": "test-rf-token-abc123"}
DEFAULT_SETTINGS = {
    "base_url": "https://api.recordedfuture.com/gw/phantom",
    "timeout": 30,
}


def _make_action(cls, credentials=None, settings=None):
    """Create an action instance for testing."""
    return cls(
        integration_id="recordedfuture",
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
# EMPTY RESPONSE HELPER
# ============================================================================


class TestEmptyIntelligenceResponse:
    """Test the _empty_intelligence_response helper."""

    def test_returns_stub_structure(self):
        result = _empty_intelligence_response()
        assert "entity" in result
        assert "risk" in result
        assert "timestamps" in result
        assert result["risk"]["score"] is None
        assert result["risk"]["riskSummary"] == "No information available."


# ============================================================================
# HEALTH CHECK
# ============================================================================


class TestHealthCheckAction:
    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        helo_resp = _mock_response({})
        config_resp = _mock_response({"some": "config"})

        # http_request is called twice: /helo then /config/info
        action.http_request = AsyncMock(side_effect=[helo_resp, config_resp])

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert "integration_id" in result
        assert action.http_request.call_count == 2

    @pytest.mark.asyncio
    async def test_missing_api_token(self):
        action = _make_action(HealthCheckAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "api_token" in result["error"]

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
# IP INTELLIGENCE
# ============================================================================


class TestIpIntelligenceAction:
    @pytest.fixture
    def action(self):
        return _make_action(IpIntelligenceAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_data = {
            "entity": {"id": "ip:1.2.3.4", "name": "1.2.3.4", "type": "IpAddress"},
            "risk": {"score": 75, "criticalityLabel": "Malicious"},
            "timestamps": {"firstSeen": "2026-04-26", "lastSeen": "2026-04-26"},
        }
        action.http_request = AsyncMock(return_value=_mock_response({"data": api_data}))

        result = await action.execute(ip="1.2.3.4")

        assert result["status"] == "success"
        assert result["data"]["risk"]["score"] == 75
        assert result["data"]["entity"]["name"] == "1.2.3.4"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_ip(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ip" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(IpIntelligenceAction, credentials={})
        result = await action.execute(ip="1.2.3.4")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404, "Not Found"))
        result = await action.execute(ip="1.2.3.4")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["risk"]["score"] is None

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Internal Server Error")
        )
        result = await action.execute(ip="1.2.3.4")

        assert result["status"] == "error"


# ============================================================================
# IP REPUTATION
# ============================================================================


class TestIpReputationAction:
    @pytest.fixture
    def action(self):
        return _make_action(IpReputationAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        entity_data = {
            "id": "ip:1.2.3.4",
            "name": "1.2.3.4",
            "riskscore": 55,
            "rulecount": 3,
            "maxrules": 42,
        }
        action.http_request = AsyncMock(return_value=_mock_response([entity_data]))

        result = await action.execute(ip="1.2.3.4")

        assert result["status"] == "success"
        assert result["data"]["riskscore"] == 55
        assert result["data"]["rulecount"] == 3

    @pytest.mark.asyncio
    async def test_missing_ip(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404, "Not Found"))
        result = await action.execute(ip="1.2.3.4")

        assert result["status"] == "success"
        assert result["not_found"] is True


# ============================================================================
# DOMAIN INTELLIGENCE
# ============================================================================


class TestDomainIntelligenceAction:
    @pytest.fixture
    def action(self):
        return _make_action(DomainIntelligenceAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_data = {
            "entity": {
                "id": "domain:attacker.example",
                "name": "attacker.example",
                "type": "InternetDomainName",
            },
            "risk": {"score": 90, "criticalityLabel": "Very Malicious"},
        }
        action.http_request = AsyncMock(return_value=_mock_response({"data": api_data}))

        result = await action.execute(domain="attacker.example")

        assert result["status"] == "success"
        assert result["data"]["risk"]["score"] == 90

    @pytest.mark.asyncio
    async def test_missing_domain(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(domain="unknown.example")
        assert result["status"] == "success"
        assert result["not_found"] is True


# ============================================================================
# DOMAIN REPUTATION
# ============================================================================


class TestDomainReputationAction:
    @pytest.fixture
    def action(self):
        return _make_action(DomainReputationAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        entity_data = {"id": "domain:attacker.example", "riskscore": 80, "rulecount": 5}
        action.http_request = AsyncMock(return_value=_mock_response([entity_data]))

        result = await action.execute(domain="attacker.example")
        assert result["status"] == "success"
        assert result["data"]["riskscore"] == 80

    @pytest.mark.asyncio
    async def test_missing_domain(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# ============================================================================
# FILE INTELLIGENCE
# ============================================================================


class TestFileIntelligenceAction:
    @pytest.fixture
    def action(self):
        return _make_action(FileIntelligenceAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_data = {
            "entity": {"id": "hash:abc123", "name": "abc123", "type": "Hash"},
            "risk": {"score": 60, "criticalityLabel": "Suspicious"},
        }
        action.http_request = AsyncMock(return_value=_mock_response({"data": api_data}))

        result = await action.execute(hash="abc123def456")
        assert result["status"] == "success"
        assert result["data"]["risk"]["score"] == 60

    @pytest.mark.asyncio
    async def test_missing_hash(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(hash="deadbeef")
        assert result["status"] == "success"
        assert result["not_found"] is True


# ============================================================================
# FILE REPUTATION
# ============================================================================


class TestFileReputationAction:
    @pytest.fixture
    def action(self):
        return _make_action(FileReputationAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        entity_data = {"id": "hash:abc", "riskscore": 40, "rulecount": 2}
        action.http_request = AsyncMock(return_value=_mock_response([entity_data]))

        result = await action.execute(hash="abc123")
        assert result["status"] == "success"
        assert result["data"]["riskscore"] == 40

    @pytest.mark.asyncio
    async def test_missing_hash(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# ============================================================================
# URL INTELLIGENCE
# ============================================================================


class TestUrlIntelligenceAction:
    @pytest.fixture
    def action(self):
        return _make_action(UrlIntelligenceAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_data = {
            "entity": {"name": "http://attacker.example/malware"},
            "risk": {"score": 85, "criticalityLabel": "Malicious"},
        }
        action.http_request = AsyncMock(return_value=_mock_response({"data": api_data}))

        result = await action.execute(url="http://attacker.example/malware")
        assert result["status"] == "success"
        assert result["data"]["risk"]["score"] == 85

    @pytest.mark.asyncio
    async def test_missing_url(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(url="http://unknown.example")
        assert result["status"] == "success"
        assert result["not_found"] is True


# ============================================================================
# URL REPUTATION
# ============================================================================


class TestUrlReputationAction:
    @pytest.fixture
    def action(self):
        return _make_action(UrlReputationAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        entity_data = {"id": "url:x", "riskscore": 70, "rulecount": 4}
        action.http_request = AsyncMock(return_value=_mock_response([entity_data]))

        result = await action.execute(url="http://attacker.example")
        assert result["status"] == "success"
        assert result["data"]["riskscore"] == 70

    @pytest.mark.asyncio
    async def test_missing_url(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# ============================================================================
# VULNERABILITY LOOKUP
# ============================================================================


class TestVulnerabilityLookupAction:
    @pytest.fixture
    def action(self):
        return _make_action(VulnerabilityLookupAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_data = {
            "entity": {"id": "vuln:CVE-2021-44228", "name": "CVE-2021-44228"},
            "risk": {"score": 99, "criticalityLabel": "Critical"},
            "cvss": {"score": 10.0},
            "nvdDescription": "Apache Log4j2 RCE",
        }
        action.http_request = AsyncMock(return_value=_mock_response({"data": api_data}))

        result = await action.execute(cve="CVE-2021-44228")
        assert result["status"] == "success"
        assert result["data"]["risk"]["score"] == 99
        assert result["data"]["cvss"]["score"] == 10.0

    @pytest.mark.asyncio
    async def test_missing_cve(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "cve" in result["error"]

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(cve="CVE-9999-99999")
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(VulnerabilityLookupAction, credentials={})
        result = await action.execute(cve="CVE-2021-44228")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# THREAT ASSESSMENT
# ============================================================================


class TestThreatAssessmentAction:
    @pytest.fixture
    def action(self):
        return _make_action(ThreatAssessmentAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        triage_result = {
            "verdict": True,
            "triage_riskscore": 80,
            "entities": [
                {"name": "1.2.3.4", "score": 75, "type": "IpAddress"},
            ],
        }
        action.http_request = AsyncMock(return_value=_mock_response(triage_result))

        result = await action.execute(threat_context="c2", ip="1.2.3.4")

        assert result["status"] == "success"
        assert result["data"]["verdict"] is True
        assert result["data"]["triage_riskscore"] == 80

    @pytest.mark.asyncio
    async def test_missing_context(self, action):
        result = await action.execute(ip="1.2.3.4")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "threat_context" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_context(self, action):
        result = await action.execute(threat_context="ransomware", ip="1.2.3.4")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "ransomware" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_iocs(self, action):
        result = await action.execute(threat_context="c2")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "IOC" in result["error"]

    @pytest.mark.asyncio
    async def test_multiple_ioc_types(self, action):
        triage_result = {
            "verdict": False,
            "triage_riskscore": 10,
            "entities": [],
        }
        action.http_request = AsyncMock(return_value=_mock_response(triage_result))

        result = await action.execute(
            threat_context="malware",
            ip="1.2.3.4,5.6.7.8",
            domain="attacker.example",
        )

        assert result["status"] == "success"
        # Verify the payload sent to the API
        call_kwargs = action.http_request.call_args.kwargs
        payload = call_kwargs["json_data"]
        assert len(payload["ip"]) == 2
        assert payload["domain"] == ["attacker.example"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ThreatAssessmentAction, credentials={})
        result = await action.execute(threat_context="c2", ip="1.2.3.4")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# ALERT SEARCH
# ============================================================================


class TestAlertSearchAction:
    @pytest.fixture
    def action(self):
        return _make_action(AlertSearchAction)

    @pytest.mark.asyncio
    async def test_success_with_alerts(self, action):
        search_resp = _mock_response(
            {
                "counts": {"total": 2, "returned": 2},
                "data": {
                    "results": [
                        {
                            "id": "alert-1",
                            "rule": {"id": "rule-abc", "name": "Test Rule"},
                        },
                        {
                            "id": "alert-2",
                            "rule": {"id": "rule-abc", "name": "Test Rule"},
                        },
                    ],
                },
            }
        )
        detail_resp_1 = _mock_response(
            {
                "id": "alert-1",
                "title": "Alert One",
                "triggered": "2026-04-26",
            }
        )
        detail_resp_2 = _mock_response(
            {
                "id": "alert-2",
                "title": "Alert Two",
                "triggered": "2026-04-27",
            }
        )

        action.http_request = AsyncMock(
            side_effect=[search_resp, detail_resp_1, detail_resp_2]
        )

        result = await action.execute(rule_id="rule-abc", timeframe="-24h to now")

        assert result["status"] == "success"
        assert result["data"]["total_alerts"] == 2
        assert len(result["data"]["alerts"]) == 2
        assert result["data"]["rule"]["name"] == "Test Rule"

    @pytest.mark.asyncio
    async def test_no_alerts_found(self, action):
        search_resp = _mock_response(
            {
                "counts": {"total": 0, "returned": 0},
                "data": {"results": []},
            }
        )

        action.http_request = AsyncMock(return_value=search_resp)

        result = await action.execute(rule_id="rule-xyz")

        assert result["status"] == "success"
        assert result["data"]["total_alerts"] == 0
        assert result["data"]["alerts"] == []

    @pytest.mark.asyncio
    async def test_missing_rule_id(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "rule_id" in result["error"]

    @pytest.mark.asyncio
    async def test_404_rule_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))
        result = await action.execute(rule_id="nonexistent")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["total_alerts"] == 0

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(AlertSearchAction, credentials={})
        result = await action.execute(rule_id="rule-abc")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_default_timeframe(self, action):
        """Verify default timeframe is used when not provided."""
        search_resp = _mock_response(
            {
                "counts": {"total": 0, "returned": 0},
                "data": {"results": []},
            }
        )
        action.http_request = AsyncMock(return_value=search_resp)

        result = await action.execute(rule_id="rule-abc")

        assert result["status"] == "success"
        # Verify default timeframe was used in the request
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["params"]["triggered"] == "-24h to now"


# ============================================================================
# AUTH HEADER INJECTION
# ============================================================================


class TestAuthHeaders:
    """Verify get_http_headers injects the X-RFToken header."""

    def test_headers_with_token(self):
        action = _make_action(HealthCheckAction)
        headers = action.get_http_headers()
        assert headers == {"X-RFToken": "test-rf-token-abc123"}

    def test_headers_without_token(self):
        action = _make_action(HealthCheckAction, credentials={})
        headers = action.get_http_headers()
        assert headers == {}

    def test_base_url_from_settings(self):
        action = _make_action(HealthCheckAction)
        assert action.base_url == "https://api.recordedfuture.com/gw/phantom"

    def test_base_url_custom(self):
        action = _make_action(
            HealthCheckAction,
            settings={"base_url": "https://custom.rf.example/api"},
        )
        assert action.base_url == "https://custom.rf.example/api"

    def test_timeout_default(self):
        action = _make_action(HealthCheckAction, settings={})
        assert action.get_timeout() == 120  # RF-specific default

    def test_timeout_custom(self):
        action = _make_action(HealthCheckAction, settings={"timeout": 60})
        assert action.get_timeout() == 60
