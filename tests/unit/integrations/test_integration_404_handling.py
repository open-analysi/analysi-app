"""Tests for graceful 404 (Resource not found) handling across integrations.

When an integration's shared HTTP helper raises Exception("Resource not found")
(or an integration-specific not-found message), lookup actions should return
{"status": "success", "not_found": True, ...} with zero/empty data instead of
{"status": "error"}.

Other errors (like "Rate limit exceeded") must still return {"status": "error"}.

This file covers representative lookup/get actions for all integrations that
use a shared HTTP helper which surfaces 404 as a specific exception message.
"""

from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.abuseipdb.actions import (
    LookupIpAction,
)
from analysi.integrations.framework.integrations.alienvaultotx.actions import (
    DomainReputationAction as OtxDomainReputationAction,
)
from analysi.integrations.framework.integrations.alienvaultotx.actions import (
    FileReputationAction as OtxFileReputationAction,
)
from analysi.integrations.framework.integrations.alienvaultotx.actions import (
    GetPulseAction as OtxGetPulseAction,
)
from analysi.integrations.framework.integrations.alienvaultotx.actions import (
    IpReputationAction as OtxIpReputationAction,
)
from analysi.integrations.framework.integrations.alienvaultotx.actions import (
    UrlReputationAction as OtxUrlReputationAction,
)
from analysi.integrations.framework.integrations.chronicle.actions import (
    ListAlertsAction as ChronicleListAlertsAction,
)
from analysi.integrations.framework.integrations.chronicle.actions import (
    ListAssetsAction as ChronicleListAssetsAction,
)
from analysi.integrations.framework.integrations.chronicle.actions import (
    ListDetectionsAction as ChronicleListDetectionsAction,
)
from analysi.integrations.framework.integrations.chronicle.actions import (
    ListEventsAction as ChronicleListEventsAction,
)
from analysi.integrations.framework.integrations.chronicle.actions import (
    ListIocDetailsAction as ChronicleListIocDetailsAction,
)
from analysi.integrations.framework.integrations.chronicle.actions import (
    ListIocsAction as ChronicleListIocsAction,
)
from analysi.integrations.framework.integrations.chronicle.actions import (
    ListRulesAction as ChronicleListRulesAction,
)
from analysi.integrations.framework.integrations.defender_endpoint.actions import (
    GetAlertAction as DefenderGetAlertAction,
)
from analysi.integrations.framework.integrations.duo.actions import (
    AuthorizeAction as DuoAuthorizeAction,
)
from analysi.integrations.framework.integrations.jira.actions import (
    CreateTicketAction as JiraCreateTicketAction,
)
from analysi.integrations.framework.integrations.jira.actions import (
    GetTicketAction as JiraGetTicketAction,
)
from analysi.integrations.framework.integrations.jira.actions import (
    ListProjectsAction as JiraListProjectsAction,
)
from analysi.integrations.framework.integrations.jira.actions import (
    SearchUsersAction as JiraSearchUsersAction,
)
from analysi.integrations.framework.integrations.maxmind.actions import (
    GeolocateIpAction as MaxmindGeolocateIpAction,
)
from analysi.integrations.framework.integrations.nistnvd.actions import (
    CveLookupAction as NistCveLookupAction,
)
from analysi.integrations.framework.integrations.sentinelone.actions import (
    GetThreatInfoAction as S1GetThreatInfoAction,
)
from analysi.integrations.framework.integrations.sentinelone.actions import (
    HashReputationAction as S1HashReputationAction,
)
from analysi.integrations.framework.integrations.shodan.actions import (
    DomainLookupAction as ShodanDomainLookupAction,
)
from analysi.integrations.framework.integrations.shodan.actions import (
    IpLookupAction as ShodanIpLookupAction,
)
from analysi.integrations.framework.integrations.tenable.actions import (
    DeleteScanAction as TenableDeleteScanAction,
)
from analysi.integrations.framework.integrations.tenable.actions import (
    ListScansAction as TenableListScansAction,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_action(action_class, credentials=None, settings=None):
    """Instantiate an action with test defaults."""
    return action_class(
        integration_id="test",
        action_id="test",
        settings=settings or {"timeout": 5},
        credentials=credentials or {},
    )


def _make_404_error():
    """Create an httpx.HTTPStatusError with status code 404."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 404
    mock_resp.text = "Not Found"
    mock_resp.json.return_value = {"error": "Resource not found"}
    return httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_resp)


def _make_429_error():
    """Create an httpx.HTTPStatusError with status code 429."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 429
    mock_resp.text = "Rate limit exceeded"
    mock_resp.json.return_value = {"error": "Rate limit exceeded"}
    return httpx.HTTPStatusError(
        "Rate limit exceeded", request=MagicMock(), response=mock_resp
    )


# ============================================================================
# 1. AbuseIPDB
# ============================================================================
class TestAbuseIpdbNotFoundHandling:
    """AbuseIPDB LookupIpAction 404 handling."""

    CREDS: ClassVar[dict] = {"api_key": "test-key"}

    @pytest.mark.asyncio
    async def test_404_returns_not_found_success(self):
        action = _make_action(LookupIpAction, credentials=self.CREDS)
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_404_error(),
        ):
            result = await action.execute(ip="192.168.1.1")
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_other_errors_still_return_error(self):
        action = _make_action(LookupIpAction, credentials=self.CREDS)
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_429_error(),
        ):
            result = await action.execute(ip="192.168.1.1")
        assert result["status"] == "error"


