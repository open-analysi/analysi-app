"""Extended OCSF Detection Finding model — Project Skaros.

The upstream py-ocsf-models library ships a DetectionFinding with the 47 core
fields defined by OCSF class 2004, but it does *not* include optional profile
fields (Security Control, OSINT, Host, Incident, etc.).  Many security products
populate those profile fields, and our normalisation pipeline needs to preserve
them.

AnalysiDetectionFinding inherits the base class and bolts on every profile
field we care about.  For OCSF object types that py-ocsf-models already
provides we import them directly; for the rest we define lightweight Pydantic
stubs with ``extra = "allow"`` so downstream code can still round-trip the full
JSON without data loss.
"""

from __future__ import annotations

from enum import IntEnum

# ── Base Detection Finding ──────────────────────────────────────────────
from py_ocsf_models.events.findings.detection_finding import (
    DetectionFinding,
)

# ── Re-usable OCSF objects already in py-ocsf-models ───────────────────
from py_ocsf_models.events.findings.disposition_id import DispositionID
from py_ocsf_models.objects.device import Device
from py_ocsf_models.objects.group import Group
from py_ocsf_models.objects.mitre_attack import MITREAttack as MitreAttack
from py_ocsf_models.objects.policy import Policy
from py_ocsf_models.objects.user import User
from pydantic import BaseModel, ConfigDict

# ── Constants ───────────────────────────────────────────────────────────
OCSF_VERSION: str = "1.8.0"

PROFILES: list[str] = [
    "security_control",
    "osint",
    "host",
    "incident",
]

# ═══════════════════════════════════════════════════════════════════════
# Integer enums not provided by py-ocsf-models
# ═══════════════════════════════════════════════════════════════════════


class ActionID(IntEnum):
    """OCSF Action ID — describes the action taken by the security product."""

    UNKNOWN = 0
    ALLOWED = 1
    DENIED = 2
    OTHER = 99


class VerdictID(IntEnum):
    """OCSF Verdict ID — describes the analyst/automated verdict."""

    UNKNOWN = 0
    BENIGN = 1
    SUSPICIOUS = 2
    MALICIOUS = 3
    INFORMATIONAL = 4
    OTHER = 99


class PriorityID(IntEnum):
    """OCSF Priority ID — describes the priority of the finding."""

    UNKNOWN = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4
    OTHER = 99


# ═══════════════════════════════════════════════════════════════════════
# Lightweight OCSF object stubs (not available in py-ocsf-models)
#
# Each stub carries the most important fields for our use-cases and is
# configured with ``extra = "allow"`` so that any additional OCSF fields
# present in the source data are preserved on round-trip.
# ═══════════════════════════════════════════════════════════════════════


class _OCSFExtraModel(BaseModel):
    """Base for all local OCSF stubs — allows extra fields."""

    model_config = ConfigDict(extra="allow")


# ═══════════════════════════════════════════════════════════════════════
# OCSF sub-models for AlertCreate validation
#
# The upstream py-ocsf-models classes incorrectly mark many fields as
# required that OCSF defines as optional, and silently drop unknown
# fields.  We define our own lightweight models that:
#   1. Only require fields that OCSF actually requires
#   2. Use extra="allow" to preserve vendor-specific fields
#   3. Type the most important fields for IDE/autocomplete support
# ═══════════════════════════════════════════════════════════════════════


class FindingInfo(_OCSFExtraModel):
    """OCSF Finding Info object."""

    uid: str | None = None
    title: str | None = None
    desc: str | None = None
    types: list[str] | None = None
    analytic: dict | None = None  # Analytic sub-object (name, uid, type_id)
    related_analytics: list[dict] | None = None
    attacks: list[dict] | None = None
    src_url: str | None = None
    data_sources: list[str] | None = None
    created_time: str | None = None
    created_time_dt: str | None = None


class OCSFMetadata(_OCSFExtraModel):
    """OCSF Metadata object — product info, version, labels."""

    version: str | None = None
    product: dict | None = None  # {name, vendor_name, version, uid}
    profiles: list[str] | None = None
    labels: list[str] | None = None
    event_code: str | None = None
    uid: str | None = None
    log_name: str | None = None
    logged_time: str | None = None
    original_time: str | None = None


class EvidenceArtifact(_OCSFExtraModel):
    """OCSF Evidence Artifact — network, process, file, URL evidence."""

    src_endpoint: dict | None = None
    dst_endpoint: dict | None = None
    connection_info: dict | None = None
    process: dict | None = None
    file: dict | None = None
    url: dict | None = None
    http_request: dict | None = None
    http_response: dict | None = None
    actor: dict | None = None
    device: dict | None = None


class Observable(_OCSFExtraModel):
    """OCSF Observable — IOC with type classification."""

    type_id: int
    value: str
    name: str | None = None
    type: str | None = None
    reputation: dict | None = None


class OCSFDevice(_OCSFExtraModel):
    """OCSF Device object — host/endpoint information."""

    hostname: str | None = None
    name: str | None = None
    ip: str | None = None
    uid: str | None = None
    type_id: int | None = None
    type: str | None = None
    domain: str | None = None
    os: dict | None = None


