+++
version = "2.0"
status = "active"

[[changelog]]
version = "2.0"
summary = "v2 — OCSF-aligned alert schema"
+++

# Alerts

## Alerts Schema

### Alert use-cases
* The Alert Schema provides Standardized representations of alerts
  * Our product ingest alerts from different products, like SIEM, XDR, EDR and more. We need to have standardized schema (Pydantic) for our parsers to generate.
* Alert is our main unit of work
  * The entire goal of this product is to analyze security alerts
* Our main UI page is the Alerts listing page
  * We want to have a comprehensive REST API backed up by Postgres to effectively retrieve and present information about alerts to our users

### Alert Data Model

Alerts have two distinct groups of fields: **immutable source data** (from external systems) and **mutable analysis data** (added/updated during investigation).

#### Database Schema

```sql
-- Main alerts table (partitioned by triggering_event_time for performance)
CREATE TABLE alerts (
    -- Core identifiers
    alert_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) NOT NULL,
    human_readable_id TEXT NOT NULL,  -- AID-1, AID-2... (unique per tenant)

    -- Source alert information (immutable)
    title TEXT NOT NULL,                    -- Alert triggering reason
    triggering_event_time TIMESTAMPTZ NOT NULL,  -- Primary sort/partition field
    source_vendor TEXT,                     -- e.g., "Cisco", "Microsoft"
    source_product TEXT,                    -- e.g., "ASA", "Defender"
    source_category TEXT CHECK (source_category IN ('Firewall', 'EDR', 'Identity', 'Cloud', 'DLP')),
    rule_name TEXT,                         -- Rule that triggered alert
    alert_type TEXT,                        -- malware, web_attack, insider, lateral_movement
    severity TEXT CHECK (severity IN ('critical', 'high', 'medium', 'low', 'info')) NOT NULL,
    device_action TEXT CHECK (device_action IN ('allowed', 'blocked', 'detected', 'quarantined', 'terminated', 'unknown')),

    -- Primary entities (separate columns for analytics performance)
    primary_risk_entity_value TEXT,        -- The actual value for grouping/analytics
    primary_risk_entity_type TEXT CHECK (primary_risk_entity_type IN ('user', 'device', 'network_artifact', 'account')),
    primary_ioc_value TEXT,                -- The actual IOC for grouping/analytics
    primary_ioc_type TEXT CHECK (primary_ioc_type IN ('ip', 'domain', 'filename', 'filehash', 'url', 'process')),

    -- Network information (JSONB for flexibility, less frequently queried)
    network_info JSONB,                     -- src_ip, dest_ip, url, http_method, user_agent, etc.

    -- Timestamps
    detected_at TIMESTAMPTZ,                -- When source system detected
    ingested_at TIMESTAMPTZ DEFAULT now() NOT NULL,

    -- Raw data preservation
    raw_alert TEXT NOT NULL,                -- Original alert as received
    content_hash TEXT NOT NULL,             -- SHA-256 of normalized key fields for dedup

    -- Analysis reference
    current_analysis_id UUID,               -- Points to latest alert_analysis record
    analysis_status TEXT CHECK (analysis_status IN ('not_analyzed', 'analyzing', 'analyzed')) DEFAULT 'not_analyzed'

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,

    -- Constraints
    UNIQUE(tenant_id, human_readable_id),
    UNIQUE(tenant_id, content_hash)         -- Prevent duplicate alerts
) PARTITION BY RANGE (triggering_event_time);

-- High-performance indexes for analytics and common queries
CREATE INDEX idx_alerts_tenant_status ON alerts(tenant_id, status);
CREATE INDEX idx_alerts_tenant_severity ON alerts(tenant_id, severity);
CREATE INDEX idx_alerts_tenant_time_desc ON alerts(tenant_id, triggering_event_time DESC);
CREATE INDEX idx_alerts_source_product ON alerts(tenant_id, source_product, source_vendor);
CREATE INDEX idx_alerts_analysis_status ON alerts(tenant_id, analysis_status);
CREATE INDEX idx_alerts_current_analysis ON alerts(current_analysis_id) WHERE current_analysis_id IS NOT NULL;

-- Analytics-optimized indexes for entity and IOC grouping
CREATE INDEX idx_alerts_risk_entity ON alerts(tenant_id, primary_risk_entity_type, primary_risk_entity_value);
CREATE INDEX idx_alerts_ioc ON alerts(tenant_id, primary_ioc_type, primary_ioc_value);
CREATE INDEX idx_alerts_risk_entity_severity ON alerts(tenant_id, primary_risk_entity_value, severity);
CREATE INDEX idx_alerts_ioc_severity ON alerts(tenant_id, primary_ioc_value, severity);

-- Alert analysis results table (separate from alerts for clean separation)
CREATE TABLE alert_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),  -- This is the analysis_id
    alert_id UUID NOT NULL REFERENCES alerts(alert_id),
    tenant_id VARCHAR(255) NOT NULL,

    -- Analysis lifecycle
    status TEXT CHECK (status IN ('pending', 'running', 'completed', 'failed')) DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    -- Step tracking (JSONB for flexibility and extensibility)
    current_step TEXT,                     -- Current step name
    steps_progress JSONB DEFAULT '{}'::jsonb,  -- Flexible step tracking
    /* Example structure:
    {
      "pre_triage": {
        "completed": false,
        "started_at": "2026-04-26T10:00:00Z",
        "completed_at": null,
        "retries": 0,
        "error": null
      },
      "context_retrieval": {
        "completed": false,
        "started_at": null,
        "completed_at": null,
        "retries": 0,
        "error": null
      },
      "workflow_builder": {
        "completed": false,
        "started_at": null,
        "completed_at": null,
        "retries": 0,
        "selected_workflow": null
      },
      "workflow_execution": {
        "completed": false,
        "started_at": null,
        "completed_at": null,
        "retries": 0,
        "workflow_run_id": null
      },
      "final_disposition_update": {
        "completed": false,
        "started_at": null,
        "completed_at": null,
        "retries": 0
      }
    }
    */

    -- Analysis results (populated from workflow artifacts)
    disposition_id UUID REFERENCES dispositions(id),
    confidence INTEGER CHECK (confidence BETWEEN 0 AND 100),
    short_summary TEXT,                    -- From "Short Summary" artifact
    long_summary TEXT,                     -- From "Summary" artifact
    -- "Complete Analysis" artifact stored separately, retrieved via artifacts API

    -- Workflow tracking
    workflow_id UUID,                       -- Which workflow template was used
    workflow_run_id UUID,                   -- Track the actual execution

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL

    -- No unique constraint - allows multiple analyses per alert
);

-- Indexes for analysis queries
CREATE INDEX idx_analysis_tenant_status ON alert_analysis(tenant_id, status);
CREATE INDEX idx_analysis_alert ON alert_analysis(alert_id);
CREATE INDEX idx_analysis_alert_created ON alert_analysis(alert_id, created_at DESC); -- For finding most recent
CREATE INDEX idx_analysis_workflow_run ON alert_analysis(workflow_run_id);
CREATE INDEX idx_analysis_steps_progress ON alert_analysis USING gin(steps_progress); -- For JSONB queries
```

#### Field Definitions

