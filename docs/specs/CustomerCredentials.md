+++
version = "1.0"
status = "active"

[[changelog]]
version = "1.0"
summary = "Vault Transit credential storage"
+++

# Customer Credentials – Minimal Spec (Dev-first, SOC2-ready)

**Scope:** Store tenant-scoped customer credentials (user/pass, API keys, OAuth tokens) using **Vault Transit** for crypto and **Postgres** for ciphertext. Keep it local now, production‑mappable later. Zero plaintext at rest.

**Design Decisions:**
- **Separate credentials table** for clean separation of concerns and audit trail
- **JSON blob storage** for flexible credential structures across different auth types
- **Multiple credentials per integration** via junction table (integration_credentials)
- **Mapping to Integration system:** provider→integration_type, account→credential label

---

## 1) Minimal Architecture

* **Write:** App → Vault **Transit `encrypt`** (AAD: `tenant_id|provider[|account]`) → store **ciphertext** in DB.
* **Read:** Load ciphertext → Transit **`decrypt`** (same AAD) → use plaintext **in memory only**.
* **Rotate:** `vault write -f transit/keys/<key>/rotate`; optional rewrap job to bump versions.

---

## 2) Local Stack (Compose)

```yaml
services:
  vault:
    image: hashicorp/vault:1.16
    command: vault server -dev -dev-root-token-id=root -dev-listen-address=0.0.0.0:8200
    ports: ["8200:8200"]
    environment:
      VAULT_DEV_ROOT_TOKEN_ID: root
    cap_add: ["IPC_LOCK"]
```

* Compose **no `version:`** field (obsolete under Compose v2).
* Dev server is **not for prod**; it’s in‑memory and insecure—OK for local only.

**Bootstrap (dev):**

```bash
export VAULT_ADDR=http://127.0.0.1:8200; export VAULT_TOKEN=root
vault secrets enable transit
vault write -f transit/keys/tenant-default type=aes256-gcm96 derived=true
```

---

## 3) Persistence Contract (DB fields we store)

### Credentials Table
* `id` (UUID) - Primary key
* `tenant_id` (VARCHAR) - Tenant identifier
* `provider` (VARCHAR) - Maps to integration_type (splunk, echo_edr, okta)
* `account` (VARCHAR) - Label/identifier for this credential set
* `ciphertext` (TEXT) - Encrypted JSON blob (opaque `vault:v<ver>:...`)
* `metadata` (JSONB) - Unencrypted metadata like label, auth type
* `key_name` (VARCHAR) - Default: `tenant-default`
* `key_version` (INTEGER) - Vault key version used
* `created_by`, `created_at`, `last_accessed_at`
* **Uniqueness:** `(tenant_id, provider, account)`

### Integration_Credentials Junction Table
* `integration_id` (VARCHAR) - References integrations
* `tenant_id` (VARCHAR) - References integrations
* `credential_id` (UUID) - References credentials
* `is_primary` (BOOLEAN) - Primary credential flag
* `purpose` (VARCHAR) - Usage purpose: read/write/admin
* **Primary Key:** `(tenant_id, integration_id, credential_id)`

---

## 4) API Surface (tiny)

* `POST /v1/{tenant}/credentials` → upsert by `(tenant, provider[, account])`, body: `{provider, account?, secret}` → `{id, version}`
* `GET /v1/{tenant}/credentials/{id}` → returns plaintext **only** to authorized internal callers
* `GET /v1/{tenant}/credentials` → metadata list (no plaintext)
* `POST /v1/{tenant}/credentials/{id}:rotate` → re-encrypt row to latest key

RBAC: internal token for machine routes; UI shows metadata by default; “reveal” gated & audited.

---

## 5) App Helpers (Python, hvac)

```python
import os, base64, json, hvac
VAULT_ADDR=os.getenv("VAULT_ADDR","http://127.0.0.1:8200"); VAULT_TOKEN=os.getenv("VAULT_TOKEN","root")
TRANSIT_KEY=os.getenv("TRANSIT_KEY","tenant-default")
client=hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)
b64e=lambda b: base64.b64encode(b).decode()

def aad(tenant, provider, account=None):
    return b64e(f"{tenant}|{provider}" + (f"|{account}" if account else "").encode())

def encrypt_secret(tenant, provider, secret: bytes, account=None):
    """Encrypt JSON credential blob"""
    r=client.secrets.transit.encrypt_data(name=TRANSIT_KEY, plaintext=b64e(secret), context=aad(tenant, provider, account))
    ct=r["data"]["ciphertext"]; ver=int(ct.split(":")[1][1:]); return ct, ver

def decrypt_secret(tenant, provider, ciphertext: str, account=None)->bytes:
    """Decrypt to get JSON credential blob"""
    r=client.secrets.transit.decrypt_data(name=TRANSIT_KEY, ciphertext=ciphertext, context=aad(tenant, provider, account))
    return base64.b64decode(r["data"]["plaintext"])  # bytes

# Usage with JSON blobs
def store_integration_credential(tenant, integration_type, credential_label, creds_dict):
    """Store integration credentials as encrypted JSON"""
    secret_json = json.dumps(creds_dict)  # e.g. {"username": "admin", "password": "secret"}
    ciphertext, version = encrypt_secret(tenant, integration_type, secret_json.encode(), credential_label)
    # Save to DB: tenant, integration_type, credential_label, ciphertext, version
    return ciphertext, version

def get_integration_credential(tenant, integration_type, credential_label, ciphertext):
    """Retrieve and parse integration credentials"""
    decrypted = decrypt_secret(tenant, integration_type, ciphertext, credential_label)
    return json.loads(decrypted)  # Returns dict with credentials
```

---

## 6) Rotation & Audit (essentials)

* **Rotate key:** `vault write -f transit/keys/tenant-default/rotate` (new writes use new version). Rewrap data to upgrade stored rows.
* **Audit:** App log on decrypt (`ts, tenant, provider, account?, cred_id, actor, why`); update `last_accessed_at` (rate-limited). Vault logs feed SIEM.

---

## 7) Road to Production (one paragraph)

Run real Vault (Raft/HSM/TLS, policies/OIDC), or swap Transit for cloud KMS using an adapter with the same DB shape (ciphertext + metadata). Keep AAD format; add background rewrap; enforce minimum decryption version post-migration. Compose v2 continues to work; avoid dev mode in prod.
