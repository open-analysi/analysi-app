"""Unit tests for Splunk Notable normalization using demo scenarios.

Tests extraction accuracy for the 9 demo scenarios used in production demos.
Each test validates that critical fields are correctly extracted.
"""

import json
from pathlib import Path

import pytest

from alert_normalizer.splunk import SplunkNotableNormalizer

# Path to notable fixtures (in same directory)
NOTABLES_PATH = Path(__file__).parent / "notables"


@pytest.fixture
def normalizer():
    """Create a SplunkNotableNormalizer instance."""
    return SplunkNotableNormalizer()


def load_notable(scenario_name: str) -> dict:
    """Load a notable from local fixtures."""
    path = NOTABLES_PATH / f"{scenario_name}.json"
    with open(path) as f:
        return json.load(f)


class TestPowershellExploit:
    """Test 01-powershell-exploit notable extraction."""

    @pytest.fixture
    def notable(self):
        return load_notable("01-powershell-exploit")

    def test_title_extraction(self, normalizer, notable):
        """Title should contain CVE-2022-41082."""
        result = normalizer.to_alertcreate(notable)
        assert "CVE-2022-41082" in result.title
        assert "PowerShell" in result.title

    def test_severity(self, normalizer, notable):
        """Should be high severity."""
        result = normalizer.to_alertcreate(notable)
        assert result.severity.value == "high"

    def test_network_info(self, normalizer, notable):
        """Network info should have correct IPs."""
        result = normalizer.to_alertcreate(notable)
        assert result.network_info is not None
        assert result.network_info.src_ip == "58.237.200.6"
        assert result.network_info.dest_ip == "172.16.20.8"  # Exchange Server 2
        # Port is inferred from HTTPS URL (443), but may not be in network_info
        # if not explicitly in the notable

    def test_web_info(self, normalizer, notable):
        """Web info should capture the malicious path."""
        result = normalizer.to_alertcreate(notable)
        assert result.web_info is not None
        # This is a path, not a full URL, so it's stored in uri_path
        assert "powershell" in result.web_info.uri_path.lower()
        assert result.web_info.http_method == "GET"

    def test_device_action(self, normalizer, notable):
        """Device action should be blocked."""
        result = normalizer.to_alertcreate(notable)
        assert result.device_action == "blocked"

    def test_cve_extraction(self, normalizer, notable):
        """CVE info should be extracted."""
        result = normalizer.to_alertcreate(notable)
        assert result.cve_info is not None
        assert (
            "CVE-2022-41082" in (result.cve_info.ids or [])
            or result.cve_info.id == "CVE-2022-41082"
        )

    def test_risk_entity(self, normalizer, notable):
        """Risk entity should be the destination host."""
        result = normalizer.to_alertcreate(notable)
        assert result.primary_risk_entity_value is not None

    def test_iocs_extracted(self, normalizer, notable):
        """Should extract source IP as IOC."""
        result = normalizer.to_alertcreate(notable)
        assert result.iocs is not None
        assert len(result.iocs) > 0
        ioc_values = [ioc.value for ioc in result.iocs]
        assert "58.237.200.6" in ioc_values


class TestSqlInjection:
    """Test 02-sql-injection-web notable extraction."""

    @pytest.fixture
    def notable(self):
        return load_notable("02-sql-injection-web")

    def test_title_extraction(self, normalizer, notable):
        """Title should indicate SQL injection."""
        result = normalizer.to_alertcreate(notable)
        assert "SQL" in result.title.upper() or "Injection" in result.title

    def test_severity(self, normalizer, notable):
        """Should be high severity."""
        result = normalizer.to_alertcreate(notable)
        assert result.severity.value == "high"

    def test_network_info(self, normalizer, notable):
        """Network info should capture attack source."""
        result = normalizer.to_alertcreate(notable)
        assert result.network_info is not None
        assert result.network_info.src_ip == "167.99.169.17"
        assert result.network_info.dest_hostname == "WebServer1001"

    def test_web_info_url(self, normalizer, notable):
        """Web info should capture SQL injection payload in URL."""
        result = normalizer.to_alertcreate(notable)
        assert result.web_info is not None
        # URL should contain SQL injection patterns
        url_lower = result.web_info.url.lower() if result.web_info.url else ""
        assert "select" in url_lower or "1=1" in url_lower or "or" in url_lower

    def test_device_action_allowed(self, normalizer, notable):
        """Device action should be allowed (attack got through)."""
        result = normalizer.to_alertcreate(notable)
        assert result.device_action == "allowed"

    def test_iocs_include_attacker_ip(self, normalizer, notable):
        """IOCs should include the attacking IP."""
        result = normalizer.to_alertcreate(notable)
        assert result.iocs is not None
        ioc_values = [ioc.value for ioc in result.iocs]
        assert "167.99.169.17" in ioc_values