##### **Core Identifiers**
- `alert_id`: UUID - Globally unique identifier
- `tenant_id`: VARCHAR(255) - Multi-tenancy isolation
- `human_readable_id`: TEXT - User-friendly ID (AID-1, AID-2...), unique per tenant

##### **Source Alert Information** (Immutable)
- `title`: TEXT - One-line description answering "what triggered this alert?"
- `triggering_event_time`: TIMESTAMPTZ - When the triggering event occurred (partition key)
- `source_vendor`: TEXT - Alert source vendor (Cisco, Microsoft, CrowdStrike)
- `source_product`: TEXT - Specific product (ASA, Defender, Falcon)
- `source_category`: ENUM - Alert category (Firewall, EDR, Identity, Cloud, DLP)
- `rule_name`: TEXT - Detection rule that fired
- `alert_type`: TEXT - Threat type (malware, web_attack, insider, lateral_movement)
- `severity`: ENUM - critical/high/medium/low/info
- `device_action`: ENUM - Response taken (allowed/blocked/detected/quarantined/terminated/unknown)

##### **Primary Entity Data** (Optimized for Analytics)
- `primary_risk_entity_value`: TEXT - Main at-risk entity value (user@corp.example, 192.168.1.50)
- `primary_risk_entity_type`: ENUM - Entity type (user/device/network_artifact/account)
- `primary_ioc_value`: TEXT - Primary indicator value (malware.exe, 192.168.1.100, malicious.com)
- `primary_ioc_type`: ENUM - IOC type (ip/domain/filename/filehash/url/process)

##### **Network Information** (JSONB Structure)
- `network_info`: JSONB - Flexible network details
  ```json
  {
    "src_ip": "10.0.0.5",
    "src_hostname": "workstation01",
    "src_port": 12345,
    "dest_ip": "8.8.8.8",
    "dest_hostname": "dns.google",
    "dest_port": 53,
    "url": "http://malicious.com/path",
    "http_method": "POST",
    "user_agent": "Mozilla/5.0..."
  }
  ```

##### **Analysis Reference** (In Alerts Table)
- `current_analysis_id`: UUID - Points to the most recent analysis in alert_analysis table
- `analysis_status`: ENUM - Quick status check (not_analyzed/analyzing/analyzed)

##### **Analysis Information** (In Alert_Analysis Table)
- `id`: UUID - The analysis_id, groups all artifacts for this analysis run
- `alert_id`: UUID - References the alert being analyzed
- `status`: ENUM - Analysis lifecycle (pending/running/completed/failed)
- `started_at`: TIMESTAMPTZ - When analysis began
- `completed_at`: TIMESTAMPTZ - When analysis completed
- `disposition_id`: UUID - References dispositions table with color coding
- `confidence`: INTEGER(0-100) - Confidence in disposition assessment
- `short_summary`: TEXT - Brief summary from "Short Summary" artifact
- `long_summary`: TEXT - Detailed summary from "Summary" artifact
- `workflow_id`: UUID - Which workflow template was used
- `workflow_run_id`: UUID - Tracks the actual workflow execution

##### **Deduplication Strategy**
- `content_hash`: TEXT - SHA-256 of normalized key fields (title + triggering_event_time + primary_risk_entity_value + source_product + primary_ioc_value)
- Prevents duplicate alerts with UNIQUE constraint on (tenant_id, content_hash)

#### Performance Benefits for Analytics

This design enables high-performance queries for common analytics:

```sql
-- Top 10 users with most alerts
SELECT primary_risk_entity_value, COUNT(*)
FROM alerts
WHERE tenant_id = ? AND primary_risk_entity_type = 'user'
GROUP BY primary_risk_entity_value
ORDER BY COUNT(*) DESC LIMIT 10;

-- IOC frequency analysis
SELECT primary_ioc_value, primary_ioc_type, COUNT(*) as alert_count
FROM alerts
WHERE tenant_id = ?
GROUP BY primary_ioc_value, primary_ioc_type
HAVING COUNT(*) > 5;

-- Critical alerts by entity type
SELECT primary_risk_entity_type, COUNT(*)
FROM alerts
WHERE tenant_id = ? AND severity = 'critical'
GROUP BY primary_risk_entity_type;
```

#### Pydantic Schemas

