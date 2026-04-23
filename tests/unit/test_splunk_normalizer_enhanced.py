"""
Unit tests for enhanced Splunk normalizer with new field extraction.

Tests the extraction of:
- device_action
- source_event_id
- web_info
- process_info
- cve_info
- other_activities

NAS-specific fields (device_action, web_info, process_info, etc.) are validated
via to_extracted_dict() since AlertCreate (OCSF shape) no longer carries them.
"""

import pytest

from alert_normalizer.splunk import SplunkNotableNormalizer


class TestSplunkNormalizerEnhanced:
    """Test enhanced Splunk normalizer field extraction."""

    @pytest.fixture
    def normalizer(self):
        """Create normalizer instance."""
        return SplunkNotableNormalizer()

    def test_extract_device_action(self, normalizer):
        """Test device_action extraction and normalization."""
        test_cases = [
            {"action": "Allowed", "expected": "allowed"},
            {"action": "Blocked", "expected": "blocked"},
            {"action": "Detected", "expected": "detected"},
            {"action": "blocked", "expected": "blocked"},
            {"action": "ALLOW", "expected": "allowed"},
            {"action": "deny", "expected": "blocked"},
            {"action": "quarantined", "expected": "quarantined"},
            {"action": None, "expected": None},
        ]

        for case in test_cases:
            notable = {
                "rule_name": "Test Alert",
                "_time": "2025-01-15T10:00:00Z",
                "severity": "high",
                "action": case["action"],
            }

            nas_dict = normalizer.to_extracted_dict(notable)
            assert nas_dict["device_action"] == case["expected"], (
                f"Failed for action: {case['action']}"
            )

    def test_extract_source_event_id(self, normalizer):
        """Test source_event_id extraction from Splunk event_id."""
        notable = {
            "rule_name": "Test Alert",
            "_time": "2025-01-15T10:00:00Z",
            "severity": "high",
            "event_id": "82e4fa80-9a68-4071-9b7c-f53840132da8@@notable@@82e4fa809a6840719b7cf53840132da8",
        }

        # source_event_id IS in AlertBase, so we can check the model too
        alert = normalizer.to_alertcreate(notable)
        assert alert.source_event_id == notable["event_id"]

    def test_extract_web_info(self, normalizer):
        """Test web_info extraction for web attacks."""
        notable = {
            "rule_name": "SQL Injection Attack",
            "_time": "2025-01-15T10:00:00Z",
            "severity": "high",
            "requested_url": "https://example.com/search?q=' OR 1=1--",
            "http_method": "GET",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "http_status": "200",
            "bytes_out": "4096",
            "bytes_in": "512",
        }

        nas_dict = normalizer.to_extracted_dict(notable)

        assert nas_dict["web_info"] is not None
        assert nas_dict["web_info"]["url"] == notable["requested_url"]
        assert nas_dict["web_info"]["http_method"] == "GET"
        assert nas_dict["web_info"]["user_agent"] == notable["user_agent"]

    def test_extract_process_info(self, normalizer):
        """Test process_info extraction for endpoint alerts."""
        notable = {
            "rule_name": "Suspicious Process Execution",
            "_time": "2025-01-15T10:00:00Z",
            "severity": "high",
            "process": "powershell.exe -encodedCommand SGVsbG8gV29ybGQ=",
            "process_name": "powershell.exe",
            "process_path": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
            "parent_process": "cmd.exe",
            "parent_process_path": "C:\\Windows\\System32\\cmd.exe",
            "process_id": "1234",
            "parent_process_id": "5678",
        }

        nas_dict = normalizer.to_extracted_dict(notable)

        assert nas_dict["process_info"] is not None
        pi = nas_dict["process_info"]
        assert pi["cmd"] == notable["process"]
        assert pi["name"] == "powershell.exe"
        assert pi["path"] == notable["process_path"]
        assert pi["parent_cmd"] == "cmd.exe"
        assert pi["parent_path"] == notable["parent_process_path"]
        assert pi["pid"] == 1234
        assert pi["parent_pid"] == 5678

    def test_extract_cve_info_from_title(self, normalizer):
        """Test CVE extraction from rule title."""
        notable = {
            "rule_name": "PowerShell Found in URL - CVE-2022-41082 Exploitation",
            "rule_title": "Possible CVE-2022-41082 Exchange Exploitation",
            "_time": "2025-01-15T10:00:00Z",
            "severity": "critical",
        }

        nas_dict = normalizer.to_extracted_dict(notable)

        assert nas_dict["cve_info"] is not None
        assert nas_dict["cve_info"]["ids"] is not None
        assert "CVE-2022-41082" in nas_dict["cve_info"]["ids"]

    def test_extract_multiple_cves(self, normalizer):
        """Test extraction of multiple CVE IDs."""
        notable = {
            "rule_name": "ProxyShell Attack Chain",
            "rule_description": "Exploitation of CVE-2021-34473, CVE-2021-34523, and CVE-2021-31207",
            "_time": "2025-01-15T10:00:00Z",
            "severity": "critical",
        }

        nas_dict = normalizer.to_extracted_dict(notable)

        assert nas_dict["cve_info"] is not None
        assert nas_dict["cve_info"]["ids"] is not None
        assert len(nas_dict["cve_info"]["ids"]) == 3
        assert "CVE-2021-34473" in nas_dict["cve_info"]["ids"]
        assert "CVE-2021-34523" in nas_dict["cve_info"]["ids"]
        assert "CVE-2021-31207" in nas_dict["cve_info"]["ids"]

    def test_extract_cve_from_annotations(self, normalizer):
        """Test CVE extraction from MITRE annotations."""
        notable = {
            "rule_name": "Suspicious Activity",
            "_time": "2025-01-15T10:00:00Z",
            "severity": "high",
            "annotations": {
                "mitre_attack": ["T1190"],
                "_all": ["CVE-2023-12345", "Remote Exploitation"],
            },
        }

        nas_dict = normalizer.to_extracted_dict(notable)

        assert nas_dict["cve_info"] is not None
        assert nas_dict["cve_info"]["ids"] is not None
        assert "CVE-2023-12345" in nas_dict["cve_info"]["ids"]

    def test_extract_other_activities(self, normalizer):
        """Test other_activities extraction for miscellaneous fields."""
        notable = {
            "rule_name": "File Activity Alert",
            "_time": "2025-01-15T10:00:00Z",
            "severity": "medium",
            "file_name": "malware.exe",
            "file_path": "C:\\Users\\Public\\malware.exe",
            "file_hash": "d41d8cd98f00b204e9800998ecf8427e",
            "registry_path": "HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run",
            "service_name": "MaliciousService",
            "signature": "Trojan.Generic",
        }

        nas_dict = normalizer.to_extracted_dict(notable)

        assert nas_dict["other_activities"] is not None
        assert nas_dict["other_activities"]["file_name"] == "malware.exe"
        assert nas_dict["other_activities"]["file_path"] == notable["file_path"]
        assert nas_dict["other_activities"]["file_hash"] == notable["file_hash"]
        assert nas_dict["other_activities"]["registry_path"] == notable["registry_path"]
        assert nas_dict["other_activities"]["service_name"] == "MaliciousService"
        assert nas_dict["other_activities"]["signature"] == "Trojan.Generic"

    def test_primary_ioc_from_requested_url(self, normalizer):
        """Test that requested_url is used as primary IOC for web attacks."""
        notable = {
            "rule_name": "SQL Injection",
            "_time": "2025-01-15T10:00:00Z",
            "severity": "high",
            "requested_url": "https://victim.com/app?id=1' OR '1'='1",
            "dest": "192.168.1.100",
        }

        nas_dict = normalizer.to_extracted_dict(notable)

        # requested_url should be the primary IOC
        assert nas_dict["primary_ioc_value"] == notable["requested_url"]
        assert nas_dict["primary_ioc_type"] == "url"

    def test_network_info_extraction(self, normalizer):
        """Test network_info extraction."""
        notable = {
            "rule_name": "Network Attack",
            "_time": "2025-01-15T10:00:00Z",
            "severity": "high",
            "src": "10.0.0.1",
            "dest": "192.168.1.100",
            "src_port": "54321",
            "dest_port": "443",
            "protocol": "tcp",
            "bytes_in": "1024",
            "bytes_out": "2048",
        }

        nas_dict = normalizer.to_extracted_dict(notable)

        assert nas_dict["network_info"] is not None
        assert nas_dict["network_info"]["src_ip"] == "10.0.0.1"
        assert nas_dict["network_info"]["dest_ip"] == "192.168.1.100"
        assert nas_dict["network_info"]["protocol"] == "tcp"

    def test_source_category_mapping(self, normalizer):
        """Test security_domain to source_category mapping."""
        test_cases = [
            {"security_domain": "network", "expected": "Firewall"},
            {"security_domain": "endpoint", "expected": "EDR"},
            {"security_domain": "identity", "expected": "Identity"},
            {"security_domain": "data", "expected": "DLP"},
            {"security_domain": "cloud", "expected": "Cloud"},
            {"security_domain": "email", "expected": "Email"},
            {"security_domain": "web", "expected": "Web"},
        ]

        for case in test_cases:
            notable = {
                "rule_name": "Test Alert",
                "_time": "2025-01-15T10:00:00Z",
                "severity": "high",
                "security_domain": case["security_domain"],
            }

            nas_dict = normalizer.to_extracted_dict(notable)
            assert nas_dict["source_category"] == case["expected"], (
                f"Failed for domain: {case['security_domain']}"
            )

    def test_all_fields_together(self, normalizer):
        """Test a comprehensive notable with all enhanced fields."""
        notable = {
            "rule_name": "Complex Security Alert - CVE-2024-1234 Exploitation",
            "rule_title": "Advanced Persistent Threat Activity",
            "rule_description": "Detected exploitation of CVE-2024-1234 vulnerability",
            "_time": "2025-01-15T10:00:00Z",
            "severity": "critical",
            "security_domain": "network",
            "action": "Blocked",
            "event_id": "abc123@@notable@@def456",
            # Web info
            "requested_url": "https://target.com/admin?exploit=true",
            "http_method": "POST",
            "user_agent": "BadBot/1.0",
            # Network info
            "src": "203.0.113.1",
            "dest": "192.168.1.50",
            "src_port": "12345",
            "dest_port": "8080",
            # Process info
            "process_name": "exploit.exe",
            "process_path": "C:\\Temp\\exploit.exe",
            "parent_process": "cmd.exe",
            # Other activities
            "file_hash": "abc123def456",
            "registry_path": "HKLM\\System",
        }

        nas_dict = normalizer.to_extracted_dict(notable)

        # Verify all enhanced fields
        assert nas_dict["device_action"] == "blocked"
        assert nas_dict["source_event_id"] == notable["event_id"]
        assert nas_dict["source_category"] == "Firewall"

        # CVE info
        assert nas_dict["cve_info"] is not None
        assert "CVE-2024-1234" in nas_dict["cve_info"]["ids"]

        # Web info
        assert nas_dict["web_info"] is not None
        assert nas_dict["web_info"]["url"] == notable["requested_url"]
        assert nas_dict["web_info"]["http_method"] == "POST"

        # Network info
        assert nas_dict["network_info"] is not None
        assert nas_dict["network_info"]["src_ip"] == "203.0.113.1"

        # Process info
        assert nas_dict["process_info"] is not None
        assert nas_dict["process_info"]["name"] == "exploit.exe"

        # Other activities
        assert nas_dict["other_activities"] is not None
        assert nas_dict["other_activities"]["file_hash"] == "abc123def456"
