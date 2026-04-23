"""Unit tests for alert normalization."""

import json
from datetime import UTC, datetime

from alert_normalizer.base import BaseNormalizer
from alert_normalizer.splunk import SplunkNotableNormalizer
from analysi.schemas.alert import (
    AlertCreate,
    AlertSeverity,
)


class TestSplunkNotableNormalizer:
    """Test SplunkNotableNormalizer conversions."""

    def test_to_alertcreate_with_complete_data(self):
        """Test SplunkNotableNormalizer.to_alertcreate() with complete mock data."""
        mock_notable = {
            "_time": "2024-01-15T10:30:00Z",
            "rule_name": "Suspicious PowerShell Activity",
            "severity": "high",
            "dest": "workstation01.corp.local",
            "user": "jsmith",
            "process": "powershell.exe -enc ...",
            "security_domain": "endpoint",
            "src": "192.168.1.100",
            "dest_port": 445,
            "protocol": "TCP",
        }

        normalizer = SplunkNotableNormalizer()
        alert_create = normalizer.to_alertcreate(mock_notable)

        # Verify it returns a Pydantic model
        assert isinstance(alert_create, AlertCreate)

        # Verify OCSF-compatible fields on the model
        assert alert_create.title == "Suspicious PowerShell Activity"
        assert alert_create.triggering_event_time == datetime(
            2024, 1, 15, 10, 30, 0, tzinfo=UTC
        )
        assert alert_create.severity == AlertSeverity.HIGH
        assert alert_create.source_vendor == "Splunk"
        assert alert_create.source_product == "Enterprise Security"

        # Verify raw_alert preservation
        raw_alert = json.loads(alert_create.raw_alert)
        assert raw_alert == mock_notable

        # Verify NAS extraction via to_extracted_dict (NAS fields are not on AlertCreate)
        nas_dict = normalizer.to_extracted_dict(mock_notable)

        # Verify entity extraction (user is prioritized over dest)
        assert nas_dict["primary_risk_entity_value"] == "jsmith"
        assert nas_dict["primary_risk_entity_type"] == "user"

        # Verify IOC extraction
        assert nas_dict["primary_ioc_value"] == "powershell.exe -enc ..."
        assert nas_dict["primary_ioc_type"] == "process"

        # Verify source category mapping
        assert nas_dict["source_category"] == "EDR"

    def test_from_alertcreate_reverse_conversion(self):
        """Test SplunkNotableNormalizer.from_alertcreate() reverse conversion."""
        alert_create = {
            "title": "Test Alert",
            "triggering_event_time": "2024-01-15T10:30:00Z",
            "severity": "high",
            "source_vendor": "Splunk",
            "source_product": "Enterprise Security",
            "primary_risk_entity_value": "server01.example.com",
            "primary_ioc_value": "malicious.exe",
            "raw_alert": json.dumps(
                {
                    "_time": "2024-01-15T10:30:00Z",
                    "rule_name": "Test Alert",
                    "custom_field": "preserved_value",
                }
            ),
        }

        normalizer = SplunkNotableNormalizer()
        notable = normalizer.from_alertcreate(alert_create)

        # Verify reverse mapping
        assert notable["rule_name"] == "Test Alert"
        assert notable["_time"] == "2024-01-15T10:30:00Z"
        assert notable["severity"] == "high"

        # Verify preserved fields from raw_alert
        assert notable["custom_field"] == "preserved_value"

    def test_bidirectional_preservation(self):
        """Test raw_alert preservation in both directions."""
        original_notable = {
            "_time": "2024-01-15T10:30:00Z",
            "rule_name": "Original Alert",
            "severity": "medium",
            "dest": "host123",
            "custom_field_1": "value1",
            "custom_field_2": "value2",
            "nested": {"data": "preserved"},
        }

        normalizer = SplunkNotableNormalizer()

        # Forward conversion (verifies AlertCreate construction works)
        normalizer.to_alertcreate(original_notable)

        # Convert to dict for reverse conversion — use NAS dict since
        # AlertCreate (OCSF) drops NAS-only fields
        nas_dict = normalizer.to_extracted_dict(original_notable)

        # Reverse conversion
        reconstructed_notable = normalizer.from_alertcreate(nas_dict)

        # All original fields should be preserved through raw_alert
        assert reconstructed_notable["custom_field_1"] == "value1"
        assert reconstructed_notable["custom_field_2"] == "value2"
        assert reconstructed_notable["nested"]["data"] == "preserved"

    def test_handling_missing_fields_with_defaults(self):
        """Test handling missing fields with appropriate defaults."""
        minimal_notable = {
            "_time": "2024-01-15T10:30:00Z",
            "rule_name": "Minimal Alert",
        }

        normalizer = SplunkNotableNormalizer()
        alert_create = normalizer.to_alertcreate(minimal_notable)
        nas_dict = normalizer.to_extracted_dict(minimal_notable)

        # Should have sensible defaults (now it's a Pydantic model)
        assert alert_create.title == "Minimal Alert"
        assert alert_create.severity == AlertSeverity.INFO  # Default severity is info
        assert alert_create.source_vendor == "Splunk"
        assert alert_create.source_product == "Enterprise Security"

        # NAS-only fields checked on dict
        assert nas_dict["primary_risk_entity_value"] is None
        assert nas_dict["primary_ioc_value"] is None

    def test_enum_normalization(self):
        """Test enum normalization (severity lowercase, etc.)."""
        notable_with_uppercase = {
            "_time": "2024-01-15T10:30:00Z",
            "rule_name": "Test Alert",
            "severity": "HIGH",  # Uppercase
            "urgency": "CRITICAL",  # Uppercase
        }

        normalizer = SplunkNotableNormalizer()
        alert_create = normalizer.to_alertcreate(notable_with_uppercase)

        # Should normalize to enum
        assert alert_create.severity == AlertSeverity.HIGH

    def test_glom_specs_with_various_structures(self):
        """Test glom specs with various Notable structures."""
        # Test with deeply nested structure
        complex_notable = {
            "_time": "2024-01-15T10:30:00Z",
            "rule_name": "Complex Alert",
            "event": {
                "severity": "high",
                "details": {"host": "nested-host", "user": "nested-user"},
            },
            "network": {
                "src": "10.0.0.1",
                "dest": "10.0.0.2",
                "ports": [80, 443, 8080],
            },
        }

        normalizer = SplunkNotableNormalizer()
        alert_create = normalizer.to_alertcreate(complex_notable)

        # Should extract data from nested structures
        assert alert_create.title == "Complex Alert"
        # Check that raw_alert preserves all structure
        raw_alert = json.loads(alert_create.raw_alert)
        assert raw_alert["event"]["details"]["host"] == "nested-host"
        assert raw_alert["network"]["ports"] == [80, 443, 8080]


