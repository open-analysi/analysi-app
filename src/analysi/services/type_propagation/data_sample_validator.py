"""
Data sample validation for tasks.

Validates that task data_samples are compatible with what the script expects.
Uses genson for schema generation and jsonschema (Draft 2020-12) for validation.
"""

from typing import Any

from genson import SchemaBuilder
from jsonschema import ValidationError, validate


def _remove_required_fields(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively remove 'required' arrays from a JSON schema.

    Genson marks all observed fields as required, but for alert schemas
    we want permissive validation - fields should be optional by default.

    Args:
        schema: JSON Schema to process

    Returns:
        Schema with all 'required' arrays removed
    """
    if not isinstance(schema, dict):
        return schema

    result = {}
    for key, value in schema.items():
        if key == "required":
            # Skip required arrays entirely
            continue
        if key == "properties" and isinstance(value, dict):
            # Recursively process nested object properties
            result[key] = {
                prop_name: _remove_required_fields(prop_schema)
                for prop_name, prop_schema in value.items()
            }
        elif isinstance(value, dict):
            result[key] = _remove_required_fields(value)
        elif isinstance(value, list):
            result[key] = [
                _remove_required_fields(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value

    return result


def generate_schema_from_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Generate JSON Schema from data samples using genson.

    Uses JSON Schema Draft 7 which is the most widely supported version.
    Genson generates schemas compatible with all modern validators.

    Note: This function removes all 'required' arrays from the generated schema.
    Fields observed in samples define the structure but are not required.
    This is important for alert processing where fields are often optional.

    Args:
        samples: List of data samples (dicts)

    Returns:
        Generated JSON Schema (with no required fields)

    Example:
        >>> samples = [{"ip": "1.2.3.4", "context": "test"}]
        >>> schema = generate_schema_from_samples(samples)
        >>> schema
        {
            "$schema": "http://json-schema.org/schema#",
            "type": "object",
            "properties": {
                "ip": {"type": "string"},
                "context": {"type": "string"}
            }
        }
    """
    builder = SchemaBuilder()

    for sample in samples:
        builder.add_object(sample)

    schema = builder.to_schema()

    # Remove all 'required' arrays - fields should be optional by default
    # This prevents overly strict validation when alerts have optional fields
    return _remove_required_fields(schema)


def validate_sample_against_schema(
    sample: dict[str, Any], schema: dict[str, Any]
) -> tuple[bool, str | None]:
    """
    Validate a data sample against a JSON Schema.

    Uses the standard jsonschema.validate() which auto-detects the schema version
    from the $schema field, or defaults to the latest draft.

    Args:
        sample: Data sample to validate
        schema: JSON Schema to validate against

    Returns:
        Tuple of (is_valid, error_message)

    Example:
        >>> sample = {"ip": "1.2.3.4"}
        >>> schema = {"type": "object", "properties": {"ip": {"type": "string"}}}
        >>> valid, error = validate_sample_against_schema(sample, schema)
        >>> valid
        True
    """
    try:
        # Use generic validate() which auto-detects schema version
        validate(instance=sample, schema=schema)
        return True, None
    except ValidationError as e:
        return False, e.message


def validate_data_samples_completeness(
    data_samples: list[dict[str, Any]], required_fields: set[str]
) -> tuple[bool, list[str]]:
    """
    Check if data samples contain all required fields.

    This is a quick check before full schema validation.

    Args:
        data_samples: List of data samples
        required_fields: Set of field names that must be present

    Returns:
        Tuple of (all_present, missing_fields)

    Example:
        >>> samples = [{"ip": "1.2.3.4"}]
        >>> required = {"ip", "context"}
        >>> valid, missing = validate_data_samples_completeness(samples, required)
        >>> valid
        False
        >>> missing
        ['context']
    """
    if not data_samples:
        return False, list(required_fields)

    # Check first sample (assuming all samples have same structure)
    sample = data_samples[0]
    sample_fields = set(sample.keys())

    missing = required_fields - sample_fields

    return len(missing) == 0, list(missing)


def is_overly_generic_schema(schema: dict[str, Any]) -> bool:
    """
    Check if schema is too generic (just {"type": "object"} with no properties).

    We want to discourage generic schemas unless absolutely necessary.

    Args:
        schema: JSON Schema to check

    Returns:
        True if schema is overly generic

    Example:
        >>> is_overly_generic_schema({"type": "object"})
        True
        >>> is_overly_generic_schema({"type": "object", "properties": {"ip": {"type": "string"}}})
        False
    """
    if schema.get("type") != "object":
        return False

    # If no properties defined, it's overly generic
    return bool("properties" not in schema or not schema["properties"])


def validate_task_data_samples(
    script: str,
    data_samples: list[dict[str, Any]],
    expected_schema: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """
    Validate that task data_samples are compatible with the script.

    Steps:
    1. Generate schema from data_samples (what we provide)
    2. Compare against expected_schema (what script needs)
    3. Validate samples conform to generated schema

    Args:
        script: Cy script to validate against
        data_samples: Data samples to validate
        expected_schema: Optional expected input schema from Cy analysis

    Returns:
        Tuple of (is_valid, error_message)

    Example:
        >>> script = 'ip = input["ip"]\\nreturn {"ip": ip}'
        >>> samples = [{"ip": "1.2.3.4"}]
        >>> expected = {"type": "object", "properties": {"ip": {"type": "string"}}}
        >>> valid, error = validate_task_data_samples(script, samples, expected)
        >>> valid
        True
    """
    if not data_samples:
        return False, "No data_samples provided"

    # Generate schema from samples
    generated_schema = generate_schema_from_samples(data_samples)

    # Check if overly generic
    if is_overly_generic_schema(generated_schema):
        return False, (
            "Generated schema is too generic (no properties defined). "
            "Please provide more specific data samples or define schema explicitly."
        )

    # If expected schema provided, validate compatibility
    if expected_schema:
        # Extract required fields from expected schema
        expected_schema.get("properties", {})
        required_fields = set(expected_schema.get("required", []))

        # Check required fields are present
        if required_fields:
            sample_fields = set(data_samples[0].keys())
            missing = required_fields - sample_fields

            if missing:
                return False, (
                    f"Data samples missing required fields: {sorted(missing)}. "
                    f"Script expects: {sorted(required_fields)}, "
                    f"but samples provide: {sorted(sample_fields)}"
                )

    # Validate each sample against generated schema
    for i, sample in enumerate(data_samples):
        valid, error = validate_sample_against_schema(sample, generated_schema)
        if not valid:
            return False, f"Sample {i} invalid: {error}"

    return True, None
