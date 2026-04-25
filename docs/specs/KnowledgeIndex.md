+++
version = "1.0"
status = "active"

[[changelog]]
version = "1.0"
summary = "pgvector-backed semantic search"
+++

# Knowledge Index — v1

## Overview

Introduces a **pluggable knowledge index** — a vector-backed retrieval system for storing and searching document chunks by semantic similarity. Each tenant can create multiple **collections** (index instances), add text entries that are automatically embedded, and search them with natural-language queries. The feature ships with a **pgvector backend** and is designed so alternative backends (ChromaDB, GraphRAG, LlamaIndex) can plug in later without changing the API, collection metadata, or tenant isolation logic.

```
  Cy Script / REST API
  ────────────────────
    index_add("threat-intel-kb", text)     ← auto-embeds, stores vector
    index_search("threat-intel-kb", query) ← auto-embeds query, returns ranked results
          │
          ▼
  KnowledgeIndexService
    ├─ embedding via AI archetype (llm_embed)
    ├─ model compatibility validation
    └─ delegates storage to IndexBackend
          │
          ▼
  IndexBackend (Protocol)
    ├─ PgvectorBackend   (v1 — ships now)
    ├─ ChromaBackend      (future)
    └─ GraphRAGBackend    (future)
```

**Design philosophy**: Don't try to be comprehensive in v1 — deliver solid vector search with metadata tracking. Make the backend pluggable so advanced strategies can be swapped in later. Keep collection metadata stable across backend types.

---

## Scope

### In Scope (v1)

- `IndexBackend` protocol with all CRUD + search methods
- `PgvectorBackend` as the first concrete implementation
- `index_entries` PostgreSQL table with pgvector `vector(1536)` column and HNSW index
- `KnowledgeIndexService` orchestrating embeddings and backend routing
- Collection-level metadata: `embedding_model`, `embedding_dimensions`, `backend_type`
- Embedding model lock — prevents mixing models within a collection
- REST API for collection CRUD, entry CRUD, and semantic search
- Cy DSL functions: `index_add`, `index_search`, `index_delete`
- Multi-tenant isolation at both service and backend layers
- pgvector extension added to the custom Postgres Dockerfile

### Deferred

- Batch embedding (OpenAI `/v1/embeddings` accepts arrays — current `LlmEmbedAction` takes a single string)
- Re-embedding / migration tooling when a user switches embedding models
- Chunking pipeline (automatic splitting of long documents before embedding)
- Hybrid search (combining vector similarity with full-text keyword search)

### Out of Scope (v1)

- GraphRAG, LlamaIndex, or any non-pgvector backend implementation
- Sub-second search latency guarantees — pgvector HNSW is fast enough at expected scale
- Automatic index rebuilding on schema changes
- Cross-collection search (searching multiple collections in one query)
- UI for collection management — API and DSL only

---

## Architecture

```
  Producers                           KnowledgeIndexService              IndexBackend
  ─────────                           ───────────────────────            ────────────
                                      ┌──────────────────────┐
  REST API (existing KU router)       │                      │
  POST /{t}/knowledge-units/indexes   │  Collection CRUD     │
    → create collection ─────────────▶│  (via existing       │
                                      │   KUIndex model)     │
  POST /{t}/knowledge-units/          │                      │
       indexes/{id}/entries           │  Entry Operations    │      ┌──────────────────┐
    → add entry ─────────────────────▶│  1. load collection  │      │                  │
                                      │  2. validate model   │      │  PgvectorBackend │
  POST /{t}/knowledge-units/          │  3. embed via AI     │      │  (v1)            │
       indexes/{id}/search            │     archetype        │      │                  │
    → search ────────────────────────▶│  4. delegate to      │─────▶│  INSERT + vector  │
                                      │     backend          │      │  cosine search   │
  Cy Script                           │                      │      │  DELETE           │
  index_add("kb", text) ────────────▶│  Backend routing     │      │                  │
  index_search("kb", query) ────────▶│  from collection's   │      └──────────────────┘
                                      │  backend_type field  │              │
                                      └──────────────────────┘              │  (future)
                                                                     ┌──────────────────┐
  AI Archetype (existing)                                            │  ChromaBackend   │
  ───────────────────────                                            │  GraphRAGBackend │
  llm_embed(text) → list[float]                                     └──────────────────┘
  (OpenAI text-embedding-3-small
   or Gemini text-embedding-004)
```

