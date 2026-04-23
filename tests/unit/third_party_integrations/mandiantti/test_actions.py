"""Unit tests for Mandiant Advantage Threat Intelligence integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.mandiantti.actions import (
    CampaignLookupAction,
    HealthCheckAction,
    IndicatorLookupAction,
    MalwareFamilyLookupAction,
    ReportListAction,
    ReportLookupAction,
    SearchAction,
    ThreatActorLookupAction,
    VulnerabilityLookupAction,
)

# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

DEFAULT_CREDENTIALS = {"api_key": "test-api-key", "secret_key": "test-secret-key"}
DEFAULT_SETTINGS = {
    "base_url": "https://api.intelligence.mandiant.com/",
    "timeout": 30,
}


def _make_action(cls, credentials=None, settings=None):
    """Create an action instance for testing."""
    return cls(
        integration_id="mandiantti",
        action_id=cls.__name__,
        settings=DEFAULT_SETTINGS.copy() if settings is None else settings,
        credentials=DEFAULT_CREDENTIALS.copy() if credentials is None else credentials,
    )


def _mock_response(json_data=None, status_code=200, text=None):
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = json_data if json_data is not None else {}
    resp.status_code = status_code
    resp.text = text if text is not None else str(json_data)
    return resp


def _mock_token_response():
    """Create a mock response for the OAuth2 token endpoint."""
    return _mock_response(
        json_data={"access_token": "test-bearer-token", "expires_in": 1799}
    )


def _mock_http_error(status_code, message="error"):
    """Create a mock httpx.HTTPStatusError."""
    request = MagicMock(spec=httpx.Request)
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = message
    return httpx.HTTPStatusError(message, request=request, response=response)


# ============================================================================
# HEALTH CHECK
# ============================================================================


class TestHealthCheckAction:
    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        token_resp = _mock_token_response()
        entitlements_resp = _mock_response({"entitlements": ["intel"]})

        action.http_request = AsyncMock(side_effect=[token_resp, entitlements_resp])

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert "integration_id" in result
        assert action.http_request.call_count == 2

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(HealthCheckAction, credentials={"secret_key": "s"})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "api_key" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_secret_key(self):
        action = _make_action(HealthCheckAction, credentials={"api_key": "k"})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "secret_key" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_all_credentials(self):
        action = _make_action(HealthCheckAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_token_failure(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(401, "Unauthorized")
        )
        result = await action.execute()

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_connection_error(self, action):
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]


# ============================================================================
# INDICATOR LOOKUP
# ============================================================================


class TestIndicatorLookupAction:
    @pytest.fixture
    def action(self):
        return _make_action(IndicatorLookupAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        token_resp = _mock_token_response()
        search_resp = _mock_response(
            {"indicators": [{"type": "ip", "value": "1.2.3.4"}]}
        )
        detail_resp = _mock_response(
            {
                "id": "ipv4--1234",
                "value": "1.2.3.4",
                "type": "ip",
                "mscore": 85,
                "sources": [{"category": ["malware", "phishing"]}],
                "attributed_associations": [{"name": "APT29", "type": "threat-actor"}],
                "first_seen": "2020-01-01",
                "last_seen": "2024-01-01",
                "campaigns": [{"name": "CAMP.001"}],
            }
        )
        report_resp = _mock_response(
            {"reports": [{"id": "rpt-1", "title": "Report 1"}]}
        )

        action.http_request = AsyncMock(
            side_effect=[token_resp, search_resp, detail_resp, report_resp]
        )

        result = await action.execute(indicator="1.2.3.4")

        assert result["status"] == "success"
        assert result["data"]["value"] == "1.2.3.4"
        assert result["data"]["confidence"] == 85
        assert "malware" in result["data"]["categories"]
        assert "phishing" in result["data"]["categories"]
        assert result["data"]["attributed_associations"][0]["name"] == "APT29"
        assert len(result["data"]["reports"]) == 1
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_indicator_not_found_empty_list(self, action):
        """When API returns empty indicators list."""
        token_resp = _mock_token_response()
        search_resp = _mock_response({"indicators": []})

        action.http_request = AsyncMock(side_effect=[token_resp, search_resp])

        result = await action.execute(indicator="unknown.example")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["indicator"] == "unknown.example"

    @pytest.mark.asyncio
    async def test_indicator_not_found_no_list(self, action):
        """When API returns non-list indicators (null/missing)."""
        token_resp = _mock_token_response()
        search_resp = _mock_response({"indicators": None})

        action.http_request = AsyncMock(side_effect=[token_resp, search_resp])

        result = await action.execute(indicator="unknown")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        """When an API call returns 404."""
        token_resp = _mock_token_response()
        action.http_request = AsyncMock(
            side_effect=[token_resp, _mock_http_error(404, "Not Found")]
        )

        result = await action.execute(indicator="1.2.3.4")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_missing_indicator(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "indicator" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(IndicatorLookupAction, credentials={})
        result = await action.execute(indicator="1.2.3.4")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        token_resp = _mock_token_response()
        action.http_request = AsyncMock(
            side_effect=[token_resp, _mock_http_error(500, "Internal Server Error")]
        )

        result = await action.execute(indicator="1.2.3.4")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_md5_indicator_includes_associated_hashes(self, action):
        """When indicator is md5, associated hashes should be included."""
        token_resp = _mock_token_response()
        search_resp = _mock_response(
            {"indicators": [{"type": "md5", "value": "abc123"}]}
        )
        detail_resp = _mock_response(
            {
                "id": "md5--abc",
                "value": "abc123",
                "type": "md5",
                "mscore": 90,
                "sources": [],
                "attributed_associations": [],
                "first_seen": "2021-01-01",
                "last_seen": "2024-06-01",
                "campaigns": [],
                "associated_hashes": [
                    {"type": "md5", "value": "abc123"},
                    {"type": "sha1", "value": "sha1hash"},
                    {"type": "sha256", "value": "sha256hash"},
                ],
            }
        )
        report_resp = _mock_response({"reports": []})

        action.http_request = AsyncMock(
            side_effect=[token_resp, search_resp, detail_resp, report_resp]
        )

        result = await action.execute(indicator="abc123")

        assert result["status"] == "success"
        assert result["data"]["associated_md5"] == "abc123"
        assert result["data"]["associated_sha1"] == "sha1hash"
        assert result["data"]["associated_sha256"] == "sha256hash"


# ============================================================================
# THREAT ACTOR LOOKUP
# ============================================================================


class TestThreatActorLookupAction:
    @pytest.fixture
    def action(self):
        return _make_action(ThreatActorLookupAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        token_resp = _mock_token_response()
        actor_resp = _mock_response(
            {
                "id": "actor--apt29",
                "name": "APT29",
                "description": "Russian threat actor",
                "motivations": [{"name": "Espionage"}],
                "industries": [{"name": "Government"}],
            }
        )
        report_resp = _mock_response(
            {"reports": [{"id": "rpt-1", "title": "APT29 Report"}]}
        )
        campaign_resp = _mock_response({"campaigns": [{"name": "CAMP.001"}]})

        action.http_request = AsyncMock(
            side_effect=[token_resp, actor_resp, report_resp, campaign_resp]
        )

        result = await action.execute(threat_actor="APT29")

        assert result["status"] == "success"
        assert result["data"]["name"] == "APT29"
        assert len(result["data"]["reports"]) == 1
        assert result["data"]["campaigns"][0]["name"] == "CAMP.001"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_threat_actor(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "threat_actor" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ThreatActorLookupAction, credentials={})
        result = await action.execute(threat_actor="APT29")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        token_resp = _mock_token_response()
        action.http_request = AsyncMock(
            side_effect=[token_resp, _mock_http_error(404, "Not Found")]
        )

        result = await action.execute(threat_actor="FAKE_ACTOR")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["threat_actor"] == "FAKE_ACTOR"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        token_resp = _mock_token_response()
        action.http_request = AsyncMock(
            side_effect=[token_resp, _mock_http_error(500, "Server Error")]
        )

        result = await action.execute(threat_actor="APT29")

        assert result["status"] == "error"


# ============================================================================
# VULNERABILITY LOOKUP
# ============================================================================


class TestVulnerabilityLookupAction:
    @pytest.fixture
    def action(self):
        return _make_action(VulnerabilityLookupAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        token_resp = _mock_token_response()
        vuln_resp = _mock_response(
            {
                "cve_id": "CVE-2021-44228",
                "risk_rating": "critical",
                "title": "Apache Log4j2 RCE",
                "description": "Remote code execution in Log4j",
            }
        )

        action.http_request = AsyncMock(side_effect=[token_resp, vuln_resp])

        result = await action.execute(vulnerability="CVE-2021-44228")

        assert result["status"] == "success"
        assert result["data"]["cve_id"] == "CVE-2021-44228"
        # risk_rating should be capitalized
        assert result["data"]["risk_rating"] == "Critical"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_vulnerability(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "vulnerability" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(VulnerabilityLookupAction, credentials={})
        result = await action.execute(vulnerability="CVE-2021-44228")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        token_resp = _mock_token_response()
        action.http_request = AsyncMock(
            side_effect=[token_resp, _mock_http_error(404, "Not Found")]
        )

        result = await action.execute(vulnerability="CVE-9999-99999")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["vulnerability"] == "CVE-9999-99999"


# ============================================================================
# MALWARE FAMILY LOOKUP
# ============================================================================


class TestMalwareFamilyLookupAction:
    @pytest.fixture
    def action(self):
        return _make_action(MalwareFamilyLookupAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        token_resp = _mock_token_response()
        malware_resp = _mock_response(
            {
                "id": "malware--emotet",
                "name": "EMOTET",
                "description": "Banking trojan turned loader",
            }
        )
        report_resp = _mock_response(
            {"reports": [{"id": "rpt-1", "title": "Emotet Report"}]}
        )
        campaign_resp = _mock_response({"campaigns": [{"name": "CAMP.EMOTET"}]})

        action.http_request = AsyncMock(
            side_effect=[token_resp, malware_resp, report_resp, campaign_resp]
        )

        result = await action.execute(malware_family="EMOTET")

        assert result["status"] == "success"
        assert result["data"]["name"] == "EMOTET"
        assert len(result["data"]["reports"]) == 1
        assert result["data"]["campaigns"][0]["name"] == "CAMP.EMOTET"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_malware_family(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "malware_family" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(MalwareFamilyLookupAction, credentials={})
        result = await action.execute(malware_family="EMOTET")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        token_resp = _mock_token_response()
        action.http_request = AsyncMock(
            side_effect=[token_resp, _mock_http_error(404, "Not Found")]
        )

        result = await action.execute(malware_family="UNKNOWN_MALWARE")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["malware_family"] == "UNKNOWN_MALWARE"


# ============================================================================
# CAMPAIGN LOOKUP
# ============================================================================


class TestCampaignLookupAction:
    @pytest.fixture
    def action(self):
        return _make_action(CampaignLookupAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        token_resp = _mock_token_response()
        campaign_resp = _mock_response(
            {
                "id": "campaign--001",
                "name": "CAMP.001",
                "description": "A campaign",
                "actors": [{"name": "APT29"}],
            }
        )
        report_resp = _mock_response(
            {"reports": [{"id": "rpt-1", "title": "Campaign Report"}]}
        )

        action.http_request = AsyncMock(
            side_effect=[token_resp, campaign_resp, report_resp]
        )

        result = await action.execute(campaign="CAMP.001")

        assert result["status"] == "success"
        assert result["data"]["name"] == "CAMP.001"
        assert len(result["data"]["reports"]) == 1
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_campaign(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "campaign" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(CampaignLookupAction, credentials={})
        result = await action.execute(campaign="CAMP.001")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        token_resp = _mock_token_response()
        action.http_request = AsyncMock(
            side_effect=[token_resp, _mock_http_error(404, "Not Found")]
        )

        result = await action.execute(campaign="FAKE_CAMPAIGN")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["campaign"] == "FAKE_CAMPAIGN"


# ============================================================================
# SEARCH
# ============================================================================


class TestSearchAction:
    @pytest.fixture
    def action(self):
        return _make_action(SearchAction)

    @pytest.mark.asyncio
    async def test_success_single_page(self, action):
        token_resp = _mock_token_response()
        search_resp = _mock_response(
            {
                "objects": [
                    {"type": "indicator", "name": "1.2.3.4"},
                    {"type": "threat-actor", "name": "APT29"},
                ],
            }
        )

        action.http_request = AsyncMock(side_effect=[token_resp, search_resp])

        result = await action.execute(query="APT29")

        assert result["status"] == "success"
        assert len(result["data"]["objects"]) == 2
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_success_paginated(self, action):
        """Test pagination when first page returns exactly 50 objects."""
        token_resp = _mock_token_response()
        page1_objects = [{"type": "indicator", "name": f"obj-{i}"} for i in range(50)]
        page1_resp = _mock_response({"objects": page1_objects, "next": "cursor-abc"})
        page2_objects = [{"type": "indicator", "name": "obj-50"}]
        page2_resp = _mock_response({"objects": page2_objects})

        action.http_request = AsyncMock(
            side_effect=[token_resp, page1_resp, page2_resp]
        )

        result = await action.execute(query="test")

        assert result["status"] == "success"
        assert len(result["data"]["objects"]) == 51

    @pytest.mark.asyncio
    async def test_empty_results(self, action):
        token_resp = _mock_token_response()
        search_resp = _mock_response({"objects": []})

        action.http_request = AsyncMock(side_effect=[token_resp, search_resp])

        result = await action.execute(query="nonexistent")

        assert result["status"] == "success"
        assert result["data"]["objects"] == []

    @pytest.mark.asyncio
    async def test_missing_query(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "query" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(SearchAction, credentials={})
        result = await action.execute(query="test")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_pagination_safety_limit(self, action):
        """Search must stop after MAX_PAGES even if API keeps returning full pages."""
        from analysi.integrations.framework.integrations.mandiantti.actions import (
            MAX_PAGES,
        )

        token_resp = _mock_token_response()

        # Build a response that always returns a full page with a next cursor
        full_page = [{"type": "indicator", "name": f"obj-{i}"} for i in range(50)]

        def _make_page_response():
            return _mock_response({"objects": full_page, "next": "cursor-forever"})

        # token + MAX_PAGES+10 page responses (more than the limit)
        side_effects = [token_resp] + [
            _make_page_response() for _ in range(MAX_PAGES + 10)
        ]
        action.http_request = AsyncMock(side_effect=side_effects)

        result = await action.execute(query="infinite")

        assert result["status"] == "success"
        # Should have exactly MAX_PAGES * 50 objects (stopped at limit)
        assert len(result["data"]["objects"]) == MAX_PAGES * 50
        # 1 token call + MAX_PAGES page calls
        assert action.http_request.call_count == 1 + MAX_PAGES
        # Caller must know results were truncated
        assert result["data"]["truncated"] is True


# ============================================================================
# REPORT LOOKUP
# ============================================================================


class TestReportLookupAction:
    @pytest.fixture
    def action(self):
        return _make_action(ReportLookupAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        token_resp = _mock_token_response()
        report_resp = _mock_response(text="<html><body>Report content</body></html>")

        action.http_request = AsyncMock(side_effect=[token_resp, report_resp])

        result = await action.execute(report_id="RPT-12345")

        assert result["status"] == "success"
        assert result["data"]["report_id"] == "RPT-12345"
        assert "<html>" in result["data"]["report"]
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_report_id(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "report_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ReportLookupAction, credentials={})
        result = await action.execute(report_id="RPT-12345")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        token_resp = _mock_token_response()
        action.http_request = AsyncMock(
            side_effect=[token_resp, _mock_http_error(404, "Not Found")]
        )

        result = await action.execute(report_id="RPT-FAKE")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["report_id"] == "RPT-FAKE"


# ============================================================================
# REPORT LIST
# ============================================================================


class TestReportListAction:
    @pytest.fixture
    def action(self):
        return _make_action(ReportListAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        token_resp = _mock_token_response()
        report_list_resp = _mock_response(
            {
                "objects": [
                    {"report_type": "ACTOR", "title": "Actor Report"},
                    {"report_type": "MALWARE", "title": "Malware Report"},
                ],
            }
        )

        action.http_request = AsyncMock(side_effect=[token_resp, report_list_resp])

        result = await action.execute()

        assert result["status"] == "success"
        assert len(result["data"]["objects"]) == 2
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_filter_by_report_type(self, action):
        token_resp = _mock_token_response()
        report_list_resp = _mock_response(
            {
                "objects": [
                    {"report_type": "ACTOR", "title": "Actor Report"},
                    {"report_type": "MALWARE", "title": "Malware Report"},
                    {"report_type": "ACTOR", "title": "Another Actor Report"},
                ],
            }
        )

        action.http_request = AsyncMock(side_effect=[token_resp, report_list_resp])

        result = await action.execute(report_type="ACTOR")

        assert result["status"] == "success"
        assert len(result["data"]["objects"]) == 2
        assert all(r["report_type"] == "ACTOR" for r in result["data"]["objects"])

    @pytest.mark.asyncio
    async def test_custom_days_parameter(self, action):
        token_resp = _mock_token_response()
        report_list_resp = _mock_response({"objects": []})

        action.http_request = AsyncMock(side_effect=[token_resp, report_list_resp])

        result = await action.execute(days=30)

        assert result["status"] == "success"
        # Verify start_epoch param was passed
        call_kwargs = action.http_request.call_args_list[1].kwargs
        assert "start_epoch" in call_kwargs["params"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ReportListAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        token_resp = _mock_token_response()
        action.http_request = AsyncMock(
            side_effect=[token_resp, _mock_http_error(500, "Server Error")]
        )

        result = await action.execute()

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_invalid_days_non_numeric(self, action):
        """Non-numeric days value should return a ValidationError, not raise."""
        result = await action.execute(days="abc")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "abc" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_days_zero(self, action):
        """Zero days should return a ValidationError."""
        result = await action.execute(days=0)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_days_negative(self, action):
        """Negative days should return a ValidationError."""
        result = await action.execute(days=-5)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_pagination_safety_limit(self, action):
        """ReportList must stop after MAX_PAGES even if API keeps returning full pages."""
        from analysi.integrations.framework.integrations.mandiantti.actions import (
            MAX_PAGES,
        )

        token_resp = _mock_token_response()

        # Build a response that always returns a full page with a next cursor
        full_page = [{"report_type": "ACTOR", "title": f"rpt-{i}"} for i in range(10)]

        def _make_page_response():
            return _mock_response({"objects": full_page, "next": "cursor-forever"})

        side_effects = [token_resp] + [
            _make_page_response() for _ in range(MAX_PAGES + 10)
        ]
        action.http_request = AsyncMock(side_effect=side_effects)

        result = await action.execute(days=30)

        assert result["status"] == "success"
        # Should have exactly MAX_PAGES * 10 objects (stopped at limit)
        assert len(result["data"]["objects"]) == MAX_PAGES * 10
        # 1 token call + MAX_PAGES page calls
        assert action.http_request.call_count == 1 + MAX_PAGES
        # Caller must know results were truncated
        assert result["data"]["truncated"] is True


# ============================================================================
# BASE CLASS HELPERS
# ============================================================================


class TestMandiantBaseHelpers:
    """Test shared base class methods."""

    def test_get_http_headers(self):
        action = _make_action(HealthCheckAction)
        headers = action.get_http_headers()
        assert headers["X-App-Name"] == "Analysi-MandiantTI-v1.0.0"

    def test_base_url_strips_trailing_slash(self):
        action = _make_action(HealthCheckAction)
        assert action.base_url == "https://api.intelligence.mandiant.com"

    def test_base_url_custom(self):
        action = _make_action(
            HealthCheckAction,
            settings={"base_url": "https://custom.mandiant.example/api/"},
        )
        assert action.base_url == "https://custom.mandiant.example/api"

    def test_timeout_default(self):
        action = _make_action(HealthCheckAction, settings={})
        assert action.get_timeout() == 60  # Mandiant default

    def test_timeout_custom(self):
        action = _make_action(HealthCheckAction, settings={"timeout": 120})
        assert action.get_timeout() == 120

    def test_require_credentials_missing_api_key(self):
        action = _make_action(HealthCheckAction, credentials={"secret_key": "s"})
        result = action._require_credentials()
        assert result is not None
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    def test_require_credentials_missing_secret_key(self):
        action = _make_action(HealthCheckAction, credentials={"api_key": "k"})
        result = action._require_credentials()
        assert result is not None
        assert result["error_type"] == "ConfigurationError"

    def test_require_credentials_all_present(self):
        action = _make_action(HealthCheckAction)
        result = action._require_credentials()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_bearer_token(self):
        action = _make_action(HealthCheckAction)
        token_resp = _mock_token_response()
        action.http_request = AsyncMock(return_value=token_resp)

        token = await action._get_bearer_token()

        assert token == "test-bearer-token"
        # Verify token endpoint was called with basic auth
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["auth"] == ("test-api-key", "test-secret-key")
        assert call_kwargs["method"] == "POST"

    @pytest.mark.asyncio
    async def test_get_bearer_token_malformed_response(self):
        action = _make_action(HealthCheckAction)
        bad_resp = _mock_response({"error": "no access_token"})
        action.http_request = AsyncMock(return_value=bad_resp)

        with pytest.raises(RuntimeError, match="Failed to obtain bearer token"):
            await action._get_bearer_token()

    def test_auth_headers(self):
        action = _make_action(HealthCheckAction)
        headers = action._auth_headers("my-token")
        assert headers["Authorization"] == "Bearer my-token"
        assert headers["Accept"] == "application/json"
