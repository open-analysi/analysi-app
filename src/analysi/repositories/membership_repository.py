"""
Repository for tenant membership operations.

Project Mikonos — Auth & RBAC (Spec: version_7/AuthAndRBAC_v1.md)
"""

from uuid import UUID, uuid4

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from analysi.models.auth import Membership


class MembershipRepository:
    """CRUD operations for the memberships table."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: UUID,
        tenant_id: str,
        role: str,
        invited_by: UUID | None = None,
    ) -> Membership:
        """Create a new tenant membership."""
        membership = Membership(
            id=uuid4(),
            user_id=user_id,
            tenant_id=tenant_id,
            role=role,
            invited_by=invited_by,
        )
        self.session.add(membership)
        await self.session.flush()
        return membership

    async def get_by_user_and_tenant(
        self, user_id: UUID, tenant_id: str
    ) -> Membership | None:
        """Fetch a user's membership in a specific tenant."""
        stmt = select(Membership).where(
            and_(Membership.user_id == user_id, Membership.tenant_id == tenant_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_tenant(self, tenant_id: str) -> list[Membership]:
        """List all members of a tenant."""
        stmt = select(Membership).where(Membership.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_tenant_with_user(self, tenant_id: str) -> list[Membership]:
        """List all members of a tenant, eagerly loading the related User."""
        stmt = (
            select(Membership)
            .where(Membership.tenant_id == tenant_id)
            .options(selectinload(Membership.user))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_with_user(self, membership_id: UUID) -> Membership | None:
        """Fetch membership by ID, eagerly loading the related User."""
        stmt = (
            select(Membership)
            .where(Membership.id == membership_id)
            .options(selectinload(Membership.user))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_role(self, membership_id: UUID, role: str) -> Membership | None:
        """Change a member's role. Returns the updated membership or None if not found."""
        stmt = (
            update(Membership)
            .where(Membership.id == membership_id)
            .values(role=role)
            .returning(Membership)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, membership_id: UUID) -> bool:
        """Remove a membership. Returns True if a row was deleted."""
        membership = await self.session.get(Membership, membership_id)
        if membership is None:
            return False
        await self.session.delete(membership)
        await self.session.flush()
        return True

    async def count_owners(self, tenant_id: str) -> int:
        """Count members with the owner role for a tenant."""
        stmt = select(func.count(Membership.id)).where(
            and_(Membership.tenant_id == tenant_id, Membership.role == "owner")
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0