### Separation of Concerns

| Concern | Owner | Rationale |
|---------|-------|-----------|
| Collection lifecycle (create, delete, update metadata) | **Service** via existing `KUIndex` model | A collection is a KU — reuses Component/KUIndex CRUD |
| Embedding generation | **Service** via AI archetype `llm_embed` | Backend-agnostic; same vectors go to any backend |
| Embedding model validation | **Service** checks `ku_index.embedding_model` | Prevents mixing; enforced before any backend call |
| Store / retrieve / search vectors | **Backend** implementation | Only thing that changes between pgvector, ChromaDB, etc. |
| Multi-tenant isolation | **Both** — Service passes `tenant_id`, Backend enforces `WHERE tenant_id = $1` | Defense in depth |

---

## Data Model

### Collection Metadata (existing KUIndex table — enhanced)

Collections are represented by the existing `KUIndex` model (which inherits from `Component` via `KnowledgeUnit`). v1 adds two columns:

| Column | Type | Description |
|--------|------|-------------|
| `embedding_model` | `VARCHAR(255)` | **Existing**. Locked at first entry addition. e.g., `text-embedding-3-small` |
| `embedding_dimensions` | `INTEGER` | **New**. Actual dimension count of the embedding model (e.g., 1536, 768) |
| `backend_type` | `VARCHAR(50)` | **New**. Which `IndexBackend` handles this collection. Default: `pgvector` |
| `vector_database` | `VARCHAR(100)` | **Existing**. Set to backend identifier. e.g., `pgvector` |
| `index_type` | `ENUM` | **Existing**. `vector`, `fulltext`, or `hybrid` |
| `build_status` | `ENUM` | **Existing**. `pending` → `completed` on first successful add |
| `index_stats` | `JSONB` | **Existing**. Updated with `{"entry_count": N}` on add/delete |

**Immutable after first entry**: `embedding_model`, `embedding_dimensions`, `backend_type`. These fields define the collection's identity and cannot be changed without creating a new collection.

### IndexEntry (new table: `index_entries`)

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | `UUID` | PK, default `gen_random_uuid()` | Entry identifier |
| `collection_id` | `UUID` | FK → `component(id)` ON DELETE CASCADE | Which collection owns this entry |
| `tenant_id` | `VARCHAR(255)` | NOT NULL | Denormalized for query performance |
| `content` | `TEXT` | NOT NULL | Original text that was embedded |
| `embedding` | `vector(1536)` | | pgvector column. Shorter vectors zero-padded |
| `metadata` | `JSONB` | DEFAULT `'{}'` | Arbitrary key-value metadata for filtering |
| `source_ref` | `TEXT` | | Origin reference (e.g., `document:abc123`) |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `CURRENT_TIMESTAMP` | |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `CURRENT_TIMESTAMP` | |

**Indexes**:
- `idx_index_entries_tenant_collection` — `(tenant_id, collection_id)` — tenant isolation + collection scoping
- `idx_index_entries_embedding_hnsw` — HNSW on `embedding vector_cosine_ops` with `(m=16, ef_construction=64)` — approximate nearest neighbor
- `idx_index_entries_metadata` — GIN on `metadata` — filtered searches

**Dimension strategy**: Fixed `vector(1536)` column. OpenAI `text-embedding-3-small` produces 1536-dim vectors; Gemini `text-embedding-004` produces 768-dim vectors. Shorter vectors are zero-padded to 1536. Cosine similarity is unaffected by zero-padding (the angle between vectors is preserved). The actual dimension count is recorded in `ku_index.embedding_dimensions` for informational purposes.

### IndexEntry (dataclass — service layer)

```python
@dataclass
class IndexEntry:
    """An entry to add to an index."""
    content: str
    embedding: list[float]
    metadata: dict[str, Any] | None = None
    source_ref: str | None = None
    entry_id: UUID | None = None          # assigned by backend if None
```

### SearchResult (dataclass — returned from search)

```python
@dataclass
class SearchResult:
    """A single search result."""
    entry_id: UUID
    content: str
    score: float                           # 0.0–1.0, higher = more similar
    metadata: dict[str, Any]
    source_ref: str | None = None
```

### StoredEntry (dataclass — returned from list)

```python
@dataclass
class StoredEntry:
    """A stored entry from list/get operations."""
    entry_id: UUID
    content: str
    metadata: dict[str, Any]
    source_ref: str | None
    created_at: datetime
```

