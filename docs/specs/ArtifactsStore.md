+++
version = "2.0"
date = "2025-12-15"
status = "active"

[[changelog]]
version = "2.0"
date = "2025-12-15"
summary = "v2 — Object storage, presigned URLs"
+++

# Artifacts Store Service v2

## About

Artifact Store is a top-level service in our Analysi Security platform.

Stores artifacts that are created during the analysis of alerts or during ad-hoc execution of workflows and tasks. All the metadata about artifacts are stored in a relational database in Postgres. These include the name of the artifact, its MIME type (voice recording, binary executable, markdown text, JSON, etc.), time of creation, and more. The actual artifact can be stored inline in Postgres if below N bytes in size (256 KB uncompressed as the default inline cap). For larger artifacts, the value is stored in our object store, which is currently MinIO for local dev and on-prem deployments and it will be S3 or other object stores from Public Cloud Providers for our SaaS deployment.

Artifacts are immutable. We keep enough information in Postgres to tie artifacts to the task_run, workflow_run, workflow_node_instance, analysis, or alert that generated it.

All clients interface to the Artifacts Store via our REST API. The API supports download of larger resources with proper support for handling compression (future work). Only Artifacts service has direct access to the object store and the db!

## Changes from v1

**Phase 45: Auto-Capture Tool & LLM Artifacts**

1. **Removed redundant columns**:
   - `task_id` - Removed (can join via `task_run_id` → `task_runs.task_id`)
   - `workflow_id` - Removed (can join via `workflow_run_id` → `workflow_runs.workflow_id`)

2. **Added new columns**:
   - `alert_id` - Direct link to alert for manual attachments
   - `integration_id` - Integration instance that produced the artifact (e.g., "virustotal-prod")
   - `source` - Provenance tracking for how artifact was created

3. **New artifact types**:
   - `tool_execution` - Auto-captured integration tool I/O
   - `llm_execution` - Auto-captured LLM prompt/completion

4. **Auto-capture behavior**:
   - Every integration tool call creates an artifact automatically
   - Every LLM call creates an artifact automatically
   - Fire-and-forget: failures are logged but don't break execution

## Use Cases

### Alert Analysis Dashboard
When analyzing security alerts, workflows generate multiple artifacts that power different parts of the UI:
- **Timeline artifacts** (`artifact_type='timeline'`): JSON data for temporal event visualization
- **Activity graph artifacts** (`artifact_type='activity_graph'`): Graph data showing entity relationships
- **Alert summary artifacts** (`artifact_type='short_summary'`, `artifact_type='long_summary'`): Analysis narratives
- **Disposition artifacts** (`artifact_type='disposition'`): Final verdict and confidence
- **Tool execution artifacts** (`artifact_type='tool_execution'`): Integration tool I/O for audit
- **LLM execution artifacts** (`artifact_type='llm_execution'`): LLM prompts/completions for audit

All these artifacts share an `analysis_id` that links back to the alert being analyzed, enabling the UI to efficiently retrieve all relevant artifacts for a given alert dashboard.

### Integration Tool Audit Trail
Every integration tool call during Cy script execution is automatically captured:
- Tool name (cy_name): `app::virustotal::ip_reputation`
- Integration instance: `virustotal-prod`
- Input parameters: `{"ip": "8.8.8.8"}`
- Output: Full response from the integration
- Duration: Execution time in milliseconds

### LLM Call Audit Trail
Every LLM call during Cy script execution is automatically captured:
- Function name: `llm_run`, `llm_summarize`, etc.
- Integration instance: `openai-prod`, `anthropic-claude`, or `primary`
- Prompt: Full prompt sent to the LLM
- Completion: Full response from the LLM
- Model: Model name if specified
- Duration: Execution time in milliseconds

## Design

### Interfacing with Tasks (Cy Language)

Tasks access Artifacts Store via native functions provided in the context of a Cy Script:

**Implemented:**
* `store_artifact(name, artifact, tags={}, artifact_type=None)` returns artifact_id - Store an artifact from Cy script (source='cy_script')

**Auto-capture (Phase 45):**
* Integration tool calls automatically create artifacts (source='auto_capture')
* LLM calls automatically create artifacts (source='auto_capture')

**Future Work:**
* `load_artifact_by_name(name)` returns the last artifact of this name
* `load_artifact_by_id(artifact_id)` returns a specific artifact

### Artifact `source` Values (Provenance Tracking)

| Source Value | Description | `analysis_id` | `alert_id` | Example |
|--------------|-------------|---------------|------------|---------|
| `auto_capture` | Automatically captured during Cy execution | Set | NULL | Integration tool calls, LLM calls |
| `cy_script` | Explicitly created via `store_artifact()` native function | Set | NULL | Analysis summaries, reports |
| `rest_api` | Manual attachment via REST API | NULL | Set | External uploads, analyst notes |
| `mcp` | Manual attachment via MCP tools | NULL | Set | IDE/agent integrations |

