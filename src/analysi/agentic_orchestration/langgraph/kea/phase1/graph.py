"""Runbook Matching LangGraph assembly.

Combines SubSteps into a LangGraph with conditional routing.
Each composition SubStep uses SkillsIR for context retrieval.

This is a programmatic reimplementation of runbook-match-agent.md.
See CLAUDE.md in this directory for sync requirements.
"""

import json
import re
from datetime import UTC, datetime
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from analysi.agentic_orchestration.langgraph.kea.phase1.confidence import (
    ConfidenceLevel,
    determine_confidence,
    should_use_match_path,
)
from analysi.agentic_orchestration.langgraph.kea.phase1.matcher import Phase1Matcher
from analysi.agentic_orchestration.langgraph.kea.phase1.substeps import (
    create_analyze_gaps_substep,
    create_compose_runbook_substep,
    create_extract_sections_substep,
    create_fix_runbook_substep,
    create_select_strategy_substep,
)
from analysi.agentic_orchestration.langgraph.kea.phase1.validators import (
    validate_runbook_output,
)
from analysi.agentic_orchestration.langgraph.skills.store import ResourceStore
from analysi.agentic_orchestration.langgraph.substep.executor import execute_substep
from analysi.agentic_orchestration.observability import WorkflowGenerationStage
from analysi.agentic_orchestration.workspace import get_system_prompt_for_stage
from analysi.config.logging import get_logger

logger = get_logger(__name__)

# =============================================================================
# System Prompt - Reused from workspace.py for consistency with SDK approach
# =============================================================================

PHASE1_SYSTEM_PROMPT = get_system_prompt_for_stage(
    WorkflowGenerationStage.RUNBOOK_GENERATION
)


class Phase1State(TypedDict):
    """State for Runbook Matching graph."""

    # Input
    alert: dict[str, Any]
    repository_path: str

    # Scoring results
    matches: list[dict[str, Any]]
    top_score: float
    has_exact_rule: bool

    # Confidence
    confidence: ConfidenceLevel | None

    # Composition state (only for composition path)
    gaps: dict[str, Any] | None
    strategy: dict[str, Any] | None
    extractions: dict[str, Any] | None

    # Output
    runbook: str | None
    composition_metadata: dict[str, Any] | None

    # Validation tracking (for fix_runbook loop)
    validation_errors: list[str] | None
    fix_retries: int

    # Dependencies (injected)
    store: ResourceStore | None


# =============================================================================
# Match Path Nodes (Deterministic - no SkillsIR)
# =============================================================================


async def load_and_score_node(state: Phase1State) -> dict:
    """Load runbook index and calculate match scores.

    This is deterministic - uses Phase1Matcher for scoring.
    No SkillsIR needed. Supports both filesystem and DB-backed modes.
    """
    store = state.get("store")
    if store:
        matcher = await Phase1Matcher.from_store(store)
    else:
        matcher = Phase1Matcher(state["repository_path"])
        matcher.load_index()

    alert = state["alert"]

    # Find matches
    matches = matcher.find_matches(alert, top_n=5)

    # Extract scoring info
    top_score = matches[0]["score"] if matches else 0
    has_exact_rule = any(
        "exact_detection_rule" in m.get("explanation", {}).get("score_breakdown", {})
        for m in matches
    )

    # Determine confidence
    confidence = determine_confidence(top_score, has_exact_rule)

    return {
        "matches": matches,
        "top_score": top_score,
        "has_exact_rule": has_exact_rule,
        "confidence": confidence,
    }


async def fetch_runbook_node(state: Phase1State) -> dict:
    """Fetch the top matched runbook with WikiLink expansion.

    This is deterministic - just file read + expansion.
    No SkillsIR needed. Supports both filesystem and DB-backed modes.
    """
    store = state.get("store")
    matches = state["matches"]

    if not matches:
        return {"runbook": None}

    top_match = matches[0]
    filename = top_match["runbook"]["filename"]

    if store:
        matcher = await Phase1Matcher.from_store(store)
        runbook_content = await matcher.get_runbook_content_async(
            filename, expand_wikilinks=True
        )
    else:
        matcher = Phase1Matcher(state["repository_path"])
        runbook_content = matcher.get_runbook_content(filename, expand_wikilinks=True)

    return {"runbook": runbook_content}


# =============================================================================
# Composition Path Nodes (LLM + SkillsIR via SubStep executor)
# =============================================================================