class TestXssAttack:
    """Test 03-xss-web-attack notable extraction."""

    @pytest.fixture
    def notable(self):
        return load_notable("03-xss-web-attack")

    def test_title_extraction(self, normalizer, notable):
        """Title should indicate XSS/JavaScript attack."""
        result = normalizer.to_alertcreate(notable)
        # Splunk uses "Javascript Code Detected" instead of "XSS"
        assert "JAVASCRIPT" in result.title.upper() or "XSS" in result.title.upper()

    def test_severity_medium(self, normalizer, notable):
        """Should be medium severity."""
        result = normalizer.to_alertcreate(notable)
        assert result.severity.value == "medium"

    def test_network_info(self, normalizer, notable):
        """Network info should capture attack source."""
        result = normalizer.to_alertcreate(notable)
        assert result.network_info is not None
        assert result.network_info.src_ip == "112.85.42.13"
        assert result.network_info.dest_port == 443

    def test_web_info_xss_payload(self, normalizer, notable):
        """Web info should capture XSS payload."""
        result = normalizer.to_alertcreate(notable)
        assert result.web_info is not None
        url = result.web_info.url or ""
        # XSS payloads typically contain script tags or event handlers
        assert "<script" in url.lower() or "alert(" in url.lower() or "%3Cscript" in url

    def test_iocs_extracted(self, normalizer, notable):
        """Should extract attacker IP as IOC."""
        result = normalizer.to_alertcreate(notable)
        assert result.iocs is not None
        ioc_values = [ioc.value for ioc in result.iocs]
        assert "112.85.42.13" in ioc_values


class TestLsCommand:
    """Test 04-ls-command-false-positive notable extraction."""

    @pytest.fixture
    def notable(self):
        return load_notable("04-ls-command-false-positive")

    def test_title_extraction(self, normalizer, notable):
        """Title should indicate command in URL."""
        result = normalizer.to_alertcreate(notable)
        assert "Command" in result.title or "URL" in result.title

    def test_severity(self, normalizer, notable):
        """Should be medium or high severity."""
        result = normalizer.to_alertcreate(notable)
        assert result.severity.value in ["medium", "high"]

    def test_internal_source_ip(self, normalizer, notable):
        """Source IP should be internal (this is a false positive)."""
        result = normalizer.to_alertcreate(notable)
        assert result.network_info is not None
        # 172.16.x.x is internal
        assert result.network_info.src_ip.startswith("172.16.")

    def test_web_info_url(self, normalizer, notable):
        """Web info should capture the URL with 'ls' in path."""
        result = normalizer.to_alertcreate(notable)
        assert result.web_info is not None
        # URL contains 'skills' which triggered false positive on 'ls'
        assert "skill" in result.web_info.url.lower()

    def test_iocs_exclude_internal_ip(self, normalizer, notable):
        """IOCs should NOT include internal IPs (they're assets, not threats)."""
        result = normalizer.to_alertcreate(notable)
        assert result.iocs is not None
        ioc_values = [ioc.value for ioc in result.iocs]
        # Internal IP should NOT be in IOCs (it's our asset, not threat)
        assert "172.16.17.46" not in ioc_values
        # Should have the external IP and URL
        assert "188.114.96.15" in ioc_values
        has_url_ioc = any("mycorp.io" in v for v in ioc_values)
        assert has_url_ioc


class TestWhoamiCommand:
    """Test 05-whoami-command-injection notable extraction."""

    @pytest.fixture
    def notable(self):
        return load_notable("05-whoami-command-injection")

    def test_title_extraction(self, normalizer, notable):
        """Title should indicate command injection."""
        result = normalizer.to_alertcreate(notable)
        assert "Command" in result.title or "whoami" in result.title.lower()

    def test_severity_high(self, normalizer, notable):
        """Should be high severity."""
        result = normalizer.to_alertcreate(notable)
        assert result.severity.value == "high"

    def test_network_info(self, normalizer, notable):
        """Network info should capture external attacker."""
        result = normalizer.to_alertcreate(notable)
        assert result.network_info is not None
        assert result.network_info.src_ip == "61.177.172.87"

    def test_web_info_post_method(self, normalizer, notable):
        """Should be a POST request (command injection via form)."""
        result = normalizer.to_alertcreate(notable)
        assert result.web_info is not None
        assert result.web_info.http_method == "POST"

    def test_iocs_extracted(self, normalizer, notable):
        """Should extract attacker IP as IOC."""
        result = normalizer.to_alertcreate(notable)
        assert result.iocs is not None
        ioc_values = [ioc.value for ioc in result.iocs]
        assert "61.177.172.87" in ioc_values


class TestIdorAttack:
    """Test 06-idor-attack notable extraction."""

    @pytest.fixture
    def notable(self):
        return load_notable("06-idor-attack")

    def test_title_extraction(self, normalizer, notable):
        """Title should indicate IDOR or access control issue."""
        result = normalizer.to_alertcreate(notable)
        assert "IDOR" in result.title.upper() or "Access" in result.title

    def test_severity_high(self, normalizer, notable):
        """Should be high severity."""
        result = normalizer.to_alertcreate(notable)
        assert result.severity.value == "high"

    def test_network_info(self, normalizer, notable):
        """Network info should capture attacker."""
        result = normalizer.to_alertcreate(notable)
        assert result.network_info is not None
        assert result.network_info.src_ip == "134.209.118.137"

    def test_web_info(self, normalizer, notable):
        """Web info should capture the request."""
        result = normalizer.to_alertcreate(notable)
        assert result.web_info is not None
        assert result.web_info.http_method == "POST"

    def test_iocs_extracted(self, normalizer, notable):
        """Should extract attacker IP as IOC."""
        result = normalizer.to_alertcreate(notable)
        assert result.iocs is not None
        ioc_values = [ioc.value for ioc in result.iocs]
        assert "134.209.118.137" in ioc_values


