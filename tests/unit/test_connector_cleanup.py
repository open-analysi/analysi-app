"""Unit tests for connector removal and cleanup.

Verifies that old connector-specific code has been properly removed
and that the new simplified IntegrationService works correctly.
"""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
class TestIntegrationServiceSimplified:
    """Test that IntegrationService works without run_repo/schedule_repo."""

    async def test_integration_service_constructor_no_run_repo(self):
        """IntegrationService can be constructed with just integration_repo."""
        from analysi.services.integration_service import IntegrationService

        mock_repo = AsyncMock()
        # New constructor: only integration_repo required, credential_repo optional
        service = IntegrationService(integration_repo=mock_repo)
        assert service.integration_repo is mock_repo

    async def test_integration_service_constructor_with_credential_repo(self):
        """IntegrationService accepts optional credential_repo."""
        from analysi.services.integration_service import IntegrationService

        mock_repo = AsyncMock()
        mock_cred_repo = AsyncMock()
        service = IntegrationService(
            integration_repo=mock_repo,
            credential_repo=mock_cred_repo,
        )
        assert service.credential_repo is mock_cred_repo

    async def test_integration_service_still_has_core_methods(self):
        """IntegrationService still exposes list, get, create, update, delete."""
        from analysi.services.integration_service import IntegrationService

        mock_repo = AsyncMock()
        service = IntegrationService(integration_repo=mock_repo)

        assert hasattr(service, "list_integrations")
        assert hasattr(service, "get_integration")
        assert hasattr(service, "create_integration")
        assert hasattr(service, "update_integration")
        assert hasattr(service, "delete_integration")

    async def test_old_methods_removed(self):
        """Old connector-specific methods are gone from IntegrationService."""
        from analysi.services.integration_service import IntegrationService

        mock_repo = AsyncMock()
        service = IntegrationService(integration_repo=mock_repo)

        # These methods should not exist anymore
        assert not hasattr(service, "create_run")
        assert not hasattr(service, "update_run_status")
        assert not hasattr(service, "cancel_run")
        assert not hasattr(service, "validate_status_transition")
        assert not hasattr(service, "create_schedule")
        assert not hasattr(service, "update_schedule")
        assert not hasattr(service, "delete_schedule")
        assert not hasattr(service, "get_schedule_runs")


class TestRegistryServiceConnectorMethodsRemoved:
    """Test that connector-specific methods are removed from the registry service."""

    def test_get_connector_removed(self):
        """get_connector is no longer on IntegrationRegistryService."""
        from analysi.services.integration_registry_service import (
            IntegrationRegistryService,
        )

        registry = IntegrationRegistryService()
        assert not hasattr(registry, "get_connector")

    def test_get_connector_credential_scopes_removed(self):
        """get_connector_credential_scopes is no longer on IntegrationRegistryService."""
        from analysi.services.integration_registry_service import (
            IntegrationRegistryService,
        )

        registry = IntegrationRegistryService()
        assert not hasattr(registry, "get_connector_credential_scopes")

    def test_get_default_schedule_removed(self):
        """get_default_schedule is no longer on IntegrationRegistryService."""
        from analysi.services.integration_registry_service import (
            IntegrationRegistryService,
        )

        registry = IntegrationRegistryService()
        assert not hasattr(registry, "get_default_schedule")

    def test_validate_connector_params_removed(self):
        """validate_connector_params is no longer on IntegrationRegistryService."""
        from analysi.services.integration_registry_service import (
            IntegrationRegistryService,
        )

        registry = IntegrationRegistryService()
        assert not hasattr(registry, "validate_connector_params")

    def test_format_connectors_removed(self):
        """_format_connectors is no longer on IntegrationRegistryService."""
        from analysi.services.integration_registry_service import (
            IntegrationRegistryService,
        )

        registry = IntegrationRegistryService()
        assert not hasattr(registry, "_format_connectors")

    def test_manifest_to_phase16_format_removed(self):
        """_manifest_to_phase16_format is no longer on IntegrationRegistryService."""
        from analysi.services.integration_registry_service import (
            IntegrationRegistryService,
        )

        registry = IntegrationRegistryService()
        assert not hasattr(registry, "_manifest_to_phase16_format")


class TestConnectorModelsRemoved:
    """Test that connector-specific model helpers are removed."""

    def test_connector_categories_removed(self):
        """CONNECTOR_CATEGORIES constant is removed from models."""
        from analysi.integrations.framework import models as models_mod

        assert not hasattr(models_mod, "CONNECTOR_CATEGORIES")

    def test_is_connector_action_removed(self):
        """is_connector_action helper is removed from models."""
        from analysi.integrations.framework import models as models_mod

        assert not hasattr(models_mod, "is_connector_action")