---

## Backend Protocol

```python
class IndexBackend(Protocol):
    """Protocol that all index backend implementations must satisfy.

    Backends handle storage and retrieval of embedded entries.
    They do NOT handle embedding generation — the service does that.

    Thread/session safety: DB-backed backends receive an AsyncSession.
    Non-DB backends (e.g., ChromaDB client) manage their own connections.
    """

    async def add(
        self,
        collection_id: UUID,
        tenant_id: str,
        entries: list[IndexEntry],
    ) -> list[UUID]:
        """Add entries to a collection. Returns assigned entry IDs."""
        ...

    async def search(
        self,
        collection_id: UUID,
        tenant_id: str,
        query_embedding: list[float],
        top_k: int = 10,
        score_threshold: float | None = None,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Search for similar entries by cosine similarity.

        Returns results ordered by score descending (most similar first).
        If score_threshold is set, only results above that score are returned.
        metadata_filter uses JSONB containment (@>) for filtering.
        """
        ...

    async def delete(
        self,
        collection_id: UUID,
        tenant_id: str,
        entry_ids: list[UUID],
    ) -> int:
        """Delete specific entries. Returns count of deleted entries."""
        ...

    async def delete_all(
        self,
        collection_id: UUID,
        tenant_id: str,
    ) -> int:
        """Delete all entries in a collection. Returns count deleted."""
        ...

    async def count(
        self,
        collection_id: UUID,
        tenant_id: str,
    ) -> int:
        """Count entries in a collection."""
        ...

    async def list_entries(
        self,
        collection_id: UUID,
        tenant_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[StoredEntry], int]:
        """List entries with pagination. Returns (entries, total_count)."""
        ...
```

### Backend Registry

```python
# Simple dict-based registry. Backends self-register at import time.

_BACKENDS: dict[str, type[IndexBackend]] = {}

def register_backend(name: str, backend_class: type) -> None:
    _BACKENDS[name] = backend_class

def get_backend(name: str, **kwargs) -> IndexBackend:
    if name not in _BACKENDS:
        raise ValueError(f"Unknown index backend '{name}'. Available: {list(_BACKENDS.keys())}")
    return _BACKENDS[name](**kwargs)

# Auto-register built-ins
from .pgvector_backend import PgvectorBackend
register_backend("pgvector", PgvectorBackend)
```

---

## v1 Implementation: PgvectorBackend

### Postgres Extension Setup

**Dockerfile change** (`deployments/docker/postgres/Dockerfile`):
```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-${PG_MAJOR}-partman \
        postgresql-${PG_MAJOR}-cron \
        postgresql-${PG_MAJOR}-pgvector \
    && rm -rf /var/lib/apt/lists/*
```

**Init script change** (`deployments/docker/configs/postgres/init/01-create-databases.sql`):
```sql
-- Add to both analysi_db and analysi_test blocks:
CREATE EXTENSION IF NOT EXISTS vector;
```

### Migration
```sql
-- migrations/flyway/sql/V001__baseline.sql
-- Project Paros: Knowledge Index with pgvector

CREATE EXTENSION IF NOT EXISTS vector;

-- Enhance ku_index with backend tracking columns
ALTER TABLE ku_index ADD COLUMN IF NOT EXISTS embedding_dimensions INTEGER;
ALTER TABLE ku_index ADD COLUMN IF NOT EXISTS backend_type VARCHAR(50) DEFAULT 'pgvector';

-- Index entries with vector embeddings
CREATE TABLE index_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collection_id   UUID NOT NULL REFERENCES component(id) ON DELETE CASCADE,
    tenant_id       VARCHAR(255) NOT NULL,
    content         TEXT NOT NULL,
    embedding       vector(1536),
    metadata        JSONB DEFAULT '{}',
    source_ref      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_index_entries_tenant_collection
    ON index_entries (tenant_id, collection_id);

CREATE INDEX idx_index_entries_embedding_hnsw
    ON index_entries USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_index_entries_metadata
    ON index_entries USING gin (metadata);
```

### PgvectorBackend Implementation

