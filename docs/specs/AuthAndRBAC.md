+++
version = "1.0"
date = "2026-03-24"
status = "active"

[[changelog]]
version = "1.0"
date = "2026-03-24"
summary = "Keycloak OIDC, RBAC, API keys (Project Mikonos)"
+++

# Authentication & Authorization (RBAC)
<!-- Project Mikonos -->

## Overview

Analysi supports two deployment models:
- **Self-hosted** (open source, Helm chart): operator deploys on their own Kubernetes cluster, single tenant per deployment
- **SaaS** (Analysi-managed): multi-tenant, Analysi runs the infrastructure

Both models share the same backend API and auth design. The difference is in who runs the identity provider.

---

## Key Concepts: Users vs Members

**User** — A global identity record, mirroring the Keycloak user store. One record per person, globally unique by email. Created automatically via JIT provisioning on first login. The `/users` API is read-only (identity resolution: `/users/me`, `/users/resolve`).

**Member** — A tenant-scoped role assignment linking a User to a specific tenant with a role (`owner`, `admin`, `analyst`, `viewer`). Stored in the `memberships` table with a unique constraint on `(user_id, tenant_id)`. The `/members` API manages invitations, role changes, and removal.

A single User can be a Member of multiple tenants with different roles:

```
Alice (User)
 ├── owner    in tenant "acme"       (Membership #1)
 ├── analyst  in tenant "globex"     (Membership #2)
 └── viewer   in tenant "contoso"    (Membership #3)
```

| API | Scope | Purpose |
|-----|-------|---------|
| `/v1/{tenant}/users/*` | Global identity | Look up who someone is (email, display name) |
| `/v1/{tenant}/members/*` | Tenant-scoped | Manage who has access to this tenant and with what role |

---

## Authentication

### Design: Hub IdP Pattern

All authentication paths produce a **JWT token**. The backend only ever validates JWTs — it does not care how the user authenticated.

```
Okta ──────┐
Azure AD ──┤──► [Hub IdP] ──► JWT ──► FastAPI (validates token)
Google ────┤
Email/pw ──┘
```

The Hub IdP for self-hosted deployments is **Keycloak**, bundled in the Helm chart. Keycloak handles:
- Email/password login natively
- OIDC federation to external IdPs (Okta, Azure AD, Google, etc.)
- SAML for enterprise customers
- Password reset, MFA, email verification

The UI does **not** implement a login form. It performs an OIDC redirect to Keycloak, which handles the login UI and redirects back with an auth code, which is exchanged for a JWT.

For the **SaaS deployment**, a managed auth provider (e.g., WorkOS, Auth0) replaces Keycloak. The FastAPI backend is identical — it validates JWTs regardless of issuer.

### OIDC Flow (UI)

Uses **Authorization Code flow with PKCE** (Proof Key for Code Exchange), as required by OAuth 2.1 for public clients (SPAs). PKCE prevents authorization code interception attacks.

```
1. User visits app → no valid token
2. App generates PKCE code_verifier + code_challenge
3. Redirect to Keycloak /authorize with code_challenge
4. User logs in at Keycloak (email/password or federated IdP)
5. Keycloak redirects back to /authentication/callback with auth code
6. App exchanges auth code + code_verifier for access_token + refresh_token
7. Tokens stored in ServiceWorker (never in JS memory — XSS-safe)
8. All API requests include: Authorization: Bearer <access_token>
9. On expiry: silent refresh via /authentication/silent-callback
```

### JWT Contract

The access token issued by Keycloak contains:

**Tenant user:**
```json
{
  "sub": "uuid-of-user-in-keycloak",
  "email": "alice@acme.com",
  "aud": "analysi-app",
  "tenant_id": "acme",
  "roles": ["analyst"],
  "iat": 1234567890,
  "exp": 1234568190,
  "iss": "https://auth.analysi.io/realms/analysi"
}
```

**Platform admin:**
```json
{
  "sub": "uuid-of-admin",
  "email": "admin@analysi.io",
  "aud": "analysi-app",
  "tenant_id": null,
  "roles": ["platform_admin"],
  "iat": 1234567890,
  "exp": 1234568190,
  "iss": "https://auth.analysi.io/realms/analysi"
}
```

