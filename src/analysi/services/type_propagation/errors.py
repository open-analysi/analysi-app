"""
Error types for type propagation.

Provides structured error classes for reporting type propagation issues
with actionable suggestions for fixing workflows.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class TypePropagationError:
    """Base class for type propagation errors."""

    node_id: str
    error_type: str
    message: str
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert error to JSON-serializable dictionary."""
        raise NotImplementedError("Subclasses must implement to_dict()")


@dataclass
class TypeMismatchError(TypePropagationError):
    """Error when predecessor output doesn't match successor input schema."""

    expected_schema: dict[str, Any] | None = None
    actual_schema: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with schema details."""
        return {
            "node_id": self.node_id,
            "error_type": self.error_type,
            "message": self.message,
            "suggestion": self.suggestion,
            "expected_schema": self.expected_schema,
            "actual_schema": self.actual_schema,
        }


@dataclass
class MergeConflictError(TypePropagationError):
    """Error when merge node receives objects with conflicting field types."""

    conflicting_field: str | None = None
    schemas: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with conflict details."""
        return {
            "node_id": self.node_id,
            "error_type": self.error_type,
            "message": self.message,
            "suggestion": self.suggestion,
            "conflicting_field": self.conflicting_field,
            "schemas": self.schemas,
        }


@dataclass
class InvalidTemplateInputError(TypePropagationError):
    """Error when template receives wrong input type."""

    template_kind: str | None = None
    required_type: str | None = None
    actual_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with template details."""
        return {
            "node_id": self.node_id,
            "error_type": self.error_type,
            "message": self.message,
            "suggestion": self.suggestion,
            "template_kind": self.template_kind,
            "required_type": self.required_type,
            "actual_type": self.actual_type,
        }


@dataclass
class DeprecatedMultiInputWarning(TypePropagationError):
    """Warning for v5 multi-input pattern (non-blocking)."""

    predecessor_count: int | None = None
    current_behavior: str | None = None
    migration_suggestion: str | None = None
    severity: str = "warning"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with deprecation details."""
        return {
            "node_id": self.node_id,
            "error_type": self.error_type,
            "message": self.message,
            "suggestion": self.suggestion,
            "severity": self.severity,
            "predecessor_count": self.predecessor_count,
            "current_behavior": self.current_behavior,
            "migration_suggestion": self.migration_suggestion,
        }
