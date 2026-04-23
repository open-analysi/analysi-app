"""Extraction pipeline wrapped as ContentReviewPipeline.

Wraps the existing 6-node extraction LangGraph as a content review pipeline
with mode=review_transform.
"""

from typing import Any, Literal

from langgraph.graph import StateGraph

from analysi.agentic_orchestration.langgraph.content_review.content_gates import (
    ContentGate,
    content_length_gate,
    content_policy_gate,
    empty_content_gate,
    format_gate,
)


class ExtractionReviewPipeline:
    """Wraps the existing extraction graph as a ContentReviewPipeline.

    Pipeline name: 'extraction'
    Mode: review_transform (content is classified, validated, AND transformed)
    """

    @property
    def name(self) -> str:
        return "extraction"

    @property
    def mode(self) -> Literal["review", "review_transform"]:
        return "review_transform"

    def content_gates(self) -> list[ContentGate]:
        """Extraction content gates: empty, length, format, and content policy."""
        return [
            empty_content_gate,
            content_length_gate,
            format_gate,
            content_policy_gate,
        ]

    def build_graph(self, llm: Any) -> StateGraph:
        """Delegate to existing build_extraction_graph."""
        from analysi.agentic_orchestration.langgraph.knowledge_extraction.graph import (
            build_extraction_graph,
        )

        return build_extraction_graph(llm)  # type: ignore[return-value]

    def initial_state(self, content: str, skill_id: str, **context: Any) -> dict:
        """Create initial state for the extraction graph."""
        return {
            "content": content,
            "source_format": context.get("source_format", "unknown"),
            "source_description": context.get("source_description", ""),
            "skill_id": skill_id,
            "tenant_id": context.get("tenant_id", ""),
            "store": context.get("store"),
        }

    def extract_results(self, final_state: dict) -> dict:
        """Extract extraction-specific results from final graph state.

        Returns dict with special keys prefixed with '_' for the service:
        - _status: 'approved', 'flagged', or 'failed'
        - _transformed_content: the transformed content (if any)
        - _summary: the extraction summary
        """
        status = final_state.get("status", "completed")
        # Map extraction status to content review status
        status_map = {
            "completed": "approved",
            "rejected": "rejected",
            "failed": "failed",
        }
        review_status = status_map.get(status, "approved")

        return {
            "_status": review_status,
            "_transformed_content": final_state.get("transformed_content"),
            "_summary": final_state.get("extraction_summary"),
            "classification": final_state.get("classification"),
            "relevance": final_state.get("relevance"),
            "placement": final_state.get("placement"),
            "merge_info": final_state.get("merge_info"),
            "validation": final_state.get("validation"),
        }


# Auto-register when this module is imported
def _register():
    from analysi.agentic_orchestration.langgraph.content_review.pipeline import (
        register_pipeline,
    )

    register_pipeline(ExtractionReviewPipeline())


_register()
