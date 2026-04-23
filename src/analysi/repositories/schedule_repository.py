"""
Repository for Schedule operations.

Project Symi: Generic scheduler CRUD and due-schedule polling.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.models.schedule import Schedule

logger = get_logger(__name__)


class ScheduleRepository:
    """Repository for schedule CRUD and due-schedule polling."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        tenant_id: str,
        target_type: str,
        target_id: UUID,
        schedule_type: str,
        schedule_value: str,
        *,
        timezone: str = "UTC",
        enabled: bool = False,
        params: dict[str, Any] | None = None,
        origin_type: str = "user",
        integration_id: str | None = None,
        next_run_at: datetime | None = None,
    ) -> Schedule:
        """Create a new schedule."""
        now = datetime.now(UTC)
        schedule = Schedule(
            id=uuid4(),
            tenant_id=tenant_id,
            target_type=target_type,
            target_id=target_id,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
            timezone=timezone,
            enabled=enabled,
            params=params,
            origin_type=origin_type,
            integration_id=integration_id,
            next_run_at=next_run_at,
            created_at=now,
            updated_at=now,
        )
        self.session.add(schedule)
        await self.session.flush()
        return schedule

    async def get(self, tenant_id: str, schedule_id: UUID) -> Schedule | None:
        """Get a schedule by ID scoped to tenant."""
        stmt = select(Schedule).where(
            and_(Schedule.tenant_id == tenant_id, Schedule.id == schedule_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: str,
        *,
        target_type: str | None = None,
        integration_id: str | None = None,
        origin_type: str | None = None,
        enabled: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Schedule]:
        """List schedules for a tenant with optional filters."""
        conditions = [Schedule.tenant_id == tenant_id]

        if target_type is not None:
            conditions.append(Schedule.target_type == target_type)
        if integration_id is not None:
            conditions.append(Schedule.integration_id == integration_id)
        if origin_type is not None:
            conditions.append(Schedule.origin_type == origin_type)
        if enabled is not None:
            conditions.append(Schedule.enabled == enabled)

        stmt = (
            select(Schedule)
            .where(and_(*conditions))
            .order_by(Schedule.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # Fields that callers are allowed to update
    _UPDATABLE_FIELDS = frozenset(
        {
            "schedule_value",
            "timezone",
            "enabled",
            "params",
            "origin_type",
            "integration_id",
            "next_run_at",
            "last_run_at",
        }
    )

    async def update(
        self, tenant_id: str, schedule_id: UUID, **fields: Any
    ) -> Schedule | None:
        """Update schedule fields. Returns None if not found."""
        schedule = await self.get(tenant_id, schedule_id)
        if schedule is None:
            return None

        for key, value in fields.items():
            if key in self._UPDATABLE_FIELDS:
                setattr(schedule, key, value)

        await self.session.flush()
        return schedule

    async def delete(self, tenant_id: str, schedule_id: UUID) -> bool:
        """Delete a schedule. Returns True if deleted."""
        stmt = (
            delete(Schedule)
            .where(and_(Schedule.tenant_id == tenant_id, Schedule.id == schedule_id))
            .returning(Schedule.id)
        )
        result = await self.session.execute(stmt)
        deleted = result.scalar_one_or_none()
        await self.session.flush()
        return deleted is not None

    async def get_by_target(
        self, tenant_id: str, target_type: str, target_id: UUID
    ) -> Schedule | None:
        """Get schedule by target (task or workflow). Returns first match.

        Used by convenience endpoints to enforce 1:1 task/workflow <-> schedule.
        Uses scalars().first() instead of scalar_one_or_none() to avoid
        MultipleResultsFound if multiple schedules exist for the same target
        (possible via the generic API).
        """
        stmt = select(Schedule).where(
            and_(
                Schedule.tenant_id == tenant_id,
                Schedule.target_type == target_type,
                Schedule.target_id == target_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_due_schedules(
        self,
        limit: int = 100,
        exclude_ids: set[UUID] | None = None,
    ) -> list[Schedule]:
        """Get schedules that are due to run.

        Uses FOR UPDATE SKIP LOCKED to prevent duplicate processing
        by concurrent workers.

        Args:
            limit: Maximum number of schedules to return.
            exclude_ids: Schedule IDs to skip (e.g. already-failed this cycle).
        """
        now = datetime.now(UTC)
        conditions = [
            Schedule.enabled == True,  # noqa: E712
            Schedule.next_run_at <= now,
        ]
        if exclude_ids:
            conditions.append(Schedule.id.notin_(exclude_ids))

        stmt = (
            select(Schedule)
            .where(and_(*conditions))
            .order_by(Schedule.next_run_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_next_run_at(
        self,
        schedule_id: UUID,
        next_run_at: datetime,
        last_run_at: datetime | None = None,
    ) -> None:
        """Update the next_run_at (and optionally last_run_at) after a schedule fires."""
        values: dict[str, Any] = {"next_run_at": next_run_at}
        if last_run_at is not None:
            values["last_run_at"] = last_run_at

        stmt = update(Schedule).where(Schedule.id == schedule_id).values(**values)
        await self.session.execute(stmt)
        await self.session.flush()
