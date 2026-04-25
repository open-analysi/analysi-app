"""
Service layer for credential management.

Orchestrates Vault encryption and database storage per CustomerCredentials spec.
"""

import json
from datetime import UTC, datetime
from uuid import UUID

import hvac.exceptions
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.repositories.credential_repository import CredentialRepository
from analysi.services.vault_client import VaultClient

logger = get_logger(__name__)


class CredentialDecryptionError(Exception):
    """Raised when Vault cannot decrypt a credential (e.g. key rotated, container recreated)."""

    def __init__(self, message: str, credential_id: UUID | None = None):
        self.credential_id = credential_id
        super().__init__(message)


class CredentialService:
    """Service for credential encryption and management."""

    def __init__(self, session: AsyncSession):
        """Initialize with database session and Vault client."""
        self.session = session
        self.repository = CredentialRepository(session)
        self.vault_client = VaultClient()

    async def store_credential(
        self,
        tenant_id: str,
        provider: str,
        secret: dict,
        account: str | None = None,
        credential_metadata: dict | None = None,
        created_by: str | None = None,
    ) -> tuple[UUID, int]:
        """
        Store encrypted credential (upsert by tenant/provider/account).

        Args:
            tenant_id: Tenant identifier
            provider: Integration type (maps to integration_type)
            secret: Credential dictionary to encrypt
            account: Optional credential label
            credential_metadata: Unencrypted metadata
            created_by: User creating credential

        Returns:
            Tuple of (credential_id, key_version)
        """
        logger.info(
            "storing_credential",
            tenant_id=tenant_id,
            provider=provider,
            account=account,
        )

        try:
            # Serialize secret to bytes
            secret_bytes = json.dumps(secret).encode("utf-8")

            # Encrypt with Vault
            ciphertext, key_version = await self.vault_client.encrypt_secret(
                tenant_id, provider, secret_bytes, account
            )

            # Store in database
            credential = await self.repository.upsert(
                tenant_id=tenant_id,
                provider=provider,
                account=account or "default",
                ciphertext=ciphertext,
                key_version=key_version,
                credential_metadata=credential_metadata,
                created_by=created_by,
            )

            logger.info(
                "stored_credential",
                credential_id=credential.id,
                key_version=key_version,
            )
            return credential.id, key_version

        except Exception as e:
            logger.error(
                "failed_to_store_credential",
                tenant_id=tenant_id,
                provider=provider,
                error=str(e),
            )
            raise

    async def get_credential(self, tenant_id: str, credential_id: UUID) -> dict | None:
        """
        Get decrypted credential.

        Args:
            tenant_id: Tenant identifier
            credential_id: Credential UUID

        Returns:
            Decrypted credential dictionary or None
        """
        logger.debug(
            "getting_credential_for_tenant",
            credential_id=credential_id,
            tenant_id=tenant_id,
        )

        # Get credential from database
        credential = await self.repository.get_by_id(tenant_id, credential_id)
        if not credential:
            logger.warning(
                "credential_not_found",
                credential_id=credential_id,
                tenant_id=tenant_id,
            )
            return None

        # Decrypt with Vault
        try:
            decrypted_bytes = await self.vault_client.decrypt_secret(
                tenant_id,
                credential.provider,
                credential.ciphertext,
                credential.account,
            )

            # Parse JSON
            secret_dict = json.loads(decrypted_bytes.decode("utf-8"))
            logger.debug(
                "successfully_decrypted_credential", credential_id=credential_id
            )
            return secret_dict

        except hvac.exceptions.InvalidRequest as e:
            logger.error(
                "failed_to_decrypt_credential",
                credential_id=credential_id,
                tenant_id=tenant_id,
                error=str(e),
            )
            raise CredentialDecryptionError(
                f"Failed to decrypt credential {credential_id}: {e}. "
                "This usually means the Vault transit key was lost (e.g. dev container recreated). "
                "Re-store the credential to fix.",
                credential_id=credential_id,
            ) from e

        except Exception as e:
            logger.error(
                "failed_to_decrypt_credential",
                credential_id=credential_id,
                error=str(e),
            )
            raise

    async def list_credentials(
        self,
        tenant_id: str,
        provider: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """
        List credential metadata (no secrets).

        Args:
            tenant_id: Tenant identifier
            provider: Optional filter by provider
            limit: Page size
            offset: Page offset

        Returns:
            List of credential metadata
        """
        logger.debug(
            "listing_credentials_for_tenant_provider",
            tenant_id=tenant_id,
            provider=provider,
        )

        # Get credentials from database
        credentials = await self.repository.list_by_tenant(
            tenant_id=tenant_id, provider=provider, limit=limit, offset=offset
        )

        # Convert to metadata-only response
        result = []
        for cred in credentials:
            result.append(
                {
                    "id": str(cred.id),
                    "tenant_id": cred.tenant_id,
                    "provider": cred.provider,
                    "account": cred.account,
                    "key_version": cred.key_version,
                    "credential_metadata": cred.credential_metadata,
                    "created_at": cred.created_at.isoformat(),
                    "updated_at": (
                        cred.updated_at.isoformat() if cred.updated_at else None
                    ),
                    "created_by": cred.created_by,
                }
            )

        logger.debug(
            "found_credentials_for_tenant",
            result_count=len(result),
            tenant_id=tenant_id,
        )
        return result

    async def count_credentials(
        self, tenant_id: str, provider: str | None = None
    ) -> int:
        """Count total credentials matching filters (for pagination metadata)."""
        return await self.repository.count_by_tenant(tenant_id, provider)

    async def rotate_credential(self, tenant_id: str, credential_id: UUID) -> int:
        """
        Re-encrypt credential with latest key version.

        Args:
            tenant_id: Tenant identifier
            credential_id: Credential UUID

        Returns:
            New key version
        """
        logger.info(
            "rotating_credential_for_tenant",
            credential_id=credential_id,
            tenant_id=tenant_id,
        )

        # Get credential from database
        credential = await self.repository.get_by_id(tenant_id, credential_id)
        if not credential:
            raise ValueError(f"Credential {credential_id} not found")

        # First rotate the key to create a new version
        key_name = f"{self.vault_client.key_prefix}-tenant-{tenant_id}"
        await self.vault_client.rotate_key(key_name)

        # Then rewrap with the new key version
        # Generate the same AAD that was used for original encryption
        aad_context = self.vault_client.aad(
            tenant_id, credential.provider, credential.account
        )
        new_ciphertext, new_version = await self.vault_client.rewrap_ciphertext(
            credential.ciphertext, key_name, aad_context
        )

        # Update database with new ciphertext and version
        credential.ciphertext = new_ciphertext
        credential.key_version = new_version
        credential.updated_at = datetime.now(UTC)
        await self.session.flush()

        logger.info(
            "rotated_credential_to_key_version",
            credential_id=credential_id,
            new_version=new_version,
        )
        return new_version

    async def delete_credential(self, tenant_id: str, credential_id: UUID) -> bool:
        """
        Delete credential.

        Args:
            tenant_id: Tenant identifier
            credential_id: Credential UUID

        Returns:
            True if deleted, False if not found
        """
        logger.info(
            "deleting_credential_for_tenant",
            credential_id=credential_id,
            tenant_id=tenant_id,
        )

        # Delete from database (repository handles tenant validation)
        deleted = await self.repository.delete(tenant_id, credential_id)

        if deleted:
            logger.info("successfully_deleted_credential", credential_id=credential_id)
        else:
            logger.warning(
                "credential_not_found_for_deletion", credential_id=credential_id
            )

        return deleted

    async def associate_with_integration(
        self,
        tenant_id: str,
        integration_id: str,
        credential_id: UUID,
        is_primary: bool = False,
        purpose: str | None = None,
    ) -> bool:
        """
        Associate credential with integration.

        Args:
            tenant_id: Tenant identifier
            integration_id: Integration identifier
            credential_id: Credential UUID
            is_primary: Primary credential flag
            purpose: Usage purpose (read/write/admin)

        Returns:
            True if associated successfully
        """
        logger.info(
            "associating_credential_with_integration",
            credential_id=credential_id,
            integration_id=integration_id,
        )

        # Verify credential exists
        credential = await self.repository.get_by_id(tenant_id, credential_id)
        if not credential:
            logger.error(
                "credential_not_found_for_tenant",
                credential_id=credential_id,
                tenant_id=tenant_id,
            )
            return False

        # Create association
        try:
            await self.repository.associate_with_integration(
                tenant_id=tenant_id,
                integration_id=integration_id,
                credential_id=credential_id,
                is_primary=is_primary,
                purpose=purpose,
            )
            logger.info(
                "credential_associated_with_integration",
                credential_id=credential_id,
                integration_id=integration_id,
            )
            return True

        except Exception as e:
            logger.error(
                "failed_to_associate_credential",
                credential_id=credential_id,
                integration_id=integration_id,
                error=str(e),
            )
            raise

    async def get_integration_credentials(
        self, tenant_id: str, integration_id: str
    ) -> list[dict]:
        """
        Get credentials for an integration.

        Args:
            tenant_id: Tenant identifier
            integration_id: Integration identifier

        Returns:
            List of credential metadata for integration
        """
        logger.debug(
            "getting_integration_credentials",
            integration_id=integration_id,
            tenant_id=tenant_id,
        )

        # Get integration credentials from repository
        integration_credentials = await self.repository.list_by_integration(
            tenant_id, integration_id
        )

        # Convert to metadata response
        result = []
        for ic in integration_credentials:
            cred = ic.credential
            result.append(
                {
                    "id": str(cred.id),
                    "tenant_id": cred.tenant_id,
                    "provider": cred.provider,
                    "account": cred.account,
                    "key_version": cred.key_version,
                    "credential_metadata": cred.credential_metadata,
                    "created_at": cred.created_at.isoformat(),
                    "updated_at": (
                        cred.updated_at.isoformat() if cred.updated_at else None
                    ),
                    "created_by": cred.created_by,
                    "is_primary": ic.is_primary,
                    "purpose": ic.purpose,
                }
            )

        logger.debug(
            "found_integration_credentials",
            count=len(result),
            integration_id=integration_id,
        )
        return result
