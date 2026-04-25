"""Unit tests for SPL IOC and URL quoting behavior."""

from unittest.mock import MagicMock

from analysi.utils.splunk_utils import SPLGenerator


class TestSPLIOCQuoting:
    """Test proper quoting of IOCs and URLs in SPL generation."""

    def test_ioc_values_are_quoted(self):
        """Test that IOC values are always quoted to handle special characters."""
        generator = SPLGenerator(MagicMock())

        # Test various types of IOCs that need quoting
        test_cases = [
            # IP addresses
            ("192.168.1.100", ["10.0.0.1"], '"192.168.1.100"'),
            # URLs
            ("http://attacker.example/malware", [], '"http://attacker.example/malware"'),
            # Domains with special chars
            ("bad-domain.com", ["evil.org"], '"bad-domain.com"'),
            # File paths
            (
                "C:\\Windows\\System32\\evil.exe",
                [],
                '"C:\\Windows\\System32\\evil.exe"',
            ),
            # Email addresses
            ("attacker@attacker.example", [], '"attacker@attacker.example"'),
            # MD5 hashes
            (
                "d41d8cd98f00b204e9800998ecf8427e",
                [],
                '"d41d8cd98f00b204e9800998ecf8427e"',
            ),
            # SHA256 hashes
            (
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                [],
                '"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"',
            ),
            # Registry keys
            (
                "HKLM\\Software\\Microsoft\\Windows",
                [],
                '"HKLM\\Software\\Microsoft\\Windows"',
            ),
        ]

        for entity, iocs, expected_entity_quote in test_cases:
            result = generator._build_entity_ioc_filter(entity, iocs)
            assert expected_entity_quote in result, f"Entity {entity} should be quoted"

            # Check IOCs are also quoted
            for ioc in iocs:
                assert f'"{ioc}"' in result, f"IOC {ioc} should be quoted"

    def test_complex_urls_are_properly_quoted(self):
        """Test that complex URLs with query parameters are quoted correctly."""
        generator = SPLGenerator(MagicMock())

        # Complex URLs that definitely need quoting
        urls = [
            "https://attacker.example/path?param1=value1&param2=value2",
            "http://malware.site/download.php?file=payload.exe&key=abc123",
            "ftp://badserver.com:8080/files/malware.zip",
            "https://phishing.site/login?redirect=http%3A%2F%2Flegit.com",
        ]

        for url in urls:
            result = generator._build_entity_ioc_filter(url, [])
            # URL should be quoted
            assert f'"{url}"' in result, f"URL {url} should be quoted"
            # But quotes should NOT be escaped
            assert '\\"' not in result, "Quotes should not be escaped"

    def test_ioc_filter_with_multiple_iocs(self):
        """Test that multiple IOCs are all properly quoted and combined."""
        generator = SPLGenerator(MagicMock())

        primary_entity = "user@corp.example"
        iocs = [
            "192.168.1.100",
            "evil.domain.com",
            "http://malware.site/payload",
            "C:\\temp\\malicious.exe",
            "e3b0c44298fc1c149afbf4c8996fb924",
        ]

        result = generator._build_entity_ioc_filter(primary_entity, iocs)

        # Check primary entity is quoted
        assert '"user@corp.example"' in result

        # Check all IOCs are quoted
        for ioc in iocs:
            assert f'"{ioc}"' in result, f"IOC {ioc} should be quoted"

        # Check structure (entity AND (ioc1 OR ioc2 OR ...))
        assert " AND " in result
        assert " OR " in result
        assert result.startswith('("user@corp.example") AND (')

    def test_no_escaping_of_quotes(self):
        """Test that quotes are not escaped in the output."""
        generator = SPLGenerator(MagicMock())

        # Values that would traditionally need escaping
        test_values = [
            "value with spaces",
            "path/with/slashes",
            "domain.with.dots.com",
            "url?with=params&and=values",
        ]

        for value in test_values:
            result = generator._build_entity_ioc_filter(value, [])
            # Should have quotes
            assert f'"{value}"' in result
            # Should NOT have escaped quotes
            assert '\\"' not in result
            assert "\\'" not in result

    def test_empty_iocs_list(self):
        """Test handling of empty IOCs list."""
        generator = SPLGenerator(MagicMock())

        result = generator._build_entity_ioc_filter("test-entity", [])

        # Should just return the quoted entity
        assert result == '"test-entity"'

    def test_special_characters_in_iocs(self):
        """Test that IOCs with special characters are handled properly."""
        generator = SPLGenerator(MagicMock())

        # IOCs with various special characters that Splunk might interpret
        special_iocs = [
            "value|with|pipes",
            "value*with*wildcards",
            "value[with]brackets",
            "value(with)parens",
            "value{with}braces",
            "value^with^carets",
            "value$with$dollars",
            "value+with+plus",
            "value=with=equals",
            "value<with>angles",
            "value&with&ampersands",
            "value;with;semicolons",
            "value:with:colons",
            "value@with@at",
            "value#with#hash",
            "value%20with%20encoding",
        ]

        for ioc in special_iocs:
            result = generator._build_entity_ioc_filter("test", [ioc])
            # IOC should be quoted
            assert f'"{ioc}"' in result, (
                f"IOC {ioc} with special chars should be quoted"
            )
            # Quotes should not be escaped
            assert '\\"' not in result

    def test_escape_spl_value_does_not_escape(self):
        """Test that _escape_spl_value doesn't actually escape anything."""
        generator = SPLGenerator(MagicMock())

        # Test that the escape function returns values unchanged
        test_values = [
            'value"with"quotes',
            "value'with'apostrophes",
            "value\\with\\backslashes",
            "normal-value",
            "192.168.1.1",
            "http://test.com",
        ]

        for value in test_values:
            escaped = generator._escape_spl_value(value)
            assert escaped == value, (
                "Values should not be modified by _escape_spl_value"
            )