def make_analyze_gaps_node(llm):
    """Create analyze_gaps node using SubStep executor with SkillsIR."""

    async def analyze_gaps_node(state: Phase1State) -> dict:
        """Analyze gaps using SubStep pattern: SkillsIR → LLM → Validate → Loop."""
        substep = create_analyze_gaps_substep()
        store = state["store"]
        assert store is not None, "store is required for composition path"

        # Build state for SubStep
        substep_state = {
            "alert": json.dumps(state["alert"], default=str),
            "top_match": json.dumps(state["matches"][0], default=str)
            if state["matches"]
            else "None",
            "score": state["top_score"],
        }

        result = await execute_substep(
            substep=substep,
            state=substep_state,
            store=store,
            llm=llm,
            system_prompt=PHASE1_SYSTEM_PROMPT,
        )

        return {"gaps": _parse_json_safe(result.output)}

    return analyze_gaps_node


def make_select_strategy_node(llm):
    """Create select_strategy node using SubStep executor with SkillsIR."""

    async def select_strategy_node(state: Phase1State) -> dict:
        """Select strategy using SubStep pattern: SkillsIR → LLM → Validate → Loop."""
        substep = create_select_strategy_substep()
        store = state["store"]
        assert store is not None, "store is required for composition path"

        # Build state for SubStep
        substep_state = {
            "alert": json.dumps(state["alert"], default=str),
            "gaps": json.dumps(state["gaps"], default=str),
            "available_runbooks": [m["runbook"]["filename"] for m in state["matches"]],
        }

        result = await execute_substep(
            substep=substep,
            state=substep_state,
            store=store,
            llm=llm,
            system_prompt=PHASE1_SYSTEM_PROMPT,
        )

        return {"strategy": _parse_json_safe(result.output)}

    return select_strategy_node


def make_extract_sections_node(llm):
    """Create extract_sections node using SubStep executor with SkillsIR."""

    async def extract_sections_node(state: Phase1State) -> dict:
        """Extract sections using SubStep pattern: SkillsIR → LLM → Validate → Loop."""
        substep = create_extract_sections_substep()
        store = state["store"]
        assert store is not None, "store is required for composition path"

        # Build state for SubStep
        strategy = state.get("strategy") or {}
        substep_state = {
            "strategy": json.dumps(state["strategy"], default=str),
            "sources": json.dumps(strategy.get("sources", []), default=str),
            "gaps": json.dumps(state["gaps"], default=str),
        }

        result = await execute_substep(
            substep=substep,
            state=substep_state,
            store=store,
            llm=llm,
            system_prompt=PHASE1_SYSTEM_PROMPT,
        )

        return {"extractions": _parse_json_safe(result.output)}

    return extract_sections_node


def make_compose_runbook_node(llm):
    """Create compose_runbook node using SubStep executor with SkillsIR."""

    async def compose_runbook_node(state: Phase1State) -> dict:
        """Compose runbook using SubStep pattern: SkillsIR → LLM → Validate → Loop."""
        substep = create_compose_runbook_substep()
        store = state["store"]
        assert store is not None, "store is required for composition path"

        extractions = state.get("extractions") or {}

        # Build state for SubStep
        substep_state = {
            "alert": json.dumps(state["alert"], default=str),
            "extractions": json.dumps(extractions.get("extractions", []), default=str),
            "remaining_gaps": json.dumps(
                extractions.get("remaining_gaps", []), default=str
            ),
        }

        result = await execute_substep(
            substep=substep,
            state=substep_state,
            store=store,
            llm=llm,
            system_prompt=PHASE1_SYSTEM_PROMPT,
        )

        runbook = result.output

        # Run validation immediately to populate validation_errors
        validation_result = validate_runbook_output(runbook) if runbook else None
        validation_errors = (
            validation_result.errors
            if validation_result and not validation_result.passed
            else []
        )

        return {
            "runbook": runbook,
            "composition_metadata": {
                "gaps": state["gaps"],
                "strategy": state["strategy"],
                "extractions": state["extractions"],
            },
            "validation_errors": validation_errors,
        }

    return compose_runbook_node


def make_fix_runbook_node(llm):
    """Create fix_runbook node using SubStep executor with SkillsIR."""

    async def fix_runbook_node(state: Phase1State) -> dict:
        """Fix runbook using SubStep pattern: SkillsIR → LLM → Validate → Loop."""
        substep = create_fix_runbook_substep()
        store = state["store"]
        assert store is not None, "store is required for composition path"

        # Build state for SubStep
        substep_state = {
            "runbook": state["runbook"] or "",
            "errors": json.dumps(state.get("validation_errors") or [], default=str),
        }

        result = await execute_substep(
            substep=substep,
            state=substep_state,
            store=store,
            llm=llm,
            system_prompt=PHASE1_SYSTEM_PROMPT,
        )

        runbook = result.output

        # Run validation immediately to populate validation_errors
        validation_result = validate_runbook_output(runbook) if runbook else None
        validation_errors = (
            validation_result.errors
            if validation_result and not validation_result.passed
            else []
        )

        # Increment retry count
        current_retries = state.get("fix_retries", 0)

        return {
            "runbook": runbook,
            "fix_retries": current_retries + 1,
            "validation_errors": validation_errors,
        }

    return fix_runbook_node


