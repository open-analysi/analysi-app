"""
Component base model - Base class for all components (Tasks and KUs).
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .kdg_edge import KDGEdge
    from .knowledge_module import KnowledgeModule
    from .knowledge_unit import KnowledgeUnit
    from .task import Task
from uuid import UUID

from sqlalchemy import ARRAY, Boolean, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analysi.constants import ComponentConstants
from analysi.db.base import Base

ComponentKind = ComponentConstants.Kind
ComponentStatus = ComponentConstants.Status


class Component(Base):
    """
    Base table for all components (Knowledge Units and Tasks) using class table inheritance.

    This is the parent class that provides common fields for all components.
    Task and KnowledgeUnit models inherit from this.
    """

    __tablename__ = "components"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # Multi-tenancy
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Component discriminator
    kind: Mapped[str] = mapped_column(
        Enum("ku", "task", "module", name="component_kind", create_constraint=False),
        nullable=False,
        index=True,
    )

    # Namespace for scoping KUs (e.g., skill cy_name for skill-owned documents)
    namespace: Mapped[str] = mapped_column(String(512), nullable=False, default="/")

    # Basic metadata
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0.0")

    # KU type for unique constraint
    # Only populated for KUs, NULL for tasks
    ku_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Script-friendly identifier for Cy language references
    # Follows function naming rules: ^[a-zA-Z_][a-zA-Z0-9_]*$
    cy_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Status and visibility
    status: Mapped[str] = mapped_column(
        Enum("enabled", "disabled", name="component_status", create_constraint=False),
        nullable=False,
        default=ComponentStatus.ENABLED,
        index=True,
    )
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    system_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Organization
    app: Mapped[str] = mapped_column(
        String(100), nullable=False, default="default", index=True
    )
    categories: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)

    # Authoring information (UUID FK to users table)
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        server_default="00000000-0000-0000-0000-000000000001",
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Component type relationships
    task: Mapped[Optional["Task"]] = relationship(
        "Task", back_populates="component", uselist=False, cascade="all, delete-orphan"
    )
    knowledge_unit: Mapped[Optional["KnowledgeUnit"]] = relationship(
        "KnowledgeUnit",
        back_populates="component",
        uselist=False,
        cascade="all, delete-orphan",
    )
    knowledge_module: Mapped[Optional["KnowledgeModule"]] = relationship(
        "KnowledgeModule",
        back_populates="component",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # KDG relationships
    outgoing_edges: Mapped[list["KDGEdge"]] = relationship(
        "KDGEdge",
        foreign_keys="KDGEdge.source_id",
        back_populates="source_component",
        lazy="select",
        cascade="all, delete-orphan",
    )
    incoming_edges: Mapped[list["KDGEdge"]] = relationship(
        "KDGEdge",
        foreign_keys="KDGEdge.target_id",
        back_populates="target_component",
        lazy="select",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Component(id={self.id}, kind={self.kind}, name={self.name!r})>"
