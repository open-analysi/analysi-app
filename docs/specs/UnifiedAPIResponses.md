+++
version = "1.0"
status = "active"

[[changelog]]
version = "1.0"
summary = "Sifnos envelope contract (Project Sifnos)"
+++

# Unified API Response Contract — Project Sifnos

## Problem

The REST API has grown organically across 29 router files with inconsistent response patterns. This makes client SDK development unpredictable and is a barrier to open-sourcing. Since there are no customers yet, this is the right time for breaking changes.

## Current State (10 patterns identified)

1. **List responses use 3 different patterns**: paginated envelopes (Tasks, Workflows), minimal envelopes (Control Events), and bare `list[T]` (API Keys, Members, Dispositions)
2. **Pagination fields vary**: `page/page_size/total_pages` vs `limit/offset` vs just `total`
3. **List field names differ**: `tasks`, `workflows`, `templates`, `rules`, `events`, `items`
4. **Many endpoints return untyped `dict`**: invisible in OpenAPI docs (sync-edges, check-delete, async jobs, workflow node creation)
5. **Same endpoint returns different types** based on query params (`include_relationships`, `slim`, `include_null_fields`)
6. **Error responses inconsistent**: `detail="string"` vs `detail={"error": ..., "message": ...}`
7. **`execution_time`** baked into some response models via `BaseResponse`, absent in others
8. **Async job responses (202)** use ad-hoc dict shapes
9. **Delete returns 204** (consistent — keep this)
10. **Create returns 201 + model** (consistent — keep this)

## Target: Envelope-Everything Contract

Every API response follows one of these shapes:

### Success — Single Item
```json
{
  "data": { "<resource fields>" },
  "meta": { "request_id": "uuid" }
}
```

### Success — List (always paginated)
```json
{
  "data": [ { "<resource>" }, "..." ],
  "meta": {
    "total": 42,
    "limit": 20,
    "offset": 0,
    "has_next": true,
    "request_id": "uuid"
  }
}
```

### Success — Delete (204 No Content)
No body. Keep as-is.

### Success — Async Job (202 Accepted)
```json
{
  "data": { "job_id": "uuid", "status": "accepted" },
  "meta": { "request_id": "uuid" }
}
```

### Error (4xx/5xx) — RFC 9457 Problem Details

Content-Type: `application/problem+json`

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Task with id 'abc' not found",
  "instance": "/v1/default/tasks/abc",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Validation errors (422) include field-level details:
```json
{
  "type": "about:blank",
  "title": "Validation Error",
  "status": 422,
  "detail": "Request validation failed",
  "request_id": "...",
  "errors": [
    {"loc": ["body", "name"], "msg": "Field required", "type": "missing"}
  ]
}
```

## Design Decisions

1. **Drop `execution_time` from response bodies** — it's a cross-cutting concern that belongs in HTTP headers (`X-Request-Duration`) or observability, not in business payloads. Remove `BaseResponse` as a parent class for resource responses.

2. **`meta.request_id`** — a UUID generated per request. Useful for debugging and support. Injected via middleware. Also included in error responses as a custom RFC 9457 extension field.

3. **All lists are offset-paginated** — even small collections (API keys, members). Consistent is better than optimal. Default `limit=50`, max `limit=200`. `ApiMeta` is extensible for future cursor-based pagination (`next_cursor`) without breaking the envelope.

4. **No conditional response shapes** — remove `include_relationships` (always include or make a separate endpoint), `slim` (use sparse fieldsets or a separate endpoint), `include_null_fields` (always include nulls — clients can ignore them).

5. **All responses typed with Pydantic models** — no bare `dict` returns. Every endpoint gets a `response_model=ApiResponse[TaskResponse]` (or `ApiListResponse[T]`). Endpoint return type annotations must use the **specific** Pydantic type matching `response_model` (e.g., `-> ApiResponse[TaskResponse]`, not `-> dict[str, Any]` or `-> ApiResponse[Any]`). The helper functions (`api_response`, `api_list_response`) return `ApiResponse[Any]` / `ApiListResponse[Any]` at runtime since they're generic, but the endpoint annotation narrows the type for IDE autocomplete and type-checking.

