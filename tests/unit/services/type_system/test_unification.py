"""
Unit tests for Type Unification algorithm in the Rodos type system.

Tests unify() and unify_schemas() functions for binding type variables.
Following TDD - these tests should fail until implementation is complete.
"""

import pytest

from analysi.services.type_system.types import (
    ConcreteType,
    TypeEnvironment,
    TypeVariable,
)
from analysi.services.type_system.unification import unify, unify_schemas


@pytest.mark.unit
class TestBasicUnification:
    """Test basic unification operations between type variables and concrete types."""

    def test_unify_type_variable_with_concrete(self):
        """
        Test unifying a TypeVariable with a ConcreteType binds the variable.

        Positive case: Variable gets bound to concrete type.
        """
        # Create TypeVariable T and ConcreteType string
        t_var = TypeVariable("T")
        string_type = ConcreteType({"type": "string"})
        empty_env = TypeEnvironment()

        # Call unify(T, string, empty_env)
        result = unify(t_var, string_type, empty_env)

        # Verify returns environment with T bound to string
        assert result is not None
        assert result.lookup(t_var) == string_type

    def test_unify_concrete_with_type_variable(self):
        """
        Test unifying a ConcreteType with a TypeVariable (symmetric).

        Positive case: Symmetric to previous test.
        """
        # Create ConcreteType string and TypeVariable T
        string_type = ConcreteType({"type": "string"})
        t_var = TypeVariable("T")
        empty_env = TypeEnvironment()

        # Call unify(string, T, empty_env)
        result = unify(string_type, t_var, empty_env)

        # Verify returns environment with T bound to string
        assert result is not None
        assert result.lookup(t_var) == string_type

    def test_unify_type_variable_with_type_variable(self):
        """
        Test unifying two TypeVariables binds one to the other.

        Positive case: Variable bound to variable.
        """
        # Create TypeVariables T and U
        t_var = TypeVariable("T")
        u_var = TypeVariable("U")
        empty_env = TypeEnvironment()

        # Call unify(T, U, empty_env)
        result = unify(t_var, u_var, empty_env)

        # Verify returns environment with one bound to the other
        assert result is not None
        # Either T bound to U or U bound to T (implementation dependent)
        assert result.lookup(t_var) is not None or result.lookup(u_var) is not None

    def test_unify_concrete_with_concrete_same(self):
        """
        Test unifying two identical ConcreteTypes succeeds.

        Positive case: Identical types unify.
        """
        # Create two identical ConcreteType instances (both string)
        string_type_1 = ConcreteType({"type": "string"})
        string_type_2 = ConcreteType({"type": "string"})
        empty_env = TypeEnvironment()

        # Call unify(string1, string2, empty_env)
        result = unify(string_type_1, string_type_2, empty_env)

        # Verify returns original environment (compatible)
        assert result is not None

    def test_unify_concrete_with_concrete_different(self):
        """
        Test unifying different ConcreteTypes fails.

        Negative case: Different primitive types don't unify.
        """
        # Create ConcreteType string and ConcreteType number
        string_type = ConcreteType({"type": "string"})
        number_type = ConcreteType({"type": "number"})
        empty_env = TypeEnvironment()

        # Call unify(string, number, empty_env)
        result = unify(string_type, number_type, empty_env)

        # Verify returns None (incompatible)
        assert result is None

    def test_unify_respects_existing_bindings(self):
        """
        Test unify respects existing variable bindings.

        Positive case: Existing bindings respected.
        """
        # Create env with T bound to string
        env = TypeEnvironment()
        t_var = TypeVariable("T")
        string_type = ConcreteType({"type": "string"})
        env.bind(t_var, string_type)

        # Create ConcreteType string
        string_type_2 = ConcreteType({"type": "string"})

        # Call unify(T, string, env)
        result = unify(t_var, string_type_2, env)

        # Verify returns env (consistent with existing binding)
        assert result is not None

    def test_unify_detects_conflicting_bindings(self):
        """
        Test unify detects conflicts with existing bindings.

        Negative case: Conflicting bindings detected.
        """
        # Create env with T bound to string
        env = TypeEnvironment()
        t_var = TypeVariable("T")
        string_type = ConcreteType({"type": "string"})
        env.bind(t_var, string_type)

        # Create ConcreteType number
        number_type = ConcreteType({"type": "number"})

        # Call unify(T, number, env)
        result = unify(t_var, number_type, env)

        # Verify returns None (conflicts with existing binding)
        assert result is None