class TestLfiAttack:
    """Test 07-lfi-attack-passwd notable extraction."""

    @pytest.fixture
    def notable(self):
        return load_notable("07-lfi-attack-passwd")

    def test_title_extraction(self, normalizer, notable):
        """Title should indicate LFI or file inclusion."""
        result = normalizer.to_alertcreate(notable)
        title_upper = result.title.upper()
        assert (
            "LFI" in title_upper or "FILE" in title_upper or "INCLUSION" in title_upper
        )

    def test_severity_high(self, normalizer, notable):
        """Should be high severity."""
        result = normalizer.to_alertcreate(notable)
        assert result.severity.value == "high"

    def test_web_info_lfi_payload(self, normalizer, notable):
        """Web info should capture LFI payload (../../etc/passwd)."""
        result = normalizer.to_alertcreate(notable)
        assert result.web_info is not None
        url = result.web_info.url or ""
        # LFI patterns
        assert "../" in url or "etc/passwd" in url or "%2e%2e" in url.lower()

    def test_iocs_extracted(self, normalizer, notable):
        """Should extract relevant IOCs."""
        result = normalizer.to_alertcreate(notable)
        assert result.iocs is not None
        assert len(result.iocs) > 0


class TestSharepointCve:
    """Test 08-sharepoint-cve-exploit notable extraction."""

    @pytest.fixture
    def notable(self):
        return load_notable("08-sharepoint-cve-exploit")

    def test_title_extraction(self, normalizer, notable):
        """Title should indicate SharePoint or CVE-2023-29357."""
        result = normalizer.to_alertcreate(notable)
        assert "SharePoint" in result.title or "CVE-2023-29357" in result.title

    def test_severity_critical(self, normalizer, notable):
        """Should be critical severity."""
        result = normalizer.to_alertcreate(notable)
        assert result.severity.value == "critical"

    def test_cve_extraction(self, normalizer, notable):
        """CVE-2023-29357 should be extracted."""
        result = normalizer.to_alertcreate(notable)
        assert result.cve_info is not None
        cve_ids = result.cve_info.ids or []
        if result.cve_info.id:
            cve_ids.append(result.cve_info.id)
        assert any("CVE-2023-29357" in cve for cve in cve_ids)

    def test_user_agent_python_requests(self, normalizer, notable):
        """User agent should be python-requests (scanner indicator)."""
        result = normalizer.to_alertcreate(notable)
        assert result.web_info is not None
        ua = result.web_info.user_agent or ""
        assert "python-requests" in ua.lower()

    def test_iocs_include_scanner_ua(self, normalizer, notable):
        """IOCs should include the suspicious user agent."""
        result = normalizer.to_alertcreate(notable)
        assert result.iocs is not None
        ioc_values = [ioc.value.lower() for ioc in result.iocs]
        # The python-requests user agent should be captured as IOC
        has_ua_ioc = any("python-requests" in v for v in ioc_values)
        assert has_ua_ioc


class TestConfluenceCve:
    """Test 09-confluence-cve-exploit notable extraction."""

    @pytest.fixture
    def notable(self):
        return load_notable("09-confluence-cve-exploit")

    def test_title_extraction(self, normalizer, notable):
        """Title should indicate Confluence or CVE-2023-22515."""
        result = normalizer.to_alertcreate(notable)
        assert "Confluence" in result.title or "CVE-2023-22515" in result.title

    def test_severity_high(self, normalizer, notable):
        """Should be high severity (Splunk Notable says 'high' not 'critical')."""
        result = normalizer.to_alertcreate(notable)
        assert result.severity.value == "high"

    def test_cve_extraction(self, normalizer, notable):
        """CVE-2023-22515 should be extracted."""
        result = normalizer.to_alertcreate(notable)
        assert result.cve_info is not None
        cve_ids = result.cve_info.ids or []
        if result.cve_info.id:
            cve_ids.append(result.cve_info.id)
        assert any("CVE-2023-22515" in cve for cve in cve_ids)

    def test_user_agent_curl(self, normalizer, notable):
        """User agent should be curl (manual attack indicator)."""
        result = normalizer.to_alertcreate(notable)
        assert result.web_info is not None
        ua = result.web_info.user_agent or ""
        assert "curl" in ua.lower()

    def test_iocs_extracted(self, normalizer, notable):
        """Should extract relevant IOCs."""
        result = normalizer.to_alertcreate(notable)
        assert result.iocs is not None
        assert len(result.iocs) > 0