# Maximum fix retries to prevent infinite loops
MAX_FIX_RETRIES = 2


# =============================================================================
# Routing
# =============================================================================


def route_after_compose(
    state: Phase1State,
) -> Literal["end", "fix_runbook"]:
    """Route after compose_runbook based on validation.

    Validation is already done in compose_runbook node and stored in validation_errors.

    If valid (no errors) -> END
    If invalid -> fix_runbook
    """
    errors = state.get("validation_errors") or []

    if not errors:
        return "end"

    return "fix_runbook"


def route_after_fix(
    state: Phase1State,
) -> Literal["end", "fix_runbook"]:
    """Route after fix_runbook based on validation.

    Validation is already done in fix_runbook node and stored in validation_errors.

    If valid -> END
    If still invalid and retries remain -> fix_runbook
    If max retries reached -> END (with whatever we have)
    """
    errors = state.get("validation_errors") or []

    if not errors:
        return "end"

    # Check retry limit
    if state.get("fix_retries", 0) >= MAX_FIX_RETRIES:
        return "end"

    return "fix_runbook"


def route_by_confidence(state: Phase1State) -> Literal["fetch_runbook", "analyze_gaps"]:
    """Route based on confidence level.

    HIGH/VERY_HIGH -> match path (fetch_runbook)
    MEDIUM/LOW/VERY_LOW -> composition path (analyze_gaps)
    """
    confidence = state.get("confidence")
    if confidence and should_use_match_path(confidence):
        return "fetch_runbook"
    return "analyze_gaps"


# =============================================================================
# Graph Building
# =============================================================================


def build_phase1_graph(llm, store: ResourceStore | None = None) -> CompiledStateGraph:
    """Build Runbook Matching LangGraph.

    Architecture:
    - Match path (HIGH/VERY_HIGH): deterministic fetch
    - Composition path (MEDIUM/LOW/VERY_LOW): 5 SubSteps with SkillsIR
      - analyze_gaps -> select_strategy -> extract_sections -> compose_runbook
      - compose_runbook validates output; if invalid -> fix_runbook (up to 2 retries)

    Args:
        llm: LangChain LLM for composition steps.
        store: ResourceStore for SkillsIR context retrieval.

    Returns:
        Compiled LangGraph.
    """
    # Create graph
    graph = StateGraph(Phase1State)

    # Add nodes
    # Match path (deterministic)
    graph.add_node("load_and_score", load_and_score_node)
    graph.add_node("fetch_runbook", fetch_runbook_node)

    # Composition path (SubStep executor with SkillsIR)
    graph.add_node("analyze_gaps", make_analyze_gaps_node(llm))
    graph.add_node("select_strategy", make_select_strategy_node(llm))
    graph.add_node("extract_sections", make_extract_sections_node(llm))
    graph.add_node("compose_runbook", make_compose_runbook_node(llm))
    graph.add_node("fix_runbook", make_fix_runbook_node(llm))

    # Set entry point
    graph.set_entry_point("load_and_score")

    # Add conditional routing after scoring
    graph.add_conditional_edges(
        "load_and_score",
        route_by_confidence,
        {
            "fetch_runbook": "fetch_runbook",
            "analyze_gaps": "analyze_gaps",
        },
    )

    # Match path -> END
    graph.add_edge("fetch_runbook", END)

    # Composition path: gaps -> strategy -> extract -> compose
    graph.add_edge("analyze_gaps", "select_strategy")
    graph.add_edge("select_strategy", "extract_sections")
    graph.add_edge("extract_sections", "compose_runbook")

    # compose_runbook -> validate -> END or fix_runbook
    graph.add_conditional_edges(
        "compose_runbook",
        route_after_compose,
        {
            "end": END,
            "fix_runbook": "fix_runbook",
        },
    )

    # fix_runbook -> validate -> END or loop back to fix_runbook
    graph.add_conditional_edges(
        "fix_runbook",
        route_after_fix,
        {
            "end": END,
            "fix_runbook": "fix_runbook",
        },
    )

    return graph.compile()


