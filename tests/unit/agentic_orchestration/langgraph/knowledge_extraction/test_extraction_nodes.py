"""Unit tests for Knowledge Extraction pipeline nodes.

Tests each node in isolation with mocked LLM and store.
"""

import pytest

from analysi.agentic_orchestration.langgraph.knowledge_extraction.nodes import (
    _validate_runbook,
    _validate_sub_runbook,
    make_classify_node,
    make_merge_node,
    make_placement_node,
    make_relevance_node,
    make_summarize_node,
    make_transform_node,
    make_validate_node,
)


class TestClassifyNode:
    """Tests for Node 1: classify_document."""

    @pytest.mark.asyncio
    async def test_classify_soar_playbook(self, mock_llm, base_state):
        node = make_classify_node(mock_llm)
        result = await node(base_state)

        assert "classification" in result
        assert result["classification"] is not None
        assert result["classification"]["doc_type"] == "new_runbook"

    @pytest.mark.asyncio
    async def test_classify_no_skillsir(self, mock_llm, base_state, mock_store):
        """Classify node should NOT call SkillsIR (needs_context=False)."""
        node = make_classify_node(mock_llm)
        await node(base_state)

        # SkillsIR retrieval methods should not be called
        mock_store.list_skills_async.assert_not_called()

    @pytest.mark.asyncio
    async def test_classify_uses_structured_output(self, mock_llm, base_state):
        node = make_classify_node(mock_llm)
        await node(base_state)

        # Should have called with_structured_output for DocumentClassification
        mock_llm.with_structured_output.assert_called()


class TestRelevanceNode:
    """Tests for Node 2: assess_relevance."""

    @pytest.mark.asyncio
    async def test_relevant_document(self, mock_llm, base_state):
        base_state["classification"] = {
            "doc_type": "new_runbook",
            "confidence": "high",
            "reasoning": "test",
        }
        node = make_relevance_node(mock_llm)
        result = await node(base_state)

        assert "relevance" in result
        assert result["relevance"]["is_relevant"] is True
        # Should NOT set status to rejected
        assert "status" not in result or result.get("status") != "rejected"

    @pytest.mark.asyncio
    async def test_irrelevant_document_sets_rejected(self, mock_llm, base_state):
        """When LLM says not relevant, node should set status=rejected."""
        from unittest.mock import AsyncMock

        from analysi.agentic_orchestration.langgraph.skills.context import (
            RetrievalDecision,
        )
        from analysi.schemas.knowledge_extraction import RelevanceAssessment

        # Override structured output to return not-relevant
        def create_structured_mock(schema):
            structured_mock = AsyncMock()
            if schema == RelevanceAssessment:
                structured_mock.ainvoke.return_value = RelevanceAssessment(
                    is_relevant=False,
                    applicable_namespaces=[],
                    reasoning="This is an HR policy, not security content.",
                )
            elif schema == RetrievalDecision:
                structured_mock.ainvoke.return_value = RetrievalDecision(
                    has_enough=True, needs=[]
                )
            return structured_mock

        mock_llm.with_structured_output.side_effect = create_structured_mock

        base_state["classification"] = {"doc_type": "reference_documentation"}
        node = make_relevance_node(mock_llm)
        result = await node(base_state)

        assert result["relevance"]["is_relevant"] is False
        assert result["status"] == "rejected"


class TestPlacementNode:
    """Tests for Node 3: determine_placement."""

    @pytest.mark.asyncio
    async def test_placement_create_new(self, mock_llm, base_state):
        base_state["classification"] = {"doc_type": "new_runbook"}
        base_state["relevance"] = {
            "is_relevant": True,
            "applicable_namespaces": ["repository/"],
        }
        node = make_placement_node(mock_llm)
        result = await node(base_state)

        assert "placement" in result
        placement = result["placement"]
        assert placement["target_namespace"] == "repository/"
        assert placement["merge_strategy"] == "create_new"

    @pytest.mark.asyncio
    async def test_placement_uses_skillsir(self, mock_llm, base_state, mock_store):
        """Placement node should use SkillsIR for namespace context."""
        base_state["classification"] = {"doc_type": "new_runbook"}
        base_state["relevance"] = {
            "is_relevant": True,
            "applicable_namespaces": ["repository/"],
        }
        node = make_placement_node(mock_llm)
        await node(base_state)

        # SkillsIR should have been called
        mock_store.list_skills_async.assert_called()


