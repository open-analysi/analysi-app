"""SQLAlchemy models for Integration system."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from analysi.db.base import Base


class Integration(Base):
    """
    Model for configured integrations to 3rd party tools.
    Represents a specific instance like 'splunk-prod' or 'echo-staging'.
    """

    __tablename__ = "integrations"

    # Composite primary key for multi-tenancy
    integration_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)

    # Integration metadata
    integration_type: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Configuration
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    settings: Mapped[dict | None] = mapped_column(JSONB)

    # Health (cached from most recent health check TaskRun — Project Symi)
    health_status: Mapped[str | None] = mapped_column(String(50))
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