class TestBaseNormalizer:
    """Test BaseNormalizer abstract class."""

    def test_preserve_raw(self):
        """Test preserve_raw converts to JSON string."""

        class TestNormalizer(BaseNormalizer):
            def to_alertcreate(self, data):
                return {"raw_alert": self.preserve_raw(data)}

            def from_alertcreate(self, alert_create):
                return json.loads(alert_create["raw_alert"])

        normalizer = TestNormalizer()
        test_data = {"field1": "value1", "nested": {"field2": "value2"}}

        result = normalizer.to_alertcreate(test_data)
        assert isinstance(result["raw_alert"], str)

        parsed = json.loads(result["raw_alert"])
        assert parsed == test_data

    def test_normalize_alias(self):
        """Test normalize() compatibility alias."""

        class TestNormalizer(BaseNormalizer):
            def to_alertcreate(self, data):
                return {"normalized": True}

            def from_alertcreate(self, alert_create):
                return {"denormalized": True}

        normalizer = TestNormalizer()
        result = normalizer.normalize({"test": "data"})
        assert result["normalized"] is True

    def test_denormalize_alias(self):
        """Test denormalize() compatibility alias."""

        class TestNormalizer(BaseNormalizer):
            def to_alertcreate(self, data):
                return {"normalized": True}

            def from_alertcreate(self, alert_create):
                return {"denormalized": True}

        normalizer = TestNormalizer()
        result = normalizer.denormalize({"alert": "data"})
        assert result["denormalized"] is True


