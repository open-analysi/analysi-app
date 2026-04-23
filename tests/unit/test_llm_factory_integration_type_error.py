"""
Test to reproduce the integration_type parameter error in LangChainFactory.

This test reproduces the error:
"IntegrationService.list_integrations() got an unexpected keyword argument 'integration_type'"
"""

from unittest.mock import AsyncMock, Mock

import pytest

from analysi.services.integration_service import IntegrationService
from analysi.services.llm_factory import LangChainFactory
from analysi.services.vault_client import VaultClient


class TestLLMFactoryIntegrationTypeError:
    """Test class to reproduce integration_type parameter error."""

    @pytest.fixture
    def mock_integration_service(self):
        """Create mock integration service with updated list_integrations signature."""
        mock = Mock(spec=IntegrationService)

        # Mock the updated method signature that accepts tenant_id, enabled, and integration_type
        async def mock_list_integrations(
            tenant_id: str,
            enabled: bool | None = None,
            integration_type: str | None = None,
        ):
            # Return empty list for now - the test just needs to verify no TypeError
            return []

        mock.list_integrations = AsyncMock(side_effect=mock_list_integrations)
        return mock

    @pytest.fixture
    def mock_vault_client(self):
        """Create mock vault client."""
        return Mock(spec=VaultClient)

    @pytest.fixture
    def llm_factory(self, mock_integration_service, mock_vault_client):
        """Create LangChainFactory with mocked dependencies."""
        return LangChainFactory(
            integration_service=mock_integration_service, vault_client=mock_vault_client
        )

    @pytest.mark.asyncio
    async def test_get_primary_llm_works_with_integration_type_parameter(
        self, llm_factory
    ):
        """
        Test that get_primary_llm now works when calling list_integrations with integration_type.

        This verifies the fix for:
        "IntegrationService.list_integrations() got an unexpected keyword argument 'integration_type'"
        """
        tenant_id = "test-tenant"

        # This should now work without raising TypeError
        # Since no integrations are returned, it will fall back to environment variables
        # but we just need to verify no TypeError occurs
        try:
            await llm_factory.get_primary_llm(tenant_id)
        except TypeError as e:
            if "unexpected keyword argument 'integration_type'" in str(e):
                pytest.fail("The integration_type parameter is still not supported")
            else:
                # Other TypeErrors are acceptable (e.g., from environment fallback)
                pass
        except Exception:
            # Other exceptions are fine - we just care about the TypeError being fixed
            pass

        # Verify list_integrations was called with integration_type (openai + gemini)
        calls = llm_factory.integration_service.list_integrations.call_args_list
        call_types = [c.kwargs.get("integration_type") for c in calls]
        assert "openai" in call_types, (
            "Expected list_integrations called with integration_type='openai'"
        )
        assert all(c.kwargs.get("tenant_id") == tenant_id for c in calls)

    @pytest.mark.asyncio
    async def test_cy_llm_functions_call_path_now_works(self, llm_factory):
        """
        Test that the call path from Cy LLM functions now works.

        This simulates the call path:
        llm_run -> _get_or_create_primary_llm -> get_primary_llm -> list_integrations
        """
        tenant_id = "default"

        # This call path should now work without the integration_type TypeError
        try:
            await llm_factory.get_primary_llm(tenant_id)
        except TypeError as e:
            if "unexpected keyword argument 'integration_type'" in str(e):
                pytest.fail(
                    "The integration_type parameter error still occurs in the Cy call path"
                )
            else:
                # Other TypeErrors are acceptable
                pass
        except Exception:
            # Other exceptions are fine - we just care about the specific TypeError being fixed
            pass

        # Verify list_integrations was called with integration_type (openai + gemini)
        calls = llm_factory.integration_service.list_integrations.call_args_list
        call_types = [c.kwargs.get("integration_type") for c in calls]
        assert "openai" in call_types, (
            "Expected list_integrations called with integration_type='openai'"
        )
        assert all(c.kwargs.get("tenant_id") == tenant_id for c in calls)
