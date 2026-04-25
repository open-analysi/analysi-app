"""Unit tests for AgentCredentialFactory.

Tests credential retrieval from anthropic_agent integrations via Vault.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.services.agent_credential_factory import AgentCredentialFactory


@pytest.mark.asyncio
class TestAgentCredentialFactory:
    """Test AgentCredentialFactory for retrieving agent OAuth tokens."""

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
        AgentCredentialFactory.clear_cache()
        return AgentCredentialFactory(mock_integration_service, mock_vault_client)

    async def test_get_agent_credentials_returns_oauth_token(
        self, factory, mock_integration_service
    ):
        """Test getting credentials returns oauth_token from integration."""
        # Mock integration data - anthropic_agent type
        mock_integration_service.list_integrations.return_value = [
            {
                "integration_id": "anthropic-agent-1",
                "integration_type": "anthropic_agent",
                "settings": {"max_turns": 100, "permission_mode": "bypassPermissions"},
                "credential_id": "cred-123",
            }
        ]

        # Mock credential retrieval from Vault
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
            mock_cred_service.get_credential.return_value = {
                "oauth_token": "sk-ant-test-token-12345"
            }
            mock_cred_class.return_value = mock_cred_service

            result = await factory.get_agent_credentials("tenant1")

            assert "oauth_token" in result
            assert result["oauth_token"] == "sk-ant-test-token-12345"

            # Verify get_credential was called with tenant_id and credential_id
            from uuid import UUID

            mock_cred_service.get_credential.assert_called_once()
            call_args = mock_cred_service.get_credential.call_args
            assert call_args[0][0] == "tenant1"  # tenant_id
            assert call_args[0][1] == UUID(
                "12345678-1234-5678-9abc-123456789012"
            )  # credential_id

    async def test_get_agent_credentials_returns_settings(
        self, factory, mock_integration_service
    ):
        """Test getting credentials returns settings with defaults."""
        mock_integration_service.list_integrations.return_value = [
            {
                "integration_id": "anthropic-agent-1",
                "integration_type": "anthropic_agent",
                "settings": {"max_turns": 200, "permission_mode": "requirePermissions"},
                "credential_id": "cred-123",
            }
        ]

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
            mock_cred_service.get_credential.return_value = {
                "oauth_token": "sk-ant-test-token"
            }
            mock_cred_class.return_value = mock_cred_service

            result = await factory.get_agent_credentials("tenant1")

            assert "settings" in result
            assert result["settings"]["max_turns"] == 200
            assert result["settings"]["permission_mode"] == "requirePermissions"

    async def test_get_agent_credentials_no_integration_raises(
        self, factory, mock_integration_service
    ):
        """Test ValueError when no anthropic_agent integration configured."""
        # Return empty list - no integrations
        mock_integration_service.list_integrations.return_value = []

        with pytest.raises(
            ValueError, match="No anthropic_agent integration configured"
        ):
            await factory.get_agent_credentials("tenant1")

    async def test_get_agent_credentials_caches_result(
        self, factory, mock_integration_service
    ):
        """Test that credentials are cached for TTL."""
        mock_integration_service.list_integrations.return_value = [
            {
                "integration_id": "anthropic-agent-1",
                "integration_type": "anthropic_agent",
                "settings": {},
                "credential_id": "cred-123",
            }
        ]

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
            mock_cred_service.get_credential.return_value = {
                "oauth_token": "sk-ant-cached-token"
            }
            mock_cred_class.return_value = mock_cred_service

            # First call - should hit the service
            result1 = await factory.get_agent_credentials("tenant1")
            # Second call - should use cache
            result2 = await factory.get_agent_credentials("tenant1")

            assert result1 == result2
            # Integration service only called once (second call used cache)
            assert mock_integration_service.list_integrations.call_count == 1

    async def test_get_agent_credentials_cache_expires(
        self, factory, mock_integration_service
    ):
        """Test that cache expires after TTL."""
        mock_integration_service.list_integrations.return_value = [
            {
                "integration_id": "anthropic-agent-1",
                "integration_type": "anthropic_agent",
                "settings": {},
                "credential_id": "cred-123",
            }
        ]

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
            mock_cred_service.get_credential.return_value = {
                "oauth_token": "sk-ant-first-token"
            }
            mock_cred_class.return_value = mock_cred_service

            # First call
            await factory.get_agent_credentials("tenant1")

            # Manually expire cache by setting timestamp in the past
            cache_key = "tenant1:anthropic_agent"
            AgentCredentialFactory._cache_timestamps[cache_key] = (
                time.time() - AgentCredentialFactory.CACHE_TTL_SECONDS - 1
            )

            # Second call should fetch fresh (cache expired)
            mock_cred_service.get_credential.return_value = {
                "oauth_token": "sk-ant-second-token"
            }
            result = await factory.get_agent_credentials("tenant1")

            assert result["oauth_token"] == "sk-ant-second-token"
            assert mock_integration_service.list_integrations.call_count == 2

    async def test_get_credentials_by_id_returns_credentials(
        self, factory, mock_integration_service
    ):
        """Test direct lookup by integration_id returns credentials."""
        mock_integration_service.get_integration.return_value = {
            "integration_id": "my-agent-1",
            "integration_type": "anthropic_agent",
            "settings": {"max_turns": 50},
            "credential_id": "cred-456",
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
            mock_cred_service.get_credential.return_value = {
                "oauth_token": "sk-ant-specific-token"
            }
            mock_cred_class.return_value = mock_cred_service

            result = await factory.get_credentials_by_id("tenant1", "my-agent-1")

            assert result["oauth_token"] == "sk-ant-specific-token"
            assert result["settings"]["max_turns"] == 50

    async def test_get_credentials_by_id_not_found_raises(
        self, factory, mock_integration_service
    ):
        """Test ValueError when integration not found by ID."""
        mock_integration_service.get_integration.return_value = None

        with pytest.raises(ValueError, match="Integration invalid-id not found"):
            await factory.get_credentials_by_id("tenant1", "invalid-id")

    async def test_clear_cache_removes_tenant_entries(
        self, factory, mock_integration_service
    ):
        """Test clearing cache for specific tenant."""
        # Pre-populate cache for multiple tenants
        AgentCredentialFactory._credential_cache = {
            "tenant1:anthropic_agent": {"oauth_token": "token1"},
            "tenant2:anthropic_agent": {"oauth_token": "token2"},
        }
        AgentCredentialFactory._cache_timestamps = {
            "tenant1:anthropic_agent": time.time(),
            "tenant2:anthropic_agent": time.time(),
        }

        # Clear only tenant1
        AgentCredentialFactory.clear_cache(tenant_id="tenant1")

        # tenant1 should be cleared
        assert "tenant1:anthropic_agent" not in AgentCredentialFactory._credential_cache
        # tenant2 should remain
        assert "tenant2:anthropic_agent" in AgentCredentialFactory._credential_cache

    async def test_clear_cache_removes_all(self, factory):
        """Test clearing entire cache."""
        # Pre-populate cache
        AgentCredentialFactory._credential_cache = {
            "tenant1:anthropic_agent": {"oauth_token": "token1"},
            "tenant2:anthropic_agent": {"oauth_token": "token2"},
        }
        AgentCredentialFactory._cache_timestamps = {
            "tenant1:anthropic_agent": time.time(),
            "tenant2:anthropic_agent": time.time(),
        }

        # Clear all
        AgentCredentialFactory.clear_cache()

        assert len(AgentCredentialFactory._credential_cache) == 0
        assert len(AgentCredentialFactory._cache_timestamps) == 0

    async def test_get_agent_credentials_on_failure_clears_cache_and_retries(
        self, factory, mock_integration_service
    ):
        """Test that on failure, cache is cleared and fresh credentials are fetched."""
        # First call returns credentials
        mock_integration_service.list_integrations.return_value = [
            {
                "integration_id": "anthropic-agent-1",
                "integration_type": "anthropic_agent",
                "settings": {},
                "credential_id": "cred-123",
            }
        ]

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
            # First call succeeds
            mock_cred_service.get_credential.return_value = {
                "oauth_token": "sk-ant-stale-token"
            }
            mock_cred_class.return_value = mock_cred_service

            # Get credentials (will be cached)
            result = await factory.get_agent_credentials("tenant1")
            assert result["oauth_token"] == "sk-ant-stale-token"

            # Now simulate failure flag (credentials are bad)
            # When retrying after failure, factory should clear cache first
            mock_cred_service.get_credential.return_value = {
                "oauth_token": "sk-ant-fresh-token"
            }

            # Call with force_refresh to simulate failure recovery pattern
            result = await factory.get_agent_credentials("tenant1", force_refresh=True)
            assert result["oauth_token"] == "sk-ant-fresh-token"
            # Should have called integration service twice
            assert mock_integration_service.list_integrations.call_count == 2


@pytest.mark.asyncio
class TestAgentCredentialFactoryNegativeCases:
    """Negative test cases for AgentCredentialFactory."""

    @pytest.fixture
    def mock_integration_service(self):
        """Create mock integration service."""
        return AsyncMock()

    @pytest.fixture
    def factory(self, mock_integration_service):
        """Create factory with mocked dependencies."""
        AgentCredentialFactory.clear_cache()
        return AgentCredentialFactory(mock_integration_service)

    async def test_empty_oauth_token_raises_value_error(
        self, factory, mock_integration_service
    ):
        """Test ValueError when oauth_token is empty string."""
        mock_integration_service.list_integrations.return_value = [
            {
                "integration_id": "anthropic-agent-1",
                "integration_type": "anthropic_agent",
                "settings": {},
                "credential_id": "cred-123",
            }
        ]

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
            # Empty oauth_token
            mock_cred_service.get_credential.return_value = {"oauth_token": ""}
            mock_cred_class.return_value = mock_cred_service

            with pytest.raises(ValueError, match="oauth_token cannot be empty"):
                await factory.get_agent_credentials("tenant1")

    async def test_invalid_integration_type_returns_error(
        self, factory, mock_integration_service
    ):
        """Test error when no integration of requested type exists."""
        # Return empty list - no integrations of requested type
        mock_integration_service.list_integrations.return_value = []

        with pytest.raises(ValueError, match="No anthropic_agent integration"):
            await factory.get_agent_credentials("tenant1", "anthropic_agent")

    async def test_missing_credentials_in_vault_handled(
        self, factory, mock_integration_service
    ):
        """Test handling when credentials are missing in Vault."""
        mock_integration_service.list_integrations.return_value = [
            {
                "integration_id": "anthropic-agent-1",
                "integration_type": "anthropic_agent",
                "settings": {},
                "credential_id": "cred-missing",
            }
        ]

        with patch(
            "analysi.services.credential_service.CredentialService"
        ) as mock_cred_class:
            mock_cred_service = AsyncMock()
            # No credentials found
            mock_cred_service.get_integration_credentials.return_value = []
            mock_cred_class.return_value = mock_cred_service

            with pytest.raises(ValueError, match="No credentials found"):
                await factory.get_agent_credentials("tenant1")

    async def test_cache_eviction_at_max_size(self, factory, mock_integration_service):
        """Test cache eviction works correctly at MAX_CACHE_SIZE."""
        # Fill cache to max
        for i in range(AgentCredentialFactory.MAX_CACHE_SIZE):
            AgentCredentialFactory._credential_cache[f"tenant{i}:anthropic_agent"] = {
                "oauth_token": f"token{i}"
            }
            AgentCredentialFactory._cache_timestamps[f"tenant{i}:anthropic_agent"] = (
                time.time() - i  # Older entries have earlier timestamps
            )

        assert (
            len(AgentCredentialFactory._credential_cache)
            == AgentCredentialFactory.MAX_CACHE_SIZE
        )

        # Add one more - should evict oldest
        mock_integration_service.list_integrations.return_value = [
            {
                "integration_id": "anthropic-agent-new",
                "integration_type": "anthropic_agent",
                "settings": {},
                "credential_id": "cred-new",
            }
        ]

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
            mock_cred_service.get_credential.return_value = {
                "oauth_token": "sk-ant-new-token"
            }
            mock_cred_class.return_value = mock_cred_service

            await factory.get_agent_credentials("tenant_new")

            # Should still be at max size (evicted oldest)
            assert (
                len(AgentCredentialFactory._credential_cache)
                == AgentCredentialFactory.MAX_CACHE_SIZE
            )
            # New entry should exist
            assert (
                "tenant_new:anthropic_agent" in AgentCredentialFactory._credential_cache
            )
