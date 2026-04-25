"""Skill validation LangGraph assembly.

3-node pipeline: assess_relevance → assess_safety → summarize.
All nodes run sequentially. If relevance or safety flags content,
status is set to 'flagged' but pipeline continues to summarize.

Spec: SecureSkillOnboarding_v1.md, Part 3.
"""

from typing import TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from analysi.agentic_orchestration.langgraph.skill_validation.nodes import (
    make_relevance_node,
    make_safety_node,
    make_summarize_node,
)
from analysi.agentic_orchestration.langgraph.skills.store import ResourceStore
from analysi.config.logging import get_logger

logger = get_logger(__name__)


class ValidationState(TypedDict):
    """State for the skill validation graph."""

    # Input (provided by caller)
    content: str
    skill_id: str
    tenant_id: str
    original_filename: str

    # Dependencies (injected)
    store: ResourceStore

    # Intermediate (populated by nodes)
    skill_name: str
    skill_context: str
    relevance: dict | None
    safety: dict | None

    # Output
    status: str  # approved | flagged | failed
    validation_summary: str | None


def build_validation_graph(llm) -> CompiledStateGraph:
    """Build the skill validation LangGraph.

    Architecture:
        assess_relevance → assess_safety → summarize → END

    If either node flags content, status becomes 'flagged'.
    Pipeline always continues to summarize for human review.

    Args:
        llm: LangChain ChatAnthropic instance.

    Returns:
        Compiled StateGraph.
    """
    graph = StateGraph(ValidationState)

    # Add nodes
    graph.add_node("assess_relevance", make_relevance_node(llm))
    graph.add_node("assess_safety", make_safety_node(llm))
    graph.add_node("summarize_validation", make_summarize_node(llm))

    # Entry point
    graph.set_entry_point("assess_relevance")

    # Linear flow: relevance → safety → summarize → END
    graph.add_edge("assess_relevance", "assess_safety")
    graph.add_edge("assess_safety", "summarize_validation")
    graph.add_edge("summarize_validation", END)

    return graph.compile()