```python
class PgvectorBackend:
    """pgvector-backed index using PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, collection_id, tenant_id, entries) -> list[UUID]:
        """INSERT entries with vector embeddings."""
        ids = []
        for entry in entries:
            padded = _pad_vector(entry.embedding, 1536)
            row = IndexEntryModel(
                collection_id=collection_id,
                tenant_id=tenant_id,
                content=entry.content,
                embedding=padded,
                metadata=entry.metadata or {},
                source_ref=entry.source_ref,
            )
            self.session.add(row)
            await self.session.flush()
            ids.append(row.id)
        await self.session.commit()
        return ids

    async def search(self, collection_id, tenant_id, query_embedding,
                     top_k=10, score_threshold=None, metadata_filter=None):
        """Cosine similarity search via pgvector <=> operator."""
        padded = _pad_vector(query_embedding, 1536)
        # 1 - cosine_distance gives similarity in [0, 1]
        similarity = (1 - IndexEntryModel.embedding.cosine_distance(padded)).label("score")

        stmt = (
            select(IndexEntryModel, similarity)
            .where(
                IndexEntryModel.tenant_id == tenant_id,
                IndexEntryModel.collection_id == collection_id,
            )
            .order_by(similarity.desc())
            .limit(top_k)
        )

        if metadata_filter:
            stmt = stmt.where(IndexEntryModel.metadata.contains(metadata_filter))

        if score_threshold is not None:
            stmt = stmt.where(similarity >= score_threshold)

        result = await self.session.execute(stmt)
        return [
            SearchResult(
                entry_id=row.id, content=row.content,
                score=score, metadata=row.metadata,
                source_ref=row.source_ref,
            )
            for row, score in result.all()
        ]
```

### Multi-tenant Enforcement

Every backend method includes `WHERE tenant_id = $1 AND collection_id = $2`. The service layer also validates that the collection belongs to the requesting tenant before delegating to the backend. This provides defense in depth: even if a backend implementation has a bug, the service layer prevents cross-tenant access.

---

## v2+ Extensibility

### Adding a New Backend

1. Create `services/index_backends/chroma_backend.py` implementing `IndexBackend`
2. Register: `register_backend("chroma", ChromaBackend)`
3. Users create collections with `backend_type="chroma"`
4. Service routes operations to ChromaBackend automatically

### Backend-Specific Requirements

| Backend | Container | Multi-tenancy | Transactions |
|---------|-----------|---------------|--------------|
| pgvector | None (existing Postgres) | `WHERE tenant_id = $1` | Full ACID |
| ChromaDB | New container | Collection naming convention or tenant-per-collection | Eventual consistency |
| GraphRAG | Depends on implementation | Graph partitioning | Varies |

### What Stays the Same Across Backends

- REST API shape and response formats
- Cy DSL function signatures (`index_add`, `index_search`)
- Collection metadata on `ku_index` (embedding_model, dimensions, backend_type)
- Embedding generation via AI archetype
- Model compatibility validation
- Tenant isolation at the service layer

---

## REST API Endpoints

All endpoints follow the Sifnos envelope pattern (`{data, meta}`).

### Collection Endpoints

Collection CRUD uses the **existing** `/knowledge-units/indexes` endpoints (already implemented). No new endpoints needed for collection management — the existing `IndexKUCreate`, `IndexKUUpdate`, `IndexKUResponse` schemas are extended with `embedding_dimensions` and `backend_type`.

### Entry and Search Endpoints (extend existing router)

New endpoints are sub-resources of the existing `/knowledge-units/indexes/{id}` path. An index is a knowledge unit — its entries and search live under it, not at a separate top-level prefix.

```
Existing router prefix: /{tenant}/knowledge-units
New sub-resources:      /{tenant}/knowledge-units/indexes/{id}/entries
                        /{tenant}/knowledge-units/indexes/{id}/search
```

> **Why sub-resources?** Tables and documents are leaf KUs — their content lives directly on the model. An index is a container with its own entry lifecycle. The sub-resource pattern reflects this structural difference without introducing a new top-level concept.

#### Add Entries

```
POST /{tenant}/knowledge-units/indexes/{collection_id}/entries
```

**Request**:
```json
{
    "entries": [
        {
            "content": "APT29 uses spearphishing with malicious attachments...",
            "metadata": {"source": "mitre-attack", "technique": "T1566.001"},
            "source_ref": "document:threat-intel-report-demo"
        }
    ]
}
```

**Response** (201):
```json
{
    "data": {
        "entry_ids": ["uuid-1", "uuid-2"],
        "collection_id": "uuid-collection",
        "entries_added": 1,
        "embedding_model": "text-embedding-3-small"
    },
    "meta": {"request_id": "..."}
}
```

#### Search

