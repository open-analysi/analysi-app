"""
Knowledge Module model - Database-backed skills and reusable knowledge containers.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analysi.db.base import Base

if TYPE_CHECKING:
    from .component import Component


from analysi.constants import ModuleTypeConstants

ModuleType = ModuleTypeConstants


class KnowledgeModule(Base):
    """
    Knowledge Module - a container for reusable knowledge content.

    Currently supports 'skill' type modules which contain documents
    organized by namespace paths. Modules can include other modules
    and declare dependencies for composition.

    Relationships:
    - 'contains' edges link to KUDocument components (with namespace_path in metadata)
    - 'includes' edges link to other KnowledgeModules (content inheritance)
    - 'depends_on' edges link to other KnowledgeModules (capability dependencies)
    """

    __tablename__ = "knowledge_modules"

    # Own primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )

    # Foreign key to component table
    component_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # Module type discriminator
    module_type: Mapped[str] = mapped_column(
        Enum("skill", name="module_type", create_type=False),
        nullable=False,
        default=ModuleType.SKILL,
        index=True,
    )

    # Root document path within the module namespace
    root_document_path: Mapped[str] = mapped_column(
        String(255), nullable=False, default="SKILL.md"
    )

    # Module-specific configuration
    # For skills: triggers, model preferences, etc.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Relationship to component
    component: Mapped["Component"] = relationship(
        "Component", back_populates="knowledge_module"
    )

    def __repr__(self) -> str:
        return f"<KnowledgeModule(id={self.id}, type={self.module_type}, root={self.root_document_path})>"
