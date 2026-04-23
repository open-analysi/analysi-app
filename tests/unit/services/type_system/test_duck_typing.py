"""
Unit tests for Duck Typing Validator in the Rodos type system.

Tests is_compatible() and get_compatibility_errors() functions for structural typing.
Following TDD - these tests should fail until implementation is complete.
"""

import pytest

from analysi.services.type_system.duck_typing import (
    get_compatibility_errors,
    is_compatible,
)


@pytest.mark.unit
class TestBasicCompatibility:
    """Test basic duck typing compatibility checks."""

    def test_is_compatible_exact_match(self):
        """
        Test compatibility with identical schemas.

        Positive case: Exact match is compatible.
        """
        # Create identical required and actual schemas
        required = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
        }
        actual = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
        }

        # Call is_compatible(required, actual)
        result = is_compatible(required, actual)

        # Verify returns True
        assert result is True

    def test_is_compatible_actual_has_extra_fields(self):
        """
        Test compatibility when actual has extra fields.

        Positive case: Duck typing allows extra fields.
        """
        # Create required schema with fields {name, age}
        required = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
        }

        # Create actual schema with fields {name, age, email}
        actual = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "number"},
                "email": {"type": "string"},
            },
        }

        # Call is_compatible(required, actual)
        result = is_compatible(required, actual)

        # Verify returns True (extra fields allowed)
        assert result is True

    def test_is_compatible_actual_missing_required_field(self):
        """
        Test incompatibility when actual is missing required field.

        Negative case: Missing required field.
        """
        # Create required schema with fields {name, age}
        required = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
            "required": ["name", "age"],
        }

        # Create actual schema with only {name}
        actual = {"type": "object", "properties": {"name": {"type": "string"}}}

        # Call is_compatible(required, actual)
        result = is_compatible(required, actual)

        # Verify returns False (missing age)
        assert result is False

    def test_is_compatible_field_type_mismatch(self):
        """
        Test incompatibility when field types don't match.

        Negative case: Field type mismatch.
        """
        # Create required schema with {name: string}
        required = {"type": "object", "properties": {"name": {"type": "string"}}}

        # Create actual schema with {name: number}
        actual = {"type": "object", "properties": {"name": {"type": "number"}}}

        # Call is_compatible(required, actual)
        result = is_compatible(required, actual)

        # Verify returns False (type mismatch)
        assert result is False

    def test_is_compatible_nested_objects(self):
        """
        Test compatibility with nested objects.

        Positive case: Nested object compatibility.
        """
        # Create required schema with nested object {user: {name: string}}
        required = {
            "type": "object",
            "properties": {
                "user": {"type": "object", "properties": {"name": {"type": "string"}}}
            },
        }

        # Create actual schema with matching nested structure plus extras
        actual = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "email": {"type": "string"},
                    },
                },
                "created_at": {"type": "string"},
            },
        }

        # Call is_compatible(required, actual)
        result = is_compatible(required, actual)

        # Verify returns True (nested duck typing)
        assert result is True

    def test_is_compatible_nested_object_mismatch(self):
        """
        Test incompatibility with nested type mismatch.

        Negative case: Nested type mismatch.
        """
        # Create required schema with nested object {user: {name: string}}
        required = {
            "type": "object",
            "properties": {
                "user": {"type": "object", "properties": {"name": {"type": "string"}}}
            },
        }

        # Create actual schema with {user: {name: number}}
        actual = {
            "type": "object",
            "properties": {
                "user": {"type": "object", "properties": {"name": {"type": "number"}}}
            },
        }

        # Call is_compatible(required, actual)
        result = is_compatible(required, actual)

        # Verify returns False (nested mismatch)
        assert result is False

    def test_is_compatible_array_types(self):
        """
        Test compatibility with array types.

        Positive case: Array type compatibility.
        """
        # Create required schema with array of strings
        required = {"type": "array", "items": {"type": "string"}}

        # Create actual schema with array of strings
        actual = {"type": "array", "items": {"type": "string"}}

        # Call is_compatible(required, actual)
        result = is_compatible(required, actual)

        # Verify returns True
        assert result is True

    def test_is_compatible_array_type_mismatch(self):
        """
        Test incompatibility with array items mismatch.

        Negative case: Array items mismatch.
        """
        # Create required schema with array of strings
        required = {"type": "array", "items": {"type": "string"}}

        # Create actual schema with array of numbers
        actual = {"type": "array", "items": {"type": "number"}}

        # Call is_compatible(required, actual)
        result = is_compatible(required, actual)

        # Verify returns False
        assert result is False


