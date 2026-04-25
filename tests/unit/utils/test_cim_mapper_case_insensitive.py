"""Unit tests for case-insensitive CIM mapping lookups."""

import pytest

from analysi.utils.splunk_utils import CIMDataNotFoundError, CIMMapper


class TestCIMMapperCaseInsensitive:
    """Test case-insensitive lookups in CIMMapper."""

    @pytest.fixture
    def sample_mappings(self):
        """Create sample mapping data with mixed case."""
        source_to_cim = {
            "Firewall": {
                "primary_cim_datamodel": "Network Traffic",
                "secondary_cim_models": ["Network Sessions"],
            },
            "EDR": {
                "primary_cim_datamodel": "Endpoint",
                "secondary_cim_models": ["Malware", "Updates"],
            },
            "Web": {"primary_cim_datamodel": "Web", "secondary_cim_models": []},
            "Authentication": {
                "primary_cim_datamodel": "Authentication",
                "secondary_cim_models": ["Account Management"],
            },
        }

        cim_to_sourcetypes = {
            "Network Traffic": {
                "sourcetypes": [
                    "pan:traffic",
                    "cisco:asa",
                    "fortinet:fortigate:traffic",
                ],
                "datamodel_id": "dm_004",
                "sourcetype_count": 3,
            },
            "Endpoint": {
                "sourcetypes": ["WinEventLog:System", "WinEventLog:Security", "sysmon"],
                "datamodel_id": "dm_003",
                "sourcetype_count": 3,
            },
            "Web": {
                "sourcetypes": ["iis", "apache:access", "nginx:access"],
                "datamodel_id": "dm_005",
                "sourcetype_count": 3,
            },
            "Authentication": {
                "sourcetypes": ["WinEventLog:Security", "linux_secure"],
                "datamodel_id": "dm_001",
                "sourcetype_count": 2,
            },
        }

        sourcetype_to_index = {
            "pan:traffic": {"index": "network", "eps_count": 45.6},
            "cisco:asa": {"index": "network", "eps_count": 32.1},
            "WinEventLog:System": {"index": "wineventlog", "eps_count": 10.5},
            "WinEventLog:Security": {"index": "wineventlog", "eps_count": 15.2},
            "sysmon": {"index": "endpoint", "eps_count": 25.7},
            "iis": {"index": "web", "eps_count": 12.3},
            "apache:access": {"index": "web", "eps_count": 8.9},
            "nginx:access": {"index": "web", "eps_count": 7.2},
            "linux_secure": {"index": "os", "eps_count": 5.4},
        }

        return source_to_cim, cim_to_sourcetypes, sourcetype_to_index

    @pytest.fixture
    def cim_mapper(self, sample_mappings):
        """Create CIMMapper instance with sample data."""
        source_to_cim, cim_to_sourcetypes, sourcetype_to_index = sample_mappings
        return CIMMapper(source_to_cim, cim_to_sourcetypes, sourcetype_to_index)

    def test_source_to_cim_case_insensitive_positive(self, cim_mapper):
        """Test NAS to CIM lookups with various cases - positive cases."""
        # Original case
        result = cim_mapper.get_cim_datamodels("Firewall")
        assert result["primary_cim_datamodel"] == "Network Traffic"
        assert result["secondary_cim_models"] == ["Network Sessions"]

        # Lowercase
        result = cim_mapper.get_cim_datamodels("firewall")
        assert result["primary_cim_datamodel"] == "Network Traffic"

        # Uppercase
        result = cim_mapper.get_cim_datamodels("FIREWALL")
        assert result["primary_cim_datamodel"] == "Network Traffic"

        # Mixed case
        result = cim_mapper.get_cim_datamodels("FiReWaLl")
        assert result["primary_cim_datamodel"] == "Network Traffic"

        # Test "Web" specifically (the reported issue)
        result = cim_mapper.get_cim_datamodels("Web")
        assert result["primary_cim_datamodel"] == "Web"

        result = cim_mapper.get_cim_datamodels("web")
        assert result["primary_cim_datamodel"] == "Web"

        result = cim_mapper.get_cim_datamodels("WEB")
        assert result["primary_cim_datamodel"] == "Web"

    def test_source_to_cim_case_insensitive_negative(self, cim_mapper):
        """Test NAS to CIM lookups - negative cases."""
        # Non-existent source
        with pytest.raises(CIMDataNotFoundError) as exc:
            cim_mapper.get_cim_datamodels("NonExistent")
        assert "NonExistent" in str(exc.value)

        # Empty string
        with pytest.raises(CIMDataNotFoundError):
            cim_mapper.get_cim_datamodels("")

        # Partial match should not work
        with pytest.raises(CIMDataNotFoundError):
            cim_mapper.get_cim_datamodels("Fire")

    def test_cim_to_sourcetypes_case_insensitive_positive(self, cim_mapper):
        """Test CIM to sourcetypes lookups with various cases - positive cases."""
        # Original case with space
        result = cim_mapper.get_sourcetypes_for_cim_datamodel("Network Traffic")
        assert "pan:traffic" in result
        assert "cisco:asa" in result

        # Lowercase
        result = cim_mapper.get_sourcetypes_for_cim_datamodel("network traffic")
        assert "pan:traffic" in result

        # Uppercase
        result = cim_mapper.get_sourcetypes_for_cim_datamodel("NETWORK TRAFFIC")
        assert "pan:traffic" in result

        # Mixed case
        result = cim_mapper.get_sourcetypes_for_cim_datamodel("NeTwOrK TrAfFiC")
        assert "pan:traffic" in result

        # Test "Web" datamodel
        result = cim_mapper.get_sourcetypes_for_cim_datamodel("Web")
        assert "iis" in result
        assert "apache:access" in result

        result = cim_mapper.get_sourcetypes_for_cim_datamodel("web")
        assert "iis" in result

        result = cim_mapper.get_sourcetypes_for_cim_datamodel("WEB")
        assert "iis" in result

    def test_cim_to_sourcetypes_case_insensitive_negative(self, cim_mapper):
        """Test CIM to sourcetypes lookups - negative cases."""
        # Non-existent datamodel
        with pytest.raises(CIMDataNotFoundError) as exc:
            cim_mapper.get_sourcetypes_for_cim_datamodel("Fake Datamodel")
        assert "Fake Datamodel" in str(exc.value)

        # Empty string
        with pytest.raises(CIMDataNotFoundError):
            cim_mapper.get_sourcetypes_for_cim_datamodel("")

        # Partial match should not work
        with pytest.raises(CIMDataNotFoundError):
            cim_mapper.get_sourcetypes_for_cim_datamodel("Network")

    def test_sourcetype_to_index_case_insensitive_positive(self, cim_mapper):
        """Test sourcetype to index lookups with various cases - positive cases."""
        # Original case
        result = cim_mapper.get_index_for_sourcetype("pan:traffic")
        assert result["index"] == "network"
        assert result["eps_count"] == 45.6

        # Lowercase
        result = cim_mapper.get_index_for_sourcetype("pan:traffic")
        assert result["index"] == "network"

        # Uppercase
        result = cim_mapper.get_index_for_sourcetype("PAN:TRAFFIC")
        assert result["index"] == "network"

        # Mixed case with colon
        result = cim_mapper.get_index_for_sourcetype("WinEventLog:Security")
        assert result["index"] == "wineventlog"

        result = cim_mapper.get_index_for_sourcetype("wineventlog:security")
        assert result["index"] == "wineventlog"

        result = cim_mapper.get_index_for_sourcetype("WINEVENTLOG:SECURITY")
        assert result["index"] == "wineventlog"

    def test_sourcetype_to_index_case_insensitive_negative(self, cim_mapper):
        """Test sourcetype to index lookups - negative cases."""
        # Non-existent sourcetype
        with pytest.raises(CIMDataNotFoundError) as exc:
            cim_mapper.get_index_for_sourcetype("fake:sourcetype")
        assert "fake:sourcetype" in str(exc.value)

        # Empty string
        with pytest.raises(CIMDataNotFoundError):
            cim_mapper.get_index_for_sourcetype("")

        # Partial match should not work
        with pytest.raises(CIMDataNotFoundError):
            cim_mapper.get_index_for_sourcetype("pan:")

    def test_perform_triple_join_case_insensitive(self, cim_mapper):
        """Test the complete triple join with case variations."""
        # Test with "Web" in different cases
        pairs = cim_mapper.perform_triple_join("Web")
        assert len(pairs) > 0
        indexes = [pair[0] for pair in pairs]
        assert "web" in indexes

        pairs = cim_mapper.perform_triple_join("web")
        assert len(pairs) > 0
        indexes = [pair[0] for pair in pairs]
        assert "web" in indexes

        pairs = cim_mapper.perform_triple_join("WEB")
        assert len(pairs) > 0
        indexes = [pair[0] for pair in pairs]
        assert "web" in indexes

        # Test with "Firewall"
        pairs = cim_mapper.perform_triple_join("firewall")
        assert len(pairs) > 0
        indexes = [pair[0] for pair in pairs]
        assert "network" in indexes

        # Test with "Authentication"
        pairs = cim_mapper.perform_triple_join("AUTHENTICATION")
        assert len(pairs) > 0
        found_sourcetypes = [pair[1] for pair in pairs]
        # Should find at least one of the authentication sourcetypes
        assert any(
            st.lower() in ["wineventlog:security", "linux_secure"]
            for st in found_sourcetypes
        )

    def test_perform_triple_join_negative(self, cim_mapper):
        """Test triple join with non-existent source."""
        with pytest.raises(CIMDataNotFoundError) as exc:
            cim_mapper.perform_triple_join("InvalidSource")
        assert "InvalidSource" in str(exc.value)

    def test_wildcard_sourcetype_matching_case_insensitive(self, cim_mapper):
        """Test wildcard matching with case variations."""
        # Add wildcard mappings to test
        source_to_cim = {
            "Test": {"primary_cim_datamodel": "Test Model", "secondary_cim_models": []}
        }
        cim_to_sourcetypes = {"Test Model": {"sourcetypes": ["crowdstrike:*"]}}
        sourcetype_to_index = {
            "crowdstrike:*": {"index": "security", "eps_count": 20.0}
        }

        mapper = CIMMapper(source_to_cim, cim_to_sourcetypes, sourcetype_to_index)

        # Should match wildcard pattern with different cases
        result = mapper.get_index_for_sourcetype("crowdstrike:event")
        assert result["index"] == "security"

        result = mapper.get_index_for_sourcetype("CROWDSTRIKE:EVENT")
        assert result["index"] == "security"

        result = mapper.get_index_for_sourcetype("CrowdStrike:Event")
        assert result["index"] == "security"

    def test_empty_mappings(self):
        """Test CIMMapper with empty mappings."""
        mapper = CIMMapper({}, {}, {})

        with pytest.raises(CIMDataNotFoundError):
            mapper.get_cim_datamodels("Any")

        with pytest.raises(CIMDataNotFoundError):
            mapper.get_sourcetypes_for_cim_datamodel("Any")

        with pytest.raises(CIMDataNotFoundError):
            mapper.get_index_for_sourcetype("any")

    def test_special_characters_in_keys(self):
        """Test handling of special characters in case-insensitive lookups."""
        source_to_cim = {
            "EDR-System": {
                "primary_cim_datamodel": "Endpoint",
                "secondary_cim_models": [],
            },
            "Auth_2FA": {
                "primary_cim_datamodel": "Authentication",
                "secondary_cim_models": [],
            },
        }
        cim_to_sourcetypes = {
            "Endpoint": {"sourcetypes": ["test:source"]},
            "Authentication": {"sourcetypes": ["auth:source"]},
        }
        sourcetype_to_index = {
            "test:source": {"index": "test"},
            "auth:source": {"index": "auth"},
        }

        mapper = CIMMapper(source_to_cim, cim_to_sourcetypes, sourcetype_to_index)

        # Should handle hyphens and underscores correctly
        result = mapper.get_cim_datamodels("edr-system")
        assert result["primary_cim_datamodel"] == "Endpoint"

        result = mapper.get_cim_datamodels("EDR-SYSTEM")
        assert result["primary_cim_datamodel"] == "Endpoint"

        result = mapper.get_cim_datamodels("auth_2fa")
        assert result["primary_cim_datamodel"] == "Authentication"

        result = mapper.get_cim_datamodels("AUTH_2FA")
        assert result["primary_cim_datamodel"] == "Authentication"
