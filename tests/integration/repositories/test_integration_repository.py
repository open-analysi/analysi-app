"""Integration tests for IntegrationRepository."""

from uuid import uuid4

import pytest

from analysi.models.integration import Integration
from analysi.repositories.integration_repository import IntegrationRepository


@pytest.mark.asyncio
@pytest.mark.integration
class TestIntegrationRepository:
    """Test IntegrationRepository database operations."""

    @pytest.fixture
    def unique_id(self):
        """Generate unique ID suffix for test isolation."""
        return uuid4().hex[:8]

    @pytest.fixture
    async def repo(self, integration_test_session):
        """Create repository instance with test session."""
        return IntegrationRepository(integration_test_session)

    @pytest.fixture
    async def test_integration(self, integration_test_session, unique_id):
        """Create a test integration for use in tests."""
        integration = Integration(
            tenant_id=f"test-tenant-{unique_id}",
            integration_id=f"splunk-prod-{unique_id}",
            integration_type="splunk",
            name="Splunk Production",
            description="Test Splunk instance",
            settings={"host": "splunk.example.com", "port": 8089},
            enabled=True,
        )
        integration_test_session.add(integration)
        await integration_test_session.flush()
        return integration

    @pytest.mark.asyncio
    async def test_create_integration(self, repo, unique_id):
        """Test creating a new integration."""
        integration_id = f"echo-test-{unique_id}"
        tenant_id = f"test-tenant-{unique_id}"
        integration = await repo.create_integration(
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="echo_edr",
            name="Echo EDR Test",
            description="Test Echo EDR instance",
            settings={"api_key": "encrypted_key"},
            enabled=True,
        )

        assert integration.integration_id == integration_id
        assert integration.tenant_id == tenant_id
        assert integration.integration_type == "echo_edr"
        assert integration.name == "Echo EDR Test"
        assert integration.enabled is True
        assert integration.settings == {"api_key": "encrypted_key"}

    @pytest.mark.asyncio
    async def test_list_integrations(self, repo, test_integration, unique_id):
        """Test listing integrations for a tenant."""
        tenant_id = test_integration.tenant_id
        echo_integration_id = f"echo-prod-{unique_id}"
        # Create another integration
        await repo.create_integration(
            tenant_id=tenant_id,
            integration_id=echo_integration_id,
            integration_type="echo_edr",
            name="Echo EDR Production",
            enabled=True,
        )

        integrations = await repo.list_integrations(tenant_id)

        assert len(integrations) >= 2
        integration_ids = [i.integration_id for i in integrations]
        assert test_integration.integration_id in integration_ids
        assert echo_integration_id in integration_ids

    @pytest.mark.asyncio
    async def test_get_integration(self, repo, test_integration):
        """Test getting an integration by ID."""
        tenant_id = test_integration.tenant_id
        integration_id = test_integration.integration_id
        integration = await repo.get_integration(tenant_id, integration_id)

        assert integration is not None
        assert integration.integration_id == integration_id
        assert integration.integration_type == "splunk"
        assert integration.name == "Splunk Production"

        # Test non-existent integration
        missing = await repo.get_integration(tenant_id, "non-existent")
        assert missing is None

        # Test wrong tenant
        wrong_tenant = await repo.get_integration("other-tenant", integration_id)
        assert wrong_tenant is None

    @pytest.mark.asyncio
    async def test_update_integration(self, repo, test_integration):
        """Test updating an integration."""
        tenant_id = test_integration.tenant_id
        integration_id = test_integration.integration_id
        updated = await repo.update_integration(
            tenant_id=tenant_id,
            integration_id=integration_id,
            updates={
                "name": "Splunk Production Updated",
                "enabled": False,
                "settings": {"host": "new-splunk.example.com"},
            },
        )

        assert updated is not None
        assert updated.name == "Splunk Production Updated"
        assert updated.enabled is False
        assert updated.settings["host"] == "new-splunk.example.com"
        assert updated.updated_at > test_integration.created_at

    @pytest.mark.asyncio
    async def test_delete_integration(self, repo, test_integration):
        """Test deleting an integration."""
        tenant_id = test_integration.tenant_id
        integration_id = test_integration.integration_id
        # Verify it exists
        exists = await repo.get_integration(tenant_id, integration_id)
        assert exists is not None

        # Delete it
        deleted = await repo.delete_integration(tenant_id, integration_id)
        assert deleted is True

        # Verify it's gone
        gone = await repo.get_integration(tenant_id, integration_id)
        assert gone is None

        # Try to delete non-existent
        deleted_again = await repo.delete_integration(tenant_id, integration_id)
        assert deleted_again is False

    @pytest.mark.asyncio
    async def test_get_integration_settings(self, repo, test_integration):
        """Test getting integration settings."""
        tenant_id = test_integration.tenant_id
        integration_id = test_integration.integration_id
        settings = await repo.get_integration_settings(tenant_id, integration_id)

        assert settings is not None
        assert settings["host"] == "splunk.example.com"
        assert settings["port"] == 8089

        # Test non-existent integration
        no_settings = await repo.get_integration_settings(tenant_id, "non-existent")
        assert no_settings is None

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, repo, integration_test_session, unique_id):
        """Test that tenant isolation works properly."""
        tenant_1 = f"tenant-1-{unique_id}"
        tenant_2 = f"tenant-2-{unique_id}"
        shared_integration_id = f"shared-name-{unique_id}"
        # Create integrations for different tenants
        await repo.create_integration(
            tenant_id=tenant_1,
            integration_id=shared_integration_id,
            integration_type="splunk",
            name="Tenant 1 Splunk",
        )

        await repo.create_integration(
            tenant_id=tenant_2,
            integration_id=shared_integration_id,
            integration_type="echo_edr",
            name="Tenant 2 Echo",
        )

        # Ensure each tenant only sees their own
        tenant1_list = await repo.list_integrations(tenant_1)
        tenant2_list = await repo.list_integrations(tenant_2)

        assert len(tenant1_list) == 1
        assert tenant1_list[0].integration_type == "splunk"

        assert len(tenant2_list) == 1
        assert tenant2_list[0].integration_type == "echo_edr"

        # Ensure get respects tenant boundaries
        tenant1_int = await repo.get_integration(tenant_1, shared_integration_id)
        tenant2_int = await repo.get_integration(tenant_2, shared_integration_id)

        assert tenant1_int.name == "Tenant 1 Splunk"
        assert tenant2_int.name == "Tenant 2 Echo"

    @pytest.mark.asyncio
    async def test_integration_with_null_settings(self, repo, unique_id):
        """Test creating integration with null settings."""
        tenant_id = f"test-tenant-{unique_id}"
        integration_id = f"minimal-{unique_id}"
        integration = await repo.create_integration(
            tenant_id=tenant_id,
            integration_id=integration_id,
            integration_type="splunk",
            name="Minimal Integration",
            settings=None,
        )

        assert integration.settings == {}  # Should default to empty dict

        # Verify retrieval
        retrieved = await repo.get_integration(tenant_id, integration_id)
        assert retrieved.settings == {}
