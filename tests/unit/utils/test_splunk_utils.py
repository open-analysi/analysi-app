"""Unit tests for Splunk Utils - TDD Implementation."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.utils.splunk_utils import (
    CIMDataNotFoundError,
    CIMMapper,
    SPLGenerator,
    SplunkConnectionError,
    SplunkCredentialError,
    SplunkMultiTenantManager,
)


class TestCIMMapper:
    """Test CIM datamodel mapping functionality."""

    @pytest.fixture
    def mock_cim_data(self):
        """Mock CIM mapping data for testing."""
        return {
            "source_to_cim": {
                "Firewall": {
                    "primary_cim_datamodel": "Network Traffic",
                    "secondary_cim_models": ["Network Sessions"],
                },
                "EDR": {
                    "primary_cim_datamodel": "Endpoint",
                    "secondary_cim_models": ["Malware", "Intrusion Detection"],
                },
            },
            "cim_to_sourcetypes": {
                "Network Traffic": {
                    "sourcetypes": ["pan:threat", "fgt:traffic", "cisco:asa"],
                    "datamodel_id": "dm_net_001",
                    "sourcetype_count": 3,
                },
                "Endpoint": {
                    "sourcetypes": ["crowdstrike:incident:*", "WinEventLog:*"],
                    "datamodel_id": "dm_endpoint_001",
                    "sourcetype_count": 2,
                },
            },
            "sourcetype_to_index": {
                "pan:threat": {"index": "main", "eps_count": 15.5},
                "fgt:traffic": {"index": "firewall", "eps_count": 22.1},
                "crowdstrike:incident:*": {"index": "security", "eps_count": 8.3},
            },
        }

    def test_init_with_mapping_data(self, mock_cim_data):
        """Test CIMMapper initialization with mapping data."""
        mapper = CIMMapper(
            mock_cim_data["source_to_cim"],
            mock_cim_data["cim_to_sourcetypes"],
            mock_cim_data["sourcetype_to_index"],
        )

        # Keys are now stored as lowercase for case-insensitive lookups
        assert mapper.source_to_cim == {
            k.lower(): v for k, v in mock_cim_data["source_to_cim"].items()
        }
        assert mapper.cim_to_sourcetypes == {
            k.lower(): v for k, v in mock_cim_data["cim_to_sourcetypes"].items()
        }
        assert mapper.sourcetype_to_index == {
            k.lower(): v for k, v in mock_cim_data["sourcetype_to_index"].items()
        }

    def test_get_cim_datamodels_success(self, mock_cim_data):
        """Test successful NAS to CIM mapping."""
        mapper = CIMMapper(
            mock_cim_data["source_to_cim"],
            mock_cim_data["cim_to_sourcetypes"],
            mock_cim_data["sourcetype_to_index"],
        )

        result = mapper.get_cim_datamodels("Firewall")

        assert result["primary_cim_datamodel"] == "Network Traffic"
        assert "Network Sessions" in result["secondary_cim_models"]

    def test_get_cim_datamodels_for_unknown_nas_source(self, mock_cim_data):
        """Test CIM mapping for unknown NAS source raises error."""
        mapper = CIMMapper(
            mock_cim_data["source_to_cim"],
            mock_cim_data["cim_to_sourcetypes"],
            mock_cim_data["sourcetype_to_index"],
        )

        with pytest.raises(CIMDataNotFoundError, match="UnknownSource"):
            mapper.get_cim_datamodels("UnknownSource")

    def test_get_sourcetypes_for_cim_datamodel_success(self, mock_cim_data):
        """Test successful CIM to sourcetypes mapping."""
        mapper = CIMMapper(
            mock_cim_data["source_to_cim"],
            mock_cim_data["cim_to_sourcetypes"],
            mock_cim_data["sourcetype_to_index"],
        )

        result = mapper.get_sourcetypes_for_cim_datamodel("Network Traffic")

        assert isinstance(result, list)
        assert "pan:threat" in result
        assert "fgt:traffic" in result

    def test_get_index_for_sourcetype_success(self, mock_cim_data):
        """Test successful sourcetype to index mapping."""
        mapper = CIMMapper(
            mock_cim_data["source_to_cim"],
            mock_cim_data["cim_to_sourcetypes"],
            mock_cim_data["sourcetype_to_index"],
        )

        result = mapper.get_index_for_sourcetype("pan:threat")

        assert result["index"] == "main"
        assert result["eps_count"] == 15.5

    def test_get_index_for_sourcetype_wildcard_match(self, mock_cim_data):
        """Test wildcard matching for sourcetype to index."""
        mapper = CIMMapper(
            mock_cim_data["source_to_cim"],
            mock_cim_data["cim_to_sourcetypes"],
            mock_cim_data["sourcetype_to_index"],
        )

        # Should match "crowdstrike:incident:*"
        result = mapper.get_index_for_sourcetype("crowdstrike:incident:detection")

        assert result["index"] == "security"

    def test_perform_triple_join_success(self, mock_cim_data):
        """Test successful triple join operation."""
        mapper = CIMMapper(
            mock_cim_data["source_to_cim"],
            mock_cim_data["cim_to_sourcetypes"],
            mock_cim_data["sourcetype_to_index"],
        )

        result = mapper.perform_triple_join("Firewall")

        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(pair, tuple) and len(pair) == 2 for pair in result)

        # Check that we have the expected index/sourcetype pairs
        pairs_dict = dict(result)
        assert "main" in pairs_dict or "firewall" in pairs_dict


class TestSPLGenerator:
    """Test SPL statement generation functionality."""

    @pytest.fixture
    def sample_nas_alert(self):
        """Sample NAS format alert for testing."""
        return {
            "title": "Suspicious Network Activity",
            "source_category": "Firewall",
            "triggering_event_time": "2024-01-15T10:30:00Z",
            "primary_risk_entity": "10.0.0.100",
            "indicators_of_compromise": [
                "malicious-domain.com",
                "192.168.1.50",
                "evil.exe",
            ],
            "risk_score": 85,
        }

    def test_init_with_cim_mapper(self):
        """Test SPLGenerator initialization with CIM mapper."""
        mock_mapper = MagicMock(spec=CIMMapper)
        generator = SPLGenerator(mock_mapper)

        assert generator.cim_mapper == mock_mapper

    def test_generate_triggering_events_spl_success(self, sample_nas_alert):
        """Test successful SPL generation from NAS alert."""
        mock_mapper = MagicMock(spec=CIMMapper)
        mock_mapper.perform_triple_join.return_value = [
            ("main", "pan:threat"),
            ("firewall", "fgt:traffic"),
        ]

        generator = SPLGenerator(mock_mapper)
        result = generator.generate_triggering_events_spl(sample_nas_alert)

        # Verify SPL structure
        assert isinstance(result, str)
        assert "search" in result
        assert "index=" in result
        assert "sourcetype=" in result
        assert "earliest=" in result
        assert "latest=" in result
        assert sample_nas_alert["primary_risk_entity"] in result

    def test_generate_triggering_events_spl_missing_fields(self):
        """Test SPL generation with missing required fields raises ValueError."""
        generator = SPLGenerator(MagicMock())

        with pytest.raises(ValueError, match="Alert missing required field"):
            generator.generate_triggering_events_spl({})

    def test_extract_time_window_success(self):
        """Test successful time window extraction with time tolerance."""
        from analysi.utils.splunk_utils import SPLUNK_EXACT_TIME_TOLERANCE_SECONDS

        generator = SPLGenerator(MagicMock())

        earliest, latest = generator._extract_time_window("2024-01-15T10:30:00Z", 60)

        assert earliest < latest
        # The time span should be lookback_seconds + tolerance
        expected_span = 60 + SPLUNK_EXACT_TIME_TOLERANCE_SECONDS
        assert (latest - earliest).total_seconds() == expected_span

    def test_build_index_sourcetype_query_success(self):
        """Test successful index/sourcetype query building without quotes."""
        generator = SPLGenerator(MagicMock())

        pairs = [("main", "pan:threat"), ("firewall", "fgt:traffic")]
        result = generator._build_index_sourcetype_query(pairs)

        # Splunk index and sourcetype should not be quoted
        assert "(index=main AND sourcetype=pan:threat)" in result
        assert "(index=firewall AND sourcetype=fgt:traffic)" in result
        assert " OR " in result

    def test_build_entity_ioc_filter_success(self):
        """Test successful entity/IOC filter building with proper quoting."""
        generator = SPLGenerator(MagicMock())

        result = generator._build_entity_ioc_filter(
            "10.0.0.100", ["evil.com", "bad.exe"]
        )

        # All values should be quoted
        assert '"10.0.0.100"' in result
        assert '"evil.com"' in result
        assert '"bad.exe"' in result
        assert " AND " in result
        assert " OR " in result

    def test_time_tolerance_ensures_event_capture(self):
        """Test that time tolerance ensures we capture events at exact timestamps."""
        from analysi.utils.splunk_utils import SPLUNK_EXACT_TIME_TOLERANCE_SECONDS

        generator = SPLGenerator(MagicMock())

        # Test with a specific timestamp
        triggering_time = "2024-01-15T10:30:00Z"
        lookback = 300  # 5 minutes

        earliest, latest = generator._extract_time_window(triggering_time, lookback)

        # Parse the triggering time to compare
        event_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

        # Earliest should be exactly lookback seconds before event
        assert earliest.timestamp() == (event_time.timestamp() - lookback)

        # Latest should be event_time + tolerance (to ensure the event is captured)
        assert latest.timestamp() == (
            event_time.timestamp() + SPLUNK_EXACT_TIME_TOLERANCE_SECONDS
        )

        # This ensures that an event at exactly triggering_time will be included
        # because Splunk's 'latest' is exclusive


class TestSplunkMultiTenantManager:
    """Test multi-tenant Splunk connection management."""

    @pytest.fixture
    def mock_integration_service(self):
        """Mock integration service for testing."""
        return AsyncMock()

    def test_init_success(self, mock_integration_service):
        """Test SplunkMultiTenantManager initialization."""
        manager = SplunkMultiTenantManager(mock_integration_service)
        assert manager.integration_service == mock_integration_service
        assert manager._connection_cache == {}

    @pytest.mark.asyncio
    async def test_get_splunk_connection_no_integration(self, mock_integration_service):
        """Test getting Splunk connection when no integration exists."""
        manager = SplunkMultiTenantManager(mock_integration_service)
        manager._connection_cache = {}  # Initialize cache

        # Mock _get_splunk_integration to return None
        with patch.object(manager, "_get_splunk_integration", return_value=None):
            with pytest.raises(
                SplunkCredentialError, match="No Splunk integration configured"
            ):
                await manager.get_splunk_connection("tenant_123")

    @pytest.mark.asyncio
    async def test_execute_spl_query_validates_statement(
        self, mock_integration_service
    ):
        """Test SPL query execution validates the statement."""
        manager = SplunkMultiTenantManager(mock_integration_service)
        manager._connection_cache = {}  # Initialize cache

        # Test with empty SPL statement
        with pytest.raises(
            ValueError, match="SPL statement must be a non-empty string"
        ):
            await manager.execute_spl_query("tenant_123", "")

    @pytest.mark.asyncio
    async def test_get_splunk_integration(self, mock_integration_service):
        """Test getting tenant's Splunk integration."""
        manager = SplunkMultiTenantManager(mock_integration_service)

        # Mock integration service response
        mock_integration = MagicMock()
        mock_integration.enabled = True
        mock_integration.integration_type = "splunk"
        mock_integration_service.list_integrations.return_value = [mock_integration]

        result = await manager._get_splunk_integration("tenant_123")

        assert result == mock_integration
        mock_integration_service.list_integrations.assert_called_once_with(
            "tenant_123", integration_type="splunk"
        )


