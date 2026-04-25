"""Test Splunk normalizer with real notable fixtures.

Extended fields (primary_risk_entity_value, network_info, etc.) are validated
via to_extracted_dict() since AlertCreate no longer carries them.
"""

import json
from pathlib import Path

import pytest

from alert_normalizer.splunk import SplunkNotableNormalizer
from analysi.schemas.alert import AlertSeverity


class TestSplunkNormalizerRealNotables:
    """Test Splunk normalizer with real notable data."""

    @pytest.fixture
    def normalizer(self):
        """Create normalizer instance."""
        return SplunkNotableNormalizer()

    @pytest.fixture
    def fixtures(self):
        """Load all notable fixtures."""
        fixtures_file = Path("tests/fixtures/splunk_notables/all_fixtures.json")
        with open(fixtures_file) as f:
            return json.load(f)

    def test_user_notable_extraction(self, normalizer, fixtures):
        """Test that user field is properly extracted."""
        notable = fixtures["user_notable"]
        nas_dict = normalizer.to_extracted_dict(notable)

        # User should be extracted as primary risk entity
        assert nas_dict["primary_risk_entity_value"] == "ATTACKRANGE\\Administrator"
        assert nas_dict["primary_risk_entity_type"] == "user"

        # Should have proper severity and category
        assert nas_dict["severity"] == AlertSeverity.HIGH
        assert (
            nas_dict["source_category"] == "Identity"
        )  # access domain maps to Identity

    def test_process_notable_extraction(self, normalizer, fixtures):
        """Test process information extraction."""
        notable = fixtures["process_notable"]
        nas_dict = normalizer.to_extracted_dict(notable)

        # Process info should be extracted
        assert nas_dict["process_info"] is not None
        assert (
            nas_dict["process_info"]["cmd"]
            == '"C:\\Windows\\System32\\certutil.exe" -decode C:\\certutil\\encoded.txt C:\\temp\\calc.exe'
        )
        assert nas_dict["process_info"]["name"] == "certutil.exe"
        assert (
            nas_dict["process_info"]["parent_cmd"]
            == "C:\\Windows\\System32\\wbem\\WmiPrvSE.exe"
        )

        # Process should be primary IOC
        assert (
            nas_dict["primary_ioc_value"]
            == '"C:\\Windows\\System32\\certutil.exe" -decode C:\\certutil\\encoded.txt C:\\temp\\calc.exe'
        )
        assert nas_dict["primary_ioc_type"] == "process"

    def test_cve_notable_extraction(self, normalizer, fixtures):
        """Test CVE information extraction."""
        notable = fixtures["cve_notable"]
        nas_dict = normalizer.to_extracted_dict(notable)

        # CVE info should be extracted
        assert nas_dict["cve_info"] is not None
        assert nas_dict["cve_info"]["ids"] is not None
        assert "CVE-2021-44228" in nas_dict["cve_info"]["ids"]

        # Should detect exploitation context (exploitation_context field)
        assert nas_dict["cve_info"]["exploitation_context"] is True

    def test_network_notable_extraction(self, normalizer, fixtures):
        """Test network information extraction."""
        notable = fixtures["network_notable"]
        nas_dict = normalizer.to_extracted_dict(notable)

        # For this notable, src and dest are URLs which should NOT go into network_info
        # URLs are not network endpoints - they should be extracted as IOCs
        if "src" in notable and notable["src"].startswith(("http://", "https://")):
            # URLs should not populate network_info
            assert nas_dict["network_info"] is None
            # But the dest URL should be captured as an IOC
            iocs = [ioc for ioc in nas_dict["iocs"] if ioc["type"] == "url"]
            assert len(iocs) > 0
        else:
            # If not URLs, then network info should be extracted
            assert nas_dict["network_info"] is not None

            # Check for hostname vs IP differentiation
            if "src" in notable:
                src_val = notable["src"]
                # Check if it's an IP or hostname
                try:
                    import ipaddress

                    ipaddress.ip_address(src_val)
                    assert nas_dict["network_info"]["src_ip"] == src_val
                except ValueError:
                    assert nas_dict["network_info"]["src_hostname"] == src_val

    def test_action_notable_extraction(self, normalizer, fixtures):
        """Test device action extraction."""
        notable = fixtures["action_notable"]
        nas_dict = normalizer.to_extracted_dict(notable)

        # Device action should be normalized
        if notable.get("action"):
            assert nas_dict["device_action"] is not None
            # Should be lowercase and normalized
            assert nas_dict["device_action"] in [
                "allowed",
                "blocked",
                "detected",
                "quarantined",
                "alerted",
                "logged",
            ]

    def test_hostname_notable_extraction(self, normalizer, fixtures):
        """Test hostname vs IP differentiation."""
        notable = fixtures["hostname_notable"]
        nas_dict = normalizer.to_extracted_dict(notable)

        # Hostname should go to dest_hostname, not dest_ip
        assert nas_dict["network_info"] is not None
        assert (
            nas_dict["network_info"]["dest_hostname"]
            == "win-dc-7216619.attackrange.local"
        )
        assert nas_dict["network_info"].get("dest_ip") is None

    def test_security_domain_mapping(self, normalizer, fixtures):
        """Test security domain to source category mapping."""
        domain_mappings = {
            "endpoint": "EDR",
            "network": "Firewall",
            "access": "Identity",
            "threat": "IDS/IPS",
        }

        for domain, expected_category in domain_mappings.items():
            fixture_key = f"{domain}_domain_notable"
            if fixture_key in fixtures:
                notable = fixtures[fixture_key]
                nas_dict = normalizer.to_extracted_dict(notable)
                assert nas_dict["source_category"] == expected_category, (
                    f"Failed for domain: {domain}"
                )

    def test_source_event_id_extraction(self, normalizer, fixtures):
        """Test that Splunk event_id is preserved."""
        notable = fixtures["basic_notable"]
        # source_event_id IS in AlertBase, check on model
        alert = normalizer.to_alertcreate(notable)

        # Event ID should be preserved
        if notable.get("event_id"):
            assert alert.source_event_id == notable["event_id"]
            # Should match Splunk format
            assert "@@notable@@" in alert.source_event_id

    def test_comprehensive_field_extraction(self, normalizer, fixtures):
        """Test that all new schema fields are properly extracted when present."""
        for _name, notable in fixtures.items():
            nas_dict = normalizer.to_extracted_dict(notable)

            # Core fields should always be present
            assert nas_dict["title"] is not None
            assert nas_dict["severity"] is not None
            assert nas_dict["source_vendor"] == "Splunk"
            assert nas_dict["source_product"] == "Enterprise Security"

            # Conditional field extraction
            if notable.get("event_id"):
                assert nas_dict["source_event_id"] is not None

            if notable.get("action"):
                assert nas_dict["device_action"] is not None

            if notable.get("requested_url") or notable.get("http_method"):
                assert nas_dict["web_info"] is not None

            if notable.get("process") or notable.get("process_name"):
                assert nas_dict["process_info"] is not None

            if any("CVE" in str(v).upper() for v in notable.values() if v):
                assert nas_dict["cve_info"] is not None

            # Network info should only be extracted for actual network endpoints, not URLs
            if notable.get("src") or notable.get("dest"):
                src_val = notable.get("src", "")
                dest_val = notable.get("dest", "")
                # Check if values are URLs (which shouldn't go into network_info)
                if src_val.startswith(
                    ("http://", "https://", "ftp://")
                ) or dest_val.startswith(("http://", "https://", "ftp://")):
                    # URLs don't create network_info, they should be IOCs instead
                    pass  # network_info can be None
                else:
                    # Non-URL src/dest should populate network_info
                    assert nas_dict["network_info"] is not None

            if any(
                k in notable
                for k in ["file_name", "file_hash", "registry_path", "service_name"]
            ):
                assert nas_dict["other_activities"] is not None

    def test_raw_alert_preservation(self, normalizer, fixtures):
        """Test that raw alert is preserved."""
        notable = fixtures["basic_notable"]
        alert = normalizer.to_alertcreate(notable)

        # Raw alert should be preserved
        assert alert.raw_alert is not None
        raw_data = json.loads(alert.raw_alert)

        # Should contain original fields
        assert raw_data["rule_name"] == notable["rule_name"]
        assert raw_data["_time"] == notable["_time"]

    def test_no_incorrect_status_mapping(self, normalizer, fixtures):
        """Test that Splunk status field is NOT mapped to web_info."""
        for _name, notable in fixtures.items():
            if notable.get("status") and not notable.get("http_status"):
                nas_dict = normalizer.to_extracted_dict(notable)

                # Status should NOT create web_info
                if nas_dict.get("web_info"):
                    assert nas_dict["web_info"].get("http_status") is None

    def test_user_field_priority(self, normalizer, fixtures):
        """Test that user fields are prioritized over host fields."""
        # Create a test notable with both user and host fields
        notable = {
            "rule_name": "Test Alert",
            "_time": "2026-04-26T10:00:00Z",
            "severity": "high",
            "user": "john.doe",
            "dest": "server.example.com",
            "src": "10.0.0.1",
        }

        nas_dict = normalizer.to_extracted_dict(notable)

        # User should be primary risk entity, not the host
        assert nas_dict["primary_risk_entity_value"] == "john.doe"
        assert nas_dict["primary_risk_entity_type"] == "user"