**Query Pattern - All Evidence for Active Alert:**
```sql
WHERE analysis_id = :active_analysis_id
   OR (alert_id = :alert_id AND analysis_id IS NULL)
```

### Database Schema

```sql
-- Artifacts table (partitioned by created_at like task_runs and workflow_runs)
CREATE TABLE artifacts (
    id UUID DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) NOT NULL,

    -- Core metadata
    name TEXT NOT NULL,  -- For tool_execution: cy_name (e.g., "app::virustotal::ip_reputation")
    artifact_type TEXT,  -- Semantic type: 'timeline', 'tool_execution', 'llm_execution', etc.
    mime_type TEXT NOT NULL,
    tags JSONB DEFAULT '[]'::jsonb,

    -- Content hashing
    sha256 BYTEA NOT NULL,
    md5 BYTEA,  -- Optional for compatibility
    size_bytes BIGINT NOT NULL,  -- Size before any compression

    -- Storage strategy
    storage_class TEXT NOT NULL CHECK (storage_class IN ('inline', 'object')),
    inline_content BYTEA,  -- For small artifacts (<= 256KB)

    -- Object store reference (when storage_class = 'object')
    bucket TEXT,
    object_key TEXT,

    -- Relationship fields (at least one must be non-null)
    alert_id UUID,  -- For manual attachments via REST API
    task_run_id UUID,  -- References task_runs(id) but partition-aware
    workflow_run_id UUID,  -- References workflow_runs(id) but partition-aware
    workflow_node_instance_id UUID,  -- References workflow_node_instances(id) but partition-aware
    analysis_id UUID,  -- References analysis table for alert analysis grouping

    -- Provenance
    integration_id VARCHAR(255),  -- Integration instance (e.g., "virustotal-prod")
    source VARCHAR(50) NOT NULL DEFAULT 'unknown',  -- auto_capture, cy_script, rest_api, mcp

    -- Soft delete
    is_deleted VARCHAR(10) DEFAULT 'false',

    -- Metadata (no updated_at since artifacts are immutable)
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    -- Constraints
    PRIMARY KEY (id, created_at),  -- Composite for partitioning
    CONSTRAINT artifacts_relationship_check CHECK (
        alert_id IS NOT NULL OR
        task_run_id IS NOT NULL OR
        workflow_run_id IS NOT NULL OR
        workflow_node_instance_id IS NOT NULL OR
        analysis_id IS NOT NULL
    ),
    CONSTRAINT artifacts_source_check CHECK (
        source IN ('auto_capture', 'cy_script', 'rest_api', 'mcp', 'unknown')
    )
) PARTITION BY RANGE (created_at);

-- Indexes for common queries
CREATE INDEX idx_artifacts_tenant_name ON artifacts(tenant_id, name);
CREATE INDEX idx_artifacts_tenant_type ON artifacts(tenant_id, artifact_type);
CREATE INDEX idx_artifacts_tenant_created ON artifacts(tenant_id, created_at DESC);
CREATE INDEX idx_artifacts_task_run ON artifacts(task_run_id) WHERE task_run_id IS NOT NULL;
CREATE INDEX idx_artifacts_workflow_run ON artifacts(workflow_run_id) WHERE workflow_run_id IS NOT NULL;
CREATE INDEX idx_artifacts_analysis ON artifacts(analysis_id) WHERE analysis_id IS NOT NULL;
CREATE INDEX idx_artifacts_alert ON artifacts(alert_id) WHERE alert_id IS NOT NULL;
CREATE INDEX idx_artifacts_integration ON artifacts(integration_id) WHERE integration_id IS NOT NULL;
CREATE INDEX idx_artifacts_source ON artifacts(source);
```

**Storage Decision Logic:**
1. If mime_type is text-based (application/json, text/markdown, text/plain, text/csv) AND size_bytes ≤ 256KB → storage_class='inline'
2. Else → storage_class='object'

**Relationship Rules:**
- At least ONE relationship field must be non-null
- Multiple relationships can be populated (e.g., both task_run_id and workflow_run_id)
- Manual attachments use `alert_id` directly; automated artifacts use `analysis_id`

**Well-Known Artifact Types:**
```
# Analysis outputs
short_summary        - Brief summary for prominent UI display
long_summary         - Detailed analysis narrative
disposition          - Final verdict and confidence

# Event artifacts
triggering_events    - Events that triggered the alert
supporting_events    - Correlated events supporting analysis

# Execution artifacts
tool_execution       - Integration tool call input/output
llm_execution        - LLM call with prompt and completion

# Visualizations
timeline             - Chronological event sequence
activity_graph       - Entity relationship visualization
```

### Tool Execution Artifact Content

```json
{
  "input": {"ip": "8.8.8.8"},
  "output": {
    "reputation": "clean",
    "score": 0,
    "last_analysis_stats": {...}
  },
  "duration_ms": 234,
  "timestamp": "2025-12-15T10:30:00Z"
}
```

### LLM Execution Artifact Content

