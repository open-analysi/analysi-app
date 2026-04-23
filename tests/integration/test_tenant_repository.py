"""Integration tests for TenantRepository."""

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.repositories.tenant import TenantRepository


def _unique_id() -> str:
    """Generate a unique tenant ID for test isolation."""
    return f"test-{uuid4().hex[:8]}"


@pytest.mark.integration
class TestTenantRepository:
    """Integration tests for TenantRepository CRUD."""

    @pytest_asyncio.fixture
    async def repo(self, integration_test_session: AsyncSession) -> TenantRepository:
        return TenantRepository(integration_test_session)

    @pytest_asyncio.fixture
    async def session(self, integration_test_session: AsyncSession) -> AsyncSession:
        return integration_test_session

    async def test_create_tenant(self, repo: TenantRepository, session: AsyncSession):
        """Create a tenant and verify round-trip."""
        tid = _unique_id()
        tenant = await repo.create(tenant_id=tid, name="Test Corp")
        await session.commit()

        assert tenant.id == tid
        assert tenant.name == "Test Corp"
        assert tenant.status == "active"
        assert tenant.created_at is not None
        assert tenant.updated_at is not None

    async def test_create_tenant_duplicate_id_fails(
        self, repo: TenantRepository, session: AsyncSession
    ):
        """Duplicate PK raises IntegrityError."""
        tid = _unique_id()
        await repo.create(tenant_id=tid, name="First")
        await session.commit()

        with pytest.raises(IntegrityError):
            await repo.create(tenant_id=tid, name="Second")
            await session.flush()

    async def test_get_by_id_found(self, repo: TenantRepository, session: AsyncSession):
        """Retrieve an existing tenant."""
        tid = _unique_id()
        await repo.create(tenant_id=tid, name="Found Me")
        await session.commit()

        result = await repo.get_by_id(tid)
        assert result is not None
        assert result.name == "Found Me"

    async def test_get_by_id_not_found(self, repo: TenantRepository):
        """Returns None for nonexistent tenant."""
        result = await repo.get_by_id("nonexistent-tenant-xyz")
        assert result is None

    async def test_list_all(self, repo: TenantRepository, session: AsyncSession):
        """List returns all tenants."""
        tid1 = _unique_id()
        tid2 = _unique_id()
        await repo.create(tenant_id=tid1, name="One")
        await repo.create(tenant_id=tid2, name="Two")
        await session.commit()

        tenants, total = await repo.list_all()
        tenant_ids = [t.id for t in tenants]
        assert tid1 in tenant_ids
        assert tid2 in tenant_ids
        assert total >= 2

    async def test_list_all_with_status_filter(
        self, repo: TenantRepository, session: AsyncSession
    ):
        """Filter by status returns only matching tenants."""
        tid_active = _unique_id()
        tid_suspended = _unique_id()
        await repo.create(tenant_id=tid_active, name="Active", status="active")
        await repo.create(tenant_id=tid_suspended, name="Suspended", status="suspended")
        await session.commit()

        active_tenants, _ = await repo.list_all(status="active")
        active_ids = [t.id for t in active_tenants]
        assert tid_active in active_ids
        assert tid_suspended not in active_ids

        suspended_tenants, _ = await repo.list_all(status="suspended")
        suspended_ids = [t.id for t in suspended_tenants]
        assert tid_suspended in suspended_ids
        assert tid_active not in suspended_ids

    async def test_exists_true(self, repo: TenantRepository, session: AsyncSession):
        """Exists returns True for existing tenant."""
        tid = _unique_id()
        await repo.create(tenant_id=tid, name="Exists")
        await session.commit()

        assert await repo.exists(tid) is True

    async def test_exists_false(self, repo: TenantRepository):
        """Exists returns False for nonexistent tenant."""
        assert await repo.exists("nonexistent-tenant-xyz") is False

    async def test_delete_existing(self, repo: TenantRepository, session: AsyncSession):
        """Delete an existing tenant returns True."""
        tid = _unique_id()
        await repo.create(tenant_id=tid, name="To Delete")
        await session.commit()

        result = await repo.delete(tid)
        await session.commit()
        assert result is True

        # Verify deleted
        assert await repo.get_by_id(tid) is None

    async def test_delete_nonexistent(self, repo: TenantRepository):
        """Delete nonexistent tenant returns False."""
        result = await repo.delete("nonexistent-tenant-xyz")
        assert result is False

    async def test_update_status(self, repo: TenantRepository, session: AsyncSession):
        """Update tenant status."""
        tid = _unique_id()
        await repo.create(tenant_id=tid, name="Status Test")
        await session.commit()

        updated = await repo.update_status(tid, "suspended")
        await session.commit()
        assert updated is not None
        assert updated.status == "suspended"

    async def test_update_status_nonexistent(self, repo: TenantRepository):
        """Update status of nonexistent tenant returns None."""
        result = await repo.update_status("nonexistent-xyz", "suspended")
        assert result is None
