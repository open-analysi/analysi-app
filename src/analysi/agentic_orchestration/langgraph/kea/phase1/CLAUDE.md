# Runbook Matching & Composition

## Architecture: LangGraph Reimplementation of Claude Code Agent

**This LangGraph implementation is a programmatic reimplementation of `runbook-match-agent.md`.**

| Aspect | Claude Code Agent | LangGraph |
|--------|------------------|-------------------|
| **Source** | `agents/dist/runbook-match-agent.md` | This directory |
| **Execution** | Claude Agent SDK with Skill tool | LangGraph StateGraph with SkillsIR |
| **Skills** | Frontmatter: `skills: runbooks-manager, cybersecurity-analyst` | Hardcoded in `substeps.py` |
| **Process** | Agent follows markdown instructions | Graph follows SubStep definitions |

## Why Two Implementations?

- **Claude Code Agent**: Used by the full Kea orchestration pipeline (production)
- **LangGraph**: Experimental/research implementation for testing composition strategies

## Keeping Them In Sync

When updating either implementation, ensure these aspects remain aligned:

### 1. Skills Configuration

**Agent** (`runbook-match-agent.md` frontmatter):
```yaml
skills: runbooks-manager, cybersecurity-analyst
```

**LangGraph** (`substeps.py`):
```python
# compose_runbook uses both skills
skills=["runbooks-manager", "cybersecurity-analyst"]

# Other substeps use runbooks-manager only
skills=["runbooks-manager"]
```

### 2. Confidence Levels & Routing

Both implementations should use the same confidence thresholds from:
- `runbooks-manager/references/matching/confidence-rubric.md`

**Agent**: Described in "Process" section
**LangGraph**: Implemented in `confidence.py` and `graph.py` routing

### 3. Composition Strategy

Both should follow the same composition patterns from:
- `runbooks-manager/references/matching/composition-guide.md`

**Agent**: "Execute Core Workflow" section references this
**LangGraph**: `select_strategy` substep implements these strategies

### 4. Output Requirements

**Agent** specifies:
- Self-contained output (no WikiLinks in final runbook)
- Critical step markers (★)
- Specific file outputs (matching-report.json, composed-runbook.md)

**LangGraph** produces equivalent output via:
- `compose_runbook` substep prompt
- `validators.py` validation rules
- `run_phase1()` returns a `matching_report` dict conforming to SDK schema

### 5. System Prompt Alignment

**Both implementations use the same system prompt** via workspace.py:
```python
from analysi.agentic_orchestration.workspace import get_system_prompt_for_stage
from analysi.agentic_orchestration.observability import WorkflowGenerationStage

PHASE1_SYSTEM_PROMPT = get_system_prompt_for_stage(WorkflowGenerationStage.RUNBOOK_GENERATION)
# Returns: "Expert Cyber Security Analyst specialized in creating comprehensive runbooks..."
```

## SDK Contract Alignment

The `run_phase1()` function returns a dict that aligns with the SDK workspace output:

### matching_report Schema

For matched decisions (HIGH/VERY_HIGH confidence):
```json
{
  "confidence": "VERY HIGH",
  "score": 170,
  "decision": "matched",
  "matched_runbook": "repository/sql-injection-detection.md",
  "timestamp": "2025-11-16T17:45:00Z"
}
```

For composed decisions (MEDIUM/LOW/VERY_LOW confidence):
```json
{
  "confidence": "MEDIUM",
  "score": 55,
  "decision": "composed",
  "composed_runbook": "composed-runbook.md",
  "composition_sources": ["runbook1.md", "runbook2.md"],
  "timestamp": "2025-11-16T17:45:00Z"
}
```

### Full Return Value

```python
{
    # SDK contract fields
    "matching_report": {...},  # Schema above
    "runbook": str,            # Full runbook content (matched or composed)

    # Internal debugging fields
    "matches": list,           # Scored match results
    "top_score": float,        # Highest match score
    "confidence": ConfidenceLevel,
    "gaps": dict | None,       # Gap analysis (composition only)
    "strategy": dict | None,   # Composition strategy
    "extractions": dict | None,# Extracted sections
    "composition_metadata": dict | None,
    "fix_retries": int,        # Validation retry count
}
```

## Checklist: Before Modifying Either Implementation

- [ ] Check if the change affects skills configuration
- [ ] Check if confidence thresholds are impacted
- [ ] Check if composition strategies are affected
- [ ] Check if output format requirements change
- [ ] Update BOTH implementations if needed
- [ ] Run tests for both: `pytest tests/unit/agentic_orchestration/langgraph/kea/`

## Key Files

### LangGraph Runbook Matching
- `graph.py` - Main graph definition and routing
- `substeps.py` - SubStep definitions with skills and prompts
- `confidence.py` - Confidence level calculation
- `matcher.py` - Runbook matching algorithm
- `validators.py` - Output validation

### Claude Code Agent
- `agents/dist/runbook-match-agent.md` - Agent definition
- Skills are DB-only — accessed via `DatabaseResourceStore`

## SkillsIR Context Retrieval

LangGraph uses SkillsIR for progressive context retrieval from skills. The retrieval prompt (`skills/prompts.py`) guides the LLM to load appropriate reference files.

Key retrieval behavior for composition:
- **Creating/Composing tasks** → Should load format specs AND templates
- Format spec: `runbooks-manager/references/building/format-specification.md`
- Templates: `runbooks-manager/templates/runbook-template.md`

If output quality differs between implementations, check what files SkillsIR loaded vs what the agent accessed.
