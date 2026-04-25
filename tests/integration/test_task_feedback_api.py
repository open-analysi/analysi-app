"""Integration tests for Task Feedback REST API (Project Zakynthos).

Tests the full CRUD lifecycle via HTTP endpoints.
"""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.component import Component, ComponentKind, ComponentStatus
from analysi.models.task import Task

TENANT = f"test-feedback-{uuid4().hex[:8]}"
SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"


@pytest.mark.integration
@pytest.mark.asyncio
class TestTaskFeedbackAPI:
    """Full CRUD lifecycle for task feedback via REST API."""

    @pytest.fixture
    async def client(self, integration_test_session) -> AsyncGenerator[AsyncClient]:
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.pop(get_db, None)

    @pytest.fixture
    async def task_component_id(self, integration_test_session: AsyncSession) -> str:
        """Create a task with component and return the component ID."""
        component = Component(
            tenant_id=TENANT,
            kind=ComponentKind.TASK,
            name="Test Task for Feedback",
            description="Task used in feedback tests",
            status=ComponentStatus.ENABLED,
            created_by=SYSTEM_USER_ID,
        )
        integration_test_session.add(component)
        await integration_test_session.flush()

        task = Task(
            component_id=component.id,
            directive="Analyze alerts",
            script="return 'hello'",
        )
        integration_test_session.add(task)
        await integration_test_session.commit()

        return str(component.id)

    def _url(self, task_component_id: str, feedback_id: str | None = None) -> str:
        base = f"/v1/{TENANT}/tasks/{task_component_id}/feedback"
        if feedback_id:
            base += f"/{feedback_id}"
        return base

    async def test_create_feedback(self, client: AsyncClient, task_component_id: str):
        """POST creates a feedback entry and returns 201."""
        resp = await client.post(
            self._url(task_component_id),
            json={"feedback": "Always check for SQL injection patterns"},
        )
        assert resp.status_code == 201, resp.text

        body = resp.json()
        data = body["data"]
        assert data["feedback"] == "Always check for SQL injection patterns"
        assert data["task_component_id"] == task_component_id
        assert data["status"] == "enabled"
        assert "title" in data
        assert len(data["title"]) > 0
        assert "meta" in body

    async def test_create_feedback_with_metadata(
        self, client: AsyncClient, task_component_id: str
    ):
        resp = await client.post(
            self._url(task_component_id),
            json={
                "feedback": "Prioritize CVE-2024 entries",
                "metadata": {"priority": "high", "category": "vulnerability"},
            },
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["metadata"]["priority"] == "high"

    async def test_create_feedback_invalid_task_returns_404(self, client: AsyncClient):
        fake_id = str(uuid4())
        resp = await client.post(
            self._url(fake_id),
            json={"feedback": "Won't work"},
        )
        assert resp.status_code == 404

    async def test_create_feedback_empty_text_returns_422(
        self, client: AsyncClient, task_component_id: str
    ):
        resp = await client.post(
            self._url(task_component_id),
            json={"feedback": ""},
        )
        assert resp.status_code == 422

    async def test_list_feedback(self, client: AsyncClient, task_component_id: str):
        """GET returns all active feedback entries."""
        # Create two entries
        await client.post(
            self._url(task_component_id),
            json={"feedback": "First feedback"},
        )
        await client.post(
            self._url(task_component_id),
            json={"feedback": "Second feedback"},
        )

        resp = await client.get(self._url(task_component_id))
        assert resp.status_code == 200

        body = resp.json()
        assert body["meta"]["total"] >= 2
        feedbacks = [d["feedback"] for d in body["data"]]
        assert "First feedback" in feedbacks
        assert "Second feedback" in feedbacks

    async def test_get_single_feedback(
        self, client: AsyncClient, task_component_id: str
    ):
        create_resp = await client.post(
            self._url(task_component_id),
            json={"feedback": "Specific entry"},
        )
        feedback_id = create_resp.json()["data"]["id"]

        resp = await client.get(self._url(task_component_id, feedback_id))
        assert resp.status_code == 200
        assert resp.json()["data"]["feedback"] == "Specific entry"

    async def test_get_nonexistent_feedback_returns_404(
        self, client: AsyncClient, task_component_id: str
    ):
        resp = await client.get(self._url(task_component_id, str(uuid4())))
        assert resp.status_code == 404

    async def test_update_feedback(self, client: AsyncClient, task_component_id: str):
        create_resp = await client.post(
            self._url(task_component_id),
            json={"feedback": "Original text"},
        )
        feedback_id = create_resp.json()["data"]["id"]

        resp = await client.patch(
            self._url(task_component_id, feedback_id),
            json={"feedback": "Updated text"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["feedback"] == "Updated text"

    async def test_update_metadata_only(
        self, client: AsyncClient, task_component_id: str
    ):
        create_resp = await client.post(
            self._url(task_component_id),
            json={"feedback": "Keep this text", "metadata": {"old": True}},
        )
        feedback_id = create_resp.json()["data"]["id"]

        resp = await client.patch(
            self._url(task_component_id, feedback_id),
            json={"metadata": {"new": True}},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["feedback"] == "Keep this text"
        assert data["metadata"] == {"new": True}

    async def test_update_empty_body_returns_400(
        self, client: AsyncClient, task_component_id: str
    ):
        create_resp = await client.post(
            self._url(task_component_id),
            json={"feedback": "Some text"},
        )
        feedback_id = create_resp.json()["data"]["id"]

        resp = await client.patch(
            self._url(task_component_id, feedback_id),
            json={},
        )
        assert resp.status_code == 400

    async def test_delete_feedback_soft_deletes(
        self, client: AsyncClient, task_component_id: str
    ):
        """DELETE sets status to disabled and returns 204."""
        create_resp = await client.post(
            self._url(task_component_id),
            json={"feedback": "Will be deleted"},
        )
        feedback_id = create_resp.json()["data"]["id"]

        resp = await client.delete(self._url(task_component_id, feedback_id))
        assert resp.status_code == 204

        # Should not appear in list anymore
        list_resp = await client.get(self._url(task_component_id))
        ids = [d["id"] for d in list_resp.json()["data"]]
        assert feedback_id not in ids

    async def test_delete_nonexistent_returns_404(
        self, client: AsyncClient, task_component_id: str
    ):
        resp = await client.delete(self._url(task_component_id, str(uuid4())))
        assert resp.status_code == 404

    async def test_delete_idempotent(self, client: AsyncClient, task_component_id: str):
        """Deleting an already-deleted entry returns 404 (not 204)."""
        create_resp = await client.post(
            self._url(task_component_id),
            json={"feedback": "Double delete test"},
        )
        feedback_id = create_resp.json()["data"]["id"]

        await client.delete(self._url(task_component_id, feedback_id))
        resp = await client.delete(self._url(task_component_id, feedback_id))
        assert resp.status_code == 404