```
POST /{tenant}/knowledge-units/indexes/{collection_id}/search
```

**Request**:
```json
{
    "query": "lateral movement techniques using stolen credentials",
    "top_k": 5,
    "score_threshold": 0.7,
    "metadata_filter": {"source": "mitre-attack"}
}
```

**Response** (200):
```json
{
    "data": {
        "results": [
            {
                "entry_id": "uuid-1",
                "content": "APT29 uses spearphishing with malicious attachments...",
                "score": 0.87,
                "metadata": {"source": "mitre-attack", "technique": "T1566.001"},
                "source_ref": "document:threat-intel-report-demo"
            }
        ],
        "query": "lateral movement techniques using stolen credentials",
        "collection_id": "uuid-collection",
        "total_results": 1
    },
    "meta": {"request_id": "..."}
}
```

#### Delete Entry

```
DELETE /{tenant}/knowledge-units/indexes/{collection_id}/entries/{entry_id}
```

**Response**: 204 No Content

#### List Entries

```
GET /{tenant}/knowledge-units/indexes/{collection_id}/entries?limit=50&offset=0
```

**Response** (200):
```json
{
    "data": [
        {
            "entry_id": "uuid-1",
            "content": "APT29 uses spearphishing...",
            "metadata": {"source": "mitre-attack"},
            "source_ref": "document:threat-intel-report-demo",
            "created_at": "2026-04-26T10:00:00Z"
        }
    ],
    "meta": {"total": 42, "limit": 50, "offset": 0, "request_id": "..."}
}
```

---

## DSL Integration (Cy Language)

### Functions

Following the existing `CyKUFunctions` pattern, a new `CyIndexFunctions` class exposes index operations to Cy scripts.

#### `index_add(name, content, metadata?, source_ref?)`

Adds a single text entry to a collection. Embedding is automatic — the collection's configured model is used.

```python
# Cy script usage
index_add("threat-intel-kb", "APT29 uses spearphishing with malicious attachments")
index_add("threat-intel-kb", alert_summary, metadata={"alert_id": alert.id})
```

#### `index_search(name, query, top_k?, threshold?)`

Searches a collection by semantic similarity. Returns list of result dicts.

```python
# Cy script usage
results = index_search("threat-intel-kb", "credential theft techniques", top_k=5)
for result in results:
    print(result["content"], result["score"])
```

#### `index_delete(name, entry_id)`

Deletes a single entry from a collection.

```python
# Cy script usage
index_delete("threat-intel-kb", entry_id)
```

### Registration

Functions are registered in `native_tools_registry.py` under `native::ku::index_*` namespace and loaded in `task_execution.py` via a `_load_index_functions()` method.

### Embedding is Automatic

When `index_add` is called, the service:
1. Looks up the collection by name (tenant-scoped)
2. Resolves the tenant's AI integration and its embedding model
3. Validates the model matches the collection's `embedding_model`
4. Calls `llm_embed(text)` via the AI archetype
5. Passes the vector to the backend's `add()` method

When `index_search` is called, the same embedding flow is applied to the query string before searching.

### Embedding Model Validation

On every `add` or `search` call, the service checks:

```python
# Resolve what model the tenant's AI integration would use
tenant_embedding_model = resolve_embedding_model(ai_integration)

# First entry: lock the collection's model
if collection.embedding_model is None:
    collection.embedding_model = tenant_embedding_model
    collection.embedding_dimensions = len(embedding_result)
    await session.commit()

# Subsequent entries: validate match
elif collection.embedding_model != tenant_embedding_model:
    raise EmbeddingModelMismatchError(
        f"Collection '{collection.name}' uses model '{collection.embedding_model}' "
        f"but tenant's current embedding model is '{tenant_embedding_model}'. "
        f"Cannot mix embedding models within a collection."
    )
```

---

## Migration Path: Changing Embedding Models

If a tenant changes their AI integration (e.g., from OpenAI to Gemini), existing collections become incompatible because the embedding models differ. v1 does **not** support automatic re-embedding. Instead:

1. **Detection**: On the next `add` or `search` call, the service raises `EmbeddingModelMismatchError` with a clear message.
2. **Manual migration**: The tenant creates a new collection with the new model and re-adds entries from source.
3. **Future (deferred)**: A re-embedding job that reads all entries from a collection, re-embeds with the new model, and replaces the vectors in-place.

