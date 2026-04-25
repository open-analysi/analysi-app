"""Test complete SPL format with all our fixes."""

from datetime import UTC
from unittest.mock import MagicMock

from analysi.utils.splunk_utils import (
    SPLUNK_EXACT_TIME_TOLERANCE_SECONDS,
    SPLGenerator,
)


class TestCompleteSPLFormat:
    """Test the complete SPL format with all fixes applied."""

    def test_complete_spl_format_example(self):
        """Test that a complete SPL query has the correct format."""
        from datetime import datetime

        generator = SPLGenerator(MagicMock())

        # Build a complete query manually to test format
        # 1. Index/sourcetype - no quotes
        index_query = generator._build_index_sourcetype_query(
            [("main", "pan:threat"), ("firewall", "cisco:asa")]
        )

        expected_index = "(index=main AND sourcetype=pan:threat) OR (index=firewall AND sourcetype=cisco:asa)"
        assert index_query == expected_index

        # 2. Time window with tolerance
        earliest, latest = generator._extract_time_window("2024-01-15T10:30:00Z", 300)
        event_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Latest should be event_time + tolerance
        assert (
            latest.timestamp()
            == event_time.timestamp() + SPLUNK_EXACT_TIME_TOLERANCE_SECONDS
        )

        # 3. IOCs and entities - with quotes
        ioc_filter = generator._build_entity_ioc_filter(
            "user@corp.example",
            ["192.168.1.100", "http://attacker.example/malware", "bad-domain.com"],
        )

        expected_filter = '("user@corp.example") AND ("192.168.1.100" OR "http://attacker.example/malware" OR "bad-domain.com")'
        assert ioc_filter == expected_filter

        # 4. Complete SPL format
        complete_spl = f"search {index_query} earliest={int(earliest.timestamp())} latest={int(latest.timestamp())} {ioc_filter}"

        # Verify the complete format:
        # - No quotes on index/sourcetype
        assert "index=main" in complete_spl
        assert "sourcetype=pan:threat" in complete_spl
        assert 'index="' not in complete_spl
        assert 'sourcetype="' not in complete_spl

        # - Time window includes tolerance
        assert (
            f"latest={int(event_time.timestamp() + SPLUNK_EXACT_TIME_TOLERANCE_SECONDS)}"
            in complete_spl
        )

        # - IOCs are quoted
        assert '"user@corp.example"' in complete_spl
        assert '"192.168.1.100"' in complete_spl
        assert '"http://attacker.example/malware"' in complete_spl
        assert '"bad-domain.com"' in complete_spl

        # - No escaped quotes
        assert '\\"' not in complete_spl

    def test_real_world_spl_examples(self):
        """Test with real-world examples of SPL generation."""
        generator = SPLGenerator(MagicMock())

        # Example 1: Authentication alert with user and IP
        auth_entity_filter = generator._build_entity_ioc_filter(
            "john.doe@corp.example", ["192.168.1.50", "10.0.0.100", "vpn.company.com"]
        )

        assert (
            auth_entity_filter
            == '("john.doe@corp.example") AND ("192.168.1.50" OR "10.0.0.100" OR "vpn.company.com")'
        )

        # Example 2: Malware alert with file hashes and URLs
        malware_entity_filter = generator._build_entity_ioc_filter(
            "workstation-01.corp.local",
            [
                "d41d8cd98f00b204e9800998ecf8427e",  # MD5
                "http://malware.site/payload.exe",  # URL
                "C:\\Windows\\Temp\\suspicious.exe",  # File path
                "evil-c2-server.com",  # Domain
            ],
        )

        # All should be quoted
        assert '"workstation-01.corp.local"' in malware_entity_filter
        assert '"d41d8cd98f00b204e9800998ecf8427e"' in malware_entity_filter
        assert '"http://malware.site/payload.exe"' in malware_entity_filter
        assert '"C:\\Windows\\Temp\\suspicious.exe"' in malware_entity_filter
        assert '"evil-c2-server.com"' in malware_entity_filter

        # Example 3: Network alert with various IOCs
        network_query = generator._build_index_sourcetype_query(
            [
                ("network", "paloalto:traffic"),
                ("firewall", "fortinet:utm"),
                ("proxy", "bluecoat:proxysg"),
            ]
        )

        # No quotes on index/sourcetype
        assert (
            network_query
            == "(index=network AND sourcetype=paloalto:traffic) OR (index=firewall AND sourcetype=fortinet:utm) OR (index=proxy AND sourcetype=bluecoat:proxysg)"
        )

    def test_spl_format_documentation(self):
        """Document the expected SPL format for reference."""
        # This test serves as documentation of the expected SPL format

        # Final SPL format should be:
        # search (index=<idx> AND sourcetype=<st>) OR ...
        #        earliest=<timestamp> latest=<timestamp+tolerance>
        #        ("<entity>") AND ("<ioc1>" OR "<ioc2>" OR ...)

        # Key points:
        # 1. Index and sourcetype: NO quotes (unless they contain spaces, which is rare)
        # 2. Time: latest includes tolerance to capture events at exact timestamp
        # 3. IOCs/entities: ALWAYS quoted to handle special characters
        # 4. No escaping of quotes in the values

        expected_format = """
        search (index=main AND sourcetype=pan:threat) OR (index=firewall AND sourcetype=cisco:asa)
               earliest=1705315500 latest=1705315801
               ("user@corp.example") AND ("192.168.1.100" OR "http://attacker.example/path" OR "malicious.domain.com")
        """.strip()

        # This is what we expect the SPL to look like
        assert "index=main AND sourcetype=pan:threat" in expected_format
        assert '"user@corp.example"' in expected_format
        assert '"http://attacker.example/path"' in expected_format
