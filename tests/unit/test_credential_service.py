"""
Unit tests for Credential Service.

Tests encryption integration, error handling, and logging.
"""

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.credential import Credential
from analysi.repositories.credential_repository import CredentialRepository
from analysi.services.credential_service import CredentialService
from analysi.services.vault_client import VaultClient


class TestCredentialServiceEncryption:
    """Test encryption integration in service layer."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def mock_repository(self):
        """Create mock credential repository."""
        return AsyncMock(spec=CredentialRepository)

    @pytest.fixture
    def mock_vault_client(self):
        """Create mock Vault client."""
        return AsyncMock(spec=VaultClient)

    @pytest.fixture
    def service(self, mock_session, mock_repository, mock_vault_client):
        """Create CredentialService with mocks."""
        with patch(
            "analysi.services.credential_service.CredentialRepository",
            return_value=mock_repository,
        ):
            with patch(
                "analysi.services.credential_service.VaultClient",
                return_value=mock_vault_client,
            ):
                service = CredentialService(mock_session)
                service.repository = mock_repository
                service.vault_client = mock_vault_client
                return service

    @pytest.mark.asyncio
    async def test_store_credential_with_encryption(
        self, service, mock_vault_client, mock_repository
    ):
        """Full storage flow with encryption."""
        # Arrange
        tenant_id = "test-tenant"
        provider = "splunk"
        secret = {"username": "admin", "password": "secret123"}
        account = "prod-instance"
        metadata = {"environment": "production"}

        # Mock Vault encryption
        mock_vault_client.aad.return_value = "base64_aad"
        mock_vault_client.encrypt_secret.return_value = ("vault:v1:encrypted", 1)

        # Mock repository
        credential = MagicMock(spec=Credential)
        credential.id = uuid4()
        credential.key_version = 1
        mock_repository.upsert.return_value = credential

        # Act
        cred_id, version = await service.store_credential(
            tenant_id=tenant_id,
            provider=provider,
            secret=secret,
            account=account,
            credential_metadata=metadata,
            created_by=str(SYSTEM_USER_ID),
        )

        # Assert
        # Verify encryption called with correct parameters
        mock_vault_client.encrypt_secret.assert_called_once_with(
            tenant_id, provider, json.dumps(secret).encode("utf-8"), account
        )

        # Check database has ciphertext, not plaintext
        mock_repository.upsert.assert_called_once()
        call_args = mock_repository.upsert.call_args
        assert call_args.kwargs["ciphertext"] == "vault:v1:encrypted"
        assert call_args.kwargs["key_version"] == 1
        # Ensure plaintext not in call
        assert "password" not in str(call_args)

    @pytest.mark.asyncio
    async def test_get_credential_with_decryption(
        self, service, mock_vault_client, mock_repository
    ):
        """Full retrieval flow with decryption."""
        # Arrange
        tenant_id = "test-tenant"
        credential_id = uuid4()

        # Mock credential from DB
        credential = MagicMock(spec=Credential)
        credential.id = credential_id
        credential.provider = "splunk"
        credential.account = "prod"
        credential.ciphertext = "vault:v1:encrypted"
        credential.credential_metadata = {"env": "prod"}
        credential.key_version = 1
        mock_repository.get_by_id.return_value = credential

        # Mock Vault decryption
        secret_data = {"username": "admin", "password": "decrypted_pass"}
        mock_vault_client.aad.return_value = "base64_aad"
        mock_vault_client.decrypt_secret.return_value = json.dumps(secret_data).encode()

        # Act
        result = await service.get_credential(tenant_id, credential_id)

        # Assert
        # Verify original secret recovered
        assert result == secret_data
        mock_vault_client.decrypt_secret.assert_called_once_with(
            tenant_id, "splunk", "vault:v1:encrypted", "prod"
        )


class TestCredentialServiceLogging:
    """Test logging behavior for troubleshooting."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_session):
        """Create CredentialService with mocks."""
        with patch("analysi.services.credential_service.CredentialRepository"):
            with patch("analysi.services.credential_service.VaultClient"):
                return CredentialService(mock_session)

    @pytest.mark.asyncio
    async def test_no_plaintext_logged(self, service, caplog):
        """Verify secrets never appear in logs."""
        # Setup service with mocks
        service.vault_client = AsyncMock()
        service.repository = AsyncMock()

        # Known secret
        secret = {"password": "super_secret_password_12345"}

        # Mock successful operations
        service.vault_client.aad.return_value = "aad"
        service.vault_client.encrypt_secret.return_value = ("encrypted", 1)
        service.vault_client.decrypt_secret.return_value = json.dumps(secret).encode()
        service.vault_client.rotate_key.return_value = 2
        service.vault_client.rewrap_ciphertext.return_value = ("new_cipher", 2)

        credential = MagicMock()
        credential.id = uuid4()
        credential.ciphertext = "old_cipher"
        credential.provider = "test"
        credential.account = "test"
        credential.key_version = 1
        service.repository.upsert.return_value = credential
        service.repository.get_by_id.return_value = credential

        # Set log level to debug to capture all logs
        caplog.set_level(logging.DEBUG)

        # Perform operations
        # Create
        await service.store_credential("tenant", "provider", secret, "account")

        # Decrypt
        await service.get_credential("tenant", credential.id)

        # Rotate
        await service.rotate_credential("tenant", credential.id)

        # Scan all log outputs for plaintext secret
        all_logs = "\n".join(record.message for record in caplog.records)

        # Verify secret never appears
        assert "super_secret_password_12345" not in all_logs
        assert (
            "password" not in all_logs.lower() or "password" in "rotate_credential"
        )  # Allow method names

    @pytest.mark.asyncio
    async def test_error_logging(self, service):
        """Verify errors are logged properly."""
        # Setup service with mocks
        service.vault_client = AsyncMock()
        service.repository = AsyncMock()

        # Trigger various error conditions
        # 1. Vault error
        service.vault_client.encrypt_secret.side_effect = Exception(
            "Vault connection failed"
        )

        with pytest.raises(Exception, match="Vault connection failed"):
            await service.store_credential(
                "tenant", "provider", {"key": "value"}, "account"
            )

        # Note: With structlog, we can't easily capture logs in unit tests
        # The important part is that the exception propagates correctly
        # and the error handling code path is executed


