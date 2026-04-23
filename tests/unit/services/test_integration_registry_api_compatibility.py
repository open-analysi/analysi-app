"""
Test registry API compatibility with unified actions backend.

Validates that IntegrationRegistryService returns the correct shape
after the Symi unification (no more connectors/tools split).
"""

import pytest

from analysi.services.integration_registry_service import IntegrationRegistryService


class TestRegistryAPICompatibility:
    """Test registry service returns unified actions API contract."""

    @pytest.mark.asyncio
    async def test_list_integrations_returns_unified_format(self):
        """Verify list_integrations returns unified actions format."""
        registry = IntegrationRegistryService()
        integrations = await registry.list_integrations()

        # Should return list
        assert isinstance(integrations, list)
        assert len(integrations) >= 1  # At least Echo EDR

        # Each integration should have the unified format
        for integration in integrations:
            assert "integration_type" in integration
            assert "display_name" in integration
            assert "description" in integration
            assert "action_count" in integration
            assert isinstance(integration["action_count"], int)
            assert integration["action_count"] >= 0
            assert "archetypes" in integration
            assert "priority" in integration
            assert isinstance(integration["archetypes"], list)
            assert isinstance(integration["priority"], int)
            assert "integration_id_config" in integration
            assert "requires_credentials" in integration

            # Old keys must NOT be present
            assert "connectors" not in integration
            assert "tool_count" not in integration
            assert "tools" not in integration

    @pytest.mark.asyncio
    async def test_get_integration_returns_full_details(self):
        """Verify get_integration returns unified actions detail format."""
        registry = IntegrationRegistryService()
        echo = await registry.get_integration("echo_edr")

        assert echo is not None
        assert echo["integration_type"] == "echo_edr"
        assert echo["display_name"] == "Echo EDR"
        assert "description" in echo
        assert "credential_schema" in echo
        assert "settings_schema" in echo

        # credential_schema should have expected structure
        assert isinstance(echo["credential_schema"], dict)
        assert "type" in echo["credential_schema"]
        assert "properties" in echo["credential_schema"]
        assert "api_key" in echo["credential_schema"]["properties"]

        # settings_schema should have expected structure
        assert isinstance(echo["settings_schema"], dict)
        assert "properties" in echo["settings_schema"]
        assert "api_url" in echo["settings_schema"]["properties"]

        # integration_id_config present
        assert "integration_id_config" in echo
        assert isinstance(echo["integration_id_config"], dict)

        # Unified actions list (not separate connectors/tools)
        assert "actions" in echo
        assert isinstance(echo["actions"], list)
        assert len(echo["actions"]) > 0

        # Old keys must NOT be present
        assert "connectors" not in echo
        assert "tools" not in echo

        # Archetype fields
        assert "archetypes" in echo
        assert "priority" in echo
        assert "archetype_mappings" in echo
        assert echo["archetypes"] == ["EDR"]
        assert echo["priority"] == 50
        assert "EDR" in echo["archetype_mappings"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_integration_returns_none(self):
        """Verify querying non-existent integration returns None."""
        registry = IntegrationRegistryService()
        result = await registry.get_integration("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_actions_list_format(self):
        """Verify actions list has expected format for each action."""
        registry = IntegrationRegistryService()
        echo = await registry.get_integration("echo_edr")

        assert echo is not None
        actions = echo["actions"]

        # Should have health_check as one of the actions
        health_check = next(
            (a for a in actions if a["action_id"] == "health_check"), None
        )
        assert health_check is not None

        # Verify all required fields present
        required_fields = [
            "action_id",
            "name",
            "description",
            "categories",
            "cy_name",
            "enabled",
            "params_schema",
            "result_schema",
        ]
        for field in required_fields:
            assert field in health_check, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_backward_compatibility_with_existing_code(self):
        """
        Verify registry works as current code expects.

        This simulates how routers/services currently use the registry.
        """
        registry = IntegrationRegistryService()

        # Pattern 1: List all integrations (used in GET /registry)
        integrations = await registry.list_integrations()
        assert len(integrations) >= 1
        assert integrations[0]["integration_type"]  # Must have this field

        # Pattern 2: Get integration details (used in GET /registry/{type})
        integration = await registry.get_integration("echo_edr")
        assert integration["credential_schema"]["properties"][
            "api_key"
        ]  # UI needs this
        assert integration[
            "integration_id_config"
        ]  # UI needs this for integration_id hints
        assert integration["actions"]  # Unified actions list

    @pytest.mark.asyncio
    async def test_archetype_fields(self):
        """
        Verify archetype information is present on both list and detail views.
        """
        registry = IntegrationRegistryService()

        # List view includes archetypes
        integrations = await registry.list_integrations()
        echo_list = next(i for i in integrations if i["integration_type"] == "echo_edr")
        assert echo_list["archetypes"] == ["EDR"]
        assert echo_list["priority"] == 50

        # Detail view includes archetype mappings
        echo = await registry.get_integration("echo_edr")
        assert echo["archetypes"] == ["EDR"]
        assert echo["priority"] == 50
        assert "EDR" in echo["archetype_mappings"]

        # Verify EDR archetype has required methods mapped
        edr_mappings = echo["archetype_mappings"]["EDR"]
        assert "pull_processes" in edr_mappings
        assert "isolate_host" in edr_mappings
        assert edr_mappings["pull_processes"] == "pull_processes"
        assert edr_mappings["isolate_host"] == "isolate_host"

    @pytest.mark.asyncio
    async def test_action_count_matches_actions_list(self):
        """
        Verify action_count in list view matches len(actions) in detail view.
        """
        registry = IntegrationRegistryService()
        integrations = await registry.list_integrations()

        echo_list = next(i for i in integrations if i["integration_type"] == "echo_edr")
        echo_detail = await registry.get_integration("echo_edr")

        assert echo_list["action_count"] == len(echo_detail["actions"])
