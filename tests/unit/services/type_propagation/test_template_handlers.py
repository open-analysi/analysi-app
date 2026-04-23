"""
Unit tests for Template Type Handlers.

Tests Identity, Merge, and Collect template type inference logic.
Following TDD - these tests should fail until implementation is complete.
"""

import pytest

from analysi.services.type_propagation.errors import (
    InvalidTemplateInputError,
    MergeConflictError,
)
from analysi.services.type_propagation.template_handlers import (
    create_union_schema,
    handle_collect_template,
    handle_identity_template,
    handle_merge_template,
    merge_object_schemas,
)


@pytest.mark.unit
class TestIdentityTemplate:
    """Test Identity template: T => T (pass-through)."""

    def test_identity_template_basic(self):
        """
        Test Identity template preserves primitive type.

        Positive case: Identity preserves primitive type.
        """
        # Input: string schema
        input_schema = {"type": "string"}

        # Call handle_identity_template()
        output = handle_identity_template(input_schema)

        # Output should be identical
        assert output == {"type": "string"}

    def test_identity_template_object(self):
        """
        Test Identity template preserves object structure.

        Positive case: Identity preserves object structure.
        """
        # Input: object schema with properties
        input_schema = {
            "type": "object",
            "properties": {"ip": {"type": "string"}, "port": {"type": "number"}},
        }

        # Call handle_identity_template()
        output = handle_identity_template(input_schema)

        # Output should be identical
        assert output == input_schema
        assert output["properties"]["ip"]["type"] == "string"
        assert output["properties"]["port"]["type"] == "number"

    def test_identity_template_array(self):
        """
        Test Identity template preserves array type.

        Positive case: Identity preserves array type.
        """
        # Input: array schema
        input_schema = {"type": "array", "items": {"type": "number"}}

        # Call handle_identity_template()
        output = handle_identity_template(input_schema)

        # Output should be identical
        assert output == input_schema
        assert output["items"]["type"] == "number"


@pytest.mark.unit
class TestMergeTemplate:
    """Test Merge template: [T1, T2] => {...T1, ...T2} (object merging)."""

    def test_merge_template_compatible_objects(self):
        """
        Test Merge template merges compatible object schemas.

        Positive case: Compatible objects merge successfully.
        """
        # Inputs: two compatible object schemas
        inputs = [
            {"type": "object", "properties": {"a": {"type": "string"}}},
            {"type": "object", "properties": {"b": {"type": "number"}}},
        ]

        # Call handle_merge_template()
        output = handle_merge_template(inputs)

        # Should not be an error
        assert not isinstance(output, (MergeConflictError, InvalidTemplateInputError))

        # Output should have both properties merged
        assert output["type"] == "object"
        assert "a" in output["properties"]
        assert "b" in output["properties"]
        assert output["properties"]["a"]["type"] == "string"
        assert output["properties"]["b"]["type"] == "number"

    def test_merge_template_empty_object_identity(self):
        """
        Test Merge template treats empty object as identity.

        Positive case: Empty object is identity for merge.
        """
        # Inputs: empty object and object with properties
        inputs = [
            {"type": "object"},
            {"type": "object", "properties": {"a": {"type": "string"}}},
        ]

        # Call handle_merge_template()
        output = handle_merge_template(inputs)

        # Should not be an error
        assert not isinstance(output, (MergeConflictError, InvalidTemplateInputError))

        # Output should be the non-empty object
        assert output["properties"]["a"]["type"] == "string"

    def test_merge_template_field_type_conflict(self):
        """
        Test Merge template detects field type conflicts.

        Negative case: Conflicting field types detected.
        """
        # Inputs: objects with same field but different types
        inputs = [
            {"type": "object", "properties": {"status": {"type": "number"}}},
            {"type": "object", "properties": {"status": {"type": "string"}}},
        ]

        # Call handle_merge_template()
        output = handle_merge_template(inputs)

        # Should return MergeConflictError
        assert isinstance(output, MergeConflictError)
        assert output.conflicting_field == "status"
        assert "status" in output.message.lower()

    def test_merge_template_array_field_concatenation(self):
        """
        Test Merge template concatenates array fields logically.

        Positive case: Array fields handled correctly.
        """
        # Inputs: objects with array fields
        inputs = [
            {
                "type": "object",
                "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
            },
            {
                "type": "object",
                "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
            },
        ]

        # Call handle_merge_template()
        output = handle_merge_template(inputs)

        # Should not be an error
        assert not isinstance(output, (MergeConflictError, InvalidTemplateInputError))

        # Array fields should be handled (implementation detail)
        assert "tags" in output["properties"]

    def test_merge_template_non_object_input(self):
        """
        Test Merge template rejects non-object inputs.

        Negative case: Merge requires all inputs to be objects.
        """
        # Inputs: mix of string and object
        inputs = [
            {"type": "string"},
            {"type": "object", "properties": {"a": {"type": "string"}}},
        ]

        # Call handle_merge_template()
        output = handle_merge_template(inputs)

        # Should return InvalidTemplateInputError
        assert isinstance(output, InvalidTemplateInputError)
        assert "object" in output.message.lower()

    def test_merge_template_single_input(self):
        """
        Test Merge template with single input passes through.

        Positive case: Single input passes through.
        """
        # Input: single object schema
        inputs = [{"type": "object", "properties": {"a": {"type": "string"}}}]

        # Call handle_merge_template()
        output = handle_merge_template(inputs)

        # Should not be an error
        assert not isinstance(output, (MergeConflictError, InvalidTemplateInputError))

        # Output should be same as input
        assert output["properties"]["a"]["type"] == "string"


