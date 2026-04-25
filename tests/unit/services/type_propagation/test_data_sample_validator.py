"""
Unit tests for data_sample_validator module.

Tests schema generation from samples, particularly that fields are not marked as required.
"""

from analysi.services.type_propagation.data_sample_validator import (
    _remove_required_fields,
    generate_schema_from_samples,
)


class TestRemoveRequiredFields:
    """Test the _remove_required_fields helper function."""

    def test_removes_top_level_required(self):
        """Test that required array is removed from top level."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        result = _remove_required_fields(schema)
        assert "required" not in result
        assert result["properties"]["name"]["type"] == "string"

    def test_removes_nested_required(self):
        """Test that required arrays are removed from nested objects."""
        schema = {
            "type": "object",
            "properties": {
                "network_info": {
                    "type": "object",
                    "properties": {
                        "protocol": {"type": "string"},
                        "src_ip": {"type": "string"},
                    },
                    "required": ["protocol"],  # This should be removed
                }
            },
            "required": ["network_info"],  # This should also be removed
        }
        result = _remove_required_fields(schema)

        assert "required" not in result
        assert "required" not in result["properties"]["network_info"]

    def test_preserves_other_fields(self):
        """Test that non-required fields are preserved."""
        schema = {
            "$schema": "http://json-schema.org/schema#",
            "type": "object",
            "properties": {
                "ip": {"type": "string", "format": "ipv4"},
                "port": {"type": "integer", "minimum": 1, "maximum": 65535},
            },
            "required": ["ip"],
            "additionalProperties": False,
        }
        result = _remove_required_fields(schema)

        assert result["$schema"] == "http://json-schema.org/schema#"
        assert result["type"] == "object"
        assert result["properties"]["ip"]["format"] == "ipv4"
        assert result["properties"]["port"]["minimum"] == 1
        assert result["additionalProperties"] is False
        assert "required" not in result

    def test_handles_deeply_nested_objects(self):
        """Test removal works on deeply nested structures."""
        schema = {
            "type": "object",
            "properties": {
                "level1": {
                    "type": "object",
                    "properties": {
                        "level2": {
                            "type": "object",
                            "properties": {"value": {"type": "string"}},
                            "required": ["value"],
                        }
                    },
                    "required": ["level2"],
                }
            },
            "required": ["level1"],
        }
        result = _remove_required_fields(schema)

        assert "required" not in result
        assert "required" not in result["properties"]["level1"]
        assert "required" not in result["properties"]["level1"]["properties"]["level2"]

    def test_handles_empty_schema(self):
        """Test that empty schema is handled."""
        result = _remove_required_fields({})
        assert result == {}

    def test_handles_non_dict_input(self):
        """Test that non-dict values are returned as-is."""
        assert _remove_required_fields("string") == "string"
        assert _remove_required_fields(123) == 123
        assert _remove_required_fields(None) is None


class TestGenerateSchemaFromSamples:
    """Test that generate_schema_from_samples produces schemas without required fields."""

    def test_simple_object_no_required(self):
        """Test that a simple object schema has no required fields."""
        samples = [{"ip": "1.2.3.4", "context": "test"}]
        schema = generate_schema_from_samples(samples)

        assert "required" not in schema
        assert schema["type"] == "object"
        assert "ip" in schema["properties"]
        assert "context" in schema["properties"]

    def test_nested_object_no_required(self):
        """Test that nested objects also have no required fields."""
        samples = [
            {
                "title": "Alert",
                "network_info": {"protocol": "tcp", "src_ip": "1.2.3.4"},
            }
        ]
        schema = generate_schema_from_samples(samples)

        assert "required" not in schema
        assert "required" not in schema["properties"]["network_info"]

    def test_alert_like_structure_no_required(self):
        """Test with an alert-like structure similar to what caused the bug."""
        samples = [
            {
                "title": "Suspicious Activity",
                "severity": "high",
                "network_info": {
                    "protocol": "tcp",
                    "src_ip": "192.168.1.1",
                    "dst_port": 443,
                },
                "device_action": None,
            }
        ]
        schema = generate_schema_from_samples(samples)

        # No required at top level
        assert "required" not in schema

        # No required in nested network_info
        assert "required" not in schema["properties"]["network_info"]

    def test_null_values_create_null_type(self):
        """Test that null values result in type that allows null."""
        samples = [{"value": None}]
        schema = generate_schema_from_samples(samples)

        # Genson should recognize null type
        assert schema["properties"]["value"]["type"] == "null"

    def test_mixed_null_and_string_creates_union_type(self):
        """Test that mixed null and string creates union type."""
        samples = [{"value": "hello"}, {"value": None}]
        schema = generate_schema_from_samples(samples)

        # Genson creates a union type for mixed values
        value_type = schema["properties"]["value"]["type"]
        assert isinstance(value_type, list)
        assert "null" in value_type
        assert "string" in value_type

    def test_empty_samples_list(self):
        """Test with empty samples list."""
        schema = generate_schema_from_samples([])
        # Genson returns a generic schema for empty input
        assert schema == {"$schema": "http://json-schema.org/schema#"}

    def test_structured_samples_with_input_key(self):
        """Test that samples using {name, input, description} pattern
        generate schema from the input values, not the wrapper."""
        # This is the structured format used by demo-loader tasks
        samples = [
            {
                "name": "Test case 1",
                "description": "Happy path",
                "input": {
                    "primary_ioc_value": "1.2.3.4",
                    "network_info": {"src_ip": "1.2.3.4"},
                },
            }
        ]
        # Extract input values (same logic as task.py create_task)
        input_samples = [
            s["input"]
            for s in samples
            if isinstance(s, dict) and "input" in s and isinstance(s["input"], dict)
        ]
        schema = generate_schema_from_samples(input_samples)

        # Schema should be for the input data, not the wrapper
        assert "primary_ioc_value" in schema["properties"]
        assert "network_info" in schema["properties"]
        # Should NOT have wrapper keys
        assert "name" not in schema["properties"]
        assert "description" not in schema["properties"]
