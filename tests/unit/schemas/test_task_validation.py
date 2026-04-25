"""Unit tests for task schema validation."""

import pytest
from pydantic import ValidationError

from analysi.schemas.task import TaskCreate, TaskUpdate


class TestTaskScopeValidation:
    """Test task scope validation to prevent invalid values."""

    def test_valid_task_scopes(self):
        """Test that valid task scopes are accepted."""
        valid_scopes = ["input", "processing", "output"]

        for scope in valid_scopes:
            task_data = {"name": "Test Task", "script": "print('test')", "scope": scope}
            task = TaskCreate(**task_data)
            assert task.scope == scope

    def test_invalid_task_scope_playground(self):
        """Test that 'playground' scope is rejected with a meaningful error."""
        task_data = {
            "name": "Test Task",
            "script": "print('test')",
            "scope": "playground",  # Invalid scope
        }

        with pytest.raises(ValidationError) as exc_info:
            TaskCreate(**task_data)

        errors = exc_info.value.errors()
        assert len(errors) == 1
        error = errors[0]
        assert error["loc"] == ("scope",)
        assert "Invalid task scope 'playground'" in error["msg"]
        assert "Must be one of: input, processing, output" in error["msg"]
        assert "'input' for data ingestion" in error["msg"]
        assert "'processing' for data transformation" in error["msg"]
        assert "'output' for tasks that produce final results" in error["msg"]

    def test_invalid_task_scope_custom(self):
        """Test that other invalid scopes are rejected."""
        invalid_scopes = ["test", "debug", "experimental", "custom"]

        for scope in invalid_scopes:
            task_data = {"name": "Test Task", "script": "print('test')", "scope": scope}

            with pytest.raises(ValidationError) as exc_info:
                TaskCreate(**task_data)

            errors = exc_info.value.errors()
            assert len(errors) == 1
            error = errors[0]
            assert f"Invalid task scope '{scope}'" in error["msg"]

    def test_none_scope_allowed(self):
        """Test that None scope is allowed (defaults to 'processing' in repository)."""
        task_data = {"name": "Test Task", "script": "print('test')", "scope": None}
        task = TaskCreate(**task_data)
        assert task.scope is None

    def test_update_with_invalid_scope(self):
        """Test that TaskUpdate also validates scope."""
        with pytest.raises(ValidationError) as exc_info:
            TaskUpdate(scope="playground")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        error = errors[0]
        assert "Invalid task scope 'playground'" in error["msg"]


class TestTaskModeValidation:
    """Test task mode validation."""

    def test_valid_task_modes(self):
        """Test that valid task modes are accepted."""
        valid_modes = ["ad_hoc", "saved"]

        for mode in valid_modes:
            task_data = {"name": "Test Task", "script": "print('test')", "mode": mode}
            task = TaskCreate(**task_data)
            assert task.mode == mode

    def test_invalid_task_mode(self):
        """Test that invalid modes are rejected with a meaningful error."""
        invalid_modes = ["temporary", "permanent", "test", "debug"]

        for mode in invalid_modes:
            task_data = {"name": "Test Task", "script": "print('test')", "mode": mode}

            with pytest.raises(ValidationError) as exc_info:
                TaskCreate(**task_data)

            errors = exc_info.value.errors()
            assert len(errors) == 1
            error = errors[0]
            assert f"Invalid task mode '{mode}'" in error["msg"]
            assert "Must be one of: ad_hoc, saved" in error["msg"]
            assert "'ad_hoc' for temporary one-time tasks" in error["msg"]
            assert "'saved' for persistent reusable tasks" in error["msg"]

    def test_default_mode_is_saved(self):
        """Test that default mode is 'saved'."""
        task_data = {
            "name": "Test Task",
            "script": "print('test')",
            # mode not specified
        }
        task = TaskCreate(**task_data)
        assert task.mode == "saved"

    def test_update_with_invalid_mode(self):
        """Test that TaskUpdate also validates mode."""
        with pytest.raises(ValidationError) as exc_info:
            TaskUpdate(mode="temporary")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        error = errors[0]
        assert "Invalid task mode 'temporary'" in error["msg"]


class TestValidationErrorMessages:
    """Test that validation error messages are helpful for users."""

    def test_error_message_helps_user_fix_input(self):
        """Test that error messages provide clear guidance on how to fix the input."""
        task_data = {
            "name": "Test Task",
            "script": "print('test')",
            "scope": "playground",
            "mode": "temporary",
        }

        with pytest.raises(ValidationError) as exc_info:
            TaskCreate(**task_data)

        errors = exc_info.value.errors()
        # Should have 2 validation errors
        assert len(errors) == 2

        # Check that both errors have helpful messages
        for error in errors:
            assert "Must be one of:" in error["msg"]
            assert "for" in error["msg"]  # Explains what each option is for

            # Verify field-specific guidance
            if error["loc"] == ("scope",):
                assert "data ingestion" in error["msg"]
                assert "data transformation" in error["msg"]
                assert "final results" in error["msg"]
            elif error["loc"] == ("mode",):
                assert "temporary one-time" in error["msg"]
                assert "persistent reusable" in error["msg"]

    def test_api_error_format(self):
        """Test that validation errors follow standard FastAPI error format."""
        task_data = {
            "name": "Test Task",
            "script": "print('test')",
            "scope": "playground",
        }

        try:
            TaskCreate(**task_data)
            raise AssertionError("Should have raised ValidationError")
        except ValidationError as e:
            # Convert to FastAPI error format
            errors = e.errors()

            # Verify error structure
            assert isinstance(errors, list)
            assert len(errors) == 1

            error = errors[0]
            assert "type" in error
            assert "loc" in error
            assert "msg" in error
            assert "input" in error

            # Error should be clear and actionable
            assert error["type"] == "value_error"
            assert error["loc"] == ("scope",)
            assert error["input"] == "playground"
            assert "Invalid task scope 'playground'" in error["msg"]
