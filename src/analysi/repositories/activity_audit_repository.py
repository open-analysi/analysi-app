"""
Repository for Activity Audit Trail operations.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.activity_audit import ActivityAuditTrail


class ActivityAuditRepository:
    """Repository for activity audit trail operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        tenant_id: str,
        actor_id: UUID,
        action: str,
        actor_type: str = "user",
        source: str = "unknown",
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> ActivityAuditTrail:
        """Create a new activity audit event."""
        now = datetime.now(UTC)

        event = ActivityAuditTrail(
            id=uuid4(),
            created_at=now,
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_type=actor_type,
            source=source,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )

        self.session.add(event)
        await self.session.flush()

        return event

    async def get_by_id(
        self,
        tenant_id: str,
        event_id: UUID,
        created_at: datetime | None = None,
    ) -> ActivityAuditTrail | None:
        """Get an event by ID.

        Note: For partitioned tables, providing created_at improves performance.
        """
        conditions = [
            ActivityAuditTrail.tenant_id == tenant_id,
            ActivityAuditTrail.id == event_id,
        ]

        if created_at:
            conditions.append(ActivityAuditTrail.created_at == created_at)

        stmt = select(ActivityAuditTrail).where(and_(*conditions))
        result = await self.session.execute(stmt)

        return result.scalar_one_or_none()

    async def list_events(
        self,
        tenant_id: str,
        actor_id: UUID | None = None,
        source: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[ActivityAuditTrail]:
        """List events with filters."""
        conditions = [ActivityAuditTrail.tenant_id == tenant_id]

        if actor_id:
            conditions.append(ActivityAuditTrail.actor_id == actor_id)
        if source:
            conditions.append(ActivityAuditTrail.source == source)
        if action:
            # Support prefix matching with LIKE if action contains %
            if "%" in action:
                conditions.append(ActivityAuditTrail.action.like(action))
            else:
                conditions.append(ActivityAuditTrail.action == action)
        if resource_type:
            conditions.append(ActivityAuditTrail.resource_type == resource_type)
        if resource_id:
            conditions.append(ActivityAuditTrail.resource_id == resource_id)
        if from_date:
            conditions.append(ActivityAuditTrail.created_at >= from_date)
        if to_date:
            conditions.append(ActivityAuditTrail.created_at < to_date)

        stmt = (
            select(ActivityAuditTrail)
            .where(and_(*conditions))
            .order_by(desc(ActivityAuditTrail.created_at))
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_events(
        self,
        tenant_id: str,
        actor_id: UUID | None = None,
        source: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> int:
        """Count events with filters."""
        conditions = [ActivityAuditTrail.tenant_id == tenant_id]

        if actor_id:
            conditions.append(ActivityAuditTrail.actor_id == actor_id)
        if source:
            conditions.append(ActivityAuditTrail.source == source)
        if action:
            if "%" in action:
                conditions.append(ActivityAuditTrail.action.like(action))
            else:
                conditions.append(ActivityAuditTrail.action == action)
        if resource_type:
            conditions.append(ActivityAuditTrail.resource_type == resource_type)
        if resource_id:
            conditions.append(ActivityAuditTrail.resource_id == resource_id)
        if from_date:
            conditions.append(ActivityAuditTrail.created_at >= from_date)
        if to_date:
            conditions.append(ActivityAuditTrail.created_at < to_date)

        stmt = select(func.count(ActivityAuditTrail.id)).where(and_(*conditions))

        result = await self.session.execute(stmt)
        return result.scalar() or 0
