"""Subgraphs for agentic orchestration.

Both subgraphs use plain asyncio (no LangGraph) for simplicity and consistency.
"""

from .first_subgraph import (
    WorkflowGenerationState,
    run_first_subgraph,
)
from .second_subgraph_no_langgraph import run_second_subgraph

__all__ = [
    # First subgraph (Runbook Generation → Task Proposals)
    "WorkflowGenerationState",
    "run_first_subgraph",
    # Second subgraph (Task Building → Workflow Assembly)
    "run_second_subgraph",
]
