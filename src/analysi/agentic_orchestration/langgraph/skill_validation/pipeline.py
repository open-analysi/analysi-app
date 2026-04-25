"""Skill validation pipeline wrapped as ContentReviewPipeline.

Pipeline name: 'skill_validation'
Mode: review (content is judged but not transformed)

Spec: SecureSkillOnboarding_v1.md, Part 3.
"""

from typing import Any, Literal

from langgraph.graph import StateGraph

from analysi.agentic_orchestration.langgraph.content_review.content_gates import (
    ContentGate,
    content_length_gate,
    content_policy_gate,
    empty_content_gate,
    format_gate,
    python_ast_gate,
)
from analysi.models.content_review import ContentReviewStatus


class SkillValidationPipeline:
    """Skill content validation pipeline.

    Pipeline name: 'skill_validation'
    Mode: review (content is judged but not modified)

    Content gates: python_ast_gate (for .py), content_policy_gate,
    format_gate, empty_content_gate.
    """

    @property
    def name(self) -> str:
        return "skill_validation"

    @property
    def mode(self) -> Literal["review", "review_transform"]:
        return "review"

    def content_gates(self) -> list[ContentGate]:
        """Validation content gates: empty, format, AST, and content policy."""
        return [
            empty_content_gate,
            content_length_gate,
            format_gate,
            python_ast_gate,
            content_policy_gate,
        ]

    def build_graph(self, llm: Any) -> StateGraph:
        """Delegate to build_validation_graph."""
        from analysi.agentic_orchestration.langgraph.skill_validation.graph import (
            build_validation_graph,
        )

        return build_validation_graph(llm)  # type: ignore[return-value]

    def initial_state(self, content: str, skill_id: str, **context: Any) -> dict:
        """Create initial state for the validation graph."""
        return {
            "content": content,
            "skill_id": skill_id,
            "tenant_id": context.get("tenant_id", ""),
            "original_filename": context.get("original_filename", "unknown"),
            "store": context.get("store"),
            "skill_name": context.get("skill_name", "unknown"),
            "skill_context": "",
            "relevance": None,
            "safety": None,
            "status": "pending",
            "validation_summary": None,
        }

    def extract_results(self, final_state: dict) -> dict:
        """Extract validation-specific results from final graph state.

        Returns dict with special keys prefixed with '_' for the service:
        - _status: 'approved' or 'flagged'
        - _summary: the validation summary
        """
        status = final_state.get("status", "approved")
        # If still pending, it means nothing flagged it → approved
        if status == ContentReviewStatus.PENDING:
            status = "approved"

        return {
            "_status": status,
            "_summary": final_state.get("validation_summary"),
            "relevance": final_state.get("relevance"),
            "safety": final_state.get("safety"),
        }


# Auto-register when this module is imported
def _register():
    from analysi.agentic_orchestration.langgraph.content_review.pipeline import (
        register_pipeline,
    )

    register_pipeline(SkillValidationPipeline())


_register()
