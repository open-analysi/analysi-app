"""Unit tests for Kaspersky Threat Intelligence Portal integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.kasperskyti.actions import (
    DomainReputationAction,
    FileReputationAction,
    GetAptReportsAction,
    GetIndicatorDetailsAction,
    HealthCheckAction,
    IpReputationAction,
    UrlReputationAction,
    _detect_indicator_type,
    _extract_summary,
    _prepare_url_indicator,
)
from analysi.integrations.framework.integrations.kasperskyti.constants import (
    ENDPOINT_DOMAIN,
    ENDPOINT_HASH,
    ENDPOINT_IP,
    ENDPOINT_URL,
    ZONE_GREY,
)

# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================


class TestPrepareUrlIndicator:
    """Test URL indicator normalization."""

    def test_strips_http_protocol(self):
        result = _prepare_url_indicator("http://example.com/path")
        assert "http" not in result
        assert "example.com" in result

    def test_strips_https_protocol(self):
        result = _prepare_url_indicator("https://example.com/path")
        assert "https" not in result

    def test_strips_www_prefix(self):
        result = _prepare_url_indicator("http://www.example.com/path")
        assert "www." not in result

    def test_strips_trailing_slash(self):
        result = _prepare_url_indicator("http://example.com/")
        assert not result.endswith("/")
        assert not result.endswith("%2F")

    def test_strips_fragment(self):
        result = _prepare_url_indicator("http://example.com/path#section")
        assert "#section" not in result
        assert "%23section" not in result

    def test_encodes_special_characters(self):
        result = _prepare_url_indicator("http://example.com/path?q=hello&x=1")
        # The path and query should be URL-encoded
        assert "example.com" in result

    def test_strips_embedded_credentials(self):
        result = _prepare_url_indicator("http://user:pass@example.com/path")
        assert "user" not in result
        assert "pass" not in result

    def test_strips_port(self):
        result = _prepare_url_indicator("http://example.com:8080/path")
        assert "8080" not in result


class TestDetectIndicatorType:
    """Test indicator type detection."""

    def test_detects_ipv4(self):
        assert _detect_indicator_type("192.168.1.1") == ENDPOINT_IP

    def test_detects_md5_hash(self):
        assert (
            _detect_indicator_type("d41d8cd98f00b204e9800998ecf8427e") == ENDPOINT_HASH
        )

    def test_detects_sha256_hash(self):
        sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert _detect_indicator_type(sha256) == ENDPOINT_HASH

    def test_detects_url(self):
        assert _detect_indicator_type("http://example.com/malware") == ENDPOINT_URL
        assert _detect_indicator_type("https://evil.com") == ENDPOINT_URL

    def test_defaults_to_domain(self):
        assert _detect_indicator_type("example.com") == ENDPOINT_DOMAIN
        assert _detect_indicator_type("malware.evil.org") == ENDPOINT_DOMAIN


class TestExtractSummary:
    """Test summary extraction from API responses."""

    def test_empty_response_returns_defaults(self):
        summary = _extract_summary({})
        assert summary["found"] is False
        assert summary["zone"] == ZONE_GREY
        assert summary["categories"] == []
        assert summary["threat_score"] == 0
        assert summary["apt_related"] is False

    def test_red_zone_sets_found_true(self):
        summary = _extract_summary({"Zone": "Red"})
        assert summary["found"] is True
        assert summary["zone"] == "Red"

    def test_grey_zone_keeps_found_false(self):
        summary = _extract_summary({"Zone": "Grey"})
        assert summary["found"] is False
        assert summary["zone"] == "Grey"

    def test_domain_info_extraction(self):
        response = {
            "Zone": "Orange",
            "DomainGeneralInfo": {
                "Domain": "evil.com",
                "HitsCount": 42,
                "Categories": ["Phishing"],
                "HasApt": True,
                "RelatedAptReports": [{"Title": "APT29 Campaign", "Id": "apt-123"}],
            },
        }
        summary = _extract_summary(response)
        assert summary["found"] is True
        assert summary["hits_count"] == 42
        assert summary["categories"] == ["Phishing"]
        assert summary["apt_related"] is True
        assert summary["apt_report"] == "APT29 Campaign"
        assert summary["apt_report_id"] == "apt-123"

    def test_ip_info_with_threat_score(self):
        response = {
            "Zone": "Red",
            "IpGeneralInfo": {
                "Ip": "192.168.1.1",
                "HitsCount": 100,
                "Categories": ["Botnet"],
                "HasApt": False,
                "ThreatScore": 85,
                "RelatedAptReports": [],
            },
        }
        summary = _extract_summary(response)
        assert summary["threat_score"] == 85
        assert summary["categories"] == ["Botnet"]
        assert summary["apt_related"] is False

    def test_file_info_with_detections(self):
        response = {
            "Zone": "Red",
            "FileGeneralInfo": {
                "Md5": "abc123",
                "Sha1": "def456",
                "Sha256": "ghi789",
                "HitsCount": 50,
                "HasApt": True,
                "RelatedAptReports": [{"Title": "Lazarus Group", "Id": "apt-456"}],
            },
            "DetectionsInfo": [
                {"DetectionName": "Trojan.Win32.Agent"},
                {"DetectionName": "Backdoor.Win32.Poison"},
            ],
        }
        summary = _extract_summary(response)
        assert summary["hash"] == "abc123"
        assert summary["sha1"] == "def456"
        assert summary["sha256"] == "ghi789"
        assert len(summary["categories"]) == 2
        assert "Trojan.Win32.Agent" in summary["categories"]
        assert summary["apt_related"] is True
        assert summary["apt_report"] == "Lazarus Group"

    def test_url_info_extraction(self):
        response = {
            "Zone": "Orange",
            "UrlGeneralInfo": {
                "Url": "http://evil.com/phish",
                "Categories": ["Phishing", "Malware"],
                "HasApt": False,
                "RelatedAptReports": [],
            },
        }
        summary = _extract_summary(response)
        assert summary["categories"] == ["Phishing", "Malware"]
        assert summary["apt_related"] is False

    def test_license_info_extraction(self):
        response = {
            "Zone": "Grey",
            "LicenseInfo": {
                "DayRequests": 42,
                "DayQuota": 1000,
            },
        }
        summary = _extract_summary(response)
        assert summary["day_requests"] == 42
        assert summary["day_quota"] == 1000

    def test_apt_publication_data(self):
        response = {
            "return_data": {
                "name": "APT29 Cozy Bear",
                "id": "pub-001",
                "desc": "Russian state-sponsored group",
                "tags_geo": "Russia",
                "tags_industry": "Government",
                "tags_actors": "APT29",
            }
        }
        summary = _extract_summary(response)
        assert summary["apt_report"] == "APT29 Cozy Bear"
        assert (
            summary["apt_report_url"]
            == "https://tip.kaspersky.com/reporting?id=pub-001"
        )
        assert summary["apt_report_desc"] == "Russian state-sponsored group"
        assert summary["apt_report_geo"] == "Russia"
        assert summary["apt_report_industry"] == "Government"
        assert summary["apt_report_actors"] == "APT29"


# ============================================================================
# HEALTH CHECK ACTION
# ============================================================================


class TestHealthCheckAction:
    """Test Kaspersky TIP health check action."""

    @pytest.fixture
    def action(self):
        return HealthCheckAction(
            integration_id="kasperskyti",
            action_id="health_check",
            settings={},
            credentials={"username": "test-user", "password": "test-pass"},
        )

    @pytest.mark.asyncio
    async def test_health_check_success(self, action):
        """Test successful health check returns quota info."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Zone": "Green",
            "LicenseInfo": {"DayRequests": 10, "DayQuota": 1000},
        }

        action.http_request = AsyncMock(return_value=mock_response)
        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert result["data"]["day_quota"] == 1000
        assert result["data"]["day_requests"] == 10
        assert "integration_id" in result
        assert result["integration_id"] == "kasperskyti"

    @pytest.mark.asyncio
    async def test_health_check_missing_credentials(self):
        """Test health check fails with missing credentials."""
        action = HealthCheckAction(
            integration_id="kasperskyti",
            action_id="health_check",
            settings={},
            credentials={},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "credentials" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_health_check_403_access_denied(self, action):
        """Test 403 returns access denied error."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 403
        error = httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_response
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "AuthenticationError"

    @pytest.mark.asyncio
    async def test_health_check_401_invalid_creds(self, action):
        """Test 401 returns invalid credentials error."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401
        error = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "AuthenticationError"

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self, action):
        """Test connection error is handled gracefully."""
        action.http_request = AsyncMock(side_effect=Exception("Connection refused"))

        result = await action.execute()

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_health_check_uses_basic_auth(self, action):
        """Test that HTTP Basic Auth is passed."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Zone": "Grey",
            "LicenseInfo": {"DayRequests": 0, "DayQuota": 100},
        }
        action.http_request = AsyncMock(return_value=mock_response)

        await action.execute()

        call_kwargs = action.http_request.call_args[1]
        assert call_kwargs["auth"] == ("test-user", "test-pass")

    @pytest.mark.asyncio
    async def test_health_check_uses_custom_base_url(self):
        """Test custom base_url from settings is used."""
        action = HealthCheckAction(
            integration_id="kasperskyti",
            action_id="health_check",
            settings={"base_url": "https://custom.tip.kaspersky.com"},
            credentials={"username": "user", "password": "pass"},
        )
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Zone": "Grey",
            "LicenseInfo": {"DayRequests": 0, "DayQuota": 100},
        }
        action.http_request = AsyncMock(return_value=mock_response)

        await action.execute()

        call_kwargs = action.http_request.call_args[1]
        assert "custom.tip.kaspersky.com" in call_kwargs["url"]


# ============================================================================
# DOMAIN REPUTATION ACTION
# ============================================================================


class TestDomainReputationAction:
    """Test domain reputation action."""

    @pytest.fixture
    def action(self):
        return DomainReputationAction(
            integration_id="kasperskyti",
            action_id="domain_reputation",
            settings={},
            credentials={"username": "test-user", "password": "test-pass"},
        )

    @pytest.mark.asyncio
    async def test_domain_reputation_success(self, action):
        """Test successful domain reputation lookup."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Zone": "Red",
            "DomainGeneralInfo": {
                "Domain": "evil.com",
                "HitsCount": 100,
                "Categories": ["Phishing", "Malware"],
                "HasApt": True,
                "RelatedAptReports": [{"Title": "APT29", "Id": "rpt-123"}],
            },
        }
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(domain="evil.com")

        assert result["status"] == "success"
        assert result["data"]["domain"] == "evil.com"
        assert result["data"]["zone"] == "Red"
        assert result["data"]["found"] is True
        assert result["data"]["categories"] == ["Phishing", "Malware"]
        assert result["data"]["apt_related"] is True
        assert result["data"]["apt_report"] == "APT29"
        assert "tip_url" in result["data"]
        assert "full_data" in result["data"]
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_domain_reputation_grey_zone(self, action):
        """Test domain in Grey zone (not found in threat intel)."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Zone": "Grey",
            "DomainGeneralInfo": {
                "Domain": "safe.com",
                "HitsCount": 0,
                "Categories": [],
                "HasApt": False,
                "RelatedAptReports": [],
            },
        }
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(domain="safe.com")

        assert result["status"] == "success"
        assert result["data"]["zone"] == "Grey"
        assert result["data"]["found"] is False

    @pytest.mark.asyncio
    async def test_domain_reputation_missing_param(self, action):
        """Test error when domain parameter is missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "domain" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_domain_reputation_missing_credentials(self):
        """Test error when credentials are missing."""
        action = DomainReputationAction(
            integration_id="kasperskyti",
            action_id="domain_reputation",
            settings={},
            credentials={},
        )

        result = await action.execute(domain="example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_domain_reputation_404_returns_not_found(self, action):
        """Test 404 returns success with not_found=True."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404
        error = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute(domain="nonexistent.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["domain"] == "nonexistent.com"
        assert result["data"]["zone"] == ZONE_GREY

    @pytest.mark.asyncio
    async def test_domain_reputation_400_returns_not_found(self, action):
        """Test 400 returns success with not_found=True (API returns 400 for bad queries)."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 400
        error = httpx.HTTPStatusError(
            "Bad Request", request=MagicMock(), response=mock_response
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute(domain="invalid..domain")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_domain_reputation_403_returns_error(self, action):
        """Test 403 returns access denied error."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 403
        error = httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_response
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute(domain="evil.com")

        assert result["status"] == "error"
        assert result["error_type"] == "AuthenticationError"

    @pytest.mark.asyncio
    async def test_domain_reputation_generic_error(self, action):
        """Test generic exception is handled."""
        action.http_request = AsyncMock(side_effect=Exception("Network error"))

        result = await action.execute(domain="evil.com")

        assert result["status"] == "error"
        assert "Network error" in result["error"]


# ============================================================================
# IP REPUTATION ACTION
# ============================================================================


class TestIpReputationAction:
    """Test IP reputation action."""

    @pytest.fixture
    def action(self):
        return IpReputationAction(
            integration_id="kasperskyti",
            action_id="ip_reputation",
            settings={},
            credentials={"username": "test-user", "password": "test-pass"},
        )

    @pytest.mark.asyncio
    async def test_ip_reputation_success(self, action):
        """Test successful IP reputation lookup."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Zone": "Red",
            "IpGeneralInfo": {
                "Ip": "192.168.1.100",
                "HitsCount": 200,
                "Categories": ["Botnet", "C&C"],
                "HasApt": True,
                "ThreatScore": 90,
                "RelatedAptReports": [{"Title": "Fancy Bear", "Id": "apt-007"}],
            },
        }
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(ip="192.168.1.100")

        assert result["status"] == "success"
        assert result["data"]["ip"] == "192.168.1.100"
        assert result["data"]["zone"] == "Red"
        assert result["data"]["threat_score"] == 90
        assert result["data"]["categories"] == ["Botnet", "C&C"]
        assert result["data"]["apt_related"] is True
        assert result["data"]["apt_report"] == "Fancy Bear"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_ip_reputation_missing_param(self, action):
        """Test error when IP parameter is missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_ip_reputation_missing_credentials(self):
        """Test error when credentials are missing."""
        action = IpReputationAction(
            integration_id="kasperskyti",
            action_id="ip_reputation",
            settings={},
            credentials={},
        )
        result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_ip_reputation_404_returns_not_found(self, action):
        """Test 404 returns success with not_found=True."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404
        error = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute(ip="10.0.0.1")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["ip"] == "10.0.0.1"
        assert result["data"]["threat_score"] == 0

    @pytest.mark.asyncio
    async def test_ip_reputation_generic_error(self, action):
        """Test generic exception handling."""
        action.http_request = AsyncMock(side_effect=Exception("Timeout"))

        result = await action.execute(ip="8.8.8.8")

        assert result["status"] == "error"
        assert "Timeout" in result["error"]


# ============================================================================
# FILE REPUTATION ACTION
# ============================================================================


class TestFileReputationAction:
    """Test file reputation action."""

    @pytest.fixture
    def action(self):
        return FileReputationAction(
            integration_id="kasperskyti",
            action_id="file_reputation",
            settings={},
            credentials={"username": "test-user", "password": "test-pass"},
        )

    @pytest.mark.asyncio
    async def test_file_reputation_success(self, action):
        """Test successful file hash lookup."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Zone": "Red",
            "FileGeneralInfo": {
                "Md5": "abc123def456",
                "Sha1": "sha1hash",
                "Sha256": "sha256hash",
                "HitsCount": 75,
                "HasApt": True,
                "RelatedAptReports": [{"Title": "Equation Group", "Id": "apt-eq"}],
            },
            "DetectionsInfo": [
                {"DetectionName": "Trojan.Win32.Agent"},
                {"DetectionName": "Exploit.PDF.CVE"},
            ],
        }
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(hash="abc123def456")

        assert result["status"] == "success"
        assert result["data"]["hash"] == "abc123def456"
        assert result["data"]["zone"] == "Red"
        assert result["data"]["md5"] == "abc123def456"
        assert result["data"]["sha1"] == "sha1hash"
        assert result["data"]["sha256"] == "sha256hash"
        assert len(result["data"]["categories"]) == 2
        assert result["data"]["apt_related"] is True
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_file_reputation_missing_param(self, action):
        """Test error when hash parameter is missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_file_reputation_missing_credentials(self):
        """Test error when credentials are missing."""
        action = FileReputationAction(
            integration_id="kasperskyti",
            action_id="file_reputation",
            settings={},
            credentials={},
        )
        result = await action.execute(hash="abc123def456")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_file_reputation_404_returns_not_found(self, action):
        """Test 404 returns success with not_found=True."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404
        error = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute(hash="nonexistent_hash")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["hash"] == "nonexistent_hash"

    @pytest.mark.asyncio
    async def test_file_reputation_generic_error(self, action):
        """Test generic exception handling."""
        action.http_request = AsyncMock(side_effect=Exception("Server error"))

        result = await action.execute(hash="abc123")

        assert result["status"] == "error"


# ============================================================================
# URL REPUTATION ACTION
# ============================================================================


class TestUrlReputationAction:
    """Test URL reputation action."""

    @pytest.fixture
    def action(self):
        return UrlReputationAction(
            integration_id="kasperskyti",
            action_id="url_reputation",
            settings={},
            credentials={"username": "test-user", "password": "test-pass"},
        )

    @pytest.mark.asyncio
    async def test_url_reputation_success(self, action):
        """Test successful URL reputation lookup."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Zone": "Red",
            "UrlGeneralInfo": {
                "Url": "http://evil.com/phishing",
                "Categories": ["Phishing"],
                "HasApt": False,
                "RelatedAptReports": [],
            },
        }
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(url="http://evil.com/phishing")

        assert result["status"] == "success"
        assert result["data"]["url"] == "http://evil.com/phishing"
        assert result["data"]["zone"] == "Red"
        assert result["data"]["categories"] == ["Phishing"]
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_url_reputation_missing_param(self, action):
        """Test error when URL parameter is missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_url_reputation_missing_credentials(self):
        """Test error when credentials are missing."""
        action = UrlReputationAction(
            integration_id="kasperskyti",
            action_id="url_reputation",
            settings={},
            credentials={},
        )
        result = await action.execute(url="http://example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_url_reputation_404_returns_not_found(self, action):
        """Test 404 returns success with not_found=True."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404
        error = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute(url="http://unknown.com")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["url"] == "http://unknown.com"

    @pytest.mark.asyncio
    async def test_url_reputation_url_is_prepared(self, action):
        """Test that URLs are normalized before API call."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Zone": "Grey",
            "UrlGeneralInfo": {
                "Url": "evil.com/path",
                "Categories": [],
                "HasApt": False,
                "RelatedAptReports": [],
            },
        }
        action.http_request = AsyncMock(return_value=mock_response)

        await action.execute(url="http://www.evil.com/path")

        # Verify the URL in the API call was normalized (no protocol, no www)
        call_kwargs = action.http_request.call_args[1]
        assert "www." not in call_kwargs["url"]
        assert "http://" not in call_kwargs["url"].split("/api/url/")[1]


# ============================================================================
# GET INDICATOR DETAILS ACTION
# ============================================================================


class TestGetIndicatorDetailsAction:
    """Test get indicator details action."""

    @pytest.fixture
    def action(self):
        return GetIndicatorDetailsAction(
            integration_id="kasperskyti",
            action_id="get_indicator_details",
            settings={"records_count": 10},
            credentials={"username": "test-user", "password": "test-pass"},
        )

    @pytest.mark.asyncio
    async def test_get_indicator_details_ip(self, action):
        """Test indicator details for IP address."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "Zone": "Red",
            "IpGeneralInfo": {
                "Ip": "10.0.0.1",
                "HitsCount": 50,
                "Categories": ["Spam"],
                "HasApt": False,
                "ThreatScore": 40,
                "RelatedAptReports": [],
            },
        }
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(indicator="10.0.0.1")

        assert result["status"] == "success"
        assert result["data"]["indicator"] == "10.0.0.1"
        assert result["data"]["threat_score"] == 40

    @pytest.mark.asyncio
    async def test_get_indicator_details_with_sections(self, action):
        """Test indicator details with custom sections."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"Zone": "Grey"}
        action.http_request = AsyncMock(return_value=mock_response)

        await action.execute(
            indicator="example.com", sections="Zone,DomainGeneralInfo,DomainWhoIsInfo"
        )

        call_kwargs = action.http_request.call_args[1]
        assert "sections=Zone,DomainGeneralInfo,DomainWhoIsInfo" in call_kwargs["url"]

    @pytest.mark.asyncio
    async def test_get_indicator_details_missing_param(self, action):
        """Test error when indicator parameter is missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_get_indicator_details_missing_credentials(self):
        """Test error when credentials are missing."""
        action = GetIndicatorDetailsAction(
            integration_id="kasperskyti",
            action_id="get_indicator_details",
            settings={},
            credentials={},
        )
        result = await action.execute(indicator="example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_get_indicator_details_404_returns_not_found(self, action):
        """Test 404 returns success with not_found=True."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404
        error = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute(indicator="nonexistent.com")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_get_indicator_details_records_count(self, action):
        """Test records_count setting is applied."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"Zone": "Grey"}
        action.http_request = AsyncMock(return_value=mock_response)

        await action.execute(indicator="example.com")

        call_kwargs = action.http_request.call_args[1]
        assert "count=10" in call_kwargs["url"]


# ============================================================================
# GET APT REPORTS ACTION
# ============================================================================


class TestGetAptReportsAction:
    """Test get APT reports action."""

    @pytest.fixture
    def action(self):
        return GetAptReportsAction(
            integration_id="kasperskyti",
            action_id="get_apt_reports",
            settings={},
            credentials={"username": "test-user", "password": "test-pass"},
        )

    @pytest.mark.asyncio
    async def test_get_apt_reports_success(self, action):
        """Test successful APT report retrieval."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "return_data": {
                "name": "APT29 - Cozy Bear",
                "id": "pub-001",
                "desc": "Russian state-sponsored group targeting Western governments",
                "tags_geo": "Russia, Europe",
                "tags_industry": "Government, Defense",
                "tags_actors": "APT29, Cozy Bear",
            }
        }
        action.http_request = AsyncMock(return_value=mock_response)

        result = await action.execute(apt_id="pub-001")

        assert result["status"] == "success"
        assert result["data"]["apt_id"] == "pub-001"
        assert result["data"]["apt_report"] == "APT29 - Cozy Bear"
        assert "Russian state-sponsored" in result["data"]["apt_report_desc"]
        assert result["data"]["apt_report_geo"] == "Russia, Europe"
        assert result["data"]["apt_report_industry"] == "Government, Defense"
        assert result["data"]["apt_report_actors"] == "APT29, Cozy Bear"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_get_apt_reports_missing_param(self, action):
        """Test error when apt_id parameter is missing."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_get_apt_reports_missing_credentials(self):
        """Test error when credentials are missing."""
        action = GetAptReportsAction(
            integration_id="kasperskyti",
            action_id="get_apt_reports",
            settings={},
            credentials={},
        )
        result = await action.execute(apt_id="pub-001")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_get_apt_reports_404_returns_not_found(self, action):
        """Test 404 returns success with not_found=True."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404
        error = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )
        action.http_request = AsyncMock(side_effect=error)

        result = await action.execute(apt_id="nonexistent-pub")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["apt_id"] == "nonexistent-pub"

    @pytest.mark.asyncio
    async def test_get_apt_reports_uses_publications_endpoint(self, action):
        """Test correct API endpoint and params for publications."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "return_data": {
                "name": "Test Report",
                "id": "pub-123",
                "desc": "",
                "tags_geo": "",
                "tags_industry": "",
                "tags_actors": "",
            }
        }
        action.http_request = AsyncMock(return_value=mock_response)

        await action.execute(apt_id="pub-123")

        call_kwargs = action.http_request.call_args[1]
        assert "/api/publications/get_one" in call_kwargs["url"]
        assert call_kwargs["params"]["publication_id"] == "pub-123"
        assert call_kwargs["params"]["include_info"] == "all"

    @pytest.mark.asyncio
    async def test_get_apt_reports_generic_error(self, action):
        """Test generic exception handling."""
        action.http_request = AsyncMock(side_effect=Exception("Server Error"))

        result = await action.execute(apt_id="pub-001")

        assert result["status"] == "error"
        assert "Server Error" in result["error"]
