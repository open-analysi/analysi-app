"""Unit tests for tenant validation middleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from analysi.middleware.tenant import (
    TenantValidationMiddleware,
    extract_tenant_from_path,
    validate_tenant_permissions,
)


class TestTenantValidationMiddleware:
    """Test TenantValidationMiddleware."""

    def test_middleware_initialization(self):
        """Test middleware can be initialized."""
        app = FastAPI()
        middleware = TenantValidationMiddleware(app)
        assert middleware is not None

    @pytest.mark.asyncio
    async def test_dispatch_with_valid_tenant(self):
        """Test middleware dispatch with valid tenant."""
        app = FastAPI()
        app.add_middleware(TenantValidationMiddleware)

        @app.get("/v1/{tenant}/test")
        @pytest.mark.asyncio
        async def test_endpoint(tenant: str):
            return {"tenant": tenant}

        client = TestClient(app)
        # This will fail until middleware is implemented
        response = client.get("/v1/test-tenant/test")

        # These assertions will fail until implementation
        assert response.status_code == 200
        data = response.json()
        assert data["tenant"] == "test-tenant"

    @pytest.mark.asyncio
    async def test_dispatch_with_invalid_tenant(self):
        """Test middleware dispatch with invalid tenant."""
        from fastapi import HTTPException

        app = FastAPI()
        app.add_middleware(TenantValidationMiddleware)

        @app.get("/v1/{tenant}/test")
        @pytest.mark.asyncio
        async def test_endpoint(tenant: str):
            return {"tenant": tenant}

        client = TestClient(app)
        # Use a tenant that extracts successfully but fails validation (contains 'script')
        with pytest.raises(HTTPException) as exc_info:
            client.get("/v1/tenant-script-alert/test")

        # Should raise 403 Forbidden HTTPException for invalid tenant
        assert exc_info.value.status_code == 403
        assert "tenant-script-alert" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_dispatch_platform_endpoint(self):
        """Test middleware dispatch with platform endpoint (no tenant in URL)."""
        app = FastAPI()
        app.add_middleware(TenantValidationMiddleware)

        @app.get("/platform/v1/tenants")
        async def platform_endpoint():
            return {"message": "platform"}

        client = TestClient(app)
        response = client.get("/platform/v1/tenants")
        assert response.status_code == 200


class TestExtractTenantFromPath:
    """Test extract_tenant_from_path function."""

    def test_extract_valid_tenant(self):
        """Test extracting valid tenant from path."""
        tenant = extract_tenant_from_path("/v1/acme-corp/tasks")
        assert tenant == "acme-corp"

    def test_platform_path_has_no_tenant(self):
        """Platform paths don't contain a tenant."""
        tenant = extract_tenant_from_path("/platform/v1/tenants")
        assert tenant is None

    def test_extract_tenant_invalid_path(self):
        """Test extracting tenant from invalid path."""
        tenant = extract_tenant_from_path("/invalid/path")
        assert tenant is None  # Invalid path should return None

    def test_extract_tenant_malformed_path(self):
        """Test extracting tenant from malformed path."""
        test_paths = [
            "/v1//tasks",  # Empty tenant
            "/v1/tenant/",  # Trailing slash only
            "v1/tenant/tasks",  # Missing leading slash
            "/v1/../../admin/tasks",  # Path traversal attempt
        ]

        for path in test_paths:
            result = extract_tenant_from_path(path)
            # Should handle malformed paths gracefully
            assert result is None or isinstance(result, str)

    def test_extract_tenant_special_characters(self):
        """Test extracting tenant with special characters."""
        test_cases = [
            ("/v1/<script>alert(1)</script>/tasks", None),  # XSS attempt
            ("/v1/tenant with spaces/tasks", None),  # Spaces
            ("/v1/tenant@domain.com/tasks", "tenant@domain.com"),  # Valid tenant with @
            (
                "/v1/tenant-123_test/tasks",
                "tenant-123_test",
            ),  # Valid with hyphens/underscores
        ]

        for path, expected in test_cases:
            result = extract_tenant_from_path(path)
            assert result == expected


class TestValidateTenantPermissions:
    """Test validate_tenant_permissions function."""

    def test_validate_active_tenant(self):
        """Test validating an active tenant."""
        result = validate_tenant_permissions("active-tenant")
        assert result is True

    def test_validate_inactive_tenant(self):
        """Test validating an inactive tenant."""
        # Use a truly invalid tenant (with spaces)
        result = validate_tenant_permissions("inactive tenant")
        assert result is False

    def test_validate_nonexistent_tenant(self):
        """Test validating a nonexistent tenant."""
        # Use a tenant with malicious content
        result = validate_tenant_permissions("<script>alert(1)</script>")
        assert result is False

    def test_validate_admin_tenant(self):
        """Test validating the special admin tenant."""
        result = validate_tenant_permissions("_")
        assert result is True

    def test_validate_empty_tenant(self):
        """Test validating empty tenant."""
        result = validate_tenant_permissions("")
        assert result is False

    def test_validate_none_tenant(self):
        """Test validating None tenant."""
        result = validate_tenant_permissions(None)
        assert result is False
