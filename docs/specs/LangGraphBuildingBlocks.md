+++
version = "1.0"
date = "2026-02-01"
status = "active"

[[changelog]]
version = "1.0"
date = "2026-02-01"
summary = "Reusable LangGraph patterns for Kea"
+++

# LangGraph Building Blocks for Kea - v1

## Overview

This spec defines reusable LangGraph building blocks that replace the Claude Agent SDK for all Kea phases. The key insight is that each Kea phase follows the same pattern: break agent.md into sub-steps, retrieve context from Skills for each sub-step, execute with validation loops.

**Current state:** Each phase has agent.md (monolithic prompt) + Skills (progressive context via Claude SDK)

**Target state:** Each phase = chain of SubSteps, each SubStep uses SkillsIR for context retrieval

## Conceptual Model: Skills-Based Context Retrieval

```
┌─────────────────────┐                           ┌─────────────────────┐
│      SKILLS         │                           │   TARGET CONTEXT    │
│  (Source Material)  │                           │   (Task-Specific)   │
├─────────────────────┤                           ├─────────────────────┤
│                     │                           │                     │
│  runbooks-manager/  │                           │  • SKILL.md         │
│    ├── SKILL.md     │     ┌───────────────┐     │  • confidence-      │
│    ├── references/  │     │               │     │    rubric.md        │
│    ├── repository/  │────▶│    AGENT      │────▶│  • sql-injection-   │
│    └── index/       │     │  (SkillsIR)   │     │    detection.md     │
│                     │     │               │     │                     │
│  cybersecurity-     │     └───────────────┘     │  (only what's       │
│    analyst/         │            │              │   needed for task)  │
│    ├── SKILL.md     │            │              │                     │
│    └── ...          │            ▼              └─────────────────────┘
│                     │     Given: Task + Skills
│  task-builder/      │     Decides: Which files
│    └── ...          │
│                     │
└─────────────────────┘
```

**Three actors:**
1. **Skills** - Collections of markdown files organized in folders. Can be arbitrary number. Skills implicitly reference each other.
2. **Agent (SkillsIR)** - Given the task at hand, decides which files from which skills to bring into context.
3. **Target Context** - The subset of files needed to solve the specific task, accumulated with token budget tracking.

**Two configuration points:**
1. **Which skills to use** - Specified by the caller (e.g., from agent.md frontmatter: `skills: runbooks-manager, cybersecurity-analyst`)
2. **How files are accessed** - Via `ResourceStore` abstraction:
   - Today: `FileSystemResourceStore` (local filesystem)
   - Future: `KnowledgeUnitResourceStore` (database with flat files + namespace/tags)

---

## The Three Abstractions

| Abstraction | Role |
|-------------|------|
| **SkillsIR** | Progressive retrieval of context for an objective |
| **SubStep** | Retrieve → Execute → Validate → Loop pattern |
| **Phase** | Chain of SubSteps (a complete Kea phase) |

---

## Part 1: SkillsIR (Progressive Retrieval)

SkillsIR is an Information Retrieval system that progressively loads context from Skills based on what the LLM needs to complete a task.

### Design Principles

1. **Tree upfront** - Show what's available without loading everything
2. **Single question** - "Do you have enough?" (simple yes/no decision)
3. **Context budget** - Track and respect token limits
4. **Cascading references** - Files can reference other files, ask about those too

### Flow

```
┌─────────────────────────────────────────────────────────────┐
│                      INITIALIZATION                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Load SKILL REGISTRY                                      │
│     All available skills → {name: description}               │
│                                                              │
│  2. For initial skills (from agent.md):                      │
│     - Load SKILL.md content                                  │
│     - Load file tree (just names, not content)               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    RETRIEVAL LOOP                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Context = [skill registry + SKILL.md + tree]                │
│                                                              │
│  Ask LLM: "Given the input and this context,                 │
│            do you have enough to complete the task?          │
│            If not, what files do you need?"                  │
│                                                              │
│       │                                                      │
│       ├─ "Yes, enough" → DONE                                │
│       │                                                      │
│       └─ "Need: references/matching/composition-guide.md"    │
│              │                                               │
│              ▼                                               │
│         Load file → Add to context                           │
│              │                                               │
│         File may reference other files                       │
│              │                                               │
│         Ask: "Are these also relevant?"                      │
│              │                                               │
│              └─► Loop (until enough or context limit)        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Core Components

```python
# 1. ResourceStore - Where skill resources live (abstracted from filesystem)
class ResourceStore(ABC):
    def list_skills(self) -> dict[str, str]: ...  # name -> description
    def tree(self, skill: str) -> list[str]: ...  # List all paths in skill
    def read(self, skill: str, path: str) -> str: ... # Read content

# 2. SkillContext - Accumulated knowledge with budget tracking
@dataclass
class SkillContext:
    registry: dict[str, str]           # All skill descriptions
    trees: dict[str, list[str]]        # skill -> file paths
    loaded: dict[str, dict[str, str]]  # skill -> path -> content
    token_count: int = 0
    token_limit: int = 50000           # Configurable

    def add(self, skill: str, path: str, content: str) -> bool:
        """Add content if within budget. Returns False if would exceed."""
        tokens = estimate_tokens(content)
        if self.token_count + tokens > self.token_limit:
            return False
        self.loaded.setdefault(skill, {})[path] = content
        self.token_count += tokens
        return True

    def for_prompt(self) -> str:
        """Format loaded content for LLM injection."""
        ...

# 3. Pydantic models for structured LLM output
class FileRequest(BaseModel):
    """A request to load a specific file from a skill."""
    skill: str
    path: str
    reason: str  # Why this file is needed (for observability)

class RetrievalDecision(BaseModel):
    """LLM's decision about context sufficiency."""
    has_enough: bool
    needs: list[FileRequest] = []  # Empty if has_enough=True
```

### The Retrieval Algorithm

```python
async def retrieve(
    store: ResourceStore,
    initial_skills: list[str],  # From agent.md frontmatter
    task_input: dict,           # The input for the task
    objective: str,             # What we're trying to accomplish
    llm: StructuredLLM,         # LLM with Pydantic output support
) -> SkillContext:
    """Progressive retrieval: LLM decides what's needed, code loads it."""

    # 1. Initialize context with registry and trees
    context = SkillContext(
        registry=store.list_skills(),
        trees={s: store.tree(s) for s in initial_skills},
        loaded={},
    )

    # 2. Load SKILL.md for initial skills (always needed)
    for skill in initial_skills:
        content = store.read(skill, "SKILL.md")
        context.add(skill, "SKILL.md", content)

    # 3. Retrieval loop - LLM decides, code executes
    for iteration in range(MAX_ITERATIONS):
        # Ask LLM with structured Pydantic output
        prompt = format_retrieval_prompt(objective, task_input, context)
        decision: RetrievalDecision = await llm.generate(
            prompt,
            response_model=RetrievalDecision
        )

        if decision.has_enough:
            break

        # Code loads requested files (deterministic)
        for req in decision.needs[:MAX_FILES_PER_REQUEST]:
            content = store.read(req.skill, req.path)
            if not context.add(req.skill, req.path, content):
                # Token budget exceeded - force completion
                break

    return context
```

**Key Design Decisions:**
- **LLM decides** what files are needed via structured `RetrievalDecision`
- **Code executes** file loading (deterministic, auditable)
- **Pydantic validates** LLM output (type safety, no parsing errors)
- **Iteration cap** enforced by code (`MAX_ITERATIONS`)
- **Files-per-request cap** prevents runaway requests (`MAX_FILES_PER_REQUEST`)

### The Retrieval Prompt

```python
RETRIEVAL_PROMPT = """
## Your Objective
{objective}

## Task Input
{task_input}

## Available Skills (can request files from any)
{skill_registry}

## Already Loaded (don't request again)
{loaded_files_list}

## Available Files (can request these)
{file_trees}

## Token Budget
Used: {token_count} / {token_limit}

## Instructions
Analyze the objective and input. Do you have enough context to complete the task?

If you have enough context, respond with has_enough=true.
If you need more files, list them in the needs array (max 3 per request).
"""
```

The LLM responds with a `RetrievalDecision` Pydantic model - no JSON parsing needed.

### Limits

| Constraint | Value | Rationale |
|------------|-------|-----------|
| Max iterations | 5 | Prevent infinite loops |
| Default token limit | 50,000 | Leave room for task execution |
| Max files per request | 3 | Encourage focused requests |

### As LangGraph Graph

```
┌─────────────────────────────────────────────────────────────┐
│                   SkillsIR Graph                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Input: initial_skills, objective, task_input                │
│                                                              │
│  [init] ─────────────────────────────────────────────────►  │
│     │  Load registry, trees, SKILL.md files                  │
│     ▼                                                        │
│  [check_enough] ◄────────────────────────────┐              │
│     │  LLM → RetrievalDecision (Pydantic)    │              │
│     │                                         │              │
│     ├─ has_enough=true ──► [finish]          │              │
│     │                         │               │              │
│     │                         ▼               │              │
│     │                   return SkillContext   │              │
│     │                                         │              │
│     └─ has_enough=false ──► [load_files] ────┘              │
│                                │                             │
│                         Code loads files                     │
│                         Updates context                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Nodes:**
| Node | Type | Description |
|------|------|-------------|
| `init` | Deterministic | Load registry, trees, initial SKILL.md files |
| `check_enough` | LLM | Ask LLM, get `RetrievalDecision` via structured output |
| `load_files` | Deterministic | Load requested files into context |
| `finish` | Deterministic | Return final `SkillContext` |

