"""Unit tests for chat RBAC enforcement (Project Rhodes).

Tests that:
1. Action tools (run_workflow, run_task, analyze_alert, create_alert) enforce
   role-based permissions — viewers cannot execute, only analysts+.
2. search_audit_trail gate includes owner role (inherits from admin).
3. Permission map includes chat delete/update permissions.
"""

from analysi.auth.permissions import has_permission


class TestChatActionToolRoleGating:
    """Chat action tools must enforce RBAC — viewer cannot execute workflows/tasks.

    The chat service passes user_roles via ChatDeps. Action tools must check
    the user has the appropriate permission before executing mutations.
    """

    def test_viewer_cannot_execute_workflows(self):
        """Viewer role should NOT have workflows.execute permission."""
        assert not has_permission(["viewer"], "workflows", "execute")

    def test_viewer_cannot_execute_tasks(self):
        """Viewer role should NOT have tasks.execute permission."""
        assert not has_permission(["viewer"], "tasks", "execute")

    def test_viewer_cannot_create_alerts(self):
        """Viewer role should NOT have alerts.create permission."""
        assert not has_permission(["viewer"], "alerts", "create")

    def test_analyst_can_execute_workflows(self):
        """Analyst role should have workflows.execute permission."""
        assert has_permission(["analyst"], "workflows", "execute")

    def test_analyst_can_execute_tasks(self):
        """Analyst role should have tasks.execute permission."""
        assert has_permission(["analyst"], "tasks", "execute")

    def test_analyst_can_create_alerts(self):
        """Analyst role should have alerts.create permission."""
        assert has_permission(["analyst"], "alerts", "create")


class TestChatActionToolsEnforcePermissions:
    """Action tools in _build_agent must check user_roles before executing.

    These tests import the role-check helper used by action tools and verify
    it correctly gates access.
    """

    def test_check_chat_action_permission_denies_viewer_workflow_execute(self):
        """check_chat_action_permission should deny viewer for workflows.execute."""
        from analysi.services.chat_service import check_chat_action_permission

        result = check_chat_action_permission(
            user_roles=["viewer"],
            resource="workflows",
            action="execute",
        )
        assert result is not None  # Returns an error message
        assert "permission" in result.lower() or "role" in result.lower()

    def test_check_chat_action_permission_allows_analyst_workflow_execute(self):
        """check_chat_action_permission should allow analyst for workflows.execute."""
        from analysi.services.chat_service import check_chat_action_permission

        result = check_chat_action_permission(
            user_roles=["analyst"],
            resource="workflows",
            action="execute",
        )
        assert result is None  # No error — allowed

    def test_check_chat_action_permission_denies_viewer_task_execute(self):
        """check_chat_action_permission should deny viewer for tasks.execute."""
        from analysi.services.chat_service import check_chat_action_permission

        result = check_chat_action_permission(
            user_roles=["viewer"],
            resource="tasks",
            action="execute",
        )
        assert result is not None

    def test_check_chat_action_permission_denies_viewer_alert_create(self):
        """check_chat_action_permission should deny viewer for alerts.create."""
        from analysi.services.chat_service import check_chat_action_permission

        result = check_chat_action_permission(
            user_roles=["viewer"],
            resource="alerts",
            action="create",
        )
        assert result is not None

    def test_check_chat_action_permission_allows_admin(self):
        """Admin should be allowed for all action tool permissions."""
        from analysi.services.chat_service import check_chat_action_permission

        for resource, action in [
            ("workflows", "execute"),
            ("tasks", "execute"),
            ("alerts", "create"),
            ("alerts", "update"),
        ]:
            result = check_chat_action_permission(
                user_roles=["admin"],
                resource=resource,
                action=action,
            )
            assert result is None, f"Admin should have {resource}.{action}"


class TestSearchAuditTrailRoleGate:
    """search_audit_trail must allow owner role (inherits from admin)."""

    def test_owner_has_audit_trail_read(self):
        """Owner role should have audit_trail.read permission."""
        assert has_permission(["owner"], "audit_trail", "read")

    def test_admin_has_audit_trail_read(self):
        """Admin role should have audit_trail.read permission."""
        assert has_permission(["admin"], "audit_trail", "read")

    def test_viewer_has_audit_trail_read(self):
        """Viewer role has audit_trail.read (but search_audit_trail has extra gate)."""
        # The permission map gives viewer audit_trail.read, but the
        # search_audit_trail tool in chat_service adds an additional
        # admin-only gate. This is intentional — the REST API audit
        # endpoint uses require_permission, the chat tool adds a
        # stricter inline check.
        assert has_permission(["viewer"], "audit_trail", "read")


class TestChatDeletePermission:
    """Chat delete and update should use proper permission actions."""

    def test_chat_delete_permission_exists(self):
        """chat.delete permission should exist for admin+ roles."""
        assert has_permission(["admin"], "chat", "delete")
        assert has_permission(["owner"], "chat", "delete")

    def test_viewer_cannot_delete_chat(self):
        """Viewer should not have chat.delete permission."""
        assert not has_permission(["viewer"], "chat", "delete")

    def test_analyst_cannot_delete_chat(self):
        """Analyst should not have chat.delete — only admin+ can delete."""
        assert not has_permission(["analyst"], "chat", "delete")

    def test_viewer_can_create_chat(self):
        """All users (viewer+) can create chat conversations."""
        assert has_permission(["viewer"], "chat", "create")

    def test_chat_update_permission_exists(self):
        """chat.update permission should exist for all users who can create."""
        # Users who can create should also be able to update their own titles
        assert has_permission(["viewer"], "chat", "update")
