# Auth Module — Dual-Path Invariant

**Any auth change must be applied to BOTH paths.** The system has two independent authentication/authorization paths that must stay in sync:

| Concern | REST API path | MCP path |
|---------|--------------|----------|
| Auth enforcement | `auth/dependencies.py` → `get_current_user()` | `mcp/middleware.py` → `MCPTenantMiddleware.dispatch()` |
| RBAC permissions | `auth/dependencies.py` → `require_permission()` | `mcp/context.py` → `check_mcp_permission()` (per-tool) |
| Role resolution | `auth/dependencies.py` → `_resolve_local_roles()` | `mcp/middleware.py` → `_resolve_jwt_local_roles()` |
| Actor identity | `dependencies/audit.py` → `get_audit_context()` | `mcp/context.py` → `get_mcp_actor_user_id()` |

## Checklist for auth changes

1. **Authentication** — If you change how credentials are validated (JWT, API key), update both `auth/dependencies.py` and `mcp/middleware.py`.
2. **Role resolution** — If you change how roles are determined, update both `_resolve_local_roles` (REST) and `_resolve_jwt_local_roles` (MCP).
3. **Permission map** — Changes to `auth/permissions.py` affect both REST and MCP RBAC. Both paths use `has_permission()`.
4. **New endpoints** — REST endpoints need `dependencies=[Depends(require_permission(...))]` on every write handler (not just the router level). MCP mutation tools must call `check_mcp_permission(resource, action)` before any writes.
5. **Tenant isolation** — REST uses `check_tenant_access()`. MCP middleware enforces tenant match after authentication. System actors and platform_admin bypass.

## Key design decisions

- **Local membership is source of truth for roles**, not JWT claims. JWT roles may be stale after admin role changes.
- **MCP middleware rejects all unauthenticated requests** (no pass-through). Both Bearer and API key must validate successfully.
- **`get_mcp_actor_user_id()` raises RuntimeError** when no authenticated user is present — it never silently falls back to SYSTEM_USER_ID.
- **Role resolution fails closed**: when a user exists locally but has no membership, roles are cleared to `[]` (not kept from JWT). Both paths behave the same way.
- **MCP tenant isolation**: middleware rejects requests where the authenticated user's tenant doesn't match the URL tenant. System actors and platform_admin bypass.
- **System API keys use `system` role with explicit permissions** — NOT `platform_admin`. Workers operate under `_SYSTEM_PERMS` in `permissions.py`, which enumerates exactly what workers can do. If a new worker operation needs a permission, add it to `_SYSTEM_PERMS`. Never add `platform_admin` to system keys — that bypasses ALL RBAC checks and creates a privilege escalation vector.
