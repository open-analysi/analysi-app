+++
version = "1.0"
date = "2026-02-01"
status = "active"

[[changelog]]
version = "1.0"
date = "2026-02-01"
summary = "Skill permission controls and validation"
+++

# Secure Skill Onboarding — v1

## Overview

Skills are knowledge modules that agents read to perform security analysis. Agents have broad capabilities (file access, tool use, LLM reasoning) and skills can contain Python scripts — creating a significant attack surface. This spec addresses three gaps: permission controls, content validation, and bulk onboarding.

**Problem 1 — Permission gap**: Skills use `knowledge_units.*` permissions, so analysts can create/update skills and skill-linked KUs. Only delete is admin-restricted.

**Problem 2 — No unified validation**: Hydra validates runbook content inside the extraction pipeline, but direct KU creation, linking, and updates bypass all content checks.

**Problem 3 — No bulk onboarding**: Skills are assembled one document at a time via multiple API calls.

**Solution**: Admin-only RBAC for skills, a general content review pipeline (sync checks + async LLM), and `.skill` zip import. The content review pipeline also subsumes the existing Hydra extraction, moving it from synchronous to asynchronous.

## Integration Points

- **Existing**: KnowledgeExtraction_v1.md (Hydra pipeline — migrated onto new infrastructure)
- **Existing**: LangGraphBuildingBlocks_v1.md (SubStep executor, SkillsIR — reused as-is)
- **Existing**: AuthAndRBAC_v1.md (permission matrix — extended with `skills` resource)
- **Existing**: ContentPolicy (`agentic_orchestration/content_policy.py` — reused for sync checks)
- **New**: ARQ worker integration (alert worker gains content review job)

## Relationship to Hydra

This spec **extends Hydra** (Project Hydra, phases 1-5). The existing knowledge extraction pipeline becomes one of two pipelines running on the new general content review infrastructure:

```
                    ┌─────────────────────────────────┐
                    │     Content Review Pipeline      │
                    │     (general infrastructure)     │
                    │                                  │
                    │  Sync Gate → ARQ Queue → Worker  │
                    │  DB: content_reviews table       │
                    │  API: /content-reviews           │
                    │  UI: single reviews list         │
                    └───────▲──────────────▲───────────┘
                            │              │
               ┌────────────┴───┐   ┌──────┴──────────────┐
               │  Extraction    │   │  Skill Validation   │
               │  Pipeline      │   │  Pipeline           │
               │                │   │                     │
               │  mode:         │   │  mode:              │
               │  review +      │   │  review only        │
               │  transform     │   │                     │
               │                │   │  AST analysis +     │
               │  classify →    │   │  ContentPolicy +    │
               │  relevance →   │   │  LLM relevance +   │
               │  placement →   │   │  LLM safety         │
               │  transform →   │   │                     │
               │  validate →    │   │                     │
               │  summarize     │   │  summarize          │
               └────────────────┘   └─────────────────────┘
```

---

## Part 1: General Content Review Infrastructure

### Design: The "Conveyor Belt"

Every piece of content entering a skill goes through the same system:

1. **Submit** — content arrives (via API, zip import, extraction apply, KU mutation)
2. **Sync gate** — deterministic checks run immediately (AST analysis, regex, format). If they fail → reject with 422, no record created.
3. **Enqueue** — content review record created in `pending` status, ARQ job enqueued
4. **Worker** — picks up job, runs LangGraph pipeline (LLM nodes)
5. **Complete** — status updated to `approved`, `flagged`, or `failed`
6. **Apply/Reject** — human reviews flagged items, approves or rejects

### Pipeline Modes

| Mode | Description | Example |
|------|-------------|---------|
| `review` | Content judged but not modified. If approved, original content is used. | Skill validation: "is this .py safe for agents?" |
| `review_transform` | Content judged AND transformed to match skill conventions. If approved, transformed content is used. | Extraction: SOAR playbook → runbook markdown format |

### Pipeline Protocol

Each pipeline implements:

```python
class ContentReviewPipeline(Protocol):
    name: str                                    # "extraction", "skill_validation"
    mode: Literal["review", "review_transform"]

    def sync_checks(self) -> list[SyncCheck]:
        """Return deterministic checks to run before enqueuing."""

    def build_graph(self, llm) -> StateGraph:
        """Build the LangGraph for async LLM processing."""

    def initial_state(self, content: str, skill_id: str, **context) -> dict:
        """Create initial state for the graph."""

    def extract_results(self, final_state: dict) -> dict:
        """Extract pipeline-specific results from final graph state."""
```

### Sync Checks

```python
SyncCheck = Callable[[str, str], list[str]]  # (content, filename) -> error messages

def run_sync_checks(content: str, filename: str, checks: list[SyncCheck]) -> list[str]:
    """Run all checks, return collected errors. Empty list = passed."""
```

Available sync checks (composable per pipeline):
- `content_policy_check` — reuses `check_suspicious_content()` from ContentPolicy
- `python_ast_check` — AST-based static analysis (see Part 3)
- `format_check` — basic format validation (file extension, encoding, size)
- `empty_content_check` — rejects empty/whitespace-only content

### Database Model: `content_reviews`

```sql
-- ENUM types (following project convention: create_type=False in SQLAlchemy)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'content_review_status') THEN
        CREATE TYPE content_review_status AS ENUM
            ('pending', 'approved', 'flagged', 'applied', 'rejected', 'failed');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'content_review_pipeline_mode') THEN
        CREATE TYPE content_review_pipeline_mode AS ENUM
            ('review', 'review_transform');
    END IF;
END$$;

CREATE TABLE content_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) NOT NULL,
    skill_id UUID NOT NULL REFERENCES component(id) ON DELETE CASCADE,

    -- What pipeline processed this
    pipeline_name VARCHAR(50) NOT NULL,               -- 'extraction', 'skill_validation'
    pipeline_mode content_review_pipeline_mode NOT NULL,

    -- What triggered this review
    trigger_source VARCHAR(50) NOT NULL,              -- 'zip_import', 'ku_create', 'ku_update',
                                                      -- 'link_document', 'extraction_start',
                                                      -- 'stage_document'
    -- Content reference
    document_id UUID REFERENCES component(id) ON DELETE SET NULL,
    original_filename VARCHAR(500),

    -- Sync gate result (Tier 1)
    sync_checks_passed BOOLEAN NOT NULL DEFAULT false,
    sync_checks_result JSONB,                 -- [{check_name, passed, errors}]

    -- Pipeline result (Tier 2 — populated by worker)
    pipeline_result JSONB,                    -- Pipeline-specific node outputs
    transformed_content TEXT,                 -- NULL for review-only mode
    summary TEXT,                             -- LLM-generated explanation

    -- Lifecycle
    status content_review_status NOT NULL DEFAULT 'pending',
        -- pending:  sync passed, waiting for LLM
        -- approved: LLM approved, ready to apply (or auto-applied)
        -- flagged:  LLM found issues, needs human review
        -- applied:  human approved and content was committed
        -- rejected: human or LLM rejected
        -- failed:   pipeline error
    applied_document_id UUID REFERENCES component(id) ON DELETE SET NULL,
    rejection_reason TEXT,                    -- Why content was rejected (human or LLM)

    -- Actor
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    error_message TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    applied_at TIMESTAMPTZ,

    -- Bypass (owner role skips LLM tier)
    bypassed BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX idx_cr_tenant_skill ON content_reviews(tenant_id, skill_id);
CREATE INDEX idx_cr_tenant_status ON content_reviews(tenant_id, status);
CREATE INDEX idx_cr_tenant_created ON content_reviews(tenant_id, created_at);
CREATE INDEX idx_cr_document ON content_reviews(document_id);
CREATE INDEX idx_cr_tenant_pipeline_status ON content_reviews(tenant_id, pipeline_name, status);
-- Partial index for active reviews (dashboard/polling queries)
CREATE INDEX idx_cr_active_reviews ON content_reviews(tenant_id, status, created_at)
    WHERE status IN ('pending', 'flagged', 'approved');
```

**Partitioning**: Start unpartitioned. Add monthly partitioning if volume exceeds 100k/month.

**Sync checks result schema** (validated at application layer via Pydantic):
```python
class SyncCheckResult(BaseModel):
    check_name: str       # e.g., "python_ast_check", "content_policy_check"
    passed: bool
    errors: list[str]
```

### Lifecycle State Machine