@pytest.mark.unit
class TestCollectTemplate:
    """Test Collect template: [T1, T2] => [T1 | T2] (array aggregation)."""

    def test_collect_template_homogeneous(self):
        """
        Test Collect template with homogeneous input types.

        Positive case: Homogeneous types produce precise array schema.
        """
        # Inputs: all same type (object with verdict)
        inputs = [
            {"type": "object", "properties": {"verdict": {"type": "string"}}},
            {"type": "object", "properties": {"verdict": {"type": "string"}}},
            {"type": "object", "properties": {"verdict": {"type": "string"}}},
        ]

        # Call handle_collect_template()
        output = handle_collect_template(inputs)

        # Should return array schema
        assert output["type"] == "array"

        # Items should be the homogeneous type (not oneOf)
        # Implementation may simplify homogeneous union
        assert "items" in output

    def test_collect_template_heterogeneous(self):
        """
        Test Collect template with heterogeneous input types.

        Positive case: Heterogeneous types produce union schema.
        """
        # Inputs: different types (string and number)
        inputs = [{"type": "string"}, {"type": "number"}]

        # Call handle_collect_template()
        output = handle_collect_template(inputs)

        # Should return array schema
        assert output["type"] == "array"

        # Items should be union (oneOf)
        assert "items" in output
        # Implementation should have oneOf or similar union

    def test_collect_template_single_input(self):
        """
        Test Collect template with single input.

        Positive case: Single input creates array of that type.
        """
        # Input: single string schema
        inputs = [{"type": "string"}]

        # Call handle_collect_template()
        output = handle_collect_template(inputs)

        # Should return array schema
        assert output["type"] == "array"
        assert output["items"]["type"] == "string"

    def test_collect_template_empty_input(self):
        """
        Test Collect template with empty input list.

        Positive case: Empty input handled gracefully.
        """
        # Input: empty list
        inputs = []

        # Call handle_collect_template()
        output = handle_collect_template(inputs)

        # Should return generic array schema
        assert output["type"] == "array"
        # Items should be empty schema or generic
        assert "items" in output


@pytest.mark.unit
class TestMergeObjectSchemasHelper:
    """Test merge_object_schemas() helper function."""

    def test_merge_object_schemas_compatible(self):
        """
        Test merge_object_schemas() merges compatible schemas.

        Positive case: Compatible schemas merge.
        """
        # Schemas: compatible object schemas
        schema1 = {"type": "object", "properties": {"a": {"type": "string"}}}
        schema2 = {"type": "object", "properties": {"b": {"type": "number"}}}

        # Call merge_object_schemas()
        output = merge_object_schemas(schema1, schema2)

        # Should not be an error
        assert not isinstance(output, MergeConflictError)

        # Output should have both properties
        assert output["properties"]["a"]["type"] == "string"
        assert output["properties"]["b"]["type"] == "number"

    def test_merge_object_schemas_conflict(self):
        """
        Test merge_object_schemas() detects conflicts.

        Negative case: Conflict detected.
        """
        # Schemas: same field but different types
        schema1 = {"type": "object", "properties": {"status": {"type": "number"}}}
        schema2 = {"type": "object", "properties": {"status": {"type": "string"}}}

        # Call merge_object_schemas()
        output = merge_object_schemas(schema1, schema2)

        # Should return MergeConflictError
        assert isinstance(output, MergeConflictError)
        assert (
            "status" in output.message.lower() or output.conflicting_field == "status"
        )


@pytest.mark.unit
class TestCreateUnionSchemaHelper:
    """Test create_union_schema() helper function."""

    def test_create_union_schema_homogeneous(self):
        """
        Test create_union_schema() simplifies homogeneous types.

        Positive case: Homogeneous union simplified.
        """
        # Schemas: all same type
        schemas = [{"type": "string"}, {"type": "string"}, {"type": "string"}]

        # Call create_union_schema()
        output = create_union_schema(schemas)

        # Should be simplified to single type (not oneOf)
        assert output["type"] == "string"
        # Should not have oneOf for homogeneous
        assert "oneOf" not in output

    def test_create_union_schema_heterogeneous(self):
        """
        Test create_union_schema() creates oneOf for heterogeneous types.

        Positive case: Heterogeneous union uses oneOf.
        """
        # Schemas: different types
        schemas = [{"type": "string"}, {"type": "number"}, {"type": "boolean"}]

        # Call create_union_schema()
        output = create_union_schema(schemas)

        # Should use oneOf
        assert "oneOf" in output
        assert len(output["oneOf"]) == 3

    def test_create_union_schema_single(self):
        """
        Test create_union_schema() with single schema.

        Positive case: Single schema returns as-is.
        """
        # Schema: single type
        schemas = [{"type": "number"}]

        # Call create_union_schema()
        output = create_union_schema(schemas)

        # Should return the single schema
        assert output["type"] == "number"
        assert "oneOf" not in output
