"""Integration tests for RBAC enforcement.

Tests:
- Unauthenticated requests → 401
- Cross-tenant access → 403
- Correct tenant access → 200
- Security headers on all responses
- Admin routes require platform_admin
- Role-based access (analyst/viewer) on protected routes
"""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.auth.dependencies import get_current_user
from analysi.auth.models import CurrentUser
from analysi.main import app


def _make_user(
    roles: list[str],
    tenant_id: str | None,
    user_id: str = "test-user",
) -> CurrentUser:
    return CurrentUser(
        user_id=user_id,
        email="test@analysi.local",
        tenant_id=tenant_id,
        roles=roles,
        actor_type="user",
    )


FAKE_UUID = "00000000-0000-0000-0000-000000000099"


@pytest.mark.integration
class TestTenantIsolation:
    """Tenant isolation — cross-tenant access must be blocked."""

    @pytest.fixture
    async def acme_client(self) -> AsyncGenerator[AsyncClient]:
        """Client authenticated as an 'acme' tenant user."""
        user = _make_user(["owner"], tenant_id="acme")
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    @pytest.fixture
    async def unauthed_client(self) -> AsyncGenerator[AsyncClient]:
        """Client with no authentication."""
        app.dependency_overrides[get_current_user] = lambda: None
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    async def test_unauthenticated_request_returns_401(self, unauthed_client):
        """Any /v1/{tenant}/... route without auth → 401."""
        response = await unauthed_client.get("/v1/acme/tasks")
        assert response.status_code == 401

    async def test_cross_tenant_access_returns_403(self, acme_client):
        """User from 'acme' cannot access 'other-tenant' resources."""
        response = await acme_client.get("/v1/other-tenant/tasks")
        assert response.status_code == 403

    # --- Cross-tenant writes: every verb must be blocked ---

    async def test_cross_tenant_create_task_returns_403(self, acme_client):
        """User from 'acme' cannot create a task in 'other-tenant'."""
        resp = await acme_client.post(
            "/v1/other-tenant/tasks", json={"name": "x", "script": "return 1"}
        )
        assert resp.status_code == 403

    async def test_cross_tenant_update_task_returns_403(self, acme_client):
        resp = await acme_client.put(f"/v1/other-tenant/tasks/{FAKE_UUID}", json={})
        assert resp.status_code == 403

    async def test_cross_tenant_delete_task_returns_403(self, acme_client):
        resp = await acme_client.delete(f"/v1/other-tenant/tasks/{FAKE_UUID}")
        assert resp.status_code == 403

    async def test_cross_tenant_create_workflow_returns_403(self, acme_client):
        resp = await acme_client.post("/v1/other-tenant/workflows", json={})
        assert resp.status_code == 403

    async def test_cross_tenant_delete_workflow_returns_403(self, acme_client):
        resp = await acme_client.delete(f"/v1/other-tenant/workflows/{FAKE_UUID}")
        assert resp.status_code == 403

    async def test_cross_tenant_create_integration_returns_403(self, acme_client):
        resp = await acme_client.post("/v1/other-tenant/integrations", json={})
        assert resp.status_code == 403

    async def test_cross_tenant_read_alerts_returns_403(self, acme_client):
        resp = await acme_client.get("/v1/other-tenant/alerts")
        assert resp.status_code == 403

    async def test_cross_tenant_create_credential_returns_403(self, acme_client):
        resp = await acme_client.post("/v1/other-tenant/credentials", json={})
        assert resp.status_code == 403

    async def test_correct_tenant_access_returns_200_or_data(self, acme_client):
        """User from 'acme' can access their own tenant's routes."""
        response = await acme_client.get("/v1/acme/tasks")
        # 200 (empty list) or any 2xx — not 401 or 403
        assert response.status_code not in (401, 403)


@pytest.mark.integration
class TestAdminRouteProtection:
    """Admin routes must require platform_admin."""

    @pytest.fixture
    async def regular_user_client(self) -> AsyncGenerator[AsyncClient]:
        user = _make_user(["owner"], tenant_id="acme")
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    @pytest.fixture
    async def platform_admin_client(self) -> AsyncGenerator[AsyncClient]:
        user = _make_user(["platform_admin"], tenant_id=None)
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    async def test_regular_user_cannot_access_platform_route(self, regular_user_client):
        """Owner cannot call platform endpoints."""
        response = await regular_user_client.get("/platform/v1/tenants")
        assert response.status_code == 403

    async def test_platform_admin_can_access_platform_route(
        self, platform_admin_client
    ):
        """platform_admin can call platform endpoints."""
        response = await platform_admin_client.get("/platform/v1/tenants")
        assert response.status_code not in (401, 403)


@pytest.mark.integration
class TestRoleBasedAccess:
    """Role-based access: analyst and viewer can read; viewer cannot write."""

    @pytest.fixture
    async def analyst_client(self) -> AsyncGenerator[AsyncClient]:
        user = _make_user(["analyst"], tenant_id="acme")
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    @pytest.fixture
    async def viewer_client(self) -> AsyncGenerator[AsyncClient]:
        user = _make_user(["viewer"], tenant_id="acme")
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    async def test_analyst_can_read_tasks(self, analyst_client):
        response = await analyst_client.get("/v1/acme/tasks")
        assert response.status_code not in (401, 403)

    async def test_viewer_can_read_tasks(self, viewer_client):
        response = await viewer_client.get("/v1/acme/tasks")
        assert response.status_code not in (401, 403)


