"""
Unit tests for Core Type Classes in the Rodos type system.

Tests TypeVariable, ConcreteType, ParametricType, and TypeEnvironment classes.
Following TDD - these tests should fail until implementation is complete.
"""

import pytest

from analysi.services.type_system.types import (
    ConcreteType,
    ParametricType,
    TypeEnvironment,
    TypeVariable,
)


@pytest.mark.unit
class TestTypeVariable:
    """Test TypeVariable class - represents parametric type variables (T, U, F)."""

    def test_type_variable_creation(self):
        """
        Test TypeVariable instances can be created with different names.

        Positive case: Valid variable names.
        """
        # Create type variables with common names
        t_var = TypeVariable("T")
        u_var = TypeVariable("U")
        f_var = TypeVariable("F")

        # Verify name attribute is set correctly
        assert t_var.name == "T"
        assert u_var.name == "U"
        assert f_var.name == "F"

    def test_type_variable_equality(self):
        """
        Test TypeVariable equality semantics.

        Positive and negative cases: Equality based on name.
        """
        # Create two TypeVariables with same name
        t_var_1 = TypeVariable("T")
        t_var_2 = TypeVariable("T")

        # Verify they are equal (== returns True)
        assert t_var_1 == t_var_2

        # Create two TypeVariables with different names
        t_var = TypeVariable("T")
        u_var = TypeVariable("U")

        # Verify they are not equal (== returns False)
        assert t_var != u_var

    def test_type_variable_hashing(self):
        """
        Test TypeVariable can be used as dict key and in sets.

        Positive case: Hashable for use in collections.
        """
        # Create TypeVariable and use as dict key
        t_var = TypeVariable("T")
        type_dict = {t_var: "string"}

        # Verify it can be used in dict
        assert type_dict[t_var] == "string"

        # Verify it can be used in sets
        type_set = {t_var}
        assert t_var in type_set

        # Verify two TypeVariables with same name have same hash
        t_var_2 = TypeVariable("T")
        assert hash(t_var) == hash(t_var_2)

    def test_type_variable_repr(self):
        """
        Test TypeVariable string representation for debugging.

        Positive case: Debugging representation.
        """
        # Create TypeVariable and call repr()
        t_var = TypeVariable("T")
        repr_str = repr(t_var)

        # Verify output contains variable name
        assert "T" in repr_str
        # Verify output is useful for debugging (includes class name)
        assert "TypeVariable" in repr_str or "T" in repr_str


