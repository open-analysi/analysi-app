"""
Repository for Checkpoint operations.

Project Symi: Cross-run cursor state for Tasks and Workflows.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.models.checkpoint import Checkpoint

logger = get_logger(__name__)


class CheckpointRepository:
    """Repository for checkpoint get/upsert/delete."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(
        self,
        tenant_id: str,
        owner_id: UUID,
        key: str,
        owner_type: str = "task",
    ) -> Any | None:
        """Get a checkpoint value. Returns the JSONB value or None."""
        stmt = select(Checkpoint.value).where(
            and_(
                Checkpoint.tenant_id == tenant_id,
                Checkpoint.owner_type == owner_type,
                Checkpoint.owner_id == owner_id,
                Checkpoint.key == key,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        tenant_id: str,
        owner_id: UUID,
        key: str,
        value: Any,
        owner_type: str = "task",
    ) -> Checkpoint:
        """Create or update a checkpoint. Uses INSERT ... ON CONFLICT UPDATE."""
        now = datetime.now(UTC)
        stmt = (
            pg_insert(Checkpoint)
            .values(
                id=uuid4(),
                tenant_id=tenant_id,
                owner_type=owner_type,
                owner_id=owner_id,
                key=key,
                value=value,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["tenant_id", "owner_type", "owner_id", "key"],
                set_={"value": value, "updated_at": now},
            )
            .returning(Checkpoint)
        )
        result = await self.session.execute(stmt)
        checkpoint = result.scalar_one()
        await self.session.flush()
        return checkpoint

    async def delete_by_owner(
        self,
        tenant_id: str,
        owner_id: UUID,
        owner_type: str = "task",
    ) -> int:
        """Delete all checkpoints for an owner. Returns count of deleted rows."""
        stmt = delete(Checkpoint).where(
            and_(
                Checkpoint.tenant_id == tenant_id,
                Checkpoint.owner_type == owner_type,
                Checkpoint.owner_id == owner_id,
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount
