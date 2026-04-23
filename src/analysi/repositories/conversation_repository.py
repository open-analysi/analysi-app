"""Repository for Conversation database operations."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, literal, select, update
from sqlalchemy.dialects.postgresql import JSONB as JSONB_TYPE
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from analysi.models.conversation import Conversation


class ConversationRepository:
    """Repository for conversation CRUD with ownership enforcement.

    Every query filters by user_id AND deleted_at IS NULL to enforce
    per-user isolation. A user cannot access another user's conversation.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        tenant_id: str,
        user_id: UUID,
        title: str | None = None,
        page_context: dict | None = None,
    ) -> Conversation:
        """Create a new conversation."""
        conversation = Conversation(
            tenant_id=tenant_id,
            user_id=user_id,
            title=title,
            page_context=page_context,
        )
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get_by_id(
        self,
        conversation_id: UUID,
        tenant_id: str,
        user_id: UUID,
    ) -> Conversation | None:
        """Get a conversation by ID with ownership enforcement."""
        stmt = select(Conversation).where(
            and_(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
                Conversation.user_id == user_id,
                Conversation.deleted_at.is_(None),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_with_messages(
        self,
        conversation_id: UUID,
        tenant_id: str,
        user_id: UUID,
    ) -> Conversation | None:
        """Get a conversation with its messages (eager-loaded)."""
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.tenant_id == tenant_id,
                    Conversation.user_id == user_id,
                    Conversation.deleted_at.is_(None),
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        tenant_id: str,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Conversation], int]:
        """List conversations for a user with pagination.

        Returns (items, total) tuple.
        """
        conditions = and_(
            Conversation.tenant_id == tenant_id,
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        )

        # Count query
        count_stmt = select(func.count()).select_from(Conversation).where(conditions)
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Data query
        stmt = (
            select(Conversation)
            .where(conditions)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def update_title(
        self,
        conversation_id: UUID,
        tenant_id: str,
        user_id: UUID,
        title: str,
    ) -> Conversation | None:
        """Update conversation title with ownership enforcement."""
        conversation = await self.get_by_id(conversation_id, tenant_id, user_id)
        if conversation is None:
            return None
        conversation.title = title
        conversation.updated_at = datetime.now(UTC)
        await self.session.flush()
        return conversation

    async def soft_delete(
        self,
        conversation_id: UUID,
        tenant_id: str,
        user_id: UUID,
    ) -> bool:
        """Soft-delete a conversation with ownership enforcement.

        Returns True if deleted, False if not found.
        """
        conversation = await self.get_by_id(conversation_id, tenant_id, user_id)
        if conversation is None:
            return False
        conversation.soft_delete()
        await self.session.flush()
        return True

    async def increment_token_count(
        self,
        conversation_id: UUID,
        tenant_id: str,
        token_count: int,
    ) -> None:
        """Increment the lifetime token count for a conversation.

        Filters by tenant_id for defense-in-depth consistency with other
        repository methods.
        """
        stmt = (
            update(Conversation)
            .where(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.tenant_id == tenant_id,
                )
            )
            .values(
                token_count_total=Conversation.token_count_total + token_count,
                updated_at=datetime.now(UTC),
            )
        )
        await self.session.execute(stmt)

    async def update_loaded_skills(
        self,
        conversation_id: UUID,
        tenant_id: str,
        skill_names: list[str],
    ) -> None:
        """Update the list of pinned skills in conversation metadata.

        Uses JSONB concat (||) to merge loaded_skills into the existing metadata
        without overwriting other metadata fields.
        """
        await self.update_metadata_field(
            conversation_id, tenant_id, "loaded_skills", skill_names
        )

    async def update_metadata_field(
        self,
        conversation_id: UUID,
        tenant_id: str,
        field_name: str,
        value: object,
    ) -> None:
        """Update a single field in conversation JSONB metadata.

        Uses JSONB concat (||) to merge the field into existing metadata
        without overwriting other fields. Passing None as value still sets
        the key (to JSON null), which is useful for clearing pending_action.
        """
        stmt = (
            update(Conversation)
            .where(
                and_(
                    Conversation.id == conversation_id,
                    Conversation.tenant_id == tenant_id,
                )
            )
            .values(
                metadata_=func.coalesce(
                    Conversation.metadata_, literal({}, type_=JSONB_TYPE)
                ).concat(literal({field_name: value}, type_=JSONB_TYPE)),
                updated_at=datetime.now(UTC),
            )
        )
        await self.session.execute(stmt)