| Claim | Source | Validation |
|---|---|---|
| `sub` | Keycloak user ID | Used as `user_id` in `CurrentUser` |
| `aud` | Keycloak client ID | Backend verifies `aud == "analysi-app"` — prevents cross-client token reuse |
| `tenant_id` | Custom mapper (user attribute) | `null` for `platform_admin`. For tenant users, must match `{tenant_id}` in URL path |
| `roles` | Custom mapper (realm roles, flattened) | Checked against permission map. `platform_admin` is a realm role that bypasses tenant checks |
| `exp` | Keycloak realm config | **Access token lifetime: 5 minutes** (configurable in Keycloak realm settings) |

**Access token lifetime is intentionally short (5 minutes).** This limits the damage window if a token is compromised. The UI silently refreshes tokens before expiry using the refresh token. See Token Lifecycle below.

### Token Lifecycle

Short-lived access tokens are the primary revocation mechanism. When a user is removed or a role changes, the impact is bounded:

```
Token compromised or user removed
  → Access token expires in ≤5 minutes
  → Next refresh token exchange is validated against Keycloak session
  → Keycloak rejects if user is disabled/removed → session ends
```

**Refresh token rotation:** Keycloak's "Revoke Refresh Token" setting is enabled. Each time a refresh token is used, a new one is issued and the old one is invalidated. If a stolen refresh token is reused, Keycloak detects the replay and revokes the entire session (token theft detection).

**Session monitoring:** The UI's `monitor_session: true` (via `@axa-fr/react-oidc`) polls the Keycloak session iframe and detects when the server-side session has been terminated. This is **UI-only** — it does not affect headless API clients or stolen Bearer tokens. When an admin disables a user in Keycloak, the UI tab detects this within the next session-check interval and forces re-authentication.

**Note:** Full OIDC Back-Channel Logout (server-push session termination) requires a `sid` claim in the JWT and a registered `backchannel_logout_uri` endpoint on FastAPI. This is not implemented in V1. Effective revocation relies on the 5-minute access token TTL + refresh token rotation. See `FUTURE_WORK.md` for the back-channel logout design.

**API key revocation** is immediate — deleting the `api_keys` row means the next request fails. No expiry window.

### Failure Modes (Fail-Closed)

The system always fails closed — when in doubt, deny. JWT and API key auth are independent failure domains.

| Component | Failure | Behavior |
|---|---|---|
| JWKS fetch | Fails at startup | **Server refuses to start** — cannot validate any tokens without keys |
| JWKS fetch | Fails at runtime (cache refresh) | **Use cached keys**, log warning — auto-recovers when Keycloak returns |
| JWKS cache | Expired + Keycloak still unreachable | **Fail closed — 401 all JWT-based requests** — API key auth continues working independently |
| Keycloak | Down entirely | Existing access tokens valid for up to 5 min. New logins fail. Refresh fails. Admin API (if JWT-only) becomes inaccessible. |
| PostgreSQL | Down | API key auth fails (cannot query `api_keys` table). JWT auth continues working. |
| Token | Invalid, expired, or tampered | **401** — always |
| Token | Valid JWT but wrong `aud` or `iss` | **401** — always |
| Token | Valid JWT but `tenant_id` mismatch with URL | **403** — not 404 (do not leak tenant existence) |

**Design principle:** The JWKS cache (`lifespan=300s`) provides resilience against brief Keycloak outages. Beyond the cache window, the system prefers denial over skipping validation. Health endpoints (`/healthz`, `/readyz`) are always exempt and remain reachable regardless of auth infrastructure state.

### API Key Authentication

For programmatic access (CI/CD, integrations), users can create API keys. These bypass Keycloak entirely and are validated directly by FastAPI.

API key format: `analysi_<random_32_chars>`  (e.g., `analysi_xK9mP2qR8nJvL3wY...`)

Validation: SHA-256 hash of the incoming key is compared to `key_hash` in the `api_keys` table. The plaintext key is shown **once** on creation and never stored.

---

## Authorization (RBAC)

### Roles

There are two scopes of roles:

**Tenant-scoped roles** (assigned via `memberships` table, apply to one tenant):

| Role | Description |
|---|---|
| `owner` | Full access including billing, user management, org deletion |
| `admin` | Manage integrations, settings, tasks, workflows, invite users |
| `analyst` | Trigger executions, disposition alerts, create/edit tasks |
| `viewer` | Read-only access across all resources |

**Platform-scoped role** (assigned via Keycloak realm role, applies across all tenants):

| Role | Description |
|---|---|
| `platform_admin` | Full access to all tenants + admin API. No `memberships` row required — authority comes from the Keycloak realm role. |

The `platform_admin` is the "uber administrator" — the person who operates the Analysi platform itself. In self-hosted deployments, this is the operator who deployed the Helm chart. In SaaS, this is internal Analysi staff.