# ============================================================================
# 2. AlienVault OTX
# ============================================================================
class TestAlienVaultOtxNotFoundHandling:
    """AlienVault OTX lookup action 404 handling."""

    CREDS: ClassVar[dict] = {"api_key": "test-key"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("action_class", "execute_kwargs"),
        [
            (OtxDomainReputationAction, {"domain": "example.com"}),
            (OtxIpReputationAction, {"ip": "192.168.1.1"}),
            (OtxFileReputationAction, {"hash": "d41d8cd98f00b204e9800998ecf8427e"}),
            (OtxUrlReputationAction, {"url": "https://example.com/page"}),
            (OtxGetPulseAction, {"pulse_id": "test-pulse-123"}),
        ],
        ids=["domain", "ip", "file", "url", "pulse"],
    )
    async def test_404_returns_not_found_success(self, action_class, execute_kwargs):
        action = _make_action(action_class, credentials=self.CREDS)
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_404_error(),
        ):
            result = await action.execute(**execute_kwargs)
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("action_class", "execute_kwargs"),
        [
            (OtxDomainReputationAction, {"domain": "example.com"}),
            (OtxIpReputationAction, {"ip": "192.168.1.1"}),
            (OtxFileReputationAction, {"hash": "d41d8cd98f00b204e9800998ecf8427e"}),
            (OtxUrlReputationAction, {"url": "https://example.com/page"}),
            (OtxGetPulseAction, {"pulse_id": "test-pulse-123"}),
        ],
        ids=["domain", "ip", "file", "url", "pulse"],
    )
    async def test_other_errors_still_return_error(self, action_class, execute_kwargs):
        action = _make_action(action_class, credentials=self.CREDS)
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_429_error(),
        ):
            result = await action.execute(**execute_kwargs)
        assert result["status"] == "error"


