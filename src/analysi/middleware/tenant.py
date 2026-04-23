"""Tenant validation middleware for multi-tenant routing."""

import re

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware


class TenantValidationMiddleware(BaseHTTPMiddleware):
    """Middleware to validate tenant from URL path and add to request state."""

    async def dispatch(self, request: Request, call_next):
        """Process request and validate tenant."""
        # Extract tenant from URL path
        tenant_id = extract_tenant_from_path(str(request.url.path))

        if tenant_id is not None:
            # Validate tenant permissions
            if not validate_tenant_permissions(tenant_id):
                raise HTTPException(
                    status_code=403, detail=f"Access denied for tenant: {tenant_id}"
                )

            # Add tenant to request state for use by dependencies
            request.state.tenant_id = tenant_id

        # Continue with request
        response = await call_next(request)
        return response


def extract_tenant_from_path(path: str) -> str | None:
    """Extract tenant ID from URL path following /v1/{tenant}/... pattern."""
    if not path:
        return None

    # Pattern for data plane: /v1/{tenant}/...
    data_plane_pattern = r"^/v1/([^/]+)(/.*)?$"
    match = re.match(data_plane_pattern, path)
    if match:
        tenant_candidate = match.group(1)

        # Validate tenant format (basic security check)
        if _is_valid_tenant_format(tenant_candidate):
            return tenant_candidate
        return None

    # /platform/v1/* endpoints are tenant-agnostic (no tenant in URL)
    # No tenant found in path
    return None


def validate_tenant_permissions(tenant_id: str) -> bool:
    """Validate that tenant exists and is active."""
    if not tenant_id:
        return False

    # Special case: admin tenant always allowed
    if tenant_id == "_":
        return True

    # Basic validation
    # In future phases, this would check database for tenant status

    # Basic format validation
    if not _is_valid_tenant_format(tenant_id):
        return False

    # Block obvious invalid/malicious tenants
    blocked_patterns = [
        r"\.\.",  # Path traversal (any .. sequence)
        r"<.*>",  # HTML/XSS
        r"script",  # Script injection
        r"[;\|&]",  # Command injection
        r"[\s]",  # Contains spaces
    ]

    for pattern in blocked_patterns:
        if re.search(pattern, tenant_id, re.IGNORECASE):
            return False

    # For now, allow all properly formatted tenants
    return True


def _is_valid_tenant_format(tenant_id: str) -> bool:
    """Check if tenant ID has valid format."""
    if not tenant_id:
        return False

    # Allow letters, numbers, hyphens, underscores, @ symbol
    # Length between 1-100 characters
    pattern = r"^[a-zA-Z0-9@._-]{1,100}$"
    return bool(re.match(pattern, tenant_id))