class TestTransformNode:
    """Tests for Node 4a: extract_and_transform."""

    @pytest.mark.asyncio
    async def test_transform_returns_content(self, mock_llm, base_state):
        base_state["classification"] = {"doc_type": "new_runbook"}
        base_state["placement"] = {
            "target_namespace": "repository/",
            "target_filename": "test-runbook.md",
        }
        node = make_transform_node(mock_llm)
        result = await node(base_state)

        assert "transformed_content" in result
        assert result["transformed_content"] is not None
        assert len(result["transformed_content"]) > 0


class TestMergeNode:
    """Tests for Node 4b: merge_with_existing."""

    @pytest.mark.asyncio
    async def test_merge_returns_content_and_info(self, mock_llm, base_state):
        base_state["classification"] = {"doc_type": "source_evidence_pattern"}
        base_state["placement"] = {
            "target_namespace": "common/by_source/",
            "target_filename": "edr-lateral-movement-evidence.md",
            "merge_strategy": "merge_with_existing",
            "merge_target": "common/by_source/edr-lateral-movement-evidence.md",
        }
        node = make_merge_node(mock_llm)
        result = await node(base_state)

        assert "transformed_content" in result
        assert "merge_info" in result
        merge_info = result["merge_info"]
        assert merge_info is not None
        assert "merged_content" in merge_info
        assert "original_content" in merge_info

    @pytest.mark.asyncio
    async def test_merge_loads_existing_document(
        self, mock_llm, base_state, mock_store
    ):
        base_state["classification"] = {"doc_type": "source_evidence_pattern"}
        base_state["placement"] = {
            "merge_strategy": "merge_with_existing",
            "merge_target": "common/by_source/test.md",
        }
        node = make_merge_node(mock_llm)
        await node(base_state)

        # Should have loaded the existing document
        mock_store.read_document_async.assert_called_once_with(
            "runbooks-manager", "common/by_source/test.md"
        )


class TestValidateNode:
    """Tests for Node 5: validate_output."""

    @pytest.mark.asyncio
    async def test_validate_valid_runbook(self, mock_llm, base_state):
        base_state["classification"] = {"doc_type": "new_runbook"}
        base_state["placement"] = {"target_namespace": "repository/"}
        base_state["transformed_content"] = (
            "---\ntitle: Test\ndetection_rule: test\nalert_type: test\n"
            "subcategory: test\nsource_category: test\n---\n\n"
            "# Test Runbook\n\n### 1. Step ★\nDo thing.\n"
        )
        node = make_validate_node(mock_llm)
        result = await node(base_state)

        assert "validation" in result
        assert result["validation"]["valid"] is True
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_validate_empty_content(self, mock_llm, base_state):
        base_state["classification"] = {"doc_type": "new_runbook"}
        base_state["placement"] = {"target_namespace": "repository/"}
        base_state["transformed_content"] = ""
        node = make_validate_node(mock_llm)
        result = await node(base_state)

        assert result["validation"]["valid"] is False
        assert "empty" in result["validation"]["errors"][0].lower()


class TestRunbookValidation:
    """Tests for deterministic runbook validation."""

    def test_valid_runbook(self):
        content = (
            "---\ndetection_rule: test\nalert_type: test\n"
            "subcategory: test\nsource_category: test\n---\n"
            "# Runbook\n### 1. Step ★\nDo thing."
        )
        errors, warnings = [], []
        _validate_runbook(content, errors, warnings)
        assert len(errors) == 0

    def test_missing_frontmatter(self):
        content = "# Runbook\n### 1. Step ★\nDo thing."
        errors, warnings = [], []
        _validate_runbook(content, errors, warnings)
        assert any("frontmatter" in w.lower() for w in warnings)

    def test_malformed_yaml(self):
        content = "---\n: invalid: yaml: here\n---\n# Test"
        errors, warnings = [], []
        _validate_runbook(content, errors, warnings)
        assert any("malformed" in e.lower() for e in errors)

    def test_no_critical_markers(self):
        content = (
            "---\ndetection_rule: test\nalert_type: test\n"
            "subcategory: test\nsource_category: test\n---\n"
            "# Runbook\n### 1. Step\nDo thing."
        )
        errors, warnings = [], []
        _validate_runbook(content, errors, warnings)
        assert any("★" in w for w in warnings)

    def test_missing_frontmatter_fields(self):
        content = "---\ndetection_rule: test\n---\n# Runbook\n### 1. Step ★\nDo thing."
        errors, warnings = [], []
        _validate_runbook(content, errors, warnings)
        assert any("alert_type" in w for w in warnings)


