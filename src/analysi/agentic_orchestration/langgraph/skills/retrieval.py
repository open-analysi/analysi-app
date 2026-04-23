"""SkillsIR retrieval using LangGraph."""

import json
import time
from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from analysi.agentic_orchestration.langgraph.skills.context import (
    RetrievalDecision,
    SkillContext,
)
from analysi.agentic_orchestration.langgraph.skills.prompts import (
    format_retrieval_prompt,
)
from analysi.agentic_orchestration.langgraph.skills.store import ResourceStore
from analysi.agentic_orchestration.logging_context import get_skillsir_logger

# Configuration
MAX_ITERATIONS = 5
MAX_STRUCTURED_OUTPUT_RETRIES = 2
MAX_FILES_PER_REQUEST = 3
DEFAULT_TOKEN_LIMIT = 50000


class RetrievalState(TypedDict):
    """State for the SkillsIR retrieval graph."""

    # Inputs (set once at start)
    objective: str
    task_input: str  # JSON string
    initial_skills: list[str]

    # Context (accumulated)
    context: SkillContext

    # Control flow
    iteration: int
    decision: RetrievalDecision | None

    # Dependencies (injected)
    store: ResourceStore


async def init_node(state: RetrievalState) -> dict:
    """Initialize context with registry, trees, and SKILL.md files.

    This is the entry point of the graph. It:
    1. Loads the skill registry (all skill descriptions)
    2. Loads file trees for initial skills
    3. Loads SKILL.md for each initial skill
    """
    logger = get_skillsir_logger()
    store = state["store"]
    initial_skills = state["initial_skills"]
    objective = state["objective"]

    logger.info(
        "starting_retrieval",
        objective=objective[:80],
        truncated=len(objective) > 80,
    )
    logger.info("initial_skills", initial_skills=initial_skills)

    # Use async methods for database-backed stores
    registry = await store.list_skills_async()
    trees = {}
    for skill in initial_skills:
        trees[skill] = await store.tree_async(skill)

    # Create context with registry
    context = SkillContext(
        registry=registry,
        trees=trees,
        token_limit=DEFAULT_TOKEN_LIMIT,
    )

    logger.info("registry_loaded", skills_count=len(context.registry))

    # Load SKILL.md for each initial skill
    for skill in initial_skills:
        content = await store.read_async(skill, "SKILL.md")
        if content:
            context.add(skill, "SKILL.md", content)
            logger.info(
                "loaded_skillmd_tokens_total",
                skill=skill,
                token_count=context.token_count,
            )

    return {
        "context": context,
        "iteration": 0,
        "decision": None,
    }


def make_check_enough_node(llm):
    """Create check_enough node with LLM bound.

    We need this factory to properly bind the LLM while keeping
    the async function signature that LangGraph expects.
    """

    async def check_enough_node(state: RetrievalState) -> dict:
        """Ask LLM if it has enough context, get structured RetrievalDecision."""
        context = state["context"]
        objective = state["objective"]
        task_input = state["task_input"]
        iteration = state["iteration"]

        logger = get_skillsir_logger(iteration=iteration)
        logger.info(
            "checking_context_sufficiency",
            token_count=context.token_count,
            token_limit=context.token_limit,
        )

        # Format prompt
        prompt = format_retrieval_prompt(
            objective=objective,
            task_input=task_input,
            context=context,
        )

        # Get structured output from LLM with retry + safe fallback
        start_time = time.time()
        decision = None
        last_error = None

        for attempt in range(1, MAX_STRUCTURED_OUTPUT_RETRIES + 1):
            try:
                structured_llm = llm.with_structured_output(RetrievalDecision)
                decision = await structured_llm.ainvoke(prompt)
                break
            except Exception as e:
                last_error = e
                logger.warning(
                    "retrieval_decision_attempt_failed",
                    attempt=attempt,
                    max_retries=MAX_STRUCTURED_OUTPUT_RETRIES,
                    error_type=type(e).__name__,
                    error=str(e),
                )

        if decision is None:
            logger.warning(
                "all_retrieval_decision_attempts_failed_using_safe_default",
                last_error=str(last_error),
            )
            decision = RetrievalDecision(has_enough=True)

        elapsed_ms = (time.time() - start_time) * 1000

        # Log decision at INFO level for visibility
        if decision.has_enough:
            logger.info("llm_decided_has_enough_context_took_ms", elapsed_ms=elapsed_ms)
        else:
            requested_files = [f"{r.skill}/{r.path}" for r in decision.needs]
            logger.info(
                "llm_decided_needs_more_files",
                files_needed=len(decision.needs),
                elapsed_ms=round(elapsed_ms),
                requested_files=requested_files,
            )

        return {
            "decision": decision,
            "iteration": iteration + 1,
        }

    return check_enough_node


