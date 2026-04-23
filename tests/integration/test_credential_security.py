"""
Integration tests for credential security.

Tests encryption, tenant isolation, and no plaintext storage.
"""

import pytest
from sqlalchemy import select

from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.credential import Credential
from analysi.services.credential_service import CredentialService
from analysi.services.vault_client import VaultClient

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.integration
class TestCredentialSecurityE2E:
    """End-to-end security tests."""

    @pytest.mark.asyncio
    async def test_e2e_credential_lifecycle(self, integration_test_session):
        """Complete credential lifecycle."""
        # Create service instance
        service = CredentialService(integration_test_session)

        # 1. Create credential via service
        tenant_id = "test-tenant"
        provider = "splunk"
        secret = {"username": "admin", "password": "test_password"}
        account = "test-instance"

        cred_id, version = await service.store_credential(
            tenant_id=tenant_id,
            provider=provider,
            secret=secret,
            account=account,
            credential_metadata={"env": "test"},
            created_by=str(SYSTEM_USER_ID),
        )

        await integration_test_session.commit()

        # 2. Associate with integration
        await service.associate_with_integration(
            tenant_id=tenant_id,
            integration_id="splunk-integration",
            credential_id=cred_id,
            is_primary=True,
            purpose="read",
        )

        await integration_test_session.commit()

        # 3. Retrieve and verify decryption works
        retrieved = await service.get_credential(tenant_id, cred_id)
        assert retrieved == secret

        # 4. Rotate key
        new_version = await service.rotate_credential(tenant_id, cred_id)
        assert new_version > version

        await integration_test_session.commit()

        # 5. Delete credential
        deleted = await service.delete_credential(tenant_id, cred_id)
        assert deleted is True

        await integration_test_session.commit()

        # Verify deletion
        result = await service.get_credential(tenant_id, cred_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_connector_with_credentials(self, integration_test_session):
        """Test connector using credentials."""
        service = CredentialService(integration_test_session)

        # Create integration with credentials
        tenant_id = "test-tenant"
        cred_id, _ = await service.store_credential(
            tenant_id=tenant_id,
            provider="splunk",
            secret={
                "username": "splunk_admin",
                "password": "splunk_pass",
                "host": "localhost",
                "port": 8089,
            },
            account="splunk-test",
        )

        await integration_test_session.commit()

        # Associate with integration
        await service.associate_with_integration(
            tenant_id=tenant_id,
            integration_id="splunk-connector",
            credential_id=cred_id,
            is_primary=True,
        )

        await integration_test_session.commit()

        # Simulate connector retrieving credentials
        creds = await service.get_integration_credentials(tenant_id, "splunk-connector")

        assert len(creds) == 1
        assert creds[0]["id"] == str(cred_id)  # Convert UUID to string for comparison

        # Get actual secret for connector
        secret = await service.get_credential(tenant_id, cred_id)

        # Verify connector can authenticate (simulated)
        assert secret["username"] == "splunk_admin"
        assert "password" in secret

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, integration_test_session):
        """Verify complete tenant separation."""
        service = CredentialService(integration_test_session)

        # Create credentials for tenant A
        tenant_a = "tenant-a"
        cred_a_id, _ = await service.store_credential(
            tenant_id=tenant_a,
            provider="splunk",
            secret={"key": "tenant_a_secret"},
            account="shared-name",
        )

        # Create credentials for tenant B with same account name
        tenant_b = "tenant-b"
        cred_b_id, _ = await service.store_credential(
            tenant_id=tenant_b,
            provider="splunk",
            secret={"key": "tenant_b_secret"},
            account="shared-name",
        )

        await integration_test_session.commit()

        # Verify A cannot access B's credentials
        result = await service.get_credential(tenant_a, cred_b_id)
        assert result is None

        # Verify B cannot access A's credentials
        result = await service.get_credential(tenant_b, cred_a_id)
        assert result is None

        # Check listings are isolated
        list_a = await service.list_credentials(tenant_a)
        list_b = await service.list_credentials(tenant_b)

        assert len(list_a) >= 1
        assert len(list_b) >= 1

        # Ensure no cross-contamination
        a_ids = [c["id"] for c in list_a]
        b_ids = [c["id"] for c in list_b]
        assert str(cred_a_id) in a_ids  # Convert UUID to string for comparison
        assert str(cred_b_id) in b_ids  # Convert UUID to string for comparison
        assert str(cred_a_id) not in b_ids  # Convert UUID to string for comparison
        assert str(cred_b_id) not in a_ids  # Convert UUID to string for comparison

    @pytest.mark.asyncio
    async def test_tenant_in_aad(self, integration_test_session):
        """Verify AAD includes tenant for isolation."""
        vault = VaultClient()

        # Generate AAD for tenant A
        aad_a = vault.aad("tenant-a", "provider", "account")

        # Generate AAD for tenant B
        aad_b = vault.aad("tenant-b", "provider", "account")

        # AADs should be different
        assert aad_a != aad_b

        # With real Vault, encryption with tenant A's AAD
        # should fail decryption with tenant B's AAD
        # This test verifies the AAD generation includes tenant


