"""
Repository for API key operations.

Project Mikonos — Auth & RBAC (Spec: version_7/AuthAndRBAC_v1.md)
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.auth import ApiKey


class ApiKeyRepository:
    """CRUD operations for the api_keys table."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        tenant_id: str,
        name: str,
        key_hash: str,
        key_prefix: str,
        user_id: UUID | None = None,
        scopes: list | None = None,
        expires_at: datetime | None = None,
    ) -> ApiKey:
        """Create a new API key record. The plaintext secret is NOT stored here."""
        api_key = ApiKey(
            id=uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scopes=scopes or [],
            expires_at=expires_at,
        )
        self.session.add(api_key)
        await self.session.flush()
        return api_key

    async def get_by_id(self, key_id: UUID) -> ApiKey | None:
        """Fetch API key by primary key."""
        stmt = select(ApiKey).where(ApiKey.id == key_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
        """Look up API key by its SHA-256 hash (used in the auth path)."""
        stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_tenant(self, tenant_id: str) -> list[ApiKey]:
        """List all API keys for a tenant (no secrets)."""
        stmt = select(ApiKey).where(ApiKey.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, key_id: UUID) -> bool:
        """Revoke an API key by ID. Returns True if a row was deleted."""
        api_key = await self.session.get(ApiKey, key_id)
        if api_key is None:
            return False
        await self.session.delete(api_key)
        await self.session.flush()
        return True

    async def delete_by_user_and_tenant(self, user_id: UUID, tenant_id: str) -> int:
        """Delete all API keys for a user in a tenant (cascade on member removal).

        Returns the number of rows deleted.
        """
        stmt = (
            delete(ApiKey)
            .where(and_(ApiKey.user_id == user_id, ApiKey.tenant_id == tenant_id))
            .returning(ApiKey.id)
        )
        result = await self.session.execute(stmt)
        return len(result.fetchall())

    async def update_last_used(self, key_id: UUID, last_used_at: datetime) -> None:
        """Stamp last_used_at for the given API key."""
        stmt = (
            update(ApiKey).where(ApiKey.id == key_id).values(last_used_at=last_used_at)
        )
        await self.session.execute(stmt)
