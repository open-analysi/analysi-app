"""
Unit tests for Credential Repository.

Tests CRUD operations, tenant isolation, and associations.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.credential import Credential, IntegrationCredential
from analysi.repositories.credential_repository import CredentialRepository


class TestCredentialRepositoryCRUD:
    """Test CRUD operations for credentials."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def repository(self, mock_session):
        """Create CredentialRepository instance."""
        return CredentialRepository(mock_session)

    @pytest.fixture
    def sample_credential(self):
        """Create a sample credential for testing."""
        cred = MagicMock(spec=Credential)
        cred.id = uuid4()
        cred.tenant_id = "test-tenant"
        cred.provider = "splunk"
        cred.account = "prod-instance"
        cred.ciphertext = "vault:v1:encrypted_data"
        cred.key_version = 1
        cred.credential_metadata = {"environment": "production"}
        cred.created_by = "test-user"
        cred.created_at = datetime.now(UTC)
        cred.updated_at = datetime.now(UTC)
        return cred

    @pytest.mark.asyncio
    async def test_upsert_create(self, repository, mock_session, sample_credential):
        """Test credential creation."""
        # Setup mock for no existing credential
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        # Create new credential
        _ = await repository.upsert(
            tenant_id="test-tenant",
            provider="splunk",
            account="prod-instance",
            ciphertext="vault:v1:encrypted_data",
            key_version=1,
            credential_metadata={"environment": "production"},
            created_by=str(SYSTEM_USER_ID),
        )

        # Verify all fields stored correctly
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

        # Check unique constraint works (would be enforced by DB)
        # This test mainly verifies the method structure

    @pytest.mark.asyncio
    async def test_upsert_update(self, repository, mock_session, sample_credential):
        """Test credential update via upsert."""
        # Setup mock for existing credential
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_credential
        mock_session.execute.return_value = mock_result
        mock_session.flush = AsyncMock()

        # Upsert with same tenant/provider/account
        _ = await repository.upsert(
            tenant_id="test-tenant",
            provider="splunk",
            account="prod-instance",
            ciphertext="vault:v2:new_encrypted_data",
            key_version=2,
            credential_metadata={"environment": "production", "updated": True},
        )

        # Verify update occurred, not duplicate creation
        assert sample_credential.ciphertext == "vault:v2:new_encrypted_data"
        assert sample_credential.key_version == 2
        mock_session.add.assert_not_called()  # Should not add new instance
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upsert_duplicate_different_tenant(self, repository, mock_session):
        """Verify tenant isolation in uniqueness."""
        # First call - tenant A
        mock_result1 = MagicMock()
        mock_result1.scalar_one_or_none.return_value = None

        # Second call - tenant B
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = None

        mock_session.execute.side_effect = [mock_result1, mock_result2]
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        # Create credential for tenant A
        await repository.upsert(
            tenant_id="tenant-a",
            provider="splunk",
            account="shared-account",
            ciphertext="vault:v1:tenant_a_data",
            key_version=1,
        )

        # Create same provider/account for tenant B
        await repository.upsert(
            tenant_id="tenant-b",
            provider="splunk",
            account="shared-account",
            ciphertext="vault:v1:tenant_b_data",
            key_version=1,
        )

        # Verify both exist independently (2 add calls)
        assert mock_session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_get_by_id(self, repository, mock_session, sample_credential):
        """Test retrieval by ID."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_credential
        mock_session.execute.return_value = mock_result

        # Retrieve by ID
        result = await repository.get_by_id(
            tenant_id="test-tenant", credential_id=sample_credential.id
        )

        # Verify all fields match
        assert result == sample_credential
        assert result.tenant_id == "test-tenant"
        assert result.provider == "splunk"

    @pytest.mark.asyncio
    async def test_get_by_id_wrong_tenant(self, repository, mock_session):
        """Verify tenant isolation on retrieval."""
        # Setup mock to return None (not found)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Attempt retrieval with wrong tenant
        result = await repository.get_by_id(
            tenant_id="wrong-tenant", credential_id=uuid4()
        )

        # Verify returns None (not found)
        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_tenant(self, repository, mock_session):
        """Test listing with tenant isolation."""
        # Create mock credentials for different tenants
        cred1 = MagicMock(spec=Credential)
        cred1.tenant_id = "tenant-a"
        cred1.provider = "splunk"

        cred2 = MagicMock(spec=Credential)
        cred2.tenant_id = "tenant-a"
        cred2.provider = "echo_edr"

        cred3 = MagicMock(spec=Credential)
        cred3.tenant_id = "tenant-b"
        cred3.provider = "splunk"

        # Setup mock for tenant-a query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [cred1, cred2]
        mock_session.execute.return_value = mock_result

        # List for specific tenant
        results = await repository.list_by_tenant(
            tenant_id="tenant-a", limit=10, offset=0
        )

        # Verify only that tenant's credentials returned
        assert len(results) == 2
        assert all(c.tenant_id == "tenant-a" for c in results)

    @pytest.mark.asyncio
    async def test_list_with_provider_filter(self, repository, mock_session):
        """Test filtered listing."""
        # Create mock credentials
        cred1 = MagicMock(spec=Credential)
        cred1.provider = "splunk"

        cred2 = MagicMock(spec=Credential)
        cred2.provider = "splunk"

        # Setup mock
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [cred1, cred2]
        mock_session.execute.return_value = mock_result

        # Filter by specific provider
        results = await repository.list_by_tenant(
            tenant_id="test-tenant", provider="splunk"
        )

        # Verify filtering works correctly
        assert len(results) == 2
        assert all(c.provider == "splunk" for c in results)

    @pytest.mark.asyncio
    async def test_delete(self, repository, mock_session, sample_credential):
        """Test credential deletion."""
        # Setup mock to find credential first (for get_by_id call)
        mock_get_result = MagicMock()
        mock_get_result.scalar_one_or_none.return_value = sample_credential

        # Setup mock for DELETE statement result
        mock_delete_result = MagicMock()
        mock_delete_result.rowcount = 1

        # Configure session.execute to return different results for different calls
        mock_session.execute.side_effect = [mock_get_result, mock_delete_result]
        mock_session.flush = AsyncMock()

        # Delete it
        result = await repository.delete(
            tenant_id="test-tenant", credential_id=sample_credential.id
        )

        # Verify it's deleted
        assert result is True
        # Verify flush was called
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, repository, mock_session):
        """Test deleting non-existent credential."""
        # Setup mock to not find credential
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Attempt to delete non-existent ID
        result = await repository.delete(tenant_id="test-tenant", credential_id=uuid4())

        # Verify returns False (not found)
        assert result is False
        # No exceptions thrown

    @pytest.mark.asyncio
    async def test_delete_wrong_tenant(self, repository, mock_session):
        """Test deletion with wrong tenant."""
        # Setup mock to not find (wrong tenant)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        # Attempt deletion with wrong tenant
        result = await repository.delete(
            tenant_id="wrong-tenant", credential_id=uuid4()
        )

        # Verify returns False
        assert result is False


class TestCredentialRepositoryAssociations:
    """Test integration-credential associations."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def repository(self, mock_session):
        """Create CredentialRepository instance."""
        return CredentialRepository(mock_session)

    @pytest.mark.asyncio
    async def test_associate_with_integration(self, repository, mock_session):
        """Test integration association."""
        # Setup mock for existing association check (none found)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        # Create association
        _ = await repository.associate_with_integration(
            tenant_id="test-tenant",
            integration_id="splunk-prod",
            credential_id=uuid4(),
            is_primary=True,
            purpose="read",
        )

        # Verify junction table entry created
        mock_session.add.assert_called_once()
        added_obj = mock_session.add.call_args[0][0]

        # Check is_primary and purpose fields
        assert isinstance(added_obj, IntegrationCredential)
        assert added_obj.is_primary is True
        assert added_obj.purpose == "read"

    @pytest.mark.asyncio
    async def test_list_by_integration(self, repository, mock_session):
        """Test listing credentials for integration."""
        # Create mock associations
        assoc1 = MagicMock(spec=IntegrationCredential)
        assoc1.credential_id = uuid4()
        assoc1.is_primary = True
        assoc1.purpose = "read"

        assoc2 = MagicMock(spec=IntegrationCredential)
        assoc2.credential_id = uuid4()
        assoc2.is_primary = False
        assoc2.purpose = "write"

        # Setup mock
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [assoc1, assoc2]
        mock_session.execute.return_value = mock_result

        # List by integration
        results = await repository.list_by_integration(
            tenant_id="test-tenant", integration_id="splunk-prod"
        )

        # Verify all associations returned
        assert len(results) == 2
        assert results[0].is_primary is True
        assert results[1].purpose == "write"
