"""Integration tests for Activity Audit Trail REST API."""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID

# The test auth fixture has db_user_id=None, so the router sets
# actor_id = SYSTEM_USER_ID for all requests.
EXPECTED_ACTOR_ID = str(SYSTEM_USER_ID)


@pytest.mark.asyncio
@pytest.mark.integration
class TestActivityAuditAPI:
    """Integration tests for Activity Audit Trail API endpoints."""

    @pytest.fixture
    async def client(
        self, integration_test_session: AsyncSession
    ) -> AsyncGenerator[AsyncClient]:
        """Create an async HTTP client for testing with test database."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.pop(get_db, None)

    @pytest.fixture
    def tenant_id(self) -> str:
        """Generate a unique tenant ID for test isolation."""
        return f"test-tenant-{uuid4().hex[:8]}"

    def _audit_payload(self, **overrides) -> dict:
        """Build a valid audit trail payload with UUID actor_id."""
        base = {
            "actor_id": str(uuid4()),
            "action": "test.action",
        }
        base.update(overrides)
        return base

    @pytest.mark.asyncio
    async def test_record_activity_success(self, client: AsyncClient, tenant_id: str):
        """Test recording a new activity event."""
        response = await client.post(
            f"/v1/{tenant_id}/audit-trail",
            json=self._audit_payload(
                action="workflow.execute",
                resource_type="workflow",
                resource_id="wf-123",
                details={"workflow_name": "Alert Triage"},
                ip_address="192.168.1.1",
                user_agent="Mozilla/5.0",
                request_id="req-abc123",
            ),
        )

        assert response.status_code == 201
        data = response.json()["data"]

        # actor_id is overridden by the router to the authenticated user's UUID
        assert data["actor_id"] == EXPECTED_ACTOR_ID
        assert data["actor_type"] == "user"
        assert data["action"] == "workflow.execute"
        assert data["resource_type"] == "workflow"
        assert data["resource_id"] == "wf-123"
        assert data["details"] == {"workflow_name": "Alert Triage"}
        assert data["ip_address"] == "192.168.1.1"
        assert data["tenant_id"] == tenant_id
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_record_activity_minimal(self, client: AsyncClient, tenant_id: str):
        """Test recording an activity with only required fields."""
        response = await client.post(
            f"/v1/{tenant_id}/audit-trail",
            json=self._audit_payload(action="page.view"),
        )

        assert response.status_code == 201
        data = response.json()["data"]

        assert data["actor_id"] == EXPECTED_ACTOR_ID
        assert data["actor_type"] == "user"  # Default value
        assert data["action"] == "page.view"
        assert data["resource_type"] is None
        assert data["resource_id"] is None

    @pytest.mark.asyncio
    async def test_record_activity_system_actor(
        self, client: AsyncClient, tenant_id: str
    ):
        """Test recording activity with system actor type."""
        response = await client.post(
            f"/v1/{tenant_id}/audit-trail",
            json=self._audit_payload(
                actor_type="system",
                action="task.execute",
                resource_type="task",
                resource_id="task-456",
            ),
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["actor_type"] == "system"

    @pytest.mark.asyncio
    async def test_list_activities_empty(self, client: AsyncClient, tenant_id: str):
        """Test listing activities when none exist."""
        response = await client.get(f"/v1/{tenant_id}/audit-trail")

        assert response.status_code == 200
        body = response.json()

        assert body["data"] == []
        assert body["meta"]["total"] == 0
        assert body["meta"]["limit"] == 50
        assert body["meta"]["offset"] == 0

    @pytest.mark.asyncio
    async def test_list_activities_with_data(self, client: AsyncClient, tenant_id: str):
        """Test listing activities after creating some."""
        # Create a few events
        for i in range(3):
            await client.post(
                f"/v1/{tenant_id}/audit-trail",
                json=self._audit_payload(action=f"test.action{i}"),
            )

        response = await client.get(f"/v1/{tenant_id}/audit-trail")

        assert response.status_code == 200
        body = response.json()

        assert body["meta"]["total"] == 3
        assert len(body["data"]) == 3

    @pytest.mark.asyncio
    async def test_list_activities_filter_by_actor(
        self, client: AsyncClient, tenant_id: str
    ):
        """Test filtering activities by actor_id.

        Since the router overrides actor_id to SYSTEM_USER_ID for all requests
        from the test auth fixture, we just verify the filter works.
        """
        await client.post(
            f"/v1/{tenant_id}/audit-trail",
            json=self._audit_payload(action="test.action"),
        )

        response = await client.get(
            f"/v1/{tenant_id}/audit-trail?actor_id={EXPECTED_ACTOR_ID}"
        )

        assert response.status_code == 200
        body = response.json()

        assert body["meta"]["total"] == 1
        assert body["data"][0]["actor_id"] == EXPECTED_ACTOR_ID

    @pytest.mark.asyncio
    async def test_list_activities_filter_by_action(
        self, client: AsyncClient, tenant_id: str
    ):
        """Test filtering activities by action."""
        await client.post(
            f"/v1/{tenant_id}/audit-trail",
            json=self._audit_payload(action="workflow.execute"),
        )
        await client.post(
            f"/v1/{tenant_id}/audit-trail",
            json=self._audit_payload(action="task.execute"),
        )

        response = await client.get(
            f"/v1/{tenant_id}/audit-trail?action=workflow.execute"
        )

        assert response.status_code == 200
        body = response.json()

        assert body["meta"]["total"] == 1
        assert body["data"][0]["action"] == "workflow.execute"

    @pytest.mark.asyncio
    async def test_list_activities_filter_by_resource(
        self, client: AsyncClient, tenant_id: str
    ):
        """Test filtering activities by resource_type and resource_id."""
        await client.post(
            f"/v1/{tenant_id}/audit-trail",
            json=self._audit_payload(
                action="view",
                resource_type="alert",
                resource_id="alert-123",
            ),
        )
        await client.post(
            f"/v1/{tenant_id}/audit-trail",
            json=self._audit_payload(
                action="view",
                resource_type="workflow",
                resource_id="wf-456",
            ),
        )

        response = await client.get(
            f"/v1/{tenant_id}/audit-trail?resource_type=alert&resource_id=alert-123"
        )

        assert response.status_code == 200
        body = response.json()

        assert body["meta"]["total"] == 1
        assert body["data"][0]["resource_type"] == "alert"
        assert body["data"][0]["resource_id"] == "alert-123"

    @pytest.mark.asyncio
    async def test_list_activities_pagination(
        self, client: AsyncClient, tenant_id: str
    ):
        """Test pagination of activity list."""
        # Create 10 events
        for _i in range(10):
            await client.post(
                f"/v1/{tenant_id}/audit-trail",
                json=self._audit_payload(action="test.action"),
            )

        # Get first page
        response = await client.get(f"/v1/{tenant_id}/audit-trail?limit=3&offset=0")
        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 3
        assert body["meta"]["total"] == 10
        assert body["meta"]["limit"] == 3
        assert body["meta"]["offset"] == 0

        # Get second page
        response = await client.get(f"/v1/{tenant_id}/audit-trail?limit=3&offset=3")
        assert response.status_code == 200
        body = response.json()
        assert len(body["data"]) == 3
        assert body["meta"]["offset"] == 3

    @pytest.mark.asyncio
    async def test_get_activity_by_id(self, client: AsyncClient, tenant_id: str):
        """Test getting a single activity by ID."""
        # Create an event
        create_response = await client.post(
            f"/v1/{tenant_id}/audit-trail",
            json=self._audit_payload(
                action="workflow.execute",
                resource_type="workflow",
                resource_id="wf-789",
            ),
        )
        created = create_response.json()["data"]
        event_id = created["id"]

        # Get by ID
        response = await client.get(f"/v1/{tenant_id}/audit-trail/{event_id}")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == event_id
        assert data["actor_id"] == EXPECTED_ACTOR_ID
        assert data["action"] == "workflow.execute"

    @pytest.mark.asyncio
    async def test_get_activity_not_found(self, client: AsyncClient, tenant_id: str):
        """Test 404 for non-existent activity."""
        fake_id = str(uuid4())
        response = await client.get(f"/v1/{tenant_id}/audit-trail/{fake_id}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, client: AsyncClient):
        """Test that activities are isolated by tenant."""
        tenant1 = f"tenant1-{uuid4().hex[:8]}"
        tenant2 = f"tenant2-{uuid4().hex[:8]}"

        # Create event for tenant1
        await client.post(
            f"/v1/{tenant1}/audit-trail",
            json=self._audit_payload(action="test.action"),
        )

        # Create event for tenant2
        await client.post(
            f"/v1/{tenant2}/audit-trail",
            json=self._audit_payload(action="test.action"),
        )

        # tenant1 should only see their event
        response = await client.get(f"/v1/{tenant1}/audit-trail")
        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["total"] == 1
        assert body["data"][0]["tenant_id"] == tenant1

        # tenant2 should only see their event
        response = await client.get(f"/v1/{tenant2}/audit-trail")
        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["total"] == 1
        assert body["data"][0]["tenant_id"] == tenant2

    @pytest.mark.asyncio
    async def test_record_activity_external_user_actor(
        self, client: AsyncClient, tenant_id: str
    ):
        """Test recording activity with external_user actor type (HITL answers)."""
        response = await client.post(
            f"/v1/{tenant_id}/audit-trail",
            json=self._audit_payload(
                actor_type="external_user",
                action="hitl.question_answered",
                resource_type="hitl_question",
                resource_id=str(uuid4()),
            ),
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["actor_type"] == "external_user"
        assert data["action"] == "hitl.question_answered"

    @pytest.mark.asyncio
    async def test_invalid_actor_type(self, client: AsyncClient, tenant_id: str):
        """Test validation error for invalid actor_type."""
        response = await client.post(
            f"/v1/{tenant_id}/audit-trail",
            json=self._audit_payload(actor_type="invalid_type"),
        )

        assert response.status_code == 422  # Validation error
