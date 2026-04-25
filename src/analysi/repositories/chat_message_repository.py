"""Repository for ChatMessage database operations."""

from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.conversation import ChatMessage


class ChatMessageRepository:
    """Repository for chat message persistence.

    Messages belong to conversations; ownership is enforced at the
    conversation level (the router checks conversation ownership before
    listing messages).
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        conversation_id: UUID,
        tenant_id: str,
        role: str,
        content: Any,
        tool_calls: Any | None = None,
        token_count: int | None = None,
        model: str | None = None,
        latency_ms: int | None = None,
    ) -> ChatMessage:
        """Create a new chat message."""
        message = ChatMessage(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            token_count=token_count,
            model=model,
            latency_ms=latency_ms,
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def list_by_conversation(
        self,
        conversation_id: UUID,
        tenant_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ChatMessage], int]:
        """List messages for a conversation, chronological order (oldest first).

        Returns (items, total) tuple. For paginated UI display.
        """
        conditions = and_(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.tenant_id == tenant_id,
        )

        # Count query
        count_stmt = select(func.count()).select_from(ChatMessage).where(conditions)
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Data query — chronological order (oldest first)
        stmt = (
            select(ChatMessage)
            .where(conditions)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def list_recent_by_conversation(
        self,
        conversation_id: UUID,
        tenant_id: str,
        limit: int = 50,
    ) -> list[ChatMessage]:
        """Fetch the most recent N messages in chronological order.

        Used for LLM context building: returns the NEWEST messages (not oldest)
        so the agent has the most relevant recent conversation context.

        Uses a subquery to select the newest N messages (DESC), then re-orders
        them chronologically (ASC) for correct LLM history sequencing.
        """
        conditions = and_(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.tenant_id == tenant_id,
        )

        # Subquery: select newest N messages
        newest_subq = (
            select(ChatMessage.id, ChatMessage.created_at)
            .where(conditions)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        ).subquery()

        # Outer query: re-order chronologically
        stmt = (
            select(ChatMessage)
            .join(
                newest_subq,
                and_(
                    ChatMessage.id == newest_subq.c.id,
                    ChatMessage.created_at == newest_subq.c.created_at,
                ),
            )
            .order_by(ChatMessage.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