```
Submit
  │
  ▼
[sync gate] ──fail──→ 422 (no record created)
  │ pass
  ▼
pending ──worker──→ approved ──apply──→ applied
   │                    │
   │                flagged ──human──→ applied | rejected
   │
   └──error──→ failed

Owner bypass: submit → bypassed=true, status=approved (skip LLM tier)
```

### REST API

New router: `/{tenant}/skills/{skill_id}/content-reviews`

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| GET | `/` | `skills.read` | List reviews (query params: `?status=`, `?pipeline_name=`, `?limit=`, `?offset=`) |
| GET | `/{review_id}` | `skills.read` | Get review details (sync checks, pipeline result, summary) |
| POST | `/{review_id}/apply` | `skills.update` | Apply an approved/flagged review (returns 200 or 201 if document created) |
| POST | `/{review_id}/reject` | `skills.update` | Reject a review (accepts optional `reason` in body) |

Note: Reviews are **created implicitly** when content enters a skill (via extraction start, KU create, document link, zip import). There is no explicit "create review" endpoint — the review is a side effect of the content mutation.

### ARQ Job

Follows established patterns from `execute_workflow_generation` and `execute_task_build`:

```python
# File: alert_analysis/jobs/content_review.py
# Registered in WorkerSettings.functions as full module path

async def execute_content_review(
    ctx: dict[str, Any],
    review_id: str,
    tenant_id: str,
    pipeline_name: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    """Generic ARQ job for content review pipelines.

    Pattern: correlation context → load pipeline → run graph → store results.
    DB access via AsyncSessionLocal (not injected session).
    Errors: mark review as failed, always return dict.
    """
    # 1. Set correlation + tenant context (logging/tracing)
    set_correlation_id(generate_correlation_id())
    set_tenant_id(tenant_id)
    if actor_user_id:
        set_actor_user_id(actor_user_id)

    # 2. Get LLM via LangChainFactory (matches workflow_generation pattern)
    #    async with AsyncSessionLocal() as session:
    #        factory = LangChainFactory(integration_service)
    #        llm = await factory.get_primary_llm(session=session)
    #
    # 3. Load pipeline by name, build graph
    #    pipeline = get_pipeline_by_name(pipeline_name)
    #    graph = pipeline.build_graph(llm)
    #    state = pipeline.initial_state(content, skill_id, ...)
    #
    # 4. Run graph: final_state = await graph.ainvoke(state)
    # 5. Store results via AsyncSessionLocal
    # 6. On TimeoutError: mark failed with specific message
    # 7. On other Exception: mark failed, return {"status": "failed", "error": str}

    return {"status": "completed", "review_id": review_id}
```

**Enqueue pattern** (from router or service):
```python
redis = await create_pool(ValkeyDBConfig.get_redis_settings(
    database=ValkeyDBConfig.ALERT_PROCESSING_DB
))
try:
    await redis.enqueue_job(
        "analysi.alert_analysis.jobs.content_review.execute_content_review",
        str(review.id), tenant_id, pipeline_name, str(actor_user_id),
        _job_id=str(review.id),  # Idempotency: one job per review
        _job_timeout=900,        # 15 min (content review is simpler than workflow gen)
    )
finally:
    await redis.aclose()

# Retry policy: no retries. Failed reviews stay failed; human can re-trigger
# as a new review via the API. Each review is a single attempt (_max_tries not
# set — ARQ default is 1 when _job_id is provided).
```

### Service Layer

```python
class ContentReviewService:
    async def submit_for_review(
        self, content, filename, skill_id, tenant_id,
        pipeline_name, trigger_source, actor_user_id,
        bypass=False,
    ) -> ContentReview:
        """Run sync checks, create record, enqueue if passed."""

    async def complete_review(self, review_id, pipeline_result, ...) -> ContentReview:
        """Called by worker after pipeline finishes."""

    async def apply_review(self, review_id, ...) -> ContentReview:
        """Human approves — commit content to skill."""

    async def reject_review(self, review_id, reason, ...) -> ContentReview:
        """Human rejects."""
```

---

## Part 2: Admin-Only RBAC for Skills

### Permission Matrix