@pytest.mark.unit
class TestConcreteType:
    """Test ConcreteType class - represents concrete JSON Schema types."""

    def test_concrete_type_is_object(self):
        """
        Test ConcreteType.is_object() correctly identifies object types.

        Positive and negative cases: Object type detection.
        """
        # Create ConcreteType with object schema
        object_type = ConcreteType({"type": "object"})
        # Verify is_object() returns True
        assert object_type.is_object() is True

        # Create ConcreteType with string schema
        string_type = ConcreteType({"type": "string"})
        # Verify is_object() returns False
        assert string_type.is_object() is False

        # Create ConcreteType with array schema
        array_type = ConcreteType({"type": "array"})
        # Verify is_object() returns False
        assert array_type.is_object() is False

    def test_concrete_type_is_array(self):
        """
        Test ConcreteType.is_array() correctly identifies array types.

        Positive and negative cases: Array type detection.
        """
        # Create ConcreteType with array schema
        array_type = ConcreteType({"type": "array"})
        # Verify is_array() returns True
        assert array_type.is_array() is True

        # Create ConcreteType with object schema
        object_type = ConcreteType({"type": "object"})
        # Verify is_array() returns False
        assert object_type.is_array() is False

        # Create ConcreteType with string schema
        string_type = ConcreteType({"type": "string"})
        # Verify is_array() returns False
        assert string_type.is_array() is False

    def test_concrete_type_is_primitive(self):
        """
        Test ConcreteType.is_primitive() identifies primitive types.

        Positive and negative cases: Primitive type detection.
        """
        # Create ConcreteType with primitive schemas
        string_type = ConcreteType({"type": "string"})
        number_type = ConcreteType({"type": "number"})
        boolean_type = ConcreteType({"type": "boolean"})
        null_type = ConcreteType({"type": "null"})

        # Verify is_primitive() returns True for each
        assert string_type.is_primitive() is True
        assert number_type.is_primitive() is True
        assert boolean_type.is_primitive() is True
        assert null_type.is_primitive() is True

        # Create ConcreteType with complex types
        object_type = ConcreteType({"type": "object"})
        array_type = ConcreteType({"type": "array"})

        # Verify is_primitive() returns False
        assert object_type.is_primitive() is False
        assert array_type.is_primitive() is False

    def test_concrete_type_get_properties(self):
        """
        Test ConcreteType.get_properties() extracts object properties.

        Positive and negative cases: Property extraction.
        """
        # Create ConcreteType with object schema containing properties
        object_type = ConcreteType(
            {
                "type": "object",
                "properties": {"name": {"type": "string"}, "age": {"type": "number"}},
            }
        )

        # Verify get_properties() returns properties dict
        properties = object_type.get_properties()
        assert "name" in properties
        assert "age" in properties
        assert properties["name"] == {"type": "string"}
        assert properties["age"] == {"type": "number"}

        # Create ConcreteType with non-object schema
        string_type = ConcreteType({"type": "string"})

        # Verify get_properties() returns empty dict
        assert string_type.get_properties() == {}

    def test_concrete_type_get_items(self):
        """
        Test ConcreteType.get_items() extracts array items schema.

        Positive and negative cases: Items extraction.
        """
        # Create ConcreteType with array schema containing items
        array_type = ConcreteType({"type": "array", "items": {"type": "string"}})

        # Verify get_items() returns items schema dict
        items = array_type.get_items()
        assert items == {"type": "string"}

        # Create ConcreteType with non-array schema
        object_type = ConcreteType({"type": "object"})

        # Verify get_items() returns empty dict
        assert object_type.get_items() == {}

    def test_concrete_type_repr(self):
        """
        Test ConcreteType string representation for debugging.

        Positive case: Debugging representation.
        """
        # Create ConcreteType with various schemas
        string_type = ConcreteType({"type": "string"})
        object_type = ConcreteType(
            {"type": "object", "properties": {"name": {"type": "string"}}}
        )

        # Verify repr() output contains schema information
        string_repr = repr(string_type)
        assert "string" in string_repr.lower() or "ConcreteType" in string_repr

        object_repr = repr(object_type)
        assert "object" in object_repr.lower() or "ConcreteType" in object_repr


@pytest.mark.unit
class TestParametricType:
    """Test ParametricType class - represents template types with type variables."""

    def test_parametric_type_creation(self):
        """
        Test ParametricType can be created with variables and schema template.

        Positive case: Valid parametric type creation.
        """
        # Create ParametricType with variables and schema template
        t_var = TypeVariable("T")
        parametric = ParametricType(variables=(t_var,), schema_template={"type": "T"})

        # Verify variables and schema_template attributes are set
        assert parametric.variables == (t_var,)
        assert parametric.schema_template == {"type": "T"}

    def test_parametric_type_substitute_all_bound(self):
        """
        Test ParametricType.substitute() with all variables bound.

        Positive case: All variables bound.
        """
        # Create ParametricType with variable T
        t_var = TypeVariable("T")
        parametric = ParametricType(
            variables=(t_var,),
            schema_template={
                "type": "object",
                "properties": {"field": {"$ref": "#/T"}},
            },
        )

        # Create TypeEnvironment with T bound to string
        env = TypeEnvironment()
        string_type = ConcreteType({"type": "string"})
        env.bind(t_var, string_type)

        # Call substitute(env)
        result = parametric.substitute(env)

        # Verify returns ConcreteType with substitution applied
        assert isinstance(result, ConcreteType)
        # The implementation should replace type variable references

    def test_parametric_type_substitute_unbound_variable(self):
        """
        Test ParametricType.substitute() raises error for unbound variables.

        Negative case: Missing variable binding.
        """
        # Create ParametricType with variable T
        t_var = TypeVariable("T")
        parametric = ParametricType(variables=(t_var,), schema_template={"type": "T"})

        # Create TypeEnvironment without T binding
        env = TypeEnvironment()

        # Call substitute(env)
        # Verify raises ValueError for unbound variable
        with pytest.raises((ValueError, NotImplementedError)):
            parametric.substitute(env)

    def test_parametric_type_repr(self):
        """
        Test ParametricType string representation for debugging.

        Positive case: Debugging representation.
        """
        # Create ParametricType
        t_var = TypeVariable("T")
        parametric = ParametricType(
            variables=(t_var,), schema_template={"type": "object"}
        )

        # Verify repr() output contains variables and template
        repr_str = repr(parametric)
        assert "T" in repr_str or "ParametricType" in repr_str


