"""Router for integration tool execution API."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.api.responses import ApiResponse, api_response
from analysi.auth.dependencies import require_permission
from analysi.config.logging import get_logger
from analysi.db.session import get_db
from analysi.schemas.integration_execution import (
    IntegrationToolExecuteRequest,
    IntegrationToolExecuteResponse,
)
from analysi.services.integration_execution_service import (
    IntegrationExecutionService,
)

logger = get_logger(__name__)

router = APIRouter(
    prefix="/{tenant}/integrations",
    tags=["integration-execution"],
    dependencies=[Depends(require_permission("integrations", "read"))],
)


@router.post(
    "/{integration_id}/tools/{action_id}/execute",
    response_model=ApiResponse[IntegrationToolExecuteResponse],
    status_code=200,
    dependencies=[Depends(require_permission("integrations", "execute"))],
)
async def execute_integration_tool(
    tenant: str,
    integration_id: str,
    action_id: str,
    body: IntegrationToolExecuteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[IntegrationToolExecuteResponse]:
    """
    Execute an integration tool and return results.

    Enables testing integration tools before writing Cy scripts.

    Args:
        tenant: Tenant ID
        integration_id: Integration identifier (e.g., "virustotal", "splunk")
        action_id: Action identifier (e.g., "ip_reputation", "health_check")
        request: Execution request with arguments and timeout
        db: Database session

    Returns:
        Execution results with output and optional schema

    Raises:
        HTTPException: 404 if integration/action not found, 400 for validation errors

    Examples:
        - Splunk health check: POST /v1/default/integrations/splunk/tools/health_check/execute
          Body: {"arguments": {}, "timeout_seconds": 30}
        - VirusTotal IP lookup: POST /v1/default/integrations/virustotal/tools/ip_reputation/execute
          Body: {"arguments": {"ip": "8.8.8.8"}, "timeout_seconds": 30}
    """
    # Create service
    service = IntegrationExecutionService(db)

    # Execute tool
    result = await service.execute_tool(
        tenant_id=tenant,
        integration_id=integration_id,
        action_id=action_id,
        arguments=body.arguments,
        timeout_seconds=body.timeout_seconds,
        capture_schema=body.capture_schema,
    )

    # Handle errors with appropriate HTTP status codes
    if result["status"] == "error":
        error_msg = result.get("error", "Unknown error")
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)

    # Return response
    return api_response(
        IntegrationToolExecuteResponse(
            status=result["status"],
            output=result["output"],
            output_schema=result.get("output_schema"),
            error=result.get("error"),
            execution_time_ms=result["execution_time_ms"],
        ),
        request=request,
    )