```python
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from enum import Enum
from pydantic import BaseModel, Field, field_validator

# Enums for validation
class AlertSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class AlertStatus(str, Enum):
    NOT_ANALYZED = "not_analyzed"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"

class SourceCategory(str, Enum):
    FIREWALL = "Firewall"
    EDR = "EDR"
    IDENTITY = "Identity"
    CLOUD = "Cloud"
    DLP = "DLP"

class EntityType(str, Enum):
    USER = "user"
    DEVICE = "device"
    NETWORK_ARTIFACT = "network_artifact"
    ACCOUNT = "account"

class IOCType(str, Enum):
    IP = "ip"
    DOMAIN = "domain"
    FILENAME = "filename"
    FILEHASH = "filehash"
    URL = "url"
    PROCESS = "process"

class DeviceAction(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    DETECTED = "detected"
    QUARANTINED = "quarantined"
    TERMINATED = "terminated"
    UNKNOWN = "unknown"

# Base Alert Schema
class AlertBase(BaseModel):
    """Base schema for Alert with common fields."""

    # Required source fields
    title: str = Field(..., min_length=1, max_length=500, description="Alert triggering reason")
    triggering_event_time: datetime = Field(..., description="When the triggering event occurred")
    severity: AlertSeverity = Field(..., description="Alert severity level")

    # Optional source fields
    source_vendor: Optional[str] = Field(None, max_length=100, description="Alert source vendor")
    source_product: Optional[str] = Field(None, max_length=100, description="Specific product")
    source_category: Optional[SourceCategory] = Field(None, description="Alert category")
    rule_name: Optional[str] = Field(None, max_length=255, description="Detection rule name")
    alert_type: Optional[str] = Field(None, max_length=100, description="Threat type")
    device_action: Optional[DeviceAction] = Field(None, description="Response taken")

    # Entity and IOC fields
    primary_risk_entity_value: Optional[str] = Field(None, max_length=500, description="At-risk entity")
    primary_risk_entity_type: Optional[EntityType] = Field(None, description="Entity type")
    primary_ioc_value: Optional[str] = Field(None, max_length=500, description="Primary IOC")
    primary_ioc_type: Optional[IOCType] = Field(None, description="IOC type")

    # Network information
    network_info: Optional[Dict[str, Any]] = Field(None, description="Network details")

    # Timestamps
    detected_at: Optional[datetime] = Field(None, description="When source system detected")

    # Raw data
    raw_alert: str = Field(..., description="Original alert as received")

    @field_validator('network_info')
    @classmethod
    def validate_network_info(cls, v):
        """Validate network_info structure if provided."""
        if v is not None:
            # Validate expected fields if present
            allowed_keys = {
                'src_ip', 'src_hostname', 'src_port',
                'dest_ip', 'dest_hostname', 'dest_port',
                'url', 'http_method', 'user_agent'
            }
            extra_keys = set(v.keys()) - allowed_keys
            if extra_keys:
                # Log warning but don't fail - flexibility for different sources
                pass
        return v

# Create Alert Request
class AlertCreate(AlertBase):
    """Schema for creating new alerts."""

    # Optional fields that can be provided
    human_readable_id: Optional[str] = Field(None, description="Custom human-readable ID")

    @field_validator('human_readable_id')
    @classmethod
    def validate_human_readable_id(cls, v):
        """Validate human_readable_id format if provided."""
        if v and not v.startswith('AID-'):
            raise ValueError("human_readable_id must start with 'AID-'")
        return v

# Update Alert Request (only analysis fields can be updated)
class AlertUpdate(BaseModel):
    """Schema for updating alert analysis fields only."""

    # Only analysis-related fields can be updated
    analysis_status: Optional[AlertStatus] = None
    current_analysis_id: Optional[UUID] = None

    class Config:
        extra = "forbid"  # Prevent updating immutable fields

# Alert Response
class AlertResponse(AlertBase):
    """Schema for alert API responses."""

    # Identifiers
    alert_id: UUID = Field(..., description="Globally unique identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    human_readable_id: str = Field(..., description="Human-friendly ID")

    # Analysis reference
    current_analysis_id: Optional[UUID] = Field(None, description="Current analysis")
    analysis_status: AlertStatus = Field(..., description="Analysis status")

    # System fields
    content_hash: str = Field(..., description="Deduplication hash")
    ingested_at: datetime = Field(..., description="When alert was ingested")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    # Optional expanded fields
    current_analysis: Optional['AlertAnalysisResponse'] = None
    disposition: Optional['DispositionResponse'] = None

    class Config:
        from_attributes = True

# Alert List Response
class AlertList(BaseModel):
    """Schema for paginated alert list responses."""

    alerts: List[AlertResponse] = Field(..., description="List of alerts")
    total: int = Field(..., description="Total number of alerts")
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Pagination offset")

# Analysis Schemas
class AnalysisStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class StepProgress(BaseModel):
    """Schema for individual step progress."""
    completed: bool = False
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retries: int = 0
    error: Optional[str] = None

class AlertAnalysisResponse(BaseModel):
    """Schema for alert analysis responses."""

    id: UUID = Field(..., description="Analysis ID")
    alert_id: UUID = Field(..., description="Associated alert")
    tenant_id: str = Field(..., description="Tenant identifier")

    # Lifecycle
    status: AnalysisStatus = Field(..., description="Analysis status")
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Step tracking
    current_step: Optional[str] = None
    steps_progress: Dict[str, Any] = Field(default_factory=dict)

    # Results
    disposition_id: Optional[UUID] = None
    confidence: Optional[int] = Field(None, ge=0, le=100)
    short_summary: Optional[str] = None
    long_summary: Optional[str] = None

    # Workflow tracking
    workflow_id: Optional[UUID] = None
    workflow_run_id: Optional[UUID] = None

    # Metadata
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class AnalysisProgress(BaseModel):
    """Schema for analysis progress endpoint."""

    analysis_id: UUID
    current_step: str
    completed_steps: int
    total_steps: int = 5
    status: AnalysisStatus
    steps_detail: Dict[str, StepProgress]

class AnalysisHistory(BaseModel):
    """Schema for analysis history endpoint."""

    analyses: List[AlertAnalysisResponse]
    total: int

# Disposition Response (referenced in AlertResponse)
class DispositionResponse(BaseModel):
    """Schema for disposition in alert responses."""

    id: UUID
    category: str
    subcategory: str
    display_name: str
    color_hex: str
    color_name: str
    priority_score: int
    requires_escalation: bool
```

#### Alerts REST API

##### Core Alert Operations

**List Alerts**
```
GET /v1/{tenant}/alerts
```
Query Parameters:
- `status`: Filter by alert status (new, analyzing, resolved, suppressed)
- `severity`: Filter by severity (critical, high, medium, low, info) - supports comma-separated list
- `source_vendor`: Filter by source vendor (exact match)
- `source_product`: Filter by source product (exact match)
- `source_category`: Filter by category (Firewall, EDR, Identity, Cloud, DLP)
- `alert_type`: Filter by alert type (malware, web_attack, insider, lateral_movement)
- `primary_risk_entity_type`: Filter by entity type (user, device, network_artifact, account)
- `primary_risk_entity_value`: Filter by entity value (exact match or partial with wildcard)
- `primary_ioc_type`: Filter by IOC type (ip, domain, filename, filehash, url, process)
- `primary_ioc_value`: Filter by IOC value (exact match or partial with wildcard)
- `disposition_id`: Filter by disposition UUID
- `analysis_id`: Filter by analysis UUID (groups related alerts)
- `time_from`: Start time filter (ISO 8601) - filters triggering_event_time
- `time_to`: End time filter (ISO 8601) - filters triggering_event_time
- `ingested_from`: Start ingestion filter (ISO 8601)
- `ingested_to`: End ingestion filter (ISO 8601)
- `rule_name`: Filter by detection rule name (partial match)
- `human_readable_id`: Filter by human ID (AID-1, AID-2...)
- `limit`: Page size (default: 20, max: 100)
- `offset`: Pagination offset
- `sort`: Sort field (triggering_event_time, severity, status, created_at, human_readable_id)
- `order`: Sort order (asc, desc) - default desc for time fields
- `include_disposition`: Include expanded disposition details (true/false)
- `include_analysis`: Include current analysis details (true/false)

Response (200):
```json
{
  "alerts": [
    {
      "alert_id": "uuid",
      "tenant_id": "tenant",
      "human_readable_id": "AID-1",
      "title": "Suspicious Login Activity",
      "triggering_event_time": "2026-04-26T10:00:00Z",
      "severity": "high",
      "analysis_status": "analyzed",
      "source_vendor": "Microsoft",
      "source_product": "Defender",
      // ... other alert fields
      "current_analysis": {  // Only if include_analysis=true
        "id": "uuid",
        "status": "completed",
        "started_at": "2026-04-26T10:05:00Z",
        "completed_at": "2026-04-26T10:10:00Z",
        "short_summary": "Suspicious login detected from unusual location",
        "long_summary": "Analysis indicates login attempt from...",
        "confidence": 85
      },
      "disposition": {  // Only if include_disposition=true and analysis exists
        "id": "uuid",
        "category": "Undetermined",
        "subcategory": "Suspicious, Not Confirmed",
        "display_name": "Suspicious Activity",
        "color_hex": "#9333EA",
        "color_name": "purple",
        "priority_score": 4,
        "requires_escalation": true
      }
    }
  ],
  "total": 150,
  "limit": 20,
  "offset": 0
}
```

**Get Specific Alert**
```
GET /v1/{tenant}/alerts/{alert_id}
```
Query Parameters:
- `include_disposition`: Include expanded disposition details (true/false) - default true
- `include_analysis`: Include current analysis details (true/false) - default true

Response (200): Alert object with all fields
Error Response (404): `{"detail": "Alert not found"}`

**Create Alert**
```
POST /v1/{tenant}/alerts
```
Note: Creates new alert with auto-generated human_readable_id and content_hash for deduplication

Response (201): Created alert object
Error Responses:
- 400: `{"detail": "Invalid severity value"}`
- 409: `{"detail": "Duplicate alert detected"}`

**Update Alert Analysis Fields**
```
PATCH /v1/{tenant}/alerts/{alert_id}
```
Note: Only allows updating mutable analysis fields (status, disposition_id, confidence, descriptions, analysis_id)

Response (200): Updated alert object
Error Responses:
- 404: `{"detail": "Alert not found"}`
- 400: `{"detail": "Cannot update immutable field"}`

