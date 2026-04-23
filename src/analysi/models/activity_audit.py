"""
SQLAlchemy model for Activity Audit Trail.

Tracks all user and system actions for audit purposes.
Partitioned by created_at for time-series performance.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from analysi.db.base import Base


class ActivityAuditTrail(Base):
    """
    Model for activity audit trail - partitioned by created_at.

    Tracks all user and system actions including:
    - Page views
    - CRUD operations
    - Task/workflow executions
    - Configuration changes
    """

    __tablename__ = "activity_audit_trails"

    # Composite primary key for partitioning
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        server_default=func.current_timestamp(),
    )

    # Multi-tenancy
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Actor information (UUID, no FK — partitioned table)
    actor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True
    )  # UUID reference to users table
    actor_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="user"
    )  # user, system, api_key, workflow

    # Action details
    action: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )  # e.g., "workflow.execute"
    resource_type: Mapped[str | None] = mapped_column(
        String(100)
    )  # e.g., "workflow", "alert"
    resource_id: Mapped[str | None] = mapped_column(
        String(255)
    )  # ID of the affected resource

    # Source subsystem
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="unknown", index=True
    )  # rest_api, mcp, ui, internal

    # Context
    details: Mapped[dict | None] = mapped_column(JSONB)  # Additional structured data
    ip_address: Mapped[str | None] = mapped_column(String(45))  # IPv4/IPv6
    user_agent: Mapped[str | None] = mapped_column(Text)  # Browser/client info
    request_id: Mapped[str | None] = mapped_column(
        String(100)
    )  # Request correlation ID
