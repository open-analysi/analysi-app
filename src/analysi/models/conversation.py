"""SQLAlchemy models for product chatbot."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from analysi.db.base import Base


class Conversation(Base):
    """Per-tenant, per-user conversation session.

    Not partitioned (low volume). Soft-delete via deleted_at.
    All queries MUST filter by user_id AND deleted_at IS NULL.
    """

    __tablename__ = "chat_conversations"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(Text)
    page_context: Mapped[dict | None] = mapped_column(JSONB)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    token_count_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=lambda: datetime.now(UTC),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships — order_by ensures chronological message order when
    # eager-loaded via selectinload (critical for partitioned chat_messages table
    # where PostgreSQL does NOT guarantee row order without ORDER BY)
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    __table_args__ = (
        Index(
            "idx_conversations_tenant_user",
            "tenant_id",
            "user_id",
            "updated_at",
            postgresql_where=deleted_at.is_(None),
        ),
        Index(
            "idx_conversations_tenant_id",
            "tenant_id",
            "id",
            postgresql_where=deleted_at.is_(None),
        ),
    )

    def soft_delete(self) -> None:
        """Mark conversation as deleted (hidden from list, kept for audit)."""
        self.deleted_at = datetime.now(UTC)


class ChatMessage(Base):
    """Individual chat message turn.

    Monthly-partitioned by created_at. 90-day retention via pg_partman.
    """

    __tablename__ = "chat_messages"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, server_default=func.gen_random_uuid()
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chat_conversations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # user, assistant, system, tool
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    tool_calls: Mapped[dict | None] = mapped_column(JSONB)
    token_count: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", "created_at"),
        Index("idx_chat_messages_conversation", "conversation_id", "created_at"),
        Index("idx_chat_messages_tenant", "tenant_id", "created_at"),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )
