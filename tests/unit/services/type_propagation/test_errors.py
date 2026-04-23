"""
Unit tests for Type Propagation Error classes.

Tests error creation and JSON serialization for all error types.
Following TDD - these tests should fail until implementation is complete.
"""

import pytest

from analysi.services.type_propagation.errors import (
    DeprecatedMultiInputWarning,
    InvalidTemplateInputError,
    MergeConflictError,
    TypeMismatchError,
    TypePropagationError,
)


@pytest.mark.unit
class TestTypePropagationError:
    """Test TypePropagationError base class."""

    def test_type_propagation_error_to_dict_not_implemented(self):
        """
        Test base TypePropagationError.to_dict() raises NotImplementedError.

        Negative case: Base class cannot be used directly.
        """
        # Create base TypePropagationError instance
        error = TypePropagationError(
            node_id="test_node",
            error_type="test_error",
            message="Test message",
            suggestion="Test suggestion",
        )

        # Call to_dict()
        # Verify raises NotImplementedError (base class must be subclassed)
        with pytest.raises(NotImplementedError):
            error.to_dict()


@pytest.mark.unit
class TestTypeMismatchError:
    """Test TypeMismatchError - predecessor output doesn't match successor input."""

    def test_type_mismatch_error_creation(self):
        """
        Test TypeMismatchError can be created with schema details.

        Positive case: Error object created with schema details.
        """
        # Create TypeMismatchError with expected/actual schemas
        error = TypeMismatchError(
            node_id="task_b",
            error_type="type_mismatch",
            message="Expected field 'name: string', got 'ip: string'",
            suggestion="Add transformation to convert ip to name",
            expected_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
            },
            actual_schema={"type": "object", "properties": {"ip": {"type": "string"}}},
        )

        # Verify all fields set correctly
        assert error.node_id == "task_b"
        assert error.error_type == "type_mismatch"
        assert "name" in error.message
        assert error.expected_schema is not None
        assert error.actual_schema is not None
        assert error.expected_schema["properties"]["name"]["type"] == "string"
        assert error.actual_schema["properties"]["ip"]["type"] == "string"

    def test_type_mismatch_error_to_dict(self):
        """
        Test TypeMismatchError.to_dict() serializes to JSON-compatible dict.

        Positive case: Error serializes to JSON-compatible dict.
        """
        # Create TypeMismatchError
        error = TypeMismatchError(
            node_id="task_b",
            error_type="type_mismatch",
            message="Expected field 'name: string', got 'ip: string'",
            suggestion="Add transformation",
            expected_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
            },
            actual_schema={"type": "object", "properties": {"ip": {"type": "string"}}},
        )

        # Call to_dict()
        result = error.to_dict()

        # Verify returns dict with all required fields
        assert isinstance(result, dict)
        assert result["node_id"] == "task_b"
        assert result["error_type"] == "type_mismatch"
        assert "message" in result
        assert "expected_schema" in result
        assert "actual_schema" in result
        assert result["expected_schema"]["properties"]["name"]["type"] == "string"


@pytest.mark.unit
class TestMergeConflictError:
    """Test MergeConflictError - merge node receives conflicting field types."""

    def test_merge_conflict_error_creation(self):
        """
        Test MergeConflictError can be created with conflict details.

        Positive case: Error object created with conflict details.
        """
        # Create MergeConflictError with conflicting field and schemas
        error = MergeConflictError(
            node_id="merge_node",
            error_type="merge_conflict",
            message="Field 'status' has conflicting types: number vs string",
            suggestion="Ensure all merge inputs have compatible types for shared fields",
            conflicting_field="status",
            schemas=[
                {"type": "object", "properties": {"status": {"type": "number"}}},
                {"type": "object", "properties": {"status": {"type": "string"}}},
            ],
        )

        # Verify all fields set correctly
        assert error.node_id == "merge_node"
        assert error.error_type == "merge_conflict"
        assert error.conflicting_field == "status"
        assert len(error.schemas) == 2
        assert error.schemas[0]["properties"]["status"]["type"] == "number"
        assert error.schemas[1]["properties"]["status"]["type"] == "string"

    def test_merge_conflict_error_to_dict(self):
        """
        Test MergeConflictError.to_dict() serializes conflict details.

        Positive case: Conflict details serialized correctly.
        """
        # Create MergeConflictError
        error = MergeConflictError(
            node_id="merge_node",
            error_type="merge_conflict",
            message="Field 'status' has conflicting types",
            suggestion="Fix conflicting types",
            conflicting_field="status",
            schemas=[
                {"type": "object", "properties": {"status": {"type": "number"}}},
                {"type": "object", "properties": {"status": {"type": "string"}}},
            ],
        )

        # Call to_dict()
        result = error.to_dict()

        # Verify returns dict with conflicting_field and schemas list
        assert isinstance(result, dict)
        assert result["node_id"] == "merge_node"
        assert result["error_type"] == "merge_conflict"
        assert result["conflicting_field"] == "status"
        assert "schemas" in result
        assert len(result["schemas"]) == 2