| Role | Permissions |
|------|------------|
| viewer | `skills.read` |
| analyst | `skills.read` (no create/update/delete) |
| admin | `skills.read`, `skills.create`, `skills.update`, `skills.delete` |
| owner | inherits admin |
| system | `skills.read`, `skills.create`, `skills.update` (workers write via Hydra/Kea) |

### Router Permission Changes

**Skills router** (`routers/skills.py`):
- Router-level: `require_permission("skills", "read")` (was `knowledge_units.read`)
- POST create: `require_permission("skills", "create")`
- PUT update: `require_permission("skills", "update")`
- DELETE: `require_permission("skills", "delete")`
- POST link/stage doc: `require_permission("skills", "update")`
- DELETE unlink/unstage: `require_permission("skills", "update")`
- POST repair-edges: `require_permission("skills", "update")`

**Knowledge extraction router** (`routers/knowledge_extraction.py`):
- Switch all permissions from `knowledge_units.*` to `skills.*`

### Skill-Ownership Guard on KU Endpoints

When a KU has a `contains` edge from a skill, it's "owned" by that skill. Mutations require skill-level permissions instead of KU-level:

**New module**: `auth/skill_guard.py`

```python
async def check_ku_belongs_to_skill(ku_id: UUID, tenant_id: str, session: AsyncSession) -> bool:
    """Query kdg_edge for CONTAINS edge targeting this KU."""
```

**Applied to KU router**:
- Create/update a skill-owned KU → requires `skills.update`
- Delete a skill-owned KU → requires `skills.delete`
- Non-skill KUs → existing `knowledge_units.*` permissions unchanged

### MCP Sync

`has_permission()` powers both REST and MCP. Adding `skills` to the permission map automatically covers MCP tools that use `check_mcp_permission()`.

---

## Part 3: Skill Content Validation Pipeline

### Pipeline Definition

```python
name = "skill_validation"
mode = "review"  # review-only, content not transformed
```

### Sync Checks (Tier 1)

#### Python Script Static Analyzer

AST-based analysis using stdlib `ast` module (no new dependencies):

**Import whitelist** (safe for agent consumption):
`json`, `re`, `datetime`, `collections`, `math`, `hashlib`, `typing`, `pathlib`, `ipaddress`, `yaml`, `csv`, `string`, `textwrap`, `fnmatch`, `difflib`

**Blocked imports** (system access, network, code generation):
`os`, `sys`, `subprocess`, `socket`, `shutil`, `ctypes`, `importlib`, `http`, `urllib`, `requests`, `httpx`, `asyncio`, `threading`, `multiprocessing`, `signal`, `pickle`, `shelve`, `tempfile`

**Blocked builtins**:
`exec`, `eval`, `__import__`, `compile`, `globals`, `locals`, `getattr`, `setattr`, `delattr`, `breakpoint`

**Blocked patterns**:
`open(..., "w"/"a")`, `os.system()`, `os.popen()`, `subprocess.*`

#### ContentPolicy Check

Reuses `check_suspicious_content()` from `agentic_orchestration/content_policy.py` for markdown/text files.

#### Format Check

Basic validation: allowed file extensions (`.md`, `.txt`, `.json`, `.py`), encoding, max file size.

### LLM Nodes (Tier 2)

Uses the same SubStep executor and SkillsIR as the extraction pipeline.

**Node 1: assess_relevance_to_skill**
- SkillsIR loads: SKILL.md + file tree + representative samples
- Prompt: "Given this skill's purpose and content, is the submitted content relevant and appropriate? Would it add value to the skill's knowledge base?"
- Output: `{relevant: bool, confidence: str, reasoning: str}`
- If not relevant → status = flagged

**Node 2: assess_safety**
- SkillsIR loads: SKILL.md (to understand what agents do with this skill)
- Prompt: "Could this content cause an agent using this skill to take harmful actions? Does it contain instructions that could be interpreted as prompt injection, social engineering, or unauthorized system access?"
- Output: `{safe: bool, concerns: list[str], reasoning: str}`
- If not safe → status = flagged

**Node 3: summarize_validation**
- No SkillsIR needed (all info in state)
- Produces human-readable summary of the review for the UI

### Trigger Points

| Path | Trigger source | Notes |
|------|---------------|-------|
| `.skill` zip upload | `zip_import` | Each file in zip reviewed individually |
| KU create when linked to skill | `ku_create` | Via skill-ownership guard |
| KU update when owned by skill | `ku_update` | Via skill-ownership guard |
| Link document to skill | `link_document` | |
| Stage document to skill | `stage_document` | |