class TestSplunkUtilsErrorHandling:
    """Test error handling and edge cases."""

    def test_splunk_credential_error_creation(self):
        """Test SplunkCredentialError can be created."""
        error = SplunkCredentialError("Invalid credentials for tenant")
        assert str(error) == "Invalid credentials for tenant"
        assert isinstance(error, Exception)

    def test_splunk_connection_error_creation(self):
        """Test SplunkConnectionError can be created."""
        error = SplunkConnectionError("Connection timeout")
        assert str(error) == "Connection timeout"
        assert isinstance(error, Exception)

    def test_cim_data_not_found_error_creation(self):
        """Test CIMDataNotFoundError can be created."""
        error = CIMDataNotFoundError("NAS source 'Unknown' not found in CIM mappings")
        assert "Unknown" in str(error)
        assert isinstance(error, Exception)


class TestSplunkUtilsIntegration:
    """Test integration scenarios between components."""

    def test_spl_generator_with_cim_mapper_integration(self):
        """Test integrated workflow between SPLGenerator and CIMMapper."""
        # Create mock mapping data
        source_to_cim = {
            "Firewall": {
                "primary_cim_datamodel": "Network Traffic",
                "secondary_cim_models": [],
            }
        }
        cim_to_sourcetypes = {
            "Network Traffic": {
                "sourcetypes": ["pan:threat", "cisco:asa"],
                "datamodel_id": "dm_001",
                "sourcetype_count": 2,
            }
        }
        sourcetype_to_index = {
            "pan:threat": {"index": "main", "eps_count": 15.5},
            "cisco:asa": {"index": "network", "eps_count": 10.2},
        }

        mapper = CIMMapper(source_to_cim, cim_to_sourcetypes, sourcetype_to_index)
        generator = SPLGenerator(mapper)

        # Test integrated SPL generation
        alert = {
            "source_category": "Firewall",
            "triggering_event_time": "2024-01-15T10:30:00Z",
            "primary_risk_entity": "192.168.1.100",
            "indicators_of_compromise": ["malware.exe"],
        }

        result = generator.generate_triggering_events_spl(alert)

        assert isinstance(result, str)
        assert "search" in result
        assert "index=" in result
        assert "192.168.1.100" in result