class TestSubRunbookValidation:
    """Tests for deterministic sub-runbook validation."""

    def test_valid_sub_runbook(self):
        content = "### 1. Step\nDo thing.\n### 2. Step\nDo other thing."
        errors, warnings = [], []
        _validate_sub_runbook(content, errors, warnings)
        assert len(errors) == 0

    def test_sub_runbook_with_frontmatter_warns(self):
        content = "---\ntitle: test\n---\n### 1. Step\nDo thing."
        errors, warnings = [], []
        _validate_sub_runbook(content, errors, warnings)
        assert any("frontmatter" in w.lower() for w in warnings)

    def test_sub_runbook_no_headers(self):
        content = "Just some plain text without headers."
        errors, warnings = [], []
        _validate_sub_runbook(content, errors, warnings)
        assert any("###" in w for w in warnings)


class TestSummarizeNode:
    """Tests for Node 6: summarize_extraction."""

    @pytest.mark.asyncio
    async def test_summarize_completed_extraction(self, mock_llm, base_state):
        """T1: Summarize node produces non-empty summary for completed state."""
        base_state["status"] = "completed"
        base_state["classification"] = {"doc_type": "new_runbook", "confidence": "high"}
        base_state["relevance"] = {
            "is_relevant": True,
            "applicable_namespaces": ["repository/"],
        }
        base_state["placement"] = {
            "target_namespace": "repository/",
            "target_filename": "test-runbook.md",
            "merge_strategy": "create_new",
        }
        base_state["transformed_content"] = "# Test Runbook\n\n### 1. Step\nDo thing."
        base_state["validation"] = {"valid": True, "errors": [], "warnings": []}

        node = make_summarize_node(mock_llm)
        result = await node(base_state)

        assert "extraction_summary" in result
        assert result["extraction_summary"] is not None
        assert len(result["extraction_summary"]) > 0

    @pytest.mark.asyncio
    async def test_summarize_rejected_extraction(self, mock_llm, base_state):
        """T2: Summarize node produces rejection explanation for rejected state."""
        base_state["status"] = "rejected"
        base_state["classification"] = {
            "doc_type": "reference_documentation",
            "confidence": "low",
        }
        base_state["relevance"] = {
            "is_relevant": False,
            "applicable_namespaces": [],
            "reasoning": "Not security investigation content",
        }

        node = make_summarize_node(mock_llm)
        result = await node(base_state)

        assert "extraction_summary" in result
        assert result["extraction_summary"] is not None
        assert len(result["extraction_summary"]) > 0

    @pytest.mark.asyncio
    async def test_summarize_no_internal_terms(self, mock_llm, base_state):
        """T3: Summary should not contain internal pipeline terms."""
        from unittest.mock import AsyncMock

        from analysi.schemas.knowledge_extraction import ExtractionSummary

        # Set up state for completed extraction
        base_state["status"] = "completed"
        base_state["classification"] = {"doc_type": "new_runbook", "confidence": "high"}
        base_state["relevance"] = {"is_relevant": True}
        base_state["placement"] = {
            "target_namespace": "repository/",
            "target_filename": "t.md",
        }
        base_state["transformed_content"] = "# Runbook"
        base_state["validation"] = {"valid": True, "errors": [], "warnings": []}

        # Mock LLM to return a summary that leaks internal terms (should be caught by prompt)
        def create_structured_mock(schema):
            structured_mock = AsyncMock()
            if schema == ExtractionSummary:
                structured_mock.ainvoke.return_value = ExtractionSummary(
                    summary="This document was extracted as a new runbook for investigating brute force attacks."
                )
            else:
                from analysi.agentic_orchestration.langgraph.skills.context import (
                    RetrievalDecision,
                )

                structured_mock.ainvoke.return_value = RetrievalDecision(
                    has_enough=True, needs=[]
                )
            return structured_mock

        mock_llm.with_structured_output.side_effect = create_structured_mock

        node = make_summarize_node(mock_llm)
        result = await node(base_state)

        summary = result["extraction_summary"]
        assert "Node 3" not in summary
        assert "SkillsIR" not in summary
        assert "SubStep" not in summary
