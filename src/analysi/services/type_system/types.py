"""
Core type classes for parametric type system.

Provides the fundamental building blocks for type inference:
- TypeVariable: Parametric type variables (T, U, F)
- ConcreteType: Concrete JSON Schema types
- ParametricType: Template types with type variables
- TypeEnvironment: Bindings from type variables to concrete types
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TypeVariable:
    """
    Represents a parametric type variable (e.g., T, U, F).

    Type variables are used in templates to express generic behavior.
    For example, Identity template has signature T => T.

    Attributes:
        name: Variable name (e.g., 'T', 'U', 'F')
    """

    name: str

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return f"TypeVariable({self.name!r})"


@dataclass(frozen=True)
class ConcreteType:
    """
    Represents a concrete JSON Schema type.

    This wraps a JSON Schema and provides utility methods for
    inspecting and working with the schema.

    Attributes:
        schema: JSON Schema dict representing the type
    """

    schema: dict[str, Any]

    def is_object(self) -> bool:
        """Check if this is an object type."""
        return self.schema.get("type") == "object"

    def is_array(self) -> bool:
        """Check if this is an array type."""
        return self.schema.get("type") == "array"

    def is_primitive(self) -> bool:
        """Check if this is a primitive type (string, number, boolean, null)."""
        schema_type = self.schema.get("type")
        return schema_type in ("string", "number", "boolean", "null", "integer")

    def get_properties(self) -> dict[str, Any]:
        """Get object properties schema (empty dict if not an object)."""
        if self.is_object():
            return self.schema.get("properties", {})
        return {}

    def get_items(self) -> dict[str, Any]:
        """Get array items schema (empty dict if not an array)."""
        if self.is_array():
            return self.schema.get("items", {})
        return {}

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        schema_type = self.schema.get("type", "unknown")
        return f"ConcreteType(type={schema_type!r})"


@dataclass(frozen=True)
class ParametricType:
    """
    Represents a template type with type variables.

    For example, Merge template might have type:
    [T1, T2] => {...T1, ...T2}

    Attributes:
        variables: List of type variables used in this type
        schema_template: JSON Schema template (may contain variable references)
    """

    variables: tuple[TypeVariable, ...]
    schema_template: dict[str, Any]

    def substitute(self, env: "TypeEnvironment") -> ConcreteType:
        """
        Substitute type variables with concrete types from environment.

        Args:
            env: Type environment with variable bindings

        Returns:
            Concrete type with all variables substituted

        Raises:
            ValueError: If some variables are not bound in environment
        """
        # Check all variables are bound
        for var in self.variables:
            if env.lookup(var) is None:
                raise ValueError(f"Unbound type variable: {var.name}")

        # For now, return schema_template as-is
        # Full substitution would require walking the schema tree and replacing
        # type variable references (not yet implemented)
        return ConcreteType(self.schema_template)

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        var_names = ", ".join(v.name for v in self.variables)
        return f"ParametricType([{var_names}])"


@dataclass
class TypeEnvironment:
    """
    Maps type variables to concrete types (bindings).

    Used during type unification to track which type variables
    have been bound to which concrete types.

    Attributes:
        bindings: Dict mapping variable names to concrete types
    """

    bindings: dict[str, ConcreteType] = field(default_factory=dict)

    def bind(self, var: TypeVariable, concrete_type: ConcreteType) -> None:
        """
        Bind a type variable to a concrete type.

        Args:
            var: Type variable to bind
            concrete_type: Concrete type to bind to

        Raises:
            ValueError: If variable is already bound to a different type
        """
        existing = self.bindings.get(var.name)
        if existing is not None:
            # Check if trying to bind to a different type
            if existing.schema != concrete_type.schema:
                raise ValueError(
                    f"Type variable {var.name} already bound to {existing}, "
                    f"cannot rebind to {concrete_type}"
                )
            # Same type, no-op
            return
        self.bindings[var.name] = concrete_type

    def lookup(self, var: TypeVariable) -> ConcreteType | None:
        """
        Look up the concrete type bound to a variable.

        Args:
            var: Type variable to look up

        Returns:
            Concrete type if bound, None otherwise
        """
        return self.bindings.get(var.name)

    def merge(self, other: "TypeEnvironment") -> "TypeEnvironment":
        """
        Merge two type environments.

        Args:
            other: Environment to merge with

        Returns:
            New environment with combined bindings

        Raises:
            ValueError: If environments have conflicting bindings
        """
        # Create new environment with copy of current bindings
        new_env = TypeEnvironment(bindings=dict(self.bindings))

        # Merge other's bindings
        for var_name, concrete_type in other.bindings.items():
            existing = new_env.bindings.get(var_name)
            if existing is not None and existing.schema != concrete_type.schema:
                raise ValueError(
                    f"Conflicting bindings for {var_name}: "
                    f"{existing} vs {concrete_type}"
                )
            new_env.bindings[var_name] = concrete_type

        return new_env

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        if not self.bindings:
            return "TypeEnvironment({})"
        bindings_str = ", ".join(f"{k}: {v}" for k, v in self.bindings.items())
        return f"TypeEnvironment({{{bindings_str}}})"