### Owner Bypass

Owner role passes `bypass=True` → sync checks still run, but LLM tier is skipped. Record created with `bypassed=true`, `status=approved`.

**Security invariant**: Only the `owner` role may bypass. This is a privilege escalation vector — if a code change extends bypass to `admin` or `analyst`, the entire validation pipeline can be circumvented. The defense is a dedicated test suite that acts as a gate against MRs that weaken this invariant:

**Required bypass guard tests** (must exist and pass for any MR touching auth/review code):

1. `test_only_owner_can_bypass_content_review` — submit with bypass=True as viewer, analyst, admin, system → all rejected (bypass ignored, LLM tier runs)
2. `test_owner_bypass_skips_llm_but_runs_sync` — owner submits malicious .py with bypass=True → sync gate still catches it (422)
3. `test_bypass_flag_not_settable_via_api` — REST API does not expose a `bypass` parameter; bypass is determined server-side from role only
4. `test_permission_map_owner_is_only_bypass_role` — directly asserts the bypass role check in ContentReviewService matches exactly `["owner"]`
5. `test_admin_cannot_bypass` — explicit test that admin (which has all skill CRUD permissions) still cannot bypass content review
6. `test_system_cannot_bypass` — workers cannot bypass (they submit content from Kea/Hydra pipelines, which must be reviewed)

These tests should be in a dedicated file (`tests/unit/services/test_content_review_bypass_guard.py`) to make them visible during code review. The filename signals "if you're changing bypass logic, these tests must still pass."

---

## Part 4: Extraction Pipeline Migration

The existing Hydra extraction pipeline (KnowledgeExtraction_v1.md) migrates onto the content review infrastructure.

### Pipeline Definition

```python
name = "extraction"
mode = "review_transform"  # content is transformed to match skill conventions
```

### Changes from Current Implementation

| Aspect | Before (inline) | After (async) |
|--------|-----------------|---------------|
| Execution | Synchronous in API request | ARQ job on alert worker |
| Response | Returns completed extraction | Returns pending review, client polls |
| Storage | `knowledge_extractions` table | `content_reviews` table |
| Status model | pending → completed → applied/rejected | pending → approved/flagged → applied/rejected |

### Sync Checks (Tier 1)

- `empty_content_check` — reject empty/whitespace-only documents
- `content_length_check` — reject documents > 15,000 characters

### LLM Nodes (Tier 2)

Same 6-node graph from KnowledgeExtraction_v1.md, unchanged:
classify → relevance → placement → transform/merge → validate → summarize

### Migration Strategy

1. New submissions go through `content_reviews`
2. The `knowledge_extractions` table remains read-only for historical data
3. Existing REST API (`/extractions`) becomes a thin wrapper that:
   - POST start → calls `ContentReviewService.submit_for_review(pipeline_name="extraction")`
   - GET list/detail → queries `content_reviews` filtered by `pipeline_name="extraction"`
   - POST apply/reject → delegates to `ContentReviewService`
4. Old extraction records stay in `knowledge_extractions` — no data migration needed

### Internal Callers (Critical Blocker)

Two functions in `skills_sync.py` call `start_extraction()` synchronously and immediately auto-apply the result:

| Function | Called from | Pattern |
|----------|------------|---------|
| `submit_new_files_to_hydra()` | `first_subgraph.py`, `agent_stages.py` (Kea pipeline) | Loop over files → `start_extraction()` → auto-apply if `completed` |
| `submit_content_to_hydra()` | `kea/phase1/graph.py` (LangGraph runbook composition) | Single content → `start_extraction()` → auto-apply if `completed` |

Both expect synchronous execution: they call `start_extraction()`, check `extraction.status`, and immediately call `apply_extraction()` in the same transaction. Moving extraction to async breaks this contract.

**Caller risk assessment:**

| Caller | Risk | Why |
|--------|------|-----|
| `first_subgraph.py` | Low | Only logs results, no control flow branching |
| `agent_stages.py` | Low | Only logs results, no control flow branching |
| `kea/phase1/graph.py` | **Critical** | Lines 561-591: branches on `status == "applied"`, uses `placement` to update `matching_report`. With async, this branch never executes and the UI won't know the actual placement path. |

