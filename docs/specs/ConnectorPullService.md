+++
version = "1.0"
status = "active"

[[changelog]]
version = "1.0"
summary = "ARQ-based pull service for alert ingestion"
+++

# Connector Pull Service

## Summary

### Scope of Work

The **Connectors Service** consists of three main modules:

1. **Control Module** – Stores settings and credentials for connecting to third-party integrations (e.g., Splunk, ServiceNow, CrowdStrike).
2. **Pull Jobs** – Periodically pull data (mainly Alerts) from integrations into our system.
3. **Push APIs** – Manage updates back to third parties (e.g., updating a Splunk Notable status).

This document focuses only on **(2) Pull Jobs**, referred to as the **Connector Pull Service**. Modules (1) and (3) will be covered in separate documents.

### About

The **Connector Pull Service** is a containerized service that uses **Valkey + ARQ** to implement a worker queue for polling Alerts from external systems. These workers are referred to as **Connector Pull Workers**.

* **v1 scope**: Only pulling alerts from **Splunk**.
* **Scheduling**: Uses `arq.cron.cron()` for periodic jobs.
* **Credentials**: Pulled from environment variables in v1; a dedicated Secrets Store will be implemented later.
* **Workflow**:

  1. Pull alerts from Splunk.
  2. Normalize alerts into the **Normalized Alert Schema (NAS)**.
  3. Store alerts via the `/alerts` API (`POST /v1/{tenant}/alerts`).
  4. Trigger alert execution via REST API.

#### Future Improvements

* Implement batch `/alerts` insert API for efficiency.
* Implement batch `/alerts/analyze` API to queue multiple alerts for analysis.

---

## Multi-Tenant Architecture

The Connector Pull Service is designed with multi-tenancy as a core principle:

### Isolation Strategy

1. **Service Level (Redis DB)**:
   - DB 0: Alert Analysis Worker (processes alerts internally)
   - DB 1: Alert Pull Connector (pulls from external sources)
   - DB 2+: Reserved for future services

2. **Tenant Level (Queue Names)**:
   - Each tenant gets their own queue: `alert_pull:tenant:{tenant_id}:queue`
   - Prevents one tenant from blocking another
   - Allows parallel processing per tenant

3. **Source Level (Checkpoints)**:
   - Tenant+source specific: `alert_pull:tenant:{tenant_id}:checkpoint:{source}:last_event_time`
   - Each tenant maintains separate checkpoints per integration

### Admin API for Manual Triggers (Temporary Solution)

**TEMPORARY IMPLEMENTATION**: Until the full Integration Service is implemented, we provide an admin API endpoint for manual pull triggers. This is essential for:

1. **Testing**: Trigger pulls without waiting 60 seconds
2. **Debugging**: Force immediate pulls for troubleshooting
3. **Demo/POC**: Show real-time ingestion capabilities

```python
# Temporary admin endpoint
POST /admin/v1/trigger-alert-pull/{tenant_id}
{
    "source": "splunk"  # or "crowdstrike", etc.
}

# Returns
{
    "status": "queued",
    "job_id": "abc-123",
    "queue": "alert_pull:tenant:default:queue",
    "message": "Alert pull job queued successfully"
}
```

**Future**: Will be replaced by the proper Integration Service API:
- `GET /v1/{tenant}/integrations` - List configured integrations
- `POST /v1/{tenant}/integrations/{id}/pull` - Trigger manual pull
- `GET /v1/{tenant}/integrations/{id}/status` - Check pull status
- `PUT /v1/{tenant}/integrations/{id}/schedule` - Configure pull schedule

The admin API uses the exact same configuration (`AlertPullConfig`) as the worker to ensure consistency - no hardcoded values or magic numbers.

## Deployment Requirements

To run the **Connector Pull Service**, the following components are required:

1. **New Docker Container**

   * A dedicated container image for the Connector Pull Workers.
   * Contains ARQ worker code, alert normalization logic, and Splunk integration.
   * Named `connector-alert-pull-worker` to distinguish from `alert-worker`

2. **Valkey/Redis Configuration**

   * Uses same Valkey server but different database (DB 1)
   * Triple isolation: different DB, queue names, and key namespaces
   * Tenant-specific queues within DB 1

3. **Configuration**

   * Environment variables for Splunk credentials (v1).
   * **Polling controls (new):**

     * `POLL_INTERVAL_SECONDS` (default: `60`) – how often the worker runs.
     * `PULL_LOOKBACK_SECONDS` (default: `120`) – time window pulled on each run to create an intentional **overlap** and reduce miss risk; deduplication on `/alerts` handles duplicates.
   * Future versions will integrate with a Secrets Store.