**Delete Alert** (Soft Delete)
```
DELETE /v1/{tenant}/alerts/{alert_id}
```
Note: Marks alert as deleted, preserves for audit trail

Response (204): No content
Error Response (404): `{"detail": "Alert not found"}`

##### Alert Analysis Operations

**Start Alert Analysis**
```
POST /v1/{tenant}/alerts/{alert_id}/analyze
```
Note: Creates new alert_analysis record and triggers async workflow. Can be called multiple times for re-analysis.

Response (202):
```json
{
  "analysis_id": "uuid",
  "alert_id": "uuid",
  "status": "pending",
  "created_at": "2026-04-26T10:00:00Z"
}
```

**Get Analysis Progress**
```
GET /v1/{tenant}/alerts/{alert_id}/analysis/progress
```
Note: Returns current analysis progress for UI display

Response (200):
```json
{
  "analysis_id": "uuid",
  "current_step": "workflow_execution",
  "completed_steps": 3,
  "total_steps": 5,
  "status": "running",
  "steps_detail": {
    "pre_triage": {"completed": true, "completed_at": "2026-04-26T10:01:00Z"},
    "context_retrieval": {"completed": true, "completed_at": "2026-04-26T10:02:00Z"},
    "workflow_builder": {"completed": true, "completed_at": "2026-04-26T10:03:00Z"},
    "workflow_execution": {"completed": false, "started_at": "2026-04-26T10:04:00Z"},
    "final_disposition_update": {"completed": false}
  }
}
```

**Get Analysis History**
```
GET /v1/{tenant}/alerts/{alert_id}/analyses
```
Note: Returns all analysis runs for an alert (supports re-analysis)

Response (200):
```json
{
  "analyses": [
    {
      "id": "uuid",
      "status": "completed",
      "created_at": "2026-04-26T09:00:00Z",
      "completed_at": "2026-04-26T09:10:00Z",
      "disposition": "Suspicious Activity",
      "confidence": 75
    },
    {
      "id": "uuid",
      "status": "running",
      "created_at": "2026-04-26T10:00:00Z",
      "current_step": "workflow_execution"
    }
  ],
  "total": 2
}
```

##### Alert Analytics & Reporting (Future Work)

The following analytics endpoints are planned but not yet implemented:

- **Alert Statistics** (`GET /v1/{tenant}/alerts/stats`) - Aggregate statistics by various dimensions
- **Top Risk Entities** (`GET /v1/{tenant}/alerts/top-entities`) - Most frequently targeted entities
- **Top IOCs** (`GET /v1/{tenant}/alerts/top-iocs`) - Most prevalent indicators of compromise
- **Alert Timeline** (`GET /v1/{tenant}/alerts/timeline`) - Time-bucketed alert counts
- **Alert Trends** (`GET /v1/{tenant}/alerts/trends`) - Trending metrics over time

##### Alert Search & Discovery

**Full-Text Search**
```
GET /v1/{tenant}/alerts/search
```
Query Parameters:
- `q`: Search query (searches title, rule_name, short_description, long_description)
- `entity_search`: Search in primary_risk_entity_value
- `ioc_search`: Search in primary_ioc_value
- Standard filtering parameters (status, severity, time_from, time_to, etc.)
- Standard pagination (limit, offset, sort, order)

**Similar Alerts**
```
GET /v1/{tenant}/alerts/{alert_id}/similar
```
Query Parameters:
- `similarity_threshold`: Confidence threshold for similarity (0.0-1.0) - default: 0.7
- `time_window`: Look-back window in days (default: 30)
- `limit`: Number of similar alerts (default: 10, max: 50)

**Related Alerts by Entity**
```
GET /v1/{tenant}/alerts/by-entity/{entity_value}
```
Query Parameters:
- `entity_type`: Required - specify entity type for the value
- Standard filtering and pagination parameters

**Related Alerts by IOC**
```
GET /v1/{tenant}/alerts/by-ioc/{ioc_value}
```
Query Parameters:
- `ioc_type`: Required - specify IOC type for the value
- Standard filtering and pagination parameters

##### Bulk Operations

**Bulk Status Update**
```
PUT /v1/{tenant}/alerts/bulk/status
```
Note: Update status for multiple alerts based on filter criteria

**Bulk Disposition Update**
```
PUT /v1/{tenant}/alerts/bulk/disposition
```
Note: Set disposition for multiple alerts based on filter criteria

**Bulk Export**
```
GET /v1/{tenant}/alerts/export
```
Query Parameters:
- `format`: Export format (json, csv) - default: json
- Standard filtering parameters to define export scope
- `include_raw`: Include raw_alert field in export (true/false) - default: false

##### Alert Validation & Health

**Validate Alert Schema**
```
POST /v1/{tenant}/alerts/validate
```
Note: Validate alert payload against schema before creation

**Alert Deduplication Check**
```
POST /v1/{tenant}/alerts/check-duplicate
```
Note: Check if alert would be duplicate based on content_hash

**Alert Health Metrics**
```
GET /v1/{tenant}/alerts/health
```
Note: System health metrics (ingestion rate, processing delays, error rates)

##### Disposition Categories and Subcategories

Dispositions are a critical part of the data model and should be stored in their own table with a comprehensive REST API for management and querying.

| Category | Subcategory | Suggested Color | Rationale |
| :---- | :---- | :---- | :---- |
| **True Positive (Malicious)** | Confirmed Compromise | 🔴 **Red** | Active compromise with impact. Immediate incident response required. |
|  | Confirmed Malicious Attempt (Blocked/Prevented, No Impact) | 🟠 **Orange** | Verified malicious activity, but blocked before causing harm. Important for intel/tuning, but not urgent containment. |
| **True Positive (Policy Violation)** | Acceptable Use Violation (non-security but against policy) | 🟡 **Yellow** | Typically HR/management follow-up. Not a direct technical threat. |
|  | Unauthorized Access / Privilege Misuse | 🟠 **Orange** | Potential insider threat / misuse. Higher risk than acceptable use violation. |
| **False Positive** | Detection Logic Error | 🟡 **Yellow** | Rule incorrectly designed or triggered. Needs rule fix. |
|  | Rule Misconfiguration / Sensitivity Issue | 🟡 **Yellow** | Tuning issue causing noise. Fixable but not dangerous. |
|  | Vendor Signature Bug | 🟡 **Yellow** | Upstream/vendor problem. Same urgency as other false positives. |
| **Security Testing / Expected Activity** | Red Team / Pentest | 🔵 **Blue** | Expected malicious-like activity. Needs separation from real incidents. |
|  | Compliance / Audit | 🔵 **Blue** | Scheduled or approved test activity. Not a threat. |
|  | Training / Tabletop | 🔵 **Blue** | Drill-only alerts. Must be tracked but not triaged as real incidents. |
| **Benign Explained** | Known Business Process | 🟢 **Green** | Normal business behavior. Should be documented to avoid future noise. |
|  | IT Maintenance / Patch / Scanning | 🟢 **Green** | Routine IT activity (patch cycles, admin scripts, scans). |
|  | Environmental Noise (e.g., server patching or restart) | 🟢 **Green** | Background “chatter” or expected environmental activity. |
| **Undetermined** | Suspicious, Not Confirmed | 🟣 **Purple** | Needs more evidence. Potential threat but not validated. |
|  | Insufficient Data / Logs Missing | 🟣 **Purple** | Can't confirm due to lack of telemetry. Requires escalation or closure. |
|  | Escalated for Review | 🟣 **Purple** | Passed to Tier 2/3 or specialized team. Unresolved. |
| **Analysis Stopped by User** | Invalid Alert | ⚪ **Gray** | Analyst stopped analysis due to invalid trigger (e.g., malformed alert). |
|  | Known Issue / Duplicate | ⚪ **Gray** | Duplicate alert, or already tracked incident. Closed administratively. |

