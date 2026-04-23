"""Unit tests for LangChain factory service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from analysi.services.llm_factory import LangChainFactory


@pytest.mark.asyncio
class TestLangChainFactory:
    """Test LangChain factory for creating LLM instances."""

    @pytest.fixture
    def mock_integration_service(self):
        """Create mock integration service."""
        mock = AsyncMock()
        return mock

    @pytest.fixture
    def mock_vault_client(self):
        """Create mock vault client."""
        mock = MagicMock()
        return mock

    @pytest.fixture
    def factory(self, mock_integration_service, mock_vault_client):
        """Create factory with mocked dependencies."""
        # Clear cache before each test to ensure isolation
        LangChainFactory.clear_cache()
        return LangChainFactory(mock_integration_service, mock_vault_client)

    @pytest.mark.asyncio
    async def test_get_primary_llm_with_marked_primary(
        self, factory, mock_integration_service
    ):
        """Test getting primary LLM when one is marked as primary."""
        # Mock integration data
        mock_integration_service.list_integrations.return_value = [
            {
                "integration_id": "openai-secondary",
                "integration_type": "openai",
                "settings": {"is_primary": False},
            },
            {
                "integration_id": "openai-primary",
                "integration_type": "openai",
                "settings": {
                    "is_primary": True,
                    "model": "gpt-4",
                    "temperature": 0.5,
                    "max_tokens": 4096,
                },
                "credential_id": "cred-123",
            },
        ]

        mock_integration_service.get_integration.return_value = {
            "integration_id": "openai-primary",
            "integration_type": "openai",
            "settings": {
                "is_primary": True,
                "model": "gpt-4",
                "temperature": 0.5,
                "max_tokens": 4096,
            },
            "credential_id": "cred-123",
        }

        # Mock credential service with proper two-step retrieval
        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            # First call returns credential metadata
            mock_cred_service.get_integration_credentials.return_value = [
                {"id": "12345678-1234-5678-9abc-123456789012", "provider": "openai"}
            ]
            # Second call returns actual credential data
            mock_cred_service.get_credential.return_value = {"api_key": "sk-test123"}
            mock_cred_class.return_value = mock_cred_service

            with patch("analysi.services.llm_factory.ChatOpenAI") as mock_chat:
                mock_llm = MagicMock()
                mock_chat.return_value = mock_llm

                result = await factory.get_primary_llm("tenant1")

                assert result == mock_llm
                # API key is now wrapped in SecretStr
                call_args = mock_chat.call_args[1]
                assert call_args["model"] == "gpt-4"
                assert call_args["temperature"] == 0.5
                assert call_args["max_tokens"] == 4096
                assert call_args["api_key"].get_secret_value() == "sk-test123"

    @pytest.mark.asyncio
    async def test_get_primary_llm_uses_first_when_none_marked(
        self, factory, mock_integration_service
    ):
        """Test that first integration is used when none marked as primary."""
        mock_integration_service.list_integrations.return_value = [
            {
                "integration_id": "openai-1",
                "integration_type": "openai",
                "settings": {},
                "credential_id": "cred-123",
            },
            {
                "integration_id": "openai-2",
                "integration_type": "openai",
                "settings": {},
            },
        ]

        mock_integration_service.get_integration.return_value = {
            "integration_id": "openai-1",
            "integration_type": "openai",
            "settings": {},
            "credential_id": "cred-123",
        }

        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            # First call returns credential metadata
            mock_cred_service.get_integration_credentials.return_value = [
                {"id": "12345678-1234-5678-9abc-123456789012", "provider": "openai"}
            ]
            # Second call returns actual credential data
            mock_cred_service.get_credential.return_value = {"api_key": "sk-test123"}
            mock_cred_class.return_value = mock_cred_service

            with patch("analysi.services.llm_factory.ChatOpenAI") as mock_chat:
                mock_llm = MagicMock()
                mock_chat.return_value = mock_llm

                result = await factory.get_primary_llm("tenant1")

                assert result == mock_llm

    @pytest.mark.asyncio
    async def test_get_primary_llm_raises_when_no_integrations(
        self, factory, mock_integration_service
    ):
        """Test error when no integrations configured for tenant."""
        mock_integration_service.list_integrations.return_value = []

        with pytest.raises(ValueError, match="No LLM integrations configured"):
            await factory.get_primary_llm("tenant1")

    @pytest.mark.asyncio
    async def test_get_llm_by_id(self, factory, mock_integration_service):
        """Test getting specific LLM by integration ID."""
        mock_integration_service.get_integration.return_value = {
            "integration_id": "openai-specific",
            "integration_type": "openai",
            "settings": {"model": "gpt-3.5-turbo"},
            "credential_id": "cred-456",
        }

        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            # First call returns credential metadata
            mock_cred_service.get_integration_credentials.return_value = [
                {"id": "12345678-1234-5678-9abc-123456789012", "provider": "openai"}
            ]
            # Second call returns actual credential data
            mock_cred_service.get_credential.return_value = {"api_key": "sk-test456"}
            mock_cred_class.return_value = mock_cred_service

            with patch("analysi.services.llm_factory.ChatOpenAI") as mock_chat:
                mock_llm = MagicMock()
                mock_chat.return_value = mock_llm

                result = await factory.get_llm_by_id("tenant1", "openai-specific")

                assert result == mock_llm
                mock_chat.assert_called_once_with(
                    model="gpt-3.5-turbo",
                    temperature=0.7,
                    max_tokens=4096,
                    api_key=SecretStr("sk-test456"),
                )

    @pytest.mark.asyncio
    async def test_get_llm_by_id_not_found(self, factory, mock_integration_service):
        """Test error when integration not found."""
        mock_integration_service.get_integration.return_value = None

        with pytest.raises(ValueError, match="Integration invalid-id not found"):
            await factory.get_llm_by_id("tenant1", "invalid-id")

    @pytest.mark.asyncio
    async def test_create_azure_openai(self, factory, mock_integration_service):
        """Test creating Azure OpenAI instance."""
        mock_integration_service.get_integration.return_value = {
            "integration_id": "azure-openai",
            "integration_type": "openai",
            "settings": {
                "api_url": "https://myorg.openai.azure.com/v1",
                "model": "gpt-4",
                "deployment_name": "my-deployment",
                "api_version": "2024-02-01",
            },
            "credential_id": "cred-789",
        }

        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            # First call returns credential metadata
            mock_cred_service.get_integration_credentials.return_value = [
                {"id": "12345678-1234-5678-9abc-123456789012", "provider": "openai"}
            ]
            # Second call returns actual credential data
            mock_cred_service.get_credential.return_value = {"api_key": "azure-key"}
            mock_cred_class.return_value = mock_cred_service

            with patch("analysi.services.llm_factory.AzureChatOpenAI") as mock_azure:
                mock_llm = MagicMock()
                mock_azure.return_value = mock_llm

                result = await factory.get_llm_by_id("tenant1", "azure-openai")

                assert result == mock_llm
                mock_azure.assert_called_once_with(
                    azure_endpoint="https://myorg.openai.azure.com",
                    api_key=SecretStr("azure-key"),
                    api_version="2024-02-01",
                    azure_deployment="my-deployment",
                    temperature=0.7,
                    max_tokens=4096,
                )

    @pytest.mark.asyncio
    async def test_create_openai_with_custom_url(
        self, factory, mock_integration_service
    ):
        """Test creating OpenAI with custom base URL."""
        mock_integration_service.get_integration.return_value = {
            "integration_id": "custom-openai",
            "integration_type": "openai",
            "settings": {"api_url": "https://custom.api.com/v1"},
            "credential_id": "cred-custom",
        }

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

                result = await factory.get_llm_by_id("tenant1", "custom-openai")

                assert result == mock_llm
                mock_chat.assert_called_once_with(
                    model="gpt-4o-mini",
                    temperature=0.7,
                    max_tokens=4096,
                    api_key=SecretStr("custom-key"),
                    base_url="https://custom.api.com/v1",
                )

    @pytest.mark.asyncio
    async def test_missing_api_key_error(self, factory, mock_integration_service):
        """Test error when API key is missing."""
        mock_integration_service.get_integration.return_value = {
            "integration_id": "no-key",
            "integration_type": "openai",
            "settings": {},
            "credential_id": "cred-nokey",
        }

        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            # First call returns credential metadata
            mock_cred_service.get_integration_credentials.return_value = [
                {"id": "12345678-1234-5678-9abc-123456789012", "provider": "openai"}
            ]
            # Second call returns credential data without api_key
            mock_cred_service.get_credential.return_value = {
                "some_other_field": "value"
            }
            mock_cred_class.return_value = mock_cred_service

            with pytest.raises(ValueError, match="Missing API key"):
                await factory.get_llm_by_id("tenant1", "no-key")

    @pytest.mark.asyncio
    async def test_unsupported_integration_type(
        self, factory, mock_integration_service
    ):
        """Test error for unsupported integration type."""
        mock_integration_service.get_integration.return_value = {
            "integration_id": "unsupported",
            "integration_type": "unknown",
            "settings": {},
            "credential_id": "cred-123",
        }

        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            # First call returns credential metadata
            mock_cred_service.get_integration_credentials.return_value = [
                {"id": "12345678-1234-5678-9abc-123456789012", "provider": "openai"}
            ]
            # Second call returns actual credential data
            mock_cred_service.get_credential.return_value = {"api_key": "key"}
            mock_cred_class.return_value = mock_cred_service

            with pytest.raises(ValueError, match="Unsupported LLM integration type"):
                await factory.get_llm_by_id("tenant1", "unsupported")

    @pytest.mark.asyncio
    async def test_get_primary_llm_finds_anthropic(
        self, factory, mock_integration_service
    ):
        """Test that get_primary_llm discovers anthropic_agent integrations."""

        # Simulate: no openai or gemini, only anthropic_agent configured
        async def list_by_type(tenant_id, integration_type):
            if integration_type == "anthropic_agent":
                return [
                    {
                        "integration_id": "anthropic-agent-main",
                        "integration_type": "anthropic_agent",
                        "settings": {
                            "is_primary": True,
                            "model_presets": {
                                "default": {"model": "claude-sonnet-4-20250514"},
                            },
                        },
                    },
                ]
            return []

        mock_integration_service.list_integrations.side_effect = list_by_type

        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            mock_cred_service.get_integration_credentials.return_value = [
                {
                    "id": "12345678-1234-5678-9abc-123456789012",
                    "provider": "anthropic_agent",
                }
            ]
            mock_cred_service.get_credential.return_value = {"api_key": "sk-ant-test"}
            mock_cred_class.return_value = mock_cred_service

            with patch("analysi.services.llm_factory.ChatAnthropic") as mock_anthropic:
                mock_llm = MagicMock()
                mock_anthropic.return_value = mock_llm

                result = await factory.get_primary_llm("tenant1")

                assert result == mock_llm
                mock_anthropic.assert_called_once()
                call_kwargs = mock_anthropic.call_args[1]
                assert call_kwargs["model"] == "claude-sonnet-4-20250514"
                assert call_kwargs["api_key"].get_secret_value() == "sk-ant-test"

    @pytest.mark.asyncio
    async def test_get_llm_by_id_anthropic(self, factory, mock_integration_service):
        """Test creating Anthropic LLM by integration ID."""
        mock_integration_service.get_integration.return_value = {
            "integration_id": "anthropic-agent-main",
            "integration_type": "anthropic_agent",
            "settings": {
                "model_presets": {
                    "default": {"model": "claude-sonnet-4-20250514"},
                    "fast": {"model": "claude-haiku-3-20250307"},
                },
            },
        }

        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            mock_cred_service.get_integration_credentials.return_value = [
                {
                    "id": "12345678-1234-5678-9abc-123456789012",
                    "provider": "anthropic_agent",
                }
            ]
            mock_cred_service.get_credential.return_value = {"api_key": "sk-ant-test"}
            mock_cred_class.return_value = mock_cred_service

            with patch("analysi.services.llm_factory.ChatAnthropic") as mock_anthropic:
                mock_llm = MagicMock()
                mock_anthropic.return_value = mock_llm

                result = await factory.get_llm_by_id("tenant1", "anthropic-agent-main")

                assert result == mock_llm
                call_kwargs = mock_anthropic.call_args[1]
                assert call_kwargs["model"] == "claude-sonnet-4-20250514"
                assert call_kwargs["max_tokens"] == 4096