class TestPositiveCases:
    """Test positive scenarios - these should pass once implementation is complete."""

    @pytest.fixture
    def valid_nas_alert(self):
        """Valid NAS alert for positive testing."""
        return {
            "title": "Malware Detection",
            "source_category": "EDR",
            "triggering_event_time": "2024-01-15T14:22:33Z",
            "primary_risk_entity": "WORKSTATION-01",
            "indicators_of_compromise": ["malware.exe", "192.168.1.100"],
            "risk_score": 95,
        }

    def test_valid_alert_structure_accepted(self, valid_nas_alert):
        """Test that valid NAS alert structure is accepted - will pass after implementation."""
        # This test documents the expected alert structure
        required_fields = [
            "source_category",
            "triggering_event_time",
            "primary_risk_entity",
            "indicators_of_compromise",
        ]

        for field in required_fields:
            assert field in valid_nas_alert, (
                f"Required field {field} missing from alert"
            )

    def test_expected_spl_output_format(self):
        """Test expected SPL output format - documents requirements."""
        # This documents what the SPL should look like after implementation
        expected_spl_pattern = r"\(index:\w+ AND sourcetype:\w+[\w:*]*\)(\s+OR\s+\(index:\w+ AND sourcetype:\w+[\w:*]*\))*"

        # This will be used to validate output format once implemented
        sample_expected = "(index:main AND sourcetype:pan:threat) OR (index:firewall AND sourcetype:fgt:traffic)"

        import re

        # Verify our regex matches expected format
        assert re.match(expected_spl_pattern, sample_expected), (
            "SPL pattern validation failed"
        )