---

## Part 2: SubStep Pattern

The SubStep is the reusable execution unit that combines SkillsIR with task execution and validation.

### The Universal Sub-Step Pattern

Every sub-step in any Kea phase follows this pattern:

```
┌─────────────────────────────────────────────────────────────┐
│                       SUB-STEP                               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. GET CONTEXT                                              │
│     SkillsIR.retrieve(objective) → context                   │
│                                                              │
│  2. EXECUTE TASK                                             │
│     LLM(context + task_prompt) → output                      │
│                                                              │
│  3. VALIDATE                                                 │
│     tool_validate(output) OR llm_validate(output)            │
│           │                                                  │
│      ┌────┴────┐                                             │
│      ▼         ▼                                             │
│    PASS      FAIL                                            │
│      │         │                                             │
│      │    ┌────┴────┐                                        │
│      │    ▼         ▼                                        │
│      │  RETRY    NEED MORE CONTEXT?                          │
│      │    │         │                                        │
│      │    │         ▼                                        │
│      │    │    4. GET MORE CONTEXT (optional)                │
│      │    │         │                                        │
│      │    └────┬────┘                                        │
│      │         ▼                                             │
│      │    (loop back to EXECUTE)                             │
│      │                                                       │
│      ▼                                                       │
│   → NEXT SUB-STEP                                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### SubStep Definition

```python
@dataclass
class SubStep:
    """A single step in a Kea phase."""

    name: str
    objective: str              # For SkillsIR retrieval
    skills: list[str]           # Which skills to query
    task_prompt: str            # The LLM task template
    validator: Callable         # How to validate output
    max_retries: int = 3

@dataclass
class ValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    needs_more_context: bool = False
    context_hint: str | None = None  # More specific objective for retry
```

### SubStep Execution Flow

```python
async def execute_substep(
    substep: SubStep,
    state: dict,
    store: ResourceStore,
    llm: LLM,
) -> dict:
    """Execute a substep with the retrieve → execute → validate loop."""

    # 1. GET CONTEXT
    context = await retrieve(
        store=store,
        initial_skills=substep.skills,
        task_input=state,
        objective=substep.objective,
        llm=llm,
    )

    for attempt in range(substep.max_retries):
        # 2. EXECUTE TASK
        prompt = substep.task_prompt.format(
            context=context.for_prompt(),
            **state,
        )
        output = await llm.generate(prompt)

        # 3. VALIDATE
        validation = substep.validator(output)

        if validation.passed:
            return {"output": output, "context": context}

        # 4. RETRY or GET MORE CONTEXT
        if validation.needs_more_context:
            context = await retrieve(
                store=store,
                initial_skills=substep.skills,
                task_input=state,
                objective=validation.context_hint,  # More specific
                llm=llm,
            )
        # else: retry with same context, error feedback in prompt

    raise MaxRetriesExceeded(substep.name)
```

### As LangGraph SubGraph

```
┌─────────────────────────────────────────────────────────────┐
│                    SubStep SubGraph                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [get_context] ─────────────────────────────────────────►   │
│       │  SkillsIR.retrieve(objective)                        │
│       ▼                                                      │
│  [execute_task] ◄────────────────────────────┐              │
│       │  LLM(context + task_prompt)          │              │
│       ▼                                       │              │
│  [validate] ─────────────────────────────────┤              │
│       │                                       │              │
│       ├─ pass ──► [finish] ──► return output │              │
│       │                                       │              │
│       ├─ fail + retry ────────────────────────┘              │
│       │                                                      │
│       └─ fail + need_context ──► [get_more_context] ─┐      │
│                                       │               │      │
│                                       └───────────────┘      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Part 3: Phase Composition

A Kea Phase is a chain of SubSteps that transforms input into output.

### A Kea Phase = Chain of Sub-Steps

```
agent.md (monolithic) → [SubStep1] → [SubStep2] → [SubStep3] → Output
                            │            │            │
                         Skills       Skills       Skills
                        (context)    (context)    (context)
```

### Example: Phase 1 (Runbook Matching) as SubSteps

