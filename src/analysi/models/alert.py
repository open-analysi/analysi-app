"""Alert system database models.

OCSF Detection Finding v1.8.0 schema.
"""

from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analysi.db.base import Base
from analysi.schemas.alert import AlertStatus


class Alert(Base):
    """Alert model — OCSF Detection Finding v1.8.0 (Project Skaros).

    Columns follow OCSF Detection Finding v1.8.0. Legacy columns:
    (primary_risk_entity_*, primary_ioc_*, device_action, alert_type,
    source_category, network_info, web_info, process_info, file_info,
    email_info, cloud_info, cve_info, other_activities, risk_entities,
    iocs, content_hash) have been removed.
    """

    __tablename__ = "alerts"

    # ── Core identifiers ──────────────────────────────────────────────
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    human_readable_id: Mapped[str] = mapped_column(Text, nullable=False)

    # ── Source alert information (immutable) ──────────────────────────
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # Partition key (legacy) — kept for existing queries
    triggering_event_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source_vendor: Mapped[str | None] = mapped_column(Text)
    source_product: Mapped[str | None] = mapped_column(Text)
    rule_name: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(
        String, nullable=False
    )  # String caption: critical, high, medium, low, info

    # Source system reference
    source_event_id: Mapped[str | None] = mapped_column(String(500))

    # ── OCSF structured JSONB fields ─────────────────────────────────
    finding_info: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )  # OCSF FindingInfo: title, uid, analytic, types, data_sources
    ocsf_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )  # OCSF Metadata: product, version, labels, profiles
    evidences: Mapped[list | None] = mapped_column(JSONB)
    observables: Mapped[list | None] = mapped_column(JSONB)
    osint: Mapped[list | None] = mapped_column(JSONB)
    actor: Mapped[dict | None] = mapped_column(JSONB)
    device: Mapped[dict | None] = mapped_column(JSONB)
    cloud: Mapped[dict | None] = mapped_column(JSONB)
    vulnerabilities: Mapped[list | None] = mapped_column(JSONB)
    unmapped: Mapped[dict | None] = mapped_column(JSONB)

    # ── OCSF scalar enum columns ─────────────────────────────────────
    severity_id: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=3, server_default="3"
    )  # 1=Info, 2=Low, 3=Medium, 4=High, 5=Critical
    disposition_id: Mapped[int | None] = mapped_column(SmallInteger)
    verdict_id: Mapped[int | None] = mapped_column(SmallInteger)
    action_id: Mapped[int | None] = mapped_column(SmallInteger)
    status_id: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default="1"
    )
    confidence_id: Mapped[int | None] = mapped_column(SmallInteger)
    risk_level_id: Mapped[int | None] = mapped_column(SmallInteger)

    # ── OCSF time + dedup ────────────────────────────────────────────
    ocsf_time: Mapped[int | None] = mapped_column(BigInteger)
    raw_data_hash: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )  # SHA-256 of raw_data for dedup (replaces content_hash)
    raw_data_hash_algorithm: Mapped[str] = mapped_column(
        String(10), nullable=False, default="SHA-256", server_default="SHA-256"
    )

    # ── Timestamps ────────────────────────────────────────────────────
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Raw data preservation (renamed from raw_alert)
    raw_data: Mapped[str] = mapped_column(Text, nullable=False)

    # ── Analysis reference ────────────────────────────────────────────
    current_analysis_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    analysis_status: Mapped[str | None] = mapped_column(
        String, default="new"
    )  # Enum: new, in_progress, completed, failed, cancelled

    # Denormalized disposition fields for fast filtering and UI display
    current_disposition_category: Mapped[str | None] = mapped_column(String)
    current_disposition_subcategory: Mapped[str | None] = mapped_column(String)
    current_disposition_display_name: Mapped[str | None] = mapped_column(String)
    current_disposition_confidence: Mapped[int | None] = mapped_column(Integer)

    # ── Metadata ──────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=lambda: datetime.now(UTC),
    )

    @property
    def alert_id(self) -> UUID:
        """Backward-compatible alias for API serialization.

        The DB column is ``id`` (standard PK naming), but the API contract
        exposes ``alert_id`` via Pydantic's ``AlertResponse`` schema.
        """
        return self.id

    @property
    def raw_alert(self) -> str:
        """Backward-compatible alias — reads from ``raw_data``."""
        return self.raw_data

    @raw_alert.setter
    def raw_alert(self, value: str) -> None:
        """Backward-compatible alias — writes to ``raw_data``."""
        self.raw_data = value

    # Relationships
    analyses: Mapped[list["AlertAnalysis"]] = relationship(
        "AlertAnalysis", back_populates="alert", cascade="all, delete-orphan"
    )

    # Table arguments for partitioning and constraints
    # NOTE: The table is partitioned by ingested_at, not triggering_event_time
    # This allows ingesting historical alerts without partition management issues
    __table_args__ = (
        PrimaryKeyConstraint("id", "ingested_at"),
        UniqueConstraint(
            "tenant_id",
            "human_readable_id",
            "ingested_at",
            name="alerts_tenant_human_readable_id_unique",
        ),
        # ── Shared / kept indexes ─────────────────────────────────────
        Index("idx_alerts_tenant_status", "tenant_id", "analysis_status"),
        Index("idx_alerts_tenant_severity", "tenant_id", "severity"),
        Index("idx_alerts_tenant_time_desc", "tenant_id", "triggering_event_time"),
        Index(
            "idx_alerts_source_product", "tenant_id", "source_product", "source_vendor"
        ),
        # ── OCSF indexes ─────────────────────────────────────────────
        Index(
            "idx_alerts_raw_data_hash",
            "tenant_id",
            "raw_data_hash",
            postgresql_where=text("raw_data_hash != ''"),
        ),
        Index("idx_alerts_severity_id", "tenant_id", "severity_id"),
        Index(
            "idx_alerts_disposition_id",
            "tenant_id",
            "disposition_id",
            postgresql_where=text("disposition_id IS NOT NULL"),
        ),
        {"postgresql_partition_by": "RANGE (ingested_at)"},
    )

    @staticmethod
    def generate_human_readable_id(sequence_number: int) -> str:
        """Generate human-readable ID like AID-1, AID-2."""
        return f"AID-{sequence_number}"


