"""Repositories for control event bus (Project Tilos)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, delete, desc, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.constants import ControlEventConstants
from analysi.models.control_event import (
    ControlEvent,
    ControlEventDispatch,
    ControlEventRule,
)


class ControlEventRepository:
    """Repository for control_events table operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert(
        self,
        tenant_id: str,
        channel: str,
        payload: dict,
    ) -> ControlEvent:
        """Insert a new control event with status='pending'."""
        event = ControlEvent(
            tenant_id=tenant_id,
            channel=channel,
            payload=payload,
            status=ControlEventConstants.Status.PENDING,
            retry_count=0,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_by_id(self, event_id: UUID) -> ControlEvent | None:
        """Fetch a control event by ID (cross-partition scan — acceptable for 2-3 active months)."""
        stmt = select(ControlEvent).where(ControlEvent.id == event_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def claim_batch(
        self,
        batch_size: int = 50,
        max_retries: int = 3,
        stuck_hours: int = 1,
    ) -> list[ControlEvent]:
        """
        Atomically claim a batch of dispatchable events.

        Step 1: Reset events stuck in 'claimed' for > stuck_hours back to 'pending'.
                Handles the case where Valkey was restarted before the ARQ job started.
        Step 2: SELECT FOR UPDATE SKIP LOCKED pending/failed events with
                retry_count < max_retries, mark them 'claimed'.

        Returns the list of newly claimed events.
        """
        stuck_cutoff = datetime.now(UTC) - timedelta(hours=stuck_hours)

        # Step 1: Reset stuck claimed events
        await self.session.execute(
            update(ControlEvent)
            .where(
                and_(
                    ControlEvent.status == ControlEventConstants.Status.CLAIMED,
                    ControlEvent.claimed_at < stuck_cutoff,
                )
            )
            .values(status=ControlEventConstants.Status.PENDING, claimed_at=None)
        )

        # Step 2: Claim pending/failed events
        stmt = (
            select(ControlEvent)
            .where(
                and_(
                    ControlEvent.status.in_(
                        [
                            ControlEventConstants.Status.PENDING,
                            ControlEventConstants.Status.FAILED,
                        ]
                    ),
                    ControlEvent.retry_count < max_retries,
                )
            )
            .with_for_update(skip_locked=True)
            .limit(batch_size)
        )
        result = await self.session.execute(stmt)
        events = list(result.scalars().all())

        if events:
            now = datetime.now(UTC)
            for event in events:
                event.status = ControlEventConstants.Status.CLAIMED
                event.claimed_at = now
            await self.session.flush()

        return events

    async def list_distinct_channels(self, tenant_id: str) -> list[str]:
        """Return distinct channel names used in rules for this tenant."""
        from sqlalchemy import distinct

        stmt = select(distinct(ControlEventRule.channel)).where(
            ControlEventRule.tenant_id == tenant_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_tenant(
        self,
        tenant_id: str,
        channel: str | None = None,
        status: str | None = None,
        limit: int = 50,
        since_days: int = 30,
    ) -> list[ControlEvent]:
        """List recent control events for a tenant, newest first.

        Scoped to the last `since_days` days to avoid full partition scans.
        """
        since = datetime.now(UTC) - timedelta(days=since_days)
        conditions = [
            ControlEvent.tenant_id == tenant_id,
            ControlEvent.created_at >= since,
        ]
        if channel is not None:
            conditions.append(ControlEvent.channel == channel)
        if status is not None:
            conditions.append(ControlEvent.status == status)

        stmt = (
            select(ControlEvent)
            .where(and_(*conditions))
            .order_by(desc(ControlEvent.created_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_completed(self, event: ControlEvent) -> None:
        """Mark event as fully completed (all rules completed)."""
        event.status = ControlEventConstants.Status.COMPLETED
        await self.session.flush()

    async def mark_failed(self, event: ControlEvent) -> None:
        """Mark event as failed and increment retry_count."""
        event.status = ControlEventConstants.Status.FAILED
        event.retry_count += 1
        await self.session.flush()


class ControlEventRuleRepository:
    """Repository for control_event_rules table operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        tenant_id: str,
        channel: str,
        target_type: str,
        target_id: UUID,
        name: str,
        enabled: bool = True,
        config: dict | None = None,
    ) -> ControlEventRule:
        """Create a new control event rule."""
        rule = ControlEventRule(
            tenant_id=tenant_id,
            channel=channel,
            target_type=target_type,
            target_id=target_id,
            name=name,
            enabled=enabled,
            config=config or {},
        )
        self.session.add(rule)
        await self.session.flush()
        return rule

    async def get_by_id(self, tenant_id: str, rule_id: UUID) -> ControlEventRule | None:
        """Get a rule by ID with tenant isolation."""
        stmt = select(ControlEventRule).where(
            and_(
                ControlEventRule.tenant_id == tenant_id,
                ControlEventRule.id == rule_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_channel(
        self,
        tenant_id: str,
        channel: str,
        enabled_only: bool = True,
    ) -> list[ControlEventRule]:
        """List rules for a (tenant, channel) pair, optionally filtered to enabled only."""
        conditions = [
            ControlEventRule.tenant_id == tenant_id,
            ControlEventRule.channel == channel,
        ]
        if enabled_only:
            conditions.append(ControlEventRule.enabled == True)  # noqa: E712

        stmt = select(ControlEventRule).where(and_(*conditions))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_tenant(
        self,
        tenant_id: str,
        channel: str | None = None,
        enabled_only: bool = False,
    ) -> list[ControlEventRule]:
        """List all rules for a tenant, with optional channel and enabled filters."""
        conditions = [ControlEventRule.tenant_id == tenant_id]
        if channel is not None:
            conditions.append(ControlEventRule.channel == channel)
        if enabled_only:
            conditions.append(ControlEventRule.enabled == True)  # noqa: E712

        stmt = (
            select(ControlEventRule)
            .where(and_(*conditions))
            .order_by(ControlEventRule.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        tenant_id: str,
        rule_id: UUID,
        **fields,
    ) -> ControlEventRule | None:
        """Update allowed fields on a rule. Returns None if not found."""
        rule = await self.get_by_id(tenant_id, rule_id)
        if rule is None:
            return None

        allowed = {"name", "enabled", "target_type", "target_id", "config"}
        for key, value in fields.items():
            if key in allowed:
                setattr(rule, key, value)

        rule.updated_at = datetime.now(UTC)
        await self.session.flush()
        return rule

    async def delete(self, tenant_id: str, rule_id: UUID) -> bool:
        """Delete a rule by ID. Returns True if deleted, False if not found."""
        rule = await self.get_by_id(tenant_id, rule_id)
        if rule is None:
            return False

        await self.session.delete(rule)
        await self.session.flush()
        return True


class ControlEventDispatchRepository:
    """Repository for control_event_dispatches table operations."""

    # Atomic upsert: INSERT on new row, UPDATE to 'running' only if currently 'failed'.
    # Returns the dispatch id when the caller should proceed, nothing when it should skip.
    _CLAIM_SQL = text(
        """
        INSERT INTO control_event_dispatches (control_event_id, rule_id, status)
        VALUES (:event_id, :rule_id, 'running')
        ON CONFLICT (control_event_id, rule_id) DO UPDATE
            SET status = 'running',
                attempt_number = control_event_dispatches.attempt_number + 1,
                updated_at = NOW()
            WHERE control_event_dispatches.status = 'failed'
        RETURNING id
    """
    )

    def __init__(self, session: AsyncSession):
        self.session = session

    async def claim_or_skip(self, control_event_id: UUID, rule_id: UUID) -> UUID | None:
        """
        Atomically claim a dispatch slot or skip if already handled.

        Returns:
            dispatch id (UUID) if the caller should execute the rule
            None if the rule was already completed or is currently running elsewhere
        """
        result = await self.session.execute(
            self._CLAIM_SQL,
            {"event_id": control_event_id, "rule_id": rule_id},
        )
        row = result.fetchone()
        return row.id if row else None

    async def mark_completed(self, dispatch_id: UUID) -> None:
        """Mark a dispatch as completed."""
        await self.session.execute(
            update(ControlEventDispatch)
            .where(ControlEventDispatch.id == dispatch_id)
            .values(
                status=ControlEventConstants.Status.COMPLETED,
                updated_at=datetime.now(UTC),
            )
        )

    async def mark_failed(self, dispatch_id: UUID) -> None:
        """Mark a dispatch as failed."""
        await self.session.execute(
            update(ControlEventDispatch)
            .where(ControlEventDispatch.id == dispatch_id)
            .values(
                status=ControlEventConstants.Status.FAILED, updated_at=datetime.now(UTC)
            )
        )

    async def delete_for_event(self, control_event_id: UUID) -> int:
        """
        Delete all dispatch rows for a control event.

        Called atomically with mark_completed() when an event completes
        successfully — keeps the table lean.
        """
        result = await self.session.execute(
            delete(ControlEventDispatch).where(
                ControlEventDispatch.control_event_id == control_event_id
            )
        )
        return result.rowcount
