"""Unit tests for base Pydantic schemas."""

import pytest
from pydantic import ValidationError

from analysi.schemas.base import (
    ErrorResponse,
)


class TestErrorResponse:
    """Test ErrorResponse schema."""

    def test_error_response_required_fields(self):
        """Test ErrorResponse with required fields only."""
        response = ErrorResponse(
            error="Something went wrong",
            error_code="GENERIC_ERROR",
            execution_time=0.05,
        )
        assert response.error == "Something went wrong"
        assert response.error_code == "GENERIC_ERROR"
        assert response.context is None
        assert response.execution_time == 0.05

    def test_error_response_with_context(self):
        """Test ErrorResponse with context."""
        context = {"tenant_id": "test-tenant", "endpoint": "/v1/test"}
        response = ErrorResponse(
            error="Validation failed",
            error_code="VALIDATION_ERROR",
            context=context,
            execution_time=0.02,
        )
        assert response.context == context

    def test_error_response_missing_required_fields(self):
        """Test ErrorResponse validation with missing fields."""
        with pytest.raises(ValidationError):
            ErrorResponse(error="Missing error code")

    def test_error_response_serialization(self):
        """Test ErrorResponse JSON serialization."""
        response = ErrorResponse(
            error="Not found", error_code="NOT_FOUND", execution_time=0.01
        )
        json_data = response.model_dump()

        expected = {
            "error": "Not found",
            "error_code": "NOT_FOUND",
            "context": None,
            "execution_time": 0.01,
        }
        assert json_data == expected
