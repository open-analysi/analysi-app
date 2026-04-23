"""
Knowledge Unit models - Tables, Documents, Tools, and Indexes.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analysi.constants import KUTypeConstants
from analysi.db.base import Base

from .component import Component

KUType = KUTypeConstants


class KnowledgeUnit(Base):
    """
    Intermediate table for Knowledge Units with type discriminator.

    This sits between Component and the specific KU subtypes.
    """

    __tablename__ = "knowledge_units"

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

    # KU type discriminator
    ku_type: Mapped[str] = mapped_column(
        Enum(
            "table",
            "document",
            "tool",
            "index",
            name="ku_type",
            create_constraint=False,
        ),
        nullable=False,
        index=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Relationship to component
    component: Mapped["Component"] = relationship(
        "Component", back_populates="knowledge_unit"
    )

    # Relationships to KU subtypes (via component_id)
    ku_table: Mapped[Optional["KUTable"]] = relationship(
        "KUTable",
        primaryjoin="KnowledgeUnit.component_id == foreign(KUTable.component_id)",
        uselist=False,
        cascade="all, delete-orphan",
    )
    ku_document: Mapped[Optional["KUDocument"]] = relationship(
        "KUDocument",
        primaryjoin="KnowledgeUnit.component_id == foreign(KUDocument.component_id)",
        uselist=False,
        cascade="all, delete-orphan",
    )
    ku_tool: Mapped[Optional["KUTool"]] = relationship(
        "KUTool",
        primaryjoin="KnowledgeUnit.component_id == foreign(KUTool.component_id)",
        uselist=False,
        cascade="all, delete-orphan",
    )
    ku_index: Mapped[Optional["KUIndex"]] = relationship(
        "KUIndex",
        primaryjoin="KnowledgeUnit.component_id == foreign(KUIndex.component_id)",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<KnowledgeUnit(id={self.id}, ku_type={self.ku_type})>"


class KUTable(Base):
    """
    Knowledge Unit Table subtype for structured tabular data.
    """

    __tablename__ = "ku_tables"

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

    # Table-specific fields
    schema: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    column_count: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    file_path: Mapped[str | None] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Relationship to component (via Component, not KnowledgeUnit)
    component: Mapped["Component"] = relationship("Component", overlaps="ku_table")

    def __repr__(self) -> str:
        return (
            f"<KUTable(id={self.id}, rows={self.row_count}, cols={self.column_count})>"
        )


class KUDocument(Base):
    """
    Knowledge Unit Document subtype for unstructured text content.
    """

    __tablename__ = "ku_documents"

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

    # Document-specific fields
    doc_format: Mapped[str] = mapped_column(String(50), default="raw")
    content: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)
    markdown_content: Mapped[str | None] = mapped_column(Text)
    document_type: Mapped[str | None] = mapped_column(String(50))
    content_source: Mapped[str | None] = mapped_column(String(50))
    source_url: Mapped[str | None] = mapped_column(Text)
    doc_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict
    )
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    character_count: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str | None] = mapped_column(String(10))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Relationship to component
    component: Mapped["Component"] = relationship("Component", overlaps="ku_document")

    def __repr__(self) -> str:
        return f"<KUDocument(id={self.id}, type={self.document_type}, words={self.word_count})>"


class KUTool(Base):
    """
    Knowledge Unit Tool subtype for MCP and native tool integrations.
    """

    __tablename__ = "ku_tools"

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

    # Tool-specific fields
    tool_type: Mapped[str] = mapped_column(String(50), nullable=False)
    mcp_endpoint: Mapped[str | None] = mapped_column(Text)
    mcp_server_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    auth_type: Mapped[str] = mapped_column(String(50), default="none")
    credentials_ref: Mapped[str | None] = mapped_column(Text)
    timeout_ms: Mapped[int] = mapped_column(Integer, default=30000)
    rate_limit: Mapped[int] = mapped_column(Integer, default=100)
    integration_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Relationship to component
    component: Mapped["Component"] = relationship("Component", overlaps="ku_tool")

    def __repr__(self) -> str:
        return f"<KUTool(id={self.id}, type={self.tool_type}, endpoint={self.mcp_endpoint})>"


class KUIndex(Base):
    """
    Knowledge Unit Index subtype for semantic search capabilities.
    """

    __tablename__ = "ku_indexes"

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

    # Index-specific fields
    index_type: Mapped[str] = mapped_column(
        Enum("vector", "fulltext", "hybrid", name="ku_index_type", create_type=False),
        default="vector",
    )
    vector_database: Mapped[str | None] = mapped_column(String(100))
    embedding_model: Mapped[str | None] = mapped_column(String(255))
    # Project Paros: embedding dimensions and backend type for pluggable index
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    backend_type: Mapped[str | None] = mapped_column(String(50), default="pgvector")
    chunking_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    build_status: Mapped[str] = mapped_column(
        Enum(
            "pending",
            "building",
            "completed",
            "failed",
            "outdated",
            name="index_build_status",
            create_type=False,
        ),
        default="pending",
    )
    build_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    build_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    build_error_message: Mapped[str | None] = mapped_column(Text)
    index_stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    # Relationship to component
    component: Mapped["Component"] = relationship("Component", overlaps="ku_index")

    def __repr__(self) -> str:
        return f"<KUIndex(id={self.id}, type={self.index_type}, status={self.build_status})>"
