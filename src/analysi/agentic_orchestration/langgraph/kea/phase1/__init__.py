"""Kea Runbook Matching and Composition.

This module implements runbook matching and composition using the SubStep pattern.

Match Path (HIGH/VERY_HIGH confidence):
- Fetch existing runbook
- Expand WikiLinks
- Return as-is

Composition Path (MEDIUM/LOW confidence):
- 5 LLM steps: gaps → strategy → extraction → compose → fix
- Produces new runbook from multiple sources
"""

from analysi.agentic_orchestration.langgraph.kea.phase1.confidence import (
    THRESHOLDS,
    ConfidenceLevel,
    determine_confidence,
    should_use_match_path,
)
from analysi.agentic_orchestration.langgraph.kea.phase1.graph import (
    Phase1State,
    build_phase1_graph,
    route_by_confidence,
    run_phase1,
)
from analysi.agentic_orchestration.langgraph.kea.phase1.matcher import Phase1Matcher

__all__ = [
    "THRESHOLDS",
    # Confidence
    "ConfidenceLevel",
    # Matcher
    "Phase1Matcher",
    # Graph
    "Phase1State",
    "build_phase1_graph",
    "determine_confidence",
    "route_by_confidence",
    "run_phase1",
    "should_use_match_path",
]
