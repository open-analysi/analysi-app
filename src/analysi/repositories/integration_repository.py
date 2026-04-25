"""
Repository for Integration operations.

Health is derived from TaskRun data via managed health check Tasks.
"""

from datetime import UTC, datetime

from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.integration import Integration


class IntegrationRepository:
    """Repository for integration operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_integration(
        self,
        tenant_id: str,
        integration_id: str,
        integration_type: str,
        name: str,
        description: str | None = None,
        settings: dict | None = None,
        enabled: bool = True,
    ) -> Integration:
        """Create a new integration."""
        integration = Integration(
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type=integration_type,
            name=name,
            description=description,
            settings=settings or {},
            enabled=enabled,
        )
        self.session.add(integration)
        await self.session.flush()
        return integration

    async def list_integrations(
        self,
        tenant_id: str,
        enabled: bool | None = None,
        integration_type: str | None = None,
    ) -> list[Integration]:
        """List all integrations for a tenant, optionally filtered."""
        stmt = select(Integration).where(Integration.tenant_id == tenant_id)

        if enabled is not None:
            stmt = stmt.where(Integration.enabled == enabled)

        if integration_type is not None:
            stmt = stmt.where(Integration.integration_type == integration_type)

        stmt = stmt.order_by(Integration.created_at.desc())

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_integration(
        self, tenant_id: str, integration_id: str
    ) -> Integration | None:
        """Get integration by ID."""
        stmt = select(Integration).where(
            and_(
                Integration.tenant_id == tenant_id,
                Integration.integration_id == integration_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_integration(
        self, tenant_id: str, integration_id: str, updates: dict
    ) -> Integration | None:
        """Update an integration."""
        updates["updated_at"] = datetime.now(UTC)

        stmt = (
            update(Integration)
            .where(
                and_(
                    Integration.tenant_id == tenant_id,
                    Integration.integration_id == integration_id,
                )
            )
            .values(**updates)
            .returning(Integration)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one_or_none()

    async def update_health_status(
        self,
        tenant_id: str,
        integration_id: str,
        health_status: str,
        last_health_check_at: datetime,
    ) -> None:
        """Persist cached health status from a health check TaskRun."""
        stmt = (
            update(Integration)
            .where(
                and_(
                    Integration.tenant_id == tenant_id,
                    Integration.integration_id == integration_id,
                )
            )
            .values(
                health_status=health_status,
                last_health_check_at=last_health_check_at,
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def delete_integration(self, tenant_id: str, integration_id: str) -> bool:
        """Delete an integration and cascade delete related credentials."""
        from analysi.models.credential import Credential, IntegrationCredential

        # Get all credential IDs associated with this integration
        cred_select = select(IntegrationCredential.credential_id).where(
            and_(
                IntegrationCredential.tenant_id == tenant_id,
                IntegrationCredential.integration_id == integration_id,
            )
        )
        cred_result = await self.session.execute(cred_select)
        credential_ids = [row[0] for row in cred_result.fetchall()]

        # Delete all credential associations for this integration
        cred_assoc_stmt = delete(IntegrationCredential).where(
            and_(
                IntegrationCredential.tenant_id == tenant_id,
                IntegrationCredential.integration_id == integration_id,
            )
        )
        await self.session.execute(cred_assoc_stmt)

        # Delete the actual credentials themselves
        if credential_ids:
            cred_delete_stmt = delete(Credential).where(
                and_(
                    Credential.tenant_id == tenant_id,
                    Credential.id.in_(credential_ids),
                )
            )
            await self.session.execute(cred_delete_stmt)

        # Delete the integration itself
        stmt = delete(Integration).where(
            and_(
                Integration.tenant_id == tenant_id,
                Integration.integration_id == integration_id,
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def get_integration_settings(
        self, tenant_id: str, integration_id: str
    ) -> dict | None:
        """Get integration settings."""
        integration = await self.get_integration(tenant_id, integration_id)
        if not integration:
            return None
        return integration.settings or {}