#### Disposition Data Model

```sql
-- Dispositions lookup table
CREATE TABLE dispositions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category TEXT NOT NULL,
    subcategory TEXT NOT NULL,
    display_name TEXT NOT NULL,           -- UI-friendly name
    color_hex TEXT NOT NULL,             -- Hex color code (#FF0000, #FFA500, etc.)
    color_name TEXT NOT NULL,            -- CSS color name (red, orange, yellow, etc.)
    priority_score INTEGER NOT NULL,     -- For sorting/filtering (1=highest, 10=lowest)
    description TEXT,                    -- Detailed explanation/rationale
    requires_escalation BOOLEAN DEFAULT false,
    is_system BOOLEAN DEFAULT true,      -- System-defined vs user-created
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    UNIQUE(category, subcategory)
);

-- Sample data (all system-defined dispositions)
INSERT INTO dispositions (category, subcategory, display_name, color_hex, color_name, priority_score, description, requires_escalation, is_system) VALUES
('True Positive (Malicious)', 'Confirmed Compromise', 'Confirmed Compromise', '#DC2626', 'red', 1, 'Active compromise with impact. Immediate incident response required.', true, true),
('True Positive (Malicious)', 'Confirmed Malicious Attempt (Blocked/Prevented, No Impact)', 'Malicious Attempt Blocked', '#EA580C', 'orange', 2, 'Verified malicious activity, but blocked before causing harm.', false, true),
('True Positive (Policy Violation)', 'Acceptable Use Violation (non-security but against policy)', 'Policy Violation', '#EAB308', 'yellow', 5, 'Typically HR/management follow-up. Not a direct technical threat.', false, true),
('True Positive (Policy Violation)', 'Unauthorized Access / Privilege Misuse', 'Unauthorized Access', '#EA580C', 'orange', 3, 'Potential insider threat / misuse. Higher risk than acceptable use violation.', true, true),
('False Positive', 'Detection Logic Error', 'Detection Logic Error', '#EAB308', 'yellow', 6, 'Rule incorrectly designed or triggered. Needs rule fix.', false, true),
('False Positive', 'Rule Misconfiguration / Sensitivity Issue', 'Rule Misconfiguration', '#EAB308', 'yellow', 6, 'Tuning issue causing noise. Fixable but not dangerous.', false, true),
('False Positive', 'Vendor Signature Bug', 'Vendor Signature Bug', '#EAB308', 'yellow', 6, 'Upstream/vendor problem. Same urgency as other false positives.', false, true),
('Security Testing / Expected Activity', 'Red Team / Pentest', 'Red Team Activity', '#2563EB', 'blue', 8, 'Expected malicious-like activity. Needs separation from real incidents.', false, true),
('Security Testing / Expected Activity', 'Compliance / Audit', 'Compliance Testing', '#2563EB', 'blue', 8, 'Scheduled or approved test activity. Not a threat.', false, true),
('Security Testing / Expected Activity', 'Training / Tabletop', 'Training Exercise', '#2563EB', 'blue', 8, 'Drill-only alerts. Must be tracked but not triaged as real incidents.', false, true),
('Benign Explained', 'Known Business Process', 'Business Process', '#16A34A', 'green', 9, 'Normal business behavior. Should be documented to avoid future noise.', false, true),
('Benign Explained', 'IT Maintenance / Patch / Scanning', 'IT Maintenance', '#16A34A', 'green', 9, 'Routine IT activity (patch cycles, admin scripts, scans).', false, true),
('Benign Explained', 'Environmental Noise (e.g., server patching or restart)', 'Environmental Noise', '#16A34A', 'green', 9, 'Background "chatter" or expected environmental activity.', false, true),
('Undetermined', 'Suspicious, Not Confirmed', 'Suspicious Activity', '#9333EA', 'purple', 4, 'Needs more evidence. Potential threat but not validated.', true, true),
('Undetermined', 'Insufficient Data / Logs Missing', 'Insufficient Data', '#9333EA', 'purple', 4, 'Cannot confirm due to lack of telemetry. Requires escalation or closure.', true, true),
('Undetermined', 'Escalated for Review', 'Escalated for Review', '#9333EA', 'purple', 4, 'Passed to Tier 2/3 or specialized team. Unresolved.', true, true),
('Analysis Stopped by User', 'Invalid Alert', 'Invalid Alert', '#6B7280', 'gray', 10, 'Analyst stopped analysis due to invalid trigger (e.g., malformed alert).', false, true),
('Analysis Stopped by User', 'Known Issue / Duplicate', 'Known Issue/Duplicate', '#6B7280', 'gray', 10, 'Duplicate alert, or already tracked incident. Closed administratively.', false, true);
```

#### Dispositions REST API

##### List All Dispositions
```
GET /v1/{tenant}/dispositions
```

Query Parameters:
- `category`: Filter by category (exact match)
- `requires_escalation`: Filter by escalation requirement (true/false)
- `priority_min`: Minimum priority score (1-10)
- `priority_max`: Maximum priority score (1-10)
- `limit`: Page size (default: 50, max: 100)
- `offset`: Pagination offset
- `sort`: Sort field (priority_score, category, display_name)
- `order`: Sort order (asc, desc)

Response (200):
```json
{
  "dispositions": [
    {
      "id": "uuid",
      "tenant_id": "tenant",
      "category": "True Positive (Malicious)",
      "subcategory": "Confirmed Compromise",
      "display_name": "Confirmed Compromise",
      "color_hex": "#DC2626",
      "color_name": "red",
      "priority_score": 1,
      "description": "Active compromise with impact. Immediate incident response required.",
      "requires_escalation": true,
      "is_system": true,
      "created_at": "2026-04-26T00:00:00Z",
      "updated_at": "2026-04-26T00:00:00Z"
    }
  ],
  "total": 18,
  "limit": 50,
  "offset": 0
}
```

##### Get Specific Disposition
```
GET /v1/{tenant}/dispositions/{id}
```

Response (200):
```json
{
  "id": "uuid",
  "tenant_id": "tenant",
  "category": "True Positive (Malicious)",
  "subcategory": "Confirmed Compromise",
  "display_name": "Confirmed Compromise",
  "color_hex": "#DC2626",
  "color_name": "red",
  "priority_score": 1,
  "description": "Active compromise with impact. Immediate incident response required.",
  "requires_escalation": true,
  "is_system": true,
  "created_at": "2026-04-26T00:00:00Z",
  "updated_at": "2026-04-26T00:00:00Z"
}
```

##### Get Dispositions by Category
```
GET /v1/{tenant}/dispositions/by-category
```

