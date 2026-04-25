"""
Schema compatibility validation utilities.

Implements duck typing validation: checks if an actual schema is compatible
with a required schema (i.e., has all required fields with compatible types).
"""

from typing import Any

from analysi.services.type_propagation.errors import TypeMismatchError


def validate_schema_compatibility(
    node_id: str,
    required_schema: dict[str, Any],
    actual_schema: dict[str, Any],
) -> TypeMismatchError | None:
    """
    Validate that actual schema is compatible with required schema (duck typing).

    Compatibility rules:
    1. If required schema has "required" fields, actual must have those fields
    2. Field types must be compatible (same type or compatible types)
    3. Extra fields in actual schema are allowed (duck typing)

    Args:
        node_id: ID of node being validated
        required_schema: Expected input schema from node definition
        actual_schema: Actual input schema propagated from predecessors

    Returns:
        TypeMismatchError if incompatible, None if compatible

    Example:
        Required: {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
        Actual: {"type": "object", "properties": {"name": {"type": "string"}, "age": {"type": "number"}}}
        Result: Compatible (has required "name" field, extra "age" is ok)

        Required: {"type": "object", "properties": {"alert": {"type": "object", "properties": {"iocs": {"type": "array"}}, "required": ["iocs"]}}}
        Actual: {"type": "object", "properties": {"alert": {"type": "object", "properties": {"title": {"type": "string"}}}}}
        Result: Incompatible (missing required "iocs" field in alert object)
    """
    # If required schema is empty object or has no constraints, anything is compatible
    if not required_schema or required_schema == {"type": "object"}:
        return None

    # Check top-level type compatibility
    required_type = required_schema.get("type")
    actual_type = actual_schema.get("type")

    if required_type and actual_type and required_type != actual_type:
        return TypeMismatchError(
            node_id=node_id,
            error_type="type_mismatch",
            message=f"Type mismatch: expected '{required_type}' but got '{actual_type}'",
            suggestion="Check predecessor output or fix node input schema",
            expected_schema=required_schema,
            actual_schema=actual_schema,
        )

    # For objects, check properties and required fields
    if required_type == "object":
        required_props = required_schema.get("properties", {})
        actual_props = actual_schema.get("properties", {})
        required_fields = required_schema.get("required", [])

        # Check that all required fields are present
        for field_name in required_fields:
            if field_name not in actual_props:
                return TypeMismatchError(
                    node_id=node_id,
                    error_type="missing_required_field",
                    message=f"Missing required field '{field_name}' in input schema",
                    suggestion=f"Ensure predecessor provides '{field_name}' field or update node input schema",
                    expected_schema=required_schema,
                    actual_schema=actual_schema,
                )

        # Check field type compatibility for all fields in required schema
        for field_name, required_field_schema in required_props.items():
            if field_name in actual_props:
                actual_field_schema = actual_props[field_name]

                # Recursively validate nested objects
                nested_error = validate_schema_compatibility(
                    node_id=node_id,
                    required_schema=required_field_schema,
                    actual_schema=actual_field_schema,
                )
                if nested_error:
                    # Update message to include field path
                    nested_error.message = (
                        f"In field '{field_name}': {nested_error.message}"
                    )
                    return nested_error

    # For arrays, check items schema if specified
    if required_type == "array":
        required_items = required_schema.get("items")
        actual_items = actual_schema.get("items")

        if required_items and actual_items:
            items_error = validate_schema_compatibility(
                node_id=node_id,
                required_schema=required_items,
                actual_schema=actual_items,
            )
            if items_error:
                items_error.message = f"In array items: {items_error.message}"
                return items_error

    # Schemas are compatible
    return None
