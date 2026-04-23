"""Unit tests for skill validation pipeline nodes."""

from unittest.mock import AsyncMock

import pytest

from analysi.agentic_orchestration.langgraph.skill_validation.graph import (
    build_validation_graph,
)
from analysi.agentic_orchestration.langgraph.skill_validation.nodes import (
    make_relevance_node,
    make_safety_node,
    make_summarize_node,
)
from analysi.schemas.skill_validation import (
    RelevanceResult,
    SafetyResult,
)


class TestRelevanceNode:
    @pytest.mark.asyncio
    async def test_relevant_content(self, mock_llm, base_validation_state):
        """Relevant content should not set status to flagged."""
        node = make_relevance_node(mock_llm)
        result = await node(base_validation_state)

        assert "relevance" in result
        assert result["relevance"]["relevant"] is True
        assert "status" not in result  # Not flagged

    @pytest.mark.asyncio
    async def test_not_relevant_sets_flagged(self, mock_llm, base_validation_state):
        """Irrelevant content should set status to flagged."""

        def create_irrelevant_mock(schema):
            if schema == RelevanceResult:
                mock = AsyncMock()
                mock.ainvoke.return_value = RelevanceResult(
                    relevant=False,
                    confidence="high",
                    reasoning="Content is about cooking, not security.",
                )
                return mock
            # Default for other schemas
            from analysi.agentic_orchestration.langgraph.skills.context import (
                RetrievalDecision,
            )

            mock = AsyncMock()
            mock.ainvoke.return_value = RetrievalDecision(has_enough=True, needs=[])
            return mock

        mock_llm.with_structured_output.side_effect = create_irrelevant_mock

        node = make_relevance_node(mock_llm)
        result = await node(base_validation_state)

        assert result["relevance"]["relevant"] is False
        assert result["status"] == "flagged"


class TestSafetyNode:
    @pytest.mark.asyncio
    async def test_safe_content(self, mock_llm, base_validation_state):
        """Safe content should not set status to flagged."""
        node = make_safety_node(mock_llm)
        result = await node(base_validation_state)

        assert "safety" in result
        assert result["safety"]["safe"] is True
        assert "status" not in result

    @pytest.mark.asyncio
    async def test_unsafe_sets_flagged(self, mock_llm, base_validation_state):
        """Unsafe content should set status to flagged."""

        def create_unsafe_mock(schema):
            if schema == SafetyResult:
                mock = AsyncMock()
                mock.ainvoke.return_value = SafetyResult(
                    safe=False,
                    concerns=["Prompt injection attempt detected"],
                    reasoning="Contains hidden instructions.",
                )
                return mock
            from analysi.agentic_orchestration.langgraph.skills.context import (
                RetrievalDecision,
            )

            mock = AsyncMock()
            mock.ainvoke.return_value = RetrievalDecision(has_enough=True, needs=[])
            return mock

        mock_llm.with_structured_output.side_effect = create_unsafe_mock

        node = make_safety_node(mock_llm)
        result = await node(base_validation_state)

        assert result["safety"]["safe"] is False
        assert result["safety"]["concerns"] == ["Prompt injection attempt detected"]
        assert result["status"] == "flagged"


class TestSummarizeNode:
    @pytest.mark.asyncio
    async def test_produces_summary(self, mock_llm, base_validation_state):
        """Summarize node should produce a non-empty summary."""
        base_validation_state["relevance"] = {
            "relevant": True,
            "confidence": "high",
            "reasoning": "ok",
        }
        base_validation_state["safety"] = {
            "safe": True,
            "concerns": [],
            "reasoning": "ok",
        }

        node = make_summarize_node(mock_llm)
        result = await node(base_validation_state)

        assert "validation_summary" in result
        assert len(result["validation_summary"]) > 0


class TestGraphBuilds:
    def test_graph_compiles(self, mock_llm):
        """Validation graph should compile without error."""
        graph = build_validation_graph(mock_llm)
        assert graph is not None
