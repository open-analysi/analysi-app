"""Unit tests for Activity Audit Service."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from analysi.models.activity_audit import ActivityAuditTrail
from analysi.models.auth import SYSTEM_USER_ID
from analysi.repositories.activity_audit_repository import ActivityAuditRepository
from analysi.schemas.activity_audit import (
    ActivityAuditCreate,
    ActorType,
)
from analysi.services.activity_audit_service import ActivityAuditService


@pytest.fixture
def mock_repository() -> AsyncMock:
    """Create a mock repository."""
    return AsyncMock(spec=ActivityAuditRepository)


@pytest.fixture
def service(mock_repository: AsyncMock) -> ActivityAuditService:
    """Create service with mock repository."""
    return ActivityAuditService(mock_repository)


@pytest.fixture
def sample_event() -> ActivityAuditTrail:
    """Create a sample event model."""
    return ActivityAuditTrail(
        id=uuid4(),
        created_at=datetime.now(UTC),
        tenant_id="test-tenant",
        actor_id=SYSTEM_USER_ID,
        actor_type="user",
        source="rest_api",
        action="workflow.execute",
        resource_type="workflow",
        resource_id="wf-123",
        details={"workflow_name": "Test Workflow"},
        ip_address="192.168.1.1",
        user_agent="Mozilla/5.0",
        request_id="req-123",
    )


class TestActivityAuditService:
    """Unit tests for ActivityAuditService."""

    @pytest.mark.asyncio
    async def test_record_activity_success(
        self,
        service: ActivityAuditService,
        mock_repository: AsyncMock,
        sample_event: ActivityAuditTrail,
    ):
        """Test recording a new activity event."""
        mock_repository.create.return_value = sample_event

        data = ActivityAuditCreate(
            actor_id=SYSTEM_USER_ID,
            actor_type=ActorType.USER,
            action="workflow.execute",
            resource_type="workflow",
            resource_id="wf-123",
            details={"workflow_name": "Test Workflow"},
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            request_id="req-123",
        )

        result = await service.record_activity("test-tenant", data)

        mock_repository.create.assert_called_once_with(
            tenant_id="test-tenant",
            actor_id=SYSTEM_USER_ID,
            actor_type="user",
            source="unknown",
            action="workflow.execute",
            resource_type="workflow",
            resource_id="wf-123",
            details={"workflow_name": "Test Workflow"},
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            request_id="req-123",
        )

        assert result.actor_id == SYSTEM_USER_ID
        assert result.action == "workflow.execute"

    @pytest.mark.asyncio
    async def test_record_activity_minimal(
        self,
        service: ActivityAuditService,
        mock_repository: AsyncMock,
    ):
        """Test recording activity with minimal fields."""
        event = ActivityAuditTrail(
            id=uuid4(),
            created_at=datetime.now(UTC),
            tenant_id="test-tenant",
            actor_id=SYSTEM_USER_ID,
            actor_type="user",
            source="unknown",
            action="page.view",
            resource_type=None,
            resource_id=None,
            details=None,
            ip_address=None,
            user_agent=None,
            request_id=None,
        )
        mock_repository.create.return_value = event

        data = ActivityAuditCreate(
            actor_id=SYSTEM_USER_ID,
            action="page.view",
        )

        result = await service.record_activity("test-tenant", data)

        assert result.actor_id == SYSTEM_USER_ID
        assert result.action == "page.view"
        assert result.resource_type is None

    @pytest.mark.asyncio
    async def test_get_activity_found(
        self,
        service: ActivityAuditService,
        mock_repository: AsyncMock,
        sample_event: ActivityAuditTrail,
    ):
        """Test getting an existing activity."""
        mock_repository.get_by_id.return_value = sample_event

        result = await service.get_activity("test-tenant", sample_event.id)

        mock_repository.get_by_id.assert_called_once_with(
            tenant_id="test-tenant",
            event_id=sample_event.id,
            created_at=None,
        )
        assert result is not None
        assert result.id == sample_event.id

    @pytest.mark.asyncio
    async def test_get_activity_not_found(
        self,
        service: ActivityAuditService,
        mock_repository: AsyncMock,
    ):
        """Test getting a non-existent activity."""
        mock_repository.get_by_id.return_value = None

        result = await service.get_activity("test-tenant", uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_activity_with_created_at(
        self,
        service: ActivityAuditService,
        mock_repository: AsyncMock,
        sample_event: ActivityAuditTrail,
    ):
        """Test getting activity with created_at for partition optimization."""
        mock_repository.get_by_id.return_value = sample_event
        created_at = datetime.now(UTC)

        await service.get_activity("test-tenant", sample_event.id, created_at)

        mock_repository.get_by_id.assert_called_once_with(
            tenant_id="test-tenant",
            event_id=sample_event.id,
            created_at=created_at,
        )

    @pytest.mark.asyncio
    async def test_list_activities_empty(
        self,
        service: ActivityAuditService,
        mock_repository: AsyncMock,
    ):
        """Test listing activities when none exist."""
        mock_repository.list_events.return_value = []
        mock_repository.count_events.return_value = 0

        items, total = await service.list_activities("test-tenant")

        assert items == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_activities_with_filters(
        self,
        service: ActivityAuditService,
        mock_repository: AsyncMock,
        sample_event: ActivityAuditTrail,
    ):
        """Test listing activities with all filters."""
        mock_repository.list_events.return_value = [sample_event]
        mock_repository.count_events.return_value = 1

        from_date = datetime.now(UTC)
        to_date = datetime.now(UTC)

        items, total = await service.list_activities(
            tenant_id="test-tenant",
            actor_id=SYSTEM_USER_ID,
            action="workflow.execute",
            resource_type="workflow",
            resource_id="wf-123",
            from_date=from_date,
            to_date=to_date,
            offset=10,
            limit=25,
        )

        mock_repository.list_events.assert_called_once_with(
            tenant_id="test-tenant",
            actor_id=SYSTEM_USER_ID,
            source=None,
            action="workflow.execute",
            resource_type="workflow",
            resource_id="wf-123",
            from_date=from_date,
            to_date=to_date,
            offset=10,
            limit=25,
        )

        mock_repository.count_events.assert_called_once_with(
            tenant_id="test-tenant",
            actor_id=SYSTEM_USER_ID,
            source=None,
            action="workflow.execute",
            resource_type="workflow",
            resource_id="wf-123",
            from_date=from_date,
            to_date=to_date,
        )

        assert len(items) == 1
        assert total == 1

    @pytest.mark.asyncio
    async def test_list_activities_pagination(
        self,
        service: ActivityAuditService,
        mock_repository: AsyncMock,
        sample_event: ActivityAuditTrail,
    ):
        """Test pagination parameters are passed correctly."""
        mock_repository.list_events.return_value = [sample_event]
        mock_repository.count_events.return_value = 100

        items, total = await service.list_activities(
            tenant_id="test-tenant",
            offset=50,
            limit=25,
        )

        assert total == 100
        assert len(items) == 1
