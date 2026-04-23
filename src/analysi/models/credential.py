"""
SQLAlchemy models for credentials system.

Following CustomerCredentials spec for field names and relationships.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analysi.db.base import Base


class Credential(Base):
    """
    Credential model storing encrypted secrets.

    Maps to CustomerCredentials spec with provider/account fields.
    """

    __tablename__ = "credentials"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", "account"),
        {"schema": None, "extend_existing": True},
    )

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # Tenant and uniqueness fields
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # Maps to integration_type
    account: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # Credential label

    # Encryption fields
    ciphertext: Mapped[str] = mapped_column(
        String, nullable=False
    )  # Vault-encrypted JSON
    credential_metadata: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # Unencrypted metadata
    key_name: Mapped[str] = mapped_column(
        String(255), nullable=False, server_default="tenant-default"
    )
    key_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1"
    )

    # Standard fields (UUID FK to users table)
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationship to integrations through junction table
    integrations: Mapped[list["IntegrationCredential"]] = relationship(
        "IntegrationCredential",
        back_populates="credential",
        cascade="all, delete-orphan",
    )


class IntegrationCredential(Base):
    """
    Junction table linking integrations to credentials.

    Supports many-to-many with additional fields.
    """

    __tablename__ = "integration_credentials"
    __table_args__ = ({"schema": None, "extend_existing": True},)

    # Composite primary key
    tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    integration_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    credential_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("credentials.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Additional fields
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    purpose: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # read/write/admin
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Relationships
    credential: Mapped["Credential"] = relationship(
        "Credential", back_populates="integrations"
    )
