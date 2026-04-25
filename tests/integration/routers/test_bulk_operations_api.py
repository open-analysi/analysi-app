"""Integration tests for bulk-delete endpoints.

Tests /v1/{tenant}/ bulk-delete endpoints migrated from /admin/v1/.
These endpoints require owner role (bulk_operations.delete permission).
"""

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.auth.dependencies import get_current_user
from analysi.auth.models import CurrentUser
from analysi.main import app

_SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def _unique_id() -> str:
    return f"test-{uuid4().hex[:8]}"


def _owner_user(tenant_id: str) -> CurrentUser:
    return CurrentUser(
        user_id="owner-test-user",
        email="owner@test.local",
        tenant_id=tenant_id,
        roles=["owner"],
        actor_type="user",
        db_user_id=_SYSTEM_USER_ID,
    )


def _analyst_user(tenant_id: str) -> CurrentUser:
    return CurrentUser(
        user_id="analyst-test-user",
        email="analyst@test.local",
        tenant_id=tenant_id,
        roles=["analyst"],
        actor_type="user",
        db_user_id=_SYSTEM_USER_ID,
    )


@pytest.mark.integration
class TestBulkDeleteTaskRuns:
    """Tests for DELETE /v1/{tenant}/task-runs."""

    @pytest.fixture
    async def tenant(self) -> str:
        return _unique_id()

    @pytest.fixture
    async def owner_client(self, tenant: str) -> AsyncGenerator[AsyncClient]:
        user = _owner_user(tenant)
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    @pytest.fixture
    async def analyst_client(self, tenant: str) -> AsyncGenerator[AsyncClient]:
        user = _analyst_user(tenant)
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    async def test_bulk_delete_task_runs_empty(
        self, owner_client: AsyncClient, tenant: str
    ):
        """Delete with no matching rows returns 0."""
        response = await owner_client.delete(f"/v1/{tenant}/task-runs")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["deleted_count"] == 0

    async def test_bulk_delete_task_runs_requires_owner(
        self, analyst_client: AsyncClient, tenant: str
    ):
        """Analyst cannot bulk-delete (requires owner)."""
        response = await analyst_client.delete(f"/v1/{tenant}/task-runs")
        assert response.status_code == 403


@pytest.mark.integration
class TestBulkDeleteWorkflowRuns:
    """Tests for DELETE /v1/{tenant}/workflow-runs."""

    @pytest.fixture
    async def tenant(self) -> str:
        return _unique_id()

    @pytest.fixture
    async def owner_client(self, tenant: str) -> AsyncGenerator[AsyncClient]:
        user = _owner_user(tenant)
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    async def test_bulk_delete_workflow_runs_empty(
        self, owner_client: AsyncClient, tenant: str
    ):
        """Delete with no matching rows returns 0."""
        response = await owner_client.delete(f"/v1/{tenant}/workflow-runs")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["deleted_count"] == 0


@pytest.mark.integration
class TestBulkDeleteAllRuns:
    """Tests for DELETE /v1/{tenant}/runs."""

    @pytest.fixture
    async def tenant(self) -> str:
        return _unique_id()

    @pytest.fixture
    async def owner_client(self, tenant: str) -> AsyncGenerator[AsyncClient]:
        user = _owner_user(tenant)
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    async def test_delete_all_runs_empty(self, owner_client: AsyncClient, tenant: str):
        """Delete all runs returns both task_runs and workflow_runs counts."""
        response = await owner_client.delete(f"/v1/{tenant}/runs")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "task_runs" in data
        assert "workflow_runs" in data
        assert data["task_runs"]["deleted_count"] == 0
        assert data["workflow_runs"]["deleted_count"] == 0


@pytest.mark.integration
class TestBulkDeleteAnalysisGroups:
    """Tests for DELETE /v1/{tenant}/analysis-groups."""

    @pytest.fixture
    async def tenant(self) -> str:
        return _unique_id()

    @pytest.fixture
    async def owner_client(self, tenant: str) -> AsyncGenerator[AsyncClient]:
        user = _owner_user(tenant)
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    async def test_bulk_delete_analysis_groups_empty(
        self, owner_client: AsyncClient, tenant: str
    ):
        """Delete with no matching rows returns 0."""
        response = await owner_client.delete(f"/v1/{tenant}/analysis-groups")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["deleted_count"] == 0