class TestOldModulesRemoved:
    """Test that old connector-specific modules/classes are removed."""

    def test_old_schedule_executor_removed(self):
        """Importing the old schedule_executor module raises ImportError."""
        with pytest.raises(ImportError):
            from analysi.integrations.schedule_executor import (  # noqa: F401
                schedule_executor,
            )

    def test_parse_schedule_interval_in_new_location(self):
        """parse_schedule_interval is available in scheduler.interval."""
        from analysi.scheduler.interval import parse_schedule_interval

        assert parse_schedule_interval("60s") == 60
        assert parse_schedule_interval("5m") == 300
        assert parse_schedule_interval("1h") == 3600

    def test_connector_schemas_removed(self):
        """Old connector-specific schemas are no longer importable."""
        from analysi.schemas import integration as schema_mod

        # These should not exist anymore
        assert not hasattr(schema_mod, "ConnectorTypeResponse")
        assert not hasattr(schema_mod, "IntegrationRunCreate")
        assert not hasattr(schema_mod, "IntegrationRunResponse")
        assert not hasattr(schema_mod, "IntegrationRunUpdate")
        assert not hasattr(schema_mod, "IntegrationRunStatus")
        assert not hasattr(schema_mod, "IntegrationScheduleCreate")
        assert not hasattr(schema_mod, "IntegrationScheduleUpdate")
        assert not hasattr(schema_mod, "IntegrationScheduleResponse")
        assert not hasattr(schema_mod, "IntegrationTypeResponse")

    def test_old_repository_removed(self):
        """IntegrationRunRepository and IntegrationScheduleRepository are gone."""
        with pytest.raises(ImportError):
            from analysi.repositories.integration_run_repository import (  # noqa: F401
                IntegrationRunRepository,
            )

    def test_old_models_removed(self):
        """IntegrationRun and IntegrationSchedule models are gone."""
        from analysi.models import integration as models_mod

        assert not hasattr(models_mod, "IntegrationRun")
        assert not hasattr(models_mod, "IntegrationSchedule")

    def test_integration_model_still_exists(self):
        """The core Integration model is still available."""
        from analysi.models.integration import Integration

        assert Integration is not None
        assert Integration.__tablename__ == "integrations"


class TestRouterCleanup:
    """Test that connector endpoints are removed from the router."""

    def test_no_connector_endpoints_in_router(self):
        """No /connectors/ paths in the integrations router."""
        from analysi.routers.integrations import router

        paths = [route.path for route in router.routes]
        connector_paths = [p for p in paths if "/connectors/" in p]
        assert connector_paths == [], f"Found connector paths: {connector_paths}"

    def test_no_connector_runs_endpoint(self):
        """No connector-runs endpoint."""
        from analysi.routers.integrations import router

        paths = [route.path for route in router.routes]
        run_paths = [p for p in paths if "connector-runs" in p]
        assert run_paths == [], f"Found connector-runs paths: {run_paths}"

    def test_no_legacy_runs_endpoint(self):
        """No /{id}/runs endpoint (used IntegrationRun)."""
        from analysi.routers.integrations import router

        paths = [route.path for route in router.routes]
        # The endpoint /{integration_id}/runs should be gone
        legacy_runs = [
            p
            for p in paths
            if p.endswith("/runs") and "/connectors/" not in p and "/managed/" not in p
        ]
        assert legacy_runs == [], f"Found legacy runs paths: {legacy_runs}"

    def test_core_endpoints_still_exist(self):
        """Core CRUD integration endpoints still exist."""
        from analysi.routers.integrations import router

        paths = [route.path for route in router.routes]
        # These must still exist
        assert "/{tenant}/integrations" in paths or any(
            "integrations" in p and "{integration_id}" not in p for p in paths
        )


class TestWorkerCleanup:
    """Test that the integrations worker is cleaned up."""

    def test_worker_no_legacy_cron(self):
        """WorkerSettings.cron_jobs has only execute_due_schedules, no legacy."""
        import os

        os.environ["DISABLE_INTEGRATION_WORKER"] = "false"

        # Re-import to pick up non-disabled cron_jobs
        import importlib

        from analysi.integrations import worker as worker_mod

        importlib.reload(worker_mod)

        from analysi.integrations.worker import WorkerSettings

        # Should have exactly 1 cron job (new executor)
        cron_jobs = WorkerSettings.cron_jobs
        assert len(cron_jobs) == 1, f"Expected 1 cron job, got {len(cron_jobs)}"

    def test_worker_no_run_integration_function(self):
        """run_integration function should be removed from worker module."""
        from analysi.integrations import worker as worker_mod

        assert not hasattr(worker_mod, "run_integration")