async def run_phase1(
    alert: dict[str, Any],
    llm,
    store: ResourceStore,
    repository_path: str,
) -> dict[str, Any]:
    """Run runbook matching/composition.

    This is the main entry point for the Runbook Matching stage.

    Args:
        alert: alert dict.
        llm: LangChain LLM instance.
        store: ResourceStore for SkillsIR.
        repository_path: Path to runbook repository.

    Returns:
        Dict with:
        - matching_report: Dict conforming to SDK matching-report.json schema
        - runbook: The matched or composed runbook content
        - Internal fields for debugging (matches, gaps, strategy, etc.)
    """
    # Build graph
    compiled_graph = build_phase1_graph(llm, store)

    # Prepare initial state
    initial_state: Phase1State = {
        "alert": alert,
        "repository_path": repository_path,
        "matches": [],
        "top_score": 0,
        "has_exact_rule": False,
        "confidence": None,
        "gaps": None,
        "strategy": None,
        "extractions": None,
        "runbook": None,
        "composition_metadata": None,
        "validation_errors": None,
        "fix_retries": 0,
        "store": store,
    }

    # Run graph
    final_state = await compiled_graph.ainvoke(initial_state)

    # Build matching_report conforming to SDK schema
    confidence = final_state.get("confidence")
    top_score = final_state.get("top_score", 0)
    matches = final_state.get("matches", [])
    composition_metadata = final_state.get("composition_metadata")
    timestamp = datetime.now(UTC).isoformat()

    # Determine if this was a match or composition based on which path was taken
    # Composition path sets composition_metadata, match path does not
    is_composition = composition_metadata is not None

    if is_composition:
        # Get composition sources from strategy if available
        strategy = final_state.get("strategy") or {}
        sources = strategy.get("sources", [])
        # Extract just filenames from sources
        source_filenames = [
            s.get("filename", s) if isinstance(s, dict) else s for s in sources
        ]

        matching_report = {
            "confidence": confidence.value if confidence else "LOW",
            "score": int(top_score),
            "decision": "composed",
            "composed_runbook": "composed-runbook.md",
            "composition_sources": source_filenames,
            "timestamp": timestamp,
        }
    else:
        # Match path - get matched runbook filename
        matched_runbook = matches[0]["runbook"]["filename"] if matches else None

        matching_report = {
            "confidence": confidence.value if confidence else "HIGH",
            "score": int(top_score),
            "decision": "matched",
            "matched_runbook": matched_runbook,
            "timestamp": timestamp,
        }

    # Persist composed runbook to store and update the index.
    if is_composition and final_state.get("runbook") and store:
        try:
            alert_title = alert.get("title", "unknown")
            slug = re.sub(r"[^a-z0-9]+", "-", alert_title.lower()).strip("-")[:60]
            ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
            filename = f"{slug}-{ts}.md"
            path = f"repository/{filename}"

            written = await store.write_document_async(
                "runbooks-manager",
                path,
                final_state["runbook"],
                metadata={
                    "source": "phase1_composition",
                    "alert_title": alert_title,
                    "composition_sources": matching_report.get(
                        "composition_sources", []
                    ),
                    "timestamp": timestamp,
                },
            )
            if written:
                matching_report["composed_runbook"] = filename

                # Update index table with new runbook entry
                index_data = await store.read_table_async(
                    "runbooks-manager", "index/all_runbooks"
                )
                if isinstance(index_data, list):
                    new_entry = {
                        "filename": filename,
                        "title": alert_title,
                        "alert_type": alert.get("alert_type", ""),
                        "source_category": next(
                            (
                                lbl.split(":", 1)[1]
                                for lbl in alert.get("metadata", {}).get("labels", [])
                                if isinstance(lbl, str)
                                and lbl.startswith("source_category:")
                            ),
                            alert.get("source_category", ""),  # fallback for transition
                        ),
                        "source": "composed",
                        "timestamp": timestamp,
                    }
                    index_data.append(new_entry)
                    await store.write_table_async(
                        "runbooks-manager", "index/all_runbooks", index_data
                    )
        except Exception:
            logger.warning("composed_runbook_persist_failed", exc_info=True)

    # Return relevant fields
    return {
        # SDK contract fields
        "matching_report": matching_report,
        "runbook": final_state.get("runbook"),
        # Internal debugging fields
        "matches": matches,
        "top_score": top_score,
        "has_exact_rule": final_state.get("has_exact_rule", False),
        "confidence": confidence,
        "gaps": final_state.get("gaps"),
        "strategy": final_state.get("strategy"),
        "extractions": final_state.get("extractions"),
        "composition_metadata": composition_metadata,
        "fix_retries": final_state.get("fix_retries", 0),
    }


def _extract_json_from_text(text: str) -> str:
    """Extract JSON from text, handling markdown code blocks.

    LLMs often wrap JSON in markdown code blocks like:
    ```json
    {"key": "value"}
    ```
    """
    import re

    text = text.strip()

    # Try to extract from markdown code block (```json ... ``` or ``` ... ```)
    code_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
    match = re.search(code_block_pattern, text)
    if match:
        return match.group(1).strip()

    return text


def _parse_json_safe(text: str) -> dict[str, Any] | None:
    """Parse JSON from text, handling markdown code blocks. Returns None on failure."""
    if not text:
        return None
    try:
        json_str = _extract_json_from_text(text)
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None