@pytest.mark.unit
class TestTypeEnvironment:
    """Test TypeEnvironment class - maps type variables to concrete types."""

    def test_type_environment_bind(self):
        """
        Test TypeEnvironment.bind() stores variable bindings.

        Positive case: Variable binding.
        """
        # Create empty TypeEnvironment
        env = TypeEnvironment()

        # Bind TypeVariable to ConcreteType
        t_var = TypeVariable("T")
        string_type = ConcreteType({"type": "string"})
        env.bind(t_var, string_type)

        # Verify binding is stored
        assert env.lookup(t_var) == string_type

    def test_type_environment_bind_already_bound_same(self):
        """
        Test TypeEnvironment.bind() allows rebinding to same type.

        Positive case: Rebinding to same type.
        """
        # Create TypeEnvironment with T bound to string
        env = TypeEnvironment()
        t_var = TypeVariable("T")
        string_type = ConcreteType({"type": "string"})
        env.bind(t_var, string_type)

        # Bind T to string again
        env.bind(t_var, string_type)

        # Verify succeeds (same type is OK)
        assert env.lookup(t_var) == string_type

    def test_type_environment_bind_already_bound_different(self):
        """
        Test TypeEnvironment.bind() rejects conflicting bindings.

        Negative case: Conflicting bindings.
        """
        # Create TypeEnvironment with T bound to string
        env = TypeEnvironment()
        t_var = TypeVariable("T")
        string_type = ConcreteType({"type": "string"})
        env.bind(t_var, string_type)

        # Attempt to bind T to number
        number_type = ConcreteType({"type": "number"})

        # Verify raises ValueError (conflicting binding)
        with pytest.raises((ValueError, NotImplementedError)):
            env.bind(t_var, number_type)

    def test_type_environment_lookup_bound(self):
        """
        Test TypeEnvironment.lookup() returns bound type.

        Positive case: Successful lookup.
        """
        # Create TypeEnvironment with T bound to string
        env = TypeEnvironment()
        t_var = TypeVariable("T")
        string_type = ConcreteType({"type": "string"})
        env.bind(t_var, string_type)

        # Call lookup(T)
        result = env.lookup(t_var)

        # Verify returns string ConcreteType
        assert result == string_type

    def test_type_environment_lookup_unbound(self):
        """
        Test TypeEnvironment.lookup() returns None for unbound variables.

        Positive case: Missing binding returns None.
        """
        # Create empty TypeEnvironment
        env = TypeEnvironment()
        t_var = TypeVariable("T")

        # Call lookup(T)
        result = env.lookup(t_var)

        # Verify returns None
        assert result is None

    def test_type_environment_merge_no_conflicts(self):
        """
        Test TypeEnvironment.merge() combines compatible environments.

        Positive case: Compatible environments merge.
        """
        # Create env1 with T bound to string
        env1 = TypeEnvironment()
        t_var = TypeVariable("T")
        string_type = ConcreteType({"type": "string"})
        env1.bind(t_var, string_type)

        # Create env2 with U bound to number
        env2 = TypeEnvironment()
        u_var = TypeVariable("U")
        number_type = ConcreteType({"type": "number"})
        env2.bind(u_var, number_type)

        # Call env1.merge(env2)
        result = env1.merge(env2)

        # Verify result has both bindings
        assert result.lookup(t_var) == string_type
        assert result.lookup(u_var) == number_type

    def test_type_environment_merge_with_conflicts(self):
        """
        Test TypeEnvironment.merge() rejects conflicting bindings.

        Negative case: Incompatible environments.
        """
        # Create env1 with T bound to string
        env1 = TypeEnvironment()
        t_var = TypeVariable("T")
        string_type = ConcreteType({"type": "string"})
        env1.bind(t_var, string_type)

        # Create env2 with T bound to number
        env2 = TypeEnvironment()
        number_type = ConcreteType({"type": "number"})
        env2.bind(t_var, number_type)

        # Call env1.merge(env2)
        # Verify raises ValueError for conflicting T binding
        with pytest.raises((ValueError, NotImplementedError)):
            env1.merge(env2)

    def test_type_environment_repr(self):
        """
        Test TypeEnvironment string representation for debugging.

        Positive case: Debugging representation.
        """
        # Create TypeEnvironment with bindings
        env = TypeEnvironment()
        t_var = TypeVariable("T")
        string_type = ConcreteType({"type": "string"})
        env.bind(t_var, string_type)

        # Verify repr() output shows bindings
        repr_str = repr(env)
        assert (
            "T" in repr_str or "TypeEnvironment" in repr_str or "bindings" in repr_str
        )
