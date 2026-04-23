"""Unit test: schedules must be enabled when integration is created with enabled=True.

Reproduces the bug where create_integration() calls _create_managed_resources()
(which creates schedules with enabled=False) but never calls
cascade_enable_schedules() when the integration starts enabled.

Project Symi.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from analysi.schemas.integration import IntegrationCreate


def _make_integration(*, enabled: bool = True):
    """Create a mock Integration model."""
    integration = MagicMock()
    integration.integration_id = f"splunk-{uuid4().hex[:8]}"
    integration.integration_type = "splunk"
    integration.tenant_id = "test-tenant"
    integration.name = "Test Splunk"
    integration.description = "Test"
    integration.enabled = enabled
    integration.settings = {}
    integration.created_at = MagicMock()
    integration.updated_at = MagicMock()
    integration.health_status = None
    integration.last_health_check_at = None
    return integration


def _make_manifest():
    """Create a mock manifest with no archetypes."""
    manifest = MagicMock()
    manifest.archetypes = []
    return manifest


@pytest.mark.asyncio
class TestScheduleEnableOnCreate:
    """Verify that create_integration enables schedules when integration starts enabled."""

    @patch("analysi.services.integration_service.get_registry")
    async def test_cascade_enable_called_when_created_enabled(self, mock_registry):
        """BUG: create_integration(enabled=True) must call cascade_enable_schedules."""
        from analysi.services.integration_service import IntegrationService

        # Setup registry
        manifest = _make_manifest()
        mock_registry.return_value.get_integration.return_value = manifest
        mock_registry.return_value.list_by_archetype.return_value = []

        # Setup service with mocked repo
        service = IntegrationService.__new__(IntegrationService)
        service.integration_repo = AsyncMock()
        mock_integration = _make_integration(enabled=True)
        service.integration_repo.get_integration.return_value = None  # not found
        service.integration_repo.create_integration.return_value = mock_integration
        service.integration_repo.session = AsyncMock()

        # Mock the internal methods
        service._create_managed_resources = AsyncMock()
        service.calculate_health = AsyncMock(
            return_value={"status": "unknown", "last_successful_run": None}
        )

        data = IntegrationCreate(
            integration_id=mock_integration.integration_id,
            integration_type="splunk",
            name="Test Splunk",
            enabled=True,
        )

        with patch(
            "analysi.services.task_factory.cascade_enable_schedules",
            new_callable=AsyncMock,
        ) as mock_cascade:
            mock_cascade.return_value = 1

            await service.create_integration("test-tenant", data)

            # The cascade MUST be called when integration is created enabled
            mock_cascade.assert_called_once_with(
                service.integration_repo.session,
                "test-tenant",
                mock_integration.integration_id,
            )

    @patch("analysi.services.integration_service.get_registry")
    async def test_cascade_enable_not_called_when_created_disabled(self, mock_registry):
        """No cascade when integration starts disabled (schedules stay disabled)."""
        from analysi.services.integration_service import IntegrationService

        # Setup registry
        manifest = _make_manifest()
        mock_registry.return_value.get_integration.return_value = manifest
        mock_registry.return_value.list_by_archetype.return_value = []

        # Setup service
        service = IntegrationService.__new__(IntegrationService)
        service.integration_repo = AsyncMock()
        mock_integration = _make_integration(enabled=False)
        service.integration_repo.get_integration.return_value = None  # not found
        service.integration_repo.create_integration.return_value = mock_integration
        service.integration_repo.session = AsyncMock()

        service._create_managed_resources = AsyncMock()
        service.calculate_health = AsyncMock(
            return_value={"status": "unknown", "last_successful_run": None}
        )

        data = IntegrationCreate(
            integration_id=mock_integration.integration_id,
            integration_type="splunk",
            name="Test Splunk",
            enabled=False,
        )

        with patch(
            "analysi.services.task_factory.cascade_enable_schedules",
            new_callable=AsyncMock,
        ) as mock_cascade:
            await service.create_integration("test-tenant", data)

            # Cascade should NOT be called when integration starts disabled
            mock_cascade.assert_not_called()