# ============================================================================
# 3. Chronicle
# ============================================================================
class TestChronicleNotFoundHandling:
    """Chronicle SIEM action 404 handling."""

    PATCH_REQUEST = "analysi.integrations.framework.integrations.chronicle.actions._make_chronicle_request"
    PATCH_CREDS = "analysi.integrations.framework.integrations.chronicle.actions._get_credentials_from_key_json"
    CREDS: ClassVar[dict] = {"key_json": '{"type": "service_account"}'}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("action_class", "execute_kwargs"),
        [
            (
                ChronicleListIocDetailsAction,
                {"artifact_indicator": "Domain Name", "value": "example.com"},
            ),
            (
                ChronicleListAssetsAction,
                {
                    "artifact_indicator": "Domain Name",
                    "value": "example.com",
                    "start_time": "2024-01-01T00:00:00Z",
                    "end_time": "2024-01-02T00:00:00Z",
                },
            ),
            (
                ChronicleListEventsAction,
                {
                    "asset_identifier": "hostname",
                    "asset_identifier_value": "server1",
                    "start_time": "2024-01-01T00:00:00Z",
                    "end_time": "2024-01-02T00:00:00Z",
                },
            ),
            (ChronicleListIocsAction, {"start_time": "2024-01-01T00:00:00Z"}),
            (
                ChronicleListAlertsAction,
                {
                    "start_time": "2024-01-01T00:00:00Z",
                    "end_time": "2024-01-02T00:00:00Z",
                },
            ),
            (ChronicleListRulesAction, {}),
            (ChronicleListDetectionsAction, {"rule_id": "test-rule-123"}),
        ],
        ids=[
            "list_ioc_details",
            "list_assets",
            "list_events",
            "list_iocs",
            "list_alerts",
            "list_rules",
            "list_detections",
        ],
    )
    async def test_404_returns_not_found_success(self, action_class, execute_kwargs):
        action = _make_action(action_class, credentials=self.CREDS)
        with (
            patch(self.PATCH_CREDS, return_value=MagicMock()),
            patch(
                self.PATCH_REQUEST,
                new_callable=AsyncMock,
                side_effect=Exception("Resource not found"),
            ),
        ):
            result = await action.execute(**execute_kwargs)
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("action_class", "execute_kwargs"),
        [
            (
                ChronicleListIocDetailsAction,
                {"artifact_indicator": "Domain Name", "value": "example.com"},
            ),
            (ChronicleListRulesAction, {}),
            (ChronicleListDetectionsAction, {"rule_id": "test-rule-123"}),
        ],
        ids=["list_ioc_details", "list_rules", "list_detections"],
    )
    async def test_other_errors_still_return_error(self, action_class, execute_kwargs):
        action = _make_action(action_class, credentials=self.CREDS)
        with (
            patch(self.PATCH_CREDS, return_value=MagicMock()),
            patch(
                self.PATCH_REQUEST,
                new_callable=AsyncMock,
                side_effect=Exception("Rate limit exceeded"),
            ),
        ):
            result = await action.execute(**execute_kwargs)
        assert result["status"] == "error"


# ============================================================================
# 4. Microsoft Defender for Endpoint
# ============================================================================
class TestDefenderEndpointNotFoundHandling:
    """Defender for Endpoint GetAlertAction 404 handling."""

    PATCH_REQUEST = "analysi.integrations.framework.integrations.defender_endpoint.actions._make_defender_request"
    PATCH_TOKEN = "analysi.integrations.framework.integrations.defender_endpoint.actions._get_access_token"
    CREDS: ClassVar[dict] = {"client_id": "c", "client_secret": "s"}
    SETTINGS: ClassVar[dict] = {"timeout": 5, "tenant_id": "t"}

    @pytest.mark.asyncio
    async def test_404_returns_not_found_success(self):
        action = _make_action(
            DefenderGetAlertAction, credentials=self.CREDS, settings=self.SETTINGS
        )
        with (
            patch(self.PATCH_TOKEN, new_callable=AsyncMock, return_value="fake-token"),
            patch(
                self.PATCH_REQUEST,
                new_callable=AsyncMock,
                side_effect=Exception("Resource not found"),
            ),
        ):
            result = await action.execute(alert_id="test-alert-123")
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_other_errors_still_return_error(self):
        action = _make_action(
            DefenderGetAlertAction, credentials=self.CREDS, settings=self.SETTINGS
        )
        with (
            patch(self.PATCH_TOKEN, new_callable=AsyncMock, return_value="fake-token"),
            patch(
                self.PATCH_REQUEST,
                new_callable=AsyncMock,
                side_effect=Exception("Rate limit exceeded"),
            ),
        ):
            result = await action.execute(alert_id="test-alert-123")
        assert result["status"] == "error"


# ============================================================================
# 5. Duo Security
# ============================================================================
class TestDuoNotFoundHandling:
    """Duo AuthorizeAction 404 handling."""

    CREDS: ClassVar[dict] = {
        "ikey": "test-ikey",
        "skey": "test-skey",
    }
    SETTINGS: ClassVar[dict] = {"timeout": 5, "api_host": "api-test.duosecurity.com"}

    @pytest.mark.asyncio
    async def test_404_returns_not_found_success(self):
        action = _make_action(
            DuoAuthorizeAction, credentials=self.CREDS, settings=self.SETTINGS
        )
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_404_error(),
        ):
            result = await action.execute(user="testuser")
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_other_errors_still_return_error(self):
        action = _make_action(
            DuoAuthorizeAction, credentials=self.CREDS, settings=self.SETTINGS
        )
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_429_error(),
        ):
            result = await action.execute(user="testuser")
        assert result["status"] == "error"


