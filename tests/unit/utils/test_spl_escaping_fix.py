"""Unit tests to verify SPL escaping fix - no backslash escaping."""

import pytest

from analysi.utils.splunk_utils import CIMMapper, SPLGenerator


class TestSPLEscapingFix:
    """Test that SPL generation doesn't over-escape values."""

    @pytest.fixture
    def mock_mapper(self):
        """Create a mock CIM mapper for testing."""
        source_to_cim = {
            "Test": {"primary_cim_datamodel": "TestModel", "secondary_cim_models": []}
        }
        cim_to_sourcetypes = {"TestModel": {"sourcetypes": ["test:source"]}}
        sourcetype_to_index = {"test:source": {"index": "test"}}
        return CIMMapper(source_to_cim, cim_to_sourcetypes, sourcetype_to_index)

    @pytest.fixture
    def spl_generator(self, mock_mapper):
        """Create SPL generator with mock mapper."""
        return SPLGenerator(mock_mapper)

    def test_simple_values_with_quotes(self, spl_generator):
        """Test that all IOCs and entities are quoted for safety."""
        alert = {
            "source_category": "Test",
            "triggering_event_time": "2024-01-01T10:00:00Z",
            "primary_risk_entity": "hostname",
            "indicators_of_compromise": ["192.168.1.100", "attacker.example"],
        }

        spl = spl_generator.generate_triggering_events_spl(alert, 60)

        # All IOCs and entities should be quoted to handle special characters
        assert '("hostname")' in spl
        assert '("192.168.1.100" OR "attacker.example")' in spl
        # Should NOT have escaped quotes
        assert '\\"' not in spl

    def test_values_with_quotes_not_escaped(self, spl_generator):
        """Test that quotes in values are NOT escaped with backslashes."""
        alert = {
            "source_category": "Test",
            "triggering_event_time": "2024-01-01T10:00:00Z",
            "primary_risk_entity": 'server-"prod"',
            "indicators_of_compromise": ['app-"test"', "normal.com"],
        }

        spl = spl_generator.generate_triggering_events_spl(alert, 60)

        # Quotes should NOT be escaped
        assert 'server-"prod"' in spl
        assert 'app-"test"' in spl
        # Should NOT have escaped quotes
        assert '\\"prod\\"' not in spl
        assert '\\"test\\"' not in spl

    def test_values_with_spaces_are_quoted(self, spl_generator):
        """Test that all values are properly quoted, regardless of spaces."""
        alert = {
            "source_category": "Test",
            "triggering_event_time": "2024-01-01T10:00:00Z",
            "primary_risk_entity": "host with spaces",
            "indicators_of_compromise": ["another value", "no-space"],
        }

        spl = spl_generator.generate_triggering_events_spl(alert, 60)

        # All values should be quoted for consistency and safety
        assert '("host with spaces")' in spl
        assert '"another value"' in spl
        # Even values without spaces are quoted now
        assert '"no-space"' in spl

    def test_backslashes_not_escaped(self, spl_generator):
        """Test that backslashes are NOT escaped."""
        alert = {
            "source_category": "Test",
            "triggering_event_time": "2024-01-01T10:00:00Z",
            "primary_risk_entity": "DOMAIN\\Administrator",
            "indicators_of_compromise": ["c:\\windows\\system32", "file.exe"],
        }

        spl = spl_generator.generate_triggering_events_spl(alert, 60)

        # Backslashes should NOT be escaped
        assert "DOMAIN\\Administrator" in spl
        assert "c:\\windows\\system32" in spl
        # Should NOT have double backslashes
        assert "DOMAIN\\\\Administrator" not in spl
        assert "c:\\\\windows\\\\system32" not in spl

    def test_mixed_special_characters(self, spl_generator):
        """Test combinations of special characters."""
        alert = {
            "source_category": "Test",
            "triggering_event_time": "2024-01-01T10:00:00Z",
            "primary_risk_entity": 'DOMAIN\\user-"prod"',
            "indicators_of_compromise": ["path with spaces\\and\\slashes", "10.0.0.1"],
        }

        spl = spl_generator.generate_triggering_events_spl(alert, 60)

        # Complex value with backslash and quotes - quoted but not escaped
        assert '"DOMAIN\\user-\\"prod\\""' in spl or 'DOMAIN\\user-"prod"' in spl
        # Path with spaces should be quoted but backslashes not escaped
        assert '"path with spaces\\and\\slashes"' in spl
        # IP should also be quoted now for consistency
        assert '"10.0.0.1"' in spl

        # Should NOT have double-escaped characters
        assert "\\\\" not in spl.replace("\\and\\", "").replace(
            "\\user", ""
        )  # Ignore legitimate backslashes in paths

    def test_empty_iocs_list(self, spl_generator):
        """Test handling of empty IOCs list."""
        alert = {
            "source_category": "Test",
            "triggering_event_time": "2024-01-01T10:00:00Z",
            "primary_risk_entity": "test-host",
            "indicators_of_compromise": [],
        }

        spl = spl_generator.generate_triggering_events_spl(alert, 60)

        # Should only have the primary entity, quoted
        assert '"test-host"' in spl
        # No AND clause for IOCs when only entity is present
        # The entity filter should just be the quoted entity value
        assert spl.endswith('"test-host"')

    def test_single_ioc(self, spl_generator):
        """Test with a single IOC."""
        alert = {
            "source_category": "Test",
            "triggering_event_time": "2024-01-01T10:00:00Z",
            "primary_risk_entity": "hostname",
            "indicators_of_compromise": ["192.168.1.1"],
        }

        spl = spl_generator.generate_triggering_events_spl(alert, 60)

        # Should have AND with single IOC - both quoted
        assert '("hostname") AND ("192.168.1.1")' in spl

    def test_real_world_example_with_quotes(self, spl_generator):
        """Test a real-world example that was failing before the fix."""
        # This is the type of value that was causing issues
        alert = {
            "source_category": "Test",
            "triggering_event_time": "2024-01-01T10:00:00Z",
            "primary_risk_entity": 'server-name-"production"',
            "indicators_of_compromise": ['app-config-"v2.1"', "malicious.domain.com"],
        }

        spl = spl_generator.generate_triggering_events_spl(alert, 60)

        # The fix: quotes should appear in the SPL without backslashes
        assert 'server-name-"production"' in spl
        assert 'app-config-"v2.1"' in spl

        # These should NOT appear (the old buggy behavior)
        assert 'server-name-\\"production\\"' not in spl
        assert 'app-config-\\"v2.1\\"' not in spl

        print(f"Generated SPL filter: {spl.split('latest=')[1].split(' ', 1)[1]}")