**Key differences from tenant `owner`:**
- `platform_admin` has no `tenant_id` in their JWT — they target tenants via the URL path
- `platform_admin` can access the `/admin/v1/` endpoints (tenant roles cannot)
- `platform_admin` can access any tenant's data via `/v1/{tenant_id}/` without a `memberships` row
- `platform_admin` does NOT need a row in the `memberships` table (but does need a `users` row, JIT provisioned)
- A user can be both a `platform_admin` AND have tenant-scoped roles (e.g., `platform_admin` + `analyst` on tenant `demo`)

### Resources & Actions

| Resource | Actions |
|---|---|
| `tasks` | `create`, `read`, `update`, `delete`, `execute` |
| `workflows` | `create`, `read`, `update`, `delete`, `execute` |
| `alerts` | `read`, `analyze`, `disposition` |
| `integrations` | `create`, `read`, `update`, `delete`, `execute` |
| `knowledge_units` | `create`, `read`, `update`, `delete` |
| `control_event_rules` | `create`, `read`, `update`, `delete` |
| `audit_trail` | `read` |
| `members` | `invite`, `read`, `update`, `remove` |
| `api_keys` | `create`, `read`, `delete` (own keys only) |

### Role → Permission Matrix

| Resource + Action | owner | admin | analyst | viewer |
|---|---|---|---|---|
| tasks.create | ✅ | ✅ | ✅ | ❌ |
| tasks.read | ✅ | ✅ | ✅ | ✅ |
| tasks.update | ✅ | ✅ | ✅ | ❌ |
| tasks.delete | ✅ | ✅ | ❌ | ❌ |
| tasks.execute | ✅ | ✅ | ✅ | ❌ |
| workflows.create | ✅ | ✅ | ✅ | ❌ |
| workflows.read | ✅ | ✅ | ✅ | ✅ |
| workflows.update | ✅ | ✅ | ✅ | ❌ |
| workflows.delete | ✅ | ✅ | ❌ | ❌ |
| workflows.execute | ✅ | ✅ | ✅ | ❌ |
| alerts.read | ✅ | ✅ | ✅ | ✅ |
| alerts.analyze | ✅ | ✅ | ✅ | ❌ |
| alerts.disposition | ✅ | ✅ | ✅ | ❌ |
| integrations.* | ✅ | ✅ | ❌ | ❌ |
| integrations.read | ✅ | ✅ | ✅ | ✅ |
| knowledge_units.* | ✅ | ✅ | ✅ | ✅ (read only) |
| control_event_rules.* | ✅ | ✅ | ❌ | ❌ |
| audit_trail.read | ✅ | ✅ | ✅ | ✅ |
| members.invite | ✅ | ✅ | ❌ | ❌ |
| members.read | ✅ | ✅ | ✅ | ✅ |
| members.update | ✅ | ✅ | ❌ | ❌ |
| members.remove | ✅ | ❌ | ❌ | ❌ |
| api_keys.create | ✅ | ✅ | ✅ | ✅ |
| api_keys.delete | ✅ (any) | ✅ (any) | ✅ (own) | ✅ (own) |

### Enforcement

Authorization is enforced in **FastAPI via dependency injection**. A `require_permission` dependency is injected at the router level:

```python
@router.post("/v1/{tenant_id}/tasks")
async def create_task(
    tenant_id: str,
    current_user: CurrentUser = Depends(require_permission("tasks", "create")),
    ...
):
```

`require_permission` validates that `current_user.tenant_id == tenant_id` (tenant isolation) and that the user's role has the requested permission.

**Platform admin bypass:** If `current_user.is_platform_admin` is `True`, `require_permission` skips the tenant match check and grants access. The platform admin can access any tenant's resources via the URL path. All actions are still logged in the audit trail with the admin's real `user_id`.

**Invariant — null tenant_id:** A JWT with `tenant_id: null` but WITHOUT `platform_admin` in `roles` is **always a hard 403**. This must be checked explicitly — the `str | None` typing means a naive `if current_user.tenant_id and current_user.tenant_id != tenant_id` check would silently pass null through. The correct check is:
```python
if not current_user.is_platform_admin:
    if current_user.tenant_id is None or current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403)
```

**Admin API protection:** The `/admin/v1/` endpoints use a separate `require_platform_admin` dependency that checks for the `platform_admin` role. Tenant-scoped roles (`owner`, `admin`, etc.) cannot access admin endpoints.

