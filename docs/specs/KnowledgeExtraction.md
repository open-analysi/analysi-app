+++
version = "1.0"
date = "2026-01-15"
status = "active"

[[changelog]]
version = "1.0"
date = "2026-01-15"
summary = "Document ingestion pipeline (Project Hydra)"
+++

# Knowledge Extraction Pipeline - v1

## Overview

The Knowledge Extraction Pipeline takes arbitrary security-related documents and ingests them as new resources into skills — primarily the `runbooks-manager` skill. It bridges the gap between raw source material (SOAR playbooks, internet articles, detection rule snippets, analyst write-ups) and structured, reusable knowledge that skills can reference.

**Problem**: Today, adding new knowledge to a skill requires a human to manually read a document, decide where it belongs, reformat it, and place it in the right namespace. This is slow and doesn't scale.

**Solution**: A LangGraph pipeline that classifies documents, determines placement, transforms content to match the target namespace's format, and produces a preview for human approval before committing.

## Integration Points

- **Input**: Raw document (markdown or JSON string) + source metadata
- **Output**: Preview of transformed content + proposed placement, then committed KUDocument on approval
- **Skills System**: Uses SkillsIR to read skill structure and existing content for context
- **Storage**: DatabaseResourceStore for writing; HybridResourceStore for reading
- **Existing Specs**: Builds on LangGraphBuildingBlocks_v1.md (SubStep pattern, SkillsIR)

## Relationship to Project Kea

This pipeline is **not part of Kea**. They are independent systems with a shared dependency:

```
                         ┌─────────────────────┐
                         │  runbooks-manager    │
                         │  skill               │
                         │  (repository/,       │
                         │   common/, etc.)     │
                         └──────▲───────▲───────┘
                                │       │
                         reads  │       │  writes
                                │       │
               ┌────────────────┘       └────────────────┐
               │                                         │
   ┌───────────┴───────────┐             ┌───────────────┴──────────┐
   │  Project Kea          │             │  Knowledge Extraction    │
   │  Phase 1              │             │  Pipeline                │
   │                       │             │                          │
   │  Matches/composes     │             │  Ingests new documents   │
   │  runbooks for alerts  │             │  into the skill          │
   └───────────────────────┘             └──────────────────────────┘
```

- **Kea Phase 1** reads from runbooks-manager to match alerts to runbooks. It never writes to the skill.
- **Knowledge Extraction** writes to runbooks-manager by ingesting new documents. It is triggered manually by users, not by alerts.
- Over time, Knowledge Extraction enriches the skill, which improves Kea Phase 1's matching coverage — but there is no direct coupling between them.

## Output Format: Always Markdown

Regardless of input format (JSON SOAR playbook, plain text article, structured detection rule), **all extracted output documents are markdown** following the conventions already established in the runbooks-manager skill:

- **Runbooks** (`repository/`): YAML frontmatter + numbered investigation steps with ★ critical markers + WikiLinks to common patterns. See existing runbooks like `sql-injection-detection.md` for the canonical format.
- **Sub-runbooks** (`common/*`): No frontmatter, `###` step headers, `${alert.field}` variables, embeddable via WikiLink. See `common/universal/alert-understanding.md` and `common/by_source/waf-siem-evidence.md`.
- **References** (`references/`): Standard markdown documentation. See `references/building/format-specification.md`.

This means a JSON SOAR playbook gets **transformed into markdown** with the same structure as a hand-written runbook. The source format is preserved only in the provenance record (see Provenance Tracking below), never in the output document itself.

## Scope

### In Scope (v1)

