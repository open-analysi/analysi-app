"""Comprehensive OCSF field mapping tests for SplunkOCSFNormalizer.

Ported from the NAS-era test files, adapted to verify that each Splunk
Notable input field maps to the correct OCSF Detection Finding field.

Test origins:
- test_splunk_normalizer_enhanced.py  -> TestDispositionMapping, TestWebInfoMapping,
    TestProcessInfoMapping, TestCVEMapping, TestOtherActivitiesMapping,
    TestNetworkInfoMapping, TestSourceCategoryMapping, TestComprehensiveFieldMapping
- test_splunk_normalizer_lists.py     -> TestEntityListMapping, TestIOCListMapping,
    TestDeduplication, TestIPClassification, TestHashTypeMapping,
    TestUserAgentMapping
- test_splunk_normalizer_real_notables.py -> TestRealFixtureFieldMappings
- test_splunk_normalizer_roundtrip.py    -> TestOCSFEquivalence

Project Skaros -- NAS-to-OCSF field mapping validation.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from alert_normalizer.splunk_ocsf import (
    IOC_TYPE_TO_OBSERVABLE,
    SplunkOCSFNormalizer,
    _build_attack_entry,
    _collect_technique_ids,
)

NOTABLES_DIR = Path(__file__).parent.parent.parent / "alert_normalizer" / "notables"


@pytest.fixture
def normalizer():
    return SplunkOCSFNormalizer()


def _load_fixture(name: str) -> dict[str, Any]:
    with open(NOTABLES_DIR / name) as f:
        return json.load(f)


def _make_notable(**overrides: Any) -> dict[str, Any]:
    """Create a minimal notable dict with overrides."""
    base = {
        "rule_name": "Test Alert",
        "_time": "2025-01-15T10:00:00Z",
        "severity": "high",
    }
    base.update(overrides)
    return base


# ======================================================================
# Ported from test_splunk_normalizer_enhanced.py
# ======================================================================


class TestDispositionMapping:
    """NAS device_action -> OCSF disposition_id / disposition."""

    @pytest.mark.parametrize(
        ("action", "expected_id", "expected_label"),
        [
            ("Allowed", 1, "Allowed"),
            ("Blocked", 2, "Blocked"),
            ("Detected", 15, "Detected"),
            ("blocked", 2, "Blocked"),
            ("ALLOW", 1, "Allowed"),
            ("deny", 2, "Blocked"),
            ("quarantined", 3, "Quarantined"),
        ],
    )
    def test_device_action_to_disposition(
        self, normalizer, action, expected_id, expected_label
    ):
        """device_action value maps to correct OCSF disposition_id and label."""
        notable = _make_notable(action=action)
        ocsf = normalizer.to_ocsf(notable)
        assert ocsf.get("disposition_id") == expected_id
        assert ocsf.get("disposition") == expected_label

    def test_no_action_means_no_disposition(self, normalizer):
        """When action is None, disposition should be absent."""
        notable = _make_notable()
        ocsf = normalizer.to_ocsf(notable)
        assert "disposition_id" not in ocsf
        assert "disposition" not in ocsf


class TestSourceEventIdMapping:
    """NAS source_event_id -> OCSF metadata.event_code."""

    def test_event_id_in_metadata(self, normalizer):
        notable = _make_notable(
            event_id="82e4fa80-9a68@@notable@@82e4fa809a6840719b7cf53840132da8"
        )
        ocsf = normalizer.to_ocsf(notable)
        assert ocsf["metadata"]["event_code"] == notable["event_id"]


class TestWebInfoMapping:
    """NAS web_info -> OCSF evidences[].url + http_request."""

    def test_url_in_evidences(self, normalizer):
        notable = _make_notable(
            requested_url="https://example.com/search?q=' OR 1=1--",
            http_method="GET",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            http_status="200",
        )
        ocsf = normalizer.to_ocsf(notable)
        ev = ocsf["evidences"][0]
        assert "example.com/search" in ev["url"]["url_string"]
        assert ev["http_request"]["http_method"] == "GET"
        assert ev["http_request"]["user_agent"] == notable["user_agent"]

    def test_url_path_and_query_parsed(self, normalizer):
        """Full URL should have path and query_string extracted."""
        notable = _make_notable(
            requested_url="https://example.com/search?q=test&page=1",
        )
        ocsf = normalizer.to_ocsf(notable)
        url_obj = ocsf["evidences"][0]["url"]
        assert url_obj["url_string"] == "https://example.com/search?q=test&page=1"
        assert url_obj["path"] == "/search"
        assert url_obj["query_string"] == "q=test&page=1"

    def test_path_only_url(self, normalizer):
        """Path-only URL (no scheme) should still extract path and query."""
        notable = _make_notable(
            requested_url="/api/users?id=123",
            http_method="GET",
        )
        ocsf = normalizer.to_ocsf(notable)
        url_obj = ocsf["evidences"][0]["url"]
        assert url_obj["path"] == "/api/users"
        assert url_obj["query_string"] == "id=123"

    def test_path_only_no_query(self, normalizer):
        """Path-only URL with no query string."""
        notable = _make_notable(
            requested_url="/api/users",
            http_method="GET",
        )
        ocsf = normalizer.to_ocsf(notable)
        url_obj = ocsf["evidences"][0]["url"]
        assert url_obj["path"] == "/api/users"
        assert "query_string" not in url_obj


class TestProcessInfoMapping:
    """NAS process_info -> OCSF evidences[].process."""

    def test_process_fields_in_evidence(self, normalizer):
        notable = _make_notable(
            process="powershell.exe -encodedCommand SGVsbG8gV29ybGQ=",
            process_name="powershell.exe",
            process_path="C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
            parent_process="cmd.exe",
            parent_process_path="C:\\Windows\\System32\\cmd.exe",
            process_id="1234",
            parent_process_id="5678",
        )
        ocsf = normalizer.to_ocsf(notable)
        proc = ocsf["evidences"][0]["process"]
        assert proc["name"] == "powershell.exe"
        assert "encodedCommand" in proc["cmd_line"]
        assert proc["pid"] == 1234
        assert proc["parent_process"].get("name") or proc["parent_process"].get(
            "cmd_line"
        )
        assert proc["parent_process"]["pid"] == 5678


class TestCVEMapping:
    """NAS cve_info -> OCSF vulnerabilities[]."""

    def test_cve_from_title(self, normalizer):
        notable = _make_notable(
            rule_name="PowerShell Found in URL - CVE-2022-41082 Exploitation",
            rule_title="Possible CVE-2022-41082 Exchange Exploitation",
        )
        ocsf = normalizer.to_ocsf(notable)
        vulns = ocsf.get("vulnerabilities", [])
        cve_uids = [v["cve"]["uid"] for v in vulns]
        assert "CVE-2022-41082" in cve_uids

    def test_multiple_cves(self, normalizer):
        notable = _make_notable(
            rule_name="ProxyShell Attack Chain",
            rule_description="Exploitation of CVE-2021-34473, CVE-2021-34523, and CVE-2021-31207",
        )
        ocsf = normalizer.to_ocsf(notable)
        vulns = ocsf.get("vulnerabilities", [])
        cve_uids = [v["cve"]["uid"] for v in vulns]
        assert len(cve_uids) == 3
        assert "CVE-2021-34473" in cve_uids
        assert "CVE-2021-34523" in cve_uids
        assert "CVE-2021-31207" in cve_uids

    def test_cve_from_annotations(self, normalizer):
        notable = _make_notable(
            rule_name="Suspicious Activity",
            annotations={
                "mitre_attack": ["T1190"],
                "_all": ["CVE-2023-12345", "Remote Exploitation"],
            },
        )
        ocsf = normalizer.to_ocsf(notable)
        vulns = ocsf.get("vulnerabilities", [])
        cve_uids = [v["cve"]["uid"] for v in vulns]
        assert "CVE-2023-12345" in cve_uids


class TestOtherActivitiesMapping:
    """NAS other_activities -> OCSF unmapped."""

    def test_other_activities_in_unmapped(self, normalizer):
        notable = _make_notable(
            file_name="malware.exe",
            file_path="C:\\Users\\Public\\malware.exe",
            file_hash="d41d8cd98f00b204e9800998ecf8427e",
            registry_path="HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            service_name="MaliciousService",
            signature="Trojan.Generic",
        )
        ocsf = normalizer.to_ocsf(notable)
        unmapped = ocsf.get("unmapped", {})
        assert unmapped.get("file_name") == "malware.exe"
        assert unmapped.get("file_path") == notable["file_path"]
        assert unmapped.get("file_hash") == notable["file_hash"]
        assert unmapped.get("registry_path") == notable["registry_path"]
        assert unmapped.get("service_name") == "MaliciousService"
        assert unmapped.get("signature") == "Trojan.Generic"


class TestNetworkInfoMapping:
    """NAS network_info -> OCSF evidences[].src_endpoint / dst_endpoint."""

    def test_network_endpoints_in_evidence(self, normalizer):
        notable = _make_notable(
            src="10.0.0.1",
            dest="192.168.1.100",
            src_port="54321",
            dest_port="443",
            protocol="tcp",
        )
        ocsf = normalizer.to_ocsf(notable)
        ev = ocsf["evidences"][0]
        assert ev["src_endpoint"]["ip"] == "10.0.0.1"
        assert ev["dst_endpoint"]["ip"] == "192.168.1.100"
        assert ev["connection_info"]["protocol_name"] == "tcp"

    def test_src_port_in_evidence(self, normalizer):
        notable = _make_notable(
            src_ip="10.0.0.1",
            src_port="54321",
        )
        ocsf = normalizer.to_ocsf(notable)
        ev = ocsf["evidences"][0]
        assert ev["src_endpoint"]["port"] == "54321"


class TestSourceCategoryMapping:
    """NAS source_category -> OCSF metadata.labels."""

    @pytest.mark.parametrize(
        ("security_domain", "expected_label"),
        [
            ("network", "source_category:Firewall"),
            ("endpoint", "source_category:EDR"),
            ("identity", "source_category:Identity"),
            ("data", "source_category:DLP"),
            ("cloud", "source_category:Cloud"),
            ("email", "source_category:Email"),
            ("web", "source_category:Web"),
        ],
    )
    def test_domain_to_label(self, normalizer, security_domain, expected_label):
        notable = _make_notable(security_domain=security_domain)
        ocsf = normalizer.to_ocsf(notable)
        labels = ocsf["metadata"].get("labels", [])
        assert expected_label in labels


class TestComprehensiveFieldMapping:
    """NAS comprehensive test -> all OCSF fields at once."""

    def test_all_fields_together(self, normalizer):
        notable = _make_notable(
            rule_name="Complex Security Alert - CVE-2024-1234 Exploitation",
            rule_title="Advanced Persistent Threat Activity",
            rule_description="Detected exploitation of CVE-2024-1234 vulnerability",
            security_domain="network",
            action="Blocked",
            event_id="abc123@@notable@@def456",
            requested_url="https://target.com/admin?exploit=true",
            http_method="POST",
            user_agent="BadBot/1.0",
            src="203.0.113.1",
            dest="192.168.1.50",
            src_port="12345",
            dest_port="8080",
            process_name="exploit.exe",
            process_path="C:\\Temp\\exploit.exe",
            parent_process="cmd.exe",
            file_hash="abc123def456",
            registry_path="HKLM\\System",
        )
        ocsf = normalizer.to_ocsf(notable)

        # Disposition
        assert ocsf["disposition_id"] == 2
        assert ocsf["disposition"] == "Blocked"

        # Metadata
        assert ocsf["metadata"]["event_code"] == "abc123@@notable@@def456"
        assert "source_category:Firewall" in ocsf["metadata"]["labels"]

        # Severity
        assert ocsf["severity_id"] == 4
        assert ocsf["severity"] == "High"

        # CVE -> vulnerabilities
        vulns = ocsf.get("vulnerabilities", [])
        cve_uids = [v["cve"]["uid"] for v in vulns]
        assert "CVE-2024-1234" in cve_uids

        # Web info -> evidences.url
        ev = ocsf["evidences"][0]
        assert "target.com/admin" in ev["url"]["url_string"]
        assert ev["http_request"]["http_method"] == "POST"

        # Network info -> evidences endpoints
        assert ev["src_endpoint"]["ip"] == "203.0.113.1"

        # Process info -> evidences.process
        assert ev["process"]["name"] == "exploit.exe"

        # Other activities -> unmapped
        assert ocsf["unmapped"]["file_hash"] == "abc123def456"

    def test_primary_ioc_from_url(self, normalizer):
        """requested_url as primary IOC -> URL observable."""
        notable = _make_notable(
            rule_name="SQL Injection",
            requested_url="https://victim.com/app?id=1' OR '1'='1",
            dest="192.168.1.100",
        )
        ocsf = normalizer.to_ocsf(notable)
        # URL should appear as observable with type_id=6
        url_obs = [o for o in ocsf.get("observables", []) if o["type_id"] == 6]
        assert len(url_obs) >= 1


# ======================================================================
# Ported from test_splunk_normalizer_lists.py
# ======================================================================


class TestEntityListMapping:
    """NAS risk_entities -> OCSF device / actor."""

    def test_user_entity_becomes_actor(self, normalizer):
        notable = _make_notable(
            user="john.doe",
            dest="server01.example.com",
        )
        ocsf = normalizer.to_ocsf(notable)
        assert ocsf["actor"]["user"]["name"] == "john.doe"

    def test_device_entity_becomes_device(self, normalizer):
        notable = _make_notable(
            risk_object="WebServer1001",
            risk_object_type="system",
            dest="WebServer1001",
        )
        ocsf = normalizer.to_ocsf(notable)
        device = ocsf.get("device", {})
        assert device.get("hostname") == "WebServer1001"
        assert device.get("type_id") == 0

    def test_mixed_entities(self, normalizer):
        """Both user and device entities produce actor and device."""
        notable = _make_notable(
            user="john.doe",
            risk_object="server01.internal",
            risk_object_type="system",
            dest="server01.internal",
        )
        ocsf = normalizer.to_ocsf(notable)
        # User -> actor
        assert ocsf["actor"]["user"]["name"] == "john.doe"
        # Device -> device
        assert ocsf["device"]["hostname"] == "server01.internal"


class TestIOCListMapping:
    """NAS IOC list -> OCSF observables[]."""

    def test_multiple_ioc_types_become_observables(self, normalizer):
        notable = _make_notable(
            requested_url="http://evil.com/malware.exe",
            domain="evil.com",
            file_hash="d41d8cd98f00b204e9800998ecf8427e",
            process="powershell.exe -enc Base64String",
            dest_ip="185.220.101.45",
            attacker_ip="203.0.113.1",
        )
        ocsf = normalizer.to_ocsf(notable)
        obs = ocsf.get("observables", [])
        obs_types = {o["type_id"] for o in obs}

        # URL (6), Domain/Hostname (1), Hash (8), Process (9), IP (2)
        assert 6 in obs_types  # URL
        assert 2 in obs_types  # IP
        assert 8 in obs_types  # Hash

    def test_cves_not_in_observables(self, normalizer):
        """CVEs are vulnerabilities, not IOC observables."""
        notable = _make_notable(
            rule_name="Log4j Exploitation CVE-2021-44228",
            rule_description="Detects CVE-2021-45046 and CVE-2021-45105",
        )
        ocsf = normalizer.to_ocsf(notable)
        obs = ocsf.get("observables", [])
        for o in obs:
            assert "CVE" not in str(o.get("value", ""))


class TestDeduplication:
    """NAS dedup -> OCSF observables should not duplicate."""

    def test_no_duplicate_ip_observables(self, normalizer):
        """Same IP in multiple fields should appear once in observables."""
        notable = _make_notable(
            src="185.220.101.45",
            src_ip="185.220.101.45",
            attacker_ip="185.220.101.45",
        )
        ocsf = normalizer.to_ocsf(notable)
        obs = ocsf.get("observables", [])
        ip_values = [o["value"] for o in obs if o["type_id"] == 2]
        # Should not have duplicates
        assert len(ip_values) == len(set(ip_values))

    def test_internal_ips_not_in_observables(self, normalizer):
        """Private IPs (risk entities) should NOT appear as IOC observables."""
        notable = _make_notable(
            src_ip="192.168.1.100",
            dest_ip="10.0.0.1",
        )
        ocsf = normalizer.to_ocsf(notable)
        obs = ocsf.get("observables", [])
        ip_values = [o["value"] for o in obs if o["type_id"] == 2]
        assert "192.168.1.100" not in ip_values
        assert "10.0.0.1" not in ip_values


class TestIPClassification:
    """NAS internal vs external IP -> OCSF device vs observable."""

    def test_external_ips_become_observables(self, normalizer):
        notable = _make_notable(
            src_ip="192.168.1.100",
            dest_ip="185.220.101.45",
        )
        ocsf = normalizer.to_ocsf(notable)
        obs = ocsf.get("observables", [])
        ip_obs_values = [o["value"] for o in obs if o["type_id"] == 2]
        assert "185.220.101.45" in ip_obs_values

    def test_internal_ips_in_evidence_endpoints(self, normalizer):
        """Internal IPs should appear in evidences as endpoints, not observables."""
        notable = _make_notable(
            src_ip="192.168.1.100",
            dest_ip="10.0.0.1",
        )
        ocsf = normalizer.to_ocsf(notable)
        ev = ocsf["evidences"][0]
        # Internal IPs should be in endpoints
        assert ev["src_endpoint"]["ip"] == "192.168.1.100"
        assert ev["dst_endpoint"]["ip"] == "10.0.0.1"


class TestHashTypeMapping:
    """NAS hash IOC with hash_type -> OCSF observable type_id=8."""

    def test_hash_becomes_observable(self, normalizer):
        notable = _make_notable(
            file_hash="d41d8cd98f00b204e9800998ecf8427e",
        )
        ocsf = normalizer.to_ocsf(notable)
        obs = ocsf.get("observables", [])
        hash_obs = [o for o in obs if o["type_id"] == 8]
        assert len(hash_obs) >= 1
        assert hash_obs[0]["value"] == "d41d8cd98f00b204e9800998ecf8427e"

    def test_sha256_hash_becomes_observable(self, normalizer):
        notable = _make_notable(
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )
        ocsf = normalizer.to_ocsf(notable)
        obs = ocsf.get("observables", [])
        hash_obs = [o for o in obs if o["type_id"] == 8]
        assert len(hash_obs) >= 1


class TestUserAgentMapping:
    """NAS user_agent IOC -> OCSF observable type_id=16."""

    def test_suspicious_user_agent_observable(self, normalizer):
        notable = _make_notable(
            rule_name="SQL Injection Attack",
            user_agent="sqlmap/1.5.2",
            http_method="GET",
        )
        ocsf = normalizer.to_ocsf(notable)
        obs = ocsf.get("observables", [])
        ua_obs = [o for o in obs if o["type_id"] == 16]
        assert len(ua_obs) >= 1
        assert ua_obs[0]["value"] == "sqlmap/1.5.2"
        # High confidence (90) -> High reputation score
        assert ua_obs[0]["reputation"]["base_score"] == 90
        assert ua_obs[0]["reputation"]["score_id"] == 3  # High

    def test_scanner_user_agent_high_confidence(self, normalizer):
        notable = _make_notable(
            rule_name="Scanner Activity",
            user_agent="Mozilla/5.0 zgrab/0.x",
            dest_ip="185.220.101.45",
        )
        ocsf = normalizer.to_ocsf(notable)
        obs = ocsf.get("observables", [])
        ua_obs = [o for o in obs if o["type_id"] == 16]
        assert len(ua_obs) >= 1
        assert ua_obs[0]["reputation"]["base_score"] == 90

    def test_normal_user_agent_medium_confidence(self, normalizer):
        notable = _make_notable(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0",
            http_method="GET",
            requested_url="/index.html",
        )
        ocsf = normalizer.to_ocsf(notable)
        obs = ocsf.get("observables", [])
        ua_obs = [o for o in obs if o["type_id"] == 16]
        assert len(ua_obs) >= 1
        assert ua_obs[0]["reputation"]["base_score"] == 70

    def test_empty_user_agent_not_in_observables(self, normalizer):
        notable = _make_notable(user_agent="")
        ocsf = normalizer.to_ocsf(notable)
        obs = ocsf.get("observables", [])
        ua_obs = [o for o in obs if o.get("type_id") == 16]
        assert len(ua_obs) == 0

    def test_duplicate_user_agent_deduplicated(self, normalizer):
        notable = _make_notable(
            user_agent="sqlmap/1.5.2",
            http_user_agent="sqlmap/1.5.2",
        )
        ocsf = normalizer.to_ocsf(notable)
        obs = ocsf.get("observables", [])
        ua_obs = [o for o in obs if o["type_id"] == 16]
        assert len(ua_obs) == 1


# ======================================================================
# Ported from test_splunk_normalizer_real_notables.py
# Using the 9 real fixtures in tests/alert_normalizer/notables/
# ======================================================================


class TestRealFixtureFieldMappings:
    """Test OCSF field mapping against real Splunk notable fixtures."""

    @pytest.fixture
    def ocsf_normalizer(self):
        return SplunkOCSFNormalizer()

    def test_powershell_cve_extraction(self, ocsf_normalizer):
        """01-powershell: CVE-2022-41082 -> vulnerabilities[]."""
        notable = _load_fixture("01-powershell-exploit.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)

        # CVE should be extracted from rule_name
        vulns = ocsf.get("vulnerabilities", [])
        cve_uids = [v["cve"]["uid"] for v in vulns]
        assert "CVE-2022-41082" in cve_uids

    def test_powershell_device_extraction(self, ocsf_normalizer):
        """01-powershell: risk_object=Exchange Server 2 -> device."""
        notable = _load_fixture("01-powershell-exploit.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)

        device = ocsf.get("device", {})
        assert device.get("hostname") == "Exchange Server 2"
        assert device.get("type_id") == 0

    def test_powershell_blocked_disposition(self, ocsf_normalizer):
        """01-powershell: action=blocked -> disposition_id=2."""
        notable = _load_fixture("01-powershell-exploit.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)

        assert ocsf["disposition_id"] == 2
        assert ocsf["disposition"] == "Blocked"

    def test_powershell_threat_ip_observable(self, ocsf_normalizer):
        """01-powershell: threat_object=58.237.200.6 -> IP observable."""
        notable = _load_fixture("01-powershell-exploit.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)

        ip_obs = [o for o in ocsf.get("observables", []) if o["type_id"] == 2]
        ip_values = [o["value"] for o in ip_obs]
        assert "58.237.200.6" in ip_values

    def test_powershell_user_agent_observable(self, ocsf_normalizer):
        """01-powershell: user_agent=Mozilla/5.0 zgrab/0.x -> observable."""
        notable = _load_fixture("01-powershell-exploit.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)

        ua_obs = [o for o in ocsf.get("observables", []) if o["type_id"] == 16]
        assert len(ua_obs) >= 1
        assert ua_obs[0]["value"] == "Mozilla/5.0 zgrab/0.x"
        # zgrab is suspicious -> high confidence
        assert ua_obs[0]["reputation"]["base_score"] == 90

    def test_sql_injection_allowed_disposition(self, ocsf_normalizer):
        """02-sql-injection: action=allowed -> disposition_id=1."""
        notable = _load_fixture("02-sql-injection-web.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)
        assert ocsf["disposition_id"] == 1
        assert ocsf["disposition"] == "Allowed"

    def test_sql_injection_network_endpoints(self, ocsf_normalizer):
        """02-sql-injection: src/dest IPs -> evidence endpoints."""
        notable = _load_fixture("02-sql-injection-web.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)

        ev = ocsf["evidences"][0]
        assert ev["src_endpoint"]["ip"] == "167.99.169.17"
        assert ev["dst_endpoint"]["ip"] == "172.16.17.18"

    def test_sql_injection_url_with_path_and_query(self, ocsf_normalizer):
        """02-sql-injection: full URL -> url_string + path + query_string."""
        notable = _load_fixture("02-sql-injection-web.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)

        url_obj = ocsf["evidences"][0]["url"]
        assert "172.16.17.18/search/" in url_obj["url_string"]
        assert url_obj["path"] == "/search/"
        assert url_obj["query_string"] == "q=%22%20OR%201%20%3D%201%20--%20-"

    def test_sql_injection_severity(self, ocsf_normalizer):
        """02-sql-injection: severity=high -> severity_id=4."""
        notable = _load_fixture("02-sql-injection-web.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)
        assert ocsf["severity_id"] == 4
        assert ocsf["severity"] == "High"

    def test_xss_medium_severity(self, ocsf_normalizer):
        """03-xss: severity=medium -> severity_id=3."""
        notable = _load_fixture("03-xss-web-attack.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)
        assert ocsf["severity_id"] == 3
        assert ocsf["severity"] == "Medium"

    def test_xss_dest_port_in_evidence(self, ocsf_normalizer):
        """03-xss: dest_port=443 -> evidences.dst_endpoint.port."""
        notable = _load_fixture("03-xss-web-attack.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)
        ev = ocsf["evidences"][0]
        assert ev["dst_endpoint"]["port"] == 443

    def test_xss_protocol_in_connection_info(self, ocsf_normalizer):
        """03-xss: protocol=HTTPS -> evidences.connection_info.protocol_name."""
        notable = _load_fixture("03-xss-web-attack.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)
        ev = ocsf["evidences"][0]
        assert ev["connection_info"]["protocol_name"] == "HTTPS"

    def test_ls_command_device_hostname(self, ocsf_normalizer):
        """04-ls-command: risk_object=EliotPRD -> device.hostname."""
        notable = _load_fixture("04-ls-command-false-positive.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)
        # EliotPRD is not recognized as internal hostname, but it IS the
        # risk_object with type=system, so it should be the device
        device = ocsf.get("device", {})
        assert device.get("hostname") == "EliotPRD" or device.get("ip") is not None

    def test_whoami_post_method(self, ocsf_normalizer):
        """05-whoami: http_method=POST -> evidences.http_request.http_method."""
        notable = _load_fixture("05-whoami-command-injection.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)
        ev = ocsf["evidences"][0]
        assert ev["http_request"]["http_method"] == "POST"

    def test_idor_threat_ip_observable(self, ocsf_normalizer):
        """06-idor: threat_object=134.209.118.137 -> IP observable."""
        notable = _load_fixture("06-idor-attack.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)
        ip_obs = [o for o in ocsf.get("observables", []) if o["type_id"] == 2]
        ip_values = [o["value"] for o in ip_obs]
        assert "134.209.118.137" in ip_values

    def test_lfi_url_path(self, ocsf_normalizer):
        """07-lfi: URL with path traversal -> url.path."""
        notable = _load_fixture("07-lfi-attack-passwd.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)
        url_obj = ocsf["evidences"][0]["url"]
        assert url_obj["path"] == "/"
        assert "etc/passwd" in url_obj["query_string"]

    def test_sharepoint_cve_2023_29357(self, ocsf_normalizer):
        """08-sharepoint: CVE-2023-29357 -> vulnerabilities."""
        notable = _load_fixture("08-sharepoint-cve-exploit.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)
        vulns = ocsf.get("vulnerabilities", [])
        cve_uids = [v["cve"]["uid"] for v in vulns]
        assert "CVE-2023-29357" in cve_uids

    def test_sharepoint_critical_severity(self, ocsf_normalizer):
        """08-sharepoint: severity=critical -> severity_id=5."""
        notable = _load_fixture("08-sharepoint-cve-exploit.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)
        assert ocsf["severity_id"] == 5
        assert ocsf["severity"] == "Critical"

    def test_sharepoint_detected_disposition(self, ocsf_normalizer):
        """08-sharepoint: action=detected -> disposition_id=15."""
        notable = _load_fixture("08-sharepoint-cve-exploit.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)
        assert ocsf["disposition_id"] == 15
        assert ocsf["disposition"] == "Detected"

    def test_sharepoint_path_only_url(self, ocsf_normalizer):
        """08-sharepoint: requested_url=/_api/web/siteusers -> path."""
        notable = _load_fixture("08-sharepoint-cve-exploit.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)
        url_obj = ocsf["evidences"][0]["url"]
        assert url_obj["path"] == "/_api/web/siteusers"

    def test_confluence_cve_2023_22515(self, ocsf_normalizer):
        """09-confluence: CVE-2023-22515 -> vulnerabilities."""
        notable = _load_fixture("09-confluence-cve-exploit.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)
        vulns = ocsf.get("vulnerabilities", [])
        cve_uids = [v["cve"]["uid"] for v in vulns]
        assert "CVE-2023-22515" in cve_uids

    def test_confluence_path_with_query(self, ocsf_normalizer):
        """09-confluence: path-only URL with query string."""
        notable = _load_fixture("09-confluence-cve-exploit.json")
        ocsf = ocsf_normalizer.to_ocsf(notable)
        url_obj = ocsf["evidences"][0]["url"]
        assert url_obj["path"] == "/server-info.action"
        assert (
            url_obj["query_string"]
            == "bootstrapStatusProvider.applicationConfig.setupComplete=false"
        )


class TestAllFixturesOCSFInvariants:
    """Validate OCSF invariants across all 9 real fixtures."""

    @pytest.fixture
    def all_notables(self):
        results = {}
        for p in sorted(NOTABLES_DIR.glob("*.json")):
            with open(p) as f:
                results[p.name] = json.load(f)
        return results

    def test_all_have_status_new(self, normalizer, all_notables):
        """All Create events should have status_id=1, status=New."""
        for name, notable in all_notables.items():
            ocsf = normalizer.to_ocsf(notable)
            assert ocsf["status_id"] == 1, f"{name}: missing status_id"
            assert ocsf["status"] == "New", f"{name}: wrong status"

    def test_all_have_device_type_id(self, normalizer, all_notables):
        """All fixtures with device should have type_id=0."""
        for name, notable in all_notables.items():
            ocsf = normalizer.to_ocsf(notable)
            if "device" in ocsf:
                assert ocsf["device"]["type_id"] == 0, f"{name}: device missing type_id"

    def test_all_have_finding_info_analytic(self, normalizer, all_notables):
        """All fixtures must have finding_info.analytic with rule name."""
        for name, notable in all_notables.items():
            ocsf = normalizer.to_ocsf(notable)
            fi = ocsf["finding_info"]
            assert "analytic" in fi, f"{name}: missing analytic"
            assert fi["analytic"]["name"], f"{name}: empty analytic.name"
            assert fi["analytic"]["type_id"] == 1, f"{name}: wrong type_id"

    def test_all_have_valid_severity(self, normalizer, all_notables):
        """All fixtures must have valid severity_id."""
        for name, notable in all_notables.items():
            ocsf = normalizer.to_ocsf(notable)
            assert ocsf["severity_id"] in (1, 2, 3, 4, 5, 6), (
                f"{name}: invalid severity_id {ocsf['severity_id']}"
            )

    def test_all_raw_data_hash_matches(self, normalizer, all_notables):
        """All fixtures must have valid raw_data_hash."""
        import hashlib

        for name, notable in all_notables.items():
            ocsf = normalizer.to_ocsf(notable)
            expected = hashlib.sha256(ocsf["raw_data"].encode()).hexdigest()
            assert ocsf["raw_data_hash"] == expected, f"{name}: hash mismatch"

    def test_all_have_source_category_label(self, normalizer, all_notables):
        """All fixtures with security_domain should have source_category label."""
        for name, notable in all_notables.items():
            ocsf = normalizer.to_ocsf(notable)
            if notable.get("security_domain"):
                labels = ocsf["metadata"].get("labels", [])
                has_cat = any("source_category:" in lbl for lbl in labels)
                assert has_cat, f"{name}: missing source_category label"


# ======================================================================
# Ported from test_splunk_normalizer_roundtrip.py
# Verify OCSF output contains equivalent information
# ======================================================================


class TestOCSFEquivalence:
    """Verify OCSF output contains equivalent info to NAS round-trip data."""

    def test_risk_object_in_device(self, normalizer):
        """NAS risk_object -> OCSF device or actor."""
        notable = _make_notable(
            risk_object="user123",
            normalized_risk_object="DOMAIN\\user123",
            risk_object_type="user",
        )
        ocsf = normalizer.to_ocsf(notable)
        # User risk object -> actor
        assert ocsf["actor"]["user"]["name"] == "DOMAIN\\user123"

    def test_threat_object_in_observables(self, normalizer):
        """NAS threat_object -> OCSF observable."""
        notable = _make_notable(
            threat_object="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
            threat_object_type="hash",
        )
        ocsf = normalizer.to_ocsf(notable)
        obs = ocsf.get("observables", [])
        hash_obs = [o for o in obs if o["type_id"] == 8]
        hash_values = [o["value"] for o in hash_obs]
        assert "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4" in hash_values

    def test_process_name_in_evidence(self, normalizer):
        """NAS process_info.name -> OCSF evidences[].process.name."""
        notable = _make_notable(
            process='"C:\\Windows\\System32\\certutil.exe" -decode file.txt',
            process_name="certutil.exe",
            parent_process="C:\\Windows\\System32\\wbem\\WmiPrvSE.exe",
        )
        ocsf = normalizer.to_ocsf(notable)
        proc = ocsf["evidences"][0]["process"]
        assert proc["name"] == "certutil.exe"
        assert "certutil.exe" in proc["cmd_line"]

    def test_network_info_in_evidence(self, normalizer):
        """NAS network_info -> OCSF evidences endpoints."""
        notable = _make_notable(
            src="192.168.1.100",
            src_ip="192.168.1.100",
            src_port="54321",
            dest="external.site.com",
            dest_ip="10.0.0.1",
            dest_port="443",
            protocol="tcp",
        )
        ocsf = normalizer.to_ocsf(notable)
        ev = ocsf["evidences"][0]

        assert ev["src_endpoint"]["ip"] == "192.168.1.100"
        assert ev["src_endpoint"]["port"] == "54321"
        assert ev["dst_endpoint"]["ip"] == "10.0.0.1"
        assert ev["dst_endpoint"]["port"] == "443"
        assert ev["connection_info"]["protocol_name"] == "tcp"

    def test_web_info_in_evidence(self, normalizer):
        """NAS web_info -> OCSF evidences url + http_request."""
        notable = _make_notable(
            requested_url="http://malicious.site/payload",
            http_method="POST",
            user_agent="Mozilla/5.0 (suspicious)",
            http_referrer="http://referrer.site",
        )
        ocsf = normalizer.to_ocsf(notable)
        ev = ocsf["evidences"][0]

        assert ev["url"]["url_string"] == "http://malicious.site/payload"
        assert ev["http_request"]["http_method"] == "POST"
        assert ev["http_request"]["user_agent"] == "Mozilla/5.0 (suspicious)"
        assert ev["http_request"]["referrer"] == "http://referrer.site"

    def test_invalid_values_filtered_from_actor(self, normalizer):
        """Invalid/placeholder values should not appear as actor."""
        notable = _make_notable(
            user="unknown",
            dest="-",
            src="n/a",
            risk_object="none",
            normalized_risk_object="real_user123",
            risk_object_type="user",
        )
        ocsf = normalizer.to_ocsf(notable)
        # Should use normalized_risk_object
        assert ocsf["actor"]["user"]["name"] == "real_user123"

    def test_cve_in_vulnerabilities(self, normalizer):
        """NAS cve_info -> OCSF vulnerabilities."""
        notable = _make_notable(
            rule_name="CVE-2021-44228 Log4Shell Exploitation",
            rule_description="Detection of CVE-2021-44228 exploitation attempts",
        )
        ocsf = normalizer.to_ocsf(notable)
        vulns = ocsf.get("vulnerabilities", [])
        cve_uids = [v["cve"]["uid"] for v in vulns]
        assert "CVE-2021-44228" in cve_uids


# ======================================================================
# New tests for fixes introduced in this PR
# ======================================================================


class TestMITREAttackMapping:
    """Fix 1: MITRE ATT&CK technique IDs -> finding_info.attacks[]."""

    def test_technique_from_mitre_field(self, normalizer):
        """mitre_technique field -> finding_info.attacks."""
        notable = _make_notable(mitre_technique="T1190")
        ocsf = normalizer.to_ocsf(notable)
        attacks = ocsf["finding_info"].get("attacks", [])
        assert len(attacks) >= 1
        assert attacks[0]["technique"]["uid"] == "T1190"
        assert attacks[0]["technique"]["name"] == "Exploit Public-Facing Application"
        assert attacks[0]["tactic"]["uid"] == "TA0001"
        assert attacks[0]["tactic"]["name"] == "Initial Access"

    def test_technique_from_annotations(self, normalizer):
        """annotations.mitre_attack -> finding_info.attacks."""
        notable = _make_notable(
            annotations={"mitre_attack": ["T1059", "T1078"]},
        )
        ocsf = normalizer.to_ocsf(notable)
        attacks = ocsf["finding_info"].get("attacks", [])
        technique_uids = [a["technique"]["uid"] for a in attacks]
        assert "T1059" in technique_uids
        assert "T1078" in technique_uids

    def test_sub_technique(self, normalizer):
        """Sub-technique T1059.001 -> technique + sub_technique."""
        notable = _make_notable(mitre_technique="T1059.001")
        ocsf = normalizer.to_ocsf(notable)
        attacks = ocsf["finding_info"].get("attacks", [])
        assert len(attacks) >= 1
        # Parent technique
        assert attacks[0]["technique"]["uid"] == "T1059"
        assert attacks[0]["technique"]["name"] == "Command and Scripting Interpreter"
        # Sub-technique
        assert attacks[0]["sub_technique"]["uid"] == "T1059.001"
        # Tactic
        assert attacks[0]["tactic"]["uid"] == "TA0002"

    def test_unknown_technique_still_emitted(self, normalizer):
        """Unknown technique ID should still produce an attack entry."""
        notable = _make_notable(mitre_technique="T9999")
        ocsf = normalizer.to_ocsf(notable)
        attacks = ocsf["finding_info"].get("attacks", [])
        assert len(attacks) >= 1
        assert attacks[0]["technique"]["uid"] == "T9999"

    def test_no_technique_means_no_attacks(self, normalizer):
        """No mitre_technique -> no attacks in finding_info."""
        notable = _make_notable()
        ocsf = normalizer.to_ocsf(notable)
        assert "attacks" not in ocsf["finding_info"]

    def test_collect_technique_ids_deduplicates(self):
        """_collect_technique_ids should not return duplicates."""
        notable = _make_notable(
            mitre_technique="T1190",
            annotations={"mitre_attack": ["T1190", "T1059"]},
        )
        ids = _collect_technique_ids(notable)
        assert ids == ["T1190", "T1059"]

    def test_build_attack_entry_known(self):
        """_build_attack_entry for a known technique."""
        entry = _build_attack_entry("T1110")
        assert entry is not None
        assert entry["technique"]["uid"] == "T1110"
        assert entry["technique"]["name"] == "Brute Force"
        assert entry["tactic"]["uid"] == "TA0006"
        assert entry["tactic"]["name"] == "Credential Access"


class TestSeverityFatal:
    """Fix 5: severity fatal -> severity_id=6."""

    def test_fatal_severity(self, normalizer):
        notable = _make_notable(severity="fatal")
        ocsf = normalizer.to_ocsf(notable)
        assert ocsf["severity_id"] == 6
        assert ocsf["severity"] == "Fatal"


class TestStatusOnCreate:
    """Fix 6: status_id=1 and status=New on Create events."""

    def test_status_present(self, normalizer):
        notable = _make_notable()
        ocsf = normalizer.to_ocsf(notable)
        assert ocsf["status_id"] == 1
        assert ocsf["status"] == "New"


class TestNewObservableTypes:
    """Fix 4: email, MAC, port observable types."""

    def test_email_observable_type(self):
        """Email IOC type should map to type_id=5."""
        assert IOC_TYPE_TO_OBSERVABLE["email"] == (5, "Email Address")

    def test_mac_observable_type(self):
        """MAC IOC type should map to type_id=3."""
        assert IOC_TYPE_TO_OBSERVABLE["mac"] == (3, "MAC Address")

    def test_port_observable_type(self):
        """Port IOC type should map to type_id=11."""
        assert IOC_TYPE_TO_OBSERVABLE["port"] == (11, "Port")


class TestURLParsing:
    """Fix 3: URL path and query_string parsing."""

    def test_full_url_parsed(self, normalizer):
        """Full URL should extract path and query_string."""
        notable = _make_notable(
            requested_url="https://example.com/api/v1/users?page=1&limit=10",
        )
        ocsf = normalizer.to_ocsf(notable)
        url_obj = ocsf["evidences"][0]["url"]
        assert url_obj["url_string"] == notable["requested_url"]
        assert url_obj["path"] == "/api/v1/users"
        assert url_obj["query_string"] == "page=1&limit=10"

    def test_url_no_query(self, normalizer):
        """URL without query string should only have path."""
        notable = _make_notable(
            requested_url="https://example.com/api/v1/users",
        )
        ocsf = normalizer.to_ocsf(notable)
        url_obj = ocsf["evidences"][0]["url"]
        assert url_obj["path"] == "/api/v1/users"
        assert "query_string" not in url_obj

    def test_path_with_query(self, normalizer):
        """Path-only (no scheme) with query string."""
        notable = _make_notable(
            requested_url="/search?q=test",
            http_method="GET",
        )
        ocsf = normalizer.to_ocsf(notable)
        url_obj = ocsf["evidences"][0]["url"]
        assert url_obj["path"] == "/search"
        assert url_obj["query_string"] == "q=test"

    def test_lfi_path_traversal_url(self, normalizer):
        """URL with path traversal should preserve path components."""
        notable = _make_notable(
            requested_url="https://172.16.17.13/?file=../../../../etc/passwd",
        )
        ocsf = normalizer.to_ocsf(notable)
        url_obj = ocsf["evidences"][0]["url"]
        assert url_obj["path"] == "/"
        assert "etc/passwd" in url_obj["query_string"]


# ── OCSF Compliance Review Fixes (post-audit) ───────────────────────────


class TestIsAlertField:
    """is_alert should be True for all Splunk Notables."""

    def test_is_alert_always_true(self, normalizer):
        ocsf = normalizer.to_ocsf(_make_notable())
        assert ocsf["is_alert"] is True


class TestFindingInfoDesc:
    """finding_info.desc should map from rule_description."""

    def test_desc_from_rule_description(self, normalizer):
        notable = _make_notable(
            rule_description="SQL injection detected in web request"
        )
        ocsf = normalizer.to_ocsf(notable)
        assert ocsf["finding_info"]["desc"] == "SQL injection detected in web request"

    def test_desc_from_description_field(self, normalizer):
        notable = _make_notable(description="Suspicious PowerShell activity")
        ocsf = normalizer.to_ocsf(notable)
        assert ocsf["finding_info"]["desc"] == "Suspicious PowerShell activity"

    def test_no_desc_when_absent(self, normalizer):
        ocsf = normalizer.to_ocsf(_make_notable())
        assert "desc" not in ocsf["finding_info"]


class TestRiskScoreMapping:
    """risk_score should map to OCSF risk_score and risk_level_id."""

    @pytest.mark.parametrize(
        ("score", "expected_level_id", "expected_level"),
        [
            (95, 4, "Critical"),
            (75, 3, "High"),
            (50, 2, "Medium"),
            (30, 1, "Low"),
            (10, 0, "Info"),
        ],
    )
    def test_risk_score_levels(
        self, normalizer, score, expected_level_id, expected_level
    ):
        notable = _make_notable(risk_score=score)
        ocsf = normalizer.to_ocsf(notable)
        assert ocsf["risk_score"] == score
        assert ocsf["risk_level_id"] == expected_level_id
        assert ocsf["risk_level"] == expected_level

    def test_no_risk_score_when_absent(self, normalizer):
        ocsf = normalizer.to_ocsf(_make_notable())
        assert "risk_score" not in ocsf

    def test_string_risk_score_converted(self, normalizer):
        notable = _make_notable(risk_score="75")
        ocsf = normalizer.to_ocsf(notable)
        assert ocsf["risk_score"] == 75


class TestActionIdMapping:
    """action_id should map from device_action per Security Control profile."""

    def test_allowed_action(self, normalizer):
        notable = _make_notable(action="allowed")
        ocsf = normalizer.to_ocsf(notable)
        assert ocsf["action_id"] == 1
        assert ocsf["action"] == "Allowed"

    def test_blocked_action(self, normalizer):
        notable = _make_notable(action="blocked")
        ocsf = normalizer.to_ocsf(notable)
        assert ocsf["action_id"] == 2
        assert ocsf["action"] == "Denied"

    def test_no_action_id_for_detected(self, normalizer):
        """detected has disposition but no action_id (not allowed/denied)."""
        notable = _make_notable(action="detected")
        ocsf = normalizer.to_ocsf(notable)
        assert ocsf["disposition_id"] == 15
        assert "action_id" not in ocsf


class TestObservableNameField:
    """Observable.name should be the OCSF attribute path."""

    def test_ip_observable_has_name(self, normalizer):
        notable = _make_notable(threat_object="8.8.8.8", threat_object_type="ip")
        ocsf = normalizer.to_ocsf(notable)
        ip_obs = [o for o in ocsf.get("observables", []) if o["type_id"] == 2]
        assert len(ip_obs) > 0
        assert ip_obs[0]["name"] == "dst_endpoint.ip"

    def test_url_observable_has_name(self, normalizer):
        notable = _make_notable(
            threat_object="https://evil.com/payload",
            threat_object_type="url",
        )
        ocsf = normalizer.to_ocsf(notable)
        url_obs = [o for o in ocsf.get("observables", []) if o["type_id"] == 6]
        assert len(url_obs) > 0
        assert url_obs[0]["name"] == "url.url_string"
