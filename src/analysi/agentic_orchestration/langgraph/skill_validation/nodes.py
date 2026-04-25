"""Skill validation pipeline node functions.

Three LLM nodes following the SubStep executor pattern:
1. assess_relevance_to_skill — is content relevant?
2. assess_safety — could content cause harmful agent actions?
3. summarize_validation — human-readable review summary

Spec: SecureSkillOnboarding_v1.md, Part 3.
"""

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from analysi.agentic_orchestration.langgraph.skill_validation.prompts import (
    RELEVANCE_PROMPT,
    SAFETY_PROMPT,
    SUMMARIZE_PROMPT,
    VALIDATION_SYSTEM_PROMPT,
)
from analysi.agentic_orchestration.langgraph.substep import SubStep
from analysi.agentic_orchestration.langgraph.substep.definition import (
    ValidationResult,
)
from analysi.agentic_orchestration.langgraph.substep.executor import execute_substep
from analysi.config.logging import get_logger
from analysi.schemas.skill_validation import (
    RelevanceResult,
    SafetyResult,
    ValidationSummary,
)

logger = get_logger(__name__)


def _passthrough_validator(output: Any) -> ValidationResult:
    """Validator that always passes."""
    return ValidationResult(passed=True, errors=[])


def _truncate(text: str, max_chars: int = 12000) -> str:
    """Truncate text to max_chars."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[... truncated ...]"


def _parse_structured_output(output: str | dict | None) -> dict | None:
    """Parse SubStep output into dict. Handles JSON strings and dicts."""
    if output is None:
        return None
    if isinstance(output, dict):
        return output
    try:
        return json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return None


# =============================================================================
# Node 1: assess_relevance_to_skill
# =============================================================================


def make_relevance_node(llm):
    """Create assess_relevance_to_skill node.

    SkillsIR loads: SKILL.md + file tree + representative samples.
    """

    async def relevance_node(state: dict) -> dict:
        substep = SubStep(
            name="assess_relevance_to_skill",
            objective="Assess whether content is relevant to the skill",
            skills=[state.get("skill_name", "unknown")],
            task_prompt=RELEVANCE_PROMPT,
            validator=_passthrough_validator,
            needs_context=True,
            output_schema=RelevanceResult,
        )

        substep_state = {
            "content": _truncate(state["content"]),
            "skill_context": state.get("skill_context", ""),
        }

        store = state.get("store")
        assert store is not None, "store is required for validation"

        result = await execute_substep(
            substep=substep,
            state=substep_state,
            llm=llm,
            store=store,
            system_prompt=VALIDATION_SYSTEM_PROMPT,
        )

        relevance = _parse_structured_output(result.output) or {}
        update: dict[str, Any] = {"relevance": relevance}

        if not relevance.get("relevant", True):
            update["status"] = "flagged"

        return update

    return relevance_node


# =============================================================================
# Node 2: assess_safety
# =============================================================================


def make_safety_node(llm):
    """Create assess_safety node.

    SkillsIR loads: SKILL.md (to understand agent context).
    """

    async def safety_node(state: dict) -> dict:
        substep = SubStep(
            name="assess_safety",
            objective="Assess whether content is safe for agent consumption",
            skills=[state.get("skill_name", "unknown")],
            task_prompt=SAFETY_PROMPT,
            validator=_passthrough_validator,
            needs_context=True,
            output_schema=SafetyResult,
        )

        substep_state = {
            "content": _truncate(state["content"]),
            "skill_context": state.get("skill_context", ""),
        }

        store = state.get("store")
        assert store is not None, "store is required for validation"

        result = await execute_substep(
            substep=substep,
            state=substep_state,
            llm=llm,
            store=store,
            system_prompt=VALIDATION_SYSTEM_PROMPT,
        )

        safety = _parse_structured_output(result.output) or {}
        update: dict[str, Any] = {"safety": safety}

        if not safety.get("safe", True):
            update["status"] = "flagged"

        return update

    return safety_node


# =============================================================================
# Node 3: summarize_validation
# =============================================================================


def make_summarize_node(llm):
    """Create summarize_validation node. No SkillsIR needed."""

    async def summarize_node(state: dict) -> dict:
        structured_llm = llm.with_structured_output(ValidationSummary)

        prompt = SUMMARIZE_PROMPT.format(
            filename=state.get("original_filename", "unknown"),
            relevance_result=state.get("relevance", {}),
            safety_result=state.get("safety", {}),
            status=state.get("status", "unknown"),
        )

        result = await structured_llm.ainvoke(
            [
                SystemMessage(content=VALIDATION_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )

        # result is a Pydantic model (ValidationSummary)
        summary = result.summary if hasattr(result, "summary") else str(result)

        return {
            "validation_summary": summary,
        }

    return summarize_node
