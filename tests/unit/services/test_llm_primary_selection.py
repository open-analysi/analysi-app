"""Unit tests for primary LLM selection logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.services.llm_factory import LangChainFactory


class TestPrimaryLLMSelection:
    """Test primary LLM selection for multiple integrations."""

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
    async def test_selects_primary_when_multiple_integrations(
        self, factory, mock_integration_service
    ):
        """Test that primary integration is selected when multiple exist."""
        # Setup: Two OpenAI integrations, second one is primary
        mock_integration_service.list_integrations.return_value = [
            {
                "integration_id": "openai-secondary",
                "integration_type": "openai",
                "settings": {"is_primary": False, "model": "gpt-3.5-turbo"},
                "credential_id": "cred-1",
            },
            {
                "integration_id": "openai-primary",
                "integration_type": "openai",
                "settings": {"is_primary": True, "model": "gpt-4"},
                "credential_id": "cred-2",
            },
            {
                "integration_id": "openai-another",
                "integration_type": "openai",
                "settings": {"model": "gpt-4-turbo"},  # No is_primary
                "credential_id": "cred-3",
            },
        ]

        mock_integration_service.get_integration.return_value = {
            "integration_id": "openai-primary",
            "integration_type": "openai",
            "settings": {"is_primary": True, "model": "gpt-4"},
            "credential_id": "cred-2",
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
            mock_cred_service.get_credential.return_value = {"api_key": "sk-primary"}
            mock_cred_class.return_value = mock_cred_service

            with patch("analysi.services.llm_factory.ChatOpenAI") as mock_chat:
                mock_llm = MagicMock()
                mock_chat.return_value = mock_llm

                result = await factory.get_primary_llm("tenant1")

                # Should use the primary integration
                assert result == mock_llm
                mock_chat.assert_called_once()
                call_args = mock_chat.call_args[1]
                assert call_args["api_key"].get_secret_value() == "sk-primary"
                assert call_args["model"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_uses_first_when_no_primary_marked(
        self, factory, mock_integration_service
    ):
        """Test that first integration is used when none marked as primary."""
        mock_integration_service.list_integrations.return_value = [
            {
                "integration_id": "openai-first",
                "integration_type": "openai",
                "settings": {"model": "gpt-4"},
                "credential_id": "cred-1",
            },
            {
                "integration_id": "openai-second",
                "integration_type": "openai",
                "settings": {"model": "gpt-3.5-turbo"},
                "credential_id": "cred-2",
            },
        ]

        mock_integration_service.get_integration.return_value = {
            "integration_id": "openai-first",
            "integration_type": "openai",
            "settings": {"model": "gpt-4"},
            "credential_id": "cred-1",
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
            mock_cred_service.get_credential.return_value = {"api_key": "sk-first"}
            mock_cred_class.return_value = mock_cred_service

            with patch("analysi.services.llm_factory.ChatOpenAI") as mock_chat:
                mock_llm = MagicMock()
                mock_chat.return_value = mock_llm

                result = await factory.get_primary_llm("tenant1")

                # Should use the first integration
                assert result == mock_llm
                call_args = mock_chat.call_args[1]
                assert call_args["api_key"].get_secret_value() == "sk-first"
                assert call_args["model"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_caches_primary_llm_instance(self, factory, mock_integration_service):
        """Test that primary LLM instance is cached."""
        # Clear cache before test
        from analysi.services.llm_factory import LangChainFactory

        LangChainFactory.clear_cache()

        mock_integration_service.list_integrations.return_value = [
            {
                "integration_id": "openai-primary",
                "integration_type": "openai",
                "settings": {"is_primary": True},
                "credential_id": "cred-1",
            }
        ]

        mock_integration_service.get_integration.return_value = {
            "integration_id": "openai-primary",
            "integration_type": "openai",
            "settings": {"is_primary": True},
            "credential_id": "cred-1",
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
            mock_cred_service.get_credential.return_value = {"api_key": "sk-test"}
            mock_cred_class.return_value = mock_cred_service

            with patch("analysi.services.llm_factory.ChatOpenAI") as mock_chat:
                mock_llm = MagicMock()
                mock_chat.return_value = mock_llm

                # First call
                result1 = await factory.get_primary_llm("tenant1")
                # Second call (should use cache)
                result2 = await factory.get_primary_llm("tenant1")

                assert result1 == result2
                # ChatOpenAI should only be called once due to caching
                assert mock_chat.call_count == 1
                # list_integrations is called once per AI-archetype type per get_primary_llm call.
                # With cache hit on 2nd call, list_integrations is still called (to find primary).
                from analysi.integrations.framework.models import Archetype
                from analysi.integrations.framework.registry import get_registry

                ai_type_count = len(get_registry().list_by_archetype(Archetype.AI))
                assert (
                    mock_integration_service.list_integrations.call_count
                    == ai_type_count * 2
                )
                # get_integration should not be called (primary found via list_integrations)
                assert mock_integration_service.get_integration.call_count == 0
