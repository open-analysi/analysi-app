---
name: agent-to-langgraph
description: |
  Convert Claude Code agents (markdown files with skills) into LangGraph implementations.
  Takes a source agent .md file and its referenced skills, then produces a programmatic
  LangGraph reimplementation with SkillsIR for context retrieval.

  Use when:
  - You need to convert a Claude Code agent to a programmatic LangGraph workflow
  - You want to optimize an agent's execution with structured graph control flow
  - You need better observability, testing, or cost control than agent SDK provides

  <example>
  User: "Convert runbook-match-agent.md to LangGraph"
  Agent: Analyzes the agent, identifies workflow structure, creates graph.py with nodes
  </example>
skills: cy-language-programming
model: sonnet
color: blue
---

# Agent-to-LangGraph Converter

Convert Claude Code agents into programmatic LangGraph implementations while preserving behavior and aligning with SDK contracts.

## Why Convert Agents to LangGraph?

| Aspect | Claude Code Agent | LangGraph Implementation |
|--------|------------------|--------------------------|
| Execution | Claude Agent SDK interprets .md | Python code with explicit graph |
| Control Flow | Implicit in markdown instructions | Explicit nodes and edges |
| Context Retrieval | Skill tool loads files on demand | SkillsIR progressive retrieval |
| Testing | End-to-end only | Unit tests per node |
| Observability | Limited to SDK callbacks | Full state visibility |
| Cost | LLM decides everything | Deterministic paths where possible |

## Conversion Process Overview

```
┌─────────────────────────────────────────────────────────────┐
│ 1. ANALYZE SOURCE AGENT                                     │
│    - Parse frontmatter (skills, model, description)         │
│    - Identify workflow phases/steps from markdown structure │
│    - Map skills to retrieval needs                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. DESIGN GRAPH STRUCTURE                                   │
│    - Identify deterministic vs LLM-based nodes              │
│    - Design state schema (TypedDict)                        │
│    - Plan routing logic (conditional edges)                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. CREATE SUBSTEPS                                          │
│    - Define SubStep for each LLM-based node                 │
│    - Create Pydantic models for structured output           │
│    - Write validators for output verification               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. IMPLEMENT GRAPH                                          │
│    - Build StateGraph with nodes and edges                  │
│    - Add conditional routing                                │
│    - Implement retry/fix loops where needed                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. ALIGN SDK CONTRACT                                       │
│    - Use same system prompt as SDK                          │
│    - Match output format (e.g., matching-report.json)       │
│    - Document sync requirements in CLAUDE.md                │
└─────────────────────────────────────────────────────────────┘
```

## Step 1: Analyze Source Agent

### Parse Frontmatter

Extract key configuration from the agent's YAML frontmatter:

```yaml
---
name: runbook-match-agent
description: Match OCSF alerts to existing runbooks...
skills: runbooks-manager, cybersecurity-analyst  # <- Skills to map to SkillsIR
model: sonnet
color: purple
---
```

**Key fields:**
- `skills`: These become the initial skills for SkillsIR retrieval
- `model`: Determines LLM to use in LangGraph
- `description`: Helps understand the agent's purpose

### Identify Workflow Structure

Look for process steps in the agent markdown:

```markdown
## Process

### Step 1: Load and Score
Load the runbook index and calculate match scores...

### Step 2: Route by Confidence
If HIGH/VERY_HIGH confidence → return match
If MEDIUM/LOW → composition path...

### Step 3: Compose Runbook
Analyze gaps, select strategy, compose...
```

**Map to graph nodes:**
- Sequential steps → linear edges
- Conditional logic → conditional edges
- Retry/fix instructions → loops

### Identify Node Types

| Pattern in Agent | Node Type | Implementation |
|------------------|-----------|----------------|
| "Load/Read/Fetch X" | Deterministic | Python function, no LLM |
| "Calculate/Score/Match" | Deterministic | Algorithm, no LLM |
| "Analyze/Assess/Evaluate" | LLM-based | SubStep with SkillsIR |
| "Generate/Compose/Create" | LLM-based | SubStep with SkillsIR |
| "Fix/Correct/Repair" | LLM-based | SubStep in retry loop |
| "If X then Y else Z" | Routing | Conditional edge |

## Step 2: Design Graph Structure

### State Schema

Create a TypedDict that captures all data flowing through the graph:

```python
from typing import Any, TypedDict

class Phase1State(TypedDict):
    # Input
    alert: dict[str, Any]
    repository_path: str

    # Intermediate results
    matches: list[dict[str, Any]]
    top_score: float
    confidence: str | None

    # Composition state (optional path)
    gaps: dict[str, Any] | None
    strategy: dict[str, Any] | None

    # Output
    runbook: str | None

    # Control flow
    validation_errors: list[str] | None
    fix_retries: int

    # Dependencies (injected)
    store: ResourceStore | None
```