async def load_files_node(state: RetrievalState) -> dict:
    """Load requested files into context with WikiLink expansion.

    Files are loaded with WikiLinks (![[path/to/file.md]]) automatically
    expanded inline. This ensures the LLM receives fully self-contained
    content without needing to request referenced files separately.
    """
    logger = get_skillsir_logger(iteration=state.get("iteration", 0) - 1)
    store = state["store"]
    context = state["context"]
    decision = state["decision"]

    if not decision or decision.has_enough:
        return {}

    # Load requested files with WikiLink expansion (up to MAX_FILES_PER_REQUEST)
    files_loaded = 0
    total_wikilinks_expanded = 0
    for req in decision.needs[:MAX_FILES_PER_REQUEST]:
        # Use read_expanded_async() to automatically expand WikiLinks inline
        content, wikilinks_expanded = await store.read_expanded_async(
            req.skill, req.path
        )
        if content:
            if context.add(req.skill, req.path, content):
                files_loaded += 1
                total_wikilinks_expanded += wikilinks_expanded
                logger.info(
                    "loaded_file",
                    skill=req.skill,
                    path=req.path,
                    token_count=context.token_count,
                    token_limit=context.token_limit,
                    wikilinks_expanded=wikilinks_expanded,
                )
            else:
                logger.warning(
                    "token_budget_exceeded_skipping_file",
                    skill=req.skill,
                    path=req.path,
                    token_count=context.token_count,
                    token_limit=context.token_limit,
                )
                break
        else:
            context.mark_not_found(req.skill, req.path)
            logger.warning("file_not_found", skill=req.skill, path=req.path)

    if files_loaded > 0:
        expansion_summary = (
            f" ({total_wikilinks_expanded} WikiLinks expanded)"
            if total_wikilinks_expanded > 0
            else ""
        )
        logger.info(
            "loaded_files_this_iteration",
            files_loaded=files_loaded,
            expansion_summary=expansion_summary,
        )

    return {"context": context}


def should_continue(state: RetrievalState) -> Literal["check_enough", "finish"]:
    """Determine if we should continue iterating or finish."""
    decision = state.get("decision")
    iteration = state.get("iteration", 0)

    # Finish if LLM says it has enough
    if decision and decision.has_enough:
        return "finish"

    # Finish if we've reached max iterations
    if iteration >= MAX_ITERATIONS:
        logger = get_skillsir_logger(iteration=iteration - 1)
        logger.warning(
            "max_iterations_reached_stopping_retrieval", MAX_ITERATIONS=MAX_ITERATIONS
        )
        return "finish"

    # Continue if decision requested more files
    if decision and decision.needs:
        return "check_enough"

    # First iteration - go to check_enough
    if decision is None:
        return "check_enough"

    # No files requested but not enough - weird state, finish
    return "finish"


def build_retrieval_graph(llm) -> CompiledStateGraph:
    """Build the SkillsIR retrieval graph.

    Args:
        llm: LangChain ChatAnthropic instance for LLM calls.

    Returns:
        Compiled LangGraph StateGraph.
    """
    # Create graph
    graph = StateGraph(RetrievalState)

    # Add nodes
    graph.add_node("init", init_node)
    graph.add_node("check_enough", make_check_enough_node(llm))
    graph.add_node("load_files", load_files_node)

    # Set entry point
    graph.set_entry_point("init")

    # Add edges
    graph.add_edge("init", "check_enough")
    graph.add_conditional_edges(
        "check_enough",
        should_continue,
        {
            "check_enough": "load_files",  # Need more files -> load them -> check again
            "finish": END,
        },
    )
    graph.add_edge("load_files", "check_enough")

    return graph.compile()


async def retrieve(
    store: ResourceStore,
    initial_skills: list[str],
    task_input: dict,
    objective: str,
    llm,
) -> SkillContext:
    """Progressive retrieval: LLM decides what's needed, code loads it.

    This is the main entry point for SkillsIR. It runs the LangGraph
    retrieval loop until the LLM indicates it has enough context.

    Args:
        store: ResourceStore for accessing skill files.
        initial_skills: List of skill names to start with (from agent.md frontmatter).
        task_input: The input for the task (will be JSON-serialized).
        objective: What we're trying to accomplish.
        llm: LangChain ChatAnthropic instance.

    Returns:
        SkillContext with all loaded content.
    """
    logger = get_skillsir_logger()
    start_time = time.time()

    # Build graph
    compiled_graph = build_retrieval_graph(llm)

    # Prepare initial state
    initial_state: RetrievalState = {
        "objective": objective,
        "task_input": json.dumps(task_input, indent=2),
        "initial_skills": initial_skills,
        "context": SkillContext(),  # Will be replaced by init_node
        "iteration": 0,
        "decision": None,
        "store": store,
    }

    # Run graph
    final_state = await compiled_graph.ainvoke(initial_state)

    # Calculate total time
    elapsed_sec = time.time() - start_time
    context = final_state["context"]
    iterations = final_state["iteration"]

    # Log completion summary
    loaded_files = sum(len(files) for files in context.loaded.values())
    logger.info(
        "retrieval_complete",
        iterations=iterations,
        files_loaded=loaded_files,
        token_count=context.token_count,
        elapsed_sec=round(elapsed_sec, 1),
    )

    return context
