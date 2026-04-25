# Project Paros — Knowledge Index

## Key Points

- **Pluggable vector index**: A retrieval system for storing and searching document chunks by semantic similarity, backed by an `IndexBackend` protocol that ships with pgvector and is designed for future backends (ChromaDB, GraphRAG, LlamaIndex).
- **pgvector v1 backend**: Uses PostgreSQL's pgvector extension — zero new containers, ACID-transactional with existing data, HNSW index for approximate nearest neighbor search. Vectors stored in a `vector(1536)` column; shorter embeddings (e.g., Gemini 768-dim) are zero-padded.
- **Automatic embedding**: Callers pass text, not vectors. The service generates embeddings via the tenant's AI archetype (`llm_embed`) — OpenAI `text-embedding-3-small` or Gemini `text-embedding-004`. The embedding model is locked per collection to prevent mixing.
- **Collection = KUIndex**: Each collection is a `KUIndex` knowledge unit with `Component` metadata (tenant isolation, cy_name, categories). New columns: `embedding_dimensions`, `backend_type`.
- **Backend protocol**: `IndexBackend` defines `add`, `search`, `delete`, `delete_all`, `count`, `list_entries`. Implementations are registered in a simple dict registry and looked up from the collection's `backend_type` field.
- **Cy DSL functions**: `index_add(name, text)`, `index_search(name, query)`, `index_delete(name, entry_id)` — auto-embed, tenant-scoped, follow existing `CyKUFunctions` pattern.
- **REST API**: Entry and search endpoints are sub-resources of the existing KU router: `/{tenant}/knowledge-units/indexes/{id}/entries` and `/{tenant}/knowledge-units/indexes/{id}/search`. Collection CRUD is already implemented.
- **Spec**: `docs/specs/KnowledgeIndex.md`

## Terminology

| Term | Definition |
|------|-----------|
| **Collection** | An instance of a knowledge index, represented as a `KUIndex` knowledge unit. Has a fixed embedding model, backend type, and tenant. Contains zero or more entries. |
| **Entry** | A single text chunk stored in a collection, with its vector embedding, arbitrary JSONB metadata, and an optional source reference. Stored in the `index_entries` table. |
| **IndexBackend** | A Python Protocol defining the storage/retrieval contract. Implementations handle add, search, delete. The service selects the backend from the collection's `backend_type` field. |
| **PgvectorBackend** | The v1 built-in backend using PostgreSQL's pgvector extension. Stores vectors in a `vector(1536)` column with an HNSW index for cosine similarity search. |
| **Backend registry** | A simple dict mapping backend names (e.g., `"pgvector"`) to implementation classes. Backends self-register at import time. |
| **Embedding model lock** | Once the first entry is added to a collection, the `embedding_model` and `embedding_dimensions` are locked. Subsequent adds/searches must use the same model or raise `EmbeddingModelMismatchError`. |
| **Zero-padding** | Shorter embedding vectors (e.g., 768-dim from Gemini) are padded with zeros to fill the fixed 1536-dim `vector` column. Cosine similarity is unaffected because zero dimensions don't change the angle between vectors. |
| **Score** | Similarity score in `[0, 1]` returned by search. Computed as `1 - cosine_distance`. Higher = more similar. |
| **Source ref** | An optional string on each entry identifying where the text came from (e.g., `document:abc123`, `alert:xyz789`). Used for traceability, not for querying. |
