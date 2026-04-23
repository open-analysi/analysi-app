"""Integration tests for integration enable/disable functionality."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.component import Component
from analysi.models.integration import Integration
from analysi.models.schedule import Schedule
from analysi.models.task import Task


@pytest.mark.integration
class TestIntegrationEnableDisable:
    """Test integration enable/disable with schedule synchronization."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, AsyncSession]]:
        """Create an async HTTP client for testing with test database."""

        # Override the database dependency to use test database
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        # Create async test client
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield (ac, integration_test_session)

        # Clean up overrides
        app.dependency_overrides.clear()

    @pytest.fixture
    async def test_integration_with_schedules(self, integration_test_session):
        """Create a test integration with multiple schedules."""
        tenant_id = "test-tenant"
        integration_id = f"test-integration-{uuid4().hex[:8]}"

        # Create integration
        integration = Integration(
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
            name="Test Splunk Integration",
            description="Integration for testing enable/disable",
            enabled=True,
            settings={"host": "splunk.test.com", "port": 8089},
        )
        integration_test_session.add(integration)
        await integration_test_session.flush()

        # Create real Component/Task targets so cascade_enable_schedules
        # can verify the target exists (it joins on Component).
        schedules = []
        for label in ["pull_alerts", "health_check"]:
            for i in range(2):
                comp_id = uuid4()
                component = Component(
                    id=comp_id,
                    tenant_id=tenant_id,
                    kind="task",
                    name=f"Test {label} {i}",
                    description="Test task for schedule",
                    version="1.0.0",
                )
                task = Task(
                    component_id=comp_id,
                    directive="test",
                    script="return 'ok'",
                    scope="processing",
                    mode="saved",
                )
                integration_test_session.add(component)
                integration_test_session.add(task)
                await integration_test_session.flush()

                schedule = Schedule(
                    tenant_id=tenant_id,
                    target_type="task",
                    target_id=comp_id,
                    schedule_type="every",
                    schedule_value=f"{(i + 1) * 5}m",
                    origin_type="system",
                    integration_id=integration_id,
                    enabled=True,
                    timezone="UTC",
                    params={"test": f"schedule-{label}-{i}"},
                )
                integration_test_session.add(schedule)
                schedules.append(schedule)

        await integration_test_session.flush()
        await integration_test_session.commit()

        return {
            "tenant_id": tenant_id,
            "integration": integration,
            "schedules": schedules,
        }

    @pytest.mark.asyncio
    async def test_disable_integration_disables_all_schedules(
        self, client, test_integration_with_schedules
    ):
        """Test that disabling an integration atomically disables all its schedules."""
        http_client, session = client
        tenant_id = test_integration_with_schedules["tenant_id"]
        integration = test_integration_with_schedules["integration"]
        schedules = test_integration_with_schedules["schedules"]

        # Verify initial state - all schedules are enabled
        for schedule in schedules:
            await session.refresh(schedule)
            assert schedule.enabled is True

        # Disable the integration via API
        response = await http_client.patch(
            f"/v1/{tenant_id}/integrations/{integration.integration_id}",
            json={"enabled": False},
        )
        assert response.status_code == 200
        result = response.json()["data"]
        assert result["enabled"] is False

        # Commit to ensure changes are persisted
        await session.commit()

        # Query fresh data from database to verify changes

        # Verify integration is disabled
        stmt = select(Integration).where(
            Integration.tenant_id == tenant_id,
            Integration.integration_id == integration.integration_id,
        )
        result = await session.execute(stmt)
        fresh_integration = result.scalar_one()
        assert fresh_integration.enabled is False

        # Verify all schedules are disabled
        stmt = select(Schedule).where(
            Schedule.tenant_id == tenant_id,
            Schedule.integration_id == integration.integration_id,
        )
        result = await session.execute(stmt)
        fresh_schedules = result.scalars().all()

        for schedule in fresh_schedules:
            assert schedule.enabled is False, (
                f"Schedule {schedule.id} should be disabled"
            )

    @pytest.mark.asyncio
    async def test_enable_integration_enables_all_schedules(
        self, client, test_integration_with_schedules
    ):
        """Test that enabling an integration atomically enables all its schedules."""
        http_client, session = client
        tenant_id = test_integration_with_schedules["tenant_id"]
        integration = test_integration_with_schedules["integration"]
        schedules = test_integration_with_schedules["schedules"]

        # First disable the integration
        integration.enabled = False
        for schedule in schedules:
            schedule.enabled = False
        await session.commit()

        # Verify initial state - all schedules are disabled
        for schedule in schedules:
            await session.refresh(schedule)
            assert schedule.enabled is False

        # Enable the integration via API
        response = await http_client.patch(
            f"/v1/{tenant_id}/integrations/{integration.integration_id}",
            json={"enabled": True},
        )
        assert response.status_code == 200
        result = response.json()["data"]
        assert result["enabled"] is True

        # Commit to ensure changes are persisted
        await session.commit()

        # Query fresh data from database to verify changes

        # Verify integration is enabled
        stmt = select(Integration).where(
            Integration.tenant_id == tenant_id,
            Integration.integration_id == integration.integration_id,
        )
        result = await session.execute(stmt)
        fresh_integration = result.scalar_one()
        assert fresh_integration.enabled is True

        # Verify all schedules are enabled
        stmt = select(Schedule).where(
            Schedule.tenant_id == tenant_id,
            Schedule.integration_id == integration.integration_id,
        )
        result = await session.execute(stmt)
        fresh_schedules = result.scalars().all()

        for schedule in fresh_schedules:
            assert schedule.enabled is True, f"Schedule {schedule.id} should be enabled"

    @pytest.mark.asyncio
    async def test_update_without_enabled_field_does_not_affect_schedules(
        self, client, test_integration_with_schedules
    ):
        """Test that updating integration without changing enabled doesn't affect schedules."""
        http_client, session = client
        tenant_id = test_integration_with_schedules["tenant_id"]
        integration = test_integration_with_schedules["integration"]
        schedules = test_integration_with_schedules["schedules"]

        # Disable first schedule manually
        schedules[0].enabled = False
        await session.commit()

        # Update integration name (without touching enabled field)
        response = await http_client.patch(
            f"/v1/{tenant_id}/integrations/{integration.integration_id}",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 200
        result = response.json()["data"]
        assert result["name"] == "Updated Name"

        # Commit to ensure changes are persisted
        await session.commit()

        # Verify schedules maintain their individual enabled states
        await session.refresh(schedules[0])
        assert schedules[0].enabled is False, "First schedule should remain disabled"

        for schedule in schedules[1:]:
            await session.refresh(schedule)
            assert schedule.enabled is True, (
                f"Schedule {schedule.id} should remain enabled"
            )

    @pytest.mark.asyncio
    async def test_atomic_operation_with_database_error(
        self, client, test_integration_with_schedules
    ):
        """Test that enable/disable operations are atomic even with errors."""
        http_client, session = client
        tenant_id = test_integration_with_schedules["tenant_id"]
        integration = test_integration_with_schedules["integration"]
        schedules = test_integration_with_schedules["schedules"]

        # Simulate a database error during schedule update.
        # When session.execute raises inside ASGI middleware, the error propagates
        # as an ExceptionGroup through the Starlette stack rather than returning
        # a clean HTTP 500 response.
        with patch.object(
            session,
            "execute",
            side_effect=[
                # First call succeeds (update integration)
                AsyncMock(),
                # Second call fails (update schedules)
                Exception("Database error"),
            ],
        ):
            with pytest.raises((Exception, ExceptionGroup)):
                await http_client.patch(
                    f"/v1/{tenant_id}/integrations/{integration.integration_id}",
                    json={"enabled": False},
                )

        # Refresh from database to check state
        await session.rollback()
        await session.refresh(integration)

        # Integration should remain in original state due to transaction rollback
        assert integration.enabled is True

        # All schedules should remain enabled
        for schedule in schedules:
            await session.refresh(schedule)
            assert schedule.enabled is True

    @pytest.mark.asyncio
    async def test_integration_with_no_schedules(
        self, client, integration_test_session
    ):
        """Test that enable/disable works for integrations without schedules."""
        http_client, session = client
        tenant_id = "test-tenant"
        integration_id = f"no-schedule-{uuid4().hex[:8]}"

        # Create integration without schedules
        integration = Integration(
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
            name="Integration Without Schedules",
            enabled=True,
            settings={},
        )
        session.add(integration)
        await session.commit()

        # Disable the integration
        response = await http_client.patch(
            f"/v1/{tenant_id}/integrations/{integration_id}", json={"enabled": False}
        )
        assert response.status_code == 200
        result = response.json()["data"]
        assert result["enabled"] is False

        # Verify no errors occurred with no schedules to update
        await session.refresh(integration)
        assert integration.enabled is False

        # Enable the integration
        response = await http_client.patch(
            f"/v1/{tenant_id}/integrations/{integration_id}", json={"enabled": True}
        )
        assert response.status_code == 200
        result = response.json()["data"]
        assert result["enabled"] is True

        await session.refresh(integration)
        assert integration.enabled is True
