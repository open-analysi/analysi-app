"""Knowledge Extraction LangGraph assembly — Hydra project.

5-node pipeline: classify → relevance → placement → transform/merge → validate.
Conditional routing after relevance (not relevant → END) and after placement
(create_new vs merge_with_existing).
"""

from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from analysi.agentic_orchestration.langgraph.knowledge_extraction.nodes import (
    make_classify_node,
    make_merge_node,
    make_placement_node,
    make_relevance_node,
    make_summarize_node,
    make_transform_node,
    make_validate_node,
)
from analysi.agentic_orchestration.langgraph.skills.store import ResourceStore
from analysi.config.logging import get_logger
from analysi.schemas.knowledge_extraction import ExtractionStatus

logger = get_logger(__name__)


class ExtractionState(TypedDict):
    """State for the knowledge extraction graph."""

    # Input (provided by caller)
    content: str
    source_format: str
    source_description: str
    skill_id: str
    tenant_id: str

    # Dependencies (injected)
    store: ResourceStore

    # Intermediate (populated by nodes)
    skill_name: str
    skill_tree: list[str]
    classification: dict | None
    relevance: dict | None
    placement: dict | None
    transformed_content: str | None
    merge_info: dict | None
    validation: dict | None

    # Output
    status: str  # completed | rejected | failed
    extraction_summary: str | None


# =============================================================================
# Routing
# =============================================================================


def route_after_relevance(
    state: ExtractionState,
) -> Literal["determine_placement", "summarize_extraction"]:
    """Route after relevance: not relevant → summarize → END, else → placement."""
    if state.get("status") == "rejected":
        return "summarize_extraction"
    return "determine_placement"


def route_after_placement(
    state: ExtractionState,
) -> Literal["extract_and_transform", "merge_with_existing"]:
    """Route after placement: create_new → transform, merge → merge node."""
    placement = state.get("placement") or {}
    if placement.get("merge_strategy") == "merge_with_existing":
        return "merge_with_existing"
    return "extract_and_transform"


# =============================================================================
# Graph Building
# =============================================================================


def build_extraction_graph(llm) -> CompiledStateGraph:
    """Build the knowledge extraction LangGraph.

    Architecture:
        classify → relevance → (route) → placement → transform/merge → validate

    Args:
        llm: LangChain ChatAnthropic instance.

    Returns:
        Compiled StateGraph.
    """
    graph = StateGraph(ExtractionState)

    # Add nodes
    graph.add_node("classify_document", make_classify_node(llm))
    graph.add_node("assess_relevance", make_relevance_node(llm))
    graph.add_node("determine_placement", make_placement_node(llm))
    graph.add_node("extract_and_transform", make_transform_node(llm))
    graph.add_node("merge_with_existing", make_merge_node(llm))
    graph.add_node("validate_output", make_validate_node(llm))
    graph.add_node("summarize_extraction", make_summarize_node(llm))

    # Entry point
    graph.set_entry_point("classify_document")

    # Edges
    graph.add_edge("classify_document", "assess_relevance")

    # After relevance: not relevant → summarize → END, else → placement
    graph.add_conditional_edges(
        "assess_relevance",
        route_after_relevance,
        {
            "determine_placement": "determine_placement",
            "summarize_extraction": "summarize_extraction",
        },
    )

    # After placement: create_new → transform, merge → merge node
    graph.add_conditional_edges(
        "determine_placement",
        route_after_placement,
        {
            "extract_and_transform": "extract_and_transform",
            "merge_with_existing": "merge_with_existing",
        },
    )

    # Both paths converge at validate
    graph.add_edge("extract_and_transform", "validate_output")
    graph.add_edge("merge_with_existing", "validate_output")

    # Validate → summarize → END
    graph.add_edge("validate_output", "summarize_extraction")
    graph.add_edge("summarize_extraction", END)

    return graph.compile()


async def run_extraction(
    content: str,
    source_format: str,
    source_description: str,
    skill_id: str,
    tenant_id: str,
    llm: Any,
    store: ResourceStore,
    skill_name: str = "runbooks-manager",
) -> dict[str, Any]:
    """Run the knowledge extraction pipeline.

    This is the main entry point called by the service layer.

    Args:
        content: Source document content.
        source_format: Document format (markdown, json, text).
        source_description: Human-readable name/description of the source.
        skill_id: Target skill UUID (as string).
        tenant_id: Tenant identifier.
        llm: LangChain LLM instance.
        store: ResourceStore for SkillsIR context retrieval.

    Returns:
        Dict with pipeline outputs: status, classification, relevance,
        placement, transformed_content, merge_info, validation.
    """
    compiled_graph = build_extraction_graph(llm)

    initial_state: ExtractionState = {
        "content": content,
        "source_format": source_format,
        "source_description": source_description,
        "skill_id": skill_id,
        "tenant_id": tenant_id,
        "store": store,
        "skill_name": skill_name,
        "skill_tree": [],
        "classification": None,
        "relevance": None,
        "placement": None,
        "transformed_content": None,
        "merge_info": None,
        "validation": None,
        "extraction_summary": None,
        "status": "pending",
    }

    final_state = await compiled_graph.ainvoke(initial_state)

    status = final_state.get("status")
    if not status or status == ExtractionStatus.PENDING:
        logger.warning("Graph completed without setting status, defaulting to failed")
        status = ExtractionStatus.FAILED

    return {
        "status": status,
        "classification": final_state.get("classification"),
        "relevance": final_state.get("relevance"),
        "placement": final_state.get("placement"),
        "transformed_content": final_state.get("transformed_content"),
        "merge_info": final_state.get("merge_info"),
        "validation": final_state.get("validation"),
        "extraction_summary": final_state.get("extraction_summary"),
    }
