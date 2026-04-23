"""Runbook Matching SubStep definitions.

Match path (deterministic) and composition path (LLM) SubSteps.
"""

from typing import Literal

from pydantic import BaseModel, Field

from analysi.agentic_orchestration.langgraph.kea.phase1.validators import (
    validate_extraction,
    validate_gap_analysis,
    validate_matched_runbook,
    validate_matches,
    validate_strategy,
)
from analysi.agentic_orchestration.langgraph.substep import SubStep
from analysi.agentic_orchestration.langgraph.substep.definition import (
    ValidationResult,
)

# =============================================================================
# Pydantic Models for Structured LLM Output
# =============================================================================


class Gap(BaseModel):
    """A gap identified between the top match and alert requirements."""

    category: str = Field(
        description="Category of the gap (e.g., 'attack_vector', 'indicator')"
    )
    description: str = Field(description="What's missing or not covered")
    severity: Literal["high", "medium", "low"] = Field(description="Impact of this gap")


class GapAnalysisOutput(BaseModel):
    """Structured output for gap analysis step."""

    gaps: list[Gap] = Field(description="List of gaps identified")
    coverage_assessment: str = Field(
        description="Assessment of what the top match covers"
    )


class StrategySource(BaseModel):
    """A source runbook to use in composition."""

    runbook: str = Field(description="Filename of the source runbook")
    sections: list[str] = Field(description="Sections to extract from this runbook")
    reason: str = Field(description="Why this source is relevant")


class StrategyOutput(BaseModel):
    """Structured output for strategy selection step."""

    strategy: Literal[
        "same_attack_family_adaptation",
        "multi_source_blending",
        "category_based_assembly",
        "minimal_scaffold",
    ] = Field(description="Composition strategy to use")
    sources: list[StrategySource] = Field(description="Source runbooks to use")
    template: str | None = Field(default=None, description="Optional template name")


class Extraction(BaseModel):
    """An extracted section with provenance."""

    content: str = Field(description="The extracted content")
    source: str = Field(description="Source runbook filename")
    section: str = Field(description="Section name within the runbook")


class ExtractionOutput(BaseModel):
    """Structured output for section extraction step."""

    extractions: list[Extraction] = Field(
        description="Extracted sections with provenance"
    )
    remaining_gaps: list[str] = Field(
        description="Gaps that couldn't be filled from existing runbooks"
    )


# =============================================================================
# Match Path SubSteps (Deterministic - no LLM)
# =============================================================================


def create_load_and_score_substep() -> SubStep:
    """Create SubStep for loading index and scoring matches.

    This is deterministic (needs_context=False) - uses RunbookMatcher.
    """
    return SubStep(
        name="load_and_score",
        objective="Load runbook index and calculate match scores for alert",
        skills=[],  # Deterministic, no skill context needed
        task_prompt="",  # No LLM task, uses matcher directly
        validator=validate_matches,
        needs_context=False,
    )


def create_fetch_runbook_substep() -> SubStep:
    """Create SubStep for fetching and expanding runbook.

    This is deterministic (needs_context=False) - just file read + WikiLink expansion.
    """
    return SubStep(
        name="fetch_runbook",
        objective="Fetch matched runbook and expand WikiLinks",
        skills=[],  # Deterministic, no skill context needed
        task_prompt="",  # No LLM task, uses file read directly
        validator=validate_matched_runbook,
        needs_context=False,
    )


# =============================================================================
# Composition Path SubSteps (LLM Required)
# =============================================================================


def create_analyze_gaps_substep() -> SubStep:
    """Create SubStep for gap analysis.

    LLM analyzes what's missing from top match for the given alert.
    Uses runbooks-manager for runbook context and cybersecurity-analyst
    for investigation patterns (especially useful for LOW/VERY_LOW confidence).
    """
    return SubStep(
        name="analyze_gaps",
        objective="Identify gaps between top runbook match and alert requirements",
        skills=["runbooks-manager", "cybersecurity-analyst"],
        task_prompt="""Analyze the gap between the matched runbook and the alert.

Alert: {alert}
Top Match: {top_match}
Match Score: {score}

Identify what's missing from the matched runbook to fully investigate this alert.
Consider:
- Attack vectors not covered
- Investigation steps not present
- Specific indicators not addressed

Return a gap analysis with identified gaps and a coverage assessment.""",
        validator=validate_gap_analysis,
        needs_context=True,
        output_schema=GapAnalysisOutput,
    )


