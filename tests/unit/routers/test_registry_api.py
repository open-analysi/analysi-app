"""
Unit tests for Registry API endpoints.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Removed unused schema imports - using dicts now


def _mock_request():
    """Create a mock Request with request_id for api_response()."""
    req = MagicMock()
    req.state.request_id = "test-request-id"
    return req


@pytest.mark.asyncio
class TestRegistryEndpoints:
    """Test registry endpoints."""

    @patch("analysi.routers.integrations.get_registry_service")
    @pytest.mark.asyncio
    async def test_list_integration_types(self, mock_get_service):
        """Test listing integration types."""
        from analysi.routers.integrations import list_integration_types

        # Setup mock registry
        mock_registry = AsyncMock()
        mock_get_service.return_value = mock_registry

        # Mock response — unified actions API shape
        expected_integrations = [
            {
                "integration_type": "splunk",
                "display_name": "Splunk",
                "description": "Splunk SIEM integration",
                "action_count": 8,
                "archetypes": ["SIEM", "AlertSource"],
                "priority": 90,
                "integration_id_config": {},
                "requires_credentials": True,
            },
            {
                "integration_type": "echo_edr",
                "display_name": "Echo EDR",
                "description": "Echo EDR integration",
                "action_count": 9,
                "archetypes": ["EDR"],
                "priority": 50,
                "integration_id_config": {},
                "requires_credentials": True,
            },
        ]
        mock_registry.list_integrations.return_value = expected_integrations

        # Call endpoint
        result = await list_integration_types(
            tenant="test-tenant", request=_mock_request(), registry=mock_registry
        )

        # Verify — result.data contains Pydantic models, compare as dicts
        assert [item.model_dump() for item in result.data] == expected_integrations
        mock_registry.list_integrations.assert_called_once()

    @patch("analysi.routers.integrations.get_registry_service")
    @pytest.mark.asyncio
    async def test_get_integration_type(self, mock_get_service):
        """Test getting a specific integration."""
        from analysi.routers.integrations import get_integration_type

        # Setup mock registry
        mock_registry = AsyncMock()
        mock_get_service.return_value = mock_registry

        # Mock response — unified actions API shape
        expected_integration = {
            "integration_type": "splunk",
            "display_name": "Splunk",
            "description": "Splunk SIEM integration",
            "credential_schema": {},
            "settings_schema": {},
            "integration_id_config": {},
            "requires_credentials": True,
            "archetypes": ["SIEM", "AlertSource"],
            "priority": 90,
            "archetype_mappings": {},
            "actions": [
                {
                    "action_id": "pull_alerts",
                    "name": "Pull Alerts",
                    "description": "Pull alerts from Splunk",
                    "categories": ["alert_ingestion"],
                    "cy_name": "pull_alerts",
                    "enabled": True,
                    "params_schema": {},
                    "result_schema": {},
                },
                {
                    "action_id": "health_check",
                    "name": "Health Check",
                    "description": "Check API connectivity",
                    "categories": ["health_monitoring"],
                    "cy_name": "health_check",
                    "enabled": True,
                    "params_schema": {},
                    "result_schema": {},
                },
            ],
        }
        mock_registry.get_integration.return_value = expected_integration

        # Call endpoint
        result = await get_integration_type(
            tenant="test-tenant",
            integration_type="splunk",
            request=_mock_request(),
            registry=mock_registry,
        )

        # Verify — result.data is a Pydantic model, compare as dict
        assert result.data.model_dump() == expected_integration
        mock_registry.get_integration.assert_called_once_with("splunk")

    @patch("analysi.routers.integrations.get_registry_service")
    @pytest.mark.asyncio
    async def test_list_integration_types_empty(self, mock_get_service):
        """Test listing integrations returns empty list when none available."""
        from analysi.routers.integrations import list_integration_types

        # Setup mock registry
        mock_registry = AsyncMock()
        mock_get_service.return_value = mock_registry
        mock_registry.list_integrations.return_value = []

        # Call endpoint
        result = await list_integration_types(
            tenant="test-tenant", request=_mock_request(), registry=mock_registry
        )

        # Verify
        assert result.data == []
        mock_registry.list_integrations.assert_called_once()