class AlertAnalysis(Base):
    """Alert analysis tracking model."""

    __tablename__ = "alert_analyses"

    # id is part of composite primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, server_default=func.gen_random_uuid()
    )
    alert_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("alerts.id"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Analysis lifecycle
    status: Mapped[str | None] = mapped_column(
        String, default="running"
    )  # See AnalysisStatus: running, paused, paused_human_review, completed, failed, cancelled
    error_message: Mapped[str | None] = mapped_column(Text)  # Store failure reason
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Step tracking
    current_step: Mapped[str | None] = mapped_column(Text)
    steps_progress: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # Analysis results
    disposition_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("dispositions.id")
    )
    confidence: Mapped[int | None] = mapped_column(Integer)  # 0-100
    short_summary: Mapped[str | None] = mapped_column(Text)
    long_summary: Mapped[str | None] = mapped_column(Text)

    # Workflow tracking
    workflow_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    workflow_run_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))

    # Workflow generation retry tracking
    workflow_gen_retry_count: Mapped[int | None] = mapped_column(Integer, default=0)
    workflow_gen_last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # Framework-level job tracking metadata (Project Leros)
    job_tracking: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}", default=dict
    )

    # Metadata - created_at is partition key and part of composite primary key
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    alert: Mapped["Alert"] = relationship("Alert", back_populates="analyses")
    disposition: Mapped[Optional["Disposition"]] = relationship("Disposition")

    __table_args__ = (
        PrimaryKeyConstraint("id", "created_at"),
        Index("idx_analysis_tenant_status", "tenant_id", "status"),
        Index("idx_analysis_alert", "alert_id"),
        Index("idx_analysis_alert_created", "alert_id", "created_at"),
        Index("idx_analysis_workflow_run", "workflow_run_id"),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )

    def update_step_progress(
        self, step: str, completed: bool, error: str | None = None
    ) -> None:
        """Update progress for a specific analysis step."""
        if self.steps_progress is None:
            self.steps_progress = {}

        now = datetime.now(UTC)
        step_data = self.steps_progress.get(step, {})

        if not step_data.get("started_at"):
            step_data["started_at"] = now.isoformat()

        step_data["completed"] = completed
        if completed:
            step_data["completed_at"] = now.isoformat()

        if error:
            step_data["error"] = error
            step_data["retries"] = step_data.get("retries", 0) + 1

        self.steps_progress[step] = step_data
        self.current_step = step if not completed else None

    def mark_completed(self) -> None:
        """Mark analysis as completed with timestamp."""
        self.status = AlertStatus.COMPLETED
        self.completed_at = datetime.now(UTC)

        # If there's a current step, mark it as completed before clearing
        if self.current_step and self.steps_progress:
            now = datetime.now(UTC)
            step_data = self.steps_progress.get(self.current_step, {})
            step_data["completed"] = True
            step_data["completed_at"] = now.isoformat()
            if not step_data.get("started_at"):
                step_data["started_at"] = now.isoformat()
            self.steps_progress[self.current_step] = step_data

        self.current_step = None


class Disposition(Base):
    """Disposition categories for alert classification."""

    __tablename__ = "dispositions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    subcategory: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    color_hex: Mapped[str] = mapped_column(Text, nullable=False)
    color_name: Mapped[str] = mapped_column(Text, nullable=False)
    priority_score: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # 1-10, 1 is highest
    description: Mapped[str | None] = mapped_column(Text)
    requires_escalation: Mapped[bool | None] = mapped_column(Boolean, default=False)
    is_system: Mapped[bool | None] = mapped_column(Boolean, default=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (UniqueConstraint("category", "subcategory"),)

    def to_dict(self) -> dict:
        """Convert disposition to dictionary."""
        return {
            "id": str(self.id),
            "category": self.category,
            "subcategory": self.subcategory,
            "display_name": self.display_name,
            "color_hex": self.color_hex,
            "color_name": self.color_name,
            "priority_score": self.priority_score,
            "description": self.description,
            "requires_escalation": self.requires_escalation,
            "is_system": self.is_system,
        }