```python
# Admin router — platform_admin only
@router.delete("/admin/v1/{tenant_id}/task-runs")
async def bulk_delete_task_runs(
    tenant_id: str,
    current_user: CurrentUser = Depends(require_platform_admin()),
    ...
):
```

**Multi-role resolution:** A user may have multiple roles (e.g., both `analyst` and `viewer`). The effective permission set is the **union** of all assigned roles. If any role grants the requested permission, access is allowed.

**Exempt endpoints:** The following endpoints are NOT protected and require no authentication:
- `GET /healthz` — K8s liveness probe
- `GET /readyz` — K8s readiness probe
- `POST /v1/auth/token` — token exchange endpoint (if implemented)
- Keycloak OIDC discovery endpoints are served by Keycloak itself, not FastAPI

V1 uses a simple in-memory permission map. The design is compatible with OPA/Cedar as a future drop-in replacement for the map lookup.

---

## Database Schema

All auth tables live in the main PostgreSQL database.

```sql
-- Human identity records (mirrors Keycloak user store)
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    keycloak_id     VARCHAR(255) UNIQUE NOT NULL,  -- Keycloak's sub claim
    email           VARCHAR(255) UNIQUE NOT NULL,
    display_name    VARCHAR(255),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ
);

-- Who belongs to which tenant with what role
CREATE TABLE memberships (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id   VARCHAR(255) NOT NULL,
    role        VARCHAR(50) NOT NULL CHECK (role IN ('owner', 'admin', 'analyst', 'viewer')),
    invited_by  UUID REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, tenant_id)
);
-- IMPORTANT: When a membership is deleted, cascade-delete that user's API keys for the same tenant.
-- Enforced at the application layer in MembershipRepository.remove() — delete all api_keys WHERE
-- user_id = ? AND tenant_id = ? before or within the same transaction as the membership deletion.
-- This prevents orphaned API keys surviving after a user is removed from a tenant.

-- Pending invitations (email → tenant)
-- Invite token is generated with secrets.token_urlsafe(32), hashed with SHA-256.
-- Default expiry: 7 days. Single-use: accepted_at is set on first acceptance,
-- subsequent attempts are rejected. Rate limited: max 5 accept attempts per
-- token_hash per hour to prevent brute-force.
CREATE TABLE invitations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   VARCHAR(255) NOT NULL,
    email       VARCHAR(255) NOT NULL,
    role        VARCHAR(50) NOT NULL,
    token_hash  VARCHAR(64) NOT NULL UNIQUE,  -- SHA-256 of invite token
    invited_by  UUID REFERENCES users(id),
    expires_at  TIMESTAMPTZ NOT NULL DEFAULT now() + INTERVAL '7 days',
    accepted_at TIMESTAMPTZ,                  -- non-NULL = used, reject further attempts
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Programmatic API keys
CREATE TABLE api_keys (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    VARCHAR(255) NOT NULL,
    user_id      UUID REFERENCES users(id) ON DELETE CASCADE,  -- NULL = system key
    name         VARCHAR(255) NOT NULL,
    key_hash     VARCHAR(64) NOT NULL UNIQUE,  -- SHA-256 of full key
    key_prefix   VARCHAR(16) NOT NULL,         -- first chars shown in UI
    scopes       JSONB NOT NULL DEFAULT '[]',  -- V2: ["tasks:read", "workflows:execute"]. V1: column exists but not enforced — API keys inherit the user's role permissions
    last_used_at TIMESTAMPTZ,
    expires_at   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## Secret Storage

| Secret | Where | Why |
|---|---|---|
| User passwords | Keycloak (internal) | Keycloak owns human auth |
| OAuth tokens & refresh tokens | Keycloak (internal) | Keycloak owns sessions |
| Keycloak client secret | Vault | Retrieved in plaintext by FastAPI to talk to Keycloak |
| JWT signing/verification keys | Keycloak (fetched via JWKS) | Rotated by Keycloak |
| API key values | Never stored (shown once) | SHA-256 hash in PostgreSQL |
| API key hashes | PostgreSQL | Verification only, never retrieved as plaintext |
| Integration credentials | Vault (existing) | Passed in plaintext to external APIs |

---

## Backend: CurrentUser & Middleware

Every protected request resolves to a `CurrentUser`:

```python
@dataclass
class CurrentUser:
    user_id: str            # Keycloak sub
    email: str
    tenant_id: str | None   # from JWT claim or api_keys table. None for platform_admin.
    roles: list[str]
    actor_type: str          # "user" | "api_key" | "system"

    @property
    def is_platform_admin(self) -> bool:
        return "platform_admin" in self.roles