---

## Pull Scheduling

**Policy:** Polling frequency is configurable via env vars. Default behavior is **every 60 seconds**, and each run pulls the **last 120 seconds** of Splunk data (intentional overlap). Overlap + backend deduplication (409 on duplicates) improves reliability.

### ARQ Cron Example (Every Minute) with Tenant Support

```python
import os
from arq import cron
from arq.connections import RedisSettings

POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

# Tenant-aware pull function
async def pull_alerts_for_tenant(ctx, tenant_id: str, source: str = "splunk"):
    """Pull alerts for specific tenant from specific source."""
    # Implementation uses tenant_id for:
    # - API calls to correct tenant endpoints
    # - Checkpoint keys: alert_pull:tenant:{tenant_id}:checkpoint:{source}:last_event_time
    # - Logging and monitoring
    await pull_splunk_and_persist(ctx, tenant_id, source)

class WorkerSettings:
    # Redis configuration with DB isolation
    redis_settings = RedisSettings(
        host=os.getenv('CONNECTOR_ALERT_PULL_REDIS_HOST', 'analysi-valkey'),
        port=int(os.getenv('CONNECTOR_ALERT_PULL_REDIS_PORT', 6379)),
        database=int(os.getenv('CONNECTOR_ALERT_PULL_REDIS_DB', 1))  # DB 1 for alert pulls
    )

    # Tenant-specific queue name
    default_tenant = os.getenv('CONNECTOR_TENANT_ID', 'default')
    queue_name = f'alert_pull:tenant:{default_tenant}:queue'

    # V1: Single tenant cron job
    cron_jobs = [
        cron(pull_alerts_for_tenant, minute=None, tenant_id=default_tenant)
    ]

    # Future V2: Multi-tenant support
    # cron_jobs = [
    #     cron(pull_alerts_for_tenant, minute=None, tenant_id="acme", source="splunk"),
    #     cron(pull_alerts_for_tenant, minute=None, tenant_id="globex", source="crowdstrike"),
    # ]
```

> **Note:** ARQ `cron(..., minute=None)` is equivalent to `*` in crontab, so this runs once per minute. You can also implement a repeating task that sleeps `POLL_INTERVAL_SECONDS` between iterations if you need sub-minute resolution.

---

## Splunk Integration

**Goal:** Pull *alert-like* events (e.g., Splunk ES Notables or equivalent searches) from Splunk, run them through our **Alert Normalizer** to produce **NAS** objects, and persist them to our backend via `POST /v1/{tenant}/alerts`. This keeps the integration aligned with the rest of this spec and avoids leaking vendor schemas downstream.

### How it fits

1. **Query Splunk** for alert events (not generic logs).
2. **Normalize** each event → **NAS** using the appropriate adapter (e.g., `splunk_es_notable`).
3. **Persist** NAS to our backend (`/alerts`); prefer batch if available.
4. **(Optional)** Trigger analysis for newly created alerts.

### Environment Configuration

```bash
SPLUNK_HOST=https://your-splunk-instance.com
SPLUNK_PORT=8089
SPLUNK_USERNAME=your_username
SPLUNK_PASSWORD=your_password
# Choose a search that yields alerts/notables; example placeholder below
SPLUNK_SEARCH_QUERY="search index=notable | head 50"

# Backend target
BACKEND_BASE_URL=https://api.example.com
TENANT_ID=default
BACKEND_API_TOKEN=your_token  # if using bearer auth
```

### Connection Helper (SDK)

```python
import os, socket, logging
from urllib.parse import urlparse
import splunklib.client as splunk_client

logger = logging.getLogger(__name__)

def get_splunk_service():
    host_url = os.environ["SPLUNK_HOST"]
    port = os.environ["SPLUNK_PORT"]
    username = os.environ["SPLUNK_USERNAME"]
    password = os.environ["SPLUNK_PASSWORD"]

    parsed = urlparse(host_url)
    hostname = parsed.netloc or parsed.path
    ip = socket.gethostbyname(hostname)

    service = splunk_client.connect(
        host=ip,
        port=port,
        username=username,
        password=password,
        verify=False,  # For production, enable TLS verification
    )
    return service
```

### Querying *Alert* Events (Incremental + Overlap)

Use bounded windows and a Valkey checkpoint. Each run pulls **last `PULL_LOOKBACK_SECONDS` (default 120s)** to create an overlap window. Backend deduplication prevents duplicates.

