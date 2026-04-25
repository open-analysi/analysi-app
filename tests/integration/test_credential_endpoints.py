"""
Integration tests for Credential REST API endpoints.

Tests CRUD operations, tenant isolation, and security.
"""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from analysi.db.session import get_db
from analysi.main import app
from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.credential import Credential, IntegrationCredential

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.integration
class TestCredentialCRUDEndpoints:
    """Test Credential CRUD operations via REST API."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, any]]:
        """Create an async HTTP client for testing with test database."""

        # Override the database dependency to use test database
        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        # Create async test client
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield (ac, integration_test_session)

        # Clean up overrides
        app.dependency_overrides.clear()

    @pytest.fixture
    async def sample_credential(self, integration_test_session):
        """Create a sample credential for testing."""
        from analysi.services.credential_service import CredentialService

        # Create credential using the service to get proper encryption
        service = CredentialService(integration_test_session)
        credential_id, key_version = await service.store_credential(
            tenant_id="test-tenant",
            provider="splunk",
            secret={
                "username": "test-user",
                "password": "test-pass",
                "url": "https://splunk.example.com",
            },
            account="prod-instance",
            credential_metadata={"environment": "production"},
            created_by=str(SYSTEM_USER_ID),
        )

        # Retrieve the created credential object
        from analysi.repositories.credential_repository import CredentialRepository

        repository = CredentialRepository(integration_test_session)
        credential = await repository.get_by_id("test-tenant", credential_id)
        return credential

    @pytest.mark.asyncio
    async def test_post_credentials(self, client):
        """Test credential creation endpoint."""
        # Unpack client and session from fixture
        http_client, session = client

        # Arrange
        tenant = "test-tenant"
        credential_data = {
            "provider": "splunk",
            "account": "test-instance",
            "secret": {"username": "admin", "password": "secret123"},
            "credential_metadata": {"environment": "test"},
        }

        # Act
        response = await http_client.post(
            f"/v1/{tenant}/credentials", json=credential_data
        )

        # Commit to ensure data persists
        await session.commit()

        # Assert
        # Verify 201 response
        if response.status_code != 201:
            print(f"Error: {response.json()}")
        assert response.status_code == 201

        # Check response has ID and version
        data = response.json()["data"]
        assert "id" in data
        assert "key_version" in data
        assert data["provider"] == credential_data["provider"]
        assert data["account"] == credential_data["account"]

    @pytest.mark.asyncio
    async def test_post_credentials_invalid_json(self, client):
        """Test with malformed secret."""
        http_client, _ = client
        tenant = "test-tenant"

        # POST with invalid JSON in secret field (should be dict, not string)
        credential_data = {
            "provider": "splunk",
            "account": "test",
            "secret": "not_a_json_object",  # Invalid
        }

        response = await http_client.post(
            f"/v1/{tenant}/credentials", json=credential_data
        )

        # Verify 422 Unprocessable Entity
        assert response.status_code == 422

        # Check error message is helpful
        error = response.json()
        assert "detail" in error

    @pytest.mark.asyncio
    async def test_post_credentials_missing_required(self, client):
        """Test missing required fields."""
        http_client, _ = client
        tenant = "test-tenant"

        # POST without provider field
        credential_data = {
            "account": "test",
            "secret": {"key": "value"},
            # Missing provider
        }

        response = await http_client.post(
            f"/v1/{tenant}/credentials", json=credential_data
        )

        # Verify 422 Unprocessable Entity
        assert response.status_code == 422

        # Check validation error details (RFC 9457 format)
        error = response.json()
        assert any("provider" in str(e) for e in error["errors"])

    @pytest.mark.asyncio
    async def test_get_credentials_list(self, client, sample_credential):
        """Test metadata listing."""
        http_client, session = client
        tenant = "test-tenant"

        # Create multiple credentials
        cred2 = Credential(
            tenant_id=tenant,
            provider="echo_edr",
            account="dev-instance",
            ciphertext="vault:v1:another_encrypted",
            key_version=1,
        )
        session.add(cred2)
        await session.commit()

        # GET list endpoint
        response = await http_client.get(f"/v1/{tenant}/credentials")

        # Assert
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) >= 2

        # Verify no secrets in response
        for cred in data:
            assert "secret" not in cred
            assert "ciphertext" not in cred
            assert "provider" in cred
            assert "account" in cred

    @pytest.mark.asyncio
    async def test_get_credential_by_id(self, client, sample_credential):
        """Test single credential retrieval."""
        http_client, session = client
        tenant = "test-tenant"

        await session.commit()

        # GET by ID
        response = await http_client.get(
            f"/v1/{tenant}/credentials/{sample_credential.id}"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()["data"]

        # Verify decrypted secret returned (in real impl)
        assert "id" in data
        assert data["provider"] == sample_credential.provider

    @pytest.mark.asyncio
    async def test_get_credential_by_invalid_id(self, client):
        """Test retrieval with invalid UUID."""
        http_client, _ = client
        tenant = "test-tenant"

        # GET with malformed UUID
        response = await http_client.get(f"/v1/{tenant}/credentials/not-a-uuid")

        # Verify 422 validation error
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_credential_by_nonexistent_id(self, client):
        """Test retrieval of non-existent."""
        http_client, _ = client
        tenant = "test-tenant"
        fake_id = uuid4()

        # GET with valid but non-existent UUID
        response = await http_client.get(f"/v1/{tenant}/credentials/{fake_id}")

        # Verify 404 Not Found
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_credential_wrong_tenant(self, client, sample_credential):
        """Test cross-tenant access prevention."""
        http_client, session = client

        # Ensure credential exists for tenant A
        await session.commit()

        # GET with tenant B in path
        response = await http_client.get(
            f"/v1/different-tenant/credentials/{sample_credential.id}"
        )

        # Verify 404 Not Found (not 403, to avoid information leakage)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_rotate_credential_endpoint(self, client, sample_credential):
        """Test rotation endpoint."""
        http_client, session = client
        tenant = "test-tenant"

        await session.commit()

        # POST to rotate action
        response = await http_client.post(
            f"/v1/{tenant}/credentials/{sample_credential.id}/rotate"
        )

        # Verify new key version returned
        assert response.status_code == 200
        data = response.json()["data"]
        assert "new_key_version" in data
        # Key version should be at least 1, and after rotation should be >= 2
        assert data["new_key_version"] >= 2

    @pytest.mark.asyncio
    async def test_delete_credential_endpoint(self, client, sample_credential):
        """Test deletion."""
        http_client, session = client
        tenant = "test-tenant"

        await session.commit()

        # DELETE endpoint
        response = await http_client.delete(
            f"/v1/{tenant}/credentials/{sample_credential.id}"
        )

        # Verify 204 No Content response
        assert response.status_code == 204

        # Check if deletion worked by trying to GET the credential
        get_response = await http_client.get(
            f"/v1/{tenant}/credentials/{sample_credential.id}"
        )
        # Should return 404 if properly deleted
        assert get_response.status_code == 404


@pytest.mark.integration
class TestIntegrationAssociationEndpoints:
    """Test integration-credential association endpoints."""

    @pytest.fixture
    async def client(
        self, integration_test_session
    ) -> AsyncGenerator[tuple[AsyncClient, any]]:
        """Create an async HTTP client for testing."""

        async def override_get_db():
            yield integration_test_session

        app.dependency_overrides[get_db] = override_get_db

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield (ac, integration_test_session)

        app.dependency_overrides.clear()

    @pytest.fixture
    async def sample_credential(self, integration_test_session):
        """Create a sample credential."""
        from analysi.services.credential_service import CredentialService

        # Create credential using the service to get proper encryption
        service = CredentialService(integration_test_session)
        credential_id, key_version = await service.store_credential(
            tenant_id="test-tenant",
            provider="splunk",
            secret={
                "username": "test-user",
                "password": "test-pass",
                "url": "https://splunk.example.com",
            },
            account="prod",
            credential_metadata={"env": "test"},
            created_by=str(SYSTEM_USER_ID),
        )

        # Retrieve the created credential object
        from analysi.repositories.credential_repository import CredentialRepository

        repository = CredentialRepository(integration_test_session)
        credential = await repository.get_by_id("test-tenant", credential_id)
        return credential

    @pytest.mark.asyncio
    async def test_associate_credential_endpoint(self, client, sample_credential):
        """Test association creation."""
        http_client, session = client
        tenant = "test-tenant"
        integration_id = "splunk-prod"

        await session.commit()

        # POST association
        association_data = {
            "credential_id": str(sample_credential.id),
            "is_primary": True,
            "purpose": "read",
        }

        response = await http_client.post(
            f"/v1/{tenant}/credentials/integrations/{integration_id}/associate",
            json=association_data,
        )

        # Verify 201 response
        assert response.status_code == 201

        # Check association in database
        data = response.json()["data"]
        assert data["credential_id"] == str(sample_credential.id)
        assert data["is_primary"] is True
        assert data["purpose"] == "read"

    @pytest.mark.asyncio
    async def test_list_integration_credentials_endpoint(
        self, client, sample_credential
    ):
        """Test listing for integration."""
        http_client, session = client
        tenant = "test-tenant"
        integration_id = "splunk-prod"

        # Create association
        assoc = IntegrationCredential(
            tenant_id=tenant,
            integration_id=integration_id,
            credential_id=sample_credential.id,
            is_primary=True,
            purpose="write",
        )
        session.add(assoc)
        await session.commit()

        # GET integration credentials
        response = await http_client.get(
            f"/v1/{tenant}/credentials/integrations/{integration_id}"
        )

        # Verify correct credentials returned
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["credential_id"] == str(sample_credential.id)
        assert data[0]["purpose"] == "write"
