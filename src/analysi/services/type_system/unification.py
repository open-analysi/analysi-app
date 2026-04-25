"""
Type unification algorithm for binding type variables to concrete types.

Provides the core algorithm for type inference:
- unify: Unify two types, returning updated type environment
- unify_schemas: Recursively unify two JSON Schemas

The unification algorithm is used to infer concrete types for
type variables in parametric templates.
"""

from typing import Any

from analysi.services.type_system.types import (
    ConcreteType,
    TypeEnvironment,
    TypeVariable,
)


def unify(  # noqa: C901
    type1: ConcreteType | TypeVariable,
    type2: ConcreteType | TypeVariable,
    env: TypeEnvironment,
) -> TypeEnvironment | None:
    """
    Unify two types, returning updated type environment or None if incompatible.

    This is the core unification algorithm that handles:
    - TypeVariable + TypeVariable: Bind one to the other
    - TypeVariable + ConcreteType: Bind variable to concrete type
    - ConcreteType + ConcreteType: Check structural compatibility

    Args:
        type1: First type to unify
        type2: Second type to unify
        env: Current type environment

    Returns:
        Updated type environment with new bindings, or None if types are incompatible

    Examples:
        >>> env = TypeEnvironment()
        >>> T = TypeVariable("T")
        >>> concrete = ConcreteType({"type": "string"})
        >>> new_env = unify(T, concrete, env)
        >>> new_env.lookup(T)  # Returns concrete
    """
    # Make a copy of environment to avoid mutating the input
    new_env = TypeEnvironment(bindings=dict(env.bindings))

    # Case 1: TypeVariable + TypeVariable
    if isinstance(type1, TypeVariable) and isinstance(type2, TypeVariable):
        # Check if either is already bound
        bound1 = new_env.lookup(type1)
        bound2 = new_env.lookup(type2)

        if bound1 is not None and bound2 is not None:
            # Both bound - recursively unify their bindings
            return unify(bound1, bound2, new_env)
        if bound1 is not None:
            # type1 bound - bind type2 to same thing
            try:
                new_env.bind(type2, bound1)
                return new_env
            except ValueError:
                return None
        elif bound2 is not None:
            # type2 bound - bind type1 to same thing
            try:
                new_env.bind(type1, bound2)
                return new_env
            except ValueError:
                return None
        else:
            # Neither bound - bind type1 to type2 (arbitrary choice)
            # We represent this by creating a "placeholder" binding
            # For now, we just bind one to the other by name
            # This is a simplified approach - full implementation would use union-find
            try:
                new_env.bind(type1, ConcreteType({"type": "any"}))
                new_env.bind(type2, ConcreteType({"type": "any"}))
                return new_env
            except ValueError:
                return None

    # Case 2: TypeVariable + ConcreteType (or vice versa)
    elif isinstance(type1, TypeVariable):
        bound = new_env.lookup(type1)
        if bound is not None:
            # Variable already bound - unify with bound type
            return unify(bound, type2, new_env)
        # Bind variable to concrete type
        if isinstance(type2, TypeVariable):
            bound2 = new_env.lookup(type2)
            if bound2 is not None:
                try:
                    new_env.bind(type1, bound2)
                    return new_env
                except ValueError:
                    return None
        else:
            try:
                new_env.bind(type1, type2)
                return new_env
            except ValueError:
                return None

    elif isinstance(type2, TypeVariable):
        bound = new_env.lookup(type2)
        if bound is not None:
            # Variable already bound - unify with bound type
            return unify(type1, bound, new_env)
        # Bind variable to concrete type
        try:
            new_env.bind(type2, type1)
            return new_env
        except ValueError:
            return None

    # Case 3: ConcreteType + ConcreteType
    else:
        # Both are concrete types - use schema unification
        return unify_schemas(type1.schema, type2.schema, new_env)

    return None


def unify_schemas(
    schema1: dict[str, Any], schema2: dict[str, Any], env: TypeEnvironment
) -> TypeEnvironment | None:
    """
    Recursively unify two JSON Schemas.

    Handles different schema types:
    - Objects: Recursively unify properties
    - Arrays: Unify items schemas
    - Primitives: Exact match required

    Args:
        schema1: First JSON Schema
        schema2: Second JSON Schema
        env: Current type environment

    Returns:
        Updated type environment, or None if schemas are incompatible

    Examples:
        >>> env = TypeEnvironment()
        >>> schema1 = {"type": "object", "properties": {"name": {"type": "string"}}}
        >>> schema2 = {"type": "object", "properties": {"name": {"type": "string"}}}
        >>> unify_schemas(schema1, schema2, env)  # Returns env (compatible)
    """
    # Get the types
    type1 = schema1.get("type")
    type2 = schema2.get("type")

    # Types must match
    if type1 != type2:
        return None

    # Primitives: exact match
    if type1 in ("string", "number", "boolean", "null", "integer"):
        return env

    # Objects: recursively unify properties
    if type1 == "object":
        props1 = schema1.get("properties", {})
        props2 = schema2.get("properties", {})

        # All property names must match for unification
        # (duck typing is different - that allows extra fields)
        if set(props1.keys()) != set(props2.keys()):
            return None

        # Recursively unify each property
        current_env = env
        for prop_name in props1:
            result = unify_schemas(props1[prop_name], props2[prop_name], current_env)
            if result is None:
                return None
            current_env = result

        return current_env

    # Arrays: unify items schemas
    if type1 == "array":
        items1 = schema1.get("items", {})
        items2 = schema2.get("items", {})

        # Recursively unify items
        return unify_schemas(items1, items2, env)

    # Unknown type - conservative: return None
    return None