```python
import os, time
import splunklib.results as splunk_results
from typing import List, Dict, Any, Optional

# Tenant-specific checkpoint key
CHECKPOINT_KEY = f"alert_pull:tenant:{tenant_id}:checkpoint:splunk:last_event_time"
PULL_LOOKBACK_SECONDS = int(os.getenv("PULL_LOOKBACK_SECONDS", "120"))

async def get_last_checkpoint(valkey) -> Optional[str]:
    return await valkey.get(CHECKPOINT_KEY)

async def set_last_checkpoint(valkey, value: str) -> None:
    await valkey.set(CHECKPOINT_KEY, value)


def query_alert_events(service, earliest: str, latest: str, query: str) -> List[Dict[str, Any]]:
    kwargs = {"earliest_time": earliest, "latest_time": latest, "count": 0}
    job = service.jobs.create(query, **kwargs)

    while not job.is_done():
        time.sleep(1)

    results = []
    for r in splunk_results.JSONResultsReader(job.results(output_mode="json")):
        if isinstance(r, dict):
            results.append(r)
    return results
```

```python
from datetime import datetime, timezone, timedelta

async def compute_window(valkey):
    last = await get_last_checkpoint(valkey)  # ISO string of last seen _time
    now = datetime.now(timezone.utc)
    if last:
        # Apply overlap: go back by PULL_LOOKBACK_SECONDS from the last checkpoint
        # Splunk supports ISO8601 for absolute times
        earliest_dt = datetime.fromisoformat(last.replace("Z", "+00:00")) - timedelta(seconds=PULL_LOOKBACK_SECONDS)
        earliest = earliest_dt.isoformat().replace("+00:00", "Z")
    else:
        # First run: relative lookback
        earliest = f"-{PULL_LOOKBACK_SECONDS}s"
    latest = "now"
    return earliest, latest
```

### Normalization to NAS

We treat each Splunk result as the *raw vendor event*. The normalizer produces an **AlertCreate/NAS** dict and sets `raw_alert` to the original JSON string.

```python
import json
from typing import Dict, Any

# Stub: wire to your actual adapter (e.g., alert_normalizer.splunk_es_notable)
def normalize_splunk_notable(vendor_event: Dict[str, Any]) -> Dict[str, Any]:
    # Example: minimal mapping — adapt to your NAS fields
    nas = {
        "title": vendor_event.get("rule_name") or vendor_event.get("_raw", "Splunk Alert"),
        "triggering_event_time": vendor_event.get("_time"),
        "severity": (vendor_event.get("severity") or "medium").lower(),
        "source_vendor": vendor_event.get("vendor", "Splunk"),
        "source_product": vendor_event.get("product", "Enterprise Security"),
        "rule_name": vendor_event.get("rule_name"),
        "primary_risk_entity_value": vendor_event.get("dest") or vendor_event.get("user"),
        "primary_ioc_value": vendor_event.get("url") or vendor_event.get("ip") or vendor_event.get("process"),
        "raw_alert": json.dumps(vendor_event),
    }
    return nas
```

### Persisting to `/alerts`

Prefer batch insert when available; otherwise post one-by-one with idempotency on the backend (409 on duplicate).

```python
import httpx

async def post_alerts(nas_alerts: list[dict]) -> None:
    base = os.environ["BACKEND_BASE_URL"].rstrip("/")
    tenant = os.environ["TENANT_ID"]
    token = os.environ.get("BACKEND_API_TOKEN")

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # If a batch endpoint exists, prefer that; else loop
    url = f"{base}/v1/{tenant}/alerts"
    async with httpx.AsyncClient(timeout=30) as client:
        for alert in nas_alerts:
            r = await client.post(url, json=alert, headers=headers)
            if r.status_code not in (200, 201, 409):
                raise RuntimeError(f"Alert POST failed: {r.status_code} {r.text}")
```

### End-to-End Worker (ARQ Task)

```python
from datetime import datetime, timezone, timedelta

async def pull_splunk_and_persist(ctx, tenant_id: str):
    """Pull alerts for a specific tenant.

    Args:
        ctx: ARQ context with Valkey connection
        tenant_id: Tenant identifier for isolation
    """
    service = get_splunk_service()  # Future: per-tenant credentials
    valkey = ctx["redis"]  # ARQ uses "redis" key

    # Polling window configuration
    polling_interval = int(os.environ.get("SPLUNK_POLL_INTERVAL", "60"))  # seconds
    lookback_window = int(os.environ.get("SPLUNK_LOOKBACK_WINDOW", "120"))  # seconds

    # Default earliest/last checkpoint
    last = await get_last_checkpoint(valkey)
    now = datetime.now(timezone.utc)

    if last:
        earliest = last
    else:
        # On first run, go back lookback_window seconds
        earliest = f"-{lookback_window}s"
    latest = "now"

    query = os.environ["SPLUNK_SEARCH_QUERY"]
    raw_events = query_alert_events(service, earliest, latest, query)

    if raw_events:
        newest = max(e.get("_time", "") for e in raw_events if isinstance(e, dict))
        if newest:
            await set_last_checkpoint(valkey, newest)

    nas_alerts = [normalize_splunk_notable(e) for e in raw_events]
    await post_alerts(nas_alerts)
```

