"""
Unit tests for Vault Client.

Tests encryption/decryption, AAD generation, and key rotation.
"""

import base64
from unittest.mock import MagicMock, patch

import pytest

from analysi.services.vault_client import VaultClient


class TestVaultClientAAD:
    """Test AAD generation for Vault encryption."""

    @pytest.fixture
    def vault_client(self):
        """Create VaultClient instance."""
        return VaultClient()

    def test_aad_generation_basic(self, vault_client):
        """Verify AAD format for tenant and provider only."""
        # Test that AAD follows format: base64(`{tenant}|{provider}`)
        tenant = "test-tenant"
        provider = "splunk"

        aad = vault_client.aad(tenant, provider)

        # Decode and verify format
        decoded = base64.b64decode(aad).decode("utf-8")
        assert decoded == f"{tenant}|{provider}"

    def test_aad_generation_with_account(self, vault_client):
        """Verify AAD format with account included."""
        # Test that AAD follows format: base64(`{tenant}|{provider}|{account}`)
        tenant = "test-tenant"
        provider = "splunk"
        account = "prod-instance"

        aad = vault_client.aad(tenant, provider, account)

        # Decode and verify format
        decoded = base64.b64decode(aad).decode("utf-8")
        assert decoded == f"{tenant}|{provider}|{account}"

    def test_aad_special_characters(self, vault_client):
        """Test AAD with special characters in inputs."""
        # Test with spaces, unicode, and special chars
        tenant = "test tenant with spaces"
        provider = "provider-@special#chars"
        account = "账户-unicode"

        aad = vault_client.aad(tenant, provider, account)

        # Verify proper encoding and no corruption
        decoded = base64.b64decode(aad).decode("utf-8")
        assert decoded == f"{tenant}|{provider}|{account}"


class TestVaultClientEncryption:
    """Test encryption and decryption operations."""

    @pytest.fixture
    def vault_client(self):
        """Create VaultClient instance with mocked HVAC client."""
        with patch("analysi.services.vault_client.hvac") as mock_hvac:
            mock_client = MagicMock()
            mock_hvac.Client.return_value = mock_client
            mock_client.is_authenticated.return_value = True
            client = VaultClient()
            client.client = mock_client
            return client

    @pytest.mark.asyncio
    async def test_encrypt_decrypt_roundtrip(self, vault_client):
        """Basic encryption and decryption flow."""
        # Encrypt JSON credential data
        tenant = "test-tenant"
        provider = "splunk"
        secret_data = b'{"username": "admin", "password": "secret123"}'

        # Mock Vault responses
        vault_client.client.secrets.transit.encrypt_data.return_value = {
            "data": {"ciphertext": "vault:v1:encrypted_data_here", "key_version": 1}
        }
        vault_client.client.secrets.transit.decrypt_data.return_value = {
            "data": {"plaintext": base64.b64encode(secret_data).decode("utf-8")}
        }

        # Encrypt
        ciphertext, version = await vault_client.encrypt_secret(
            tenant, provider, secret_data
        )

        # Verify ciphertext format
        assert ciphertext.startswith("vault:v")
        assert version == 1

        # Decrypt and verify original data recovered
        decrypted = await vault_client.decrypt_secret(tenant, provider, ciphertext)
        assert decrypted == secret_data

    @pytest.mark.asyncio
    async def test_encrypt_with_wrong_aad_fails(self, vault_client):
        """Verify AAD validation on decrypt."""
        # Encrypt with one AAD
        tenant = "tenant-a"
        provider = "splunk"
        secret_data = b'{"api_key": "12345"}'

        vault_client.client.secrets.transit.encrypt_data.return_value = {
            "data": {"ciphertext": "vault:v1:encrypted_data", "key_version": 1}
        }

        ciphertext, _ = await vault_client.encrypt_secret(tenant, provider, secret_data)

        # Attempt decrypt with different AAD (different tenant)
        vault_client.client.secrets.transit.decrypt_data.side_effect = Exception(
            "decryption failed: cipher: message authentication failed"
        )

        # Verify decryption fails with proper error
        with pytest.raises(Exception, match="authentication failed"):
            await vault_client.decrypt_secret("different-tenant", provider, ciphertext)

    @pytest.mark.asyncio
    async def test_key_version_tracking(self, vault_client):
        """Verify key version is returned correctly."""
        tenant = "test-tenant"
        provider = "echo_edr"
        secret_data = b'{"token": "abc123"}'

        # Mock version 3 response
        vault_client.client.secrets.transit.encrypt_data.return_value = {
            "data": {"ciphertext": "vault:v3:encrypted_data", "key_version": 3}
        }

        # Encrypt data and check version returned
        _, version = await vault_client.encrypt_secret(tenant, provider, secret_data)

        # Verify version matches Transit key version
        assert version == 3


class TestVaultClientKeyRotation:
    """Test key rotation operations."""

    @pytest.fixture
    def vault_client(self):
        """Create VaultClient instance with mocked HVAC client."""
        with patch("analysi.services.vault_client.hvac") as mock_hvac:
            mock_client = MagicMock()
            mock_hvac.Client.return_value = mock_client
            mock_client.is_authenticated.return_value = True
            client = VaultClient()
            client.client = mock_client
            return client

    @pytest.mark.asyncio
    async def test_rotate_key(self, vault_client):
        """Test key rotation operation."""
        tenant = "test-tenant"

        # Mock rotation response
        vault_client.client.secrets.transit.rotate_key.return_value = True
        vault_client.client.secrets.transit.read_key.return_value = {
            "data": {"latest_version": 2, "min_decryption_version": 1}
        }

        # Rotate key and get new version
        new_version = await vault_client.rotate_key(tenant)

        # Verify new encryptions use new version
        assert new_version == 2

        # Setup for new encryption
        vault_client.client.secrets.transit.encrypt_data.return_value = {
            "data": {"ciphertext": "vault:v2:new_encrypted_data", "key_version": 2}
        }

        # Verify old ciphertexts still decrypt (mock old version)
        vault_client.client.secrets.transit.decrypt_data.return_value = {
            "data": {"plaintext": base64.b64encode(b"old_data").decode("utf-8")}
        }

        old_ciphertext = "vault:v1:old_encrypted_data"
        decrypted = await vault_client.decrypt_secret(
            tenant, "provider", old_ciphertext
        )
        assert decrypted == b"old_data"

    @pytest.mark.asyncio
    async def test_rewrap_ciphertext(self, vault_client):
        """Test re-encryption with new key."""
        tenant = "test-tenant"

        # Create ciphertext with old key version
        old_ciphertext = "vault:v1:old_encrypted_data"

        # Mock rewrap response
        vault_client.client.secrets.transit.rewrap_data.return_value = {
            "data": {"ciphertext": "vault:v2:rewrapped_data", "key_version": 2}
        }

        # Rewrap to new version
        new_ciphertext, new_version = await vault_client.rewrap_ciphertext(
            tenant, old_ciphertext
        )

        # Verify new version
        assert new_ciphertext == "vault:v2:rewrapped_data"
        assert new_version == 2

        # Setup decrypt mocks
        vault_client.client.secrets.transit.decrypt_data.return_value = {
            "data": {"plaintext": base64.b64encode(b"same_data").decode("utf-8")}
        }

        # Verify both old and new ciphertexts decrypt correctly
        old_decrypted = await vault_client.decrypt_secret(
            tenant, "provider", old_ciphertext
        )
        new_decrypted = await vault_client.decrypt_secret(
            tenant, "provider", new_ciphertext
        )

        assert old_decrypted == new_decrypted == b"same_data"
