# Routers — API Conventions

## Response Envelope (Project Sifnos)

Every endpoint MUST return the `{data, meta}` envelope. No exceptions.

- **Single items**: `api_response(MySchema(...), request=request)` → `{"data": {...}, "meta": {"request_id": "..."}}`
- **Lists**: `api_list_response(items, total=N, request=request)` → `{"data": [...], "meta": {"total": N, "request_id": "...", ...}}`
- **Errors** (HTTPException): NOT wrapped — FastAPI returns `{"detail": "..."}` directly
- **204 DELETE**: No body, no wrapping needed
- Import from `analysi.api.responses`: `ApiResponse`, `ApiListResponse`, `api_response`, `api_list_response`
- Import `PaginationParams` from `analysi.api.pagination` for list endpoints with `limit`/`offset`
- Every endpoint function MUST accept `request: Request` (from `fastapi`) to pass to `api_response()`
- When a Pydantic body and `Request` are both needed, rename the body param to `body` (not `request`)

## Error Handling

### Error messages MUST NOT leak internals

- **Never** pass `str(e)` or `f"...{e}"` to `HTTPException(detail=...)`.
- Use generic, static messages from `analysi.auth.messages` constants.
- Log the real error server-side with `logger.error(...)` before raising.

### Status code rules for exception handlers

| Exception type | Status code | Detail message |
|---|---|---|
| `ValueError` (validation) | 400 | Static message describing the resource (e.g., "Invalid workflow definition") |
| `ValueError` (not found) | 404 | "Resource not found" or specific like "Alert not found" |
| `HTTPException` | Re-raise as-is | — |
| `Exception` (catch-all) | **500** | `"Internal server error"` — never 400 |

**Why 500 for broad `except Exception`**: A catch-all Exception likely indicates a server fault (DB error, unexpected state), not a client mistake. Returning 400 hides server issues from ops monitoring and misleads API consumers.

### Permission error messages

Use `INSUFFICIENT_PERMISSIONS` constant from `analysi.auth.messages`. Never include the resource or action name in the error detail — this prevents attackers from enumerating valid resources/actions.

### Domain-specific errors: use RFC 9457 ProblemResponse, not custom schemas

All errors use RFC 9457 Problem Details (`ProblemResponse` from `fastapi_problem_details`). When an endpoint needs structured errors with custom fields (e.g., `error_code`, `hint`), pass them as `**extra` kwargs — they become RFC 9457 extension members:

```python
from fastapi_problem_details import ProblemResponse
return ProblemResponse(
    status=422,
    title="Missing SKILL.md",
    detail="Every skill package needs a SKILL.md file...",
    request_id=getattr(request.state, "request_id", "unknown"),
    error_code="missing_skill_md",  # extension member
    hint="Add a SKILL.md file...",  # extension member
)
```

- `title` and `detail` are standard RFC 9457 fields — use them, don't invent `message` or `error`
- **NEVER** create separate error Pydantic schemas — all errors share `ProblemDetail` (in `schemas/base.py`)
- **NEVER** use `create_error_response()` from legacy middleware — it produces a different shape
- The `ProblemDetail` model is registered as the default error response on the FastAPI app