**Notes:**

* Polling frequency is controlled via `SPLUNK_POLL_INTERVAL` (default 60 seconds).
* Each poll queries the last `SPLUNK_LOOKBACK_WINDOW` seconds (default 120) to provide overlap and reduce the chance of missed alerts.
* Deduplication logic in the backend ensures duplicates are not persisted.

---

## Alert Normalizer

The **Alert Normalizer** is a new component with its own folder and entry point. It will also support running as a CLI tool in the future.

* Connector Pull Workers use vendor-specific normalizers (e.g., Splunk ES Notable) to produce alerts in the **Normalized Alert Schema (NAS)**.
* NAS is identical to the schema used in the `/alerts` endpoint.

### Goal

Normalize heterogeneous security alerts (CEF, syslog/CLI outputs, vendor JSON) into the canonical **Normalized Alert Schema (NAS)**.

**Processing Flow:**

```
Raw Input (CEF | CLI | JSON)
      │
      ▼ jc parser
Structured dict/list
      │
      ▼ glom mapping
Canonical dict
      │
      ▼ Pydantic
Normalized Alert Schema (validated)
```

### Parsing (jc)

* **jc** parses raw text into Python dicts.
* Example: `jc.parse('cef', cef_string)` → `dict`

### Mapping (glom)

* **glom** specs define field mappings from vendor schema → NAS.

#### Example (Abstract)

```python
from glom import Coalesce

CEF_SPEC = {
    "source_vendor": "DeviceVendor",
    "source_product": "DeviceProduct",
    "rule_name": "DeviceEventClassID",
    "title": Coalesce("name", "msg"),
    "severity": "DeviceSeverity",
    "triggering_event_time": Coalesce("end", "rt"),
    "primary_risk_entity_value": "dst",
    "primary_ioc_value": "request"
}
```

### Adapter Pattern (Example)

```python
def normalize_cef(cef_dict):
    mapped = glom(cef_dict, CEF_SPEC)
    return Alert(**mapped)
```

### Example Conversion

**Input (CEF):**

```
CEF:0|Acme|WebGW|2.0|1001|URL Contains Clear Text Password|High|src=10.0.0.5 request=http://ex.com/login end=1735678901234
```

**Output (Normalized Alert excerpt):**

```json
{
  "source_vendor": "Acme",
  "source_product": "WebGW",
  "rule_name": "1001",
  "title": "URL Contains Clear Text Password",
  "severity": "high",
  "triggering_event_time": "2026-04-26T12:48:21Z",
  "primary_risk_entity_value": "10.0.0.5",
  "primary_ioc_value": "http://ex.com/login",
  "raw_alert": "CEF:0|Acme|WebGW|..."
}
```

---

## Normalized Alert Schema (NAS)

The NAS aligns with the `AlertCreate` schema from the `/alerts` endpoint. Key fields include:

* **Required**:

  * `title`: Reason for the alert (≤ 500 chars)
  * `triggering_event_time`: When the event occurred
  * `severity`: critical | high | medium | low | info
  * `raw_alert`: Original alert preserved as a string

* **Optional but Recommended**:

  * `source_vendor`, `source_product`, `source_category`
  * `rule_name`, `alert_type`, `device_action`
  * `primary_risk_entity_value`, `primary_risk_entity_type`
  * `primary_ioc_value`, `primary_ioc_type`
  * `network_info` (JSONB, flexible)
  * `detected_at`

* **Auto-Generated**:

  * `human_readable_id` (`AID-{sequence}` per tenant)
  * `alert_id` (UUID)

### Enum References

* **AlertSeverity**: critical, high, medium, low, info
* **SourceCategory**: Firewall, EDR, Identity, Cloud, DLP
* **EntityType**: user, device, network\_artifact, account
* **IOCType**: ip, domain, filename, filehash, url, process
* **DeviceAction**: allowed, blocked, detected, quarantined, terminated, unknown

### Best Practices

* Always include a meaningful `title` and accurate `triggering_event_time`.
* Preserve the raw vendor alert in `raw_alert` for audit.
* Use enums correctly; use `null` if not applicable.
* Include `primary_risk_entity_*` and `primary_ioc_*` for correlation.
* `network_info` can vary per alert type but should contain useful context.

---
