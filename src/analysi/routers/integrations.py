"""
FastAPI router for Integration endpoints.

Use /schedules, /tasks/{id}/schedule, /workflows/{id}/schedule for scheduling.
Use /integrations/{id}/managed for managed resource access.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api import (
    ApiListResponse,
    ApiResponse,
    api_list_response,
    api_response,
)
from analysi.auth.dependencies import require_permission
from analysi.config.logging import get_logger
from analysi.db.session import get_db
from analysi.repositories.integration_repository import IntegrationRepository
from analysi.schemas.credential import (
    IntegrationCredentialCreateAndAssociate,
    IntegrationCredentialResponse,
)
from analysi.schemas.integration import (
    AllToolsResponse,
    IntegrationActionResponse,
    IntegrationCreate,
    IntegrationHealth,
    IntegrationRegistryDetail,
    IntegrationRegistrySummary,
    IntegrationResponse,
    IntegrationToggleResponse,
    IntegrationUpdate,
    ProvisionFreeIntegrationResult,
    ProvisionFreeResponse,
    ToolParamsSchema,
    ToolSummary,
)
from analysi.services.credential_service import CredentialService
from analysi.services.integration_registry_service import IntegrationRegistryService
from analysi.services.integration_service import IntegrationService

logger = get_logger(__name__)

router = APIRouter(
    prefix="/{tenant}/integrations",
    tags=["integrations"],
    dependencies=[Depends(require_permission("integrations", "read"))],
)


# Dependency injection helpers
async def get_integration_service(
    session: AsyncSession = Depends(get_db),
) -> IntegrationService:
    """Get integration service with dependencies."""
    integration_repo = IntegrationRepository(session)
    from analysi.repositories.credential_repository import CredentialRepository

    credential_repo = CredentialRepository(session)
    return IntegrationService(
        integration_repo=integration_repo,
        credential_repo=credential_repo,
    )


async def get_credential_service(
    session: AsyncSession = Depends(get_db),
) -> CredentialService:
    """Get credential service with dependencies."""
    return CredentialService(session)


async def get_registry_service() -> IntegrationRegistryService:
    """Get integration registry service."""
    return IntegrationRegistryService.get_instance()


# Registry endpoints - must come before dynamic routes
@router.get("/tools/all", response_model=ApiResponse[AllToolsResponse])
async def list_all_tools(
    tenant: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """List all available tools (cy-language builtins + native + integration) with schemas.

    Returns tool summaries for autocomplete, including FQN, description, and params_schema.
    Combines:
    1. cy-language built-in tools (sum, len, keys, join, etc.)
    2. Custom native tools (llm_run, store_artifact, etc.)
    3. Integration tools (app::virustotal::ip_reputation, etc.)
    """
    import inspect

    from cy_language.ui.tools import default_registry

    from analysi.services.cy_tool_registry import load_tool_registry_async
    from analysi.services.native_tools_registry import _python_type_to_json_schema

    tools = []

    # SOURCE 1: cy-language built-in tools (sum, len, str, keys, join, etc.)
    builtin_descriptions = {
        t["name"]: t.get("description", "")
        for t in default_registry.get_tool_descriptions()
    }
    builtin_funcs = default_registry.get_tools_dict()

    for name, fn in builtin_funcs.items():
        sig = inspect.signature(fn)
        properties = {}
        required = []
        for pname, param in sig.parameters.items():
            if param.annotation != inspect.Parameter.empty:
                properties[pname] = _python_type_to_json_schema(param.annotation)
            else:
                properties[pname] = {"type": "object"}
            if param.default == inspect.Parameter.empty:
                required.append(pname)

        tools.append(
            ToolSummary(
                fqn=name,
                name=name,
                description=builtin_descriptions.get(name, ""),
                category="builtin",
                integration_id=None,
                params_schema=ToolParamsSchema(
                    type="object",
                    properties=properties,
                    required=required,
                ),
            )
        )

    # SOURCE 2 + 3: Custom native + integration tools from registry
    tool_registry = await load_tool_registry_async(session, tenant)

    for fqn, schema in tool_registry.items():
        short_name = fqn.split("::")[-1] if "::" in fqn else fqn

        description = schema.get("description", "")

        # Determine category and integration_id
        integration_id = None
        parts = fqn.split("::")
        if len(parts) >= 2 and parts[0] == "app":
            category = "integration"
            integration_id = parts[1]
        elif fqn.startswith("native::"):
            category = "native"
        else:
            category = "other"

        tools.append(
            ToolSummary(
                fqn=fqn,
                name=short_name,
                description=description,
                category=category,
                integration_id=integration_id,
                params_schema=ToolParamsSchema(
                    type="object",
                    properties=schema.get("parameters", {}),
                    required=schema.get("required", []),
                ),
            )
        )

    return api_response(
        AllToolsResponse(tools=tools, total=len(tools)), request=request
    )


@router.get("/registry", response_model=ApiListResponse[IntegrationRegistrySummary])
async def list_integration_types(
    tenant: str,
    request: Request,
    registry: IntegrationRegistryService = Depends(get_registry_service),
):
    """List all available integration types."""
    result = await registry.list_integrations()
    items = [IntegrationRegistrySummary(**r) for r in result]
    return api_list_response(items, total=len(items), request=request)


@router.get(
    "/registry/{integration_type}",
    response_model=ApiResponse[IntegrationRegistryDetail],
)
async def get_integration_type(
    tenant: str,
    integration_type: str,
    request: Request,
    registry: IntegrationRegistryService = Depends(get_registry_service),
):
    """Get details for a specific integration type."""
    integration = await registry.get_integration(integration_type)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration type not found")
    return api_response(IntegrationRegistryDetail(**integration), request=request)


def _action_to_response(action) -> IntegrationActionResponse:
    """Convert a manifest ActionDefinition to an API response schema."""
    return IntegrationActionResponse(
        action_id=action.id,
        name=action.name or action.id.replace("_", " ").title(),
        description=action.description or "",
        categories=action.categories or [],
        enabled=action.enabled,
        params_schema=action.metadata.get(
            "params_schema", {"type": "object", "properties": {}}
        ),
        result_schema=action.metadata.get("result_schema", {"type": "object"}),
    )


def _get_manifest_or_404(
    registry_service: IntegrationRegistryService, integration_type: str
):
    """Look up a manifest via the registry service's framework backend, or raise 404."""
    manifest = registry_service.framework.get_integration(integration_type)
    if not manifest:
        raise HTTPException(status_code=404, detail="Integration type not found")
    return manifest