```json
{
  "prompt": "Analyze this IP address for threats: 8.8.8.8",
  "completion": "This IP address belongs to Google's public DNS...",
  "model": "gpt-4",
  "duration_ms": 1523,
  "timestamp": "2025-12-15T10:30:00Z"
}
```

### Object Store Directory Structure

```
artifacts/{tenant_id}/namespace={namespace}/event_date={YYYY-MM-DD}/artifact_id={uuid}/payload.bin
```

* Namespace is for future proofing. Use "main" as the default.
* Standard name for the payload to avoid encoding issues on file systems.
* Postgres metadata (mime_type, compression etc) contains information to decode

### REST API

#### List Artifacts
```
GET /v1/{tenant}/artifacts
```
Query Parameters:
- `name`: Filter by artifact name (partial match)
- `artifact_type`: Filter by artifact type (exact match)
- `tags`: Filter by tags (JSON array)
- `task_run_id`: Filter by task run
- `workflow_run_id`: Filter by workflow run
- `analysis_id`: Filter by analysis
- `alert_id`: Filter by alert (for manual attachments)
- `integration_id`: Filter by integration instance
- `source`: Filter by source (auto_capture, cy_script, rest_api, mcp)
- `limit`: Page size (default: 20, max: 100)
- `offset`: Pagination offset
- `sort`: Sort field (name, created_at, size_bytes)
- `order`: Sort order (asc, desc)

Response (200):
```json
{
  "artifacts": [
    {
      "id": "uuid",
      "name": "app::virustotal::ip_reputation",
      "artifact_type": "tool_execution",
      "mime_type": "application/json",
      "size_bytes": 2048,
      "tags": [],
      "storage_class": "inline",
      "integration_id": "virustotal-prod",
      "source": "auto_capture",
      "created_at": "2025-01-01T00:00:00Z",
      "task_run_id": "uuid",
      "workflow_run_id": "uuid",
      "analysis_id": "uuid"
    }
  ],
  "total": 100,
  "limit": 20,
  "offset": 0
}
```

#### Create Artifact
```
POST /v1/{tenant}/artifacts
```
Request Body:
```json
{
  "name": "alert_timeline_20250101",
  "artifact_type": "timeline",
  "mime_type": "application/json",
  "tags": ["alert:high", "ui:timeline"],
  "content": "base64_encoded_content or raw_json",
  "task_run_id": "uuid",
  "workflow_run_id": "uuid",
  "analysis_id": "uuid",
  "alert_id": "uuid",
  "integration_id": "virustotal-prod",
  "source": "rest_api"
}
```

Response (201):
```json
{
  "id": "uuid",
  "name": "alert_timeline_20250101",
  "artifact_type": "timeline",
  "mime_type": "application/json",
  "size_bytes": 2048,
  "storage_class": "inline",
  "source": "rest_api",
  "created_at": "2025-01-01T00:00:00Z"
}
```

## Implementation Notes

### Auto-Capture in Tool Wrapper

The `create_tool_wrapper` closure in `task_execution.py` automatically captures:

```python
# After successful execute_action()
duration_ms = int((time.time() - start_time) * 1000)
try:
    await artifact_service.create_tool_execution_artifact(
        tenant_id=ten_id,
        tool_fqn=tool_cy_name,  # e.g., "app::virustotal::ip_reputation"
        integration_id=cached_int_id,  # e.g., "virustotal-prod"
        input_params=params,
        output=result,
        duration_ms=duration_ms,
        analysis_id=exec_context.get("analysis_id"),
        task_run_id=exec_context.get("task_run_id"),
        workflow_run_id=exec_context.get("workflow_run_id"),
        workflow_node_instance_id=exec_context.get("workflow_node_instance_id"),
    )
except Exception as e:
    logger.warning(f"Failed to create tool execution artifact: {e}")
```

### Auto-Capture in LLM Functions

The `CyLLMFunctions.llm_run()` method automatically captures:

```python
# After successful llm.ainvoke()
duration_ms = int((time.time() - start_time) * 1000)
await self._create_llm_artifact(
    function_name="llm_run",
    integration_id=effective_integration_id,
    prompt=prompt,
    completion=result,
    model=model,
    duration_ms=duration_ms,
)
```

### Fire-and-Forget Pattern

Both tool and LLM artifact capture use fire-and-forget:
- Exceptions are caught and logged
- Failures don't break the execution flow
- The user still receives their tool/LLM result

## Future Work

### UI Helper API for Alert Artifacts
Provide a simplified API for UI to retrieve all artifacts for an alert:

```
GET /v1/{tenant}/alerts/{alert_id}/artifacts
```

This would:
1. Look up the analysis_id associated with the alert
2. Retrieve all artifacts with that analysis_id
3. Also include manual attachments with alert_id
4. Group by artifact_type for easy UI consumption

### Additional Features
- Compression support (gzip, zstd)
- Artifact versioning (track changes over time)
- Artifact relationships (link related artifacts)
- Batch operations for bulk create/delete
- Streaming upload/download for large files
- Loading artifacts in Cy scripts (load_artifact_by_name, load_artifact_by_id)