@pytest.mark.unit
class TestInvalidTemplateInputError:
    """Test InvalidTemplateInputError - template receives wrong input type."""

    def test_invalid_template_input_error_creation(self):
        """
        Test InvalidTemplateInputError can be created with template details.

        Positive case: Error object created with template details.
        """
        # Create InvalidTemplateInputError with template kind and type details
        error = InvalidTemplateInputError(
            node_id="merge_1",
            error_type="invalid_template_input",
            message="Merge template received non-object input",
            suggestion="Use Collect node instead or fix predecessor output",
            template_kind="merge",
            required_type="object",
            actual_type="number",
        )

        # Verify fields set correctly
        assert error.node_id == "merge_1"
        assert error.template_kind == "merge"
        assert error.required_type == "object"
        assert error.actual_type == "number"

    def test_invalid_template_input_error_to_dict(self):
        """
        Test InvalidTemplateInputError.to_dict() serializes template details.

        Positive case: Template error serialized correctly.
        """
        # Create InvalidTemplateInputError
        error = InvalidTemplateInputError(
            node_id="merge_1",
            error_type="invalid_template_input",
            message="Merge template received non-object input",
            suggestion="Fix predecessor output",
            template_kind="merge",
            required_type="object",
            actual_type="number",
        )

        # Call to_dict()
        result = error.to_dict()

        # Verify returns dict with template_kind, required_type, actual_type
        assert isinstance(result, dict)
        assert result["node_id"] == "merge_1"
        assert result["error_type"] == "invalid_template_input"
        assert result["template_kind"] == "merge"
        assert result["required_type"] == "object"
        assert result["actual_type"] == "number"


@pytest.mark.unit
class TestDeprecatedMultiInputWarning:
    """Test DeprecatedMultiInputWarning - v5 multi-input pattern warning."""

    def test_deprecated_multi_input_warning_creation(self):
        """
        Test DeprecatedMultiInputWarning can be created with deprecation details.

        Positive case: Warning object created with deprecation details.
        """
        # Create DeprecatedMultiInputWarning
        warning = DeprecatedMultiInputWarning(
            node_id="task_1",
            error_type="deprecated_multi_input",
            message="Node has 2 predecessors using deprecated v5 automatic aggregation",
            suggestion="Replace with explicit Merge or Collect node",
            predecessor_count=2,
            current_behavior="Node receives array: [{node_id, result}, ...]",
            migration_suggestion="Insert Merge node before task_1",
        )

        # Verify severity is "warning"
        assert warning.severity == "warning"
        # Verify predecessor_count and suggestions set
        assert warning.predecessor_count == 2
        assert warning.current_behavior is not None
        assert "Merge" in warning.migration_suggestion

    def test_deprecated_multi_input_warning_to_dict(self):
        """
        Test DeprecatedMultiInputWarning.to_dict() serializes deprecation info.

        Positive case: Warning serialized with all deprecation info.
        """
        # Create DeprecatedMultiInputWarning
        warning = DeprecatedMultiInputWarning(
            node_id="task_1",
            error_type="deprecated_multi_input",
            message="Deprecated v5 pattern",
            suggestion="Use Merge or Collect",
            predecessor_count=2,
            current_behavior="Array aggregation",
            migration_suggestion="Insert Merge node",
        )

        # Call to_dict()
        result = warning.to_dict()

        # Verify returns dict with severity="warning", predecessor_count, migration_suggestion
        assert isinstance(result, dict)
        assert result["node_id"] == "task_1"
        assert result["severity"] == "warning"
        assert result["predecessor_count"] == 2
        assert "migration_suggestion" in result
        assert "current_behavior" in result