```

FastAPI middleware validates the token and makes `CurrentUser` available via dependency injection. The audit trail (existing) reads `actor_id` and `actor_type` from `CurrentUser` — no changes to audit trail schema needed.

**Platform admin tenant targeting:** When `current_user.is_platform_admin` is `True`, the user's `tenant_id` is `None`. The target tenant comes from the URL path parameter (`/v1/{tenant_id}/...` or `/admin/v1/{tenant_id}/...`). The `require_permission` dependency handles this automatically.

---

## UI Changes

### What changes

| Component | Change |
|---|---|
| `apiClient.ts` | Read `tenant_id` from `authStore` instead of `VITE_BACKEND_API_TENANT`; attach `Authorization: Bearer` header to all requests |
| `authStore.ts` | New Zustand store: JWT, decoded claims, tenant_id, refresh logic |
| `App.tsx` | Wrap all routes in `<ProtectedRoute>` |
| `ProtectedRoute.tsx` | New component: redirect to Keycloak if no valid token |
| `nginx.conf` | Add `/api` → backend proxy block |

### What does NOT change

- All feature code in pages/services — they call `apiClient.get('/tasks')` as before
- Backend URL structure — `/v1/{tenant_id}/tasks` remains unchanged
- Any component that doesn't touch auth

### Tenant in API URLs

The `tenant_id` comes from the decoded JWT. The apiClient injects it transparently:

```typescript
// Before: build-time env var
baseURL = `/api/v1/${import.meta.env.VITE_BACKEND_API_TENANT}`

// After: runtime JWT claim, same injection point
baseURL = `/api/v1/${authStore.getState().tenant_id}`
```

Feature code is unaffected. Individual API calls remain:
```typescript
apiClient.get('/tasks')       // not apiClient.get('/acme/tasks')
```

---

## Deployment

### Self-Hosted (Helm Chart)

The Helm chart bundles Keycloak as a dependency. The operator configures:
- Keycloak realm name (= `tenant_id`)
- Admin credentials
- Optional: external IdP connection (Okta OIDC config)

Single-tenant per deployment — the `tenant_id` is fixed per installation.

**First user bootstrap:** On first login, if no `users` row exists for the Keycloak `sub`, the backend auto-provisions one:
1. User logs into Keycloak (admin creates the first Keycloak user, or uses federated IdP)
2. First API request with valid JWT triggers JIT (Just-In-Time) user provisioning
3. If no `memberships` exist for the `tenant_id`, the first user is assigned the `owner` role
4. Subsequent users require an invitation from the owner

This avoids a separate bootstrap CLI or manual DB insertion.

### SaaS

Keycloak is replaced by a managed provider. FastAPI validates JWTs from a different issuer. The only change is the `JWKS_URI` environment variable. Everything else is identical.

---

## Worker-to-API Authentication

Workers (alert-analysis-worker, integrations-worker) are separate Docker containers that call the backend API over HTTP using `httpx`. They do NOT access the database directly.

### Design: System API Keys

Workers authenticate using **system API keys** — API keys with `user_id = NULL` and `actor_type = "system"`. These are pre-provisioned during deployment.

```
Worker → HTTP request with Authorization: Bearer analysi_<system_key>
       → FastAPI validates SHA-256 hash against api_keys table
       → CurrentUser(user_id="system", tenant_id=<from_key>, roles=["system"], actor_type="system")
```

**System role (not `admin`):** Workers are assigned the `system` role — a minimal role that grants only what workers need: read/write alerts, read/execute tasks and workflows, read integrations. Workers do NOT get `members.invite`, `api_keys.create`, `integrations.delete`, or any other destructive permission. A compromised worker container cannot establish persistence (create API keys, invite accounts) or delete data. The `system` role is defined in the permission map alongside tenant roles but is never assignable to human users.

```python
PERMISSIONS = {
    ...
    "system": {
        "alerts": {"read", "analyze"},
        "tasks": {"read", "execute"},
        "workflows": {"read", "execute"},
        "integrations": {"read", "execute"},
    },
}
```

**Why system API keys (not JWT)?**
- Workers don't have a human identity — they act on behalf of the system
- No refresh token dance — keys are long-lived and rotatable
- Same validation path as user API keys (no new auth code)
- Audit trail correctly shows `actor_type: "system"` vs `actor_type: "user"`

**Provisioning:**
- `docker-compose up` seeds a system API key via init script
- Helm chart generates one via a Kubernetes Job on install
- Key is injected as an environment variable: `ANALYSI_SYSTEM_API_KEY`

**Existing code impact:**
- `BackendAPIClient` already defines `BACKEND_API_AUTH_TOKEN` but never uses it — wire it up
- `IntegrationAPIClient` follows the same pattern

**Credential rotation without downtime:**
1. Create a new system API key via the REST API (or Helm upgrade with new secret)
2. Update the `ANALYSI_SYSTEM_API_KEY` env var in the worker deployment
3. Workers pick up the new key on next restart (rolling restart = zero downtime)
4. Delete the old API key via the REST API

Both old and new keys work simultaneously during the rolling restart window. No coordination needed.

---

## MCP Server Authentication

MCP servers are embedded Starlette ASGI apps mounted inside FastAPI. They cannot use FastAPI's `Depends()` — auth must go through middleware.

### Design: Extend MCPTenantMiddleware

The existing `MCPTenantMiddleware` already extracts `tenant_id` from the URL path and stores it in a `ContextVar`. We extend it to also extract and validate Bearer tokens.

```python
# Current: extracts tenant_id from path
# After: also extracts Bearer token → validates JWT or API key → sets CurrentUser ContextVar

class MCPAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # 1. Extract tenant_id from path (existing logic)
        tenant_id = extract_tenant_from_path(request.url.path)

        # 2. Extract and validate Bearer token (new)
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        current_user = await validate_token_or_api_key(token)

        # 3. Verify tenant match
        if current_user.tenant_id != tenant_id:
            return JSONResponse(status_code=403, ...)

        # 4. Store in ContextVar for tool functions to access
        _current_user_var.set(current_user)
        return await call_next(request)
```

**MCP client configuration:** Claude Code and other MCP clients pass the Bearer token in the `Authorization` header, which is supported by the MCP Streamable HTTP transport spec (June 2025).

---

## Developer CLI Tool (`analysi`)

A lightweight CLI tool for local development that handles auth and credential caching, keeping `docker-compose up && curl` workflows frictionless.

### Commands

```bash
# Authenticate against local Keycloak (OIDC device flow or password grant)
analysi auth login

# Print a valid access token (auto-refreshes if expired)
analysi auth token

# Show current auth status (who am I, which tenant, token expiry)
analysi auth status

# Clear cached credentials
analysi auth logout
```

### How It Works

1. `analysi auth login` authenticates against the local Keycloak instance using **OIDC Resource Owner Password Grant** (dev-only, not production) or **Device Authorization Flow** (opens browser)
2. Tokens are cached in `~/.analysi/credentials.json` (access_token + refresh_token + expiry)
3. `analysi auth token` returns a valid token, silently refreshing if expired
4. Integrates with shell workflows: `curl -H "Authorization: Bearer $(analysi auth token)" localhost:8000/v1/demo/tasks`

### Implementation

- Single Python file, installed via `pip install -e .` from the project root (or `poetry install`)
- Uses `httpx` (already a dependency) for HTTP calls
- Token cache file: `~/.analysi/credentials.json` (gitignored, user-scoped)
- Default Keycloak URL: `http://localhost:8080` (configurable via `ANALYSI_AUTH_URL`)

### MCP Config Integration

```json
{
  "mcpServers": {
    "cy-script-assistant": {
      "url": "http://localhost:8000/mcp/cy-script-assistant",
      "headers": {
        "Authorization": "Bearer ${ANALYSI_TOKEN}"
      }
    }
  }
}
```

Developers run `export ANALYSI_TOKEN=$(analysi auth token)` before starting Claude Code, or add it to their shell profile.

---

## Development Mode

Local development must remain as frictionless as `docker-compose up`.

### Design: Auto-Provisioned Dev Credentials

When `ANALYSI_AUTH_MODE=dev` (set in `docker-compose.yml`):

1. **Keycloak starts with a pre-configured realm** — realm `analysi`, client `analysi-app`, a test user `dev@analysi.local` with password `dev`, role `owner`, tenant `demo`
2. **A system API key is auto-generated** — printed to stdout on first `docker-compose up`, also written to `.env.dev` (gitignored)
3. **The CLI tool auto-detects dev mode** — `analysi auth login` uses the dev user credentials without prompting

### What Does NOT Change

- `docker-compose up` still brings everything up with zero manual auth steps
- Existing curl/httpx scripts work by adding one header (or using `analysi auth token`)
- Tests use a global auth fixture (see Test Migration below) — no per-test auth setup

### Production Mode

When `ANALYSI_AUTH_MODE=production` (or unset):
- No dev user is created
- No credentials are printed
- Keycloak requires manual realm and user configuration
- CLI tool uses browser-based OIDC flow

