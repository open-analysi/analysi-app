"""ContentReviewPipeline protocol.

Defines the interface that all content review pipelines must implement.
Each pipeline provides content gates (Tier 1) and a LangGraph (Tier 2).
"""

from typing import Any, Literal, Protocol

from langgraph.graph import StateGraph

from analysi.agentic_orchestration.langgraph.content_review.content_gates import (
    ContentGate,
)


class ContentReviewPipeline(Protocol):
    """Protocol for content review pipelines.

    Two implementations:
    - ExtractionReviewPipeline (mode=review_transform): wraps existing extraction graph
    - SkillValidationPipeline (mode=review): judges content without transformation
    """

    @property
    def name(self) -> str:
        """Pipeline name, e.g. 'extraction', 'skill_validation'."""
        ...

    @property
    def mode(self) -> Literal["review", "review_transform"]:
        """Pipeline mode."""
        ...

    def content_gates(self) -> list[ContentGate]:
        """Return deterministic content gates to run before enqueuing."""
        ...

    def build_graph(self, llm: Any) -> StateGraph:
        """Build the LangGraph for async LLM processing."""
        ...

    def initial_state(self, content: str, skill_id: str, **context: Any) -> dict:
        """Create initial state for the graph."""
        ...

    def extract_results(self, final_state: dict) -> dict:
        """Extract pipeline-specific results from final graph state."""
        ...


# Pipeline registry — populated at import time by pipeline implementations
_PIPELINE_REGISTRY: dict[str, ContentReviewPipeline] = {}


def register_pipeline(pipeline: ContentReviewPipeline) -> None:
    """Register a pipeline implementation."""
    _PIPELINE_REGISTRY[pipeline.name] = pipeline


def get_pipeline_by_name(name: str) -> ContentReviewPipeline:
    """Look up a registered pipeline by name.

    Ensures known pipelines are imported (and thus registered) on first lookup.

    Raises:
        ValueError: If no pipeline is registered with the given name.
    """
    _ensure_pipelines_loaded()
    if name not in _PIPELINE_REGISTRY:
        raise ValueError(
            f"Unknown pipeline: {name!r}. Available: {list(_PIPELINE_REGISTRY.keys())}"
        )
    return _PIPELINE_REGISTRY[name]


_pipelines_loaded = False


def _ensure_pipelines_loaded() -> None:
    """Import known pipeline modules so they auto-register."""
    global _pipelines_loaded
    if _pipelines_loaded:
        return
    _pipelines_loaded = True
    # Each module calls register_pipeline() at import time
    import analysi.agentic_orchestration.langgraph.content_review.extraction_pipeline
    import analysi.agentic_orchestration.langgraph.skill_validation.pipeline  # noqa: F401
