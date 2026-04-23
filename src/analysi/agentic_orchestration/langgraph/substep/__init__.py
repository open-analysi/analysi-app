"""SubStep pattern for Kea phases.

The SubStep is the reusable execution unit that combines SkillsIR with task
execution and validation. Each Kea phase is a chain of SubSteps.

Pattern: Retrieve → Execute → Validate → Loop
"""

from analysi.agentic_orchestration.langgraph.substep.definition import (
    SubStep,
    SubStepResult,
    ValidationResult,
)
from analysi.agentic_orchestration.langgraph.substep.executor import (
    MaxRetriesExceededError,
    execute_substep,
)
from analysi.agentic_orchestration.langgraph.substep.validation import (
    validate_has_critical_steps,
    validate_json_output,
    validate_no_wikilinks,
    validate_non_empty,
    validate_pydantic_model,
)

__all__ = [
    "MaxRetriesExceededError",
    # Dataclasses
    "SubStep",
    "SubStepResult",
    "ValidationResult",
    # Executor
    "execute_substep",
    "validate_has_critical_steps",
    # Validators
    "validate_json_output",
    "validate_no_wikilinks",
    "validate_non_empty",
    "validate_pydantic_model",
]