@pytest.mark.unit
class TestErrorReporting:
    """Test error reporting for incompatible schemas."""

    def test_get_compatibility_errors_no_errors(self):
        """
        Test no errors reported for compatible schemas.

        Positive case: Compatible schemas have no errors.
        """
        # Create compatible required and actual schemas
        required = {"type": "object", "properties": {"name": {"type": "string"}}}
        actual = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
        }

        # Call get_compatibility_errors(required, actual)
        errors = get_compatibility_errors(required, actual)

        # Verify returns empty list
        assert errors == []

    def test_get_compatibility_errors_missing_field(self):
        """
        Test error reporting for missing required field.

        Negative case: Clear error for missing field.
        """
        # Create required schema needing {name, age}
        required = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
            "required": ["name", "age"],
        }

        # Create actual schema with only {name}
        actual = {"type": "object", "properties": {"name": {"type": "string"}}}

        # Call get_compatibility_errors(required, actual)
        errors = get_compatibility_errors(required, actual)

        # Verify returns error message mentioning missing "age"
        assert len(errors) > 0
        assert any("age" in err.lower() for err in errors)

    def test_get_compatibility_errors_wrong_type(self):
        """
        Test error reporting for type mismatch.

        Negative case: Clear error for type mismatch.
        """
        # Create required schema with {name: string}
        required = {"type": "object", "properties": {"name": {"type": "string"}}}

        # Create actual schema with {name: number}
        actual = {"type": "object", "properties": {"name": {"type": "number"}}}

        # Call get_compatibility_errors(required, actual)
        errors = get_compatibility_errors(required, actual)

        # Verify returns error mentioning type mismatch on "name"
        assert len(errors) > 0
        assert any("name" in err.lower() for err in errors)
        assert any("type" in err.lower() or "mismatch" in err.lower() for err in errors)

    def test_get_compatibility_errors_multiple_errors(self):
        """
        Test error reporting with multiple issues.

        Negative case: All errors reported.
        """
        # Create required schema with {name: string, age: number}
        required = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
            "required": ["name", "age"],
        }

        # Create actual schema with {name: number} (wrong type + missing field)
        actual = {"type": "object", "properties": {"name": {"type": "number"}}}

        # Call get_compatibility_errors(required, actual)
        errors = get_compatibility_errors(required, actual)

        # Verify returns list with both errors
        assert len(errors) >= 2
        # Should mention both "name" type issue and missing "age"
        error_text = " ".join(errors).lower()
        assert "name" in error_text
        assert "age" in error_text

    def test_get_compatibility_errors_nested_error(self):
        """
        Test error reporting with nested field errors.

        Negative case: Nested errors have clear paths.
        """
        # Create required schema with nested object
        required = {
            "type": "object",
            "properties": {
                "user": {"type": "object", "properties": {"name": {"type": "string"}}}
            },
        }

        # Create actual schema with nested mismatch
        actual = {
            "type": "object",
            "properties": {
                "user": {"type": "object", "properties": {"name": {"type": "number"}}}
            },
        }

        # Call get_compatibility_errors(required, actual)
        errors = get_compatibility_errors(required, actual)

        # Verify error message includes path to nested field
        assert len(errors) > 0
        error_text = " ".join(errors).lower()
        # Should mention "user" and/or "name" and type issue
        assert (
            "user" in error_text and "name" in error_text
        ) or "user.name" in error_text