@pytest.mark.integration
class TestWriteEndpointPermissions:
    """Write endpoints must enforce stricter permissions than router-level read.

    Regression test for P0 RBAC bypass: routers only enforced *.read at
    router level, allowing viewers to create/update/delete resources.

    Permission model:
      - viewer: *.read only
      - analyst: tasks/workflows create/update/execute, NOT delete; NO integrations write
      - admin: tasks/workflows delete, integrations create/update/delete/execute
    """

    @pytest.fixture
    async def viewer_client(self) -> AsyncGenerator[AsyncClient]:
        user = _make_user(["viewer"], tenant_id="acme")
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    @pytest.fixture
    async def analyst_client(self) -> AsyncGenerator[AsyncClient]:
        user = _make_user(["analyst"], tenant_id="acme")
        app.dependency_overrides[get_current_user] = lambda: user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
        app.dependency_overrides.pop(get_current_user, None)

    # --- Tasks: viewer cannot create/update/delete ---

    async def test_viewer_cannot_create_task(self, viewer_client):
        resp = await viewer_client.post("/v1/acme/tasks", json={})
        assert resp.status_code == 403

    async def test_viewer_cannot_update_task(self, viewer_client):
        resp = await viewer_client.put(f"/v1/acme/tasks/{FAKE_UUID}", json={})
        assert resp.status_code == 403

    async def test_viewer_cannot_delete_task(self, viewer_client):
        resp = await viewer_client.delete(f"/v1/acme/tasks/{FAKE_UUID}")
        assert resp.status_code == 403

    # --- Tasks: analyst can create/update but NOT delete (admin-only) ---

    async def test_analyst_cannot_delete_task(self, analyst_client):
        resp = await analyst_client.delete(f"/v1/acme/tasks/{FAKE_UUID}")
        assert resp.status_code == 403

    # --- Workflows: viewer cannot create/update/delete ---

    async def test_viewer_cannot_create_workflow(self, viewer_client):
        resp = await viewer_client.post("/v1/acme/workflows", json={})
        assert resp.status_code == 403

    async def test_viewer_cannot_replace_workflow(self, viewer_client):
        resp = await viewer_client.put(f"/v1/acme/workflows/{FAKE_UUID}", json={})
        assert resp.status_code == 403

    async def test_viewer_cannot_update_workflow(self, viewer_client):
        resp = await viewer_client.patch(f"/v1/acme/workflows/{FAKE_UUID}", json={})
        assert resp.status_code == 403

    async def test_viewer_cannot_delete_workflow(self, viewer_client):
        resp = await viewer_client.delete(f"/v1/acme/workflows/{FAKE_UUID}")
        assert resp.status_code == 403

    # --- Workflows: analyst can create/update but NOT delete (admin-only) ---

    async def test_analyst_cannot_delete_workflow(self, analyst_client):
        resp = await analyst_client.delete(f"/v1/acme/workflows/{FAKE_UUID}")
        assert resp.status_code == 403

    # --- Integrations: viewer cannot write (admin-only resource) ---

    async def test_viewer_cannot_create_integration(self, viewer_client):
        resp = await viewer_client.post("/v1/acme/integrations", json={})
        assert resp.status_code == 403

    async def test_viewer_cannot_update_integration(self, viewer_client):
        resp = await viewer_client.patch("/v1/acme/integrations/some-id", json={})
        assert resp.status_code == 403

    async def test_viewer_cannot_delete_integration(self, viewer_client):
        resp = await viewer_client.delete("/v1/acme/integrations/some-id")
        assert resp.status_code == 403

    # --- Integrations: analyst also cannot write (admin-only resource) ---

    async def test_analyst_cannot_create_integration(self, analyst_client):
        resp = await analyst_client.post("/v1/acme/integrations", json={})
        assert resp.status_code == 403

    async def test_analyst_cannot_update_integration(self, analyst_client):
        resp = await analyst_client.patch("/v1/acme/integrations/some-id", json={})
        assert resp.status_code == 403

    async def test_analyst_cannot_delete_integration(self, analyst_client):
        resp = await analyst_client.delete("/v1/acme/integrations/some-id")
        assert resp.status_code == 403

    # --- Credentials: viewer cannot write (admin-only, maps to integrations perms) ---

    async def test_viewer_cannot_create_credential(self, viewer_client):
        resp = await viewer_client.post("/v1/acme/credentials", json={})
        assert resp.status_code == 403

    async def test_viewer_cannot_delete_credential(self, viewer_client):
        resp = await viewer_client.delete(f"/v1/acme/credentials/{FAKE_UUID}")
        assert resp.status_code == 403

    # --- Credentials: analyst also cannot write (admin-only) ---

    async def test_analyst_cannot_create_credential(self, analyst_client):
        resp = await analyst_client.post("/v1/acme/credentials", json={})
        assert resp.status_code == 403

    async def test_analyst_cannot_delete_credential(self, analyst_client):
        resp = await analyst_client.delete(f"/v1/acme/credentials/{FAKE_UUID}")
        assert resp.status_code == 403


@pytest.mark.integration
class TestSecurityHeaders:
    """Security headers middleware must add headers to all responses."""

    @pytest.fixture
    async def client(self) -> AsyncGenerator[AsyncClient]:
        """Use the autouse platform_admin override."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

    async def test_x_content_type_options_header(self, client):
        response = await client.get("/healthz")
        assert response.headers.get("x-content-type-options") == "nosniff"

    async def test_x_frame_options_header(self, client):
        response = await client.get("/healthz")
        assert response.headers.get("x-frame-options") == "DENY"

    async def test_x_xss_protection_header(self, client):
        response = await client.get("/healthz")
        assert response.headers.get("x-xss-protection") == "1; mode=block"