class TestCredentialServiceErrorHandling:
    """Test error handling scenarios."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_session):
        """Create CredentialService with mocks."""
        with patch("analysi.services.credential_service.CredentialRepository"):
            with patch("analysi.services.credential_service.VaultClient"):
                service = CredentialService(mock_session)
                service.vault_client = AsyncMock()
                service.repository = AsyncMock()
                return service

    @pytest.mark.asyncio
    async def test_vault_unavailable_handling(self, service):
        """Handle Vault connection errors."""
        # Simulate Vault down
        service.vault_client.encrypt_secret.side_effect = Exception(
            "Connection refused to Vault"
        )

        # Verify graceful error handling
        with pytest.raises(Exception) as exc_info:
            await service.store_credential(
                "tenant", "provider", {"key": "val"}, "account"
            )

        # Check appropriate error message returned
        assert "Connection refused" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalid_ciphertext_handling(self, service):
        """Handle corrupted ciphertext."""
        # Store invalid ciphertext
        credential = MagicMock()
        credential.ciphertext = "corrupted_not_vault_format"
        credential.provider = "test"
        credential.account = "test"
        service.repository.get_by_id.return_value = credential

        # Mock decrypt to fail
        service.vault_client.decrypt_secret.side_effect = Exception(
            "Invalid ciphertext format"
        )

        # Attempt decryption
        with pytest.raises(Exception) as exc_info:
            await service.get_credential("tenant", uuid4())

        # Verify proper error handling
        assert "Invalid ciphertext" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_vault_decrypt_failure_raises_credential_decryption_error(
        self, service
    ):
        """Vault decryption failures (e.g. key rotation) raise CredentialDecryptionError, not raw hvac exception."""
        import hvac.exceptions

        from analysi.services.credential_service import CredentialDecryptionError

        credential = MagicMock()
        credential.id = uuid4()
        credential.provider = "splunk"
        credential.account = "default"
        credential.ciphertext = "vault:v1:old_cipher"
        service.repository.get_by_id.return_value = credential

        # Simulate Vault transit key mismatch (container recreated, key lost)
        service.vault_client.decrypt_secret.side_effect = (
            hvac.exceptions.InvalidRequest("cipher: message authentication failed")
        )

        with pytest.raises(CredentialDecryptionError) as exc_info:
            await service.get_credential("default", credential.id)

        assert "cipher: message authentication failed" in str(exc_info.value)
        assert exc_info.value.credential_id == credential.id

    @pytest.mark.asyncio
    async def test_vault_infrastructure_errors_not_wrapped(self, service):
        """VaultDown/Forbidden etc. must NOT be wrapped — they need full stack traces for debugging."""
        import hvac.exceptions

        credential = MagicMock()
        credential.id = uuid4()
        credential.provider = "splunk"
        credential.account = "default"
        credential.ciphertext = "vault:v1:some_cipher"
        service.repository.get_by_id.return_value = credential

        # VaultDown is an infrastructure error, not a decryption mismatch
        service.vault_client.decrypt_secret.side_effect = hvac.exceptions.VaultDown(
            "Vault is sealed"
        )

        with pytest.raises(hvac.exceptions.VaultDown):
            await service.get_credential("default", credential.id)