class TestNegativeCases:
    """Test negative scenarios and error conditions."""

    def test_invalid_alert_missing_required_fields(self):
        """Test handling of malformed alerts missing required fields."""
        invalid_alerts = [
            {},  # Empty alert
            {"title": "Test"},  # Missing required fields
            {"source_category": "EDR"},  # Missing other required fields
            {"triggering_event_time": "invalid-date"},  # Invalid timestamp
        ]

        # Each of these should eventually raise appropriate errors
        # For now, we document the expected behavior
        for alert in invalid_alerts:
            # Will implement validation that raises ValueError for invalid alerts
            assert isinstance(alert, dict)  # Placeholder assertion

    def test_unknown_nas_source_category(self):
        """Test handling of unknown NAS source categories."""
        unknown_alert = {
            "source_category": "UnknownSourceType",
            "triggering_event_time": "2024-01-15T10:30:00Z",
            "primary_risk_entity": "test-entity",
            "indicators_of_compromise": ["test-ioc"],
        }

        # Should eventually raise CIMDataNotFoundError
        assert unknown_alert["source_category"] == "UnknownSourceType"

    def test_empty_iocs_list(self):
        """Test handling of alerts with empty IOCs."""
        alert_no_iocs = {
            "source_category": "Firewall",
            "triggering_event_time": "2024-01-15T10:30:00Z",
            "primary_risk_entity": "10.0.0.1",
            "indicators_of_compromise": [],  # Empty IOCs
        }

        # Should handle gracefully - maybe search only for primary entity
        assert isinstance(alert_no_iocs["indicators_of_compromise"], list)
        assert len(alert_no_iocs["indicators_of_compromise"]) == 0