# ============================================================================
# 6. JIRA
# ============================================================================
class TestJiraNotFoundHandling:
    """JIRA action 404 handling."""

    PATCH_TARGET = (
        "analysi.integrations.framework.integrations.jira.actions._make_jira_request"
    )
    CREDS: ClassVar[dict] = {
        "username": "test",
        "password": "test",
    }
    SETTINGS: ClassVar[dict] = {"timeout": 5, "url": "https://jira.example.com"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("action_class", "execute_kwargs"),
        [
            (JiraGetTicketAction, {"ticket_id": "PROJ-123"}),
            (
                JiraCreateTicketAction,
                {"summary": "Test", "project_key": "PROJ", "issue_type": "Bug"},
            ),
            (JiraListProjectsAction, {}),
            (JiraSearchUsersAction, {"query": "test"}),
        ],
        ids=["get_ticket", "create_ticket", "list_projects", "search_users"],
    )
    async def test_404_returns_not_found_success(self, action_class, execute_kwargs):
        action = _make_action(
            action_class, credentials=self.CREDS, settings=self.SETTINGS
        )
        with patch(
            self.PATCH_TARGET,
            new_callable=AsyncMock,
            side_effect=Exception("Resource not found"),
        ):
            result = await action.execute(**execute_kwargs)
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("action_class", "execute_kwargs"),
        [
            (JiraGetTicketAction, {"ticket_id": "PROJ-123"}),
            (
                JiraCreateTicketAction,
                {"summary": "Test", "project_key": "PROJ", "issue_type": "Bug"},
            ),
            (JiraListProjectsAction, {}),
            (JiraSearchUsersAction, {"query": "test"}),
        ],
        ids=["get_ticket", "create_ticket", "list_projects", "search_users"],
    )
    async def test_other_errors_still_return_error(self, action_class, execute_kwargs):
        action = _make_action(
            action_class, credentials=self.CREDS, settings=self.SETTINGS
        )
        with patch(
            self.PATCH_TARGET,
            new_callable=AsyncMock,
            side_effect=Exception("Rate limit exceeded"),
        ):
            result = await action.execute(**execute_kwargs)
        assert result["status"] == "error"


# ============================================================================
# 7. MaxMind
# ============================================================================
class TestMaxmindNotFoundHandling:
    """MaxMind GeolocateIpAction 404 handling."""

    CREDS: ClassVar[dict] = {"license_key": "test"}
    SETTINGS: ClassVar[dict] = {"timeout": 5, "account_id": "test"}

    @pytest.mark.asyncio
    async def test_404_returns_not_found_success(self):
        action = _make_action(
            MaxmindGeolocateIpAction, credentials=self.CREDS, settings=self.SETTINGS
        )
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_404_error(),
        ):
            result = await action.execute(ip="192.168.1.1")
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_other_errors_still_return_error(self):
        action = _make_action(
            MaxmindGeolocateIpAction, credentials=self.CREDS, settings=self.SETTINGS
        )
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_429_error(),
        ):
            result = await action.execute(ip="192.168.1.1")
        assert result["status"] == "error"


# ============================================================================
# 8. NIST NVD
# ============================================================================
class TestNistNvdNotFoundHandling:
    """NIST NVD CveLookupAction 404 handling."""

    CREDS: ClassVar[dict] = {"api_key": "test-key"}
    SETTINGS: ClassVar[dict] = {"timeout": 5}

    @pytest.mark.asyncio
    async def test_404_returns_not_found_success(self):
        action = _make_action(
            NistCveLookupAction, credentials=self.CREDS, settings=self.SETTINGS
        )
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_404_error(),
        ):
            result = await action.execute(cve="CVE-2099-99999")
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_other_errors_still_return_error(self):
        action = _make_action(
            NistCveLookupAction, credentials=self.CREDS, settings=self.SETTINGS
        )
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_429_error(),
        ):
            result = await action.execute(cve="CVE-2099-99999")
        assert result["status"] == "error"


