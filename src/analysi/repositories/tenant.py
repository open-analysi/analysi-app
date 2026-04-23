"""Repository for tenant CRUD operations (Project Delos)."""

from datetime import UTC, datetime

from sqlalchemy import and_, delete, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.models.schedule import Schedule
from analysi.models.tenant import Tenant

logger = get_logger(__name__)


class TenantRepository:
    """Repository for Tenant table operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        tenant_id: str,
        name: str,
        status: str = "active",
    ) -> Tenant:
        """Create a new tenant.

        Args:
            tenant_id: Human-readable identifier (e.g., "acme-corp").
            name: Display name.
            status: Initial status (default "active").

        Returns:
            The created Tenant instance.
        """
        tenant = Tenant(id=tenant_id, name=name, status=status)
        self.session.add(tenant)
        await self.session.flush()
        return tenant

    async def get_by_id(self, tenant_id: str) -> Tenant | None:
        """Get a tenant by its ID.

        Returns:
            Tenant or None if not found.
        """
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(
        self,
        *,
        status: str | None = None,
        has_schedules: bool | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[Tenant], int]:
        """List tenants with optional filters.

        Args:
            status: Filter by status (e.g., "active", "suspended").
            has_schedules: Filter to tenants with/without enabled schedules.
            skip: Offset for pagination.
            limit: Max results to return.

        Returns:
            Tuple of (tenants list, total count).
        """
        conditions = []
        if status:
            conditions.append(Tenant.status == status)

        if has_schedules is not None:
            sched_subq = (
                select(distinct(Schedule.tenant_id))
                .where(Schedule.enabled.is_(True))
                .scalar_subquery()
            )
            if has_schedules:
                conditions.append(Tenant.id.in_(sched_subq))
            else:
                conditions.append(~Tenant.id.in_(sched_subq))

        # Count
        count_stmt = select(func.count()).select_from(Tenant)
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # Fetch
        stmt = select(Tenant).order_by(Tenant.created_at.desc())
        if conditions:
            stmt = stmt.where(and_(*conditions))
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        tenants = list(result.scalars().all())

        return tenants, total

    async def delete(self, tenant_id: str) -> bool:
        """Delete a tenant by ID.

        Returns:
            True if the tenant was deleted, False if not found.
        """
        stmt = delete(Tenant).where(Tenant.id == tenant_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def exists(self, tenant_id: str) -> bool:
        """Check if a tenant exists.

        Returns:
            True if the tenant exists.
        """
        stmt = select(func.count()).select_from(Tenant).where(Tenant.id == tenant_id)
        result = await self.session.execute(stmt)
        count = result.scalar() or 0
        return count > 0

    async def update_status(self, tenant_id: str, status: str) -> Tenant | None:
        """Update a tenant's status.

        Returns:
            Updated Tenant or None if not found.
        """
        tenant = await self.get_by_id(tenant_id)
        if tenant is None:
            return None
        tenant.status = status
        tenant.updated_at = datetime.now(UTC)
        await self.session.flush()
        return tenant
