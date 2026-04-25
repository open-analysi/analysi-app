"""Test LangChainFactory.get_llm_by_id method."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from analysi.services.llm_factory import LangChainFactory


@pytest.fixture
def factory():
    """Create factory with mock dependencies."""
    # Clear cache before each test to ensure isolation
    LangChainFactory.clear_cache()
    mock_integration_service = AsyncMock()
    mock_vault_client = MagicMock()
    return LangChainFactory(mock_integration_service, mock_vault_client)


@pytest.fixture
def mock_integration_service(factory):
    """Get mock integration service from factory."""
    return factory.integration_service


@pytest.mark.asyncio
class TestGetLLMById:
    """Test get_llm_by_id functionality."""

    def setup_method(self):
        """Clear cache before each test."""
        from analysi.services.llm_factory import LangChainFactory

        LangChainFactory.clear_cache()

    @pytest.mark.asyncio
    async def test_get_llm_by_id_success(self, factory, mock_integration_service):
        """Test successful LLM retrieval by ID."""
        tenant_id = "tenant-123"
        integration_id = "openai-specific"

        # Mock integration data
        mock_integration = {
            "integration_id": integration_id,
            "integration_type": "openai",
            "settings": {
                "model": "gpt-3.5-turbo",
                "temperature": 0.5,
                "max_tokens": 2048,
            },
            "credential_id": "cred-specific",
        }

        mock_integration_service.get_integration.return_value = mock_integration

        # Mock credential service (imported inside method)
        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            # First call returns credential metadata
            mock_cred_service.get_integration_credentials.return_value = [
                {"id": "12345678-1234-5678-9abc-123456789012", "provider": "openai"}
            ]
            # Second call returns actual credential data
            mock_cred_service.get_credential.return_value = {
                "api_key": "sk-specific-key"
            }
            mock_cred_class.return_value = mock_cred_service

            with patch("analysi.services.llm_factory.ChatOpenAI") as mock_chat:
                mock_llm = MagicMock()
                mock_chat.return_value = mock_llm

                # Get LLM by ID
                llm = await factory.get_llm_by_id(tenant_id, integration_id)

                # Verify correct LLM was created
                assert llm == mock_llm
                mock_chat.assert_called_once_with(
                    model="gpt-3.5-turbo",
                    temperature=0.5,
                    max_tokens=2048,
                    api_key=SecretStr("sk-specific-key"),
                )

                # Verify integration was fetched
                # Called once in get_llm_by_id
                assert mock_integration_service.get_integration.call_count == 1
                mock_integration_service.get_integration.assert_any_call(
                    tenant_id, integration_id
                )

    @pytest.mark.asyncio
    async def test_get_llm_by_id_not_found(self, factory, mock_integration_service):
        """Test error when integration ID doesn't exist."""
        tenant_id = "tenant-123"
        integration_id = "non-existent"

        # Mock integration not found
        mock_integration_service.get_integration.return_value = None

        # Should raise ValueError
        with pytest.raises(ValueError, match=f"Integration {integration_id} not found"):
            await factory.get_llm_by_id(tenant_id, integration_id)

    @pytest.mark.asyncio
    async def test_get_llm_by_id_azure_openai(self, factory, mock_integration_service):
        """Test Azure OpenAI detection and configuration."""
        tenant_id = "tenant-123"
        integration_id = "azure-openai"

        # Mock Azure OpenAI integration
        mock_integration = {
            "integration_id": integration_id,
            "integration_type": "openai",
            "settings": {
                "model": "gpt-4",
                "deployment_name": "my-gpt4-deployment",
                "api_url": "https://my-resource.openai.azure.com/v1",
                "api_version": "2024-02-01",
                "temperature": 0.3,
            },
            "credential_id": "cred-azure",
        }

        mock_integration_service.get_integration.return_value = mock_integration

        # Mock credential service (imported inside method)
        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            # First call returns credential metadata
            mock_cred_service.get_integration_credentials.return_value = [
                {"id": "12345678-1234-5678-9abc-123456789012", "provider": "openai"}
            ]
            # Second call returns actual credential data
            mock_cred_service.get_credential.return_value = {"api_key": "azure-key-123"}
            mock_cred_class.return_value = mock_cred_service

            with patch("analysi.services.llm_factory.AzureChatOpenAI") as mock_azure:
                mock_llm = MagicMock()
                mock_azure.return_value = mock_llm

                # Get Azure LLM by ID
                llm = await factory.get_llm_by_id(tenant_id, integration_id)

                # Verify Azure LLM was created
                assert llm == mock_llm
                mock_azure.assert_called_once_with(
                    azure_endpoint="https://my-resource.openai.azure.com",
                    api_key=SecretStr("azure-key-123"),
                    api_version="2024-02-01",
                    azure_deployment="my-gpt4-deployment",
                    temperature=0.3,
                    max_tokens=4096,  # Default
                )

    @pytest.mark.asyncio
    async def test_get_llm_by_id_custom_base_url(
        self, factory, mock_integration_service
    ):
        """Test custom base URL configuration."""
        tenant_id = "tenant-123"
        integration_id = "custom-openai"

        # Mock custom OpenAI-compatible endpoint
        mock_integration = {
            "integration_id": integration_id,
            "integration_type": "openai",
            "settings": {
                "model": "llama-70b",
                "api_url": "https://custom-llm-provider.com/v1",
                "temperature": 0.8,
            },
            "credential_id": "cred-custom",
        }

        mock_integration_service.get_integration.return_value = mock_integration

        # Mock credential service (imported inside method)
        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            # First call returns credential metadata
            mock_cred_service.get_integration_credentials.return_value = [
                {"id": "12345678-1234-5678-9abc-123456789012", "provider": "openai"}
            ]
            # Second call returns actual credential data
            mock_cred_service.get_credential.return_value = {"api_key": "custom-key"}
            mock_cred_class.return_value = mock_cred_service

            with patch("analysi.services.llm_factory.ChatOpenAI") as mock_chat:
                mock_llm = MagicMock()
                mock_chat.return_value = mock_llm

                # Get LLM with custom URL
                llm = await factory.get_llm_by_id(tenant_id, integration_id)

                # Verify custom base_url was used
                assert llm == mock_llm
                mock_chat.assert_called_once_with(
                    model="llama-70b",
                    temperature=0.8,
                    max_tokens=4096,
                    api_key=SecretStr("custom-key"),
                    base_url="https://custom-llm-provider.com/v1",
                )

    @pytest.mark.asyncio
    async def test_get_llm_by_id_missing_credentials(
        self, factory, mock_integration_service
    ):
        """Test error when credentials are missing."""
        tenant_id = "tenant-123"
        integration_id = "no-creds"

        # Mock integration without credential_id
        mock_integration = {
            "integration_id": integration_id,
            "integration_type": "openai",
            "settings": {"model": "gpt-4"},
            "credential_id": None,
        }

        mock_integration_service.get_integration.return_value = mock_integration

        # Mock credential service to return empty list (no credentials)
        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            # Return empty list for credential metadata
            mock_cred_service.get_integration_credentials.return_value = []
            mock_cred_class.return_value = mock_cred_service

            # Should raise ValueError about missing credentials
            with pytest.raises(ValueError, match="No credentials configured"):
                await factory.get_llm_by_id(tenant_id, integration_id)

    @pytest.mark.asyncio
    async def test_multiple_models_same_tenant(self, factory, mock_integration_service):
        """Test tenant can access multiple different models by ID."""
        tenant_id = "tenant-multi"

        # Define different model configurations
        models = {
            "fast-model": {
                "integration_id": "fast-model",
                "integration_type": "openai",
                "settings": {"model": "gpt-3.5-turbo", "temperature": 0.9},
                "credential_id": "cred-1",
            },
            "accurate-model": {
                "integration_id": "accurate-model",
                "integration_type": "openai",
                "settings": {"model": "gpt-4", "temperature": 0.1},
                "credential_id": "cred-2",
            },
        }

        # Mock integration service to return appropriate model
        mock_integration_service.get_integration.side_effect = lambda t, i: models.get(
            i
        )

        # Mock credential service (imported inside method)
        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            # First call returns credential metadata
            mock_cred_service.get_integration_credentials.return_value = [
                {"id": "12345678-1234-5678-9abc-123456789012", "provider": "openai"}
            ]
            # Second call returns actual credential data
            mock_cred_service.get_credential.return_value = {"api_key": "sk-test"}
            mock_cred_class.return_value = mock_cred_service

            with patch("analysi.services.llm_factory.ChatOpenAI") as mock_chat:
                mock_chat.return_value = MagicMock()

                # Get different models
                await factory.get_llm_by_id(tenant_id, "fast-model")
                await factory.get_llm_by_id(tenant_id, "accurate-model")

                # Verify different configurations were used
                calls = mock_chat.call_args_list
                assert len(calls) == 2

                # First call - fast model
                assert calls[0][1]["model"] == "gpt-3.5-turbo"
                assert calls[0][1]["temperature"] == 0.9

                # Second call - accurate model
                assert calls[1][1]["model"] == "gpt-4"
                assert calls[1][1]["temperature"] == 0.1
