"""
Artifact SQLAlchemy model.

Immutable artifacts with inline/object storage and multi-tenant isolation.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from analysi.db.base import Base


class Artifact(Base):
    """
    Artifacts table - partitioned by created_at for scalability.

    Stores immutable artifacts created during analysis of alerts, tasks, and workflows.
    Supports both inline storage (≤8KB) and object storage (>8KB) via MinIO.
    """

    __tablename__ = "artifacts"

    # Composite primary key for partitioning
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
        server_default=func.now(),
    )

    # Multi-tenant isolation
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Core metadata
    name: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_type: Mapped[str | None] = mapped_column(
        Text, index=True
    )  # timeline, activity_graph, alert_summary, etc.
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="'[]'::jsonb"
    )

    # Content hashing
    sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # 32 bytes
    md5: Mapped[bytes | None] = mapped_column(LargeBinary)  # 16 bytes (optional)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Storage strategy
    storage_class: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # 'inline' or 'object'
    inline_content: Mapped[bytes | None] = mapped_column(
        LargeBinary
    )  # For ≤8KB artifacts
    content_encoding: Mapped[str | None] = mapped_column(
        Text
    )  # 'zlib' when compressed, NULL otherwise

    # Object store reference (when storage_class='object')
    bucket: Mapped[str | None] = mapped_column(Text)
    object_key: Mapped[str | None] = mapped_column(Text)

    # Relationship fields (at least one must be non-null, multiple can be populated)
    alert_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), index=True
    )  # Direct link to alert (for manual attachments via REST API only)
    task_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True)
    )  # Partition-aware reference
    workflow_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True)
    )  # Partition-aware reference
    workflow_node_instance_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True)
    )  # Partition-aware reference
    analysis_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True)
    )  # Links to alert_analyses table

    # Integration and provenance tracking
    integration_id: Mapped[str | None] = mapped_column(
        String(255), index=True
    )  # Integration instance (e.g., "virustotal-prod")
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="unknown", index=True
    )  # Provenance: auto_capture, cy_script, rest_api, mcp

    # Soft delete support
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Table constraints handled in migration:
    # - CHECK constraint: at least one relationship field must be non-null
    # - CHECK constraint: storage_class IN ('inline', 'object')
    # - Partitioning: PARTITION BY RANGE (created_at)

    def __init__(self, **kwargs):
        """Initialize Artifact with all required fields."""
        # Let SQLAlchemy handle the standard initialization
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        """String representation of artifact."""
        return f"<Artifact(id={self.id}, tenant_id='{self.tenant_id}', name='{self.name}', type='{self.artifact_type}')>"

    @property
    def is_inline_storage(self) -> bool:
        """Check if artifact uses inline storage."""
        return bool(self.storage_class == "inline")

    @property
    def is_soft_deleted(self) -> bool:
        """Check if artifact is soft deleted."""
        return self.deleted_at is not None

    def get_content_size_kb(self) -> float:
        """Get content size in KB for display."""
        return float(self.size_bytes / 1024.0)
