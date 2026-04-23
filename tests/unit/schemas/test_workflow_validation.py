"""Unit tests for workflow type validation Pydantic schemas."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from analysi.schemas.workflow import NodeSchemas
from analysi.schemas.workflow_validation import (
    NodeTypeInfoResponse,
    TypeErrorResponse,
    WorkflowTypeApplyResponse,
    WorkflowTypeValidationRequest,
    WorkflowTypeValidationResponse,
)


class TestWorkflowTypeValidationRequest:
    """Test WorkflowTypeValidationRequest schema validation."""

    def test_workflow_type_validation_request_valid(self):
        """Test that WorkflowTypeValidationRequest accepts valid JSON Schema input."""
        # Given: Valid initial_input_schema with type, properties, and required fields
        valid_schema = {
            "type": "object",
            "properties": {
                "alert_id": {"type": "string"},
                "ip_address": {"type": "string"},
            },
            "required": ["alert_id", "ip_address"],
        }

        # When: Create WorkflowTypeValidationRequest instance
        request = WorkflowTypeValidationRequest(initial_input_schema=valid_schema)

        # Then: Model validates successfully, fields are correctly assigned
        assert request.initial_input_schema == valid_schema
        assert request.initial_input_schema["type"] == "object"
        assert "alert_id" in request.initial_input_schema["properties"]
        assert "ip_address" in request.initial_input_schema["properties"]

    def test_workflow_type_validation_request_invalid_schema(self):
        """Test that validation fails for malformed JSON Schema."""
        # Given: Invalid schema (not a dict)
        invalid_schema = "not a dictionary"

        # When/Then: Pydantic ValidationError is raised
        with pytest.raises(ValidationError) as exc_info:
            WorkflowTypeValidationRequest(initial_input_schema=invalid_schema)

        errors = exc_info.value.errors()
        assert len(errors) > 0


class TestNodeTypeInfoResponse:
    """Test NodeTypeInfoResponse schema validation."""

    def test_node_type_info_response_valid(self):
        """Test that NodeTypeInfoResponse can represent different node kinds."""
        # Given: Valid node_id, kind, inferred_input/output schemas
        test_cases = [
            # Task node
            {
                "node_id": "n-task-1",
                "kind": "task",
                "template_kind": None,
                "inferred_input": {
                    "type": "object",
                    "properties": {"ip": {"type": "string"}},
                },
                "inferred_output": {
                    "type": "object",
                    "properties": {"result": {"type": "string"}},
                },
            },
            # Transformation node
            {
                "node_id": "n-transform-1",
                "kind": "transformation",
                "template_kind": "static",
                "inferred_input": {"type": "object"},
                "inferred_output": {"type": "object"},
            },
            # Foreach node with list input
            {
                "node_id": "n-foreach-1",
                "kind": "foreach",
                "template_kind": None,
                "inferred_input": [{"type": "object"}],  # List for foreach expansion
                "inferred_output": {"type": "object"},
            },
        ]

        # When: Create NodeTypeInfoResponse for different node kinds
        for test_case in test_cases:
            response = NodeTypeInfoResponse(**test_case)

            # Then: All fields validate correctly, template_kind is optional
            assert response.node_id == test_case["node_id"]
            assert response.kind == test_case["kind"]
            assert response.template_kind == test_case.get("template_kind")
            assert response.inferred_input == test_case["inferred_input"]
            assert response.inferred_output == test_case["inferred_output"]


class TestTypeErrorResponse:
    """Test TypeErrorResponse schema validation."""

    def test_type_error_response_with_severity(self):
        """Test that TypeErrorResponse supports both errors and warnings."""
        # Given: Error with severity="error"
        error = TypeErrorResponse(
            node_id="n-bad-node",
            error_type="TypeMismatchError",
            message="Type mismatch detected",
            suggestion="Check input schema compatibility",
            severity="error",
            expected_schema={
                "type": "object",
                "properties": {"action_id": {"type": "string"}},
            },
            actual_schema={
                "type": "object",
                "properties": {"alert_id": {"type": "string"}},
            },
        )

        # Then: Error validates
        assert error.severity == "error"
        assert error.node_id == "n-bad-node"
        assert error.error_type == "TypeMismatchError"
        assert error.expected_schema is not None
        assert error.actual_schema is not None

        # Given: Warning with severity="warning"
        warning = TypeErrorResponse(
            node_id="n-deprecated",
            error_type="DeprecatedMultiInputWarning",
            message="Multi-input to task node is deprecated",
            suggestion="Add Merge or Collect node",
            severity="warning",
        )

        # Then: Warning validates, optional fields work correctly
        assert warning.severity == "warning"
        assert warning.node_id == "n-deprecated"
        assert warning.expected_schema is None
        assert warning.actual_schema is None


class TestWorkflowTypeValidationResponse:
    """Test WorkflowTypeValidationResponse schema validation."""

    def test_workflow_type_validation_response_valid_status(self):
        """Test that WorkflowTypeValidationResponse represents valid workflows."""
        # Given: status="valid", nodes list, workflow_output_schema, empty errors/warnings
        response_data = {
            "status": "valid",
            "nodes": [
                {
                    "node_id": "n1",
                    "kind": "transformation",
                    "template_kind": "static",
                    "inferred_input": {"type": "object"},
                    "inferred_output": {"type": "object"},
                }
            ],
            "workflow_output_schema": {
                "type": "object",
                "properties": {"result": {"type": "string"}},
            },
            "errors": [],
            "warnings": [],
        }

        # When: Create WorkflowTypeValidationResponse
        response = WorkflowTypeValidationResponse(**response_data)

        # Then: Response validates, all fields correctly assigned
        assert response.status == "valid"
        assert len(response.nodes) == 1
        assert response.workflow_output_schema is not None
        assert len(response.errors) == 0
        assert len(response.warnings) == 0

    def test_workflow_type_validation_response_invalid_status(self):
        """Test that response can represent invalid workflows with errors."""
        # Given: status="invalid", nodes list, errors list, no workflow_output_schema
        response_data = {
            "status": "invalid",
            "nodes": [
                {
                    "node_id": "n1",
                    "kind": "task",
                    "template_kind": None,
                    "inferred_input": {"type": "object"},
                    "inferred_output": {"type": "object"},
                }
            ],
            "workflow_output_schema": None,
            "errors": [
                {
                    "node_id": "n1",
                    "error_type": "TypeMismatchError",
                    "message": "Input type mismatch",
                    "suggestion": "Fix schema",
                    "severity": "error",
                }
            ],
            "warnings": [],
        }

        # When: Create WorkflowTypeValidationResponse
        response = WorkflowTypeValidationResponse(**response_data)

        # Then: Response validates, errors list populated correctly
        assert response.status == "invalid"
        assert len(response.errors) == 1
        assert response.errors[0].node_id == "n1"
        assert response.workflow_output_schema is None


class TestWorkflowTypeApplyResponse:
    """Test WorkflowTypeApplyResponse schema validation."""

    def test_workflow_type_apply_response_extends_validation(self):
        """Test that WorkflowTypeApplyResponse extends validation response with persistence metadata."""
        # Given: All validation response fields plus applied=True, nodes_updated=5, updated_at timestamp
        response_data = {
            "status": "valid",
            "nodes": [
                {
                    "node_id": f"n{i}",
                    "kind": "transformation",
                    "template_kind": "static",
                    "inferred_input": {"type": "object"},
                    "inferred_output": {"type": "object"},
                }
                for i in range(5)
            ],
            "workflow_output_schema": {"type": "object"},
            "errors": [],
            "warnings": [],
            "applied": True,
            "nodes_updated": 5,
            "updated_at": datetime.now(tz=UTC),
        }

        # When: Create WorkflowTypeApplyResponse
        response = WorkflowTypeApplyResponse(**response_data)

        # Then: All fields validate, inheritance from WorkflowTypeValidationResponse works
        assert response.status == "valid"
        assert len(response.nodes) == 5
        assert response.applied is True
        assert response.nodes_updated == 5
        assert isinstance(response.updated_at, datetime)


class TestNodeSchemas:
    """Test NodeSchemas model for JSONB validation."""

    def test_node_schemas_backward_compatible(self):
        """Test that NodeSchemas model supports both old and new fields."""
        # Given: Existing schemas with input/output
        old_schema = NodeSchemas(
            input={"type": "object"},
            output={"type": "object"},
        )

        # Then: Old fields validate
        assert old_schema.input == {"type": "object"}
        assert old_schema.output == {"type": "object"}
        assert old_schema.inferred_input is None
        assert old_schema.inferred_output is None
        assert old_schema.type_checked is False

        # Given: New schemas with inferred_input/inferred_output
        new_schema = NodeSchemas(
            input={"type": "object"},
            output={"type": "object"},
            inferred_input={"type": "object", "properties": {"ip": {"type": "string"}}},
            inferred_output={
                "type": "object",
                "properties": {"result": {"type": "number"}},
            },
            type_checked=True,
            validated_at=datetime.now(tz=UTC),
        )

        # Then: New fields validate
        assert new_schema.inferred_input is not None
        assert new_schema.inferred_output is not None
        assert new_schema.type_checked is True
        assert isinstance(new_schema.validated_at, datetime)

        # Given: Mixed schema (some old, some new)
        mixed_schema = NodeSchemas(
            inferred_input={"type": "object"},
            inferred_output={"type": "object"},
            type_checked=True,
        )

        # Then: All validate, extra fields are allowed, type_checked defaults to False if not provided
        assert mixed_schema.input is None
        assert mixed_schema.output is None
        assert mixed_schema.inferred_input is not None
        assert mixed_schema.type_checked is True
