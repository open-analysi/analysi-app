"""Integration tests for Platform Tenant Management API.

Tests /platform/v1/tenants CRUD endpoints.
"""

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.auth.dependencies import get_current_user
from analysi.auth.models import CurrentUser
from analysi.main import app
from analysi.models.component import Component

_SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def _unique_id() -> str:
    """Generate a unique tenant ID for test isolation."""
    return f"test-{uuid4().hex[:8]}"


def _platform_admin_user() -> CurrentUser:
    """Create a platform_admin CurrentUser for auth override."""
    return CurrentUser(
        user_id="platform-test-user",
        email="platform@test.local",
        tenant_id=None,
        roles=["platform_admin"],
        actor_type="user",
        db_user_id=_SYSTEM_USER_ID,
    )


def _analyst_user(tenant_id: str) -> CurrentUser:
    """Create a regular analyst user (not platform_admin)."""
    return CurrentUser(
        user_id="analyst-test-user",
        email="analyst@test.local",
        tenant_id=tenant_id,
        roles=["analyst"],
        actor_type="user",
        db_user_id=_SYSTEM_USER_ID,
    )


@pytest.fixture
async def platform_client() -> AsyncGenerator[AsyncClient]:
    """HTTP client authenticated as platform_admin."""
    user = _platform_admin_user()
    app.dependency_overrides[get_current_user] = lambda: user
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def analyst_client() -> AsyncGenerator[AsyncClient]:
    """HTTP client authenticated as regular analyst (NOT platform_admin)."""
    user = _analyst_user("some-tenant")
    app.dependency_overrides[get_current_user] = lambda: user
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# POST /platform/v1/tenants
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCreateTenant:
    """Tests for tenant creation endpoint."""

    async def test_create_tenant_success(self, platform_client: AsyncClient):
        """Create a tenant successfully."""
        tid = _unique_id()
        response = await platform_client.post(
            "/platform/v1/tenants",
            json={"id": tid, "name": "Test Corp"},
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["id"] == tid
        assert data["name"] == "Test Corp"
        assert data["status"] == "active"

    async def test_create_tenant_dry_run(self, platform_client: AsyncClient):
        """Dry run validates without creating."""
        tid = _unique_id()
        response = await platform_client.post(
            "/platform/v1/tenants",
            json={"id": tid, "name": "Dry Run Corp"},
            params={"dry_run": True},
        )
        assert response.status_code == 201
        assert response.json()["data"] is None

        # Verify not actually created
        get_response = await platform_client.get(f"/platform/v1/tenants/{tid}")
        assert get_response.status_code == 404

    async def test_create_tenant_invalid_id_too_short(
        self, platform_client: AsyncClient
    ):
        """Reject tenant ID that's too short (Pydantic validation → 422)."""
        response = await platform_client.post(
            "/platform/v1/tenants",
            json={"id": "AB", "name": "Bad ID"},
        )
        assert response.status_code == 422

    async def test_create_tenant_invalid_id_format(self, platform_client: AsyncClient):
        """Reject tenant ID with bad characters (service validation → 400)."""
        response = await platform_client.post(
            "/platform/v1/tenants",
            json={"id": "Bad_Format!", "name": "Bad Format"},
        )
        assert response.status_code == 400

    async def test_create_tenant_duplicate(self, platform_client: AsyncClient):
        """Reject duplicate tenant ID."""
        tid = _unique_id()
        # Create first
        response = await platform_client.post(
            "/platform/v1/tenants",
            json={"id": tid, "name": "First"},
        )
        assert response.status_code == 201

        # Try duplicate
        response = await platform_client.post(
            "/platform/v1/tenants",
            json={"id": tid, "name": "Second"},
        )
        assert response.status_code == 400
        assert "Invalid tenant configuration" in response.json()["detail"]

    async def test_create_tenant_requires_platform_admin(
        self, analyst_client: AsyncClient
    ):
        """Non-platform_admin gets 403."""
        response = await analyst_client.post(
            "/platform/v1/tenants",
            json={"id": _unique_id(), "name": "Forbidden"},
        )
        assert response.status_code == 403

    async def test_create_tenant_with_owner_email_new_user(
        self, platform_client: AsyncClient
    ):
        """Create tenant with owner_email JIT-creates user and membership."""
        tid = _unique_id()
        email = f"owner-{uuid4().hex[:6]}@test.local"
        response = await platform_client.post(
            "/platform/v1/tenants",
            json={"id": tid, "name": "Owner Corp", "owner_email": email},
        )
        assert response.status_code == 201
        data = response.json()["data"]
        assert data["id"] == tid

        # Verify tenant has 1 member (the owner)
        describe = await platform_client.get(f"/platform/v1/tenants/{tid}")
        assert describe.status_code == 200
        assert describe.json()["data"]["member_count"] == 1

    async def test_create_tenant_with_owner_email_existing_user(
        self, platform_client: AsyncClient
    ):
        """When owner_email matches an existing user, reuse that user."""
        # Create first tenant with a new user
        tid1 = _unique_id()
        email = f"shared-{uuid4().hex[:6]}@test.local"
        r1 = await platform_client.post(
            "/platform/v1/tenants",
            json={"id": tid1, "name": "First Corp", "owner_email": email},
        )
        assert r1.status_code == 201

        # Create second tenant with the same email — should reuse user
        tid2 = _unique_id()
        r2 = await platform_client.post(
            "/platform/v1/tenants",
            json={"id": tid2, "name": "Second Corp", "owner_email": email},
        )
        assert r2.status_code == 201

        # Both tenants should have 1 member each
        d1 = await platform_client.get(f"/platform/v1/tenants/{tid1}")
        d2 = await platform_client.get(f"/platform/v1/tenants/{tid2}")
        assert d1.json()["data"]["member_count"] == 1
        assert d2.json()["data"]["member_count"] == 1

    async def test_create_tenant_without_owner_email(
        self, platform_client: AsyncClient
    ):
        """Create tenant without owner_email — no members created."""
        tid = _unique_id()
        response = await platform_client.post(
            "/platform/v1/tenants",
            json={"id": tid, "name": "No Owner Corp"},
        )
        assert response.status_code == 201

        describe = await platform_client.get(f"/platform/v1/tenants/{tid}")
        assert describe.json()["data"]["member_count"] == 0


# ---------------------------------------------------------------------------
# GET /platform/v1/tenants
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListTenants:
    """Tests for tenant listing endpoint."""

    async def test_list_tenants(self, platform_client: AsyncClient):
        """List returns created tenants."""
        tid = _unique_id()
        await platform_client.post(
            "/platform/v1/tenants",
            json={"id": tid, "name": "Listed"},
        )

        response = await platform_client.get("/platform/v1/tenants")
        assert response.status_code == 200
        data = response.json()["data"]
        tenant_ids = [t["id"] for t in data]
        assert tid in tenant_ids

    async def test_list_tenants_status_filter(self, platform_client: AsyncClient):
        """Filter by status."""
        tid = _unique_id()
        await platform_client.post(
            "/platform/v1/tenants",
            json={"id": tid, "name": "Active"},
        )

        response = await platform_client.get(
            "/platform/v1/tenants", params={"status": "active"}
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert any(t["id"] == tid for t in data)

        response = await platform_client.get(
            "/platform/v1/tenants", params={"status": "suspended"}
        )
        data = response.json()["data"]
        assert not any(t["id"] == tid for t in data)

    async def test_list_tenants_pagination(self, platform_client: AsyncClient):
        """Pagination metadata is present."""
        response = await platform_client.get(
            "/platform/v1/tenants", params={"limit": 2, "offset": 0}
        )
        assert response.status_code == 200
        meta = response.json()["meta"]
        assert "total" in meta
        assert meta["limit"] == 2
        assert meta["offset"] == 0

    async def test_list_tenants_has_schedules_filter(
        self, platform_client: AsyncClient
    ):
        """has_schedules=true filters to tenants with enabled schedules.

        Replaces GET /admin/v1/tenants-with-schedules.
        """
        tid = _unique_id()
        await platform_client.post(
            "/platform/v1/tenants",
            json={"id": tid, "name": "No Schedules"},
        )

        # Tenant with no schedules should NOT appear when has_schedules=true
        response = await platform_client.get(
            "/platform/v1/tenants", params={"has_schedules": True}
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert not any(t["id"] == tid for t in data)

        # But SHOULD appear when has_schedules=false
        response = await platform_client.get(
            "/platform/v1/tenants", params={"has_schedules": False}
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert any(t["id"] == tid for t in data)


# ---------------------------------------------------------------------------
# GET /platform/v1/tenants/{tenant_id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDescribeTenant:
    """Tests for tenant describe endpoint."""

    async def test_describe_tenant(self, platform_client: AsyncClient):
        """Describe returns tenant details with counts."""
        tid = _unique_id()
        await platform_client.post(
            "/platform/v1/tenants",
            json={"id": tid, "name": "Described"},
        )

        response = await platform_client.get(f"/platform/v1/tenants/{tid}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == tid
        assert data["name"] == "Described"
        assert "member_count" in data
        assert "component_counts" in data
        assert "installed_packs" in data

    async def test_describe_tenant_not_found(self, platform_client: AsyncClient):
        """Describe nonexistent tenant returns 404."""
        response = await platform_client.get(
            "/platform/v1/tenants/nonexistent-tenant-xyz"
        )
        assert response.status_code == 404

    async def test_describe_tenant_with_components(
        self,
        platform_client: AsyncClient,
        integration_test_session: AsyncSession,
    ):
        """Describe shows component counts when tenant has content."""
        tid = _unique_id()
        await platform_client.post(
            "/platform/v1/tenants",
            json={"id": tid, "name": "With Content"},
        )

        # Add a component directly to the DB
        component = Component(
            tenant_id=tid,
            kind="task",
            name="Test Task",
            description="A task",
            created_by=_SYSTEM_USER_ID,
        )
        integration_test_session.add(component)
        await integration_test_session.commit()

        response = await platform_client.get(f"/platform/v1/tenants/{tid}")
        data = response.json()["data"]
        assert data["component_counts"].get("task", 0) >= 1


# ---------------------------------------------------------------------------
# DELETE /platform/v1/tenants/{tenant_id}
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDeleteTenant:
    """Tests for tenant cascade delete endpoint."""

    async def test_delete_tenant_success(self, platform_client: AsyncClient):
        """Delete tenant with correct confirmation."""
        tid = _unique_id()
        await platform_client.post(
            "/platform/v1/tenants",
            json={"id": tid, "name": "To Delete"},
        )

        response = await platform_client.delete(
            f"/platform/v1/tenants/{tid}", params={"confirm": tid}
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["tenant_id"] == tid
        assert data["tables_affected"] >= 1

        # Verify tenant is gone
        get_response = await platform_client.get(f"/platform/v1/tenants/{tid}")
        assert get_response.status_code == 404

    async def test_delete_tenant_wrong_confirmation(self, platform_client: AsyncClient):
        """Wrong confirmation string returns 400."""
        tid = _unique_id()
        await platform_client.post(
            "/platform/v1/tenants",
            json={"id": tid, "name": "Wrong Confirm"},
        )

        response = await platform_client.delete(
            f"/platform/v1/tenants/{tid}", params={"confirm": "wrong-id"}
        )
        assert response.status_code == 400
        assert "Confirmation does not match" in response.json()["detail"]

    async def test_delete_tenant_not_found(self, platform_client: AsyncClient):
        """Delete nonexistent tenant returns 404."""
        response = await platform_client.delete(
            "/platform/v1/tenants/nonexistent-xyz",
            params={"confirm": "nonexistent-xyz"},
        )
        assert response.status_code == 404

    async def test_delete_tenant_cascades_components(
        self,
        platform_client: AsyncClient,
        integration_test_session: AsyncSession,
    ):
        """Delete cascades to remove components."""
        tid = _unique_id()
        await platform_client.post(
            "/platform/v1/tenants",
            json={"id": tid, "name": "Cascade Test"},
        )

        # Add component
        component = Component(
            tenant_id=tid,
            kind="task",
            name="Cascade Task",
            description="Will be deleted",
            created_by=_SYSTEM_USER_ID,
        )
        integration_test_session.add(component)
        await integration_test_session.commit()

        # Delete
        response = await platform_client.delete(
            f"/platform/v1/tenants/{tid}", params={"confirm": tid}
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["details"].get("components", 0) >= 1