---

## Test Migration Strategy

99 integration test files make ~2,454 HTTP calls. All will break when auth is enforced.

### Design: Global Auth Override Fixture

A single conftest.py fixture provides a pre-authenticated `CurrentUser` for all tests:

```python
# tests/conftest.py
@pytest.fixture(autouse=True)
def override_auth(app):
    """Inject a test user into all requests — no real JWT needed."""
    test_user = CurrentUser(
        user_id="test-user-id",
        email="test@analysi.local",
        tenant_id=TEST_TENANT_ID,  # matches existing test tenant
        roles=["owner"],
        actor_type="user",
    )
    app.dependency_overrides[get_current_user] = lambda: test_user
    yield
    app.dependency_overrides.pop(get_current_user, None)
```

**Why this works:**
- Tests already use `app.dependency_overrides` pattern extensively
- `autouse=True` means zero changes to existing test files
- Tests that need a specific role can override locally: `app.dependency_overrides[get_current_user] = lambda: CurrentUser(roles=["viewer"])`
- RBAC-specific tests (Phase 3) explicitly test each role's access

---

## Implementation Notes (from library research)

### Backend: PyJWT + JWKS

**Library:** `PyJWT` with `cryptography` package (not `python-jose`).

`PyJWKClient` handles JWKS fetching, caching, and key rotation natively:

```python
from jwt import PyJWKClient
import jwt

jwks_client = PyJWKClient(
    jwks_url,
    cache_jwk_set=True,
    lifespan=300,          # 5 min cache TTL
    timeout=30
)

signing_key = jwks_client.get_signing_key_from_jwt(token)
payload = jwt.decode(
    token,
    signing_key,
    algorithms=["RS256"],     # MUST hardcode — never derive from token
    audience="analysi-app",
    issuer=KEYCLOAK_ISSUER,
    leeway=5                  # clock skew tolerance between containers
)
```

**Key gotchas:**
- `algorithms` parameter must be hardcoded to `["RS256"]` — deriving from the token is a security vulnerability
- `leeway=5` needed for clock skew between Keycloak and FastAPI Docker containers
- On `kid` mismatch (key rotation), `PyJWKClient` auto-retries with a fresh JWKS fetch
- Use `auto_error=False` on `OAuth2PasswordBearer` so missing tokens fall through to API key check
- Exception hierarchy: catch `ExpiredSignatureError`, `InvalidAudienceError`, `InvalidIssuerError`, `InvalidSignatureError` specifically, then `InvalidTokenError` as catch-all

### Keycloak Docker Setup

**Image:** `quay.io/keycloak/keycloak:latest` with `start-dev` command.

**Realm provisioning:** JSON file import via `--import-realm` flag (idempotent — skips if realm exists):

```yaml
# docker-compose.yml
keycloak:
  image: quay.io/keycloak/keycloak:latest
  command: start-dev --import-realm
  environment:
    KC_BOOTSTRAP_ADMIN_USERNAME: admin       # NOT the old KEYCLOAK_ADMIN
    KC_BOOTSTRAP_ADMIN_PASSWORD: change_me
  volumes:
    - ./docker/keycloak/realm-analysi.json:/opt/keycloak/data/import/realm-analysi.json
```

**Key gotchas:**
- Admin env vars are `KC_BOOTSTRAP_ADMIN_*` (not `KEYCLOAK_ADMIN_*` — deprecated)
- Import path is `/opt/keycloak/data/import/` (not `/tmp/`)
- `start-dev` disables HTTPS and enables theme hot-reload; Helm chart uses `start` with TLS
- Keycloak puts roles under `realm_access.roles` by default — we need a custom `oidc-usermodel-realm-role-mapper` to flatten to top-level `roles` claim
- `tenant_id` custom claim uses `oidc-usermodel-attribute-mapper` mapping a user attribute to a JWT claim. **Critical**: the mapper must set `User Editable: false` — without this, users can modify their own `tenant_id` attribute via the Keycloak Account Console and mint tokens for a different tenant. This must be enforced in the realm JSON import.
- `offline_access` scope must be enabled on the client for refresh tokens to work
- Prefer realm JSON import over `python-keycloak` admin scripts for dev setup (atomic, idempotent)
- Reserve `python-keycloak` for CLI tool (OpenID API) and runtime user provisioning (invitation acceptance)

### UI: @axa-fr/react-oidc

**Library:** `@axa-fr/react-oidc` (not raw `oidc-client-ts`).