@router.get(
    "/registry/{integration_type}/actions",
    response_model=ApiListResponse[IntegrationActionResponse],
)
async def list_integration_actions(
    tenant: str,
    integration_type: str,
    request: Request,
    registry: IntegrationRegistryService = Depends(get_registry_service),
):
    """List all actions for an integration type."""
    manifest = _get_manifest_or_404(registry, integration_type)
    actions = [_action_to_response(a) for a in manifest.actions]
    return api_list_response(actions, total=len(actions), request=request)


@router.get(
    "/registry/{integration_type}/actions/{action_id}",
    response_model=ApiResponse[IntegrationActionResponse],
)
async def get_integration_action(
    tenant: str,
    integration_type: str,
    action_id: str,
    request: Request,
    registry: IntegrationRegistryService = Depends(get_registry_service),
):
    """Get details for a specific action within an integration type."""
    manifest = _get_manifest_or_404(registry, integration_type)

    for action in manifest.actions:
        if action.id == action_id:
            return api_response(_action_to_response(action), request=request)

    raise HTTPException(status_code=404, detail="Action not found")


# Integration management endpoints
@router.get("", response_model=ApiListResponse[IntegrationResponse])
async def list_integrations(
    tenant: str,
    request: Request,
    enabled: bool | None = None,
    service: IntegrationService = Depends(get_integration_service),
):
    """List all integrations for a tenant."""
    result = await service.list_integrations(tenant, enabled=enabled)
    return api_list_response(result, total=len(result), request=request)