6. **RFC 9457 Problem Details for errors** — use the [`fastapi-problem-details`](https://github.com/g0di/fastapi-problem-details) library instead of custom error handlers. Industry standard (IETF RFC 9457, supersedes RFC 7807). One-line setup, auto-handles `HTTPException`, `RequestValidationError`, and unhandled exceptions. Clients can use RFC 9457 parsing libraries in any language. We extend with `request_id` as a custom field. **Exception**: `SQLAlchemyError` keeps a custom handler that returns RFC 9457 JSON directly (preserves 503 status, scrubs DB internals — raising inside Starlette exception handlers is unsafe).

## Common Library: `src/analysi/api/`

A shared module that eliminates per-router boilerplate. All routers import from here.

```
src/analysi/api/
├── __init__.py          # Re-exports public API
├── responses.py         # Schemas + helper functions
├── pagination.py        # PaginationParams FastAPI dependency
├── errors.py            # RFC 9457 setup via fastapi-problem-details
└── middleware.py         # RequestIdMiddleware, X-Request-Duration
```

### `responses.py` — Schemas and helpers

```python
class ApiMeta(BaseModel):
    request_id: str
    total: int | None = None
    limit: int | None = None
    offset: int | None = None
    has_next: bool | None = None

class ApiResponse[T](BaseModel):
    data: T
    meta: ApiMeta

class ApiListResponse[T](BaseModel):
    data: list[T]
    meta: ApiMeta

def api_response(data: Any, *, request: Request) -> ApiResponse[Any]:
    """Wrap single item in standard envelope. Returns Pydantic model."""

def api_list_response(items: list[Any], *, total: int, request: Request, pagination: Any | None = None) -> ApiListResponse[Any]:
    """Wrap list in standard envelope with pagination meta. Returns Pydantic model."""
```

### `pagination.py`

```python
class PaginationParams:
    """FastAPI dependency: pagination = Depends(PaginationParams)"""
    def __init__(self, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        self.limit = limit
        self.offset = offset
```

### `errors.py` — RFC 9457 via `fastapi-problem-details`

```python
import fastapi_problem_details as problem

def init_error_handling(app: FastAPI) -> None:
    """One-line setup: auto-converts HTTPException, RequestValidationError,
    and unhandled exceptions to RFC 9457 Problem Details format.
    Injects request_id as a custom extension field."""
    problem.init_app(app)
```

No custom `ApiError`/`ApiErrorDetail` schemas needed — the library handles everything.

### `middleware.py`

```python
class RequestIdMiddleware:
    """Generate UUID per request, store in request.state.request_id,
    add X-Request-Id header. The request_id is also injected into
    RFC 9457 error responses as a custom extension field."""

# X-Request-Duration header added via middleware (replaces execution_time in body)
```

## UI Alignment

The UI (`ui/`) already defines a matching generic type in `src/types/knowledge.ts`:

```typescript
export interface ApiResponse<T> {
  data: T;
  meta?: PaginationMeta;
}
```

**Note on `meta` optionality**: The backend contract requires `meta` on every success response (always present, never omitted). The UI's `meta?` is defensive TypeScript — not a contract weakening. When the UI is updated for Sifnos, `meta` should become required (`meta: ApiMeta`).

The UI was designed for this envelope but the backend never delivered it. Sifnos closes that gap. UI migration involves:
1. Replace per-resource `*ListResponse` types (e.g., `AlertsListResponse.alerts` → `ApiListResponse.data`)
2. Update service functions: `response.data.tasks` → `response.data.data`
3. Delete pagination conversion logic (audit trail page→offset)

## What NOT to Change

- HTTP status codes (201, 204, 202, 4xx) — these are correct
- Resource-level Pydantic models (TaskResponse, WorkflowResponse, etc.) — the inner data shapes are fine
- Authentication/authorization middleware
- URL structure and path parameters
- **Streaming/file download responses** — `StreamingResponse` (only `artifacts.py:242`, file download) bypasses the `{data, meta}` envelope since binary content cannot be wrapped in JSON. These responses still include `X-Request-Id` and `X-Request-Duration` headers for traceability.

## Scope

### In scope
- All REST API router files (~29 files)
- Base schema definitions
- Error handling middleware
- Request ID middleware
- Existing integration tests (must be updated)

### Out of scope
- MCP server endpoints (separate protocol)
- WebSocket endpoints (if any)
- Internal worker-to-worker endpoints (if clearly internal-only)
- `adhoc_search.py` — dead code (never mounted), will be deleted in Phase 5 cleanup
