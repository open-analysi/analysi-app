"""
SQLAlchemy models for authentication & authorization.

Project Mikonos — Auth & RBAC (Spec: version_7/AuthAndRBAC_v1.md)
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analysi.db.base import Base

# Well-known sentinel user IDs — real rows in the users table.
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
UNKNOWN_USER_ID = UUID("00000000-0000-0000-0000-000000000002")


class User(Base):
    """Registered user. Keycloak is the source of truth; this is a local mirror."""

    __tablename__ = "users"
    __table_args__ = ({"schema": None, "extend_existing": True},)

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    keycloak_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    memberships: Mapped[list["Membership"]] = relationship(
        "Membership",
        foreign_keys="[Membership.user_id]",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    api_keys: Mapped[list["ApiKey"]] = relationship(
        "ApiKey",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Membership(Base):
    """Tenant-scoped role assignment for a user."""

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id"),
        {"schema": None, "extend_existing": True},
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    invited_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    user: Mapped["User"] = relationship(
        "User", foreign_keys=[user_id], back_populates="memberships"
    )
    inviter: Mapped["User | None"] = relationship("User", foreign_keys=[invited_by])


class Invitation(Base):
    """Single-use, time-limited invitation token for tenant membership."""

    __tablename__ = "invitations"
    __table_args__ = ({"schema": None, "extend_existing": True},)

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    invited_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    inviter: Mapped["User | None"] = relationship("User", foreign_keys=[invited_by])


class ApiKey(Base):
    """Hashed API key for programmatic access. Secret shown once, never stored."""

    __tablename__ = "api_keys"
    __table_args__ = ({"schema": None, "extend_existing": True},)

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,  # NULL = system key
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    user: Mapped["User | None"] = relationship("User", back_populates="api_keys")
