"""
Integration tests for Vault client with real Vault instance.

Tests actual encryption/decryption against running Vault container.
"""

import json
import os

import pytest

from analysi.services.vault_client import VaultClient

pytestmark = [pytest.mark.integration, pytest.mark.requires_full_stack]


@pytest.mark.integration
@pytest.mark.requires_vault
class TestVaultIntegration:
    """Test VaultClient with real Vault instance."""

    @pytest.fixture
    def vault_client(self):
        """Create VaultClient connected to real Vault."""
        # Set test environment variables
        os.environ["VAULT_ADDR"] = "http://localhost:8200"
        os.environ["VAULT_TOKEN"] = "dev-root-token"
        os.environ["VAULT_KEY_PREFIX"] = "test"  # Use test transit mount
        return VaultClient()

    @pytest.mark.asyncio
    async def test_real_encrypt_decrypt_roundtrip(self, vault_client):
        """Test actual encryption and decryption with Vault."""
        tenant = "test-tenant"
        provider = "splunk"
        account = "test-account"

        # Test data
        secret_data = {"username": "admin", "password": "real_secret_123"}
        secret_bytes = json.dumps(secret_data).encode("utf-8")

        # Encrypt
        ciphertext, version = await vault_client.encrypt_secret(
            tenant, provider, secret_bytes, account
        )

        # Verify ciphertext format
        assert ciphertext.startswith("vault:v")
        assert version >= 1

        # Decrypt
        decrypted_bytes = await vault_client.decrypt_secret(
            tenant, provider, ciphertext, account
        )

        # Verify we got the original data back
        decrypted_data = json.loads(decrypted_bytes)
        assert decrypted_data == secret_data

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Vault Transit doesn't enforce AAD validation without derived keys"
    )
    async def test_real_aad_validation(self, vault_client):
        """Test that AAD is actually validated by Vault.

        NOTE: Vault's Transit engine only validates context/AAD when using derived keys.
        For non-derived keys, the context is included but not validated on decrypt.
        This is a known Vault behavior. We keep the AAD for future compatibility.
        """
        tenant = "test-tenant"
        provider = "splunk"
        account = "prod"

        secret_bytes = b'{"api_key": "12345"}'

        # Encrypt with one AAD
        ciphertext, _ = await vault_client.encrypt_secret(
            tenant, provider, secret_bytes, account
        )

        # Try to decrypt with different AAD (different account)
        # NOTE: This would only fail with derived=true keys
        with pytest.raises(Exception) as exc_info:
            await vault_client.decrypt_secret(
                tenant, provider, ciphertext, "different-account"
            )

        # Vault should reject due to AAD mismatch (only with derived keys)
        assert (
            "message authentication failed" in str(exc_info.value).lower()
            or "authentication" in str(exc_info.value).lower()
        )

    @pytest.mark.asyncio
    async def test_real_tenant_isolation(self, vault_client):
        """Test that different tenants use different keys."""
        secret_bytes = b'{"shared": "secret"}'

        # Encrypt for tenant-a
        ciphertext_a, _ = await vault_client.encrypt_secret(
            "tenant-a", "provider", secret_bytes
        )

        # Encrypt same data for tenant-b
        ciphertext_b, _ = await vault_client.encrypt_secret(
            "tenant-b", "provider", secret_bytes
        )

        # Ciphertexts should be different (different keys)
        assert ciphertext_a != ciphertext_b

        # Try to decrypt tenant-a's ciphertext with tenant-b's key
        # This should fail because different keys are used
        with pytest.raises(Exception):  # noqa: B017
            await vault_client.decrypt_secret("tenant-b", "provider", ciphertext_a)

    @pytest.mark.asyncio
    async def test_real_key_rotation(self, vault_client):
        """Test key rotation with real Vault."""
        tenant = "default"  # Use default tenant for this test
        # Use the correct key name with prefix
        key_name = f"{vault_client.key_prefix}-tenant-{tenant}"

        # Encrypt something first
        secret_bytes = b'{"test": "rotation"}'
        old_ciphertext, old_version = await vault_client.encrypt_secret(
            tenant, "provider", secret_bytes
        )

        # Rotate the key
        new_version = await vault_client.rotate_key(key_name)
        assert new_version > old_version

        # New encryptions should use new version
        new_ciphertext, version = await vault_client.encrypt_secret(
            tenant, "provider", secret_bytes
        )
        assert version == new_version

        # Old ciphertext should still decrypt
        decrypted = await vault_client.decrypt_secret(
            tenant, "provider", old_ciphertext
        )
        assert decrypted == secret_bytes

        # Rewrap old ciphertext
        rewrapped_ciphertext, rewrap_version = await vault_client.rewrap_ciphertext(
            old_ciphertext, key_name
        )
        assert rewrap_version == new_version
        assert rewrapped_ciphertext != old_ciphertext

        # Rewrapped should still decrypt to same data
        decrypted_rewrapped = await vault_client.decrypt_secret(
            tenant, "provider", rewrapped_ciphertext
        )
        assert decrypted_rewrapped == secret_bytes
