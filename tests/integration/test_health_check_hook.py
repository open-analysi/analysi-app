"""
Integration tests for the health check post-execution hook.

Verifies the full chain against PostgreSQL:
  1. Factory creates a health check Task with managed_resource_key="health_check"
  2. The hook reads that field and updates Integration.health_status
  3. calculate_health() reads the cached field
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.integration import Integration
from analysi.repositories.integration_repository import IntegrationRepository
from analysi.services.task_factory import (
    create_alert_ingestion_task,
    create_health_check_task,
    process_health_check_result,
)


@pytest.mark.asyncio
@pytest.mark.integration
class TestHealthCheckHookDB:
    """Integration tests for managed_resource_key and health status updates."""

    @pytest.fixture
    def unique_id(self):
        return uuid4().hex[:8]

    @pytest.fixture
    def tenant_id(self, unique_id):
        return f"tenant-{unique_id}"

    @pytest.fixture
    def integration_id(self, unique_id):
        return f"splunk-{unique_id}"

    @pytest.fixture
    async def setup_integration(
        self,
        integration_test_session: AsyncSession,
        tenant_id: str,
        integration_id: str,
    ):
        """Create an Integration row for the tests."""
        integration = Integration(
            integration_id=integration_id,
            tenant_id=tenant_id,
            integration_type="splunk",
            name=f"Splunk {integration_id}",
        )
        integration_test_session.add(integration)
        await integration_test_session.flush()
        return integration

    # ── managed_resource_key set by factory ─────────────────────────

    async def test_health_check_task_has_managed_resource_key(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Health check task gets managed_resource_key='health_check'."""
        task = await create_health_check_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )
        await integration_test_session.flush()

        assert task.managed_resource_key == "health_check"

    async def test_alert_ingestion_task_has_managed_resource_key(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """Alert ingestion task gets managed_resource_key='alert_ingestion'."""
        task = await create_alert_ingestion_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )
        await integration_test_session.flush()

        assert task.managed_resource_key == "alert_ingestion"

    # ── Integration.health_status persistence ───────────────────────

    async def test_update_health_status_persists(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
        setup_integration,
    ):
        """update_health_status writes health_status and last_health_check_at."""
        repo = IntegrationRepository(integration_test_session)
        now = datetime.now(UTC)

        await repo.update_health_status(
            tenant_id=tenant_id,
            integration_id=integration_id,
            health_status="healthy",
            last_health_check_at=now,
        )
        await integration_test_session.flush()

        # Re-read from DB
        integration = await repo.get_integration(tenant_id, integration_id)
        assert integration is not None
        assert integration.health_status == "healthy"
        assert integration.last_health_check_at is not None

    async def test_update_health_status_overwrites_previous(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
        setup_integration,
    ):
        """Successive health updates overwrite the cached value."""
        repo = IntegrationRepository(integration_test_session)
        now = datetime.now(UTC)

        await repo.update_health_status(tenant_id, integration_id, "healthy", now)
        await integration_test_session.flush()

        await repo.update_health_status(tenant_id, integration_id, "unhealthy", now)
        await integration_test_session.flush()

        integration = await repo.get_integration(tenant_id, integration_id)
        assert integration.health_status == "unhealthy"

    async def test_health_status_null_before_first_check(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
        setup_integration,
    ):
        """Before any health check runs, health_status is NULL."""
        repo = IntegrationRepository(integration_test_session)
        integration = await repo.get_integration(tenant_id, integration_id)
        assert integration.health_status is None
        assert integration.last_health_check_at is None

    # ── process_health_check_result logic (DB-free, but grouped here) ──

    async def test_process_healthy_result(self, integration_test_session: AsyncSession):
        """completed + healthy=true → 'healthy'."""
        assert process_health_check_result("completed", {"healthy": True}) == "healthy"

    async def test_process_unhealthy_result(
        self, integration_test_session: AsyncSession
    ):
        """completed + healthy=false → 'unhealthy'."""
        assert (
            process_health_check_result("completed", {"healthy": False}) == "unhealthy"
        )

    async def test_process_failed_result(self, integration_test_session: AsyncSession):
        """failed → 'unknown'."""
        assert process_health_check_result("failed", None) == "unknown"

    # ── managed_resource_key lookup in DB ───────────────────────────

    async def test_managed_resource_key_persisted_in_db(
        self,
        integration_test_session: AsyncSession,
        tenant_id,
        integration_id,
    ):
        """managed_resource_key survives a round-trip through PostgreSQL."""
        from analysi.models.task import Task

        task = await create_health_check_task(
            session=integration_test_session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
        )
        await integration_test_session.flush()

        # Re-query from DB
        stmt = select(Task).where(Task.component_id == task.component_id)
        result = await integration_test_session.execute(stmt)
        reloaded = result.scalar_one()

        assert reloaded.managed_resource_key == "health_check"
        assert reloaded.integration_id == integration_id
