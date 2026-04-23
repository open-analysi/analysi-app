"""Integration tests for TenantService."""

from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.component import Component
from analysi.models.workflow import Workflow
from analysi.services.tenant import TenantService


def _unique_id() -> str:
    """Generate a unique tenant ID for test isolation."""
    return f"test-{uuid4().hex[:8]}"


# System user UUID used for created_by fields
_SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.integration
class TestTenantServiceCreate:
    """Integration tests for tenant creation."""

    @pytest_asyncio.fixture
    async def service(self, integration_test_session: AsyncSession) -> TenantService:
        return TenantService(integration_test_session)

    @pytest_asyncio.fixture
    async def session(self, integration_test_session: AsyncSession) -> AsyncSession:
        return integration_test_session

    async def test_create_tenant_valid(
        self, service: TenantService, session: AsyncSession
    ):
        """Create a tenant with valid ID and name."""
        tid = _unique_id()
        tenant = await service.create_tenant(tenant_id=tid, name="Acme Corp")
        await session.commit()

        assert tenant is not None
        assert tenant.id == tid
        assert tenant.name == "Acme Corp"
        assert tenant.status == "active"

    async def test_create_tenant_dry_run(
        self, service: TenantService, session: AsyncSession
    ):
        """Dry run validates without persisting."""
        tid = _unique_id()
        result = await service.create_tenant(
            tenant_id=tid, name="Dry Run Corp", dry_run=True
        )
        assert result is None

        # Verify tenant was NOT created
        tenant = await service.get_tenant(tid)
        assert tenant is None

    async def test_create_tenant_invalid_id_format(self, service: TenantService):
        """Reject bad ID format."""
        with pytest.raises(ValueError, match="Invalid tenant ID"):
            await service.create_tenant(tenant_id="AB", name="Bad")

    async def test_create_tenant_duplicate(
        self, service: TenantService, session: AsyncSession
    ):
        """Reject duplicate tenant ID."""
        tid = _unique_id()
        await service.create_tenant(tenant_id=tid, name="First")
        await session.commit()

        with pytest.raises(ValueError, match="already exists"):
            await service.create_tenant(tenant_id=tid, name="Second")

    async def test_create_tenant_id_too_short(self, service: TenantService):
        """Reject IDs < 3 chars."""
        with pytest.raises(ValueError, match="at least 3"):
            await service.create_tenant(tenant_id="ab", name="Short")

    async def test_create_tenant_id_too_long(self, service: TenantService):
        """Reject IDs > 255 chars."""
        with pytest.raises(ValueError, match="at most 255"):
            await service.create_tenant(tenant_id="a" * 256, name="Long")


@pytest.mark.integration
class TestTenantServiceList:
    """Integration tests for tenant listing."""

    @pytest_asyncio.fixture
    async def service(self, integration_test_session: AsyncSession) -> TenantService:
        return TenantService(integration_test_session)

    @pytest_asyncio.fixture
    async def session(self, integration_test_session: AsyncSession) -> AsyncSession:
        return integration_test_session

    async def test_list_tenants(self, service: TenantService, session: AsyncSession):
        """List returns created tenants."""
        tid = _unique_id()
        await service.create_tenant(tenant_id=tid, name="Listed")
        await session.commit()

        tenants, total = await service.list_tenants()
        assert total >= 1
        assert any(t.id == tid for t in tenants)

    async def test_list_tenants_status_filter(
        self, service: TenantService, session: AsyncSession
    ):
        """List with status filter."""
        tid = _unique_id()
        await service.create_tenant(tenant_id=tid, name="Active")
        await session.commit()

        tenants, _ = await service.list_tenants(status="active")
        assert any(t.id == tid for t in tenants)

        tenants, _ = await service.list_tenants(status="suspended")
        assert not any(t.id == tid for t in tenants)


@pytest.mark.integration
class TestTenantServiceCascadeDelete:
    """Integration tests for cascade delete."""

    @pytest_asyncio.fixture
    async def service(self, integration_test_session: AsyncSession) -> TenantService:
        return TenantService(integration_test_session)

    @pytest_asyncio.fixture
    async def session(self, integration_test_session: AsyncSession) -> AsyncSession:
        return integration_test_session

    async def test_cascade_delete_removes_components(
        self, service: TenantService, session: AsyncSession
    ):
        """Cascade delete removes components belonging to tenant."""
        tid = _unique_id()
        await service.create_tenant(tenant_id=tid, name="To Delete")
        await session.commit()

        # Create a component in this tenant
        component = Component(
            tenant_id=tid,
            kind="task",
            name="Test Task",
            description="A test task",
            created_by=_SYSTEM_USER_ID,
        )
        session.add(component)
        await session.commit()

        # Cascade delete
        counts = await service.cascade_delete_tenant(tid)
        await session.commit()

        assert "components" in counts
        assert counts["components"] >= 1
        assert "tenants" in counts

        # Verify tenant is gone
        assert await service.get_tenant(tid) is None

    async def test_cascade_delete_removes_workflows(
        self, service: TenantService, session: AsyncSession
    ):
        """Cascade delete removes workflows belonging to tenant."""
        tid = _unique_id()
        await service.create_tenant(tenant_id=tid, name="WF Delete")
        await session.commit()

        # Create a workflow in this tenant
        workflow = Workflow(
            tenant_id=tid,
            name="Test Workflow",
            io_schema={"input": {"type": "object"}, "output": {"type": "object"}},
            created_by=_SYSTEM_USER_ID,
        )
        session.add(workflow)
        await session.commit()

        # Cascade delete
        counts = await service.cascade_delete_tenant(tid)
        await session.commit()

        assert "workflows" in counts
        assert counts["workflows"] >= 1

    async def test_cascade_delete_nonexistent_tenant(self, service: TenantService):
        """Cascade delete of nonexistent tenant raises ValueError."""
        with pytest.raises(ValueError, match="does not exist"):
            await service.cascade_delete_tenant("nonexistent-xyz-123")

    async def test_cascade_delete_empty_tenant(
        self, service: TenantService, session: AsyncSession
    ):
        """Cascade delete of tenant with no data succeeds."""
        tid = _unique_id()
        await service.create_tenant(tenant_id=tid, name="Empty Tenant")
        await session.commit()

        counts = await service.cascade_delete_tenant(tid)
        await session.commit()

        # Only the tenant record itself should be deleted
        assert counts == {"tenants": 1}
        assert await service.get_tenant(tid) is None
