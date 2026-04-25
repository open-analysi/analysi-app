"""Unit tests for Gemini LLM support in LangChain factory."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from analysi.services.llm_factory import LangChainFactory


@pytest.mark.asyncio
class TestGeminiLLM:
    """Test Gemini LLM creation via LangChain factory."""

    @pytest.fixture
    def mock_integration_service(self):
        return AsyncMock()

    @pytest.fixture
    def factory(self, mock_integration_service):
        LangChainFactory.clear_cache()
        return LangChainFactory(mock_integration_service)

    def _mock_cred_service(self, api_key: str):
        """Return a patcher for CredentialService that yields the given api_key."""
        mock_cred_service = AsyncMock()
        mock_cred_service.get_integration_credentials.return_value = [
            {"id": "12345678-1234-5678-9abc-123456789012", "provider": "gemini"}
        ]
        mock_cred_service.get_credential.return_value = {"api_key": api_key}
        return mock_cred_service

    @pytest.mark.asyncio
    async def test_create_gemini_llm_with_defaults(
        self, factory, mock_integration_service
    ):
        """Test creating a Gemini LLM uses default model and settings."""
        mock_integration_service.get_integration.return_value = {
            "integration_id": "gemini-main",
            "integration_type": "gemini",
            "settings": {},
        }

        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_class.return_value = self._mock_cred_service("AIza-test")

            with patch(
                "analysi.services.llm_factory.ChatGoogleGenerativeAI"
            ) as mock_gemini:
                mock_llm = MagicMock()
                mock_gemini.return_value = mock_llm

                result = await factory.get_llm_by_id("tenant1", "gemini-main")

                assert result == mock_llm
                mock_gemini.assert_called_once_with(
                    model="gemini-2.0-flash",
                    temperature=0.7,
                    max_output_tokens=4096,
                    google_api_key=SecretStr("AIza-test"),
                )

    @pytest.mark.asyncio
    async def test_create_gemini_llm_with_custom_settings(
        self, factory, mock_integration_service
    ):
        """Test creating a Gemini LLM respects custom settings."""
        mock_integration_service.get_integration.return_value = {
            "integration_id": "gemini-pro",
            "integration_type": "gemini",
            "settings": {
                "model": "gemini-1.5-pro",
                "temperature": 0.3,
                "max_tokens": 8192,
            },
        }

        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_class.return_value = self._mock_cred_service("AIza-pro")

            with patch(
                "analysi.services.llm_factory.ChatGoogleGenerativeAI"
            ) as mock_gemini:
                mock_llm = MagicMock()
                mock_gemini.return_value = mock_llm

                result = await factory.get_llm_by_id("tenant1", "gemini-pro")

                assert result == mock_llm
                call_kwargs = mock_gemini.call_args[1]
                assert call_kwargs["model"] == "gemini-1.5-pro"
                assert call_kwargs["temperature"] == 0.3
                assert call_kwargs["max_output_tokens"] == 8192
                assert call_kwargs["google_api_key"].get_secret_value() == "AIza-pro"

    @pytest.mark.asyncio
    async def test_gemini_missing_api_key_raises(
        self, factory, mock_integration_service
    ):
        """Test that missing API key raises ValueError."""
        mock_integration_service.get_integration.return_value = {
            "integration_id": "gemini-nokey",
            "integration_type": "gemini",
            "settings": {},
        }

        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            mock_cred_service.get_integration_credentials.return_value = [
                {"id": "12345678-1234-5678-9abc-123456789012", "provider": "gemini"}
            ]
            mock_cred_service.get_credential.return_value = {"other_field": "value"}
            mock_cred_class.return_value = mock_cred_service

            with pytest.raises(
                ValueError, match="Missing API key in Gemini credentials"
            ):
                await factory.get_llm_by_id("tenant1", "gemini-nokey")

    @pytest.mark.asyncio
    async def test_get_primary_llm_returns_gemini_when_marked_primary(
        self, factory, mock_integration_service
    ):
        """Test get_primary_llm selects the Gemini integration when it is marked primary."""

        async def list_by_type(tenant_id, integration_type):
            if integration_type == "gemini":
                return [
                    {
                        "integration_id": "gemini-main",
                        "integration_type": "gemini",
                        "settings": {"is_primary": True, "model": "gemini-2.0-flash"},
                    }
                ]
            return []

        mock_integration_service.list_integrations.side_effect = list_by_type

        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_class.return_value = self._mock_cred_service("AIza-primary")

            with patch(
                "analysi.services.llm_factory.ChatGoogleGenerativeAI"
            ) as mock_gemini:
                mock_llm = MagicMock()
                mock_gemini.return_value = mock_llm

                result = await factory.get_primary_llm("tenant1")

                assert result == mock_llm

    @pytest.mark.asyncio
    async def test_get_primary_llm_prefers_openai_over_gemini_when_both_present(
        self, factory, mock_integration_service
    ):
        """Test get_primary_llm picks the integration marked is_primary regardless of type."""

        async def list_by_type(tenant_id, integration_type):
            if integration_type == "openai":
                return [
                    {
                        "integration_id": "openai-main",
                        "integration_type": "openai",
                        "settings": {"is_primary": True, "model": "gpt-4o"},
                    }
                ]
            if integration_type == "gemini":
                return [
                    {
                        "integration_id": "gemini-secondary",
                        "integration_type": "gemini",
                        "settings": {"is_primary": False, "model": "gemini-2.0-flash"},
                    }
                ]
            return []

        mock_integration_service.list_integrations.side_effect = list_by_type

        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            mock_cred_service.get_integration_credentials.return_value = [
                {"id": "12345678-1234-5678-9abc-123456789012", "provider": "openai"}
            ]
            mock_cred_service.get_credential.return_value = {"api_key": "sk-primary"}
            mock_cred_class.return_value = mock_cred_service

            with patch("analysi.services.llm_factory.ChatOpenAI") as mock_openai:
                mock_llm = MagicMock()
                mock_openai.return_value = mock_llm

                result = await factory.get_primary_llm("tenant1")

                assert result == mock_llm
                mock_openai.assert_called_once()
