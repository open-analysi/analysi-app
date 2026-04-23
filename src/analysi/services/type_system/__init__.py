"""
Type System for Typed Workflows

This module provides parametric type checking for workflows, enabling:
- Type inference and validation throughout workflow graphs
- Duck typing for structural compatibility
- Parametric templates with type variables
- Type unification algorithm

Main components:
- types: Core type classes (TypeVariable, ConcreteType, ParametricType, TypeEnvironment)
- unification: Type unification algorithm for binding type variables
- duck_typing: Structural compatibility checking for JSON Schemas
"""

from analysi.services.type_system.duck_typing import (
    get_compatibility_errors,
    is_compatible,
)
from analysi.services.type_system.types import (
    ConcreteType,
    ParametricType,
    TypeEnvironment,
    TypeVariable,
)
from analysi.services.type_system.unification import unify, unify_schemas

__all__ = [
    "ConcreteType",
    "ParametricType",
    "TypeEnvironment",
    # Core types
    "TypeVariable",
    "get_compatibility_errors",
    # Duck typing
    "is_compatible",
    # Unification
    "unify",
    "unify_schemas",
]