@pytest.mark.integration
class TestBulkDeleteAlertAnalyses:
    """Tests for DELETE /v1/{tenant}/alert-analyses."""

    @pytest.fixture
    async def tenant(self) -> str:
        return _unique_id()

    @pytest.fixture
    async def owner_client(self, tenant: str) -> AsyncGenerator[AsyncClient]:
        user = _owner_user(tenant)
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    async def test_bulk_delete_alert_analyses_empty(
        self, owner_client: AsyncClient, tenant: str
    ):
        """Delete with no matching rows returns 0."""
        response = await owner_client.delete(f"/v1/{tenant}/alert-analyses")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["deleted_count"] == 0


@pytest.mark.integration
class TestBulkDeleteAuditTrail:
    """Tests for DELETE /v1/{tenant}/audit-trail."""

    @pytest.fixture
    async def tenant(self) -> str:
        return _unique_id()

    @pytest.fixture
    async def owner_client(self, tenant: str) -> AsyncGenerator[AsyncClient]:
        user = _owner_user(tenant)
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    async def test_bulk_delete_audit_trail_empty(
        self, owner_client: AsyncClient, tenant: str
    ):
        """Delete with no matching rows returns 0."""
        response = await owner_client.delete(f"/v1/{tenant}/audit-trail")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["deleted_count"] == 0


@pytest.mark.integration
class TestBulkDeleteWorkflowGenerations:
    """Tests for DELETE /v1/{tenant}/workflow-generations."""

    @pytest.fixture
    async def tenant(self) -> str:
        return _unique_id()

    @pytest.fixture
    async def owner_client(self, tenant: str) -> AsyncGenerator[AsyncClient]:
        user = _owner_user(tenant)
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    async def test_bulk_delete_workflow_generations_empty(
        self, owner_client: AsyncClient, tenant: str
    ):
        """Delete with no matching rows returns 0."""
        response = await owner_client.delete(f"/v1/{tenant}/workflow-generations")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["deleted_count"] == 0


@pytest.mark.integration
class TestBulkDeleteAlertRoutingRules:
    """Tests for DELETE /v1/{tenant}/alert-routing-rules."""

    @pytest.fixture
    async def tenant(self) -> str:
        return _unique_id()

    @pytest.fixture
    async def owner_client(self, tenant: str) -> AsyncGenerator[AsyncClient]:
        user = _owner_user(tenant)
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    async def test_bulk_delete_alert_routing_rules_empty(
        self, owner_client: AsyncClient, tenant: str
    ):
        """Delete with no matching rows returns 0."""
        response = await owner_client.delete(f"/v1/{tenant}/alert-routing-rules")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["deleted_count"] == 0


@pytest.mark.integration
class TestBulkOperationsRBAC:
    """Cross-cutting RBAC tests for all bulk-delete endpoints."""

    @pytest.fixture
    async def tenant(self) -> str:
        return _unique_id()

    @pytest.fixture
    async def analyst_client(self, tenant: str) -> AsyncGenerator[AsyncClient]:
        user = _analyst_user(tenant)
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    @pytest.mark.parametrize(
        "path",
        [
            "/task-runs",
            "/workflow-runs",
            "/runs",
            "/analysis-groups",
            "/workflow-generations",
            "/alert-routing-rules",
            "/alert-analyses",
            "/audit-trail",
        ],
    )
    async def test_analyst_denied_all_bulk_delete(
        self, analyst_client: AsyncClient, tenant: str, path: str
    ):
        """Analyst role cannot access any bulk-delete endpoint."""
        response = await analyst_client.delete(f"/v1/{tenant}{path}")
        assert response.status_code == 403, (
            f"Expected 403 for {path}, got {response.status_code}"
        )