- Accept markdown, JSON, or plain text documents as input
- Classify document type and determine target namespace within a skill
- Transform content to **markdown** matching the target namespace's established conventions
- Preview extraction results before committing
- Persist approved extractions as KUDocuments linked to the skill
- Track provenance in the Knowledge Dependency Graph (source document → extracted document)
- Support runbooks-manager skill namespaces (repository, common/*, references)
- Rebuild indices after committing a new runbook

### Out of Scope (v1)

- Batch ingestion (multiple documents at once)
- Automatic ingestion without human preview/approval
- Skills other than runbooks-manager (architecture supports it, but classification prompts are skill-specific)
- UI for the extraction workflow (API-only for now)
- Duplicate detection (submitting the same document twice creates two extraction records)

---

## Architecture

### Technology

- **Orchestration**: LangGraph `StateGraph` with SubStep pattern (see LangGraphBuildingBlocks_v1.md)
- **Context Retrieval**: SkillsIR for progressive loading of skill content
- **LLM**: Claude Sonnet for all nodes. Model is configured via a single `LLM_MODEL` parameter passed to `build_extraction_graph()`, making it easy to change per-node in the future (e.g., Haiku for classification, Sonnet for transform)
- **LLM Output**: Pydantic structured output models per step
- **Storage**: DatabaseResourceStore for writes, HybridResourceStore for reads

### Input Constraints

- **Maximum input size**: 15,000 characters (~3 pages of text). Enforced at the API layer before invoking the graph. Returns 400 if exceeded.
- **Supported formats**: `markdown`, `json`, `text`. The `source_format` field is informational — it tells the LLM what to expect but doesn't trigger different code paths.
- **Encoding**: UTF-8 only.

### How the Skill Guides Extraction

The extraction pipeline doesn't use hardcoded format rules. Instead, it loads **real files from the target skill** as context for the LLM. The existing files in the runbooks-manager skill *are* the format specification — the LLM learns the expected structure by seeing examples.

Each node loads different files for different reasons:

| Node | Files Loaded via SkillsIR | Purpose |
|------|--------------------------|---------|
| 1. classify | None | Classification is based on the input document alone |
| 2. relevance | `SKILL.md` + full file tree | Understand what the skill covers, judge if the input fits |
| 3. placement | File tree + 1-2 files from each candidate namespace | See naming conventions, existing coverage, decide create vs merge |
| 4a. transform | **Format exemplars**: 1-2 files from target namespace + `references/building/format-specification.md` | The LLM copies their structure — exemplars define the output format |
| 4b. merge | Target file (mandatory) + 1 sibling from same namespace | Full existing content to merge into, sibling for style consistency |
| 5. validate | `references/building/quality-guide.md` (for LLM check) | Quality criteria for the coherence check |

**Concrete example — SOAR playbook → new runbook (`repository/`):**

The transform node (4a) receives this context from SkillsIR:

```
── Context loaded from runbooks-manager skill ──

1. Format specification (always loaded for transforms):
   references/building/format-specification.md
   → Defines YAML frontmatter fields, step format, ★ markers, WikiLink syntax

2. Format exemplar #1:
   repository/sql-injection-detection.md
   → Shows: frontmatter with detection_rule/alert_type/mitre_tactics,
     investigation steps with ### N. Step Name ★,
     WikiLinks: ![[common/universal/alert-understanding.md]]

3. Format exemplar #2:
   repository/command-injection-detection.md
   → Shows: same structure, different content, reinforces the pattern
```

The LLM prompt says: *"Transform the input document into the same markdown format as the exemplar files. Your output must be indistinguishable from these examples."*

**Concrete example — blog article → sub-runbook (`common/by_source/`):**

```
── Context loaded from runbooks-manager skill ──

1. Format specification:
   references/building/sub-runbook-patterns.md
   → Defines: no frontmatter, ### step headers, ${alert.field} variables

2. Format exemplar:
   common/by_source/waf-siem-evidence.md
   → Shows: sub-runbook steps with Integration hints, Output fields

3. (Only 1 exemplar available in this namespace currently)
```

**What if the target namespace is empty?** Some namespaces (e.g., `common/by_type/`) have no files yet. In this case, SkillsIR loads:
1. The format specification from `references/` (always available)
2. Files from the closest related namespace as fallback exemplars (e.g., `common/by_source/` for `common/by_type/`, since both are sub-runbook formats)
3. The `templates/runbook-template.md` if the target is `repository/`

The fallback strategy ensures the LLM always has at least one concrete example, even for empty namespaces.

### Pipeline Steps (LangGraph)

The pipeline is a 5-step LangGraph `StateGraph`. Each step is a SubStep (LLM call with structured output) except where noted. Steps 2-4 use SkillsIR to load relevant skill content into context.

| Step | Node | Type | SkillsIR | Structured Output | Description |
|------|------|------|----------|-------------------|-------------|
| 1 | `classify_document` | LLM | No | `DocumentClassification` | Determine what kind of security knowledge the document contains |
| 2 | `assess_relevance` | LLM | Yes (SKILL.md + tree) | `RelevanceAssessment` | Is this document useful for this skill? Gate: rejects irrelevant docs |
| 3 | `determine_placement` | LLM | Yes (target namespace samples) | `PlacementDecision` | Choose namespace, filename, and create-vs-merge strategy |
| 4a | `extract_and_transform` | LLM | Yes (target namespace examples) | string (markdown) | **Create path**: Transform raw document into new skill-format markdown |
| 4b | `merge_with_existing` | LLM | Yes (existing target file) | `MergeResult` | **Merge path**: Merge new knowledge into existing document, preserving original |
| 5 | `validate_output` | Deterministic + LLM | No | `ValidationResult` | Check structural and content quality |

```
┌──────────────────────────────────────────────────────────────────┐
│                    knowledge_extraction_graph                      │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  1. classify_document                                              │
│     Input:  content, source_format, source_description             │
│     Output: DocumentClassification                                 │
│     LLM:    "What kind of security knowledge is this?"             │
│                                                                    │
│                           │                                        │
│                           ▼                                        │
│                                                                    │
│  2. assess_relevance                                               │
│     Input:  content + classification + SKILL.md + tree             │
│     Output: RelevanceAssessment                                    │
│     Gate:   is_relevant == false → status=rejected → END           │
│                                                                    │
│                           │                                        │
│                 ┌─────────┴──────────┐                             │
│                 │ relevant           │ not relevant                 │
│                 ▼                    ▼                              │
│                                 REJECTED (END)                     │
│  3. determine_placement                                            │
│     Input:  content + classification + file tree + samples         │
│     Output: PlacementDecision (includes merge_strategy)            │
│                                                                    │
│                           │                                        │
│              ┌────────────┴────────────┐                           │
│              │ create_new              │ merge_with_existing        │
│              ▼                         ▼                           │
│                                                                    │
│  4a. extract_and_transform    4b. merge_with_existing              │
│     Input:  content +            Input:  content +                 │
│             placement +                  existing_doc +            │
│             examples                     placement                 │
│     Output: new markdown         Output: MergeResult               │
│                                    { merged_content,               │
│                                      original_content,             │
│                                      change_summary }              │
│              │                         │                           │
│              └────────────┬────────────┘                           │
│                           │                                        │
│                           ▼                                        │
│                                                                    │
│  5. validate_output                                                │
│     Input:  content (new or merged) + classification               │
│     Checks: YAML frontmatter, ★ markers, WikiLinks,               │
│             token limits, content coherence                         │
│                                                                    │
│                           │                                        │
│                           ▼                                        │
│                                                                    │
│              status = "completed"                                  │
│              Return ExtractionPreview                              │
│                                                                    │
└──────────────────────────────────────────────────────────────────┘
```

### Data Flow (Full)

```
Step 0 (prerequisite): Import document via existing API
  POST /{tenant}/knowledge-units/documents
    { name, content, doc_format, ... }
    → Returns document_id

Step 1: Start extraction
  POST /{tenant}/skills/{skill_id}/extractions
    { document_id }
          │
          ▼
   1. Load source KUDocument by document_id
   2. Create knowledge_extraction record (status=pending)
   3. Run knowledge_extraction_graph (steps 1-5)
   4. Update extraction record with results (status=completed|rejected)
   5. Return ExtractionPreview (synchronous — blocks until graph completes)

Step 2: Apply extraction
  POST /{tenant}/skills/{skill_id}/extractions/{extraction_id}/apply
          │
          ▼
   1. Create or update KUDocument in skill namespace (always markdown)
   2. KDG edge: Skill ──(CONTAINS)──▶ extracted doc (if new)
   3. KDG edge: extracted doc ──(DERIVED_FROM)──▶ source doc
   4. Trigger index rebuild for skill
   5. Update extraction record (status=applied)
```

### Read-Only Until Apply

**The extraction pipeline is entirely read-only.** From `POST /extractions` through to `status: "completed"`, the only write is a single row in the `knowledge_extractions` table. No KUDocuments are created, no KDG edges are added, no skill content is modified, and no indices are rebuilt.

All mutations to the skill happen **only** when the user explicitly calls `/apply`:

| Mutation | When |
|----------|------|
| New KUDocument created in skill namespace | Apply (create path) |
| Existing KUDocument content updated | Apply (merge path) |
| KDG CONTAINS edge created | Apply (create path only) |
| KDG DERIVED_FROM edge created | Apply (both paths) |
| Skill index rebuild triggered | Apply (both paths) |

Rejecting or abandoning an extraction has **zero side effects** — the source document, the skill, and the knowledge graph are all untouched.

### Why Two Endpoints

This two-phase design (extract → review → apply/reject) is deliberate:
1. The LLM may misclassify documents or choose wrong placements
2. Transformed content needs human quality review
3. Skill content affects production alert analysis — changes should be deliberate
4. The user may want to edit the content before applying

### Synchronous Execution

The `start_extraction` endpoint runs synchronously — the HTTP request blocks until all LangGraph steps complete (expected: 20-60 seconds depending on document size). This is acceptable for v1 because:
- Extraction is a manual, low-volume user action (not triggered by alerts)
- The pipeline is 4-5 LLM calls — not minutes-long like Kea workflow generation
- Simplifies implementation: no polling, no background workers, no status tracking

**TODO:** If extraction latency becomes a problem (large documents, added retry loops in v2), switch to async: return 202 with extraction_id, poll via `GET /extractions/{id}` until status != `pending`.

---

## API Design

### Workflow

1. User imports a document into the system: `POST /knowledge-units/documents` (existing API)
2. User starts extraction from that document into a skill: `POST /skills/{skill_id}/extractions`
3. User reviews the preview, optionally edits, then applies: `POST /skills/{skill_id}/extractions/{id}/apply`

### Start Extraction

```
POST /v1/{tenant_id}/skills/{skill_id}/extractions
```

**Request Body:**
```json
{
  "document_id": "uuid — the existing KUDocument to extract knowledge from"
}
```

The source document's content, format, and metadata are read from the KUDocument record. No need to duplicate `content`, `source_format`, or `source_description` — they already live on the document.

**Response (201):**
```json
{
  "extraction_id": "uuid",
  "skill_id": "uuid",
  "document_id": "uuid (the source document)",
  "status": "completed | rejected",
  "classification": {
    "doc_type": "new_runbook | source_evidence_pattern | ...",
    "confidence": "high | medium | low",
    "reasoning": "string"
  },
  "relevance": {
    "is_relevant": true,
    "applicable_namespaces": ["repository/", "common/by_source/"],
    "reasoning": "string"
  },
  "placement": {
    "target_namespace": "repository/",
    "target_filename": "palo-alto-command-injection-detection.md",
    "merge_strategy": "create_new | merge_with_existing",
    "merge_target": "null | path to existing file",
    "reasoning": "string"
  },
  "transformed_content": "string (new or merged markdown content)",
  "merge_info": {
    "original_content": "string (existing doc before merge, for diff)",
    "change_summary": "string (what was added/changed)",
    "sections_added": ["list of new sections"],
    "sections_modified": ["list of changed sections"]
  },
  "validation": {
    "valid": true,
    "errors": [],
    "warnings": ["No MITRE tactics specified — consider adding them"]
  },
  "created_at": "ISO 8601"
}
```

- If `status` is `"rejected"`, only `classification` and `relevance` fields are populated.
- `merge_info` is `null` when `placement.merge_strategy` is `"create_new"`.
- When `merge_strategy` is `"merge_with_existing"`, the user can diff `merge_info.original_content` against `transformed_content` to review changes before applying.

### Apply Extraction

```
POST /v1/{tenant_id}/skills/{skill_id}/extractions/{extraction_id}/apply
```

Transitions status from `completed` → `applied`. Creates the skill document and KDG edges.

**Optional Request Body (overrides):**
```json
{
  "content": "optional — edited markdown content (replaces transformed_content)",
  "target_namespace": "optional — override namespace (e.g., common/by_source/)",
  "target_filename": "optional — override filename"
}
```

All overrides are optional. If omitted, the pipeline's decisions are used as-is.

**Response (201):**
```json
{
  "document_id": "uuid (the new or updated KUDocument in the skill)",
  "skill_id": "uuid",
  "namespace_path": "repository/palo-alto-command-injection-detection.md",
  "extraction_id": "uuid"
}
```

**Errors:**
- 404 if extraction not found
- 409 if status is not `completed` (already applied, already rejected, still pending, or failed)

### Reject Extraction

```
POST /v1/{tenant_id}/skills/{skill_id}/extractions/{extraction_id}/reject
```

Transitions status from `completed` → `rejected`. No skill documents or KDG edges are created. The source document is unaffected.

**Optional Request Body:**
```json
{
  "reason": "optional — why this extraction was rejected"
}
```

**Response (200):**
```json
{
  "extraction_id": "uuid",
  "status": "rejected",
  "reason": "string or null"
}
```

**Errors:**
- 404 if extraction not found
- 409 if status is not `completed`

### List Extractions

```
GET /v1/{tenant_id}/skills/{skill_id}/extractions
```

Returns history of extractions for this skill (paginated). Filterable by `?status=completed&document_id=uuid`.

### Get Extraction

```
GET /v1/{tenant_id}/skills/{skill_id}/extractions/{extraction_id}
```

Returns full extraction details (same as start extraction response).

---

## Extraction Lifecycle

The extraction follows a state machine pattern consistent with existing models in the codebase (TaskBuildingRun, WorkflowRun). The key difference is the **human review gate** between `completed` and `applied`.

```
                    ┌─────────────────────────────────┐
                    │         STATE MACHINE            │
                    ├─────────────────────────────────┤
                    │                                   │
   POST /extractions│                                   │
   { document_id }  │     ┌──────────┐                  │
   ─────────────────┼────▶│ pending  │                  │
                    │     └────┬─────┘                  │
                    │          │ graph runs (sync)       │
                    │          │                         │
                    │     ┌────┴─────┐                  │
                    │     │          │                   │
                    │     ▼          ▼                   │
                    │ ┌────────┐ ┌────────┐             │
                    │ │completed│ │ failed │ (graph err) │
                    │ └──┬───┬─┘ └────────┘             │
                    │    │   │                           │
                    │    │   │  ◄── HUMAN REVIEW GATE    │
                    │    │   │                           │
                    │    ▼   ▼                           │
                    │ ┌──────┐ ┌────────┐               │
                    │ │applied│ │rejected│               │
                    │ └──────┘ └────────┘               │
                    │   │                                │
                    │   │ creates/updates skill doc      │
                    │   │ + KDG edges + index rebuild    │
                    │                                    │
                    └─────────────────────────────────┘
```

**State transitions:**

| From | To | Trigger | Side Effects |
|------|-----|---------|-------------|
| — | `pending` | `POST /extractions` | Creates extraction record |
| `pending` | `completed` | Graph finishes successfully | Stores classification, placement, transformed_content |
| `pending` | `completed` (auto-rejected) | Graph rejects as irrelevant | Stores classification + relevance only |
| `pending` | `failed` | Graph error (LLM failure, timeout) | Stores error details |
| `completed` | `applied` | `POST /extractions/{id}/apply` | Creates skill doc, KDG edges, index rebuild |
| `completed` | `rejected` | `POST /extractions/{id}/reject` | Stores rejection reason, no side effects |

**Terminal states:** `applied`, `rejected`, `failed`. No transitions out of these.

**Note on auto-rejection:** When the LLM determines a document is not relevant (step 2), the extraction reaches `completed` status with `relevance.is_relevant: false`. This is different from user rejection — the pipeline completed successfully, it just determined the document doesn't belong. The user can still see the reasoning and disagree by starting a new extraction.

---

## Database

### Table: `knowledge_extractions`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK, auto-generated |
| tenant_id | VARCHAR | Multi-tenancy |
| skill_id | UUID | FK to components (the target skill) |
| document_id | UUID | FK to components (the source KUDocument) |
| status | ENUM | `pending`, `completed`, `rejected`, `applied`, `failed` |
| classification | JSONB | DocumentClassification output |
| relevance | JSONB | RelevanceAssessment output (null if failed before this step) |
| placement | JSONB | PlacementDecision output (null if rejected) |
| transformed_content | TEXT | Final transformed content — new or merged markdown (null if rejected) |
| merge_info | JSONB | MergeResult details: original_content, change_summary, sections_added/modified (null if create_new or rejected) |
| validation | JSONB | ValidationResult output |
| applied_document_id | UUID | FK to components (the KUDocument created/updated on apply), null until applied |
| rejection_reason | TEXT | User-provided reason when rejected, null otherwise |
| error_message | TEXT | Error details if graph failed, null otherwise |
| created_at | TIMESTAMPTZ | |
| applied_at | TIMESTAMPTZ | Null until applied |
| rejected_at | TIMESTAMPTZ | Null until rejected |

**Note:** The source document's content, format, and description are not duplicated here — they live on the KUDocument referenced by `document_id`. This avoids data duplication and keeps the source document as the single source of truth.

**Indexes:**
- `(tenant_id, skill_id)` — list extractions per skill
- `(tenant_id, status)` — filter by status

**Note:** This table does NOT use partitioning. Extraction volume is low (manual user action) and doesn't require time-based partitioning.

---

## LangGraph Pipeline

### State Definition

```python
class ExtractionState(TypedDict):
    # Input (provided by caller)
    document_id: str              # Source KUDocument ID
    content: str                  # Loaded from the KUDocument
    source_format: str            # From KUDocument.doc_format
    source_description: str       # From KUDocument.name or description
    skill_id: str
    tenant_id: str

    # Intermediate (populated by nodes)
    store: ResourceStore
    skill_name: str
    skill_tree: list[str]
    classification: dict | None
    relevance: dict | None
    placement: dict | None
    transformed_content: str | None
    merge_info: dict | None       # MergeResult if merge path, else None
    validation: dict | None

    # Output
    status: str  # completed | rejected | failed
```

The service layer loads the KUDocument by `document_id` and populates `content`, `source_format`, and `source_description` before invoking the graph. The graph itself does not access the database — it receives everything it needs through state.

### Node 1: classify_document

**Purpose:** Determine what kind of security knowledge this document contains.

**Input:** content, source_format, source_description

**Output:** DocumentClassification

```python
class DocumentClassification(BaseModel):
    doc_type: Literal[
        "new_runbook",
        "source_evidence_pattern",
        "attack_type_pattern",
        "evidence_collection",
        "universal_pattern",
        "reference_documentation",
    ]
    confidence: Literal["high", "medium", "low"]
    reasoning: str
```

**Classification guide (included in prompt):**

| doc_type | What it looks like | Target |
|----------|-------------------|--------|
| `new_runbook` | Full investigation procedure, SOAR playbook, step-by-step triage guide | `repository/` |
| `source_evidence_pattern` | How to collect/analyze evidence from a specific source (WAF, EDR, SIEM) | `common/by_source/` |
| `attack_type_pattern` | Base investigation pattern for an attack family (brute force, phishing) | `common/by_type/` |
| `evidence_collection` | Generic evidence collection technique (threat intel, network capture) | `common/evidence/` |
| `universal_pattern` | Pattern applicable to all investigations (alert understanding, final analysis) | `common/universal/` |
| `reference_documentation` | Guidance docs, scoring algorithms, format specs | `references/` |

**No SkillsIR needed** — classification is based on the document content alone.

### Node 2: assess_relevance

**Purpose:** Determine if this document contains knowledge useful for the runbooks-manager skill.

**Input:** content, classification, skill SKILL.md + file tree (via SkillsIR)

**Output:** RelevanceAssessment

```python
class RelevanceAssessment(BaseModel):
    is_relevant: bool
    applicable_namespaces: list[str]  # e.g., ["repository/", "common/by_source/"]
    reasoning: str
```

**Routing:** If `is_relevant == False` → set `status = "rejected"` → END.

**SkillsIR context:** Load SKILL.md + file tree to understand what the skill already covers. The LLM checks for:
- Does this document cover security investigation knowledge?
- Does it overlap with existing content? (overlap is OK if it adds new perspective)
- Would it be useful for building or improving runbooks?

### Node 3: determine_placement

**Purpose:** Choose exact namespace path and filename.

**Input:** content, classification, relevance, skill file tree + sample content from target namespace

**Output:** PlacementDecision

```python
class PlacementDecision(BaseModel):
    target_namespace: str           # e.g., "repository/"
    target_filename: str            # e.g., "brute-force-rdp-detection.md"
    merge_strategy: Literal["create_new", "merge_with_existing"]
    merge_target: str | None        # existing file path to merge with (e.g., "common/by_source/waf-siem-evidence.md")
    reasoning: str
```

**Merge strategy selection:** The LLM decides based on:
- **`create_new`**: No existing document covers this topic, or the input is different enough to warrant a separate file
- **`merge_with_existing`**: An existing document covers the same topic and the input adds complementary knowledge (new steps, alternative approaches, additional detail). The `merge_target` identifies the existing file path within the skill.

**SkillsIR context:** Load 1-2 example files from the target namespace so the LLM can see naming conventions and content format.

**Naming rules (included in prompt):**
- `repository/`: `{detection-rule-slug}.md` (kebab-case, descriptive)
- `common/by_source/`: `{source}-{pattern-name}.md` (e.g., `edr-process-evidence.md`)
- `common/by_type/`: `{attack-type}-base.md` (e.g., `brute-force-base.md`)
- `common/evidence/`: `{technique-name}.md` (e.g., `network-traffic-analysis.md`)
- `references/`: `{topic}/{document-name}.md`

### Node 4: extract_and_transform

**Purpose:** Transform the raw document into **markdown** matching the target namespace's established format. The output must be indistinguishable from a hand-written document already in the skill.

**Input:** content, source_format, classification, placement, example content from target namespace

**Output:** TransformedContent (a markdown string — always markdown, regardless of input format)

**Core principle:** The LLM is given 1-2 existing files from the target namespace as examples and must produce output that follows the same structure, tone, and conventions. This is format-by-example, not format-by-rules.

**Transformation rules by doc_type:**

**For `new_runbook` (→ `repository/`):**
- Add YAML frontmatter (detection_rule, alert_type, subcategory, source_category, mitre_tactics, integrations_required/optional)
- Structure as investigation steps with `### N. Step Name ★` format
- Mark 3-5 critical steps with ★
- Replace source-specific details with generic patterns
- Use WikiLinks for common patterns: `![[common/universal/alert-understanding.md]]`
- Keep total size under 800 tokens
- JSON inputs (SOAR playbooks): extract action sequence → convert to investigation steps, map tool actions to integration hints, discard SOAR-specific metadata (action IDs, connector configs)

**For `source_evidence_pattern` (→ `common/by_source/`):**
- No YAML frontmatter
- Structure as sub-runbook steps that can be embedded via WikiLink
- Use `${alert.field}` variable syntax for dynamic values
- Focus on evidence collection actions, not full investigation

**For `attack_type_pattern` (→ `common/by_type/`):**
- No YAML frontmatter
- Structure as base investigation pattern steps
- Generic enough to apply across detection rules of the same attack family

**For `evidence_collection` (→ `common/evidence/`):**
- No YAML frontmatter
- Focus on a single evidence gathering technique
- Include Integration hints (e.g., `- Integration: threat_intel`)

**For `universal_pattern` (→ `common/universal/`):**
- No YAML frontmatter
- Must be applicable across all investigation types
- High bar — most documents are NOT universal

**For `reference_documentation` (→ `references/`):**
- Standard markdown
- Preserve technical detail; organize with clear headings

**For all types:**
- Output is always markdown
- Strip source-specific identifiers (vendor product names that are too specific)
- Generalize to be reusable across multiple alerts/scenarios
- Preserve technical accuracy — never hallucinate investigation steps

**SkillsIR context:** Load 1-2 existing files from the target namespace as format examples. The LLM prompt includes: "Your output must follow the same markdown structure as these examples."

### Node 4b: merge_with_existing (alternate path)

**Purpose:** Merge new knowledge from the input document into an existing skill document, producing an enhanced version while preserving the original for diff review.

**When:** `placement.merge_strategy == "merge_with_existing"`

**Input:** content, classification, placement, existing document content (loaded via `placement.merge_target`)

**Output:** MergeResult

```python
class MergeResult(BaseModel):
    merged_content: str        # The new version of the document (markdown)
    original_content: str      # The existing document before merge (unchanged, for diff)
    change_summary: str        # Human-readable summary of what was added/changed
    sections_added: list[str]  # New sections introduced
    sections_modified: list[str]  # Existing sections that were enhanced
```

**Merge principles:**
- The merged document must maintain the same format as the original (if the original is a sub-runbook, the merged version is too)
- New knowledge is **additive** — existing steps and patterns are preserved, new ones are inserted at appropriate positions
- If the input contradicts existing content, both perspectives are kept and the contradiction is noted in `change_summary`
- The `original_content` is returned unchanged so the user can diff the two versions in the preview
- YAML frontmatter (if present) is updated to reflect new coverage (e.g., additional `mitre_tactics`)

**SkillsIR context:** Load the target file (mandatory) + 1-2 sibling files from the same namespace for style consistency.

**Example:** An article about EDR lateral movement evidence is merged into the existing `common/by_source/edr-lateral-movement-evidence.md`. The merge adds two new investigation steps while preserving the original three.

### Node 5: validate_output

**Purpose:** Check the transformed content meets quality standards.

**Output:** ValidationResult

```python
class ValidationResult(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]
```

**Deterministic checks (for runbooks):**
- YAML frontmatter parses correctly
- Required frontmatter fields present (detection_rule, alert_type, subcategory, source_category)
- At least one step marked with ★
- WikiLink paths reference files that exist in the skill tree
- Content is under 1000 tokens

**Deterministic checks (for sub-runbooks):**
- No YAML frontmatter (sub-runbooks don't have it)
- Contains at least one `###` step header
- Under 300 tokens

**LLM check (all types):**
- Content is technically coherent
- No hallucinated tool names or integration references
- Consistent with existing skill content style

**On validation failure:** Return with `valid: false` and errors. The user can see what went wrong. We do NOT auto-retry in v1 — the user can edit and re-apply.

---

## Conditional Routing

```
classify_document
      │
      ▼
assess_relevance
      │
      ├── not relevant → status="rejected" → END
      │
      ▼
determine_placement
      │
      ├── merge_strategy == "create_new"
      │     │
      │     ▼
      │   extract_and_transform
      │     │
      │     ▼
      │   validate_output ──────────────────────┐
      │                                          │
      ├── merge_strategy == "merge_with_existing"│
      │     │                                    │
      │     ▼                                    │
      │   merge_with_existing                    │
      │     │                                    │
      │     ▼                                    │
      │   validate_output ◄─────────────────────┘
      │     │
      │     ▼
      status="completed" → END (return preview)
```

Two branches after `determine_placement`:
- **Create new**: the default path — transforms the document into a new skill file
- **Merge with existing**: when the LLM determines the input should be merged into an existing document — produces a merged version while preserving the original for diff review

No retry loops in v1. Validation failures are surfaced to the user for manual correction.

---

## Transformation Guidelines

These rules govern the **extract_and_transform** (Node 4a) and **merge_with_existing** (Node 4b) prompts. They are derived from proven patterns in the `ld-runbook-agent` and generalized for arbitrary source material.

### Strip vs Keep Framework

The transform node must systematically decide what to strip and what to keep from the source document. The following table defines the policy:

| Category | Action | Examples |
|----------|--------|----------|
| Specific IPs, domains, hashes | **Strip** — replace with symbolic placeholders | `192.168.1.50` → `<source_ip>`, `evil.com` → `<suspicious_domain>` |
| Specific tool names / vendor UIs | **Strip** — replace with generic integration category | "Click VirusTotal tab" → "Query threat intelligence for the indicator" |
| Ticket IDs, case numbers, analyst names | **Strip** — remove entirely | "Case #4521", "Analyst: John" |
| Investigation procedures and decision logic | **Keep** — this is the core knowledge | "If the IP is internal, check lateral movement indicators" |
| Integration categories (SIEM, EDR, TI) | **Keep** — use generic category names | "Query SIEM for related events in ±15 min window" |
| Concrete field references | **Keep as examples only** — mark clearly | `e.g., process.name, file.hash` in an example block |
| Thresholds, timeframes, severity logic | **Keep** — these encode expert judgment | "If >5 failed logins in 10 minutes, escalate" |
| Data flow between steps | **Keep** — use namespace conventions | `alert.source_ip`, `outputs.step_1.reputation_score` |

### One-Case-to-General-Pattern Principle

Source documents typically describe a single investigation or playbook. The transform node must **generalize** the content:

- Extract the _investigation methodology_, not the specific case narrative
- Convert case-specific findings into conditional decision branches ("if X, then Y")
- Preserve the _structure_ of the investigation (order of steps, escalation criteria) while removing case-specific conclusions
- When the source contains only one example of a pattern, note that the pattern needs validation against more cases (see Criticality Marking below)

### Criticality Marking for Single-Source Inputs

When knowledge comes from a single source document, the transform node should:

- Use existing skill content as a "second opinion" — if the pattern aligns with something already in the skill, mark it with higher confidence
- For novel patterns not corroborated by existing skill content, add a metadata note: `<!-- source: single-document, needs-validation -->`
- Never assert universal applicability from a single example

### Sub-Runbook Identification

When the source document contains distinct investigation paths or reusable sub-procedures, the transform node should:

- Identify self-contained investigation segments that could serve as sub-runbooks
- Use `[[WikiLink]]` references following the existing convention in `repository/` runbooks
- Only create sub-runbook references when the segment is genuinely reusable across multiple parent runbooks
- Place sub-runbooks in the appropriate `common/` namespace based on their nature (evidence patterns → `common/evidence/`, source-specific → `common/by_source/`)

### Data Flow Namespace Conventions

Extracted runbooks must use the established data flow namespaces for variable references:

- `alert.*` — fields from the triggering alert (e.g., `alert.source_ip`, `alert.severity`)
- `outputs.<step_name>.*` — results from previous investigation steps
- `params.*` — configurable parameters (thresholds, timeframes)

These conventions ensure extracted runbooks are compatible with the Kea execution engine.

### Query Fabrication Guard

The transform node must **never invent queries or commands** not present in the source document. Specifically:

- If the source describes "check the IP reputation", the output must say "query threat intelligence for IP reputation" — not fabricate a specific SPL query or API call
- Integration-specific query syntax (SPL, KQL, API endpoints) is only included if the source document explicitly contains it
- When the source references a tool capability without a concrete query, use the generic integration category form: "Query [SIEM/EDR/TI] for [what]"

### Merge-Specific Guidelines (Node 4b)

When merging into an existing document:

- **Preserve existing structure** — add to existing sections rather than reorganizing
- **Annotate additions** — new content from the merge should be identifiable (the `change_summary` in `MergeResult` tracks this)
- **No deletions** — merge only adds or augments; it never removes existing content
- **Conflict resolution** — if the source contradicts existing content, add the new perspective as an alternative rather than replacing (e.g., "Alternative approach from [source]: ...")
- **The original document is preserved** — `MergeResult.original_content` stores the pre-merge version for diff review

---

## Provenance Tracking via Knowledge Dependency Graph

Every applied extraction creates a **provenance chain** visible in the Knowledge Dependency Graph (KDG). This answers the question: "Where did this knowledge come from?"

### Source Document

The source document is a **regular KUDocument** that already exists in the system before extraction starts. The user imports it via the existing `POST /knowledge-units/documents` API, then points at it by ID when starting an extraction.

No special fields, categories, or naming conventions are required on the source document. It's just a KUDocument — it could be a SOAR playbook (`doc_format: "json"`), a blog article (`doc_format: "markdown"`), or a detection rule snippet (`doc_format: "text"`). The KUDocument model already supports all of these.

The extraction record references the source document via `document_id` (FK). The KDG `DERIVED_FROM` edge (created on apply) provides the provenance link between source and extracted content.

### KDG Edges on Apply

When an extraction is applied, **three components** are connected:

```
Source KUDocument ◀──(DERIVED_FROM)── Extracted KUDocument ◀──(CONTAINS)── Skill
(already exists)                      (created or updated)                 (already exists)
```

1. **Extracted → Source** (`EdgeType.DERIVED_FROM`):
   - `source_id`: the extracted KUDocument (new or updated skill content)
   - `target_id`: the source KUDocument (the original input — already exists)
   - `relationship_type`: `DERIVED_FROM`
   - `edge_metadata`: `{ "extraction_id": "uuid", "extraction_method": "knowledge_extraction_v1", "classification": "new_runbook", "confidence": "high", "merge_strategy": "create_new" }`

2. **Skill → Extracted** (`EdgeType.CONTAINS`):
   - `source_id`: the skill (KnowledgeModule)
   - `target_id`: the extracted KUDocument
   - `relationship_type`: `CONTAINS`
   - `edge_metadata`: `{ "namespace_path": "repository/sql-injection-response.md" }`
   - Only created for `create_new` — for `merge_with_existing`, this edge already exists

### Visibility in Knowledge Graph

This provenance is queryable and visible in the Knowledge Graph UI:
- Navigating to an extracted document shows "Derived from: [source document]"
- Navigating to a source document shows "Used in extractions: [list of extracted documents]"
- The extraction metadata (method, confidence, classification) is on the edge
- A single source document can have multiple DERIVED_FROM edges if it was used in multiple extractions

### Rejected Extractions

Rejected extractions do **not** create any KDG edges. The source document is unaffected — it remains in the system as-is. The extraction record preserves the rejection reason (classification + relevance assessment). The user can retry by starting a new extraction from the same document.

---

## Apply Flow (Non-LangGraph)

When the user calls the apply endpoint:

1. Load the extraction record from DB
2. Validate status is `completed` (not already applied, not rejected)
3. Apply any user overrides (edited content, changed filename)
4. **Create or update** the skill document:
   - **Create path** (`merge_strategy == "create_new"`):
     - Create new KUDocument with `transformed_content` (always markdown)
     - `namespace`: `/{skill_cy_name}/{target_namespace}{target_filename}`
   - **Merge path** (`merge_strategy == "merge_with_existing"`):
     - Load the existing KUDocument identified by `merge_target`
     - Its pre-merge content is already stored in `extraction.merge_info.original_content` for audit/rollback
     - Update the existing KUDocument's `content` with `transformed_content` (the merged version)
5. Create KDG edge: Skill →(`CONTAINS`)→ document (if new; already exists if merge)
6. Create KDG edge: document →(`DERIVED_FROM`)→ source KUDocument (referenced by `extraction.document_id`)
   - `edge_metadata`: `{ "extraction_id", "extraction_method", "classification", "confidence", "merge_strategy" }`
7. Trigger index rebuild for the skill (see Index Rebuild section)
8. Update extraction record: `status = "applied"`, `applied_document_id`, `applied_at`
9. Return the document ID

---

## Skill Index Rebuild

### Problem

The runbooks-manager skill uses pre-built indices (`index/all_runbooks.json`, `index/master_index.json`, categorical indices in `index/by_*/`) for fast runbook discovery and matching. Today these are generated by `scripts/build_runbook_index.py` which reads from the filesystem. When content is stored in the database (via KUDocuments), these indices become stale.

### Solution: Automatic DB-Native Index Rebuild

Index rebuild is triggered **automatically whenever a skill's content changes** — not just from knowledge extraction, but from any mutation (add document, remove document, update document). This is a general capability of the skills system.

**Trigger points:**
- Knowledge extraction apply (this spec)
- Manual document add/remove via skills API
- Any future mutation path

**Implementation:**

```python
async def rebuild_skill_index(skill_id: str, tenant_id: str, session: AsyncSession) -> None:
    """Rebuild all indices for a skill from its DB-backed documents."""
    # 1. Load all KUDocuments linked to skill via CONTAINS edges
    # 2. For documents in repository/ namespace: parse YAML frontmatter
    # 3. Generate all_runbooks.json equivalent (list of runbook metadata)
    # 4. Generate master_index.json equivalent (aggregated counts)
    # 5. Generate categorical indices (by_subcategory, by_attack_type, etc.)
    # 6. Store indices as KUDocuments in the index/ namespace of the skill
```

**Index storage:** Indices are stored as KUDocuments with `namespace: /{skill_cy_name}/index/` and `doc_format: "json"`. This keeps them in the same storage layer as the content they index.

**Scope for v1:** Only runbooks-manager indices are supported. The rebuild logic knows how to parse runbook YAML frontmatter and generate the specific index formats used by `build_runbook_index.py`. Other skills don't have index requirements yet.

**Performance:** Index rebuild reads all `repository/` documents for the skill (currently ~15 runbooks). This is fast enough to run synchronously during the apply request. If the repository grows to hundreds of runbooks, this should move to a background task.

---

## Service Layer

### KnowledgeExtractionService

```python
class KnowledgeExtractionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.km_service = KnowledgeModuleService(session)
        self.ku_repo = KnowledgeUnitRepository(session)
        self.extraction_repo = KnowledgeExtractionRepository(session)

    async def start_extraction(
        self, tenant_id: str, skill_id: str, document_id: str
    ) -> KnowledgeExtraction:
        """Load source document, run extraction graph, store result."""
        # 1. Load KUDocument by document_id (404 if not found)
        # 2. Read content, doc_format, name/description from the document
        # 3. Create extraction record (status=pending)
        # 4. Build and run knowledge_extraction_graph with document content
        # 5. Update extraction record with results
        ...

    async def apply_extraction(
        self, tenant_id: str, skill_id: str, extraction_id: str,
        overrides: ExtractionOverrides | None = None,
    ) -> KUDocument:
        """Commit extraction: create/update skill document + KDG edges."""
        ...

    async def list_extractions(
        self, tenant_id: str, skill_id: str,
        status: str | None = None, document_id: str | None = None,
    ) -> list[KnowledgeExtraction]:
        ...

    async def get_extraction(
        self, tenant_id: str, skill_id: str, extraction_id: str
    ) -> KnowledgeExtraction:
        ...
```

---

## Example Scenarios

### Scenario 1: SOAR Playbook → New Runbook

**Step 0 — Import:** User creates a KUDocument via `POST /knowledge-units/documents`:
- `name`: "Splunk SOAR playbook for SQL injection response"
- `content`: `{ "name": "SQL Injection Response", "steps": [...] }`
- `doc_format`: "json"
- → Returns `document_id: "abc-123"`

**Step 1 — Extract:** `POST /skills/{skill_id}/extractions` with `{ "document_id": "abc-123" }`

**Classification:** `new_runbook` (high confidence) — full investigation procedure

**Placement:** `repository/sql-injection-response.md`, `merge_strategy: "create_new"`

**Transform:** Convert JSON actions to markdown investigation steps, add YAML frontmatter, mark critical steps, add WikiLinks to common patterns, strip SOAR-specific action IDs.

**Step 2 — Apply:** Creates new KUDocument in skill namespace + DERIVED_FROM edge back to source.

### Scenario 2: Blog Article → Evidence Pattern

**Source document:** KUDocument with `doc_format: "markdown"`, content is a blog post about EDR lateral movement analysis.

**Classification:** `source_evidence_pattern` (medium confidence)

**Placement:** `common/by_source/edr-lateral-movement-evidence.md`, `merge_strategy: "create_new"`

**Transform:** Extract investigation steps, format as sub-runbook, use `${alert.field}` variables, strip blog narrative.

### Scenario 3: Detection Rule Next Steps → Merge with Existing

**Source document:** KUDocument with Sigma detection rule next steps for RDP brute force.

**Classification:** `attack_type_pattern` (high confidence)

**Placement:** `common/by_type/brute-force-base.md`, `merge_strategy: "merge_with_existing"` — an existing brute force base pattern already exists.

**Merge:** LLM reads existing `brute-force-base.md` and the new detection rule steps, produces merged version with new RDP-specific steps added. `merge_info` contains the original content for diff review.

### Scenario 4: Irrelevant Document → Rejected

**Source document:** KUDocument with an HR vacation policy.

**Classification:** `reference_documentation` (low confidence)

**Relevance:** `is_relevant: false` — "This document is an HR policy with no security investigation content."

**Status:** `rejected` — source document is unaffected, no KDG edges created.

---

## File Locations

| Component | Path |
|-----------|------|
| Router | `src/analysi/routers/knowledge_extraction.py` |
| Service | `src/analysi/services/knowledge_extraction.py` |
| Repository | `src/analysi/repositories/knowledge_extraction.py` |
| DB Model | `src/analysi/models/knowledge_extraction.py` |
| Schemas | `src/analysi/schemas/knowledge_extraction.py` |
| LangGraph | `src/analysi/agentic_orchestration/langgraph/knowledge_extraction/` |
| Graph | `src/analysi/agentic_orchestration/langgraph/knowledge_extraction/graph.py` |
| Nodes | `src/analysi/agentic_orchestration/langgraph/knowledge_extraction/nodes.py` |
| Models | `src/analysi/agentic_orchestration/langgraph/knowledge_extraction/models.py` |
| Migration | `migrations/flyway/sql/V{next}__create_knowledge_extractions.sql` |

---

## Future Considerations (v2+)

- **Async execution**: If latency becomes a problem, switch to 202 + polling (see Synchronous Execution section)
- **Validation retry loop**: On validation failure, feed errors back to transform node and retry (up to 3 times)
- **Batch ingestion**: Accept multiple documents, classify and route each independently
- **Multi-skill support**: Make classification prompts skill-driven (loaded from skill config) rather than hardcoded for runbooks-manager
- **Per-node model selection**: Use cheaper models (Haiku) for classification/relevance, Sonnet for transform/merge
- **Confidence threshold**: Auto-reject documents below a confidence threshold without LLM relevance check
- **Duplicate detection**: Content hashing to detect and warn about re-ingesting the same document
- **UI**: Skills page with "Extract Knowledge" button, preview panel with diff viewer for merges, and apply/reject actions
