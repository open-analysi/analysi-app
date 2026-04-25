"""Integration test for SPL generation formatting."""

from datetime import UTC

import pytest

from analysi.utils.splunk_utils import (
    SPLUNK_EXACT_TIME_TOLERANCE_SECONDS,
    SPLGenerator,
)


@pytest.mark.integration
class TestSPLGenerationFormatting:
    """Test SPL generation with proper formatting."""

    def test_spl_format_no_quotes_on_index_sourcetype(self):
        """Test that generated SPL doesn't have quotes on index and sourcetype."""
        generator = SPLGenerator(None)

        # Create a sample alert

        # Mock CIM mappings

        # Manually call the internal method to test formatting
        index_sourcetype_pairs = [
            ("wineventlog", "WinEventLog:Security"),
            ("os", "linux_secure"),
        ]

        query = generator._build_index_sourcetype_query(index_sourcetype_pairs)

        # Verify no quotes around index and sourcetype values
        assert "index=wineventlog" in query
        assert "sourcetype=WinEventLog:Security" in query
        assert "index=os" in query
        assert "sourcetype=linux_secure" in query

        # Verify quotes are NOT present
        assert 'index="' not in query
        assert 'sourcetype="' not in query

    def test_spl_time_tolerance_applied(self):
        """Test that time tolerance is correctly applied to latest time."""
        from datetime import datetime

        generator = SPLGenerator(None)

        # Test time window extraction
        triggering_time = "2024-01-15T10:30:00Z"
        lookback = 300  # 5 minutes

        earliest, latest = generator._extract_time_window(triggering_time, lookback)

        # Expected times
        event_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        expected_earliest = event_time.timestamp() - lookback
        expected_latest = event_time.timestamp() + SPLUNK_EXACT_TIME_TOLERANCE_SECONDS

        # Verify times match expectations
        assert earliest.timestamp() == expected_earliest
        assert latest.timestamp() == expected_latest

        # Verify that an event at exactly the triggering time would be included
        # This is critical because Splunk's 'latest' is exclusive
        assert latest.timestamp() > event_time.timestamp()

    def test_complete_spl_generation_format(self):
        """Test complete SPL generation with proper formatting."""
        from unittest.mock import AsyncMock, MagicMock

        generator = SPLGenerator(MagicMock())

        # Mock CIM loader
        generator._cim_loader = AsyncMock()
        generator._cim_loader.load_source_to_cim_mappings = AsyncMock(
            return_value={
                "cim_datamodel": "Authentication",
                "sourcetypes": ["WinEventLog:Security"],
                "indexes": ["wineventlog"],
            }
        )

        # Generate SPL (synchronous test of the format)
        index_sourcetype_pairs = [("wineventlog", "WinEventLog:Security")]
        query = generator._build_index_sourcetype_query(index_sourcetype_pairs)

        # The query should look like:
        # (index=wineventlog AND sourcetype=WinEventLog:Security)
        expected = "(index=wineventlog AND sourcetype=WinEventLog:Security)"
        assert query == expected

        # Test with multiple pairs
        pairs = [
            ("main", "pan:threat"),
            ("firewall", "cisco:asa"),
            ("network", "fortinet:firewall"),
        ]
        query = generator._build_index_sourcetype_query(pairs)

        # Should be OR-joined without quotes
        assert "(index=main AND sourcetype=pan:threat)" in query
        assert "(index=firewall AND sourcetype=cisco:asa)" in query
        assert "(index=network AND sourcetype=fortinet:firewall)" in query
        assert " OR " in query

        # Count OR occurrences (should be 2 for 3 pairs)
        assert query.count(" OR ") == 2
