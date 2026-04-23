"""Shared fixtures for Knowledge Extraction pipeline tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.agentic_orchestration.langgraph.skills.context import RetrievalDecision
from analysi.schemas.knowledge_extraction import (
    DocumentClassification,
    ExtractionSummary,
    MergeResult,
    PlacementDecision,
    RelevanceAssessment,
    ValidationResult,
)


class _MockAIMessage:
    """Minimal AIMessage stand-in."""

    def __init__(self, content: str):
        self.content = content


def _create_mock_for_schema(schema):
    """Create appropriate mock response based on Pydantic schema."""
    if schema == RetrievalDecision:
        return RetrievalDecision(has_enough=True, needs=[])
    if schema == DocumentClassification:
        return DocumentClassification(
            doc_type="new_runbook",
            confidence="high",
            reasoning="Contains step-by-step investigation procedure.",
        )
    if schema == RelevanceAssessment:
        return RelevanceAssessment(
            is_relevant=True,
            applicable_namespaces=["repository/"],
            reasoning="Contains security investigation knowledge.",
        )
    if schema == PlacementDecision:
        return PlacementDecision(
            target_namespace="repository/",
            target_filename="test-runbook.md",
            merge_strategy="create_new",
            merge_target=None,
            reasoning="No existing document covers this topic.",
        )
    if schema == MergeResult:
        return MergeResult(
            merged_content="# Merged\n\n## Steps\n\n### 1. Step ★\nDo thing.",
            original_content="# Original content",
            change_summary="Added new investigation step.",
            sections_added=["Step 3"],
            sections_modified=[],
        )
    if schema == ValidationResult:
        return ValidationResult(
            valid=True,
            errors=[],
            warnings=["Minor style suggestion"],
        )
    if schema == ExtractionSummary:
        return ExtractionSummary(
            summary="This document was extracted as a new runbook for investigating brute force attacks.",
        )
    return RetrievalDecision(has_enough=True, needs=[])


@pytest.fixture
def mock_llm():
    """Mock LLM that supports both regular and structured output."""
    mock = MagicMock()

    # Regular ainvoke (for transform node — returns markdown text)
    mock.ainvoke = AsyncMock(
        return_value=_MockAIMessage(
            "---\ntitle: Test Runbook\ndetection_rule: test\nalert_type: test\n"
            "subcategory: test\nsource_category: test\n---\n\n"
            "# Test Runbook\n\n## Steps\n\n### 1. Analysis ★\nDo analysis.\n"
        )
    )

    # Structured output
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
        "runbooks-manager": "Runbook management and composition",
    }
    store.tree.return_value = [
        "SKILL.md",
        "repository/sql-injection-detection.md",
        "common/by_source/waf-siem-evidence.md",
        "references/building/format-specification.md",
    ]
    store.read.return_value = "# Skill Content\nSome guidance here."
    store.read_expanded.return_value = ("# Skill Content\nSome guidance here.", 0)

    store.list_skills_async = AsyncMock(
        return_value={
            "runbooks-manager": "Runbook management and composition",
        }
    )
    store.tree_async = AsyncMock(
        return_value=[
            "SKILL.md",
            "repository/sql-injection-detection.md",
            "common/by_source/waf-siem-evidence.md",
            "references/building/format-specification.md",
        ]
    )
    store.read_async = AsyncMock(return_value="# Skill Content\nSome guidance here.")
    store.read_expanded_async = AsyncMock(
        return_value=("# Skill Content\nSome guidance here.", 0)
    )
    store.read_document_async = AsyncMock(
        return_value="# Existing Document\n\n### 1. Original Step\nDo original thing."
    )

    return store


@pytest.fixture
def soar_playbook_content():
    """Sample SOAR playbook JSON for testing."""
    return """{
  "name": "SQL Injection Response",
  "description": "Automated response playbook for SQL injection alerts",
  "steps": [
    {"id": 1, "action": "get_alert_details", "connector": "splunk_soar"},
    {"id": 2, "action": "ip_reputation", "connector": "virustotal"},
    {"id": 3, "action": "block_ip", "connector": "firewall"}
  ]
}"""


@pytest.fixture
def blog_article_content():
    """Sample blog article for testing."""
    return """# EDR Lateral Movement Detection

Detecting lateral movement using EDR telemetry requires monitoring
process creation events, network connections, and authentication logs.

## Key Investigation Steps

1. Check for PsExec or WMI execution patterns
2. Review authentication events in the ±15 minute window
3. Correlate network connections with known C2 infrastructure
4. Analyze parent-child process relationships for anomalies

## Tools Used
- CrowdStrike Falcon for process telemetry
- Splunk for log correlation
"""


@pytest.fixture
def irrelevant_content():
    """Content that should be rejected as irrelevant."""
    return """# Company Vacation Policy 2025

All employees are entitled to 20 days of paid vacation per year.
Please submit your vacation requests at least 2 weeks in advance.

## Holiday Schedule
- New Year's Day: January 1
- Memorial Day: Last Monday in May
"""


@pytest.fixture
def base_state(mock_store, soar_playbook_content):
    """Base extraction state for testing nodes."""
    return {
        "content": soar_playbook_content,
        "source_format": "json",
        "source_description": "SQL Injection Response Playbook",
        "skill_id": "test-skill-id",
        "tenant_id": "test-tenant",
        "store": mock_store,
        "skill_name": "runbooks-manager",
        "skill_tree": [
            "repository/sql-injection-detection.md",
            "common/by_source/waf-siem-evidence.md",
        ],
        "classification": None,
        "relevance": None,
        "placement": None,
        "transformed_content": None,
        "merge_info": None,
        "validation": None,
        "status": "pending",
    }
