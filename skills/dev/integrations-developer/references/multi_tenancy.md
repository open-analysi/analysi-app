# Naxos Multi-Tenancy Guide

**Purpose**: Understanding multi-tenant architecture in Analysi's Naxos framework

**Audience**: Integration developers building Naxos integrations

---

## Key Principles

### 1. No Global State - Use Injected Properties

**Bad — stateful connector pattern**:
```python
class Connector:
    def initialize(self):
        self._api_key = config["api_key"]  # Stored as instance variable

    def handle_action(self, param):
        headers = {"Key": self._api_key}  # Uses instance variable
```

**Good — Naxos stateless pattern**:
```python
class MyAction(IntegrationAction):
    async def execute(self, **kwargs):
        # Injected per-request, tenant-scoped
        api_key = self.credentials.get("api_key")
        base_url = self.settings.get("base_url")
        headers = {"Key": api_key}
```

**Why**: Naxos actions are stateless - credentials/settings injected per-request to ensure tenant isolation.

---

### 2. Tenant Scoping is Automatic

**What you DON'T need to do**:
- ❌ Manually filter by tenant_id
- ❌ Check tenant access permissions
- ❌ Encrypt credentials yourself

**What the framework does automatically**:
- ✅ Credentials filtered by `tenant_id`
- ✅ Integration lookups scoped to `(tenant_id, integration_id)`
- ✅ Execution context includes `tenant_id`
- ✅ Vault encryption scoped to tenant

**Example Flow**:
```python
# User request: GET /acme/integrations/abuseipdb-prod/execute
#
# Framework automatically:
# 1. Extracts tenant_id="acme" from URL
# 2. Queries: WHERE tenant_id='acme' AND integration_id='abuseipdb-prod'
# 3. Decrypts credential with tenant context
# 4. Injects into action.credentials

# Your action code - no tenant handling needed:
async def execute(self, **kwargs):
    api_key = self.credentials.get("api_key")  # Already tenant-scoped!
```

---

### 3. Multiple Integration Instances Per Tenant

Same tenant can have unlimited instances of same integration type, each with different credentials/settings:

```python
# Tenant "acme" creates two AbuseIPDB integrations
POST /acme/integrations
{
  "integration_id": "abuseipdb-prod",
  "integration_type": "abuseipdb",
  "credential": {"api_key": "prod-key"}
}

POST /acme/integrations
{
  "integration_id": "abuseipdb-dev",
  "integration_type": "abuseipdb",
  "credential": {"api_key": "dev-key"}
}

# Both work independently
POST /v1/acme/integrations/abuseipdb-prod/tools/lookup_ip/execute {...}
POST /v1/acme/integrations/abuseipdb-dev/tools/lookup_ip/execute {...}
```

---

## Anti-Patterns to Avoid

### ❌ Anti-Pattern 1: Hardcoded URLs

```python
# BAD - Single base URL for all tenants
BASE_URL = "https://api.example.com"

# GOOD - Configurable per-instance
base_url = self.settings.get("base_url", "https://api.example.com")
```

### ❌ Anti-Pattern 2: Shared State/Caching

```python
# BAD - Global cache shared across tenants
CACHE = {}
if ip in CACHE:
    return CACHE[ip]  # Tenant A sees Tenant B's data!

# GOOD - No global state (or tenant-scoped caching)
cache_key = f"{tenant_id}:{ip}"
```

### ❌ Anti-Pattern 3: Assuming Single Instance

```python
# BAD - Assumes only one instance
db.query(Integration).filter_by(integration_type="abuseipdb").first()

# GOOD - Use (tenant_id, integration_id) tuple
db.query(Integration).filter_by(
    tenant_id=tenant_id,
    integration_id=integration_id
).first()
```

### ❌ Anti-Pattern 4: Logging Credentials

```python
# BAD - Credentials in logs
logger.info(f"Using API key: {self.credentials.get('api_key')}")

# GOOD - Redact sensitive data
logger.info("Making authenticated request")
safe_headers = {k: "***" if k in ["Key", "Authorization"] else v
                for k, v in headers.items()}
```

---

## Multi-Tenancy Testing

### Test Multiple Instances

```python
@pytest.mark.integration
async def test_multiple_instances_same_tenant():
    """Verify tenant can have multiple instances of same type."""

    prod = await create_integration(
        tenant_id="acme",
        integration_id="abuseipdb-prod",
        credential={"api_key": "prod-key"}
    )

    dev = await create_integration(
        tenant_id="acme",
        integration_id="abuseipdb-dev",
        credential={"api_key": "dev-key"}
    )

    # Both work independently with different credentials
    assert (await execute_action("acme", "abuseipdb-prod", ...))["status"] == "success"
    assert (await execute_action("acme", "abuseipdb-dev", ...))["status"] == "success"
```

### Test Tenant Isolation

```python
@pytest.mark.integration
async def test_tenant_isolation():
    """Verify tenant A cannot access tenant B's integrations."""

    await create_integration(tenant_id="tenant-a", integration_id="abuseipdb", ...)
    await create_integration(tenant_id="tenant-b", integration_id="abuseipdb", ...)

    # Tenant A tries to access tenant B's integration
    with pytest.raises(ValueError, match="not found"):
        await execute_action(tenant_id="tenant-a", integration_id="abuseipdb", ...)
```

---

## Multi-Tenancy Checklist

**✅ Do This**:
- [ ] Use `self.credentials` for credential access (never hardcode)
- [ ] Use `self.settings` for configuration (allow per-instance config)
- [ ] Keep actions stateless (no instance variables)
- [ ] Allow configurable base URLs (multi-region support)
- [ ] Redact credentials in logs
- [ ] Test with multiple integration instances
- [ ] Test tenant isolation

**❌ Avoid This**:
- [ ] Don't use global state or class variables
- [ ] Don't cache data without tenant scoping
- [ ] Don't hardcode URLs or credentials
- [ ] Don't assume single instance per type
- [ ] Don't log sensitive credential data
- [ ] Don't manually filter by tenant_id (framework does it)

---

## Key Takeaway

> **Naxos handles ALL multi-tenancy complexity at the framework level.** Your action code remains simple and tenant-agnostic. Just use `self.credentials` and `self.settings` - the framework ensures they're properly scoped.

---

**See Also**:
- `references/adding_integrations.md` — Step-by-step guide for adding integrations
- `references/archetypes.md` — Archetype system and routing