class TestGlomMappers:
    """Test glom mapping specifications."""

    def test_notable_to_alertcreate_spec(self):
        """Test NOTABLE_TO_ALERTCREATE glom spec for forward mapping."""
        import glom

        from alert_normalizer.mappers.splunk_notable import NOTABLE_TO_ALERTCREATE

        notable = {
            "_time": "2024-01-15T10:30:00Z",
            "rule_name": "Test Rule",
            "severity": "high",
            "dest": "target-host",
            "src": "source-host",
            "user": "testuser",
        }

        result = glom.glom(notable, NOTABLE_TO_ALERTCREATE)

        assert result["title"] == "Test Rule"
        assert result["triggering_event_time"] == "2024-01-15T10:30:00Z"
        assert result["severity"] == "high"

    def test_alertcreate_to_notable_spec(self):
        """Test ALERTCREATE_TO_NOTABLE glom spec for reverse mapping."""
        import glom

        from alert_normalizer.mappers.splunk_notable import ALERTCREATE_TO_NOTABLE

        alert_create = {
            "title": "Test Alert",
            "triggering_event_time": "2024-01-15T10:30:00Z",
            "severity": "medium",
            "primary_risk_entity_value": "host123",
        }

        result = glom.glom(alert_create, ALERTCREATE_TO_NOTABLE)

        assert result["rule_name"] == "Test Alert"
        assert result["_time"] == "2024-01-15T10:30:00Z"
        assert result["severity"] == "medium"

    def test_map_security_domain_to_category(self):
        """Test map_security_domain_to_category() for domain to SourceCategory mapping."""
        from alert_normalizer.mappers.splunk_notable import (
            map_security_domain_to_category,
        )

        assert map_security_domain_to_category("endpoint") == "EDR"
        assert map_security_domain_to_category("network") == "Firewall"
        assert map_security_domain_to_category("identity") == "Identity"
        assert map_security_domain_to_category("cloud") == "Cloud"
        assert map_security_domain_to_category("dlp") == "DLP"
        assert map_security_domain_to_category("unknown") is None
        assert map_security_domain_to_category(None) is None

    def test_extract_primary_ioc(self):
        """Test extract_primary_ioc() IOC extraction logic."""
        from alert_normalizer.mappers.splunk_notable import extract_primary_ioc

        # Test with process
        event = {"process": "malicious.exe -silent"}
        assert extract_primary_ioc(event) == "malicious.exe -silent"

        # Test with file hash
        event = {"file_hash": "abc123def456"}
        assert extract_primary_ioc(event) == "abc123def456"

        # Test with URL
        event = {"url": "http://malicious.com/payload"}
        assert extract_primary_ioc(event) == "http://malicious.com/payload"

        # Test with no IOC
        event = {"other_field": "value"}
        assert extract_primary_ioc(event) is None

    def test_determine_entity_type(self):
        """Test determine_entity_type() entity type detection."""
        from alert_normalizer.mappers.splunk_notable import determine_entity_type

        # Test host detection
        event = {"dest": "server01.example.com"}
        assert determine_entity_type(event) == "host"

        # Test user detection
        event = {"user": "jsmith"}
        assert determine_entity_type(event) == "user"

        # Test IP detection
        event = {"src": "192.168.1.100"}
        assert determine_entity_type(event) == "ip"

        # Test unknown
        event = {"other": "value"}
        assert determine_entity_type(event) == "unknown"

    def test_extract_network_info(self):
        """Test extract_network_info() network data extraction."""
        from alert_normalizer.mappers.splunk_notable import extract_network_info

        event = {
            "src": "10.0.0.1",
            "dest": "10.0.0.2",
            "src_port": 12345,
            "dest_port": 80,
            "protocol": "TCP",
            "bytes_in": 1024,
            "bytes_out": 2048,
        }

        network_info = extract_network_info(event)

        assert network_info["src_ip"] == "10.0.0.1"
        assert network_info["dest_ip"] == "10.0.0.2"
        assert network_info["src_port"] == 12345
        assert network_info["dest_port"] == 80
        assert network_info["protocol"] == "TCP"
        assert network_info["bytes_in"] == 1024
        assert network_info["bytes_out"] == 2048