@router.post(
    "",
    response_model=ApiResponse[IntegrationResponse],
    status_code=201,
    dependencies=[Depends(require_permission("integrations", "create"))],
)
async def create_integration(
    tenant: str,
    integration_data: IntegrationCreate,
    request: Request,
    service: IntegrationService = Depends(get_integration_service),
):
    """Create a new integration."""
    try:
        result = await service.create_integration(tenant, integration_data)
        return api_response(result, request=request)
    except ValueError as e:
        msg = str(e)
        if "not supported" in msg:
            logger.warning("unsupported_integration_type", error=msg)
            raise HTTPException(
                status_code=409, detail="Integration type not supported"
            )
        raise HTTPException(status_code=409, detail="Integration already exists")


@router.post(
    "/provision-free",
    response_model=ApiResponse[ProvisionFreeResponse],
    dependencies=[Depends(require_permission("integrations", "create"))],
)
async def provision_free_integrations(
    tenant: str,
    request: Request,
    service: IntegrationService = Depends(get_integration_service),
):
    """Provision all free integrations (no API key required) for a tenant.

    Idempotent: skips integrations that already exist. Returns a summary
    of what was created vs already present.
    """
    registry = IntegrationRegistryService.get_instance()
    all_types = await registry.list_integrations()
    free_types = [t for t in all_types if not t["requires_credentials"]]

    results: list[ProvisionFreeIntegrationResult] = []
    created_count = 0
    exists_count = 0

    for integration_type_info in free_types:
        integration_type = integration_type_info["integration_type"]
        display_name = integration_type_info["display_name"]

        # Use the manifest's default integration_id, or fall back to type name
        id_config = integration_type_info.get("integration_id_config") or {}
        integration_id = id_config.get("default", f"{integration_type}-default")

        try:
            await service.create_integration(
                tenant,
                IntegrationCreate(
                    integration_id=integration_id,
                    integration_type=integration_type,
                    name=display_name,
                    enabled=True,
                ),
            )
            results.append(
                ProvisionFreeIntegrationResult(
                    integration_type=integration_type,
                    integration_id=integration_id,
                    name=display_name,
                    status="created",
                )
            )
            created_count += 1
            logger.info(
                "free_integration_provisioned",
                tenant_id=tenant,
                integration_type=integration_type,
                integration_id=integration_id,
            )
        except ValueError:
            # Already exists — that's fine, this is idempotent
            results.append(
                ProvisionFreeIntegrationResult(
                    integration_type=integration_type,
                    integration_id=integration_id,
                    name=display_name,
                    status="already_exists",
                )
            )
            exists_count += 1

    return api_response(
        ProvisionFreeResponse(
            created=created_count,
            already_exists=exists_count,
            integrations=results,
        ),
        request=request,
    )