Response (200):
```json
{
  "categories": {
    "True Positive (Malicious)": [
      {
        "id": "uuid",
        "subcategory": "Confirmed Compromise",
        "display_name": "Confirmed Compromise",
        "color_hex": "#DC2626",
        "color_name": "red",
        "priority_score": 1,
        "requires_escalation": true
      },
      {
        "id": "uuid",
        "subcategory": "Confirmed Malicious Attempt (Blocked/Prevented, No Impact)",
        "display_name": "Malicious Attempt Blocked",
        "color_hex": "#EA580C",
        "color_name": "orange",
        "priority_score": 2,
        "requires_escalation": false
      }
    ],
    "False Positive": [
      {
        "id": "uuid",
        "subcategory": "Detection Logic Error",
        "display_name": "Detection Logic Error",
        "color_hex": "#EAB308",
        "color_name": "yellow",
        "priority_score": 6,
        "requires_escalation": false
      }
    ]
  }
}
```

##### Create Custom Disposition (Admin Only)
```
POST /admin/v1/{tenant}/dispositions
```

Request Body:
```json
{
  "category": "Custom Category",
  "subcategory": "Custom Subcategory",
  "display_name": "Custom Disposition",
  "color_hex": "#FF5733",
  "color_name": "custom-orange",
  "priority_score": 7,
  "description": "Custom disposition for specific use case.",
  "requires_escalation": false
}
```

Response (201):
```json
{
  "id": "uuid",
  "category": "Custom Category",
  "subcategory": "Custom Subcategory",
  "display_name": "Custom Disposition",
  "color_hex": "#FF5733",
  "color_name": "custom-orange",
  "priority_score": 7,
  "description": "Custom disposition for specific use case.",
  "requires_escalation": false,
  "is_system": false,
  "created_at": "2026-04-26T00:00:00Z",
  "updated_at": "2026-04-26T00:00:00Z"
}
```

##### Update Disposition (Admin Only, Non-System Only)
```
PUT /admin/v1/{tenant}/dispositions/{id}
```

Request Body:
```json
{
  "display_name": "Updated Custom Disposition",
  "color_hex": "#FF6B47",
  "priority_score": 6,
  "description": "Updated description for custom disposition."
}
```

Response (200): Returns updated disposition object

##### Delete Custom Disposition (Admin Only, Non-System Only)
```
DELETE /admin/v1/{tenant}/dispositions/{id}
```

Response (204): No content

##### Error Responses

All endpoints return simple error messages matching existing API patterns:

- 404: `{"detail": "Disposition not found"}`
- 403: `{"detail": "Cannot modify system disposition"}`
- 409: `{"detail": "Disposition already exists"}`
- 400: `{"detail": "Invalid color format"}`
- 400: `{"detail": "Priority score must be between 1 and 10"}`

##### Integration with Alerts

When setting alert disposition via alerts API:
```json
{
  "prediction": {
    "disposition_id": "uuid",
    "confidence": 85
  }
}
```

Alert responses automatically include expanded disposition details:
```json
{
  "alert_id": "uuid",
  "prediction": {
    "disposition": {
      "id": "uuid",
      "category": "True Positive (Malicious)",
      "subcategory": "Confirmed Compromise",
      "display_name": "Confirmed Compromise",
      "color_hex": "#DC2626",
      "color_name": "red",
      "priority_score": 1,
      "requires_escalation": true
    },
    "confidence": 85
  }
}
```

## Alert Analysis Service

### Overview

The stages of an alert are as follows

* Alert collected from an external system (system not defined yet; Future Work)
* Alert is normalized to our internal Alerts schema (see Alert Parsers section; Future work)
* Alert is persisted via POST, added into Postgres, and made available via our Alerts REST API
  * Examples
    * POST /v1/{tenant}/alerts where we push a JSONized version of our Pydantic Alert (see example below)
      * Returns an alert\_id
    * GET /v1/{tenant}/alerts/{alert\_id}
* Alert analysis is explicitly started via a REST API
  * GET /v1/{tenant}/alerts/{alert\_id}/analyze returns an analysis\_id
* Our alert analysis service is responsible for executing each alert through a series of steps. We will go through the steps next in more detail.
* The analysis service is using the Alerts REST API to update the state of the alert with the outcome of each step and with the final outcome

### Analysis Steps

When an alert is picked up for analysis, the ARQ worker executes these 5 steps sequentially:

#### Step 1: Pre-triage (`pre_triage`)
- Find similar alerts, detect duplicates, perform frequency analysis
- Currently stubbed, implementation left for Future Work
- Updates: `steps_progress.pre_triage.completed = true`

#### Step 2: Context Retrieval (`context_retrieval`)
- Gather additional context about entities, IOCs, historical data
- Currently stubbed, implementation left for Future Work
- Updates: `steps_progress.context_retrieval.completed = true`

#### Step 3: Workflow Builder (`workflow_builder`) - **[PROJECT KEA]**
- AI-powered workflow generation using LangGraph and Claude Agent SDK
- Analyzes alert context and dynamically composes custom workflows
- See `AutomatedWorkflowBuilder_v1.md` for detailed Kea architecture
- Updates: `steps_progress.workflow_builder.completed = true`
- Records: `steps_progress.workflow_builder.selected_workflow` (or generated workflow_id)

#### Step 4: Workflow Execution (`workflow_execution`)
- Execute the selected workflow with alert data as input
- Creates these artifacts:
  - **"Short Summary"** → stored in `alert_analysis.short_summary`
  - **"Summary"** → stored in `alert_analysis.long_summary`
  - **"Complete Analysis"** → stored as artifact only (retrieved via artifacts API)
  - **"Disposition"** → parsed to extract `disposition_id` and `confidence`
- Updates: `steps_progress.workflow_execution.completed = true`
- Records: `steps_progress.workflow_execution.workflow_run_id`

#### Step 5: Final Disposition Update (`final_disposition_update`)
- Parse workflow artifacts and update analysis record
- **Disposition Matching**: Use LangChain + LLM to match artifact disposition text to database UUIDs
  - Artifact contains text like "True Positive - Confirmed Compromise"
  - Query all dispositions from database with categories/subcategories
  - LLM prompt: "Match this disposition text to the closest database entry"
  - Extract disposition_id and confidence from LLM response
- Set disposition_id, confidence, summaries from artifacts
- Updates: `steps_progress.final_disposition_update.completed = true`
- Sets: `status = 'completed'`

#### Step Tracking for Idempotency
Each step checks if already completed before executing:
```python
# Pseudocode in ARQ worker
if not analysis.steps_progress.get('pre_triage', {}).get('completed'):
    execute_pre_triage()
    mark_step_completed('pre_triage')
```

This ensures job retries don't repeat completed steps.

### Alert Analysis Service Design

Note that the service does not include the REST API which is going to always be provided by our main backend FastAPI service.

The Analysis Service is temporarily hosted in the same repository and same Python project as our REST API service, but it will have its own entry point and is going to be executed by a different Docker-dev spec and run in a new container. Make sure the source code and the tests can easily be separated later when we want to split into different projects. If we have to share code between the two, say Pydantic, we should do so via a shared library if possible.

#### Tech Stack

