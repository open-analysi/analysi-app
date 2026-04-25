"""
Service layer for Activity Audit Trail operations.
"""

from datetime import datetime
from uuid import UUID

from analysi.repositories.activity_audit_repository import ActivityAuditRepository
from analysi.schemas.activity_audit import (
    ActivityAuditCreate,
    ActivityAuditResponse,
)


class ActivityAuditService:
    """Service for activity audit trail operations."""

    def __init__(self, repository: ActivityAuditRepository):
        self.repository = repository

    async def record_activity(
        self,
        tenant_id: str,
        data: ActivityAuditCreate,
    ) -> ActivityAuditResponse:
        """Record a new activity audit event."""
        event = await self.repository.create(
            tenant_id=tenant_id,
            actor_id=data.actor_id,
            actor_type=data.actor_type.value,
            source=data.source.value,
            action=data.action,
            resource_type=data.resource_type,
            resource_id=data.resource_id,
            details=data.details,
            ip_address=data.ip_address,
            user_agent=data.user_agent,
            request_id=data.request_id,
        )

        return ActivityAuditResponse.model_validate(event)

    async def get_activity(
        self,
        tenant_id: str,
        event_id: UUID,
        created_at: datetime | None = None,
    ) -> ActivityAuditResponse | None:
        """Get an activity event by ID."""
        event = await self.repository.get_by_id(
            tenant_id=tenant_id,
            event_id=event_id,
            created_at=created_at,
        )

        if not event:
            return None

        return ActivityAuditResponse.model_validate(event)

    async def list_activities(
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
    ) -> tuple[list[ActivityAuditResponse], int]:
        """List activity events with filters and pagination.

        Returns (items, total) tuple for the router to wrap in api_list_response.
        """
        events = await self.repository.list_events(
            tenant_id=tenant_id,
            actor_id=actor_id,
            source=source,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            from_date=from_date,
            to_date=to_date,
            offset=offset,
            limit=limit,
        )

        total = await self.repository.count_events(
            tenant_id=tenant_id,
            actor_id=actor_id,
            source=source,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            from_date=from_date,
            to_date=to_date,
        )

        return [ActivityAuditResponse.model_validate(e) for e in events], total
