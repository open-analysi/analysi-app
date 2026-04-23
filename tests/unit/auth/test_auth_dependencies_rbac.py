"""Unit tests for RBAC dependencies.

Tests check_tenant_access, require_permission, require_platform_admin.
"""

from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from analysi.auth.dependencies import (
    check_tenant_access,
    require_platform_admin,
)
from analysi.auth.models import CurrentUser


def _make_user(
    roles: list[str],
    tenant_id: str | None = "acme",
    user_id: str | None = None,
) -> CurrentUser:
    return CurrentUser(
        user_id=user_id or str(uuid4()),
        email="test@example.com",
        tenant_id=tenant_id,
        roles=roles,
        actor_type="user",
    )


class TestCheckTenantAccess:
    """Tests for check_tenant_access dependency."""

    @pytest.mark.asyncio
    async def test_platform_admin_bypasses_any_tenant(self):
        """platform_admin with tenant_id=None can access any tenant URL."""
        user = _make_user(["platform_admin"], tenant_id=None)
        with patch("analysi.auth.dependencies.require_current_user", return_value=user):
            result = await check_tenant_access(tenant="any-tenant", current_user=user)
        assert result == "any-tenant"

    @pytest.mark.asyncio
    async def test_matching_tenant_passes(self):
        """User whose JWT tenant_id matches the URL tenant_id is allowed."""
        user = _make_user(["analyst"], tenant_id="acme")
        result = await check_tenant_access(tenant="acme", current_user=user)
        assert result == "acme"

    @pytest.mark.asyncio
    async def test_wrong_tenant_raises_403(self):
        """User accessing a different tenant's URL gets 403."""
        user = _make_user(["owner"], tenant_id="acme")
        with pytest.raises(HTTPException) as exc_info:
            await check_tenant_access(tenant="other-tenant", current_user=user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_null_tenant_non_admin_raises_403(self):
        """Non-platform-admin user with tenant_id=None gets 403 (misconfigured JWT)."""
        user = _make_user(["analyst"], tenant_id=None)
        with pytest.raises(HTTPException) as exc_info:
            await check_tenant_access(tenant="acme", current_user=user)
        assert exc_info.value.status_code == 403


class TestRequirePermission:
    """Tests for require_permission dependency factory."""

    def _get_dep(self, resource: str, action: str):
        """Return the inner async function produced by require_permission."""
        from analysi.auth.dependencies import require_permission

        return require_permission(resource, action)

    @pytest.mark.asyncio
    async def test_platform_admin_bypasses_permission_check(self):
        """platform_admin passes regardless of resource/action."""
        user = _make_user(["platform_admin"], tenant_id=None)
        dep = self._get_dep("tasks", "delete")
        result = await dep(tenant="acme", current_user=user)
        assert result is user

    @pytest.mark.asyncio
    async def test_sufficient_role_passes(self):
        """analyst has tasks.create permission — should pass."""
        user = _make_user(["analyst"], tenant_id="acme")
        dep = self._get_dep("tasks", "create")
        result = await dep(tenant="acme", current_user=user)
        assert result is user

    @pytest.mark.asyncio
    async def test_insufficient_role_raises_403(self):
        """viewer does not have tasks.create — should get 403."""
        user = _make_user(["viewer"], tenant_id="acme")
        dep = self._get_dep("tasks", "create")
        with pytest.raises(HTTPException) as exc_info:
            await dep(tenant="acme", current_user=user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_wrong_tenant_raises_403(self):
        """Permission check fails when tenant_id doesn't match JWT, even if role is sufficient."""
        user = _make_user(["owner"], tenant_id="acme")
        dep = self._get_dep("tasks", "read")
        with pytest.raises(HTTPException) as exc_info:
            await dep(tenant="other", current_user=user)
        assert exc_info.value.status_code == 403


class TestRequirePlatformAdmin:
    """Tests for require_platform_admin dependency."""

    @pytest.mark.asyncio
    async def test_passes_for_platform_admin(self):
        """platform_admin user gets through."""
        user = _make_user(["platform_admin"], tenant_id=None)
        result = await require_platform_admin(current_user=user)
        assert result is user

    @pytest.mark.asyncio
    async def test_raises_403_for_regular_user(self):
        """Owner (not platform_admin) is denied."""
        user = _make_user(["owner"], tenant_id="acme")
        with pytest.raises(HTTPException) as exc_info:
            await require_platform_admin(current_user=user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_raises_403_for_analyst(self):
        user = _make_user(["analyst"], tenant_id="acme")
        with pytest.raises(HTTPException) as exc_info:
            await require_platform_admin(current_user=user)
        assert exc_info.value.status_code == 403