@pytest.mark.unit
class TestDeeplyNestedStructures:
    """Test duck typing with deeply nested (3+ levels) structures."""

    def test_deeply_nested_objects_compatible(self):
        """
        Test compatibility with deeply nested objects (4 levels).

        Positive case: Deep nesting with extra fields at each level.
        """
        # Create required schema with 4 levels of nesting
        required = {
            "type": "object",
            "properties": {
                "organization": {
                    "type": "object",
                    "properties": {
                        "department": {
                            "type": "object",
                            "properties": {
                                "team": {
                                    "type": "object",
                                    "properties": {
                                        "member": {
                                            "type": "object",
                                            "properties": {"name": {"type": "string"}},
                                        }
                                    },
                                }
                            },
                        }
                    },
                }
            },
        }

        # Create actual schema with same structure plus extras at each level
        actual = {
            "type": "object",
            "properties": {
                "organization": {
                    "type": "object",
                    "properties": {
                        "department": {
                            "type": "object",
                            "properties": {
                                "team": {
                                    "type": "object",
                                    "properties": {
                                        "member": {
                                            "type": "object",
                                            "properties": {
                                                "name": {"type": "string"},
                                                "id": {"type": "number"},  # Extra field
                                            },
                                        },
                                        "size": {"type": "number"},  # Extra field
                                    },
                                },
                                "budget": {"type": "number"},  # Extra field
                            },
                        },
                        "location": {"type": "string"},  # Extra field
                    },
                },
                "created_at": {"type": "string"},  # Extra field
            },
        }

        # Call is_compatible(required, actual)
        result = is_compatible(required, actual)

        # Verify returns True (extra fields at all levels allowed)
        assert result is True

    def test_deeply_nested_type_mismatch(self):
        """
        Test incompatibility with type mismatch at deep level.

        Negative case: Type mismatch at 4th level should be detected.
        """
        # Create required schema with 4 levels
        required = {
            "type": "object",
            "properties": {
                "level1": {
                    "type": "object",
                    "properties": {
                        "level2": {
                            "type": "object",
                            "properties": {
                                "level3": {
                                    "type": "object",
                                    "properties": {"level4": {"type": "string"}},
                                }
                            },
                        }
                    },
                }
            },
        }

        # Create actual schema with mismatch at deepest level
        actual = {
            "type": "object",
            "properties": {
                "level1": {
                    "type": "object",
                    "properties": {
                        "level2": {
                            "type": "object",
                            "properties": {
                                "level3": {
                                    "type": "object",
                                    "properties": {
                                        "level4": {"type": "number"}  # Type mismatch!
                                    },
                                }
                            },
                        }
                    },
                }
            },
        }

        # Call is_compatible(required, actual)
        result = is_compatible(required, actual)

        # Verify returns False (deep mismatch detected)
        assert result is False

    def test_deeply_nested_missing_field(self):
        """
        Test incompatibility with missing required field at deep level.

        Negative case: Missing field at 3rd level should be detected.
        """
        # Create required schema with required field at level 3
        required = {
            "type": "object",
            "properties": {
                "config": {
                    "type": "object",
                    "properties": {
                        "database": {
                            "type": "object",
                            "properties": {
                                "host": {"type": "string"},
                                "port": {"type": "number"},
                            },
                            "required": ["host", "port"],
                        }
                    },
                }
            },
        }

        # Create actual schema missing "port" at level 3
        actual = {
            "type": "object",
            "properties": {
                "config": {
                    "type": "object",
                    "properties": {
                        "database": {
                            "type": "object",
                            "properties": {
                                "host": {"type": "string"}
                                # Missing "port"
                            },
                        }
                    },
                }
            },
        }

        # Call is_compatible(required, actual)
        result = is_compatible(required, actual)

        # Verify returns False (missing required field)
        assert result is False

    def test_deeply_nested_error_path(self):
        """
        Test error reporting with deeply nested path.

        Negative case: Error path should show full nested path.
        """
        # Create required schema with deep nesting
        required = {
            "type": "object",
            "properties": {
                "api": {
                    "type": "object",
                    "properties": {
                        "endpoints": {
                            "type": "object",
                            "properties": {
                                "users": {
                                    "type": "object",
                                    "properties": {"method": {"type": "string"}},
                                    "required": ["method"],
                                }
                            },
                        }
                    },
                }
            },
        }

        # Create actual schema missing deep field
        actual = {
            "type": "object",
            "properties": {
                "api": {
                    "type": "object",
                    "properties": {
                        "endpoints": {
                            "type": "object",
                            "properties": {
                                "users": {
                                    "type": "object",
                                    "properties": {},  # Missing "method"
                                }
                            },
                        }
                    },
                }
            },
        }

        # Call get_compatibility_errors(required, actual)
        errors = get_compatibility_errors(required, actual)

        # Verify error includes full path
        assert len(errors) > 0
        error_text = " ".join(errors)
        # Should have path showing api.endpoints.users.method or similar
        assert "method" in error_text.lower()
        # Check for hierarchical path (multiple dots or sequential mentions)
        assert (
            "api" in error_text.lower()
            or "endpoints" in error_text.lower()
            or "users" in error_text.lower()
        )

    def test_nested_arrays_with_nested_objects(self):
        """
        Test arrays containing deeply nested objects.

        Positive case: Complex nested structure with arrays and objects.
        """
        # Create required schema: array of objects with nested objects
        required = {
            "type": "object",
            "properties": {
                "records": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "metadata": {
                                "type": "object",
                                "properties": {
                                    "tags": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    }
                                },
                            }
                        },
                    },
                }
            },
        }

        # Create actual schema with matching structure plus extras
        actual = {
            "type": "object",
            "properties": {
                "records": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "metadata": {
                                "type": "object",
                                "properties": {
                                    "tags": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "version": {"type": "number"},  # Extra field
                                },
                            },
                            "id": {"type": "string"},  # Extra field
                        },
                    },
                }
            },
        }

        # Call is_compatible(required, actual)
        result = is_compatible(required, actual)

        # Verify returns True
        assert result is True

    def test_nested_arrays_type_mismatch(self):
        """
        Test incompatibility in nested array items.

        Negative case: Type mismatch in deeply nested array items.
        """
        # Create required schema with nested arrays
        required = {
            "type": "object",
            "properties": {
                "data": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "values": {"type": "array", "items": {"type": "number"}}
                        },
                    },
                }
            },
        }

        # Create actual schema with wrong type in nested array
        actual = {
            "type": "object",
            "properties": {
                "data": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "values": {
                                "type": "array",
                                "items": {"type": "string"},  # Type mismatch!
                            }
                        },
                    },
                }
            },
        }

        # Call is_compatible(required, actual)
        result = is_compatible(required, actual)

        # Verify returns False
        assert result is False
