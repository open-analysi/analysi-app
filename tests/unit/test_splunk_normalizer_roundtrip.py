"""Test round-trip conversion between Splunk Notable and NAS formats.

Round-trip tests use to_extracted_dict() instead of to_alertcreate() because
AlertCreate (OCSF shape) drops NAS-only fields like primary_risk_entity_value,
network_info, etc.  The NAS dict preserves all extracted fields needed for
bidirectional Notable <-> NAS conversion.
"""

import json
from pathlib import Path

import pytest

from alert_normalizer.splunk import SplunkNotableNormalizer


class TestSplunkRoundTrip:
    """Test bidirectional conversion Notable <-> NAS."""

    def setup_method(self):
        """Set up test fixtures."""
        self.normalizer = SplunkNotableNormalizer()

    def test_risk_object_preservation(self):
        """Test that risk_object and normalized_risk_object are preserved."""
        notable = {
            "rule_name": "Test Alert",
            "_time": "2024-01-01T12:00:00Z",
            "severity": "high",
            "risk_object": "user123",
            "normalized_risk_object": "DOMAIN\\user123",
            "risk_object_type": "user",
        }

        # Convert to NAS dict
        nas_dict = self.normalizer.to_extracted_dict(notable)

        # Should use normalized as primary
        assert nas_dict["primary_risk_entity_value"] == "DOMAIN\\user123"
        assert nas_dict["primary_risk_entity_type"] == "user"

        # Both should be in risk_entities list
        risk_entities = nas_dict.get("risk_entities", [])
        assert len(risk_entities) >= 2
        values = [e["value"] for e in risk_entities]
        assert "user123" in values
        assert "DOMAIN\\user123" in values

        # Convert back to Notable
        reconstructed = self.normalizer.from_alertcreate(nas_dict)

        # Both should be preserved
        assert reconstructed["risk_object"] == "user123"
        assert reconstructed["normalized_risk_object"] == "DOMAIN\\user123"
        assert reconstructed["risk_object_type"] == "user"

    def test_threat_object_preservation(self):
        """Test that threat_object maps to primary IOC."""
        notable = {
            "rule_name": "Malware Detection",
            "_time": "2024-01-01T12:00:00Z",
            "severity": "critical",
            "threat_object": "a1b2c3d4e5f6",
            "threat_object_type": "hash",
            "process": "C:\\Windows\\System32\\cmd.exe",
            "dest": "workstation01",
        }

        # Convert to NAS dict
        nas_dict = self.normalizer.to_extracted_dict(notable)

        # threat_object should be primary IOC
        assert nas_dict["primary_ioc_value"] == "a1b2c3d4e5f6"
        assert nas_dict["primary_ioc_type"] == "filehash"

        # Convert back to Notable
        reconstructed = self.normalizer.from_alertcreate(nas_dict)

        # threat_object should be preserved
        assert reconstructed["threat_object"] == "a1b2c3d4e5f6"

    def test_process_name_extraction(self):
        """Test that process_name is correctly extracted as just the exe name."""
        notable = {
            "rule_name": "Suspicious Process",
            "_time": "2024-01-01T12:00:00Z",
            "severity": "high",
            "process": '"C:\\Windows\\System32\\certutil.exe" -decode file.txt',
            "process_name": "certutil.exe",
            "parent_process": "C:\\Windows\\System32\\wbem\\WmiPrvSE.exe",
            "parent_process_name": "WmiPrvSE.exe",
        }

        # Convert to NAS dict
        nas_dict = self.normalizer.to_extracted_dict(notable)

        # Process info should be extracted
        assert nas_dict.get("process_info") is not None
        process_info = nas_dict["process_info"]
        assert (
            process_info["cmd"]
            == '"C:\\Windows\\System32\\certutil.exe" -decode file.txt'
        )
        assert process_info["name"] == "certutil.exe"

        # Convert back to Notable
        reconstructed = self.normalizer.from_alertcreate(nas_dict)

        # process_name should be just the exe
        assert (
            reconstructed["process"]
            == '"C:\\Windows\\System32\\certutil.exe" -decode file.txt'
        )
        assert reconstructed["process_name"] == "certutil.exe"

    def test_network_info_preservation(self):
        """Test that network_info fields are preserved in round-trip."""
        notable = {
            "rule_name": "Network Alert",
            "_time": "2024-01-01T12:00:00Z",
            "severity": "medium",
            "src": "192.168.1.100",
            "src_ip": "192.168.1.100",
            "src_port": "54321",
            "dest": "external.site.com",
            "dest_ip": "10.0.0.1",
            "dest_port": "443",
            "protocol": "tcp",
            "bytes_in": "1024",
            "bytes_out": "2048",
        }

        # Convert to NAS dict
        nas_dict = self.normalizer.to_extracted_dict(notable)

        # Network info should be extracted
        assert nas_dict.get("network_info") is not None
        network_info = nas_dict["network_info"]
        assert network_info["src_ip"] == "192.168.1.100"
        assert int(network_info["src_port"]) == 54321
        assert network_info["dest_hostname"] == "external.site.com"
        assert network_info["dest_ip"] == "10.0.0.1"
        assert int(network_info["dest_port"]) == 443
        assert network_info["protocol"] == "tcp"

        # Convert back to Notable
        reconstructed = self.normalizer.from_alertcreate(nas_dict)

        # Network fields should be preserved (ports may be int or string depending on path)
        assert reconstructed["src_ip"] == "192.168.1.100"
        assert str(reconstructed["src_port"]) == "54321"
        assert reconstructed["dest_ip"] == "10.0.0.1"
        assert str(reconstructed["dest_port"]) == "443"
        assert reconstructed["protocol"] == "tcp"

    def test_web_info_preservation(self):
        """Test that web_info fields are preserved in round-trip."""
        notable = {
            "rule_name": "Web Attack",
            "_time": "2024-01-01T12:00:00Z",
            "severity": "high",
            "requested_url": "http://malicious.site/payload",
            "http_method": "POST",
            "user_agent": "Mozilla/5.0 (suspicious)",
            "http_referrer": "http://referrer.site",
            "bytes_in": "500",
            "bytes_out": "1500",
        }

        # Convert to NAS dict
        nas_dict = self.normalizer.to_extracted_dict(notable)

        # Web info should be extracted
        assert nas_dict.get("web_info") is not None
        web_info = nas_dict["web_info"]
        assert web_info["url"] == "http://malicious.site/payload"
        assert web_info["http_method"] == "POST"
        assert web_info["user_agent"] == "Mozilla/5.0 (suspicious)"
        assert web_info["http_referrer"] == "http://referrer.site"

        # Convert back to Notable
        reconstructed = self.normalizer.from_alertcreate(nas_dict)

        # Web fields should be preserved (through raw_alert)
        # Since we preserve raw_alert, these should come back
        assert "requested_url" in reconstructed or "url" in reconstructed

    def test_invalid_values_filtered(self):
        """Test that invalid/placeholder values are filtered out."""
        notable = {
            "rule_name": "Test Alert",
            "_time": "2024-01-01T12:00:00Z",
            "severity": "low",
            "user": "unknown",
            "dest": "-",
            "src": "n/a",
            "risk_object": "none",
            "normalized_risk_object": "real_user123",
            "risk_object_type": "user",
        }

        # Convert to NAS dict
        nas_dict = self.normalizer.to_extracted_dict(notable)

        # Should use normalized_risk_object since others are invalid
        assert nas_dict["primary_risk_entity_value"] == "real_user123"

        # Invalid values shouldn't be in risk_entities
        risk_entities = nas_dict.get("risk_entities", [])
        entity_values = [e["value"] for e in risk_entities]
        assert "unknown" not in entity_values
        assert "-" not in entity_values
        assert "n/a" not in entity_values
        assert "none" not in entity_values

    def test_real_process_notable_roundtrip(self):
        """Test round-trip with a real process notable from fixtures."""
        fixture_path = Path("tests/fixtures/splunk_notables/process_notable.json")
        if not fixture_path.exists():
            pytest.skip("Process notable fixture not found")

        with open(fixture_path) as f:
            original_notable = json.load(f)

        # Convert to NAS dict
        nas_dict = self.normalizer.to_extracted_dict(original_notable)

        # Verify key fields were extracted
        assert nas_dict["title"] == "ESCU - CertUtil With Decode Argument - Rule"
        assert nas_dict["severity"] == "high"
        assert nas_dict["primary_risk_entity_value"] == "Administrator"
        assert nas_dict["primary_ioc_type"] == "process"

        # Process info should be complete
        assert nas_dict.get("process_info") is not None
        process_info = nas_dict["process_info"]
        assert "certutil.exe" in process_info.get("name", "")
        assert "WmiPrvSE.exe" in process_info.get("parent_cmd", "")

        # Convert back to Notable
        reconstructed = self.normalizer.from_alertcreate(nas_dict)

        # Key fields should be preserved
        assert reconstructed["rule_name"] == original_notable["rule_name"]
        assert reconstructed["severity"] == original_notable["severity"]
        assert reconstructed["user"] == original_notable["user"]
        assert reconstructed["dest"] == original_notable["dest"]

        # Process fields should be preserved
        assert reconstructed["process"] == original_notable["process"]
        assert reconstructed["process_name"] == "certutil.exe"

    def test_real_network_notable_roundtrip(self):
        """Test round-trip with a real network notable from fixtures."""
        fixture_path = Path("tests/fixtures/splunk_notables/network_notable.json")
        if not fixture_path.exists():
            pytest.skip("Network notable fixture not found")

        with open(fixture_path) as f:
            original_notable = json.load(f)

        # Convert to NAS dict
        nas_dict = self.normalizer.to_extracted_dict(original_notable)

        # Should have extracted risk_object as primary
        if original_notable.get("normalized_risk_object"):
            assert (
                nas_dict["primary_risk_entity_value"]
                == original_notable["normalized_risk_object"]
            )
        elif original_notable.get("risk_object"):
            # File hash is the risk object in this case
            risk_entities = nas_dict.get("risk_entities", [])
            risk_values = [e["value"] for e in risk_entities]
            assert original_notable["risk_object"] in risk_values

        # Should have threat_object as primary IOC
        if original_notable.get("threat_object"):
            assert nas_dict["primary_ioc_value"] == original_notable["threat_object"]

        # Convert back to Notable
        reconstructed = self.normalizer.from_alertcreate(nas_dict)

        # Risk and threat objects should be preserved
        if original_notable.get("risk_object"):
            assert reconstructed.get("risk_object") == original_notable["risk_object"]
        if original_notable.get("threat_object"):
            assert (
                reconstructed.get("threat_object") == original_notable["threat_object"]
            )

    def test_cve_info_preservation(self):
        """Test that CVE information is extracted and preserved."""
        notable = {
            "rule_name": "CVE-2021-44228 Log4Shell Exploitation",
            "_time": "2024-01-01T12:00:00Z",
            "severity": "critical",
            "rule_description": "Detection of CVE-2021-44228 exploitation attempts",
            "dest": "webserver01",
        }

        # Convert to NAS dict
        nas_dict = self.normalizer.to_extracted_dict(notable)

        # CVE info should be extracted
        assert nas_dict.get("cve_info") is not None
        cve_info = nas_dict["cve_info"]
        assert "CVE-2021-44228" in cve_info.get("ids", [])

        # Round-trip should preserve through raw_alert
        reconstructed = self.normalizer.from_alertcreate(nas_dict)
        assert reconstructed["rule_name"] == notable["rule_name"]

    def test_risk_scores_preservation(self):
        """Test that risk scores are preserved through raw_alert."""
        notable = {
            "rule_name": "High Risk Alert",
            "_time": "2024-01-01T12:00:00Z",
            "severity": "high",
            "risk_score": "100",
            "dest_risk_score": "75",
            "user_risk_score": "25",
            "dest": "server01",
            "user": "admin",
        }

        # Convert to NAS dict
        nas_dict = self.normalizer.to_extracted_dict(notable)

        # Raw alert should contain risk scores
        assert nas_dict.get("raw_alert") is not None
        raw_data = json.loads(nas_dict["raw_alert"])
        assert raw_data["risk_score"] == "100"
        assert raw_data["dest_risk_score"] == "75"
        assert raw_data["user_risk_score"] == "25"

        # Convert back to Notable
        reconstructed = self.normalizer.from_alertcreate(nas_dict)

        # Risk scores should be preserved from raw_alert
        assert reconstructed["risk_score"] == "100"
        assert reconstructed["dest_risk_score"] == "75"
        assert reconstructed["user_risk_score"] == "25"

    def test_web_info_roundtrip_with_xss_alert(self):
        """
        Test that web_info fields survive full NAS -> Notable -> NAS round-trip.
        """
        # Step 1: Create NAS alert dict with web_info (simulating real XSS attack)
        nas_alert = {
            "title": "Javascript Code Detected in Requested URL",
            "triggering_event_time": "2025-11-12T02:32:20Z",
            "severity": "medium",
            "source_vendor": "Splunk",
            "source_product": "Enterprise Security",
            "source_category": "Firewall",
            "rule_name": "Javascript Code Detected in Requested URL",
            "alert_type": "network",
            "device_action": "allowed",
            "primary_risk_entity_value": "10.10.20.17",
            "primary_risk_entity_type": "device",
            "primary_ioc_value": "91.234.56.42",
            "primary_ioc_type": "ip",
            "web_info": {
                "url": "https://10.10.20.17/search/?q=<script>alert(1)</script>",
                "http_method": "GET",
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "http_status": "302",
                "http_referrer": "https://google.com",
            },
            "network_info": {
                "src_ip": "91.234.56.42",
                "dest_ip": "10.10.20.17",
                "protocol": "tcp",
                "src_port": "49283",
                "dest_port": "443",
            },
            "raw_alert": '{"test": "data"}',
        }

        # Step 2: Convert NAS -> Notable
        reconstructed_notable = self.normalizer.from_alertcreate(nas_alert)

        # CRITICAL ASSERTIONS: These fields should be populated from web_info
        assert reconstructed_notable.get("url") is not None, (
            "url should be populated from web_info.url but was None"
        )
        assert (
            reconstructed_notable["url"]
            == "https://10.10.20.17/search/?q=<script>alert(1)</script>"
        ), f"Expected XSS URL but got: {reconstructed_notable.get('url')}"

        assert reconstructed_notable.get("http_method") is not None, (
            "http_method should be populated from web_info.method but was None"
        )
        assert reconstructed_notable["http_method"] == "GET", (
            f"Expected GET but got: {reconstructed_notable.get('http_method')}"
        )

        assert reconstructed_notable.get("user_agent") is not None, (
            "user_agent should be populated from web_info.user_agent but was None"
        )
        assert (
            reconstructed_notable["user_agent"]
            == "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        ), (
            f"Expected Mozilla user agent but got: {reconstructed_notable.get('user_agent')}"
        )

        # Step 3: Convert Notable -> NAS (simulating round-trip)
        nas_dict_back = self.normalizer.to_extracted_dict(reconstructed_notable)

        # FINAL ASSERTION: web_info should be preserved with all fields
        assert nas_dict_back.get("web_info") is not None, (
            "web_info should be preserved in round-trip but was None"
        )

        web_info_back = nas_dict_back["web_info"]
        assert (
            web_info_back.get("url")
            == "https://10.10.20.17/search/?q=<script>alert(1)</script>"
        ), (
            f"web_info.url not preserved. Expected XSS URL, got: {web_info_back.get('url')}"
        )
        assert web_info_back.get("http_method") == "GET", (
            f"web_info.http_method not preserved. Expected GET, got: {web_info_back.get('http_method')}"
        )
        assert (
            web_info_back.get("user_agent")
            == "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        ), f"web_info.user_agent not preserved. Got: {web_info_back.get('user_agent')}"
