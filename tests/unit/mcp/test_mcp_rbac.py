"""Unit tests for MCP RBAC enforcement on all MCP tools.

Verifies that check_mcp_permission() enforces correct permissions
for mutations, reads, and execution operations.
"""

import pytest

from analysi.auth.messages import INSUFFICIENT_PERMISSIONS
from analysi.auth.models import CurrentUser
from analysi.mcp.context import (
    check_mcp_permission,
    mcp_current_user_context,
)


def _set_mcp_user(
    roles: list[str],
    actor_type: str = "user",
    tenant_id: str = "test-tenant",
) -> CurrentUser:
    user = CurrentUser(
        user_id="kc-test",
        email="user@test.com",
        tenant_id=tenant_id,
        roles=roles,
        actor_type=actor_type,
    )
    mcp_current_user_context.set(user)
    return user


class TestCheckMcpPermission:
    def test_no_user_raises_permission_error(self):
        mcp_current_user_context.set(None)
        with pytest.raises(PermissionError, match="No authenticated user"):
            check_mcp_permission("tasks", "create")

    def test_platform_admin_bypasses_all(self):
        _set_mcp_user(roles=["platform_admin"])
        check_mcp_permission("tasks", "create")  # should not raise
        check_mcp_permission("workflows", "delete")

    def test_viewer_denied_task_create(self):
        _set_mcp_user(roles=["viewer"])
        with pytest.raises(PermissionError, match=INSUFFICIENT_PERMISSIONS):
            check_mcp_permission("tasks", "create")

    def test_viewer_denied_workflow_create(self):
        _set_mcp_user(roles=["viewer"])
        with pytest.raises(PermissionError, match=INSUFFICIENT_PERMISSIONS):
            check_mcp_permission("workflows", "create")

    def test_analyst_allowed_task_create(self):
        _set_mcp_user(roles=["analyst"])
        check_mcp_permission("tasks", "create")  # should not raise

    def test_analyst_denied_task_delete(self):
        _set_mcp_user(roles=["analyst"])
        with pytest.raises(PermissionError, match=INSUFFICIENT_PERMISSIONS):
            check_mcp_permission("tasks", "delete")

    def test_admin_allowed_task_delete(self):
        _set_mcp_user(roles=["admin"])
        check_mcp_permission("tasks", "delete")  # should not raise

    def test_system_role_allowed_task_create(self):
        _set_mcp_user(roles=["system"])
        check_mcp_permission("tasks", "create")  # system has tasks.create

    def test_empty_roles_denied(self):
        _set_mcp_user(roles=[])
        with pytest.raises(PermissionError, match=INSUFFICIENT_PERMISSIONS):
            check_mcp_permission("tasks", "read")

    # --- Read permission tests ---

    def test_viewer_allowed_task_read(self):
        _set_mcp_user(roles=["viewer"])
        check_mcp_permission("tasks", "read")  # should not raise

    def test_viewer_allowed_workflow_read(self):
        _set_mcp_user(roles=["viewer"])
        check_mcp_permission("workflows", "read")  # should not raise

    def test_viewer_allowed_integration_read(self):
        _set_mcp_user(roles=["viewer"])
        check_mcp_permission("integrations", "read")  # should not raise

    def test_empty_roles_denied_workflow_read(self):
        _set_mcp_user(roles=[])
        with pytest.raises(PermissionError, match=INSUFFICIENT_PERMISSIONS):
            check_mcp_permission("workflows", "read")

    def test_empty_roles_denied_integration_read(self):
        _set_mcp_user(roles=[])
        with pytest.raises(PermissionError, match=INSUFFICIENT_PERMISSIONS):
            check_mcp_permission("integrations", "read")

    # --- Execute permission tests ---

    def test_viewer_denied_task_execute(self):
        _set_mcp_user(roles=["viewer"])
        with pytest.raises(PermissionError, match=INSUFFICIENT_PERMISSIONS):
            check_mcp_permission("tasks", "execute")

    def test_analyst_allowed_task_execute(self):
        _set_mcp_user(roles=["analyst"])
        check_mcp_permission("tasks", "execute")  # should not raise

    def test_viewer_denied_integration_execute(self):
        _set_mcp_user(roles=["viewer"])
        with pytest.raises(PermissionError, match=INSUFFICIENT_PERMISSIONS):
            check_mcp_permission("integrations", "execute")