**Source**: Observations from Phase 47 (`tests/eval/phase_47_observation/OBSERVATIONS.md`)

#### Key Insight: Composition is Multi-Step LLM

The composition path isn't a single "compose this" LLM call. Observed agent behavior shows **5 distinct reasoning steps**:

| Step | Type | What Happens |
|------|------|--------------|
| 1. Gap Analysis | LLM | "IDOR runbook would completely miss the XSS component" - analyzes what's MISSING from top match |
| 2. Strategy Selection | LLM | Chooses composition approach (Hybrid Blend, Category-Based, etc.) and identifies template |
| 3. Selective Extraction | LLM | Decides what to take from each source runbook |
| 4. Novel Generation | LLM | Blends sources + generates new content (e.g., "2x2 Decision Matrix") |
| 5. Self-Correction | LLM | Fixes issues after validation ("Replaced generic decision points with specific examples") |

Each step could be a separate SubStep with validation between them, or combined into fewer SubSteps with internal loops.

#### Phase 1 SubSteps (Match Path - Deterministic)

```python
# When confidence is VERY HIGH or HIGH - no LLM needed
PHASE_1_MATCH_SUBSTEPS = [
    SubStep(
        name="load_index",
        objective="",  # No context needed - deterministic
        skills=[],
        task_prompt="",  # No LLM - pure Python
        validator=validate_index_loaded,
    ),
    SubStep(
        name="calculate_scores",
        objective="",  # No context needed - deterministic
        skills=[],
        task_prompt="",  # No LLM - pure Python
        validator=validate_scores,
    ),
    SubStep(
        name="determine_confidence",
        objective="",  # Deterministic threshold check
        skills=[],
        task_prompt="",  # No LLM - pure Python
        validator=validate_confidence_level,
    ),
    SubStep(
        name="fetch_and_expand",
        objective="",  # Deterministic file read + WikiLink expansion
        skills=[],
        task_prompt="",  # No LLM - pure Python
        validator=validate_runbook_format,
    ),
]
```

#### Phase 1 SubSteps (Composition Path - LLM Required)

```python
# When confidence is MEDIUM, LOW, or VERY LOW - 5 LLM steps
PHASE_1_COMPOSE_SUBSTEPS = [
    # Steps 1-3 same as match path (deterministic)
    SubStep(name="load_index", ...),
    SubStep(name="calculate_scores", ...),
    SubStep(name="determine_confidence", ...),

    # Step 4: Gap Analysis (LLM)
    SubStep(
        name="analyze_gaps",
        objective="identify what's missing from top-scoring runbook for this alert",
        skills=["runbooks-manager"],
        task_prompt="""
        {context}

        ## Alert
        {alert}

        ## Top Match: {top_match_name} (score: {top_score})
        {top_match_content}

        ## Task
        Analyze what investigation steps are MISSING from this runbook
        for handling the given alert. Consider:
        - Attack vectors not covered
        - Evidence sources not queried
        - Hypotheses not addressed
        """,
        validator=validate_gap_analysis,
    ),

    # Step 5: Strategy Selection (LLM)
    SubStep(
        name="select_strategy",
        objective="determine composition strategy based on gaps and available runbooks",
        skills=["runbooks-manager"],
        task_prompt="""
        {context}

        ## Gaps Identified
        {gaps}

        ## Available Runbooks (top 5 by score)
        {candidate_runbooks}

        ## Task
        Select a composition strategy:
        - Same Attack Family Adaptation (HIGH confidence)
        - Multi-Source Blending (MEDIUM confidence)
        - Category-Based Assembly (MEDIUM-LOW confidence)
        - Minimal Scaffold (VERY LOW confidence)

        Identify which runbooks contribute which sections.
        """,
        validator=validate_strategy_selection,
    ),

    # Step 6: Selective Extraction (LLM)
    SubStep(
        name="extract_sections",
        objective="extract relevant sections from source runbooks",
        skills=["runbooks-manager"],
        task_prompt="""
        {context}

        ## Composition Strategy
        {strategy}

        ## Source Runbooks
        {source_runbooks}

        ## Task
        For each source runbook, extract the specific sections needed.
        Document provenance (which section came from which source).
        """,
        validator=validate_extraction,
    ),

    # Step 7: Novel Generation (LLM)
    SubStep(
        name="compose_runbook",
        objective="blend extracted sections and generate novel content for gaps",
        skills=["runbooks-manager", "cybersecurity-analyst"],
        task_prompt="""
        {context}

        ## Extracted Sections (with provenance)
        {extracted_sections}

        ## Remaining Gaps
        {remaining_gaps}

        ## Task
        1. Blend the extracted sections into a coherent runbook
        2. Generate novel content for any remaining gaps
        3. Ensure proper flow and no contradictions
        4. Mark critical steps with ★
        5. Include composition_metadata in frontmatter
        """,
        validator=validate_runbook_format,
    ),

    # Step 8: Self-Correction (LLM, conditional on validation failure)
    SubStep(
        name="fix_runbook",
        objective="fix validation errors in composed runbook",
        skills=["runbooks-manager"],
        task_prompt="""
        {context}

        ## Current Runbook
        {runbook}

        ## Validation Errors
        {errors}

        ## Task
        Fix the identified errors while preserving the investigation logic.
        """,
        validator=validate_runbook_format,
        max_retries=3,
    ),
]
```

