"""
Repository for user operations.

Project Mikonos — Auth & RBAC (Spec: version_7/AuthAndRBAC_v1.md)
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select, union_all, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.auth import SYSTEM_USER_ID, UNKNOWN_USER_ID, Membership, User

# Well-known sentinel user IDs that are always resolvable regardless of tenant.
_SENTINEL_USER_IDS = frozenset({SYSTEM_USER_ID, UNKNOWN_USER_ID})


class UserRepository:
    """CRUD operations for the users table."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        keycloak_id: str,
        email: str,
        display_name: str | None = None,
    ) -> User:
        """Create a user idempotently.

        Concurrent first-login requests (e.g. the UI firing several parallel
        API calls on mount) used to race through this method: each would find
        no existing user and issue an INSERT, and the losers would raise
        ``IntegrityError`` on the ``email`` / ``keycloak_id`` unique indexes.
        Callers caught the exception, but every loss surfaced as an ERROR in
        the Postgres log.

        We now use ``INSERT … ON CONFLICT DO NOTHING`` so conflicts resolve
        silently at the DB layer. The loser's INSERT is a no-op; a follow-up
        SELECT returns whichever row won the race so the caller still gets a
        usable ``User`` object.
        """
        stmt = (
            pg_insert(User)
            .values(
                id=uuid4(),
                keycloak_id=keycloak_id,
                email=email,
                display_name=display_name,
            )
            .on_conflict_do_nothing()
            .returning(User)
        )
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is not None:
            await self.session.flush()
            return user

        # Conflict — the row already exists. Look it up via whichever column
        # matched first (keycloak_id is indexed and more selective; fall back
        # to email for the rare cross-keycloak_id race).
        existing = await self.get_by_keycloak_id(keycloak_id)
        if existing is None:
            existing = await self.get_by_email(email)
        assert existing is not None, (
            "ON CONFLICT DO NOTHING fired but no row was found by keycloak_id "
            f"({keycloak_id!r}) or email ({email!r}) — indicates a broken "
            "unique index or a race with a DELETE."
        )
        return existing

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Fetch user by primary key."""
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_keycloak_id(self, keycloak_id: str) -> User | None:
        """Fetch user by Keycloak sub claim.

        Returns None for empty/blank keycloak_id to prevent matching
        users that were created with an empty keycloak_id (e.g., from
        JWTs missing the ``sub`` claim).
        """
        if not keycloak_id or not keycloak_id.strip():
            return None
        stmt = select(User).where(User.keycloak_id == keycloak_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Fetch user by email address."""
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_ids(self, user_ids: list[UUID]) -> list[User]:
        """Fetch multiple users by primary key list (global, unscoped).

        WARNING: Do not use for user-facing endpoints — use
        get_by_ids_in_tenant() instead to prevent cross-tenant leaks.
        """
        if not user_ids:
            return []
        stmt = select(User).where(User.id.in_(user_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_ids_in_tenant(
        self, user_ids: list[UUID], tenant_id: str
    ) -> list[User]:
        """Fetch users that are members of the given tenant.

        Only returns users who have a membership in ``tenant_id``, plus
        well-known sentinel users (SYSTEM_USER_ID, UNKNOWN_USER_ID) which
        have no memberships but must always be resolvable.
        """
        if not user_ids:
            return []

        # Separate sentinel IDs from regular IDs
        sentinel_ids = [uid for uid in user_ids if uid in _SENTINEL_USER_IDS]
        regular_ids = [uid for uid in user_ids if uid not in _SENTINEL_USER_IDS]

        # Tenant-scoped query: users who have a membership in this tenant
        tenant_stmt = (
            (
                select(User)
                .join(Membership, Membership.user_id == User.id)
                .where(User.id.in_(regular_ids), Membership.tenant_id == tenant_id)
            )
            if regular_ids
            else None
        )

        # Sentinel query: always include regardless of tenant
        sentinel_stmt = (
            (select(User).where(User.id.in_(sentinel_ids))) if sentinel_ids else None
        )

        # Combine both queries
        if tenant_stmt is not None and sentinel_stmt is not None:
            combined = union_all(tenant_stmt, sentinel_stmt).subquery()
            stmt = select(User).join(combined, User.id == combined.c.id)
        elif tenant_stmt is not None:
            stmt = tenant_stmt
        elif sentinel_stmt is not None:
            stmt = sentinel_stmt
        else:
            return []

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_last_seen(self, user_id: UUID, last_seen_at: datetime) -> None:
        """Stamp last_seen_at for activity tracking."""
        stmt = update(User).where(User.id == user_id).values(last_seen_at=last_seen_at)
        await self.session.execute(stmt)