**Resolution: Disable auto-apply, all content goes through review.**

Both functions must be updated to:
1. Call `ContentReviewService.submit_for_review(pipeline_name="extraction")` instead of `start_extraction()`
2. Return the `content_review_id` instead of the applied result
3. **Not** call `apply_extraction()` — the review pipeline handles approval
4. Kea callers must handle the async nature: log the review submission and continue without waiting for the result

**`run_phase1()` composition path fix:** The `matching_report["composed_runbook"]` field must be set to a placeholder filename (e.g., `"pending-review.md"`) and updated when the content review completes. The Kea pipeline logs the review submission and continues — the actual placement path becomes known only after the review is applied.

**`hydra_tenant_lock` removal:** The advisory lock in both functions becomes unnecessary with async submission (just creating a DB record + enqueue). Remove it from the submission path. If auto-apply is ever added to the worker, acquire the lock there instead.

This means agent-produced files are no longer instantly onboarded. They enter the content review queue and get processed by the ARQ worker. The Kea pipeline logs the submission and moves on — the skill update happens asynchronously when the review completes and is applied (manually or via auto-apply policy if we add one later).

### Breaking Change: ExtractionResponse Removed

The existing `ExtractionResponse` schema and `knowledge_extractions`-specific status model are removed. The extraction REST API returns `ContentReviewResponse` directly — same schema used by all content reviews. Clients use content review terms:

- Status: `pending`, `approved`, `flagged`, `rejected`, `applied` (not `completed`)
- Pipeline results: accessed via `pipeline_result` JSONB (not typed columns like `classification`, `relevance_score`)
- The `/extractions` router becomes a thin filter over `/content-reviews?pipeline_name=extraction`

The `knowledge_extractions` table stays for historical reads but no new records are written to it.

### Test Strategy for Async Migration

1. **Unit tests**: Mock `ContentReviewService.submit_for_review()` to return a pending review. Verify the extraction router correctly delegates.
2. **Integration tests**: Use ARQ's `MockWorker` pattern (already used for alert processing tests) to execute the content review job inline during tests.
3. **Internal caller tests**: Verify `submit_new_files_to_hydra()` and `submit_content_to_hydra()` call `ContentReviewService` instead of `KnowledgeExtractionService`, and return review IDs.

---

## Part 5: .skill Zip Import

### Manifest Schema

Every `.skill` zip must contain `manifest.json` at root:

```json
{
    "name": "My Security Skill",
    "description": "Detection rules for web application attacks",
    "version": "1.0.0",
    "cy_name": "web_attack_detection",
    "categories": ["detection", "web"],
    "config": {}
}
```

Required files: `manifest.json`, `SKILL.md`
Allowed extensions: `.md`, `.txt`, `.json`, `.py`
Max zip size: 10 MB
Max files: 100

### Import Flow

1. POST `/{tenant}/skills/import` with zip file (requires `skills.create`)
2. Open zip, validate structure (manifest.json + SKILL.md required)
3. Parse manifest → create skill via `KnowledgeModuleService.create_skill()`
4. For each file in zip:
   a. Run sync checks (AST for .py, ContentPolicy for .md/.txt, format check for all)
   b. If any file fails sync → reject entire import with details
5. For each file: submit to content review pipeline (`trigger_source="zip_import"`)
6. Return import summary with skill_id and list of review IDs

The import creates the skill immediately but documents are in `pending` status until the LLM tier completes. The UI shows import progress as reviews complete.

### Import Endpoint

```python
@router.post(
    "/import",
    response_model=ApiResponse[SkillImportResponse],
    status_code=202,  # Accepted — reviews are async
    dependencies=[Depends(require_permission("skills", "create"))],
)
async def import_skill(file: UploadFile, ...):
```

### Response Schema

```python
class SkillImportResponse(BaseModel):
    skill_id: UUID
    name: str
    documents_submitted: int
    review_ids: list[UUID]        # One per file, client can poll these
    sync_failures: list[dict]     # Files that failed sync gate (if any — means import rejected)
```

---

## File Locations

### New Files