@router.get("/{integration_id}", response_model=ApiResponse[IntegrationResponse])
async def get_integration(
    tenant: str,
    integration_id: str,
    request: Request,
    service: IntegrationService = Depends(get_integration_service),
):
    """Get integration details."""
    integration = await service.get_integration(tenant, integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    return api_response(integration, request=request)


@router.patch(
    "/{integration_id}",
    response_model=ApiResponse[IntegrationResponse],
    dependencies=[Depends(require_permission("integrations", "update"))],
)
async def update_integration(
    tenant: str,
    integration_id: str,
    update_data: IntegrationUpdate,
    request: Request,
    service: IntegrationService = Depends(get_integration_service),
):
    """Update an existing integration."""
    integration = await service.update_integration(tenant, integration_id, update_data)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    return api_response(integration, request=request)


@router.delete(
    "/{integration_id}",
    status_code=204,
    dependencies=[Depends(require_permission("integrations", "delete"))],
)
async def delete_integration(
    tenant: str,
    integration_id: str,
    service: IntegrationService = Depends(get_integration_service),
):
    """Delete an integration and its managed resources."""
    deleted = await service.delete_integration(tenant, integration_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Integration not found")


@router.get("/{integration_id}/health", response_model=ApiResponse[IntegrationHealth])
async def get_integration_health(
    tenant: str,
    integration_id: str,
    request: Request,
    service: IntegrationService = Depends(get_integration_service),
):
    """Get integration health status."""
    result = await service.calculate_health(tenant, integration_id)
    return api_response(result, request=request)


# Enable/Disable with Schedule Cascading
@router.post(
    "/{integration_id}/enable",
    response_model=ApiResponse[IntegrationToggleResponse],
    dependencies=[Depends(require_permission("integrations", "update"))],
)
async def enable_integration(
    tenant: str,
    integration_id: str,
    request: Request,
    service: IntegrationService = Depends(get_integration_service),
):
    """Enable integration and cascade-enable its schedules."""
    integration = await service.update_integration(
        tenant_id=tenant,
        integration_id=integration_id,
        data=IntegrationUpdate(enabled=True),
    )

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    return api_response(
        IntegrationToggleResponse(status="enabled", integration_id=integration_id),
        request=request,
    )


@router.post(
    "/{integration_id}/disable",
    response_model=ApiResponse[IntegrationToggleResponse],
    dependencies=[Depends(require_permission("integrations", "update"))],
)
async def disable_integration(
    tenant: str,
    integration_id: str,
    request: Request,
    service: IntegrationService = Depends(get_integration_service),
):
    """Disable integration and cascade-disable its schedules."""
    integration = await service.update_integration(
        tenant_id=tenant,
        integration_id=integration_id,
        data=IntegrationUpdate(enabled=False),
    )

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    return api_response(
        IntegrationToggleResponse(status="disabled", integration_id=integration_id),
        request=request,
    )


@router.post(
    "/{integration_id}/credentials",
    response_model=ApiResponse[IntegrationCredentialResponse],
    status_code=201,
    dependencies=[Depends(require_permission("integrations", "update"))],
)
async def create_and_associate_credential(
    tenant: str,
    integration_id: str,
    credential_data: IntegrationCredentialCreateAndAssociate,
    request: Request,
    integration_service: IntegrationService = Depends(get_integration_service),
    credential_service: CredentialService = Depends(get_credential_service),
):
    """Create a credential and associate it with an integration in one step."""
    integration = await integration_service.get_integration(tenant, integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    try:
        credential_id, key_version = await credential_service.store_credential(
            tenant_id=tenant,
            provider=credential_data.provider,
            secret=credential_data.secret,
            account=credential_data.account,
            credential_metadata=credential_data.credential_metadata,
        )

        success = await credential_service.associate_with_integration(
            tenant_id=tenant,
            integration_id=integration_id,
            credential_id=credential_id,
            is_primary=credential_data.is_primary,
            purpose=credential_data.purpose,
        )

        if not success:
            raise HTTPException(status_code=500, detail="Internal server error")

        credentials_list = await credential_service.list_credentials(
            tenant_id=tenant, limit=1000
        )

        for cred in credentials_list:
            if str(cred["id"]) == str(credential_id):
                from datetime import datetime

                return api_response(
                    IntegrationCredentialResponse(
                        credential_id=credential_id,
                        provider=cred["provider"],
                        account=cred["account"],
                        is_primary=credential_data.is_primary,
                        purpose=credential_data.purpose,
                        created_at=datetime.fromisoformat(cred["created_at"]),
                    ),
                    request=request,
                )

        raise HTTPException(
            status_code=500,
            detail="Credential created and associated but could not retrieve metadata",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("failed_to_create_and_associate_credential", error=str(e))
        raise HTTPException(
            status_code=500, detail="Failed to create and associate credential"
        )