@pytest.mark.integration
class TestNoPlaintextStorage:
    """Verify no plaintext storage in database."""

    @pytest.mark.asyncio
    async def test_no_plaintext_in_database(self, integration_test_session):
        """Verify no secrets in plaintext."""
        service = CredentialService(integration_test_session)

        # Create credential with known secret
        secret = {"password": "super_secret_database_password_xyz"}
        tenant_id = "test-tenant"

        cred_id, _ = await service.store_credential(
            tenant_id=tenant_id, provider="test", secret=secret, account="test"
        )

        await integration_test_session.commit()

        # Query database directly
        stmt = select(Credential).where(Credential.id == cred_id)
        result = await integration_test_session.execute(stmt)
        credential = result.scalar_one_or_none()

        # Verify only ciphertext stored
        assert credential is not None
        assert credential.ciphertext.startswith("vault:")
        assert "super_secret_database_password_xyz" not in credential.ciphertext
        assert "password" not in credential.ciphertext

        # Check metadata doesn't contain secrets
        if credential.credential_metadata:
            assert "password" not in str(credential.credential_metadata)

    @pytest.mark.asyncio
    async def test_no_plaintext_in_logs(self, integration_test_session, caplog):
        """Verify secrets not logged."""
        import logging

        # Enable debug logging
        caplog.set_level(logging.DEBUG)

        service = CredentialService(integration_test_session)

        # Perform operations with known secret
        secret = {"api_key": "secret_api_key_should_not_appear_in_logs"}

        cred_id, _ = await service.store_credential(
            tenant_id="test", provider="test", secret=secret, account="test"
        )

        await service.get_credential("test", cred_id)
        await service.rotate_credential("test", cred_id)
        await service.delete_credential("test", cred_id)

        await integration_test_session.commit()

        # Scan logs for plaintext secrets
        all_logs = "\n".join(record.message for record in caplog.records)

        assert "secret_api_key_should_not_appear_in_logs" not in all_logs
        assert "api_key" not in all_logs or "api_key" in "rotate_credential"

    @pytest.mark.asyncio
    async def test_internal_only_decryption(self, integration_test_session):
        """Verify decryption is restricted."""
        # This test verifies architectural constraint that
        # decryption only happens in service layer, not exposed via API

        # The GET /credentials/{id} endpoint should return decrypted data
        # only for authorized internal services

        # In production, this would be enforced by:
        # 1. Network policies
        # 2. Authentication/authorization
        # 3. Service mesh policies

        # For this test, we verify the service layer controls access
        service = CredentialService(integration_test_session)

        cred_id, _ = await service.store_credential(
            tenant_id="test", provider="test", secret={"key": "value"}, account="test"
        )

        await integration_test_session.commit()

        # Only internal services can call get_credential
        # External callers would go through API which has access control
        result = await service.get_credential("test", cred_id)
        assert result == {"key": "value"}

        # Wrong tenant cannot decrypt
        result = await service.get_credential("wrong-tenant", cred_id)
        assert result is None