class TestPydanticValidation:
    """Test Pydantic model validation and edge cases."""

    def test_minimal_valid_notable(self):
        """Test normalizer with minimal required fields."""
        minimal_notable = {
            "_time": "2024-01-15T10:30:00Z",
            "rule_name": "Test Alert",
            "severity": "medium",
        }

        normalizer = SplunkNotableNormalizer()
        alert_create = normalizer.to_alertcreate(minimal_notable)

        # Should create valid AlertCreate with defaults
        assert isinstance(alert_create, AlertCreate)
        assert alert_create.title == "Test Alert"
        assert alert_create.severity == AlertSeverity.MEDIUM
        assert alert_create.source_vendor == "Splunk"

    def test_severity_enum_mapping(self):
        """Test various severity values map to valid AlertSeverity enum."""
        normalizer = SplunkNotableNormalizer()

        severity_tests = [
            ("critical", AlertSeverity.CRITICAL),
            ("high", AlertSeverity.HIGH),
            ("medium", AlertSeverity.MEDIUM),
            ("low", AlertSeverity.LOW),
            ("info", AlertSeverity.INFO),
            ("informational", AlertSeverity.INFO),
            ("unknown", AlertSeverity.INFO),  # Default to info
            (None, AlertSeverity.INFO),  # Default to info
        ]

        for input_severity, expected_enum in severity_tests:
            notable = {
                "_time": "2024-01-15T10:30:00Z",
                "rule_name": "Test",
                "severity": input_severity,
            }
            alert_create = normalizer.to_alertcreate(notable)
            assert alert_create.severity == expected_enum, (
                f"Failed for {input_severity}"
            )

    def test_source_category_enum_mapping(self):
        """Test security domain maps to valid SourceCategory enum (via NAS dict)."""
        normalizer = SplunkNotableNormalizer()

        domain_tests = [
            ("endpoint", "EDR"),
            ("network", "Firewall"),
            ("identity", "Identity"),
            ("cloud", "Cloud"),
            ("dlp", "DLP"),
            ("unknown", None),  # Unknown maps to None
            (None, None),  # None stays None
        ]

        for domain, expected_category in domain_tests:
            notable = {
                "_time": "2024-01-15T10:30:00Z",
                "rule_name": "Test",
                "severity": "medium",
                "security_domain": domain,
            }
            nas_dict = normalizer.to_extracted_dict(notable)
            assert nas_dict["source_category"] == expected_category, (
                f"Failed for {domain}"
            )

    def test_entity_type_enum_mapping(self):
        """Test entity detection maps to valid EntityType enum (via NAS dict)."""
        normalizer = SplunkNotableNormalizer()

        entity_tests = [
            ({"dest": "host1"}, "device"),
            ({"user": "user1"}, "user"),
            ({"src": "192.168.1.1"}, "device"),
            ({}, None),  # No entity
        ]

        for fields, expected_type in entity_tests:
            notable = {
                "_time": "2024-01-15T10:30:00Z",
                "rule_name": "Test",
                "severity": "medium",
                **fields,
            }
            nas_dict = normalizer.to_extracted_dict(notable)
            assert nas_dict["primary_risk_entity_type"] == expected_type

    def test_ioc_type_enum_mapping(self):
        """Test IOC detection maps to valid IOCType enum (via NAS dict)."""
        normalizer = SplunkNotableNormalizer()

        ioc_tests = [
            ({"process": "test.exe"}, "process"),
            ({"url": "http://example.com"}, "url"),
            ({"file_hash": "abc123"}, "filehash"),
            ({"domain": "evil.com"}, "domain"),
            ({"ip": "192.168.1.1"}, "ip"),
            ({}, None),  # No IOC
        ]

        for fields, expected_type in ioc_tests:
            notable = {
                "_time": "2024-01-15T10:30:00Z",
                "rule_name": "Test",
                "severity": "medium",
                **fields,
            }
            nas_dict = normalizer.to_extracted_dict(notable)
            assert nas_dict["primary_ioc_type"] == expected_type

    def test_datetime_parsing(self):
        """Test various datetime formats are handled correctly."""
        normalizer = SplunkNotableNormalizer()

        # ISO format with Z
        notable = {
            "_time": "2024-01-15T10:30:00Z",
            "rule_name": "Test",
            "severity": "medium",
        }
        alert_create = normalizer.to_alertcreate(notable)
        expected_dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        assert alert_create.triggering_event_time == expected_dt

    def test_raw_alert_always_preserved(self):
        """Test raw_alert is always preserved as JSON string."""
        normalizer = SplunkNotableNormalizer()

        notable = {
            "_time": "2024-01-15T10:30:00Z",
            "rule_name": "Test",
            "severity": "medium",
            "custom_field": "custom_value",
            "nested": {"data": "value"},
        }

        alert_create = normalizer.to_alertcreate(notable)

        # Verify raw_alert is preserved
        assert alert_create.raw_alert
        parsed_raw = json.loads(alert_create.raw_alert)
        assert parsed_raw == notable
        assert parsed_raw["custom_field"] == "custom_value"
        assert parsed_raw["nested"]["data"] == "value"

    def test_model_dump_excludes_none(self):
        """Test that model_dump with exclude_none works correctly."""
        normalizer = SplunkNotableNormalizer()

        minimal_notable = {
            "_time": "2024-01-15T10:30:00Z",
            "rule_name": "Test",
            "severity": "medium",
        }

        alert_create = normalizer.to_alertcreate(minimal_notable)
        alert_dict = alert_create.model_dump(exclude_none=True)

        # Should not have None values
        assert None not in alert_dict.values()

        # Should have required fields
        assert "title" in alert_dict
        assert "triggering_event_time" in alert_dict
        assert "severity" in alert_dict
        # raw_data is the OCSF field name (raw_alert maps to it)
        assert "raw_data" in alert_dict

        # NAS-only fields should not be in the OCSF model at all
        assert "primary_risk_entity_type" not in alert_dict
        assert "primary_ioc_type" not in alert_dict
