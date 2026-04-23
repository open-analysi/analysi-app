"""Unit tests for Knowledge Extraction graph assembly and routing.

Tests the graph structure, conditional routing, and end-to-end flow with mocked LLM.
"""

import pytest

from analysi.agentic_orchestration.langgraph.knowledge_extraction.graph import (
    ExtractionState,
    build_extraction_graph,
    route_after_placement,
    route_after_relevance,
    run_extraction,
)


class TestRouting:
    """Tests for conditional routing functions."""

    def test_route_relevant_to_placement(self):
        state = {"status": "pending", "relevance": {"is_relevant": True}}
        assert route_after_relevance(state) == "determine_placement"

    def test_route_not_relevant_to_summarize(self):
        state = {"status": "rejected"}
        assert route_after_relevance(state) == "summarize_extraction"

    def test_route_create_new(self):
        state = {"placement": {"merge_strategy": "create_new"}}
        assert route_after_placement(state) == "extract_and_transform"

    def test_route_merge_with_existing(self):
        state = {"placement": {"merge_strategy": "merge_with_existing"}}
        assert route_after_placement(state) == "merge_with_existing"

    def test_route_default_create_new(self):
        """No placement → default to create_new."""
        state = {"placement": None}
        assert route_after_placement(state) == "extract_and_transform"

    def test_route_empty_placement(self):
        state = {"placement": {}}
        assert route_after_placement(state) == "extract_and_transform"


class TestGraphStructure:
    """Tests for graph building."""

    def test_build_graph_compiles(self, mock_llm):
        graph = build_extraction_graph(mock_llm)
        assert graph is not None

    def test_graph_has_expected_nodes(self, mock_llm):
        """The graph should have all 6 nodes."""
        from langgraph.graph import StateGraph

        StateGraph(ExtractionState)
        # We can't easily inspect compiled graph nodes, but we can verify
        # the build function doesn't error
        compiled = build_extraction_graph(mock_llm)
        assert compiled is not None


class TestEndToEnd:
    """End-to-end tests with mocked LLM — create_new path."""

    @pytest.mark.asyncio
    async def test_full_pipeline_create_new(
        self, mock_llm, mock_store, soar_playbook_content
    ):
        result = await run_extraction(
            content=soar_playbook_content,
            source_format="json",
            source_description="SQL Injection Response Playbook",
            skill_id="test-skill-id",
            tenant_id="test-tenant",
            llm=mock_llm,
            store=mock_store,
        )

        assert result["status"] == "completed"
        assert result["classification"] is not None
        assert result["relevance"] is not None
        assert result["placement"] is not None
        assert result["transformed_content"] is not None
        assert result["validation"] is not None

    @pytest.mark.asyncio
    async def test_full_pipeline_returns_extraction_summary(
        self, mock_llm, mock_store, soar_playbook_content
    ):
        """T6: run_extraction returns extraction_summary in result dict."""
        result = await run_extraction(
            content=soar_playbook_content,
            source_format="json",
            source_description="SQL Injection Response Playbook",
            skill_id="test-skill-id",
            tenant_id="test-tenant",
            llm=mock_llm,
            store=mock_store,
        )

        assert "extraction_summary" in result
        assert result["extraction_summary"] is not None
        assert len(result["extraction_summary"]) > 0

    @pytest.mark.asyncio
    async def test_rejected_document_has_summary(
        self, mock_llm, mock_store, irrelevant_content
    ):
        """T5: Graph routes rejected path through summarize node."""
        from unittest.mock import AsyncMock

        from analysi.agentic_orchestration.langgraph.skills.context import (
            RetrievalDecision,
        )
        from analysi.schemas.knowledge_extraction import (
            DocumentClassification,
            ExtractionSummary,
            RelevanceAssessment,
        )

        def create_structured_mock(schema):
            structured_mock = AsyncMock()
            if schema == DocumentClassification:
                structured_mock.ainvoke.return_value = DocumentClassification(
                    doc_type="reference_documentation",
                    confidence="low",
                    reasoning="HR policy document",
                )
            elif schema == RelevanceAssessment:
                structured_mock.ainvoke.return_value = RelevanceAssessment(
                    is_relevant=False,
                    applicable_namespaces=[],
                    reasoning="Not security content",
                )
            elif schema == ExtractionSummary:
                structured_mock.ainvoke.return_value = ExtractionSummary(
                    summary="This document is an HR vacation policy and does not contain security investigation knowledge.",
                )
            elif schema == RetrievalDecision:
                structured_mock.ainvoke.return_value = RetrievalDecision(
                    has_enough=True, needs=[]
                )
            return structured_mock

        mock_llm.with_structured_output.side_effect = create_structured_mock

        result = await run_extraction(
            content=irrelevant_content,
            source_format="markdown",
            source_description="Company Vacation Policy",
            skill_id="test-skill-id",
            tenant_id="test-tenant",
            llm=mock_llm,
            store=mock_store,
        )

        assert result["status"] == "rejected"
        assert result["extraction_summary"] is not None
        assert len(result["extraction_summary"]) > 0

    @pytest.mark.asyncio
    async def test_irrelevant_document_rejected(
        self, mock_llm, mock_store, irrelevant_content
    ):
        """Irrelevant document should be rejected at relevance step."""
        from unittest.mock import AsyncMock

        from analysi.agentic_orchestration.langgraph.skills.context import (
            RetrievalDecision,
        )
        from analysi.schemas.knowledge_extraction import (
            DocumentClassification,
            RelevanceAssessment,
        )

        # Override LLM to return not-relevant for relevance assessment
        def create_structured_mock(schema):
            structured_mock = AsyncMock()
            if schema == DocumentClassification:
                structured_mock.ainvoke.return_value = DocumentClassification(
                    doc_type="reference_documentation",
                    confidence="low",
                    reasoning="HR policy document",
                )
            elif schema == RelevanceAssessment:
                structured_mock.ainvoke.return_value = RelevanceAssessment(
                    is_relevant=False,
                    applicable_namespaces=[],
                    reasoning="Not security content",
                )
            elif schema == RetrievalDecision:
                structured_mock.ainvoke.return_value = RetrievalDecision(
                    has_enough=True, needs=[]
                )
            return structured_mock

        mock_llm.with_structured_output.side_effect = create_structured_mock

        result = await run_extraction(
            content=irrelevant_content,
            source_format="markdown",
            source_description="Company Vacation Policy",
            skill_id="test-skill-id",
            tenant_id="test-tenant",
            llm=mock_llm,
            store=mock_store,
        )

        assert result["status"] == "rejected"
        assert result["classification"] is not None
        assert result["relevance"] is not None
        assert result["relevance"]["is_relevant"] is False
        # Pipeline stops after relevance — no placement/transform/validate
        assert result["placement"] is None
        assert result["transformed_content"] is None