# ============================================================================
# 9. SentinelOne
# ============================================================================
class TestSentinelOneNotFoundHandling:
    """SentinelOne representative lookup action 404 handling."""

    CREDS: ClassVar[dict] = {"api_token": "test-token"}
    SETTINGS: ClassVar[dict] = {
        "timeout": 5,
        "console_url": "https://test.sentinelone.net",
    }

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("action_class", "execute_kwargs"),
        [
            (S1GetThreatInfoAction, {"s1_threat_id": "test-threat-123"}),
            (S1HashReputationAction, {"hash": "d41d8cd98f00b204e9800998ecf8427e"}),
        ],
        ids=["get_threat_info", "hash_reputation"],
    )
    async def test_404_returns_not_found_success(self, action_class, execute_kwargs):
        action = _make_action(
            action_class, credentials=self.CREDS, settings=self.SETTINGS
        )
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_404_error(),
        ):
            result = await action.execute(**execute_kwargs)
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("action_class", "execute_kwargs"),
        [
            (S1GetThreatInfoAction, {"s1_threat_id": "test-threat-123"}),
            (S1HashReputationAction, {"hash": "d41d8cd98f00b204e9800998ecf8427e"}),
        ],
        ids=["get_threat_info", "hash_reputation"],
    )
    async def test_other_errors_still_return_error(self, action_class, execute_kwargs):
        action = _make_action(
            action_class, credentials=self.CREDS, settings=self.SETTINGS
        )
        with patch.object(
            action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=_make_429_error(),
        ):
            result = await action.execute(**execute_kwargs)
        assert result["status"] == "error"


# ============================================================================
# 10. Shodan
# ============================================================================
class TestShodanNotFoundHandling:
    """Shodan lookup action 404 handling."""

    PATCH_TARGET = "analysi.integrations.framework.integrations.shodan.actions._make_shodan_request"
    CREDS: ClassVar[dict] = {"api_key": "test-key"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("action_class", "execute_kwargs"),
        [
            (ShodanIpLookupAction, {"ip": "192.168.1.1"}),
            (ShodanDomainLookupAction, {"domain": "example.com"}),
        ],
        ids=["ip_lookup", "domain_lookup"],
    )
    async def test_404_returns_not_found_success(self, action_class, execute_kwargs):
        action = _make_action(action_class, credentials=self.CREDS)
        with patch(
            self.PATCH_TARGET,
            new_callable=AsyncMock,
            side_effect=Exception("Resource not found"),
        ):
            result = await action.execute(**execute_kwargs)
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("action_class", "execute_kwargs"),
        [
            (ShodanIpLookupAction, {"ip": "192.168.1.1"}),
            (ShodanDomainLookupAction, {"domain": "example.com"}),
        ],
        ids=["ip_lookup", "domain_lookup"],
    )
    async def test_other_errors_still_return_error(self, action_class, execute_kwargs):
        action = _make_action(action_class, credentials=self.CREDS)
        with patch(
            self.PATCH_TARGET,
            new_callable=AsyncMock,
            side_effect=Exception("Rate limit exceeded"),
        ):
            result = await action.execute(**execute_kwargs)
        assert result["status"] == "error"


# ============================================================================
# 11. Tenable
# ============================================================================
class TestTenableNotFoundHandling:
    """Tenable action 404 handling."""

    PATCH_TARGET = "analysi.integrations.framework.integrations.tenable.actions._make_tenable_request"
    CREDS: ClassVar[dict] = {"access_key": "test", "secret_key": "test"}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("action_class", "execute_kwargs"),
        [
            (TenableListScansAction, {}),
            (TenableDeleteScanAction, {"scan_id": "123"}),
        ],
        ids=["list_scans", "delete_scan"],
    )
    async def test_404_returns_not_found_success(self, action_class, execute_kwargs):
        action = _make_action(action_class, credentials=self.CREDS)
        with patch(
            self.PATCH_TARGET,
            new_callable=AsyncMock,
            side_effect=Exception("Resource not found"),
        ):
            result = await action.execute(**execute_kwargs)
        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("action_class", "execute_kwargs"),
        [
            (TenableListScansAction, {}),
            (TenableDeleteScanAction, {"scan_id": "123"}),
        ],
        ids=["list_scans", "delete_scan"],
    )
    async def test_other_errors_still_return_error(self, action_class, execute_kwargs):
        action = _make_action(action_class, credentials=self.CREDS)
        with patch(
            self.PATCH_TARGET,
            new_callable=AsyncMock,
            side_effect=Exception("Rate limit exceeded"),
        ):
            result = await action.execute(**execute_kwargs)
        assert result["status"] == "error"
