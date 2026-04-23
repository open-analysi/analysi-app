"""
Duck typing validator for structural JSON Schema compatibility.

Provides functions to check if one schema is compatible with another
using structural typing (duck typing) rules:
- Required fields must exist in actual schema
- Required field types must match
- Extra fields in actual schema are allowed
- Recursively check nested objects
"""

from typing import Any


def is_compatible(
    required_schema: dict[str, Any], actual_schema: dict[str, Any]
) -> bool:
    """
    Check structural compatibility (duck typing) between schemas.

    Returns True if actual_schema satisfies required_schema using duck typing rules:
    - All required fields must exist in actual
    - Required field types must match
    - Extra fields in actual are allowed
    - Recursively check nested objects

    Args:
        required_schema: Schema defining requirements
        actual_schema: Schema to check against requirements

    Returns:
        True if actual satisfies required, False otherwise

    Examples:
        >>> required = {"type": "object", "properties": {"name": {"type": "string"}}}
        >>> actual = {"type": "object", "properties": {"name": {"type": "string"}, "age": {"type": "number"}}}
        >>> is_compatible(required, actual)  # True (extra 'age' allowed)

        >>> required = {"type": "object", "properties": {"name": {"type": "string"}}}
        >>> actual = {"type": "object", "properties": {"age": {"type": "number"}}}
        >>> is_compatible(required, actual)  # False (missing 'name')
    """
    # Get the types
    required_type = required_schema.get("type")
    actual_type = actual_schema.get("type")

    # Types must match
    if required_type != actual_type:
        return False

    # Primitives: exact match
    if required_type in ("string", "number", "boolean", "null", "integer"):
        return True

    # Objects: duck typing - check required fields exist
    if required_type == "object":
        required_props = required_schema.get("properties", {})
        actual_props = actual_schema.get("properties", {})
        required_fields = set(required_schema.get("required", []))

        # Check all required properties exist in actual
        for prop_name, prop_schema in required_props.items():
            # If this property is in the required list, it must exist
            if prop_name in required_fields and prop_name not in actual_props:
                return False

            # If property exists in actual, recursively check compatibility
            if prop_name in actual_props and not is_compatible(
                prop_schema, actual_props[prop_name]
            ):
                return False
            # If property is not required and not in actual, that's OK for duck typing
            # (we only check required fields)

        # All required properties are compatible
        return True

    # Arrays: check items compatibility
    if required_type == "array":
        required_items = required_schema.get("items", {})
        actual_items = actual_schema.get("items", {})

        # Recursively check items
        return is_compatible(required_items, actual_items)

    # Unknown type - conservative: not compatible
    return False


def get_compatibility_errors(
    required_schema: dict[str, Any], actual_schema: dict[str, Any], path: str = ""
) -> list[str]:
    """
    Get detailed compatibility error messages.

    Returns a list of human-readable error messages explaining why
    actual_schema does not satisfy required_schema.

    Args:
        required_schema: Schema defining requirements
        actual_schema: Schema to check against requirements
        path: Current path in schema (for nested error messages)

    Returns:
        List of error messages (empty if compatible)

    Examples:
        >>> required = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
        >>> actual = {"type": "object", "properties": {"age": {"type": "number"}}}
        >>> get_compatibility_errors(required, actual)
        ["Missing required field 'name'"]
    """
    errors: list[str] = []

    # Get the types
    required_type = required_schema.get("type")
    actual_type = actual_schema.get("type")

    # Check type mismatch
    if required_type != actual_type:
        prefix = f"At {path}: " if path else ""
        errors.append(
            f"{prefix}Type mismatch - required: {required_type}, actual: {actual_type}"
        )
        return errors

    # Primitives: no further checks needed
    if required_type in ("string", "number", "boolean", "null", "integer"):
        return errors

    # Objects: check required fields
    if required_type == "object":
        required_props = required_schema.get("properties", {})
        actual_props = actual_schema.get("properties", {})
        required_fields = set(required_schema.get("required", []))

        # Check all required properties
        for prop_name, prop_schema in required_props.items():
            prop_path = f"{path}.{prop_name}" if path else prop_name

            # Check if required field is missing
            if prop_name in required_fields and prop_name not in actual_props:
                errors.append(f"Missing required field '{prop_path}'")
                continue

            # If property exists in actual, recursively check compatibility
            if prop_name in actual_props:
                nested_errors = get_compatibility_errors(
                    prop_schema, actual_props[prop_name], prop_path
                )
                errors.extend(nested_errors)

        return errors

    # Arrays: check items
    if required_type == "array":
        required_items = required_schema.get("items", {})
        actual_items = actual_schema.get("items", {})

        items_path = f"{path}[]" if path else "[]"
        nested_errors = get_compatibility_errors(
            required_items, actual_items, items_path
        )
        errors.extend(nested_errors)

        return errors

    # Unknown type
    prefix = f"At {path}: " if path else ""
    errors.append(f"{prefix}Unknown schema type: {required_type}")
    return errors
