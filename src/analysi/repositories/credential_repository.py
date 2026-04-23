"""
Repository layer for credential database operations.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from analysi.models.credential import Credential, IntegrationCredential


class CredentialRepository:
    """Repository for credential CRUD operations."""

    def __init__(self, session: AsyncSession):
        """Initialize with database session."""
        self.session = session

    async def upsert(
        self,
        tenant_id: str,
        provider: str,
        account: str,
        ciphertext: str,
        key_version: int,
        credential_metadata: dict = None,
        created_by: UUID | None = None,
    ) -> Credential:
        """
        Create or update credential by unique constraint.

        Args:
            tenant_id: Tenant identifier
            provider: Integration type
            account: Credential label
            ciphertext: Encrypted JSON
            key_version: Vault key version
            credential_metadata: Unencrypted metadata
            created_by: User creating credential

        Returns:
            Created or updated credential
        """
        # Check if credential exists
        stmt = select(Credential).where(
            and_(
                Credential.tenant_id == tenant_id,
                Credential.provider == provider,
                Credential.account == account,
            )
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing credential
            existing.ciphertext = ciphertext
            existing.key_version = key_version
            existing.credential_metadata = credential_metadata
            existing.updated_at = datetime.now(UTC)
            await self.session.flush()
            return existing
        # Create new credential
        credential = Credential(
            tenant_id=tenant_id,
            provider=provider,
            account=account,
            ciphertext=ciphertext,
            key_version=key_version,
            credential_metadata=credential_metadata,
            created_by=created_by,
        )
        self.session.add(credential)
        await self.session.flush()
        return credential

    async def get_by_id(self, tenant_id: str, credential_id: UUID) -> Credential | None:
        """
        Get credential by ID.

        Args:
            tenant_id: Tenant identifier
            credential_id: Credential UUID

        Returns:
            Credential or None
        """
        stmt = select(Credential).where(
            and_(Credential.id == credential_id, Credential.tenant_id == tenant_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self, tenant_id: str, provider: str = None, limit: int = 100, offset: int = 0
    ) -> list[Credential]:
        """
        List credentials for tenant.

        Args:
            tenant_id: Tenant identifier
            provider: Optional filter by provider
            limit: Page size
            offset: Page offset

        Returns:
            List of credentials (without decryption)
        """
        stmt = select(Credential).where(Credential.tenant_id == tenant_id)

        if provider:
            stmt = stmt.where(Credential.provider == provider)

        stmt = stmt.order_by(Credential.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_by_tenant(self, tenant_id: str, provider: str | None = None) -> int:
        """Count credentials for tenant, with optional provider filter."""
        stmt = (
            select(func.count())
            .select_from(Credential)
            .where(Credential.tenant_id == tenant_id)
        )
        if provider:
            stmt = stmt.where(Credential.provider == provider)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def delete(self, tenant_id: str, credential_id: UUID) -> bool:
        """
        Delete credential.

        Args:
            tenant_id: Tenant identifier
            credential_id: Credential UUID

        Returns:
            True if deleted, False if not found
        """
        # Check if credential exists first
        credential = await self.get_by_id(tenant_id, credential_id)
        if not credential:
            return False

        # Use direct DELETE statement for reliable deletion
        # Note: This is more reliable than session.delete() for our AsyncSession setup
        from sqlalchemy import delete as sql_delete

        delete_stmt = sql_delete(Credential).where(
            and_(Credential.id == credential_id, Credential.tenant_id == tenant_id)
        )

        result = await self.session.execute(delete_stmt)
        rows_deleted = result.rowcount

        # Flush to ensure deletion is processed
        await self.session.flush()

        return rows_deleted > 0

    async def associate_with_integration(
        self,
        tenant_id: str,
        integration_id: str,
        credential_id: UUID,
        is_primary: bool = False,
        purpose: str = None,
    ) -> IntegrationCredential:
        """
        Create association between integration and credential.

        Args:
            tenant_id: Tenant identifier
            integration_id: Integration identifier
            credential_id: Credential UUID
            is_primary: Primary credential flag
            purpose: Usage purpose (read/write/admin)

        Returns:
            Created association
        """
        # Check if association already exists
        stmt = select(IntegrationCredential).where(
            and_(
                IntegrationCredential.tenant_id == tenant_id,
                IntegrationCredential.integration_id == integration_id,
                IntegrationCredential.credential_id == credential_id,
            )
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing association
            existing.is_primary = is_primary
            existing.purpose = purpose
            await self.session.flush()
            return existing
        # Create new association
        association = IntegrationCredential(
            tenant_id=tenant_id,
            integration_id=integration_id,
            credential_id=credential_id,
            is_primary=is_primary,
            purpose=purpose,
        )
        self.session.add(association)
        await self.session.flush()
        return association

    async def list_by_integration(
        self, tenant_id: str, integration_id: str
    ) -> list[IntegrationCredential]:
        """
        List credentials for an integration.

        Args:
            tenant_id: Tenant identifier
            integration_id: Integration identifier

        Returns:
            List of integration-credential associations
        """
        stmt = (
            select(IntegrationCredential)
            .where(
                and_(
                    IntegrationCredential.tenant_id == tenant_id,
                    IntegrationCredential.integration_id == integration_id,
                )
            )
            .options(selectinload(IntegrationCredential.credential))
        )

        result = await self.session.execute(stmt)
        return result.scalars().all()
