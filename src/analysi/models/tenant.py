"""Tenant model — first-class tenant lifecycle management (Project Delos)."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from analysi.db.base import Base


class Tenant(Base):
    """
    Explicit tenant registry.

    Previously tenants were implicit — referenced by tenant_id strings across
    tables but with no central record of which tenants exist. This model makes
    tenants first-class entities, enabling platform-level operations like
    create, list, describe, and cascade-delete.
    """

    __tablename__ = "tenants"

    # Human-readable identifier (e.g., "acme-corp", "default")
    id: Mapped[str] = mapped_column(String(255), primary_key=True)

    # Display name
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Lifecycle status: active, suspended
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")

    # Timestamps (always timezone-aware)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    def __repr__(self) -> str:
        return f"<Tenant(id='{self.id}', name='{self.name}', status='{self.status}')>"