class OCSFCloud(_OCSFExtraModel):
    """OCSF Cloud object — cloud provider context."""

    provider: str | None = None
    region: str | None = None
    account: dict | None = None
    org: dict | None = None
    project_uid: str | None = None


class VulnerabilityDetail(_OCSFExtraModel):
    """OCSF Vulnerability Details — CVE and impact data."""

    cve: dict | None = None  # {uid, cvss: [{base_score, severity, version}]}
    desc: str | None = None
    severity: str | None = None
    kb_articles: list[str] | None = None
    references: list[str] | None = None


class Actor(_OCSFExtraModel):
    """OCSF Actor object (process + user that triggered the event)."""

    user: dict | None = (
        None  # OCSF User object — loose to avoid upstream required-field issues
    )
    process: dict | None = None  # OCSF Process object — intentionally loose
    session: dict | None = None
    app_name: str | None = None
    invoked_by: str | None = None


class FirewallRule(_OCSFExtraModel):
    """OCSF Firewall Rule object."""

    uid: str | None = None
    name: str | None = None
    type: str | None = None
    condition: str | None = None
    match_location: str | None = None
    match_details: str | None = None
    rate_limit: int | None = None


class Malware(_OCSFExtraModel):
    """OCSF Malware object."""

    uid: str | None = None
    name: str | None = None
    path: str | None = None
    classification_ids: list[int] | None = None
    classifications: list[str] | None = None
    provider: str | None = None
    cves: list[dict] | None = None


class MalwareScanInfo(_OCSFExtraModel):
    """OCSF Malware Scan Info — results of a malware scan."""

    scan_uid: str | None = None
    scan_type: str | None = None
    scan_type_id: int | None = None
    scan_engine: str | None = None
    scan_result: str | None = None
    scan_result_id: int | None = None


class Authorization(_OCSFExtraModel):
    """OCSF Authorization object."""

    decision: str | None = None
    policy: Policy | None = None


class OSINT(_OCSFExtraModel):
    """OCSF OSINT (Open Source Intelligence) object."""

    uid: str | None = None
    type: str | None = None
    type_id: int | None = None
    value: str | None = None
    name: str | None = None
    src_url: str | None = None
    confidence_id: int | None = None
    confidence: str | None = None
    provider: str | None = None


class Ticket(_OCSFExtraModel):
    """OCSF Ticket object — external ticket/case reference."""

    uid: str | None = None
    url: str | None = None
    title: str | None = None
    desc: str | None = None
    type: str | None = None
    severity: str | None = None
    status: str | None = None


class VendorAttributes(_OCSFExtraModel):
    """OCSF Vendor Attributes — vendor-specific key/value pairs."""

    name: str | None = None
    uid: str | None = None
    values: list[str] | None = None


class AnomalyAnalysis(_OCSFExtraModel):
    """OCSF Anomaly Analysis object."""

    uid: str | None = None
    type: str | None = None
    type_id: int | None = None
    score: float | None = None
    threshold: float | None = None
    description: str | None = None


# ═══════════════════════════════════════════════════════════════════════
# Extended Detection Finding
# ═══════════════════════════════════════════════════════════════════════


class AnalysiDetectionFinding(DetectionFinding):
    """OCSF 1.8.0 Detection Finding with profile fields.

    Inherits the 47 core fields from ``py_ocsf_models`` and adds fields
    from the Security Control, OSINT, Host, and Incident profiles that the
    upstream library omits.

    Project Skaros — we extend rather than fork so we stay in sync with
    upstream core-field updates while still being able to ingest the richer
    payloads that modern detection tools produce.
    """

    model_config = ConfigDict(extra="allow")

    # ── Security Control profile ────────────────────────────────────
    disposition_id: DispositionID | None = None
    disposition: str | None = None
    action_id: ActionID | None = None
    action: str | None = None
    is_alert: bool | None = None
    policy: Policy | None = None
    firewall_rule: FirewallRule | None = None
    attacks: list[MitreAttack] | None = None
    malware: list[Malware] | None = None
    malware_scan_info: MalwareScanInfo | None = None
    authorizations: list[Authorization] | None = None

    # ── OSINT profile ───────────────────────────────────────────────
    osint: list[OSINT] | None = None

    # ── Host profile ────────────────────────────────────────────────
    device: Device | None = None
    actor: Actor | None = None

    # ── Incident profile ────────────────────────────────────────────
    verdict_id: VerdictID | None = None
    verdict: str | None = None
    assignee: User | None = None
    assignee_group: Group | None = None
    tickets: list[Ticket] | None = None
    is_suspected_breach: bool | None = None

    # ── Additional fields ───────────────────────────────────────────
    raw_data_hash: str | None = None
    raw_data_size: int | None = None
    priority_id: PriorityID | None = None
    priority: str | None = None
    src_url: str | None = None
    vendor_attributes: VendorAttributes | None = None
    anomaly_analyses: list[AnomalyAnalysis] | None = None
