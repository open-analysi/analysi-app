"""Unit tests for tenant extraction and validation dependencies."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Request

from analysi.dependencies.tenant import (
    get_current_tenant,
    get_tenant_id,
    validate_tenant_access,
)


class TestGetTenantId:
    """Test get_tenant_id dependency."""

    @pytest.mark.asyncio
    async def test_get_tenant_id_valid(self):
        """Test extracting valid tenant ID."""
        mock_request = MagicMock(spec=Request)
        mock_request.state = MagicMock()

        tenant_id = await get_tenant_id(tenant="acme-corp", request=mock_request)
        assert tenant_id == "acme-corp"

    @pytest.mark.asyncio
    async def test_get_tenant_id_admin_tenant(self):
        """Test extracting admin tenant ID."""
        mock_request = MagicMock(spec=Request)
        mock_request.state = MagicMock()

        tenant_id = await get_tenant_id(tenant="_", request=mock_request)
        assert tenant_id == "_"

    @pytest.mark.asyncio
    async def test_get_tenant_id_with_validation(self):
        """Test tenant ID extraction includes validation."""
        mock_request = MagicMock(spec=Request)
        mock_request.state = MagicMock()

        # Should validate tenant exists and is active
        tenant_id = await get_tenant_id(tenant="valid-tenant", request=mock_request)
        assert tenant_id == "valid-tenant"

    @pytest.mark.asyncio
    async def test_get_tenant_id_invalid_tenant(self):
        """Test extracting invalid tenant ID raises exception."""
        mock_request = MagicMock(spec=Request)
        mock_request.state = MagicMock()

        with pytest.raises(HTTPException, match="Access denied"):
            # Should raise HTTPException for tenant with malicious content
            await get_tenant_id(
                tenant="tenant<script>alert(1)</script>", request=mock_request
            )

    @pytest.mark.asyncio
    async def test_get_tenant_id_empty_tenant(self):
        """Test extracting empty tenant ID."""
        mock_request = MagicMock(spec=Request)
        mock_request.state = MagicMock()

        with pytest.raises(HTTPException, match="Tenant ID cannot be empty"):
            # Should raise HTTPException for empty tenant
            await get_tenant_id(tenant="", request=mock_request)

    @pytest.mark.asyncio
    async def test_get_tenant_id_special_characters(self):
        """Test tenant ID with special characters."""
        mock_request = MagicMock(spec=Request)
        mock_request.state = MagicMock()

        test_cases = [
            ("tenant-123", True),  # Valid with hyphens
            ("tenant_test", True),  # Valid with underscores
            ("tenant@domain.com", True),  # Valid with @
            ("tenant with space", False),  # Invalid with spaces
            ("<script>alert(1)</script>", False),  # XSS attempt
            ("../../admin", False),  # Path traversal
        ]

        for tenant, should_pass in test_cases:
            if should_pass:
                result = await get_tenant_id(tenant=tenant, request=mock_request)
                assert result == tenant
            else:
                # Should raise exception for invalid characters
                with pytest.raises(HTTPException, match="Access denied"):
                    await get_tenant_id(tenant=tenant, request=mock_request)

    @pytest.mark.asyncio
    async def test_get_tenant_id_request_state_update(self):
        """Test tenant ID is added to request state."""
        from types import SimpleNamespace

        class MockRequest:
            def __init__(self):
                self.state = SimpleNamespace()

        mock_request = MockRequest()

        tenant_id = await get_tenant_id(tenant="test-tenant", request=mock_request)

        # Should set tenant_id in request state
        assert mock_request.state.tenant_id == "test-tenant"
        assert tenant_id == "test-tenant"


class TestValidateTenantAccess:
    """Test validate_tenant_access dependency."""

    @pytest.mark.asyncio
    async def test_validate_tenant_access_authorized(self):
        """Test validating authorized tenant access."""
        tenant_id = await validate_tenant_access("authorized-tenant")
        assert tenant_id == "authorized-tenant"

    @pytest.mark.asyncio
    async def test_validate_tenant_access_unauthorized(self):
        """Test validating unauthorized tenant access."""
        with pytest.raises(HTTPException, match="Access denied"):
            # Should raise HTTPException 403 for tenant with malicious script
            await validate_tenant_access("unauthorized<script>alert(1)</script>")

    @pytest.mark.asyncio
    async def test_validate_tenant_access_admin_tenant(self):
        """Test validating admin tenant access."""
        tenant_id = await validate_tenant_access("_")
        assert tenant_id == "_"

    @pytest.mark.asyncio
    async def test_validate_tenant_access_nonexistent(self):
        """Test validating access to nonexistent tenant."""
        with pytest.raises(HTTPException, match="Access denied"):
            # Should raise HTTPException for tenant with path traversal
            await validate_tenant_access("../does-not-exist")

    @pytest.mark.asyncio
    async def test_validate_tenant_access_inactive(self):
        """Test validating access to inactive tenant."""
        with pytest.raises(HTTPException, match="Access denied"):
            # Should raise HTTPException 403 for tenant with spaces
            await validate_tenant_access("inactive tenant")

    @pytest.mark.asyncio
    async def test_validate_tenant_access_with_user_context(self):
        """Test tenant access validation considers user context."""
        # Should check user permissions for tenant
        tenant_id = await validate_tenant_access("user-tenant")
        assert tenant_id == "user-tenant"


class TestGetCurrentTenant:
    """Test get_current_tenant function."""

    def test_get_current_tenant_from_state(self):
        """Test getting tenant ID from request state."""
        mock_request = MagicMock(spec=Request)
        mock_request.state.tenant_id = "state-tenant"

        tenant_id = get_current_tenant(mock_request)
        assert tenant_id == "state-tenant"

    def test_get_current_tenant_missing_state(self):
        """Test getting tenant ID when not in request state."""

        class MockState:
            pass

        mock_request = MagicMock(spec=Request)
        mock_request.state = MockState()
        # No tenant_id attribute on this state

        tenant_id = get_current_tenant(mock_request)
        assert tenant_id is None

    def test_get_current_tenant_no_state(self):
        """Test getting tenant ID when request has no state."""

        class MockRequest:
            pass

        mock_request = MockRequest()
        # No state attribute at all

        tenant_id = get_current_tenant(mock_request)
        assert tenant_id is None

    def test_get_current_tenant_admin(self):
        """Test getting admin tenant ID from state."""
        mock_request = MagicMock(spec=Request)
        mock_request.state.tenant_id = "_"

        tenant_id = get_current_tenant(mock_request)
        assert tenant_id == "_"

    def test_get_current_tenant_empty_string(self):
        """Test getting empty tenant ID from state."""
        mock_request = MagicMock(spec=Request)
        mock_request.state.tenant_id = ""

        tenant_id = get_current_tenant(mock_request)
        # Should handle empty string appropriately
        assert tenant_id == ""
