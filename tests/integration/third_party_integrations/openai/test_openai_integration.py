"""
Integration tests for OpenAI framework integration.

End-to-end tests for OpenAI integration via Naxos framework.
Following TDD - these tests will fail until implementations are complete.
"""

import pytest

from analysi.integrations.framework.registry import (
    IntegrationRegistryService as IntegrationRegistry,
)
from analysi.services.integration_service import IntegrationService


@pytest.mark.integration
@pytest.mark.asyncio
class TestOpenAIIntegrationEndToEnd:
    """End-to-end integration tests for OpenAI."""

    @pytest.mark.asyncio
    async def test_openai_discovered_by_registry(self):
        """Test: Registry returns OpenAI with AI archetype.

        Goal: Ensure OpenAI discovered with newly added AI archetype.
        """
        registry = IntegrationRegistry()

        # List all integrations
        integrations = registry.list_integrations()

        # Find OpenAI
        openai = next((i for i in integrations if i.id == "openai"), None)

        assert openai is not None, "OpenAI should be discovered by registry"
        assert openai.name == "OpenAI"

        # Verify AI archetype
        assert "AI" in openai.archetypes, (
            f"OpenAI should have AI archetype, got {openai.archetypes}"
        )

        # Verify priority
        assert openai.priority == 80, (
            f"OpenAI should have priority 80, got {openai.priority}"
        )

        # Should have 4 actions (health_check, llm_run, llm_chat, llm_embed)
        assert len(openai.actions) == 4, (
            f"OpenAI should have 4 actions, got {len(openai.actions)}"
        )

    @pytest.mark.skip(
        reason="IntegrationRepository create_integration not yet implemented for framework integrations"
    )
    @pytest.mark.asyncio
    async def test_execute_openai_health_check_end_to_end(self, db_session):
        """Test: Execute OpenAI health_check end-to-end.

        Goal: End-to-end test of OpenAI health check.
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        from analysi.repositories.integration_repository import IntegrationRepository

        integration_repo = IntegrationRepository(db_session)

        # Create OpenAI integration
        from uuid import uuid4

        tenant_id = "test-tenant-openai"
        integration_id = str(uuid4())

        await integration_repo.create_integration(
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="openai",
            name="Test OpenAI",
            settings={"api_url": "https://api.openai.com/v1", "default_model": "gpt-4"},
            credential_id=None,  # Use stub credentials
        )

        # Execute health_check via IntegrationService with mocked httpx client
        service = IntegrationService(db_session)

        # Mock httpx client to avoid actual API calls
        with patch(
            "analysi.integrations.framework.integrations.openai.actions.httpx.AsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": [{"id": "gpt-4"}]}
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            result = await service.execute_action(
                tenant_id=tenant_id,
                integration_id=integration_id,
                integration_type="openai",
                action_id="health_check",
                params={},
            )

            # Should execute via framework
            assert result["status"] == "success"
            assert "models_available" in result
            assert result["models_available"] == 1  # Mocked 1 model
            assert "endpoint" in result


@pytest.mark.integration
@pytest.mark.asyncio
class TestRegistryListIntegrations:
    """Test registry list_integrations includes all framework integrations."""

    @pytest.mark.asyncio
    async def test_registry_lists_all_framework_integrations(self):
        """Test: Registry list_integrations includes all 3 integrations (Splunk, OpenAI, Echo EDR).

        Goal: Verify registry lists all 3 integrations.
        """
        registry = IntegrationRegistry()
        integrations = registry.list_integrations()

        integration_ids = [i.id for i in integrations]

        # Should have at least these 4
        assert "splunk" in integration_ids, "Should have Splunk"
        assert "openai" in integration_ids, "Should have OpenAI"
        assert "gemini" in integration_ids, "Should have Gemini"
        assert "echo_edr" in integration_ids, "Should have Echo EDR"

        # Verify archetypes
        splunk = next(i for i in integrations if i.id == "splunk")
        openai = next(i for i in integrations if i.id == "openai")
        echo_edr = next(i for i in integrations if i.id == "echo_edr")

        # Check archetypes
        assert "SIEM" in splunk.archetypes
        assert "AI" in openai.archetypes
        assert "EDR" in echo_edr.archetypes

    @pytest.mark.asyncio
    async def test_registry_handles_unknown_integration_type(self):
        """Test: Registry handles unknown integration type.

        Goal: Ensure registry returns None/error for unknown integration.
        """
        registry = IntegrationRegistry()

        # Try to get unknown integration (not async)
        result = registry.get_integration("unknown_integration_type_xyz")

        # Should return None or handle gracefully
        assert result is None, "Should return None for unknown integration"
