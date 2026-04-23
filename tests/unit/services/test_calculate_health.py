"""Unit tests for IntegrationService.calculate_health().

Verifies that the cached Integration.health_status field is read
correctly and mapped to IntegrationHealth responses.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from analysi.services.integration_service import IntegrationService


def _make_integration(*, health_status=None, last_health_check_at=None):
    """Build a mock Integration with the given health fields."""
    integration = MagicMock()
    integration.health_status = health_status
    integration.last_health_check_at = last_health_check_at
    return integration


def _make_service(integration=None):
    """Build an IntegrationService with a mocked repo."""
    service = IntegrationService.__new__(IntegrationService)
    repo = AsyncMock()
    repo.get_integration.return_value = integration
    service.integration_repo = repo
    service.credential_repo = AsyncMock()
    return service


@pytest.mark.asyncio
class TestCalculateHealth:
    """Tests for calculate_health() reading the cached field."""

    async def test_healthy_status(self):
        """health_status='healthy' → IntegrationHealth(status='healthy')."""
        now = datetime.now(UTC)
        integration = _make_integration(
            health_status="healthy", last_health_check_at=now
        )
        service = _make_service(integration)

        result = await service.calculate_health("t", "int-1", integration=integration)

        assert result.status == "healthy"
        assert result.message == "Integration is healthy"
        assert result.last_successful_run == now

    async def test_unhealthy_status(self):
        """health_status='unhealthy' → IntegrationHealth(status='unhealthy')."""
        integration = _make_integration(health_status="unhealthy")
        service = _make_service(integration)

        result = await service.calculate_health("t", "int-1", integration=integration)

        assert result.status == "unhealthy"
        assert result.message == "Integration is unhealthy"

    async def test_unknown_status(self):
        """health_status='unknown' → IntegrationHealth(status='unknown')."""
        integration = _make_integration(health_status="unknown")
        service = _make_service(integration)

        result = await service.calculate_health("t", "int-1", integration=integration)

        assert result.status == "unknown"
        assert result.message == "Health check could not determine status"

    async def test_null_health_status_returns_unknown(self):
        """health_status=None (no check run yet) → 'unknown'."""
        integration = _make_integration(health_status=None)
        service = _make_service(integration)

        result = await service.calculate_health("t", "int-1", integration=integration)

        assert result.status == "unknown"
        assert result.message == "No health check data available"

    async def test_integration_not_found_returns_unknown(self):
        """Non-existent integration → 'unknown'."""
        service = _make_service(integration=None)

        result = await service.calculate_health("t", "nonexistent")

        assert result.status == "unknown"

    async def test_pre_loaded_integration_skips_db_fetch(self):
        """When integration is passed, no DB call is made."""
        integration = _make_integration(health_status="healthy")
        service = _make_service()

        await service.calculate_health("t", "int-1", integration=integration)

        service.integration_repo.get_integration.assert_not_called()

    async def test_no_integration_param_fetches_from_db(self):
        """When integration is None, fetches from repo."""
        integration = _make_integration(health_status="healthy")
        service = _make_service(integration)

        await service.calculate_health("t", "int-1")

        service.integration_repo.get_integration.assert_called_once_with("t", "int-1")
