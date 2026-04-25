"""Unit tests for SchemaIntrospectionService."""

import pytest

from analysi.services.schema_introspection_service import SchemaIntrospectionService


class TestSchemaIntrospectionService:
    """Unit tests for SchemaIntrospectionService."""

    def test_get_model_schema_alert(self):
        """Test Alert model schema generation."""
        result = SchemaIntrospectionService.get_model_schema("Alert")

        assert "model_name" in result
        assert result["model_name"] == "Alert"
        assert "schema" in result
        assert "pydantic_version" in result
        assert "definitions" in result
        assert isinstance(result["schema"], dict)

    def test_get_model_schema_finding(self):
        """Test Finding model schema generation."""
        # Finding doesn't exist in our registry - should raise ValueError
        with pytest.raises(ValueError, match="Model 'Finding' not found"):
            SchemaIntrospectionService.get_model_schema("Finding")

    def test_get_model_schema_with_definitions(self):
        """Test schema includes nested model definitions."""
        result = SchemaIntrospectionService.get_model_schema(
            "Alert", include_definitions=True
        )

        assert "definitions" in result
        # Definitions may be None or a dict depending on the model
        assert result["definitions"] is None or isinstance(result["definitions"], dict)

    def test_get_model_schema_without_definitions(self):
        """Test schema without nested definitions."""
        result = SchemaIntrospectionService.get_model_schema(
            "Alert", include_definitions=False
        )

        assert "definitions" in result
        assert result["definitions"] is None
        # $defs should not be in schema
        assert "$defs" not in result["schema"]

    def test_get_model_schema_invalid_model_name(self):
        """Test error handling for unknown model."""
        with pytest.raises(ValueError, match="not found"):
            SchemaIntrospectionService.get_model_schema("NonExistentModel")

    def test_list_available_models(self):
        """Test listing all available NAS models."""
        result = SchemaIntrospectionService.list_available_models()

        assert isinstance(result, list)
        assert len(result) > 0
        assert "Alert" in result
        assert "Task" in result
        assert "Workflow" in result
        # Should be sorted
        assert result == sorted(result)

    def test_model_registry_initialization(self):
        """Test model registry is properly initialized."""
        SchemaIntrospectionService.initialize_registry()

        assert len(SchemaIntrospectionService.MODEL_REGISTRY) > 0
        assert "Alert" in SchemaIntrospectionService.MODEL_REGISTRY
        assert "Task" in SchemaIntrospectionService.MODEL_REGISTRY

    def test_schema_json_serializable(self):
        """Test returned schemas are JSON-serializable."""
        import json

        result = SchemaIntrospectionService.get_model_schema("Alert")

        # Should be JSON serializable
        json_str = json.dumps(result)
        assert len(json_str) > 0

        # Should be deserializable
        deserialized = json.loads(json_str)
        assert deserialized["model_name"] == "Alert"
