"""Tenant extraction and validation dependencies."""

from fastapi import HTTPException, Path, Request

from analysi.middleware.tenant import validate_tenant_permissions


async def get_tenant_id(
    request: Request,
    tenant: str = Path(
        ...,
        description="Tenant identifier",
        openapi_examples={"default": {"value": "default"}},
    ),
) -> str:
    """Extract and validate tenant ID from path parameter."""
    # Basic format validation
    if not tenant:
        raise HTTPException(status_code=400, detail="Tenant ID cannot be empty")

    # Validate tenant permissions (same logic as middleware)
    if not validate_tenant_permissions(tenant):
        raise HTTPException(
            status_code=403, detail=f"Access denied for tenant: {tenant}"
        )

    # Add tenant to request state
    request.state.tenant_id = tenant

    return tenant


async def validate_tenant_access(tenant_id: str) -> str:
    """Validate that the current user has access to the specified tenant."""
    # Use the same validation logic as middleware
    if not validate_tenant_permissions(tenant_id):
        # Check if it's a format issue (400) or permission issue (403)
        if not tenant_id or len(tenant_id) > 100:
            raise HTTPException(status_code=400, detail="Invalid tenant ID format")
        raise HTTPException(
            status_code=403, detail=f"Access denied for tenant: {tenant_id}"
        )

    return tenant_id


def get_current_tenant(request: Request) -> str | None:
    """Get tenant ID from request state (set by middleware)."""
    if not hasattr(request, "state"):
        return None

    return getattr(request.state, "tenant_id", None)