**Guidelines:**
- Include ALL data that flows between nodes
- Use `| None` for optional fields (not all paths populate them)
- Include control flow fields (retry counters, validation errors)
- Inject dependencies via state (store, llm reference)

### Routing Logic

Map agent's conditional logic to routing functions:

```python
def route_by_confidence(state: Phase1State) -> Literal["fetch_runbook", "analyze_gaps"]:
    """Route based on confidence level."""
    confidence = state.get("confidence")
    if confidence in ("HIGH", "VERY_HIGH"):
        return "fetch_runbook"  # Match path
    return "analyze_gaps"  # Composition path

def route_after_compose(state: Phase1State) -> Literal["end", "fix_runbook"]:
    """Route based on validation."""
    errors = state.get("validation_errors") or []
    if not errors:
        return "end"
    return "fix_runbook"
```

## Step 3: Create SubSteps

### SubStep Pattern

Each LLM-based node should use the SubStep pattern with SkillsIR:

```python
from analysi.agentic_orchestration.langgraph.substep import SubStep

def create_analyze_gaps_substep() -> SubStep:
    return SubStep(
        name="analyze_gaps",
        objective="Identify gaps between top runbook match and alert",  # For SkillsIR
        skills=["runbooks-manager"],  # Skills to retrieve context from
        task_prompt="""Analyze the gap between the matched runbook and the alert.

Alert: {alert}
Top Match: {top_match}

{context}  # SkillsIR injects retrieved context here

Identify what's missing...""",
        validator=validate_gap_analysis,
        needs_context=True,  # Enable SkillsIR retrieval
        output_schema=GapAnalysisOutput,  # Optional: Pydantic model for structured output
    )
```

### Pydantic Models for Structured Output

When you need structured JSON output, define Pydantic models:

```python
from pydantic import BaseModel, Field
from typing import Literal

class Gap(BaseModel):
    category: str = Field(description="Category of the gap")
    description: str = Field(description="What's missing")
    severity: Literal["high", "medium", "low"]

class GapAnalysisOutput(BaseModel):
    gaps: list[Gap]
    coverage_assessment: str
```

**Benefits:**
- Type-safe LLM output
- Automatic validation
- Clear schema for testing

### Validators

Create validators for each SubStep output:

```python
from analysi.agentic_orchestration.langgraph.substep.definition import ValidationResult

def validate_gap_analysis(output: str) -> ValidationResult:
    """Validate gap analysis output."""
    try:
        data = json.loads(output)
        if not data.get("gaps"):
            return ValidationResult(
                passed=False,
                errors=["Missing 'gaps' field"],
            )
        return ValidationResult(passed=True)
    except json.JSONDecodeError as e:
        return ValidationResult(passed=False, errors=[f"Invalid JSON: {e}"])
```

**Validation can request more context:**
```python
return ValidationResult(
    passed=False,
    errors=["Need more attack details"],
    needs_more_context=True,
    context_hint="Load attack pattern references for this alert type",
)
```

## Step 4: Implement Graph

### Graph Building

```python
from langgraph.graph import END, StateGraph

def build_phase1_graph(llm, store: ResourceStore | None = None) -> StateGraph:
    graph = StateGraph(Phase1State)

    # Add deterministic nodes
    graph.add_node("load_and_score", load_and_score_node)
    graph.add_node("fetch_runbook", fetch_runbook_node)

    # Add LLM-based nodes (SubStep executors)
    graph.add_node("analyze_gaps", make_analyze_gaps_node(llm))
    graph.add_node("select_strategy", make_select_strategy_node(llm))
    graph.add_node("compose_runbook", make_compose_runbook_node(llm))
    graph.add_node("fix_runbook", make_fix_runbook_node(llm))

    # Entry point
    graph.set_entry_point("load_and_score")

    # Conditional routing
    graph.add_conditional_edges(
        "load_and_score",
        route_by_confidence,
        {
            "fetch_runbook": "fetch_runbook",
            "analyze_gaps": "analyze_gaps",
        },
    )

    # Linear edges
    graph.add_edge("fetch_runbook", END)
    graph.add_edge("analyze_gaps", "select_strategy")
    graph.add_edge("select_strategy", "compose_runbook")

    # Validation loop
    graph.add_conditional_edges(
        "compose_runbook",
        route_after_compose,
        {"end": END, "fix_runbook": "fix_runbook"},
    )
    graph.add_conditional_edges(
        "fix_runbook",
        route_after_fix,
        {"end": END, "fix_runbook": "fix_runbook"},  # Self-loop for retries
    )

    return graph.compile()
```

### Node Factory Pattern

For LLM-based nodes, use factories that bind the LLM:

