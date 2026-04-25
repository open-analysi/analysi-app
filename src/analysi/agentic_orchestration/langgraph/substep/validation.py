"""Common validators for SubStep outputs."""

import json
import re

from pydantic import BaseModel, ValidationError

from analysi.agentic_orchestration.langgraph.substep.definition import (
    ValidationResult,
    Validator,
)

# WikiLink pattern from skills/store.py
WIKILINK_PATTERN = re.compile(r"!\[\[([^\]]+\.md)\]\]")


def validate_json_output(output: str) -> ValidationResult:
    """Validate that output is valid JSON.

    Args:
        output: String that should be valid JSON.

    Returns:
        ValidationResult with passed=True if valid JSON, else errors.
    """
    if not output or not output.strip():
        return ValidationResult(
            passed=False,
            errors=["Output is empty, expected valid JSON"],
        )

    try:
        json.loads(output)
        return ValidationResult(passed=True)
    except json.JSONDecodeError as e:
        return ValidationResult(
            passed=False,
            errors=[f"Invalid JSON: {e}"],
        )


def validate_pydantic_model(model: type[BaseModel]) -> Validator:
    """Factory: create validator for specific Pydantic model.

    Args:
        model: Pydantic model class to validate against.

    Returns:
        Validator function that checks output matches the model.

    Example:
        >>> from pydantic import BaseModel
        >>> class Score(BaseModel):
        ...     value: int
        >>> validator = validate_pydantic_model(Score)
        >>> result = validator('{"value": 42}')
        >>> result.passed
        True
    """

    def validator(output: str) -> ValidationResult:
        # First validate JSON
        try:
            data = json.loads(output)
        except json.JSONDecodeError as e:
            return ValidationResult(
                passed=False,
                errors=[f"Invalid JSON: {e}"],
            )

        # Then validate against Pydantic model
        try:
            model.model_validate(data)
            return ValidationResult(passed=True)
        except ValidationError as e:
            errors = [str(err) for err in e.errors()]
            return ValidationResult(
                passed=False,
                errors=errors,
            )

    return validator


def validate_non_empty(output: str) -> ValidationResult:
    """Validate that output is non-empty.

    Args:
        output: String to check.

    Returns:
        ValidationResult with passed=True if non-empty, else errors.
    """
    if not output or not output.strip():
        return ValidationResult(
            passed=False,
            errors=["Output is empty or whitespace-only"],
        )

    return ValidationResult(passed=True)


def validate_no_wikilinks(output: str) -> ValidationResult:
    """Validate that no unexpanded WikiLinks remain in output.

    WikiLinks use the syntax ![[path/to/file.md]]. If any remain in the
    output, they were not properly expanded.

    Args:
        output: Content to check for WikiLinks.

    Returns:
        ValidationResult with passed=True if no WikiLinks found.
    """
    wikilinks = WIKILINK_PATTERN.findall(output)

    if wikilinks:
        return ValidationResult(
            passed=False,
            errors=[f"Unexpanded WikiLinks found: {', '.join(wikilinks)}"],
        )

    return ValidationResult(passed=True)


def validate_has_critical_steps(output: str) -> ValidationResult:
    """Validate that runbook has critical steps marked with ★.

    Runbooks must have at least one step marked as critical using the ★
    marker. This ensures minimum viable investigation steps are identified.

    Args:
        output: Runbook content to check.

    Returns:
        ValidationResult with passed=True if ★ markers found.
    """
    # Count critical step markers
    critical_count = output.count("★")

    if critical_count == 0:
        return ValidationResult(
            passed=False,
            errors=[
                "No critical steps found. Runbooks must have at least one step marked with ★"
            ],
        )

    return ValidationResult(passed=True)
