"""SubStep executor with LangGraph implementation."""

import json
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from analysi.agentic_orchestration.langgraph.skills.context import SkillContext
from analysi.agentic_orchestration.langgraph.skills.retrieval import retrieve
from analysi.agentic_orchestration.langgraph.skills.store import ResourceStore
from analysi.agentic_orchestration.langgraph.substep.definition import (
    SubStep,
    SubStepResult,
    ValidationResult,
)


async def execute_substep(
    substep: SubStep,
    state: dict[str, Any],
    store: ResourceStore,
    llm: Any,
    system_prompt: str | None = None,
) -> SubStepResult:
    """Execute a substep with the retrieve → execute → validate → loop pattern.

    This is the core execution function for SubSteps. It:
    1. Retrieves context via SkillsIR (if needs_context=True)
    2. Executes the task by calling the LLM with formatted prompt
    3. Validates the output using the substep's validator
    4. Retries with expanded context or error feedback if validation fails

    Args:
        substep: The SubStep to execute.
        state: Current state dict (passed to task_prompt formatting).
        store: ResourceStore for SkillsIR retrieval.
        llm: LangChain LLM instance for task execution.

    Returns:
        SubStepResult with output, context, attempts, and validation history.

    Raises:
        MaxRetriesExceededError: If max_retries exceeded without passing validation.

    Example:
        >>> substep = SubStep(
        ...     name="analyze_gaps",
        ...     objective="identify missing investigation steps",
        ...     skills=["runbooks-manager"],
        ...     task_prompt="Given {context}, analyze gaps for {alert}",
        ...     validator=validate_json_output,
        ... )
        >>> result = await execute_substep(substep, {"alert": alert}, store, llm)
        >>> result.output  # The LLM's analysis
    """
    validation_history: list[ValidationResult] = []
    context: SkillContext | None = None
    output: str | None = None
    attempt = 0
    last_errors: list[str] = []

    # Retrieve initial context if needed
    if substep.needs_context and substep.skills:
        context = await retrieve(
            store=store,
            initial_skills=substep.skills,
            task_input=state,
            objective=substep.objective,
            llm=llm,
        )

    while attempt < substep.max_retries:
        attempt += 1

        # Format prompt with state and context
        format_vars = dict(state)
        if context:
            format_vars["context"] = context.for_prompt()

        prompt = substep.task_prompt.format(**format_vars)

        # Add error feedback if this is a retry
        if last_errors:
            prompt += "\n\nPrevious attempt failed with errors:\n" + "\n".join(
                f"- {e}" for e in last_errors
            )

        # Build messages list with optional system prompt
        messages: list[BaseMessage] = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        # Execute LLM call - use structured output if schema is provided
        if substep.output_schema:
            # Use with_structured_output for type-safe JSON responses
            structured_llm = llm.with_structured_output(substep.output_schema)
            response = await structured_llm.ainvoke(messages)
            # Response is a Pydantic model - convert to JSON string for validator
            if isinstance(response, BaseModel):
                output = response.model_dump_json()
            else:
                output = json.dumps(response) if response else ""
        else:
            # Regular text output
            response = await llm.ainvoke(messages)
            # Extract content from AIMessage if needed (LangChain chat models return AIMessage)
            output = response.content if hasattr(response, "content") else response

        # Validate output
        validation = substep.validator(output)
        validation_history.append(validation)

        if validation.passed:
            return SubStepResult(
                output=output,
                context=context,
                attempts=attempt,
                validation_history=validation_history,
            )

        # Handle needs_more_context - re-retrieve with hint
        if validation.needs_more_context and validation.context_hint:
            # Expand the objective with the hint for re-retrieval
            expanded_objective = f"{substep.objective}. Also: {validation.context_hint}"
            context = await retrieve(
                store=store,
                initial_skills=substep.skills,
                task_input=state,
                objective=expanded_objective,
                llm=llm,
            )

        # Store errors for feedback on next attempt
        last_errors = validation.errors

    # Max retries exceeded
    raise MaxRetriesExceededError(
        substep_name=substep.name,
        attempts=attempt,
        last_errors=last_errors,
    )


class MaxRetriesExceededError(Exception):
    """Raised when SubStep execution exceeds max_retries without passing."""

    def __init__(self, substep_name: str, attempts: int, last_errors: list[str]):
        self.substep_name = substep_name
        self.attempts = attempts
        self.last_errors = last_errors
        super().__init__(
            f"SubStep '{substep_name}' failed after {attempts} attempts. "
            f"Last errors: {last_errors}"
        )
