"""Pydantic schemas for skill validation pipeline.

Structured output schemas for LLM nodes.
"""

from pydantic import BaseModel, Field


class RelevanceResult(BaseModel):
    """Output from assess_relevance_to_skill node."""

    relevant: bool = Field(description="Whether the content is relevant to the skill")
    confidence: str = Field(description="Confidence level: high, medium, low")
    reasoning: str = Field(description="Explanation of the relevance assessment")


class SafetyResult(BaseModel):
    """Output from assess_safety node."""

    safe: bool = Field(description="Whether the content is safe for agent consumption")
    concerns: list[str] = Field(
        default_factory=list,
        description="List of safety concerns found",
    )
    reasoning: str = Field(description="Explanation of the safety assessment")


class ValidationSummary(BaseModel):
    """Output from summarize_validation node."""

    summary: str = Field(description="Human-readable summary of the validation review")
