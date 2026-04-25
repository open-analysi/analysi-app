"""
Vault Transit client for credential encryption/decryption.

Following the CustomerCredentials spec for AAD format and encryption patterns.
"""

import base64
import os

import hvac


class VaultClient:
    """Client for HashiCorp Vault Transit engine operations."""

    def __init__(self) -> None:
        """Initialize Vault client with environment configuration."""
        vault_host = os.getenv("VAULT_HOST", "vault")
        vault_port = int(os.getenv("VAULT_PORT", 8200))
        self.vault_addr = f"http://{vault_host}:{vault_port}"
        self.vault_token = os.getenv("VAULT_TOKEN", "root")
        self.key_prefix = os.getenv("VAULT_KEY_PREFIX", "dev")
        self.transit_mount = f"transit-{self.key_prefix}"  # Use separate transit mounts
        self.transit_key = os.getenv("TRANSIT_KEY", f"{self.key_prefix}-tenant-default")
        self.client = hvac.Client(url=self.vault_addr, token=self.vault_token)

    def aad(self, tenant: str, provider: str, account: str | None = None) -> str:
        """
        Generate Additional Authenticated Data for encryption context.

        Args:
            tenant: Tenant identifier
            provider: Integration type (splunk, echo_edr, etc.)
            account: Optional credential label

        Returns:
            Base64-encoded AAD string
        """
        # Build AAD string per spec: {tenant}|{provider}[|{account}]
        if account:
            aad_string = f"{tenant}|{provider}|{account}"
        else:
            aad_string = f"{tenant}|{provider}"

        # Base64 encode the AAD
        return base64.b64encode(aad_string.encode("utf-8")).decode("utf-8")

    async def encrypt_secret(
        self, tenant: str, provider: str, secret: bytes, account: str | None = None
    ) -> tuple[str, int]:
        """
        Encrypt JSON credential blob using Transit engine.

        Args:
            tenant: Tenant identifier
            provider: Integration type
            secret: JSON bytes to encrypt
            account: Optional credential label

        Returns:
            Tuple of (ciphertext, key_version)
        """
        # Generate AAD for this encryption
        aad_context = self.aad(tenant, provider, account)

        # Use tenant-specific key with environment prefix
        key_name = f"{self.key_prefix}-tenant-{tenant}"

        # Base64 encode the plaintext
        plaintext_b64 = base64.b64encode(secret).decode("utf-8")

        # Encrypt with AAD context using the environment-specific mount
        response = self.client.secrets.transit.encrypt_data(
            name=key_name,
            plaintext=plaintext_b64,
            context=aad_context,
            mount_point=self.transit_mount,
        )

        ciphertext = response["data"]["ciphertext"]

        # Extract key version from ciphertext (format: vault:v<version>:...)
        version = int(ciphertext.split(":")[1][1:])

        return ciphertext, version

    async def decrypt_secret(
        self, tenant: str, provider: str, ciphertext: str, account: str | None = None
    ) -> bytes:
        """
        Decrypt credential blob.

        Args:
            tenant: Tenant identifier
            provider: Integration type
            ciphertext: Vault ciphertext (vault:v<ver>:...)
            account: Optional credential label

        Returns:
            Decrypted bytes (JSON content)
        """
        # Generate AAD for this decryption (must match encryption AAD)
        aad_context = self.aad(tenant, provider, account)

        # Use tenant-specific key with environment prefix
        key_name = f"{self.key_prefix}-tenant-{tenant}"

        # Decrypt with AAD context using the environment-specific mount
        response = self.client.secrets.transit.decrypt_data(
            name=key_name,
            ciphertext=ciphertext,
            context=aad_context,
            mount_point=self.transit_mount,
        )

        # Decode from base64
        plaintext_b64 = response["data"]["plaintext"]
        return base64.b64decode(plaintext_b64)

    async def rotate_key(self, key_name: str | None = None) -> int:
        """
        Rotate encryption key to new version.

        Args:
            key_name: Key to rotate (default: tenant-default)

        Returns:
            New key version number
        """
        if not key_name:
            key_name = self.transit_key

        # Rotate the key using the environment-specific mount
        self.client.secrets.transit.rotate_key(
            name=key_name, mount_point=self.transit_mount
        )

        # Get the new version
        key_info = self.client.secrets.transit.read_key(
            name=key_name, mount_point=self.transit_mount
        )
        return int(key_info["data"]["latest_version"])

    async def rewrap_ciphertext(
        self, ciphertext: str, key_name: str = None, context: str = None
    ) -> tuple[str, int]:
        """
        Re-encrypt ciphertext with latest key version.

        Args:
            ciphertext: Existing ciphertext
            key_name: Key name (default: tenant-default)
            context: AAD context (required if key was created with context)

        Returns:
            Tuple of (new_ciphertext, new_version)
        """
        if not key_name:
            key_name = self.transit_key

        # Rewrap the ciphertext with latest key version using the environment-specific mount
        kwargs = {
            "name": key_name,
            "ciphertext": ciphertext,
            "mount_point": self.transit_mount,
        }

        # Include context if provided
        if context:
            kwargs["context"] = context

        response = self.client.secrets.transit.rewrap_data(**kwargs)

        new_ciphertext = response["data"]["ciphertext"]

        # Extract new version
        version = int(new_ciphertext.split(":")[1][1:])

        return new_ciphertext, version