@pytest.mark.unit
class TestSchemaUnification:
    """Test unification of JSON Schemas."""

    def test_unify_schemas_primitive_same(self):
        """
        Test unifying two identical primitive schemas.

        Positive case: Same primitive types.
        """
        # Create two string schemas
        schema1 = {"type": "string"}
        schema2 = {"type": "string"}
        empty_env = TypeEnvironment()

        # Call unify_schemas(schema1, schema2, empty_env)
        result = unify_schemas(schema1, schema2, empty_env)

        # Verify returns env (compatible)
        assert result is not None

    def test_unify_schemas_primitive_different(self):
        """
        Test unifying different primitive schemas fails.

        Negative case: Different primitive types.
        """
        # Create string schema and number schema
        schema1 = {"type": "string"}
        schema2 = {"type": "number"}
        empty_env = TypeEnvironment()

        # Call unify_schemas(schema1, schema2, empty_env)
        result = unify_schemas(schema1, schema2, empty_env)

        # Verify returns None (incompatible)
        assert result is None

    def test_unify_schemas_object_same_properties(self):
        """
        Test unifying object schemas with matching properties.

        Positive case: Objects with matching properties.
        """
        # Create two object schemas with same properties
        schema1 = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
        }
        schema2 = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
        }
        empty_env = TypeEnvironment()

        # Call unify_schemas(schema1, schema2, empty_env)
        result = unify_schemas(schema1, schema2, empty_env)

        # Verify returns env (compatible)
        assert result is not None

    def test_unify_schemas_object_different_properties(self):
        """
        Test unifying object schemas with different properties fails.

        Negative case: Objects with mismatched properties.
        """
        # Create two object schemas with different property names
        schema1 = {"type": "object", "properties": {"name": {"type": "string"}}}
        schema2 = {"type": "object", "properties": {"email": {"type": "string"}}}
        empty_env = TypeEnvironment()

        # Call unify_schemas(schema1, schema2, empty_env)
        result = unify_schemas(schema1, schema2, empty_env)

        # Verify returns None (incompatible)
        assert result is None

    def test_unify_schemas_object_nested(self):
        """
        Test unifying nested object schemas recursively.

        Positive case: Nested object unification.
        """
        # Create two nested object schemas
        schema1 = {
            "type": "object",
            "properties": {
                "user": {"type": "object", "properties": {"name": {"type": "string"}}}
            },
        }
        schema2 = {
            "type": "object",
            "properties": {
                "user": {"type": "object", "properties": {"name": {"type": "string"}}}
            },
        }
        empty_env = TypeEnvironment()

        # Call unify_schemas(schema1, schema2, empty_env)
        result = unify_schemas(schema1, schema2, empty_env)

        # Verify recursive unification works
        assert result is not None

    def test_unify_schemas_array_same_items(self):
        """
        Test unifying array schemas with matching items.

        Positive case: Arrays with matching items.
        """
        # Create two array schemas with same items type
        schema1 = {"type": "array", "items": {"type": "string"}}
        schema2 = {"type": "array", "items": {"type": "string"}}
        empty_env = TypeEnvironment()

        # Call unify_schemas(schema1, schema2, empty_env)
        result = unify_schemas(schema1, schema2, empty_env)

        # Verify returns env (compatible)
        assert result is not None

    def test_unify_schemas_array_different_items(self):
        """
        Test unifying array schemas with different items fails.

        Negative case: Arrays with mismatched items.
        """
        # Create two array schemas with different items types
        schema1 = {"type": "array", "items": {"type": "string"}}
        schema2 = {"type": "array", "items": {"type": "number"}}
        empty_env = TypeEnvironment()

        # Call unify_schemas(schema1, schema2, empty_env)
        result = unify_schemas(schema1, schema2, empty_env)

        # Verify returns None (incompatible)
        assert result is None

    def test_unify_schemas_complex_nested(self):
        """
        Test unifying complex nested schemas.

        Positive case: Complex nested structures.
        """
        # Create complex nested schemas (objects with arrays of objects)
        schema1 = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "value": {"type": "number"},
                        },
                    },
                }
            },
        }
        schema2 = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "value": {"type": "number"},
                        },
                    },
                }
            },
        }
        empty_env = TypeEnvironment()

        # Call unify_schemas(schema1, schema2, empty_env)
        result = unify_schemas(schema1, schema2, empty_env)

        # Verify deep recursive unification works
        assert result is not None