#### Observed Scoring Weights

From Phase 47 observations:

| Field | Points |
|-------|--------|
| Exact detection_rule match | +100 |
| alert_type match | +40 |
| subcategory match | +40 |
| source_category match | +30 |
| MITRE tactic overlap | +20 per tactic |

**Thresholds:**
- VERY HIGH: ~170+ with exact detection_rule match
- HIGH: 120+ without exact match
- MEDIUM: 70-120
- LOW: 40-70
- VERY LOW: <40

---

## Implementation

### Files to Create

```
src/analysi/agentic_orchestration/langgraph/
├── __init__.py
├── skills/
│   ├── __init__.py
│   ├── store.py          # ResourceStore ABC + FileSystemResourceStore
│   ├── context.py        # SkillContext dataclass
│   ├── retrieval.py      # retrieve() function
│   └── prompts.py        # ENOUGH_CONTEXT_PROMPT, etc.
├── substep/
│   ├── __init__.py
│   ├── definition.py     # SubStep, ValidationResult dataclasses
│   ├── executor.py       # execute_substep()
│   └── validation.py     # Common validators
└── phases/
    └── phase1/           # Runbook matching (first implementation)
        ├── __init__.py
        ├── substeps.py   # PHASE_1_SUBSTEPS definitions
        ├── graph.py      # Phase 1 LangGraph
        └── validators.py # Phase-specific validators
```

### Implementation Phases

**Phase 48: SkillsIR**
- ResourceStore ABC + FileSystemResourceStore
- SkillContext with token tracking
- retrieve() loop
- Unit tests with mocked LLM

**Phase 49: SubStep Pattern**
- SubStep and ValidationResult dataclasses
- execute_substep() with retry logic
- Common validators
- Unit tests

**Phase 50: Phase 1 Implementation**
- PHASE_1_SUBSTEPS definitions
- Phase 1 LangGraph assembly
- Eval tests comparing to Claude SDK baseline

---

## Configuration

```bash
# Feature flag for backend selection
ANALYSI_RUNBOOK_STAGE_BACKEND=claude_agent  # Default (existing)
ANALYSI_RUNBOOK_STAGE_BACKEND=langgraph     # New implementation

# SkillsIR configuration
ANALYSI_SKILLSIR_TOKEN_LIMIT=50000
ANALYSI_SKILLSIR_MAX_ITERATIONS=5

# LLM provider
ANALYSI_LANGGRAPH_LLM_PROVIDER=anthropic
ANALYSI_LANGGRAPH_LLM_MODEL=claude-sonnet-4-20250514
```

---

## Dependencies

Required in `pyproject.toml`:
- `langgraph`
- `langchain-anthropic`

---

---

## Future: Knowledge Units as ResourceStore Backend

The `ResourceStore` abstraction is designed to support multiple backends:

```python
# Today - filesystem
store = FileSystemResourceStore(skills_dir)

# Future - database via Knowledge Units
store = KnowledgeUnitResourceStore(db_session, tenant_id)
```

**Knowledge Units Design Notes** (to be designed later):
- Files are **flat entities** in the database
- Skill membership and folder-like hierarchy via **tagging/namespace abstraction**
- Enables per-tenant skill customization
- Enables versioning and audit trails

This abstraction is NOT designed yet - placeholder for future work.

---

## References

- AutomatedWorkflowBuilder_v1.md - Project Kea overview
- TypedWorkflows_v1.md - Workflow type system
- docker/agents_skills/ - Packaged skills and agents
- **tests/eval/phase_47_observation/** - Observed agent behavior that informed this spec
  - OBSERVATIONS.md - Detailed breakdown of 5-step LLM composition process
  - run_001_hybrid_attack/ - Exact match scenario
  - run_002_identity_anomaly/ - Composition scenario
