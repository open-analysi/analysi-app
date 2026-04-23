"""Test extraction of entity and IOC lists from Splunk notables."""

from alert_normalizer.mappers.splunk_notable_lists import (
    detect_hash_type,
    extract_all_iocs,
    extract_all_risk_entities,
    is_ip_address,
)
from alert_normalizer.splunk import SplunkNotableNormalizer


class TestSplunkListExtraction:
    """Test extraction of entity and IOC lists."""

    def test_extract_multiple_users(self):
        """Test extraction of multiple user entities."""
        notable = {
            "user": "john.doe",
            "src_user": "admin",
            "dest_user": "guest",
            "account": "service-account",
        }

        entities = extract_all_risk_entities(notable)

        assert entities is not None
        assert len(entities) == 4

        # Check each user entity
        values = [e["value"] for e in entities]
        assert "john.doe" in values
        assert "admin" in values
        assert "guest" in values
        assert "service-account" in values

        # All should be type "user"
        assert all(e["type"] == "user" for e in entities)

    def test_extract_mixed_entities(self):
        """Test extraction of mixed entity types."""
        notable = {
            "user": "john.doe",
            "dest": "server01.example.com",  # hostname
            "src": "192.168.1.100",  # IP
            "src_user": "admin",
            "dest_ip": "10.0.0.1",
        }

        entities = extract_all_risk_entities(notable)

        assert entities is not None
        assert len(entities) == 5

        # Check entity types
        user_entities = [e for e in entities if e["type"] == "user"]
        assert len(user_entities) == 2

        device_entities = [e for e in entities if e["type"] == "device"]
        assert len(device_entities) == 1
        assert device_entities[0]["value"] == "server01.example.com"

        ip_entities = [e for e in entities if e["type"] == "ip"]
        assert len(ip_entities) == 2
        assert "192.168.1.100" in [e["value"] for e in ip_entities]
        assert "10.0.0.1" in [e["value"] for e in ip_entities]

    def test_extract_multiple_iocs(self):
        """Test extraction of multiple IOC types."""
        notable = {
            "requested_url": "http://evil.com/malware.exe",
            "domain": "evil.com",
            "file_hash": "d41d8cd98f00b204e9800998ecf8427e",
            "process": "powershell.exe -enc Base64String",
            "dest_ip": "185.220.101.45",  # External IP (IOC)
            "attacker_ip": "203.0.113.1",  # Another external IP
        }

        iocs = extract_all_iocs(notable)

        assert iocs is not None
        assert len(iocs) >= 5

        # Check IOC types
        ioc_types = {ioc["type"] for ioc in iocs}
        assert "url" in ioc_types
        assert "domain" in ioc_types
        assert "filehash" in ioc_types
        assert "process" in ioc_types
        assert "ip" in ioc_types

    def test_cves_not_in_iocs(self):
        """Test that CVEs are NOT extracted as IOCs (they're vulnerabilities, not attack artifacts)."""
        notable = {
            "rule_name": "Log4j Exploitation CVE-2021-44228",
            "rule_description": "Detects CVE-2021-45046 and CVE-2021-45105 exploitation",
        }

        iocs = extract_all_iocs(notable)

        # CVEs should NOT be in IOCs list - they go in cve_info instead
        if iocs:
            for ioc in iocs:
                assert "CVE" not in str(ioc.get("value", ""))

    def test_no_duplicate_values(self):
        """Test that duplicate values are not extracted multiple times."""
        notable = {
            "src": "192.168.1.100",
            "src_ip": "192.168.1.100",  # Same IP
            "client_ip": "192.168.1.100",  # Same IP again
            "user": "john.doe",
            "src_user": "john.doe",  # Same user
        }

        entities = extract_all_risk_entities(notable)
        iocs = extract_all_iocs(notable)

        # Should only have one entry for each unique value
        entity_values = [e["value"] for e in entities] if entities else []
        assert entity_values.count("john.doe") == 1
        assert entity_values.count("192.168.1.100") == 1

        # 192.168.1.100 is internal IP, should NOT be in IOCs
        ioc_values = [i["value"] for i in iocs] if iocs else []
        assert "192.168.1.100" not in ioc_values  # Internal IPs are not IOCs

    def test_clean_dirty_values(self):
        """Test cleaning of values with artifacts."""
        notable = {
            "user": "john.doe\\nNONE_MAPPED",  # Has artifact
            "dest": "server01.example.com",
        }

        entities = extract_all_risk_entities(notable)

        assert entities is not None
        user_entity = next(e for e in entities if e["type"] == "user")
        assert user_entity["value"] == "john.doe"  # Artifact removed

    def test_is_ip_address(self):
        """Test IP address detection."""
        assert is_ip_address("192.168.1.1") is True
        assert is_ip_address("10.0.0.1") is True
        assert is_ip_address("2001:0db8:85a3:0000:0000:8a2e:0370:7334") is True
        assert is_ip_address("server.example.com") is False
        assert is_ip_address("not-an-ip") is False
        assert is_ip_address("") is False

    def test_detect_hash_type(self):
        """Test hash type detection."""
        assert detect_hash_type("d41d8cd98f00b204e9800998ecf8427e") == "md5"
        assert detect_hash_type("da39a3ee5e6b4b0d3255bfef95601890afd80709") == "sha1"
        assert (
            detect_hash_type(
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            )
            == "sha256"
        )
        assert detect_hash_type("md5:d41d8cd98f00b204e9800998ecf8427e") == "md5"
        assert detect_hash_type("short") == "unknown"

    def test_full_normalizer_with_lists(self):
        """Test that the normalizer properly includes entity and IOC lists."""
        notable = {
            "rule_name": "Multi-Entity Alert",
            "_time": "2025-01-15T10:00:00Z",
            "severity": "high",
            "user": "john.doe",
            "src_user": "admin",
            "dest": "server01.example.com",
            "src": "192.168.1.100",
            "requested_url": "http://evil.com/malware",
            "file_hash": "d41d8cd98f00b204e9800998ecf8427e",  # Valid MD5 hash
            "process": "malware.exe",
        }

        normalizer = SplunkNotableNormalizer()
        nas_dict = normalizer.to_extracted_dict(notable)

        # Should have both primary fields and lists
        assert nas_dict["primary_risk_entity_value"] == "john.doe"
        assert nas_dict["primary_ioc_value"] == "http://evil.com/malware"

        # Should have entity list
        assert nas_dict["risk_entities"] is not None
        assert len(nas_dict["risk_entities"]) >= 4  # users and devices

        # Should have IOC list
        assert nas_dict["iocs"] is not None
        assert len(nas_dict["iocs"]) >= 4  # URL, hash, process, IP

    def test_external_ip_extraction(self):
        """Test that external IPs are properly extracted as IOCs."""
        notable = {
            "src_ip": "192.168.1.100",  # Internal - should be entity
            "dest_ip": "185.220.101.45",  # External - should be IOC
            "src": "10.0.0.1",  # Internal - should be entity
            "dest": "8.8.8.8",  # External - should be IOC
        }

        entities = extract_all_risk_entities(notable)
        iocs = extract_all_iocs(notable)

        # Check entities have internal IPs
        entity_values = [e["value"] for e in entities] if entities else []
        assert "192.168.1.100" in entity_values
        assert "10.0.0.1" in entity_values

        # Check IOCs have external IPs
        ioc_values = [i["value"] for i in iocs] if iocs else []
        assert "185.220.101.45" in ioc_values
        assert "8.8.8.8" in ioc_values

    def test_hash_with_metadata(self):
        """Test hash IOC includes hash type metadata."""
        notable = {
            "file_hash": "d41d8cd98f00b204e9800998ecf8427e",
            "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        }

        iocs = extract_all_iocs(notable)

        assert iocs is not None
        hash_iocs = [ioc for ioc in iocs if ioc["type"] == "filehash"]
        assert len(hash_iocs) == 2

        # Check hash type metadata
        md5_ioc = next(ioc for ioc in hash_iocs if ioc["value"].startswith("d41d"))
        assert md5_ioc["hash_type"] == "md5"

        sha256_ioc = next(ioc for ioc in hash_iocs if ioc["value"].startswith("e3b0"))
        assert sha256_ioc["hash_type"] == "sha256"

    def test_user_agent_extraction_suspicious(self):
        """Test that suspicious user agents are extracted as high-confidence IOCs."""
        notable = {
            "rule_name": "SQL Injection Attack",
            "user_agent": "sqlmap/1.5.2",
            "http_method": "GET",
            "requested_url": "/login.php?id=1' OR '1'='1",
        }

        iocs = extract_all_iocs(notable)

        assert iocs is not None
        user_agent_iocs = [ioc for ioc in iocs if ioc["type"] == "user_agent"]
        assert len(user_agent_iocs) == 1

        ua_ioc = user_agent_iocs[0]
        assert ua_ioc["value"] == "sqlmap/1.5.2"
        assert ua_ioc["confidence"] == 90  # sqlmap is a known attack tool (high=90)
        assert ua_ioc["source_field"] == "user_agent"

    def test_user_agent_extraction_scanner(self):
        """Test that scanner user agents are extracted as high-confidence IOCs."""
        notable = {
            "rule_name": "Scanner Activity",
            "user_agent": "Mozilla/5.0 zgrab/0.x",
            "dest_ip": "185.220.101.45",
        }

        iocs = extract_all_iocs(notable)

        assert iocs is not None
        user_agent_iocs = [ioc for ioc in iocs if ioc["type"] == "user_agent"]
        assert len(user_agent_iocs) == 1

        ua_ioc = user_agent_iocs[0]
        assert ua_ioc["value"] == "Mozilla/5.0 zgrab/0.x"
        assert ua_ioc["confidence"] == 90  # zgrab is a known scanner (high=90)

    def test_user_agent_extraction_web_attack_context(self):
        """Test that any user agent in web attack context is extracted."""
        notable = {
            "rule_name": "PowerShell Command Execution via Web",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0",
            "http_method": "POST",
            "requested_url": "/execute?cmd=powershell%20-enc%20Base64String",
            "dest_ip": "192.168.1.100",
        }

        iocs = extract_all_iocs(notable)

        assert iocs is not None
        user_agent_iocs = [ioc for ioc in iocs if ioc["type"] == "user_agent"]
        assert len(user_agent_iocs) == 1  # Normal UA but in attack context

        ua_ioc = user_agent_iocs[0]
        assert (
            ua_ioc["value"] == "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0"
        )
        assert (
            ua_ioc["confidence"] == 70
        )  # Normal UA gets medium confidence (medium=70)

    def test_user_agent_extracted_from_all_notables(self):
        """Test that user agents are extracted from all Notables.

        Policy: Notables are already filtered alerts, so any user_agent is worth preserving.
        Better to include than miss a legitimate IOC.
        """
        notable = {
            "rule_name": "High Volume Traffic",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0",
            "http_method": "GET",
            "requested_url": "/index.html",
        }

        iocs = extract_all_iocs(notable)

        # Should extract user agent from any Notable event
        assert iocs is not None
        user_agent_iocs = [ioc for ioc in iocs if ioc["type"] == "user_agent"]
        assert len(user_agent_iocs) == 1
        assert (
            user_agent_iocs[0]["value"]
            == "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0"
        )
        assert (
            user_agent_iocs[0]["confidence"] == 70
        )  # Not suspicious, but still preserved (medium=70)

    def test_user_agent_malware_patterns(self):
        """Test detection of various malware and attack tool user agents."""
        # Confidence: 90=high, 70=medium, 50=low
        test_cases = [
            ("nikto/2.1.5", 90),  # Vulnerability scanner
            ("Havij/1.17", 90),  # SQL injection tool
            ("acunetix-wvs-test", 90),  # Web vulnerability scanner
            ("nessus/6.12.1", 90),  # Vulnerability scanner
            ("metasploit", 90),  # Exploitation framework
            ("burpsuite/2.1", 90),  # Security testing tool
            ("python-requests/2.25.1", 90),  # Marked as suspicious in our patterns
            ("curl/7.68.0", 90),  # Marked as suspicious in our patterns
            ("wget/1.20.3", 90),  # Marked as suspicious in our patterns
        ]

        for user_agent, expected_confidence in test_cases:
            notable = {
                "rule_name": "Suspicious Web Activity",
                "user_agent": user_agent,
                "http_method": "GET",
                "requested_url": "/admin/config.php",
            }

            iocs = extract_all_iocs(notable)

            if iocs:
                user_agent_iocs = [ioc for ioc in iocs if ioc["type"] == "user_agent"]
                if user_agent_iocs:
                    ua_ioc = user_agent_iocs[0]
                    assert ua_ioc["confidence"] == expected_confidence, (
                        f"User agent '{user_agent}' should have confidence {expected_confidence}"
                    )

    def test_user_agent_empty_and_none(self):
        """Test handling of empty and None user agent values."""
        notable = {
            "rule_name": "Web Attack",
            "user_agent": "",  # Empty string
            "http_user_agent": None,  # None value
        }

        iocs = extract_all_iocs(notable)

        # Should not extract empty or None user agents
        if iocs:
            user_agent_iocs = [ioc for ioc in iocs if ioc["type"] == "user_agent"]
            assert len(user_agent_iocs) == 0

    def test_user_agent_deduplication(self):
        """Test that duplicate user agents are not extracted multiple times."""
        notable = {
            "rule_name": "Web Attack",
            "user_agent": "sqlmap/1.5.2",
            "http_user_agent": "sqlmap/1.5.2",  # Same value in different field
        }

        iocs = extract_all_iocs(notable)

        assert iocs is not None
        user_agent_iocs = [ioc for ioc in iocs if ioc["type"] == "user_agent"]
        assert len(user_agent_iocs) == 1  # Should deduplicate

    def test_user_agent_with_full_normalizer(self):
        """Test user agent extraction through full normalizer."""
        notable = {
            "rule_name": "PowerShell Exploit via Web",
            "_time": "2025-01-15T10:00:00Z",
            "severity": "critical",
            "user": "admin",
            "user_agent": "Mozilla/5.0 zgrab/0.x",
            "http_method": "POST",
            "requested_url": "/api/execute?cmd=powershell%20-enc%20Base64",
            "dest_ip": "185.220.101.45",
        }

        normalizer = SplunkNotableNormalizer()
        nas_dict = normalizer.to_extracted_dict(notable)

        # Check that user_agent is in IOCs list
        assert nas_dict["iocs"] is not None
        user_agent_iocs = [
            ioc for ioc in nas_dict["iocs"] if ioc["type"] == "user_agent"
        ]
        assert len(user_agent_iocs) == 1

        ua_ioc = user_agent_iocs[0]
        assert ua_ioc["value"] == "Mozilla/5.0 zgrab/0.x"
        assert ua_ioc["confidence"] == 90  # high=90
