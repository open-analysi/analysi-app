"""
Repository for invitation operations.

Project Mikonos — Auth & RBAC (Spec: version_7/AuthAndRBAC_v1.md)
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.auth import Invitation


class InvitationRepository:
    """CRUD operations for the invitations table."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        tenant_id: str,
        email: str,
        role: str,
        token_hash: str,
        expires_at: datetime,
        invited_by: UUID | None = None,
    ) -> Invitation:
        """Create a new invitation record (token already hashed by caller)."""
        invitation = Invitation(
            id=uuid4(),
            tenant_id=tenant_id,
            email=email,
            role=role,
            token_hash=token_hash,
            expires_at=expires_at,
            invited_by=invited_by,
        )
        self.session.add(invitation)
        await self.session.flush()
        return invitation

    async def get_by_id(self, invitation_id: UUID) -> Invitation | None:
        """Fetch invitation by primary key."""
        stmt = select(Invitation).where(Invitation.id == invitation_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_token_hash(self, token_hash: str) -> Invitation | None:
        """Look up invitation by its SHA-256 token hash (accept-invite path)."""
        stmt = select(Invitation).where(Invitation.token_hash == token_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_tenant(self, tenant_id: str) -> list[Invitation]:
        """List all invitations for a tenant."""
        stmt = select(Invitation).where(Invitation.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_accepted(
        self, invitation_id: UUID, accepted_at: datetime
    ) -> Invitation | None:
        """Stamp accepted_at to mark a single-use invitation as consumed."""
        invitation = await self.session.get(Invitation, invitation_id)
        if invitation is None:
            return None
        invitation.accepted_at = accepted_at
        await self.session.flush()
        return invitation

    async def delete(self, invitation_id: UUID) -> bool:
        """Delete an invitation. Returns True if a row was deleted."""
        invitation = await self.session.get(Invitation, invitation_id)
        if invitation is None:
            return False
        await self.session.delete(invitation)
        await self.session.flush()
        return True

    async def list_pending_by_tenant(
        self, tenant_id: str, now: datetime
    ) -> list[Invitation]:
        """List invitations that are not yet accepted and not yet expired."""
        stmt = select(Invitation).where(
            and_(
                Invitation.tenant_id == tenant_id,
                Invitation.accepted_at.is_(None),
                Invitation.expires_at > now,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