def create_select_strategy_substep() -> SubStep:
    """Create SubStep for strategy selection.

    LLM picks composition approach based on gaps and available runbooks.
    Uses cybersecurity-analyst for investigation patterns when building
    minimal scaffolds (LOW/VERY_LOW confidence).
    """
    return SubStep(
        name="select_strategy",
        objective="Select composition strategy based on gaps and available runbooks",
        skills=["runbooks-manager", "cybersecurity-analyst"],
        task_prompt="""Select the best strategy to compose a runbook for this alert.

Alert: {alert}
Gaps identified: {gaps}
Available runbooks: {available_runbooks}

Strategies:
- same_attack_family_adaptation: Adapt a similar attack's runbook
- multi_source_blending: Combine sections from multiple runbooks
- category_based_assembly: Assemble from category templates
- minimal_scaffold: Create minimal structure, generate most content

Select the most appropriate strategy and identify source runbooks to use.""",
        validator=validate_strategy,
        needs_context=True,
        output_schema=StrategyOutput,
    )


def create_extract_sections_substep() -> SubStep:
    """Create SubStep for section extraction.

    LLM extracts relevant sections from source runbooks with provenance.
    Uses Pydantic structured output for type-safe responses.
    """
    return SubStep(
        name="extract_sections",
        objective="Extract relevant sections from source runbooks with provenance",
        skills=["runbooks-manager"],
        task_prompt="""Extract relevant sections from the source runbooks.

Strategy: {strategy}
Sources to extract from: {sources}
Gaps to fill: {gaps}

For each extraction, maintain provenance (source file and section name).
Identify any remaining gaps that couldn't be filled from existing runbooks.""",
        validator=validate_extraction,
        needs_context=True,
        output_schema=ExtractionOutput,
    )


def _passthrough_validator(output: str) -> ValidationResult:
    """Pass-through validator that always succeeds.

    Used for compose_runbook to defer validation to graph-level routing,
    allowing the fix_runbook loop to handle validation failures.
    """
    return ValidationResult(passed=True, errors=[])


def create_compose_runbook_substep() -> SubStep:
    """Create SubStep for runbook composition.

    LLM blends extracted sections and generates novel content for gaps.
    Uses both runbooks-manager and cybersecurity-analyst skills.

    Note: Uses pass-through validator to defer validation to graph-level
    routing, which enables the fix_runbook loop for semantic fixes.
    """
    return SubStep(
        name="compose_runbook",
        objective="Compose final runbook by blending extractions and generating novel content",
        skills=["runbooks-manager", "cybersecurity-analyst"],
        task_prompt="""Compose a complete investigation runbook for the alert.

Alert: {alert}
Extracted sections: {extractions}
Remaining gaps to address: {remaining_gaps}

Requirements:
- Start with H1 heading (# Title)
- Mark critical steps with ★ (steps that MUST be performed)
- No @include directives or WikiLinks - all content must be inline
- NO YAML frontmatter (this is for immediate use, not storage)
- Follow standard runbook structure with proper heading hierarchy
- Include a Steps section with numbered investigation steps

Generate a complete, self-contained runbook that blends the extracted content
and generates novel content to fill any remaining gaps.""",
        validator=_passthrough_validator,  # Defer to graph-level validation
        needs_context=True,
    )


def create_fix_runbook_substep() -> SubStep:
    """Create SubStep for fixing validation errors.

    LLM fixes issues identified by validation (conditional - only if needed).

    Note: Uses pass-through validator to defer validation to graph-level
    routing, which controls the fix_runbook retry loop.
    """
    return SubStep(
        name="fix_runbook",
        objective="Fix validation errors in composed runbook",
        skills=["runbooks-manager"],
        task_prompt="""Fix the following validation errors in the runbook.

Current runbook:
{runbook}

Validation errors:
{errors}

Fix all listed errors while preserving the runbook's content and structure.
Ensure:
- All critical steps have ★ markers
- No unresolved @include directives or WikiLinks
- NO YAML frontmatter (this is for immediate use, not storage)
- Valid markdown heading hierarchy starting with H1""",
        validator=_passthrough_validator,  # Defer to graph-level validation
        needs_context=True,
    )