```python
def make_analyze_gaps_node(llm):
    """Create analyze_gaps node with LLM bound."""

    async def analyze_gaps_node(state: Phase1State) -> dict:
        substep = create_analyze_gaps_substep()
        store = state["store"]

        substep_state = {
            "alert": json.dumps(state["alert"], default=str),
            "top_match": json.dumps(state["matches"][0], default=str),
        }

        result = await execute_substep(
            substep=substep,
            state=substep_state,
            store=store,
            llm=llm,
            system_prompt=SYSTEM_PROMPT,  # Same as SDK!
        )

        return {"gaps": parse_json(result.output)}

    return analyze_gaps_node
```

## Step 5: Align SDK Contract

### System Prompt

**CRITICAL:** Use the same system prompt as the SDK to maintain behavior parity.

```python
from analysi.agentic_orchestration.workspace import get_system_prompt_for_stage
from analysi.agentic_orchestration.observability import WorkflowGenerationStage

SYSTEM_PROMPT = get_system_prompt_for_stage(WorkflowGenerationStage.RUNBOOK_GENERATION)
# Returns: "Expert Cyber Security Analyst specialized in..."
```

Pass this to ALL LLM calls:
```python
result = await execute_substep(
    substep=substep,
    state=substep_state,
    store=store,
    llm=llm,
    system_prompt=SYSTEM_PROMPT,  # Always include!
)
```

### Output Format

If the SDK expects specific output files, generate equivalent data:

```python
# SDK expects: matching-report.json
matching_report = {
    "confidence": confidence.value,
    "score": int(top_score),
    "decision": "composed" if is_composition else "matched",
    "composed_runbook": "composed-runbook.md" if is_composition else None,
    "matched_runbook": matched_filename if not is_composition else None,
    "timestamp": datetime.now(UTC).isoformat(),
}

return {
    "matching_report": matching_report,  # SDK contract
    "runbook": final_state.get("runbook"),  # Content
    # ... internal fields for debugging
}
```

### Document Sync Requirements

Create a CLAUDE.md in your LangGraph directory:

```markdown
# Phase 1: LangGraph Reimplementation

## Architecture: Programmatic Reimplementation of Agent

**This LangGraph is a programmatic reimplementation of `agent-name.md`.**

| Aspect | Claude Code Agent | LangGraph |
|--------|------------------|-----------|
| Source | agents/agent-name.md | This directory |
| Skills | Frontmatter: `skills: X, Y` | Hardcoded in substeps.py |

## Keeping Them In Sync

When updating either implementation:
- [ ] Check skills configuration
- [ ] Check routing thresholds
- [ ] Check output format
- [ ] Update BOTH if needed
```

## SkillsIR Best Practices

### Retrieval Prompt Guidance

SkillsIR works best when the prompt clearly guides retrieval:

```python
RETRIEVAL_PROMPT = """
## How Skills Are Organized

| Directory | Purpose | When to Load |
|-----------|---------|--------------|
| SKILL.md | Overview, navigation | Always (auto-loaded) |
| references/ | Specs, formats | When you need exact rules |
| templates/ | Patterns to follow | When creating new artifacts |
| repository/ | Production artifacts | When adapting existing work |

## Instructions

1. ONLY request files from the "Available Files" list
2. Match retrieval to task type:
   - Creating/Composing → Load format specs AND templates
   - Analyzing → Load algorithm specs and examples
3. Check "Files Not Found" list - don't re-request missing files
"""
```

### Handle Missing Files

Track files that don't exist so the LLM can adapt:

```python
class SkillContext:
    not_found: set[str]  # {"skill/path", ...}

    def mark_not_found(self, skill: str, path: str):
        self.not_found.add(f"{skill}/{path}")
```

Show in prompt:
```
## Files That Don't Exist (don't request these)
- runbooks-manager/index/by_subcategory/deserialization.md
```

## Reference Implementation

See the complete Phase 1 implementation:

```
src/analysi/agentic_orchestration/langgraph/kea/phase1/
├── graph.py           # Main graph definition
├── substeps.py        # SubStep definitions with Pydantic models
├── validators.py      # Output validators
├── confidence.py      # Confidence calculation
├── matcher.py         # Deterministic matching
├── CLAUDE.md          # Sync documentation
└── GRAPH_VISUALIZATION.md  # Visual diagram
```

Key patterns demonstrated:
- Deterministic vs LLM nodes
- Conditional routing by confidence
- Fix/retry loops with max retries
- SkillsIR context retrieval
- SDK contract alignment
- Pydantic structured output

## Checklist: Converting an Agent

- [ ] Parse agent frontmatter (skills, model)
- [ ] Identify workflow steps from markdown
- [ ] Classify nodes as deterministic vs LLM-based
- [ ] Design state TypedDict
- [ ] Create SubSteps with objectives and skills
- [ ] Define Pydantic models for structured output
- [ ] Write validators for each SubStep
- [ ] Build graph with nodes and edges
- [ ] Add conditional routing
- [ ] Add retry loops where needed
- [ ] Use same system prompt as SDK
- [ ] Match output format to SDK contract
- [ ] Create CLAUDE.md documenting sync requirements
- [ ] Write unit tests for each node
- [ ] Run comparison test against SDK execution
