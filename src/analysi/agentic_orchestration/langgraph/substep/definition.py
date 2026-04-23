"""SubStep and ValidationResult dataclasses."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from analysi.agentic_orchestration.langgraph.skills.context import SkillContext


@dataclass
class ValidationResult:
    """Result of validating SubStep output.

    Attributes:
        passed: Whether validation passed.
        errors: List of error messages if validation failed.
        needs_more_context: If True, retry with expanded context.
        context_hint: More specific objective for context retrieval on retry.
    """

    passed: bool
    errors: list[str] = field(default_factory=list)
    needs_more_context: bool = False
    context_hint: str | None = None


# Type alias for validator functions
Validator = Callable[[Any], ValidationResult]


@dataclass
class SubStep:
    """A single step in a Kea phase.

    SubSteps can be either LLM-based (needs_context=True) or deterministic
    (needs_context=False). LLM-based SubSteps use SkillsIR to retrieve context
    before executing the task.

    Attributes:
        name: Unique identifier for this substep.
        objective: What we're trying to accomplish (for SkillsIR retrieval).
        skills: Which skills to query for context.
        task_prompt: Template for the LLM task (uses {context} and state vars).
        validator: Function to validate output.
        max_retries: Maximum number of retry attempts on validation failure.
        needs_context: If False, skip SkillsIR retrieval (deterministic step).
        output_schema: Optional Pydantic model for structured LLM output.
            When provided, uses `llm.with_structured_output()` for type-safe
            JSON responses instead of free-form text.
    """

    name: str
    objective: str
    skills: list[str]
    task_prompt: str
    validator: Validator
    max_retries: int = 3
    needs_context: bool = True
    output_schema: type[BaseModel] | None = None


@dataclass
class SubStepResult:
    """Result of executing a SubStep.

    Attributes:
        output: The output from the SubStep execution.
        context: The SkillContext used (None for deterministic steps).
        attempts: Number of attempts made.
        validation_history: History of validation results for observability.
    """

    output: Any
    context: SkillContext | None
    attempts: int
    validation_history: list[ValidationResult] = field(default_factory=list)