This is intentional — automatic re-embedding is expensive (API calls, tokens) and should be an explicit decision, not a side effect of changing an integration.

---

## Error Handling & Validation

### Embedding Model Mismatch

- **When**: `add_entries` or `search` called when tenant's embedding model differs from collection's locked model
- **Error**: `EmbeddingModelMismatchError` → HTTP 409 Conflict
- **Message**: Clear description of the mismatch with both model names

### Backend Type Mismatch

- **When**: Attempting to use a backend that isn't registered
- **Error**: `ValueError` → HTTP 400 Bad Request
- **Message**: Lists available backends

### Collection Not Found

- **When**: `collection_id` doesn't exist or belongs to a different tenant
- **Error**: HTTP 404 Not Found
- **Message**: `"Collection not found"`

### Entry Not Found

- **When**: `entry_id` doesn't exist in the specified collection
- **Error**: HTTP 404 Not Found
- **Message**: `"Entry not found"`

### Embedding Provider Unavailable

- **When**: Tenant has no AI integration configured, or the integration doesn't support embeddings (e.g., Anthropic)
- **Error**: HTTP 422 Unprocessable Entity
- **Message**: `"No embedding-capable AI integration configured for this tenant"`

### Invalid Search Parameters

- **When**: `top_k < 1`, `score_threshold` outside `[0, 1]`
- **Error**: HTTP 422 (Pydantic validation)

---

## File Locations

| Component | Path |
|-----------|------|
| Spec | `docs/specs/KnowledgeIndex.md` |
| Project summary | `docs/projects/paros.md` |
| Plan | `docs/planning/paros/PLAN.md` |
| **Models** | |
| IndexEntry model | `src/analysi/models/index_entry.py` |
| KUIndex model (enhanced) | `src/analysi/models/knowledge_unit.py` |
| **Schemas** | |
| Entry/search schemas | `src/analysi/schemas/knowledge_index.py` |
| KU schemas (enhanced) | `src/analysi/schemas/knowledge_unit.py` |
| **Backend** | |
| IndexBackend protocol | `src/analysi/services/index_backends/base.py` |
| Backend registry | `src/analysi/services/index_backends/registry.py` |
| PgvectorBackend | `src/analysi/services/index_backends/pgvector_backend.py` |
| **Service** | |
| KnowledgeIndexService | `src/analysi/services/knowledge_index.py` |
| **DSL** | |
| CyIndexFunctions | `src/analysi/services/cy_index_functions.py` |
| Native tools registry | `src/analysi/services/native_tools_registry.py` |
| Task execution loader | `src/analysi/services/task_execution.py` |
| **Router** | |
| Entry/search endpoints | `src/analysi/routers/knowledge_units.py` (extend existing router) |
| **Infrastructure** | |
| Postgres Dockerfile | `deployments/docker/postgres/Dockerfile` |
| Postgres init script | `deployments/docker/configs/postgres/init/01-create-databases.sql` |
| Migration | `migrations/flyway/sql/V001__baseline.sql` |
| **Tests** | |
| Unit: backend protocol | `tests/unit/services/index_backends/test_pgvector_backend.py` |
| Unit: service | `tests/unit/services/test_knowledge_index_service.py` |
| Unit: Cy functions | `tests/unit/services/test_cy_index_functions.py` |
| Integration: full stack | `tests/integration/test_knowledge_index.py` |

---

## Future Considerations

- **Batch embedding**: Modify `LlmEmbedAction` to accept `list[str]` and call OpenAI's batch endpoint. Would significantly speed up bulk `add_entries`.
- **Chunking pipeline**: Automatic splitting of long documents before embedding, with overlap and metadata preservation. Could be a separate service or integrated into `add_entries`.
- **Hybrid search**: Combine pgvector cosine similarity with PostgreSQL full-text search (`tsvector`) for keyword + semantic matching.
- **GraphRAG backend**: Build a knowledge graph from document relationships, then use graph traversal + vector similarity for retrieval. Would implement `IndexBackend` with a very different internal architecture.
- **Cross-collection search**: Search across multiple collections in a single query, with per-collection weighting.
- **Partitioning**: If `index_entries` grows large, add monthly partitioning via pg_partman (same pattern as `task_runs`, `alerts`).
- **Embedding caching**: Cache embeddings for frequently-searched queries to reduce API costs.
- **Re-embedding job**: Background job that re-embeds all entries in a collection with a new model, enabling model upgrades without collection recreation.
