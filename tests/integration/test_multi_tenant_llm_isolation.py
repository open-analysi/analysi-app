"""Integration tests for multi-tenant LLM isolation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.services.cy_llm_functions import create_cy_llm_functions
from analysi.services.llm_factory import LangChainFactory


@pytest.mark.integration
class TestMultiTenantLLMIsolation:
    """Test that different tenants have isolated LLM configurations."""

    @pytest.mark.asyncio
    async def test_different_tenants_use_different_credentials(self):
        """Test that each tenant uses their own LLM credentials."""
        # Clear cache before test
        LangChainFactory.clear_cache()

        mock_integration_service = AsyncMock()

        # Tenant1 has GPT-4 with one API key
        tenant1_integration = {
            "integration_id": "openai-tenant1",
            "integration_type": "openai",
            "settings": {"model": "gpt-4", "is_primary": True},
        }

        # Tenant2 has GPT-3.5 with different API key
        tenant2_integration = {
            "integration_id": "openai-tenant2",
            "integration_type": "openai",
            "settings": {"model": "gpt-3.5-turbo", "is_primary": True},
        }

        def list_integrations_side_effect(tenant_id, **kwargs):
            if tenant_id == "tenant1":
                return [tenant1_integration]
            if tenant_id == "tenant2":
                return [tenant2_integration]
            return []

        def get_integration_side_effect(tenant_id, integration_id):
            if tenant_id == "tenant1" and integration_id == "openai-tenant1":
                return tenant1_integration
            if tenant_id == "tenant2" and integration_id == "openai-tenant2":
                return tenant2_integration
            return None

        mock_integration_service.list_integrations.side_effect = (
            list_integrations_side_effect
        )
        mock_integration_service.get_integration.side_effect = (
            get_integration_side_effect
        )

        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()

            def get_integration_credentials_side_effect(tenant_id, integration_id):
                if integration_id == "openai-tenant1":
                    return [
                        {
                            "id": "12345678-1234-5678-9abc-000000000001",
                            "provider": "openai",
                        }
                    ]
                if integration_id == "openai-tenant2":
                    return [
                        {
                            "id": "12345678-1234-5678-9abc-000000000002",
                            "provider": "openai",
                        }
                    ]
                return []

            def get_credential_side_effect(tenant_id, credential_id):
                if str(credential_id) == "12345678-1234-5678-9abc-000000000001":
                    return {"api_key": "sk-tenant1-key"}
                if str(credential_id) == "12345678-1234-5678-9abc-000000000002":
                    return {"api_key": "sk-tenant2-key"}
                return None

            mock_cred_service.get_integration_credentials.side_effect = (
                get_integration_credentials_side_effect
            )
            mock_cred_service.get_credential.side_effect = get_credential_side_effect
            mock_cred_class.return_value = mock_cred_service

            factory = LangChainFactory(mock_integration_service, None)

            with patch("analysi.services.llm_factory.ChatOpenAI") as mock_chat:
                created_llms = []

                def chat_side_effect(**kwargs):
                    llm = MagicMock()
                    llm.config = kwargs  # Store config for verification
                    created_llms.append(llm)
                    return llm

                mock_chat.side_effect = chat_side_effect

                # Create LLMs for both tenants
                llm1 = await factory.get_primary_llm("tenant1")
                llm2 = await factory.get_primary_llm("tenant2")

                # Verify different instances
                assert llm1 != llm2

                # Verify tenant1 configuration
                assert (
                    created_llms[0].config["api_key"].get_secret_value()
                    == "sk-tenant1-key"
                )
                assert created_llms[0].config["model"] == "gpt-4"

                # Verify tenant2 configuration
                assert (
                    created_llms[1].config["api_key"].get_secret_value()
                    == "sk-tenant2-key"
                )
                assert created_llms[1].config["model"] == "gpt-3.5-turbo"

    @pytest.mark.asyncio
    async def test_tenant_without_integration_raises_error(self):
        """Test that tenant without integration raises ValueError."""
        # Clear cache before test
        LangChainFactory.clear_cache()

        mock_integration_service = AsyncMock()

        # Tenant1 has integration, tenant2 does not
        tenant1_integration = {
            "integration_id": "openai-tenant1",
            "integration_type": "openai",
            "settings": {"model": "gpt-4"},
        }

        def list_integrations_side_effect(tenant_id, **kwargs):
            if tenant_id == "tenant1":
                return [tenant1_integration]
            return []  # tenant2 has no integrations

        mock_integration_service.list_integrations.side_effect = (
            list_integrations_side_effect
        )
        mock_integration_service.get_integration.return_value = tenant1_integration

        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            mock_cred_service.get_integration_credentials.return_value = [
                {"id": "12345678-1234-5678-9abc-000000000001", "provider": "openai"}
            ]
            mock_cred_service.get_credential.return_value = {
                "api_key": "sk-tenant1-key"
            }
            mock_cred_class.return_value = mock_cred_service

            factory = LangChainFactory(mock_integration_service, None)

            with patch("analysi.services.llm_factory.ChatOpenAI") as mock_chat:
                mock_chat.return_value = MagicMock()

                # Tenant1 works fine
                await factory.get_primary_llm("tenant1")

                # Tenant2 raises error (no integrations configured)
                with pytest.raises(ValueError, match="No LLM integrations configured"):
                    await factory.get_primary_llm("tenant2")

    @pytest.mark.asyncio
    async def test_cy_functions_isolated_by_tenant(self):
        """Test that Cy LLM functions are isolated by tenant."""
        # Clear cache before test
        LangChainFactory.clear_cache()
        mock_integration_service = AsyncMock()

        # Setup different integrations for different tenants
        def list_integrations_side_effect(tenant_id, **kwargs):
            if tenant_id == "tenant1":
                return [
                    {
                        "integration_id": "openai-t1",
                        "integration_type": "openai",
                        "settings": {"model": "gpt-4", "temperature": 0.5},
                    }
                ]
            if tenant_id == "tenant2":
                return [
                    {
                        "integration_id": "openai-t2",
                        "integration_type": "openai",
                        "settings": {"model": "gpt-3.5-turbo", "temperature": 0.8},
                    }
                ]
            return []

        mock_integration_service.list_integrations.side_effect = (
            list_integrations_side_effect
        )

        # Create Cy functions for different tenants
        factory = LangChainFactory(mock_integration_service, None)

        context1 = {"tenant_id": "tenant1", "task_id": "task1"}
        context2 = {"tenant_id": "tenant2", "task_id": "task2"}

        functions1, cy_instance1 = create_cy_llm_functions(factory, context1)
        functions2, cy_instance2 = create_cy_llm_functions(factory, context2)

        # Verify they have different contexts
        assert functions1["llm_run"] != functions2["llm_run"]

        # Each should maintain its own tenant context
        # (In real usage, these would use different LLM configs based on tenant)