* For queuing up analysis request we are using Python’s arq async library
  * [https://github.com/python-arq/arq](https://github.com/python-arq/arq)
  * Version v0.26.3
* The service will be running its own container with a predefined set of workers (passed to docker through environment)
* Use **Valkey** latest version 8.1.3 (docker image)

#### Implementation Nodes from PoC: ARQ \+ **Valkey** Async Queue Implementation Guide

##### Key Dependencies

```yml
arq \= "^0.26.1"       \# Async job queue
redis \= "^5.2.1"      \# Redis client
valkey/valkey:8.1.3   \# Docker image
```

##### Critical Implementation Notes

###### *Redis Connection*

\# ✅ CORRECT \- Use RedisSettings object

```py
from arq.connections import RedisSettings

redis\_settings \= RedisSettings(host="host", port=6379)
```

\# ❌ WRONG \- String URLs don't work

`redis\_settings \= "redis://host:6379"`

###### *Worker Configuration*

\# ✅ CORRECT \- Pass parameters explicitly

```py
worker \= Worker(
    redis\_settings=redis\_settings,
    functions=functions,
    max\_jobs=10
)
```

\# ❌ WRONG \- Class.\_\_dict\_\_ includes unwanted attributes

worker \= Worker(\*\*WorkerSettings.\_\_dict\_\_)

##### Job Result Retrieval

\# ✅ CORRECT \- Create Job object

```py
from arq.jobs import Job

job \= Job(job\_id, redis\_pool)

result \= await job.result()
```

##### Concurrency Model

- **Guaranteed**: Each job processed exactly once (Redis atomic operations)
- **Scaling**: `Total Capacity = Workers × max_jobs_per_worker`
- **No duplicates**: Multiple workers never process same job

##### Docker Compose Essentials

```yml
valkey:
  image: valkey/valkey:8.1.3
  healthcheck:
    test: \["CMD", "valkey-cli", "ping"\]
worker:
  depends\_on:
    valkey:
      condition: service\_healthy  \# Wait for Valkey
  environment:
    \- MAX\_JOBS=${MAX\_JOBS:-10}   \# Concurrent jobs per worker
```

##### Scaling Strategies

**Horizontal (Multiple Containers)**

docker-compose up \-d \--scale worker=N

**Vertical (More Jobs per Worker)**

MAX\_JOBS=50 docker-compose up

##### Job Function Requirements

- Must be `async def`
- First parameter is always `ctx` (contains job metadata)
- Return serializable data (JSON-compatible)

##### Common Pitfalls

1. Using sync functions as jobs (must be async)
2. Forgetting health check dependency in docker-compose
3. Not handling job timeouts (`job_timeout` setting)
4. Using Redis URL strings instead of RedisSettings objects

## Alert Parsers (Future Work)

We will have a collector service that will be pulling (pull mode) or receiving (push mode) new alerts from different security systems. Next, we suggest the technology and the design of our alert parsing logic.

### Goal

Normalize heterogeneous security alerts (CEF, syslog/CLI outputs, vendor JSON) into a single canonical `Alert` model with minimal code, clear mappings, and strong validation.

### Canonical Model (Demonstration)

```py
from pydantic import BaseModel
from typing import Optional

class Alert(BaseModel):
    title: str                        \# Alert Triggering Reason
    triggering\_event\_time: str        \# Timestamp with timezone
    source\_product: Optional\[str\]
    source\_vendor: Optional\[str\]
    source\_category: Optional\[str\]    \# Firewall|EDR|Identity|Cloud|DLP
    tenant\_id: str
    alert\_id: str                     \# Globally unique UUID
    human\_readable\_id: str            \# AID-1, AID-2...
    rule\_name: Optional\[str\]
    type: Optional\[str\]               \# malware, web\_attack, insider, etc.
    severity: str                     \# critical/high/medium/low/info

    primary\_risk\_entity\_value: Optional\[str\]
    primary\_risk\_entity\_type: Optional\[str\]
    primary\_ioc\_value: Optional\[str\]
    primary\_ioc\_type: Optional\[str\]
    device\_action: Optional\[str\]      \# allowed|blocked|detected|etc.

    ingested\_at: str
    detected\_at: str
    raw\_alert: str

    \# Example nested info (simplified)
    network\_information: dict

    \# Analysis fields (added later)
    status: Optional\[str\]             \# new|analyzing|resolved|suppressed
    analysis\_start\_time: Optional\[str\]
    analysis\_end\_time: Optional\[str\]
    prediction\_disposition: Optional\[str\]
    prediction\_confidence: Optional\[int\]
    short\_description: Optional\[str\]
    long\_description: Optional\[str\]
```

### Flow Overview

Raw input (CEF | CLI | JSON)
        │
        ▼
   jc parser  ──▶  Python dict/list
        │
        ▼
 glom mapping  ──▶  canonical dict
        │
        ▼
  Pydantic      ──▶  Alert (validated)

### Parsing (jc)

* **jc** converts raw text (e.g., CEF string, CLI output, log lines) into structured Python dicts.
* Example: `jc.parse('cef', cef_string)` → `dict`

### Mapping (glom)

* **glom** specs declare how fields map from vendor schema to our canonical model.
* Example (abstract):

from glom import Coalesce

```py
CEF\_SPEC \= {
    "source\_vendor": "DeviceVendor",
    "source\_product": "DeviceProduct",
    "rule\_name": "DeviceEventClassID",
    "title": Coalesce("name", "msg"),
    "severity": "DeviceSeverity",
    "triggering\_event\_time": Coalesce("end", "rt"),
    "primary\_risk\_entity\_value": "dst",
    "primary\_ioc\_value": "request"
}
```

### Adapter Pattern (Abstract Example)

```py
def normalize\_cef(cef\_dict):
    mapped \= glom(cef\_dict, CEF\_SPEC)
    return Alert(\*\*mapped)
```

### Example Conversion

Input (CEF):

```
CEF:0|Acme|WebGW|2.0|1001|URL Contains Clear Text Password|High|src=10.0.0.5 request=http://ex.com/login end=1735678901234
```

Output (Canonical Alert excerpt):

```json
{
  "source\_vendor": "Acme",
  "source\_product": "WebGW",
  "rule\_name": "1001",
  "title": "URL Contains Clear Text Password",
  "severity": "high",
  "triggering\_event\_time": "2026-04-26T12:48:21Z",
  "primary\_risk\_entity\_value": "10.0.0.5",
  "primary\_ioc\_value": "http://ex.com/login"
}
```

## Step-by-Step Alert Analysis Walkthrough

This section provides a complete end-to-end walkthrough of the alert analysis experience, showing which APIs are called, what happens in each service, and the data flow between components.

### Step 1: Alert Ingestion & Storage

**Step 1.1: Alert Creation**
- **Service**: Main Backend (FastAPI)
- **API Call**: `POST /v1/{tenant}/alerts`
- **What happens**:
  - Alert data validated against `AlertCreate` schema
  - `human_readable_id` auto-generated (AID-1, AID-2...)
  - `content_hash` calculated for deduplication
  - Alert persisted to `alerts` table with `analysis_status = 'not_analyzed'`
  - Returns alert with `alert_id`

**Step 1.2: Alert Retrieval (Optional)**
- **Service**: Main Backend (FastAPI)
- **API Call**: `GET /v1/{tenant}/alerts/{alert_id}`
- **What happens**:
  - Returns alert metadata
  - `current_analysis_id` is NULL initially
  - `analysis_status` shows 'not_analyzed'

### Step 2: Analysis Initiation

**Step 2.1: Start Analysis**
- **Service**: Main Backend (FastAPI)
- **API Call**: `POST /v1/{tenant}/alerts/{alert_id}/analyze`
- **What happens**:
  - Creates new record in `alert_analysis` table with `status = 'pending'`
  - Updates `alerts.current_analysis_id` to point to new analysis
  - Updates `alerts.analysis_status = 'analyzing'`
  - **Queues ARQ job** with analysis_id for Alert Analysis Service
  - Returns `analysis_id` immediately (202 Accepted)

### Step 3: ARQ Worker Processing (Alert Analysis Service)

**Step 3.1: Pre-triage**
- **Service**: Alert Analysis Service (ARQ Worker)
- **Internal Process**:
  - Checks `steps_progress.pre_triage.completed` (idempotency)
  - If not completed: executes pre-triage logic (stubbed for now)
  - Updates `alert_analysis.steps_progress.pre_triage.completed = true`
  - Updates `alert_analysis.current_step = 'context_retrieval'`

**Step 3.2: Context Retrieval**
- **Service**: Alert Analysis Service (ARQ Worker)
- **Internal Process**:
  - Checks `steps_progress.context_retrieval.completed`
  - If not completed: gathers additional context (stubbed for now)
  - Updates `alert_analysis.steps_progress.context_retrieval.completed = true`
  - Updates `alert_analysis.current_step = 'workflow_builder'`

**Step 3.3: Workflow Builder** - **[PROJECT KEA]**
- **Service**: Alert Analysis Service (ARQ Worker)
- **Internal Process**:
  - Checks `steps_progress.workflow_builder.completed`
  - If not completed: uses AI agent to analyze alert and generate custom workflow
  - Leverages LangGraph and Claude Agent SDK for intelligent workflow composition
  - Updates `alert_analysis.steps_progress.workflow_builder.completed = true`
  - Records generated/selected workflow in `steps_progress.workflow_builder.selected_workflow`
  - Updates `alert_analysis.current_step = 'workflow_execution'`

**Step 3.4: Workflow Execution**
- **Service**: Alert Analysis Service (ARQ Worker)
- **API Calls Made by Worker**:
  - Calls existing Workflow API to execute selected workflow
  - Calls Artifacts API to store generated artifacts
- **Internal Process**:
  - Checks `steps_progress.workflow_execution.completed`
  - If not completed: executes workflow with alert data as input
  - **Creates 4 artifacts via Artifacts API**:
    - "Short Summary" → will populate `alert_analysis.short_summary`
    - "Summary" → will populate `alert_analysis.long_summary`
    - "Complete Analysis" → stored as artifact only
    - "Disposition" → contains disposition text (e.g., "True Positive - Confirmed Compromise") and confidence
  - Updates `alert_analysis.workflow_run_id`
  - Updates `steps_progress.workflow_execution.completed = true`
  - Records workflow_run_id in `steps_progress.workflow_execution.workflow_run_id`
  - Updates `alert_analysis.current_step = 'final_disposition_update'`

**Step 3.5: Final Disposition Update**
- **Service**: Alert Analysis Service (ARQ Worker)
- **Internal Process**:
  - Checks `steps_progress.final_disposition_update.completed`
  - If not completed: parses workflow artifacts
  - **Disposition Matching with LLM**:
    - Retrieves "Disposition" artifact containing text like "True Positive - Confirmed Compromise"
    - Queries all dispositions from database via internal API call
    - Uses LangChain + LLM with structured prompt:
      ```
      Available dispositions:
      1. True Positive (Malicious) - Confirmed Compromise (UUID: xxx)
      2. True Positive (Malicious) - Confirmed Malicious Attempt (UUID: yyy)
      ...

      Workflow output: "True Positive - Confirmed Compromise with 85% confidence"

      Return the matching disposition UUID and extracted confidence.
      ```
    - LLM returns structured response with disposition_id and confidence
  - Updates `alert_analysis` with:
    - `disposition_id` (from LLM matching)
    - `confidence` (extracted from artifact text)
    - `short_summary` (from "Short Summary" artifact)
    - `long_summary` (from "Summary" artifact)
  - Updates `steps_progress.final_disposition_update.completed = true`
  - Sets `alert_analysis.status = 'completed'`
  - Sets `alert_analysis.completed_at = now()`
  - Updates `alerts.analysis_status = 'analyzed'`

### Step 4: Progress Monitoring (During Analysis)

**Step 4.1: Check Analysis Progress**
- **Service**: Main Backend (FastAPI)
- **API Call**: `GET /v1/{tenant}/alerts/{alert_id}/analysis/progress`
- **What happens**:
  - Queries `alert_analysis` table for current analysis
  - Returns current step and completion status
  - Example response:
    ```json
    {
      "analysis_id": "uuid",
      "current_step": "workflow_execution",
      "completed_steps": 3,
      "total_steps": 5,
      "status": "running"
    }
    ```

### Step 5: Results Retrieval

**Step 5.1: Get Completed Analysis**
- **Service**: Main Backend (FastAPI)
- **API Call**: `GET /v1/{tenant}/alerts/{alert_id}?include_analysis=true&include_disposition=true`
- **What happens**:
  - Returns alert with expanded analysis and disposition details
  - Includes disposition with color coding from dispositions table
  - Shows short_summary, long_summary, confidence, etc.

**Step 5.2: View Analysis History**
- **Service**: Main Backend (FastAPI)
- **API Call**: `GET /v1/{tenant}/alerts/{alert_id}/analyses`
- **What happens**:
  - Returns all analysis runs for the alert (supports re-analysis)
  - Shows historical analysis attempts with timestamps and results

### Step 6: Re-analysis (Optional)

**Step 6.1: Trigger Re-analysis**
- **Service**: Main Backend (FastAPI)
- **API Call**: `POST /v1/{tenant}/alerts/{alert_id}/analyze` (same as initial)
- **What happens**:
  - Creates NEW record in `alert_analysis` table
  - Updates `alerts.current_analysis_id` to new analysis
  - Queues new ARQ job
  - Previous analysis remains in history
  - Process repeats from Phase 3

### Key Service Boundaries

**Main Backend (FastAPI)**:
- All REST API endpoints
- Database CRUD operations
- ARQ job queuing
- User-facing responses

**Alert Analysis Service (ARQ Worker)**:
- Asynchronous step-by-step processing
- Workflow execution coordination
- Artifact creation via API calls back to main backend
- LLM-powered disposition matching
- Progress updates via database writes
- No direct user interaction

**Database Tables**:
- `alerts`: Immutable alert data + analysis status
- `alert_analysis`: Mutable analysis results + step tracking
- `dispositions`: Color-coded disposition lookup
- Plus existing `workflows`, `artifacts`, etc.

### Error Handling & Retries

**Job Failures**:
- ARQ automatically retries failed jobs
- Each step's idempotency ensures no duplicate work
- Failed steps can be resumed from current position
- Error details stored in `steps_progress.{step}.error`

**Partial Completion**:
- If analysis fails at Step 3.4, Steps 3.1-3.3 remain marked completed
- Retry starts directly at Step 3.4 (workflow_execution)
- UI shows progress accurately via `steps_progress` JSONB

This design ensures clean separation where the main backend handles all user interactions and the analysis service focuses purely on processing workflows with robust error recovery.
