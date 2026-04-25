"""FastAPI router for credential management endpoints.

Following CustomerCredentials spec for API surface.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api import ApiListResponse, ApiResponse, api_list_response, api_response
from analysi.auth.dependencies import require_permission
from analysi.auth.messages import INTERNAL_ERROR
from analysi.config.logging import get_logger
from analysi.db.session import get_db
from analysi.schemas.credential import (
    CredentialCreate,
    CredentialDecrypted,
    CredentialMetadata,
    CredentialResponse,
    CredentialRotateResponse,
    IntegrationCredentialAssociation,
    IntegrationCredentialResponse,
)
from analysi.services.credential_service import CredentialService

logger = get_logger(__name__)

router = APIRouter(
    prefix="/{tenant}/credentials",
    tags=["credentials"],
    dependencies=[Depends(require_permission("integrations", "read"))],
)


# Dependency injection
async def get_credential_service(
    session: AsyncSession = Depends(get_db),
) -> CredentialService:
    """Get credential service with dependencies."""
    return CredentialService(session)


@router.post(
    "",
    response_model=ApiResponse[CredentialResponse],
    status_code=201,
    dependencies=[Depends(require_permission("integrations", "create"))],
)
async def create_credential(
    request: Request,
    tenant: str,
    credential_data: CredentialCreate,
    service: CredentialService = Depends(get_credential_service),
) -> ApiResponse[CredentialResponse]:
    """Create or update credential (upsert by tenant/provider/account).

    This endpoint encrypts the provided secret using Vault Transit and stores
    the ciphertext in the database.
    """
    try:
        credential_id, key_version = await service.store_credential(
            tenant_id=tenant,
            provider=credential_data.provider,
            secret=credential_data.secret,
            account=credential_data.account,
            credential_metadata=credential_data.credential_metadata,
        )

        # Get the credential to return full response
        credential_list = await service.list_credentials(
            tenant_id=tenant, provider=credential_data.provider, limit=100, offset=0
        )

        # Find the credential we just created/updated
        for cred_dict in credential_list:
            if str(cred_dict["id"]) == str(credential_id):
                return api_response(
                    CredentialResponse(
                        id=UUID(cred_dict["id"]),
                        tenant_id=cred_dict["tenant_id"],
                        provider=cred_dict["provider"],
                        account=cred_dict["account"],
                        credential_metadata=cred_dict["credential_metadata"],
                        key_version=cred_dict["key_version"],
                        created_at=datetime.fromisoformat(cred_dict["created_at"]),
                        updated_at=(
                            datetime.fromisoformat(cred_dict["updated_at"])
                            if cred_dict["updated_at"]
                            else datetime.fromisoformat(cred_dict["created_at"])
                        ),
                    ),
                    request=request,
                )

        # Fallback if not found in list (shouldn't happen)
        raise HTTPException(
            status_code=500, detail="Failed to retrieve created credential"
        )

    except Exception as e:
        logger.error("create_credential_failed", error=str(e))
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR)


@router.get("", response_model=ApiListResponse[CredentialMetadata])
async def list_credentials(
    request: Request,
    tenant: str,
    provider: str = Query(None, description="Filter by provider"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    service: CredentialService = Depends(get_credential_service),
) -> ApiListResponse[CredentialMetadata]:
    """List credential metadata (no plaintext secrets).

    Returns metadata only - secrets are never included in list operations.
    """
    try:
        credentials_data = await service.list_credentials(
            tenant_id=tenant, provider=provider, limit=limit, offset=offset
        )
        total = await service.count_credentials(tenant_id=tenant, provider=provider)

        items = [
            CredentialMetadata(
                id=UUID(cred["id"]),
                provider=cred["provider"],
                account=cred["account"],
                credential_metadata=cred["credential_metadata"],
                created_at=datetime.fromisoformat(cred["created_at"]),
            )
            for cred in credentials_data
        ]

        return api_list_response(items, total=total, request=request)

    except Exception as e:
        logger.error("list_credentials_failed", error=str(e))
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR)


@router.get(
    "/{credential_id}",
    response_model=ApiResponse[CredentialDecrypted],
    dependencies=[Depends(require_permission("integrations", "update"))],
)
async def get_credential(
    request: Request,
    tenant: str,
    credential_id: UUID,
    service: CredentialService = Depends(get_credential_service),
) -> ApiResponse[CredentialDecrypted]:
    """Get decrypted credential (internal use only, audited).

    This endpoint decrypts the credential and returns the plaintext secret.
    All access is logged for audit purposes.
    """
    try:
        # Get decrypted secret
        secret = await service.get_credential(tenant, credential_id)
        if secret is None:
            raise HTTPException(status_code=404, detail="Credential not found")

        # Get metadata
        credentials_list = await service.list_credentials(tenant_id=tenant, limit=1000)
        credential_metadata = None
        for cred in credentials_list:
            if str(cred["id"]) == str(credential_id):
                credential_metadata = cred
                break

        if not credential_metadata:
            raise HTTPException(status_code=404, detail="Credential metadata not found")

        return api_response(
            CredentialDecrypted(
                id=credential_id,
                provider=credential_metadata["provider"],
                account=credential_metadata["account"],
                secret=secret,
                credential_metadata=credential_metadata["credential_metadata"],
                key_version=credential_metadata["key_version"],
            ),
            request=request,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_credential_failed", error=str(e))
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR)


@router.post(
    "/{credential_id}/rotate",
    response_model=ApiResponse[CredentialRotateResponse],
    dependencies=[Depends(require_permission("integrations", "update"))],
)
async def rotate_credential(
    request: Request,
    tenant: str,
    credential_id: UUID,
    service: CredentialService = Depends(get_credential_service),
) -> ApiResponse[CredentialRotateResponse]:
    """Re-encrypt credential with latest key version.

    Rotates the credential to use the latest encryption key version.
    """
    try:
        new_key_version = await service.rotate_credential(tenant, credential_id)

        return api_response(
            CredentialRotateResponse(
                id=credential_id,
                new_key_version=new_key_version,
                rotated_at=datetime.now(tz=UTC),
            ),
            request=request,
        )

    except ValueError:
        raise HTTPException(status_code=404, detail="Credential not found")
    except Exception as e:
        logger.error("rotate_credential_failed", error=str(e))
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR)


@router.delete(
    "/{credential_id}",
    status_code=204,
    dependencies=[Depends(require_permission("integrations", "delete"))],
)
async def delete_credential(
    tenant: str,
    credential_id: UUID,
    service: CredentialService = Depends(get_credential_service),
) -> None:
    """Delete credential."""
    try:
        deleted = await service.delete_credential(tenant, credential_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Credential not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_credential_failed", error=str(e))
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR)


# Integration association endpoints
@router.post(
    "/integrations/{integration_id}/associate",
    response_model=ApiResponse[IntegrationCredentialResponse],
    status_code=201,
    dependencies=[Depends(require_permission("integrations", "update"))],
)
async def associate_credential_with_integration(
    request: Request,
    tenant: str,
    integration_id: str,
    association: IntegrationCredentialAssociation,
    service: CredentialService = Depends(get_credential_service),
) -> ApiResponse[IntegrationCredentialResponse]:
    """Associate credential with integration."""
    try:
        success = await service.associate_with_integration(
            tenant_id=tenant,
            integration_id=integration_id,
            credential_id=association.credential_id,
            is_primary=association.is_primary,
            purpose=association.purpose,
        )

        if not success:
            raise HTTPException(
                status_code=400, detail="Failed to associate credential"
            )

        # Get credential metadata to return
        credentials_list = await service.list_credentials(tenant_id=tenant, limit=1000)
        for cred in credentials_list:
            if str(cred["id"]) == str(association.credential_id):
                return api_response(
                    IntegrationCredentialResponse(
                        credential_id=association.credential_id,
                        provider=cred["provider"],
                        account=cred["account"],
                        is_primary=association.is_primary,
                        purpose=association.purpose,
                        created_at=datetime.fromisoformat(cred["created_at"]),
                    ),
                    request=request,
                )

        raise HTTPException(status_code=404, detail="Credential not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error("associate_credential_failed", error=str(e))
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR)


@router.get(
    "/integrations/{integration_id}",
    response_model=ApiListResponse[IntegrationCredentialResponse],
)
async def list_integration_credentials(
    request: Request,
    tenant: str,
    integration_id: str,
    service: CredentialService = Depends(get_credential_service),
) -> ApiListResponse[IntegrationCredentialResponse]:
    """List credentials associated with integration."""
    try:
        credentials_data = await service.get_integration_credentials(
            tenant_id=tenant, integration_id=integration_id
        )

        items = [
            IntegrationCredentialResponse(
                credential_id=UUID(cred["id"]),
                provider=cred["provider"],
                account=cred["account"],
                is_primary=cred["is_primary"],
                purpose=cred["purpose"],
                created_at=datetime.fromisoformat(cred["created_at"]),
            )
            for cred in credentials_data
        ]

        return api_list_response(items, total=len(items), request=request)

    except Exception as e:
        logger.error("list_integration_credentials_failed", error=str(e))
        raise HTTPException(status_code=500, detail=INTERNAL_ERROR)
