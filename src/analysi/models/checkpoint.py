"""
Checkpoint model — cross-run cursor state for Tasks and Workflows.

Project Symi: Persists checkpoint state between runs. Run N's checkpoint
becomes run N+1's starting point (e.g., last_pull timestamp for alert ingestion).

Generalized from task-only to support any owner_type (task, workflow, etc.).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from analysi.db.base import Base


class Checkpoint(Base):
    """Key-value checkpoint scoped to (tenant, owner_type, owner_id, key).

    Not partitioned — low row count (one row per checkpoint per owner).
    """

    __tablename__ = "checkpoints"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_type: Mapped[str] = mapped_column(String(20), nullable=False, default="task")
    owner_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    __table_args__ = (UniqueConstraint("tenant_id", "owner_type", "owner_id", "key"),)

    def __repr__(self) -> str:
        return (
            f"<Checkpoint(id={self.id}, tenant_id={self.tenant_id}, "
            f"owner_type={self.owner_type!r}, owner_id={self.owner_id}, "
            f"key={self.key!r})>"
        )
