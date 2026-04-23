"""
Knowledge Dependency Graph Edge model for relationship management.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analysi.constants import EdgeTypeConstants
from analysi.db.base import Base

from .component import Component

EdgeType = EdgeTypeConstants


class KDGEdge(Base):
    """
    Knowledge Dependency Graph edges - unified relationship table.

    Captures relationships between Components (Tasks and KUs).
    """

    __tablename__ = "component_graph_edges"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # Multi-tenancy
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Relationship endpoints
    source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Relationship metadata
    relationship_type: Mapped[str] = mapped_column(
        Enum(
            "uses",
            "generates",
            "updates",
            "calls",
            "transforms_into",
            "summarizes_into",
            "indexes_into",
            "derived_from",
            "enriches",
            "contains",
            "includes",
            "depends_on",
            "references",
            "staged_for",
            "feedback_for",
            name="kdg_relationship_type",
            create_type=False,
        ),
        nullable=False,
        index=True,
    )
    execution_order: Mapped[int] = mapped_column(Integer, default=0)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    edge_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Relationships to components
    source_component: Mapped["Component"] = relationship(
        "Component", foreign_keys=[source_id], back_populates="outgoing_edges"
    )
    target_component: Mapped["Component"] = relationship(
        "Component", foreign_keys=[target_id], back_populates="incoming_edges"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "source_id != target_id",
            name="chk_kdg_edge_different_components",
        ),
        UniqueConstraint(
            "tenant_id",
            "source_id",
            "target_id",
            "relationship_type",
            name="uq_kdg_edge_unique_relationship",
        ),
    )

    def __repr__(self) -> str:
        return f"<KDGEdge(id={self.id}, {self.source_id} --{self.relationship_type}--> {self.target_id})>"