| File | Purpose |
|------|---------|
| `agentic_orchestration/langgraph/content_review/pipeline.py` | ContentReviewPipeline protocol, run_pipeline() |
| `agentic_orchestration/langgraph/content_review/sync_checks.py` | SyncCheck type, run_sync_checks(), built-in checks |
| `agentic_orchestration/langgraph/content_review/job.py` | ARQ job: execute_content_review |
| `agentic_orchestration/langgraph/skill_validation/pipeline.py` | SkillValidationPipeline |
| `agentic_orchestration/langgraph/skill_validation/nodes.py` | assess_relevance, assess_safety, summarize |
| `agentic_orchestration/langgraph/skill_validation/prompts.py` | Validation-specific prompts |
| `services/content_review.py` | ContentReviewService |
| `services/skill_import.py` | SkillImportService |
| `services/python_script_analyzer.py` | AST-based Python static analyzer |
| `models/content_review.py` | ContentReview SQLAlchemy model |
| `schemas/content_review.py` | Pydantic schemas for review API |
| `schemas/skill_import.py` | Manifest + import response schemas |
| `routers/content_reviews.py` | Content review REST API |
| `auth/skill_guard.py` | KU skill-ownership check |
| `migrations/flyway/sql/V088__create_content_reviews.sql` | Migration |

### Modified Files

| File | Change |
|------|--------|
| `auth/permissions.py` | Add `skills` resource to permission matrix |
| `routers/skills.py` | Swap to `skills.*` permissions, add `/import` endpoint |
| `routers/knowledge_units.py` | Add skill-ownership guard |
| `routers/knowledge_extraction.py` | Swap to `skills.*` permissions, delegate to ContentReviewService |
| `services/knowledge_extraction.py` | Delegate to ContentReviewService for new submissions |
| `alert_analysis/worker.py` | Register `execute_content_review` job |

### Reused As-Is

| File | What's Reused |
|------|---------------|
| `agentic_orchestration/langgraph/substep/executor.py` | SubStep executor |
| `agentic_orchestration/langgraph/substep/definition.py` | SubStep, ValidationResult |
| `agentic_orchestration/langgraph/skills/retrieval.py` | SkillsIR retrieve() |
| `agentic_orchestration/langgraph/skills/store.py` | ResourceStore |
| `agentic_orchestration/langgraph/skills/db_store.py` | DatabaseResourceStore |
| `agentic_orchestration/langgraph/config.py` | LLM + store factories |
| `agentic_orchestration/content_policy.py` | check_suspicious_content() |
| `agentic_orchestration/langgraph/knowledge_extraction/` | Entire extraction graph (unchanged, wrapped as pipeline) |

---

## Implementation Phases

### Phase 6: Content Review Infrastructure + RBAC + Extraction Migration

1. Admin-only RBAC for skills (permission matrix, router swaps, KU guard)
2. `content_reviews` table + model + schemas
3. ContentReviewPipeline protocol + sync checks framework
4. ContentReviewService (submit, complete, apply, reject)
5. ARQ job (execute_content_review) registered in alert worker
6. Content reviews REST API
7. Extraction pipeline wrapped as ContentReviewPipeline
8. Extraction router delegated to ContentReviewService
9. Tests: RBAC, content review lifecycle, extraction migration

### Phase 7: Skill Validation Pipeline + Zip Import

1. Python script static analyzer
2. Skill validation pipeline (nodes, prompts, sync checks)
3. Wire validation into all entry points (KU mutations, document links, staging)
4. .skill zip import service + endpoint
5. Tests: analyzer, validation pipeline, zip import, end-to-end

---

## Key Design Decisions

1. **One table, one API, one UI** for all content reviews — extraction and validation are just different pipelines on the same infrastructure.

2. **Two pipeline modes**: `review` (judge only) and `review_transform` (judge + reshape). The `transformed_content` column is NULL for review-only.

3. **Sync gate is hard reject** — if deterministic checks fail, no record is created, the request gets 422 immediately. LLM resources are not wasted on obviously bad content.

4. **Extraction moves to async** — existing inline execution migrates to ARQ worker. The extraction REST API becomes a thin wrapper.

5. **Owner bypass** skips LLM tier but still runs sync checks. Protects against accidental injection even from privileged users.

6. **Historical data preserved** — `knowledge_extractions` table stays read-only. No data migration.
