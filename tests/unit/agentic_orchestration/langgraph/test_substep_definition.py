"""Tests for SubStep, ValidationResult, and SubStepResult dataclasses."""

import pytest

from analysi.agentic_orchestration.langgraph.substep.definition import (
    SubStep,
    SubStepResult,
    ValidationResult,
)


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_validation_result_passed(self):
        """ValidationResult with passed=True has empty errors by default."""
        result = ValidationResult(passed=True)

        assert result.passed is True
        assert result.errors == []
        assert result.needs_more_context is False
        assert result.context_hint is None

    def test_validation_result_failed(self):
        """ValidationResult with passed=False can have errors."""
        result = ValidationResult(
            passed=False,
            errors=["Missing required field", "Invalid format"],
        )

        assert result.passed is False
        assert len(result.errors) == 2
        assert "Missing required field" in result.errors

    def test_validation_result_needs_context(self):
        """ValidationResult can indicate more context needed with hint."""
        result = ValidationResult(
            passed=False,
            errors=["Insufficient context to compose"],
            needs_more_context=True,
            context_hint="load composition guide for hybrid attacks",
        )

        assert result.passed is False
        assert result.needs_more_context is True
        assert result.context_hint == "load composition guide for hybrid attacks"


class TestSubStep:
    """Tests for SubStep dataclass."""

    def test_substep_defaults(self):
        """SubStep has correct default values."""
        substep = SubStep(
            name="test_step",
            objective="test objective",
            skills=["skill-a"],
            task_prompt="Do something with {context}",
            validator=lambda x: ValidationResult(passed=True),
        )

        assert substep.max_retries == 3
        assert substep.needs_context is True

    def test_substep_deterministic(self):
        """SubStep with needs_context=False is valid for deterministic steps."""
        substep = SubStep(
            name="calculate_scores",
            objective="",  # Not used for deterministic
            skills=[],
            task_prompt="",  # Not used for deterministic
            validator=lambda x: ValidationResult(passed=True),
            needs_context=False,
        )

        assert substep.needs_context is False
        assert substep.skills == []

    def test_substep_custom_retries(self):
        """SubStep can have custom max_retries."""
        substep = SubStep(
            name="critical_step",
            objective="must succeed",
            skills=["skill-a"],
            task_prompt="Do it",
            validator=lambda x: ValidationResult(passed=True),
            max_retries=5,
        )

        assert substep.max_retries == 5

    def test_substep_requires_name(self):
        """SubStep requires name field."""
        with pytest.raises(TypeError):
            SubStep(
                objective="test",
                skills=[],
                task_prompt="",
                validator=lambda x: ValidationResult(passed=True),
            )

    def test_substep_requires_validator(self):
        """SubStep requires validator field."""
        with pytest.raises(TypeError):
            SubStep(
                name="test",
                objective="test",
                skills=[],
                task_prompt="",
            )


class TestSubStepResult:
    """Tests for SubStepResult dataclass."""

    def test_substep_result_tracks_attempts(self):
        """SubStepResult tracks number of attempts."""
        result = SubStepResult(
            output="some output",
            context=None,
            attempts=3,
        )

        assert result.attempts == 3

    def test_substep_result_validation_history(self):
        """SubStepResult tracks validation history."""
        history = [
            ValidationResult(passed=False, errors=["First failure"]),
            ValidationResult(passed=False, errors=["Second failure"]),
            ValidationResult(passed=True),
        ]

        result = SubStepResult(
            output="final output",
            context=None,
            attempts=3,
            validation_history=history,
        )

        assert len(result.validation_history) == 3
        assert result.validation_history[0].passed is False
        assert result.validation_history[2].passed is True

    def test_substep_result_default_history(self):
        """SubStepResult has empty validation_history by default."""
        result = SubStepResult(
            output="output",
            context=None,
            attempts=1,
        )

        assert result.validation_history == []
