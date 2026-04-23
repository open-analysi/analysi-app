"""Shared fixtures for Kea Runbook Matching tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.agentic_orchestration.langgraph.kea.phase1.substeps import (
    Extraction,
    ExtractionOutput,
    Gap,
    GapAnalysisOutput,
    StrategyOutput,
    StrategySource,
)
from analysi.agentic_orchestration.langgraph.skills.context import RetrievalDecision


class _MockAIMessage:
    """Minimal AIMessage stand-in so `hasattr(response, 'content')` works."""

    def __init__(self, content: str):
        self.content = content


@pytest.fixture
def mock_llm():
    """Create mock LLM for testing."""
    mock = MagicMock()
    mock.ainvoke = AsyncMock(return_value=_MockAIMessage("mocked response"))
    return mock


@pytest.fixture
def mock_store(mock_runbook_index):
    """Create mock ResourceStore for SkillsIR testing.

    Mocks both sync and async methods including DB-mode methods
    used by Phase1Matcher.from_store() (read_table_async) and
    run_phase1() composition persistence (write_document_async, write_table_async).
    """
    store = MagicMock()

    # --- Sync methods (used by FileSystemResourceStore-style code) ---
    store.list_skills.return_value = {
        "runbooks-manager": "Runbook management and composition",
        "cybersecurity-analyst": "Security analysis guidance",
    }
    store.tree.return_value = ["SKILL.md", "references/guide.md"]
    store.read.return_value = "# Skill Content\nSome guidance here."
    store.read_expanded.return_value = ("# Skill Content\nSome guidance here.", 0)

    # --- Async methods (used by LangGraph nodes and SkillsIR) ---
    store.list_skills_async = AsyncMock(
        return_value={
            "runbooks-manager": "Runbook management and composition",
            "cybersecurity-analyst": "Security analysis guidance",
        }
    )
    store.tree_async = AsyncMock(return_value=["SKILL.md", "references/guide.md"])
    store.read_async = AsyncMock(return_value="# Skill Content\nSome guidance here.")

    # read_expanded_async is used by both SkillsIR (for skill files) and
    # fetch_runbook_node (for runbook content with WikiLink expansion).
    # Return content that satisfies match path assertions ("SQL Injection Investigation").
    _default_runbook = (
        "---\ntitle: SQL Injection Investigation\n---\n\n"
        "# SQL Injection Investigation\n\n## Steps\n\n"
        "### 1. Alert Understanding ★\nReview details.\n\n"
        "### 2. Payload Analysis ★\nAnalyze payload.\n"
    )
    store.read_expanded_async = AsyncMock(return_value=(_default_runbook, 0))

    # --- DB-mode methods (used by Phase1Matcher.from_store and run_phase1 persistence) ---
    store.read_table_async = AsyncMock(return_value=mock_runbook_index)
    store.write_document_async = AsyncMock(return_value=True)
    store.write_table_async = AsyncMock(return_value=True)

    return store


def _create_mock_for_schema(schema):
    """Create appropriate mock response based on the Pydantic schema."""
    if schema == RetrievalDecision:
        return RetrievalDecision(has_enough=True, needs=[])
    if schema == GapAnalysisOutput:
        return GapAnalysisOutput(
            gaps=[
                Gap(category="coverage", description="Missing step", severity="medium")
            ],
            coverage_assessment="70% coverage",
        )
    if schema == StrategyOutput:
        return StrategyOutput(
            strategy="multi_source_blending",
            sources=[
                StrategySource(
                    runbook="sql-injection-detection.md",
                    sections=["payload_analysis"],
                    reason="covers injection",
                )
            ],
            template=None,
        )
    if schema == ExtractionOutput:
        return ExtractionOutput(
            extractions=[
                Extraction(
                    content="## Analysis\nContent here",
                    source="sql-injection-detection.md",
                    section="analysis",
                )
            ],
            remaining_gaps=[],
        )
    # Default fallback
    return RetrievalDecision(has_enough=True, needs=[])


@pytest.fixture
def mock_llm_with_structured_output():
    """Create mock LLM that supports structured output for SkillsIR and composition substeps."""
    mock = MagicMock()

    # For regular ainvoke calls (task execution - e.g., compose_runbook, fix_runbook)
    # Must return object with .content attribute (like AIMessage)
    mock.ainvoke = AsyncMock(
        return_value=_MockAIMessage("""# Test Runbook

## Steps

### 1. Analysis ★
Do analysis.

### 2. Review ★
Do review.
""")
    )

    # For structured output calls (SkillsIR and composition substeps)
    def create_structured_mock(schema):
        """Create a mock that returns appropriate response for the schema."""
        structured_mock = AsyncMock()
        structured_mock.ainvoke.return_value = _create_mock_for_schema(schema)
        return structured_mock

    mock.with_structured_output.side_effect = create_structured_mock

    return mock


@pytest.fixture
def sample_alert_exact_match():
    """Alert that should exactly match a runbook."""
    return {
        "title": "SQL Injection Detected",
        "detection_rule": "Possible SQL Injection Payload Detected",
        "alert_type": "Web Attack",
        "subcategory": "SQL Injection",
        "source_category": "WAF",
        "mitre_tactics": ["T1190"],
    }


@pytest.fixture
def sample_alert_composition():
    """Alert requiring composition (no exact match)."""
    return {
        "title": "IDOR with XSS Payload",
        "detection_rule": "custom-hybrid-rule",
        "alert_type": "Web Attack",
        "subcategory": "IDOR",
        "source_category": "WAF",
        "mitre_tactics": ["T1190", "T1189"],
    }


@pytest.fixture
def mock_runbook_index():
    """Mock runbook index data."""
    return [
        {
            "filename": "sql-injection-detection.md",
            "detection_rule": "Possible SQL Injection Payload Detected",
            "alert_type": "Web Attack",
            "subcategory": "SQL Injection",
            "source_category": "WAF",
            "mitre_tactics": ["T1190"],
        },
        {
            "filename": "idor-detection.md",
            "detection_rule": "IDOR Attempt Detected",
            "alert_type": "Web Attack",
            "subcategory": "IDOR",
            "source_category": "WAF",
            "mitre_tactics": ["T1190"],
        },
        {
            "filename": "xss-detection.md",
            "detection_rule": "XSS Payload Detected",
            "alert_type": "Web Attack",
            "subcategory": "XSS",
            "source_category": "WAF",
            "mitre_tactics": ["T1189"],
        },
    ]


@pytest.fixture
def mock_runbook_content():
    """Mock runbook file content."""
    return """---
title: SQL Injection Investigation
detection_rule: Possible SQL Injection Payload Detected
---

# SQL Injection Investigation

## Steps

### 1. Alert Understanding ★
Review the SQL injection attempt details.

### 2. Payload Analysis ★
Analyze the injection payload for severity.

### 3. Impact Assessment
Determine if data was accessed.
"""
