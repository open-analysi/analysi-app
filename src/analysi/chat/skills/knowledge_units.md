# Knowledge Units (KUs)

Knowledge Units are the data building blocks of the Analysi platform. They represent reusable pieces of information that tasks and workflows consume during execution. Every KU belongs to a single tenant (strict tenant isolation) and is backed by the Component base model, which provides shared metadata: name, description, version, status (enabled/disabled), categories, cy_name, namespace, and visibility flags.

## KU Types

There are three user-facing KU types plus a fourth (Tool) used internally by integrations.

### Documents

Unstructured text content: runbooks, policies, PDFs, Markdown, raw text. Documents are the most common KU type.

Key fields:
- `content` -- raw text body
- `markdown_content` -- rendered Markdown (if applicable)
- `doc_format` -- format identifier (e.g., "raw", "markdown", "pdf")
- `document_type` -- classification (e.g., "runbook", "policy", "reference")
- `source_url` -- origin URL if scraped/imported
- `word_count`, `character_count`, `page_count` -- computed stats
- `language` -- ISO language code
- `metadata` -- arbitrary JSONB metadata

Documents are used to provide context to tasks. A task's Cy script can read a document's content by referencing its cy_name, and the task engine injects the document text into the LLM prompt.

### Tables

Structured tabular data: CSV imports, lookup tables, IP allowlists, asset inventories.

Key fields:
- `schema` -- JSONB column schema definition (column names, types)
- `content` -- JSONB holding the actual row data
- `row_count`, `column_count` -- dimensions
- `file_path` -- original file path if uploaded

Tables are used for structured lookups during task execution. A Cy script can query a table's rows, filter by column values, and use the results in logic.

### Indexes

Vector/full-text search indexes built over other KUs. Used for semantic retrieval during task execution.

Key fields:
- `index_type` -- "vector", "fulltext", or "hybrid"
- `vector_database` -- backend store (e.g., pgvector)
- `embedding_model` -- model used for vectorization (e.g., "text-embedding-3-small")
- `chunking_config` -- JSONB chunking parameters (chunk size, overlap)
- `build_status` -- lifecycle: pending -> building -> completed | failed | outdated
- `build_started_at`, `build_completed_at` -- build timing
- `build_error_message` -- error details if build failed
- `index_stats` -- JSONB stats (chunk count, vector dimensions, etc.)
- `last_sync_at` -- last time source data was re-indexed

Indexes enable semantic search over documents. When a task needs to find relevant information, it queries an index rather than scanning every document.

## Component Model

Every KU is backed by a row in the `component` table (class table inheritance). The Component provides:

- `id` (UUID) -- the canonical identifier exposed in APIs
- `tenant_id` -- tenant isolation
- `kind` -- discriminator: "ku", "task", or "module"
- `name`, `description`, `version`
- `status` -- "enabled" or "disabled"
- `cy_name` -- script-friendly identifier for Cy language references (e.g., `ip_allowlist`). Must match `^[a-zA-Z_][a-zA-Z0-9_]*$`
- `namespace` -- scoping for KUs (e.g., skill-owned documents use the skill's cy_name as namespace; default is "/")
- `visible`, `system_only` -- visibility controls
- `app` -- application grouping (default: "default")
- `categories` -- array of category tags
- `created_by`, `updated_by` -- user UUID references

The KnowledgeUnit intermediate table sits between Component and the specific subtype (KUTable, KUDocument, KUIndex), holding the `ku_type` discriminator.

## Using KUs in Tasks and Workflows

KUs are referenced in Cy scripts by their `cy_name`. The task execution engine resolves these references at runtime, loading the KU data from the database and making it available to the script. When a task runs inside a workflow, each node can access KUs independently.

KUs are also connected via the Knowledge Dependency Graph (KDG), which tracks which tasks depend on which KUs. The KDG stores directed edges between components (tasks and KUs), recording dependency relationships. This graph is used during workflow composition to ensure all required KUs are available and to visualize data flow.

### KU Lifecycle in Execution

When a task executes:
1. The engine resolves all KU references in the Cy script by cy_name within the tenant scope.
2. Document content is loaded and injected into the LLM context.
3. Table data is made available for row-level queries and lookups.
4. Index KUs are queried via semantic search to retrieve relevant chunks.
5. The `last_used_at` timestamp on the Component is updated to track usage.

### Namespaces and Skill-Owned KUs

KUs can be namespaced to a skill by setting the `namespace` field to the skill's cy_name. This allows skills to package their own reference documents, lookup tables, and indexes without name collisions. The default namespace is "/" (root). Namespaced KUs are only accessible to tasks running within that skill's context.

## Tenant Isolation

All KU operations are scoped by `tenant_id`. The permission system requires `knowledge_units:read` for listing/viewing and `knowledge_units:create`, `knowledge_units:update`, `knowledge_units:delete` for mutations. These are available to analyst role and above.

## Common User Questions

See the **api** skill for full endpoint details for all KU operations (tables, documents, indexes).

- "How do I add a runbook?" -- Create a Document KU with the runbook content. Set `document_type` to "runbook" and give it a descriptive `cy_name` so tasks can reference it.
- "How do I import a CSV?" -- Create a Table KU. Provide the schema (column definitions) and content (row data) as JSON. The `row_count` and `column_count` are tracked automatically.
- "How do I set up semantic search?" -- Create an Index KU specifying the `index_type`, `embedding_model`, and `chunking_config`. The build process indexes the source documents and transitions `build_status` from pending through building to completed.
- "Can I share KUs between tenants?" -- No. Each KU belongs to exactly one tenant. Cross-tenant KU access is not supported.
- "What is cy_name for?" -- It is the identifier used in Cy scripts to reference a KU. For example, if a document has `cy_name: "incident_runbook"`, a task's Cy script can load it by that name.
