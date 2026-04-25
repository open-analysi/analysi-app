# Project Sifnos — Unified API Response Contract ✅

**Status**: Complete

## Key Points

- **Envelope-everything**: Every API response wraps data in `{"data": ..., "meta": {...}}`, replacing 10 different ad-hoc patterns across 150+ endpoints.
- **Common library at `src/analysi/api/`**: Shared module with `ApiResponse[T]`, `ApiListResponse[T]`, `PaginationParams`, error handler, and middleware — eliminates per-router boilerplate.
- **Consistent pagination**: All list endpoints use `limit/offset` with `total`, `has_next` in `meta`. Default `limit=50`, max `200`.
- **RFC 9457 Problem Details for errors**: Standard `application/problem+json` format via `fastapi-problem-details` library. Replaces mixed `HTTPException(detail=str|dict)` patterns. Includes `request_id` as extension field.
- **Request ID**: Middleware generates UUID per request, available in `meta.request_id` and `X-Request-Id` header.
- **`execution_time` moved to header**: `X-Request-Duration` header replaces `execution_time` in response body. `BaseResponse` parent class eliminated.
- **No conditional shapes**: Removed `include_relationships`, `slim`, `include_null_fields` query params that changed response structure.
- **All returns typed**: No bare `dict` returns — every endpoint uses `response_model=` with Pydantic models visible in OpenAPI docs. Endpoint return type annotations use the **specific** type matching `response_model` (e.g., `-> ApiResponse[TaskResponse]`, `-> ApiListResponse[EdgeResponse]`), not `dict[str, Any]` or `ApiResponse[Any]`.
- **UI alignment**: The UI already has a matching `ApiResponse<T>` generic type — Sifnos fulfills the contract the frontend was designed for.
- **Spec**: `docs/specs/UnifiedAPIResponses.md`

## Phases (ordered by difficulty)

| Phase | Scope | Routers | Endpoints | Status |
|-------|-------|---------|-----------|--------|
| 1 | Foundation — common library (`src/analysi/api/`), middleware, error handler | health, v1, users | ~7 | ✅ |
| 2 | Simple CRUD — small clean routers, build confidence | control events/rules/channels, api_keys, members, invitations, activity_audit, credentials, artifacts | ~35 | ✅ |
| 3 | Core Resources — big CRUD with sub-resources | tasks, workflows, knowledge_units, skills, kdg | ~60 | ✅ |
| 4 | Execution & Alerts — async 202 pattern, alert pipeline | alerts, task/workflow/integration execution, integrations | ~53 | ✅ |
| 5 | Kea, Admin, Remaining + legacy cleanup | kea_coordination, task_generations, task_building_runs, knowledge_extraction, task_assist, workflow_compose, admin | ~42 | ✅ |

## Completion Notes

All 29 routers (~197 endpoints) migrated to the `{data, meta}` envelope. UI (`ui/`) updated in parallel:
- Error interceptor parses RFC 9457 `application/problem+json` responses
- Shared `extractApiErrorMessage()` replaces 5+ inline error parsers across components
- Integration test scripts updated to read from `.data` envelope
- 187 service-layer tests including RFC 9457 error-path coverage

**Next**: TypeScript type generation from OpenAPI (see Post-Sifnos section in PLAN.md)
