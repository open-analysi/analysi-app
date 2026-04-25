"""Shared fixtures for skill validation pipeline tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.agentic_orchestration.langgraph.skills.context import RetrievalDecision
from analysi.schemas.skill_validation import (
    RelevanceResult,
    SafetyResult,
    ValidationSummary,
)


class _MockAIMessage:
    def __init__(self, content: str):
        self.content = content


def _create_mock_for_schema(schema):
    """Create appropriate mock response based on Pydantic schema."""
    if schema == RetrievalDecision:
        return RetrievalDecision(has_enough=True, needs=[])
    if schema == RelevanceResult:
        return RelevanceResult(
            relevant=True,
            confidence="high",
            reasoning="Content is relevant to the skill's purpose.",
        )
    if schema == SafetyResult:
        return SafetyResult(
            safe=True,
            concerns=[],
            reasoning="No safety concerns found.",
        )
    if schema == ValidationSummary:
        return ValidationSummary(
            summary="Content reviewed and approved. No issues found.",
        )
    return RetrievalDecision(has_enough=True, needs=[])


@pytest.fixture
def mock_llm():
    """Mock LLM that supports both regular and structured output."""
    mock = MagicMock()

    mock.ainvoke = AsyncMock(
        return_value=_MockAIMessage("Content reviewed and approved.")
    )

    def create_structured_mock(schema):
        structured_mock = AsyncMock()
        structured_mock.ainvoke.return_value = _create_mock_for_schema(schema)
        return structured_mock

    mock.with_structured_output.side_effect = create_structured_mock

    return mock


@pytest.fixture
def mock_store():
    """Mock ResourceStore for SkillsIR."""
    store = MagicMock()

    store.list_skills.return_value = {
        "test-skill": "Test skill for validation",
    }
    store.tree.return_value = ["SKILL.md", "docs/guide.md"]
    store.read.return_value = "# Test Skill\nSome guidance."
    store.read_expanded.return_value = ("# Test Skill\nSome guidance.", 0)

    store.list_skills_async = AsyncMock(
        return_value={
            "test-skill": "Test skill for validation",
        }
    )
    store.tree_async = AsyncMock(return_value=["SKILL.md", "docs/guide.md"])
    store.read_async = AsyncMock(return_value="# Test Skill\nSome guidance.")
    store.read_expanded_async = AsyncMock(
        return_value=("# Test Skill\nSome guidance.", 0)
    )

    return store


@pytest.fixture
def base_validation_state(mock_store):
    """Base validation state for testing nodes."""
    return {
        "content": "# Security Detection Rule\n\nDetect lateral movement via RDP.",
        "skill_id": "test-skill-id",
        "tenant_id": "test-tenant",
        "original_filename": "detection-rule.md",
        "store": mock_store,
        "skill_name": "test-skill",
        "skill_context": "Test skill for security detection rules.",
        "relevance": None,
        "safety": None,
        "status": "pending",
        "validation_summary": None,
    }
