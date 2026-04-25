"""
Template type handlers for NodeTemplate type rules.

Implements type inference logic for Identity, Merge, and Collect templates.
"""

from typing import Any

from analysi.services.type_propagation.errors import (
    MergeConflictError,
    TypePropagationError,
)


def handle_identity_template(input_schema: dict[str, Any]) -> dict[str, Any]:
    """
    Handle Identity template type rule: T => T.

    Args:
        input_schema: Input JSON Schema

    Returns:
        Output schema (same as input)

    Example:
        >>> handle_identity_template({"type": "object"})
        {"type": "object"}
    """
    # Identity: pass-through - return input as-is
    return input_schema


def handle_merge_template(
    input_schemas: list[dict[str, Any]],
) -> dict[str, Any] | TypePropagationError:
    """
    Handle Merge template type rule: [T1, T2, ...] => {...T1, ...T2}.

    Merges multiple object schemas into one. Detects field type conflicts.

    Args:
        input_schemas: List of input JSON Schemas from predecessors

    Returns:
        Merged object schema, or MergeConflictError if conflicts detected

    Example:
        >>> schemas = [
        ...     {"type": "object", "properties": {"ip": {"type": "string"}}},
        ...     {"type": "object", "properties": {"score": {"type": "number"}}}
        ... ]
        >>> handle_merge_template(schemas)
        {"type": "object", "properties": {"ip": {"type": "string"}, "score": {"type": "number"}}}
    """
    from analysi.services.type_propagation.errors import InvalidTemplateInputError

    # Validate: all inputs must be objects
    for schema in input_schemas:
        if schema.get("type") != "object":
            return InvalidTemplateInputError(
                node_id="merge_node",  # Will be set by caller
                error_type="invalid_template_input",
                message=f"Merge template requires all inputs to be objects, got {schema.get('type')}",
                suggestion="Use Collect node instead or fix predecessor output",
                template_kind="merge",
                required_type="object",
                actual_type=schema.get("type"),
            )

    # Handle empty list
    if not input_schemas:
        return {"type": "object", "properties": {}}

    # Single input: return as-is
    if len(input_schemas) == 1:
        return input_schemas[0]

    # Merge schemas iteratively
    result = input_schemas[0]
    for i in range(1, len(input_schemas)):
        merged = merge_object_schemas(result, input_schemas[i])
        if isinstance(merged, MergeConflictError):
            return merged  # Propagate error
        result = merged

    return result


def handle_collect_template(input_schemas: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Handle Collect template type rule: [T1, T2, ...] => [T1 | T2 | ...].

    Creates array schema with items as union of input types.

    Args:
        input_schemas: List of input JSON Schemas from predecessors

    Returns:
        Array schema with union item type

    Example:
        >>> schemas = [
        ...     {"type": "object", "properties": {"verdict": {"type": "string"}}},
        ...     {"type": "object", "properties": {"verdict": {"type": "string"}}}
        ... ]
        >>> handle_collect_template(schemas)
        {"type": "array", "items": {"type": "object", "properties": {"verdict": {"type": "string"}}}}
    """
    # Create union of all input schemas
    items_schema = create_union_schema(input_schemas)

    # Return array with union items
    return {"type": "array", "items": items_schema}


def merge_object_schemas(
    schema1: dict[str, Any], schema2: dict[str, Any]
) -> dict[str, Any] | MergeConflictError:
    """
    Merge two object schemas, detecting field type conflicts.

    Args:
        schema1: First object schema
        schema2: Second object schema

    Returns:
        Merged schema, or MergeConflictError if conflict detected

    Example:
        >>> s1 = {"type": "object", "properties": {"a": {"type": "string"}}}
        >>> s2 = {"type": "object", "properties": {"b": {"type": "number"}}}
        >>> merge_object_schemas(s1, s2)
        {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "number"}}}
    """
    # Get properties from both schemas
    props1 = schema1.get("properties", {})
    props2 = schema2.get("properties", {})

    # Start with all properties from schema1
    merged_props = dict(props1)

    # Add properties from schema2, checking for conflicts
    for field_name, field_schema2 in props2.items():
        if field_name in merged_props:
            # Field exists in both - check for type conflict
            field_schema1 = merged_props[field_name]

            # Simple conflict detection: types must match
            if field_schema1.get("type") != field_schema2.get("type"):
                # Conflict detected
                return MergeConflictError(
                    node_id="merge_node",  # Will be set by caller
                    error_type="merge_conflict",
                    message=f"Field '{field_name}' has conflicting types: {field_schema1.get('type')} vs {field_schema2.get('type')}",
                    suggestion="Ensure all merge inputs have compatible types for shared fields",
                    conflicting_field=field_name,
                    schemas=[schema1, schema2],
                )

            # If types match, prefer schema2 (could merge more deeply, but keep simple)
            merged_props[field_name] = field_schema2
        else:
            # New field from schema2
            merged_props[field_name] = field_schema2

    # Return merged schema
    return {"type": "object", "properties": merged_props}


def create_union_schema(schemas: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Create JSON Schema union type (oneOf).

    Handles homogeneous (all same type) and heterogeneous (different types) cases.

    Args:
        schemas: List of schemas to union

    Returns:
        Union schema (oneOf) or single schema if homogeneous

    Example:
        >>> schemas = [{"type": "string"}, {"type": "number"}]
        >>> create_union_schema(schemas)
        {"oneOf": [{"type": "string"}, {"type": "number"}]}

        >>> schemas = [{"type": "string"}, {"type": "string"}]
        >>> create_union_schema(schemas)
        {"type": "string"}
    """
    if not schemas:
        return {}

    # Single schema - return as-is
    if len(schemas) == 1:
        return schemas[0]

    # Check if all schemas are identical (homogeneous)
    first_schema = schemas[0]
    all_same = all(s == first_schema for s in schemas)

    if all_same:
        # Homogeneous: return single schema
        return first_schema
    # Heterogeneous: create oneOf union
    return {"oneOf": schemas}
