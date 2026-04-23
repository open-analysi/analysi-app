"""Test LLM cache TTL and DB call savings."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.services.llm_factory import LangChainFactory


@pytest.fixture
def factory():
    """Create factory with mock dependencies."""
    mock_integration_service = AsyncMock()
    mock_vault_client = MagicMock()
    return LangChainFactory(mock_integration_service, mock_vault_client)


@pytest.fixture
def mock_integration_service(factory):
    """Get mock integration service from factory."""
    return factory.integration_service


@pytest.mark.asyncio
class TestLLMCacheTTL:
    """Test LLM cache TTL and DB call optimization."""

    def setup_method(self):
        """Clear cache before each test."""
        LangChainFactory.clear_cache()

    @pytest.mark.asyncio
    async def test_cache_saves_db_calls_within_ttl(
        self, factory, mock_integration_service
    ):
        """Test that cache prevents DB calls within TTL window."""
        tenant_id = "tenant-cache-test"
        integration_id = "openai-test"

        # Mock integration data
        mock_integration_service.list_integrations.return_value = [
            {
                "integration_id": integration_id,
                "integration_type": "openai",
                "settings": {"model": "gpt-4", "is_primary": True},
                "credential_id": "cred-1",
            }
        ]

        mock_integration_service.get_integration.return_value = {
            "integration_id": integration_id,
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
            mock_cred_service.get_credential.return_value = {"api_key": "sk-test"}
            mock_cred_class.return_value = mock_cred_service

            with patch("analysi.services.llm_factory.ChatOpenAI") as mock_chat:
                mock_llm = MagicMock()
                mock_chat.return_value = mock_llm

                # First call - should create new instance
                llm1 = await factory.get_primary_llm(tenant_id)

                # Verify DB calls were made — once per AI-archetype type
                from analysi.integrations.framework.models import Archetype
                from analysi.integrations.framework.registry import get_registry

                ai_type_count = len(get_registry().list_by_archetype(Archetype.AI))
                assert (
                    mock_integration_service.list_integrations.call_count
                    == ai_type_count
                )
                # get_integration is not called for primary LLM (uses list_integrations)
                assert mock_cred_service.get_integration_credentials.call_count == 1
                assert mock_cred_service.get_credential.call_count == 1
                assert mock_chat.call_count == 1

                # Reset call counts
                mock_integration_service.list_integrations.reset_mock()
                mock_cred_service.get_integration_credentials.reset_mock()
                mock_cred_service.get_credential.reset_mock()
                mock_chat.reset_mock()

                # Second call within TTL - should use cache
                llm2 = await factory.get_primary_llm(tenant_id)

                # Should be same instance
                assert llm1 is llm2

                # list_integrations is called to find primary (once per AI-archetype type)
                assert (
                    mock_integration_service.list_integrations.call_count
                    == ai_type_count
                )
                # NO credential fetching (cache hit skips credential retrieval)
                assert mock_cred_service.get_integration_credentials.call_count == 0
                assert mock_cred_service.get_credential.call_count == 0
                # NO new ChatOpenAI creation
                assert mock_chat.call_count == 0

    @pytest.mark.asyncio
    async def test_cache_expires_after_ttl(self, factory, mock_integration_service):
        """Test that cache expires after TTL and refreshes."""
        tenant_id = "tenant-ttl-test"

        # Set very short TTL for testing
        original_ttl = LangChainFactory.CACHE_TTL_SECONDS
        LangChainFactory.CACHE_TTL_SECONDS = 0.1  # 100ms TTL

        try:
            mock_integration_service.list_integrations.return_value = [
                {
                    "integration_id": "openai-ttl",
                    "integration_type": "openai",
                    "settings": {"model": "gpt-4", "is_primary": True},
                    "credential_id": "cred-1",
                }
            ]

            mock_integration_service.get_integration.return_value = {
                "integration_id": "openai-ttl",
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
                mock_cred_service.get_credential.return_value = {"api_key": "sk-test"}
                mock_cred_class.return_value = mock_cred_service

                with patch("analysi.services.llm_factory.ChatOpenAI") as mock_chat:
                    mock_llm1 = MagicMock()
                    mock_llm2 = MagicMock()
                    mock_chat.side_effect = [mock_llm1, mock_llm2]

                    # First call
                    await factory.get_primary_llm(tenant_id)
                    assert mock_chat.call_count == 1

                    # Wait for TTL to expire
                    time.sleep(0.2)  # 200ms > 100ms TTL

                    # Second call after TTL expiry
                    llm2 = await factory.get_primary_llm(tenant_id)

                    # Should create new instance
                    assert mock_chat.call_count == 2
                    # Different instances (new one created)
                    assert llm2 is mock_llm2

        finally:
            # Restore original TTL
            LangChainFactory.CACHE_TTL_SECONDS = original_ttl

    @pytest.mark.asyncio
    async def test_get_llm_by_id_cache_works(self, factory, mock_integration_service):
        """Test that get_llm_by_id also uses cache correctly."""
        tenant_id = "tenant-by-id"
        integration_id = "openai-specific"

        mock_integration_service.get_integration.return_value = {
            "integration_id": integration_id,
            "integration_type": "openai",
            "settings": {"model": "gpt-3.5-turbo"},
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
                llm1 = await factory.get_llm_by_id(tenant_id, integration_id)
                assert mock_integration_service.get_integration.call_count == 1

                # Reset mock
                mock_integration_service.get_integration.reset_mock()
                mock_chat.reset_mock()

                # Second call - should use cache
                llm2 = await factory.get_llm_by_id(tenant_id, integration_id)

                # Same instance from cache
                assert llm1 is llm2
                # NO DB calls (cache hit)
                assert mock_integration_service.get_integration.call_count == 0
                # NO new LLM creation
                assert mock_chat.call_count == 0

    @pytest.mark.asyncio
    async def test_multiple_tenants_isolated_caches(
        self, factory, mock_integration_service
    ):
        """Test that different tenants have isolated cache entries."""

        # Setup for multiple tenants
        def list_integrations_side_effect(tenant_id, **kwargs):
            return [
                {
                    "integration_id": f"openai-{tenant_id}",
                    "integration_type": "openai",
                    "settings": {"model": "gpt-4", "is_primary": True},
                    "credential_id": f"cred-{tenant_id}",
                }
            ]

        mock_integration_service.list_integrations.side_effect = (
            list_integrations_side_effect
        )

        def get_integration_side_effect(tenant_id, integration_id):
            return {
                "integration_id": integration_id,
                "integration_type": "openai",
                "settings": {"model": "gpt-4"},
                "credential_id": f"cred-{tenant_id}",
            }

        mock_integration_service.get_integration.side_effect = (
            get_integration_side_effect
        )

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

                # Create LLMs for different tenants
                llm_t1 = await factory.get_primary_llm("tenant1")
                llm_t2 = await factory.get_primary_llm("tenant2")

                # Should create 2 separate instances
                assert mock_chat.call_count == 2

                # Reset and get again - both should be cached
                mock_chat.reset_mock()

                llm_t1_cached = await factory.get_primary_llm("tenant1")
                llm_t2_cached = await factory.get_primary_llm("tenant2")

                # Both from cache, no new creations
                assert mock_chat.call_count == 0
                assert llm_t1 is llm_t1_cached
                assert llm_t2 is llm_t2_cached

    @pytest.mark.asyncio
    async def test_cache_size_limit_eviction(self, factory, mock_integration_service):
        """Test that cache evicts oldest entries when size limit reached."""
        # Set small cache size for testing
        original_size = LangChainFactory.MAX_CACHE_SIZE
        LangChainFactory.MAX_CACHE_SIZE = 3

        try:

            def get_integration_side_effect(tenant_id, integration_id):
                return {
                    "integration_id": integration_id,
                    "integration_type": "openai",
                    "settings": {"model": "gpt-4"},
                    "credential_id": "cred-1",
                }

            mock_integration_service.get_integration.side_effect = (
                get_integration_side_effect
            )

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

                    # Add entries up to limit
                    for i in range(3):
                        await factory.get_llm_by_id(f"tenant{i}", f"integration{i}")

                    assert len(factory._llm_cache) == 3

                    # Add one more - should evict oldest
                    await factory.get_llm_by_id("tenant3", "integration3")

                    # Still only 3 entries
                    assert len(factory._llm_cache) == 3
                    # Oldest (tenant0) should be evicted
                    assert "tenant0:integration0" not in factory._llm_cache
                    # Newest should be present
                    assert "tenant3:integration3" in factory._llm_cache

        finally:
            LangChainFactory.MAX_CACHE_SIZE = original_size

    @pytest.mark.asyncio
    async def test_clear_cache_for_specific_tenant(self):
        """Test that clear_cache can target specific tenant."""
        # Manually add cache entries
        LangChainFactory._llm_cache = {
            "tenant1:integration1": MagicMock(),
            "tenant1:integration2": MagicMock(),
            "tenant2:integration1": MagicMock(),
        }
        LangChainFactory._cache_settings = {
            "tenant1:integration1": {},
            "tenant1:integration2": {},
            "tenant2:integration1": {},
        }
        LangChainFactory._cache_timestamps = {
            "tenant1:integration1": time.time(),
            "tenant1:integration2": time.time(),
            "tenant2:integration1": time.time(),
        }

        # Clear only tenant1
        LangChainFactory.clear_cache("tenant1")

        # tenant1 entries should be gone
        assert "tenant1:integration1" not in LangChainFactory._llm_cache
        assert "tenant1:integration2" not in LangChainFactory._llm_cache
        # tenant2 should remain
        assert "tenant2:integration1" in LangChainFactory._llm_cache
