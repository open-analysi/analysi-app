"""Integration test to verify LLM factory reuses database sessions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.services.llm_factory import LangChainFactory


@pytest.mark.integration
class TestLLMSessionReuse:
    """Test that LLM factory properly reuses sessions when provided."""

    @pytest.mark.asyncio
    async def test_llm_factory_uses_provided_session(self):
        """Test that LLM factory uses provided session instead of creating new one."""
        # Clear cache before test
        LangChainFactory.clear_cache()

        mock_integration_service = AsyncMock()
        mock_integration = {
            "integration_id": "openai-test",
            "integration_type": "openai",
            "settings": {"model": "gpt-4", "is_primary": True},
        }

        mock_integration_service.list_integrations.return_value = [mock_integration]
        mock_integration_service.get_integration.return_value = mock_integration

        # Create a mock session
        mock_session = MagicMock(spec=AsyncSession)

        factory = LangChainFactory(mock_integration_service, None)

        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            mock_cred_service.get_integration_credentials.return_value = [
                {"id": "12345678-1234-5678-9abc-123456789012", "provider": "openai"}
            ]
            mock_cred_service.get_credential.return_value = {"api_key": "sk-test-key"}
            mock_cred_class.return_value = mock_cred_service

            with patch("analysi.services.llm_factory.ChatOpenAI") as mock_chat:
                mock_llm = MagicMock()
                mock_chat.return_value = mock_llm

                # Important: We should NOT create a new AsyncSessionLocal
                with patch(
                    "analysi.db.session.AsyncSessionLocal"
                ) as mock_session_local:
                    # Call get_primary_llm with a session
                    await factory.get_primary_llm("test-tenant", session=mock_session)

                    # Verify AsyncSessionLocal was NOT called (no new session created)
                    mock_session_local.assert_not_called()

                    # Verify CredentialService was created with our session
                    mock_cred_class.assert_called_with(mock_session)

    @pytest.mark.asyncio
    async def test_llm_factory_creates_session_when_none_provided(self):
        """Test that LLM factory creates a new session when none is provided."""
        # Clear cache before test
        LangChainFactory.clear_cache()

        mock_integration_service = AsyncMock()
        mock_integration = {
            "integration_id": "openai-test2",
            "integration_type": "openai",
            "settings": {"model": "gpt-4", "is_primary": True},
        }

        mock_integration_service.list_integrations.return_value = [mock_integration]
        mock_integration_service.get_integration.return_value = mock_integration

        factory = LangChainFactory(mock_integration_service, None)

        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            mock_cred_service.get_integration_credentials.return_value = [
                {"id": "12345678-1234-5678-9abc-123456789012", "provider": "openai"}
            ]
            mock_cred_service.get_credential.return_value = {"api_key": "sk-test-key"}
            mock_cred_class.return_value = mock_cred_service

            with patch("analysi.services.llm_factory.ChatOpenAI") as mock_chat:
                mock_llm = MagicMock()
                mock_chat.return_value = mock_llm

                # Mock AsyncSessionLocal to verify it's called
                mock_new_session = AsyncMock(spec=AsyncSession)
                mock_session_context = AsyncMock()
                mock_session_context.__aenter__.return_value = mock_new_session

                with patch(
                    "analysi.db.session.AsyncSessionLocal",
                    return_value=mock_session_context,
                ) as mock_session_local:
                    # Call get_primary_llm without a session
                    await factory.get_primary_llm("test-tenant", session=None)

                    # Verify AsyncSessionLocal WAS called (new session created)
                    mock_session_local.assert_called_once()

                    # Verify CredentialService was created with the new session
                    mock_cred_class.assert_called_with(mock_new_session)