**Token storage:** ServiceWorker mode — tokens never touch JS memory, more secure against XSS. Requires `OidcServiceWorker.js` in public directory.

```typescript
const configuration = {
  client_id: 'analysi-app',
  redirect_uri: window.location.origin + '/authentication/callback',
  silent_redirect_uri: window.location.origin + '/authentication/silent-callback',
  scope: 'openid profile email offline_access',  // offline_access required for refresh tokens
  authority: KEYCLOAK_URL + '/realms/analysi',
  service_worker_relative_url: '/OidcServiceWorker.js',
  service_worker_only: false,    // falls back to sessionStorage if SW unavailable
  monitor_session: true,         // detect Keycloak session expiry
  // PKCE is enabled by default in @axa-fr/react-oidc — no extra config needed.
  // Keycloak client must have "Proof Key for Code Exchange Code Challenge Method" set to S256.
};
```

**Key gotchas:**
- `offline_access` scope is **required** in scope string — without it, no refresh token is issued and sessions expire
- Callback path is `/authentication/callback` by convention — not `/callback`
- Silent refresh needs a separate route: `/authentication/silent-callback` with a minimal HTML page
- `monitor_session: true` detects when Keycloak session expires server-side (user logged out from another tab)
- ServiceWorker mode stores tokens securely but requires `OidcServiceWorker.js` in public directory
- Custom components for loading/error/session-lost states integrate with existing UI patterns

---

## Security Hardening (woven into phases)

Security is not a separate phase — it is integrated into each implementation phase.

### Token & API Key Security (Phase 1)
- **Short-lived access tokens**: 5-minute TTL limits compromise window. Silent refresh handles UX.
- **Refresh token rotation**: Each refresh issues a new token and invalidates the old one. Reuse detection revokes the entire session.
- **Timing-safe comparison**: Use `hmac.compare_digest` for API key hash verification — prevents timing attacks that leak hash bytes one at a time
- **Sufficient entropy**: Generate keys with `secrets.token_urlsafe(32)` (256 bits of randomness)
- **Algorithm pinning**: Hardcode `algorithms=["RS256"]` — never derive from the token header (algorithm confusion attack)
- **Audience validation**: Verify `aud == "analysi-app"` — prevents cross-client token reuse

### Network & Endpoint Security (Phase 3)
- **Rate limiting**: In-memory sliding window on auth endpoints (login, token refresh, API key creation). Prevents brute force without external infrastructure
- **Security headers**: FastAPI middleware adds `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security`
- **CORS**: Restrict `Access-Control-Allow-Origin` to known UI domains (no `*`)
- **Auth event audit logging**: Failed login attempts, API key creation/revocation, role changes recorded in audit trail

### Keycloak Hardening (Phase 5)
- **Brute force protection**: Keycloak's built-in lockout after N failed attempts (realm config)
- **Password policy**: Minimum length, complexity requirements in realm config

### UI Security (Phase 6)
- **PKCE** (Proof Key for Code Exchange): Required by OAuth 2.1 for SPAs. Prevents authorization code interception. Enabled by default in `@axa-fr/react-oidc`; Keycloak client configured with S256 challenge method.
- **CSP headers**: `Content-Security-Policy` in nginx prevents XSS even if a bug exists
- **ServiceWorker token storage**: Tokens never in JS memory — XSS cannot exfiltrate them
- **OIDC `state` parameter**: CSRF protection built into the OIDC flow

### Dev Workflow Tooling (Phase 1)
- **`bandit`**: Python SAST scanner — catches hardcoded secrets, SQL injection, insecure hash usage. `make security-scan`
- **`pip-audit`**: Checks Python dependencies for known CVEs. `make audit-deps`
- **`gitleaks`**: Pre-commit hook — prevents accidental secret commits
- **`npm audit`**: UI dependency vulnerability check (built into npm)

---

## Out of Scope (V1)

- **Fine-grained resource ownership** (e.g., "only the creator can delete")
- **Policy engine** (OPA/Cedar) — V1 uses an in-memory permission map; compatible upgrade path exists
- **Per-tenant custom roles**
- **Group-based permissions**
- **API key scope enforcement** — the `scopes` column exists in the schema for forward compatibility, but V1 API keys inherit the creating user's role permissions. Scope-level restriction is a V2 feature.
- **SCIM provisioning** — Keycloak supports SCIM via extensions for automatic user provisioning from enterprise IdPs (Okta, Azure AD). V1 uses invitation-based onboarding. SCIM is a natural V2 addition for enterprise customers who want automated user lifecycle management.
