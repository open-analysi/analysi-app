"""Unit tests for RBAC permission map."""

from analysi.auth.permissions import has_permission


class TestViewerPermissions:
    def test_viewer_has_read_on_core_resources(self):
        for resource in [
            "tasks",
            "workflows",
            "alerts",
            "integrations",
            "knowledge_units",
            "skills",
            "audit_trail",
        ]:
            assert has_permission(["viewer"], resource, "read"), (
                f"viewer should read {resource}"
            )

    def test_viewer_cannot_create_tasks(self):
        assert not has_permission(["viewer"], "tasks", "create")

    def test_viewer_cannot_delete_tasks(self):
        assert not has_permission(["viewer"], "tasks", "delete")

    def test_viewer_cannot_manage_members(self):
        assert not has_permission(["viewer"], "members", "read")

    def test_viewer_cannot_create_api_keys(self):
        assert not has_permission(["viewer"], "api_keys", "create")

    def test_viewer_can_read_api_keys(self):
        assert has_permission(["viewer"], "api_keys", "read")

    def test_viewer_cannot_create_skills(self):
        assert not has_permission(["viewer"], "skills", "create")

    def test_viewer_cannot_update_skills(self):
        assert not has_permission(["viewer"], "skills", "update")

    def test_viewer_cannot_delete_skills(self):
        assert not has_permission(["viewer"], "skills", "delete")


class TestAnalystPermissions:
    def test_analyst_can_create_and_update_tasks(self):
        assert has_permission(["analyst"], "tasks", "create")
        assert has_permission(["analyst"], "tasks", "update")

    def test_analyst_cannot_delete_tasks(self):
        assert not has_permission(["analyst"], "tasks", "delete")

    def test_analyst_can_execute_workflows(self):
        assert has_permission(["analyst"], "workflows", "execute")

    def test_analyst_cannot_delete_workflows(self):
        assert not has_permission(["analyst"], "workflows", "delete")

    def test_analyst_can_update_alerts(self):
        assert has_permission(["analyst"], "alerts", "update")

    def test_analyst_can_execute_integrations(self):
        """Analysts need integrations.execute for app:: tools in tasks/workflows."""
        assert has_permission(["analyst"], "integrations", "execute")

    def test_analyst_cannot_manage_integrations(self):
        assert not has_permission(["analyst"], "integrations", "create")
        assert not has_permission(["analyst"], "integrations", "delete")

    def test_analyst_cannot_manage_members(self):
        assert not has_permission(["analyst"], "members", "read")

    def test_analyst_can_read_skills(self):
        """Analyst inherits viewer's skills.read."""
        assert has_permission(["analyst"], "skills", "read")

    def test_analyst_cannot_create_or_update_or_delete_skills(self):
        """Skills are admin-only for mutations."""
        assert not has_permission(["analyst"], "skills", "create")
        assert not has_permission(["analyst"], "skills", "update")
        assert not has_permission(["analyst"], "skills", "delete")


class TestAdminPermissions:
    def test_admin_can_delete_tasks(self):
        assert has_permission(["admin"], "tasks", "delete")

    def test_admin_can_manage_integrations(self):
        assert has_permission(["admin"], "integrations", "create")
        assert has_permission(["admin"], "integrations", "update")
        assert has_permission(["admin"], "integrations", "delete")

    def test_admin_can_read_members(self):
        assert has_permission(["admin"], "members", "read")

    def test_admin_can_invite_members(self):
        assert has_permission(["admin"], "members", "invite")

    def test_admin_cannot_change_member_roles(self):
        assert not has_permission(["admin"], "members", "update")

    def test_admin_cannot_delete_members(self):
        assert not has_permission(["admin"], "members", "delete")

    def test_admin_has_full_skill_permissions(self):
        """Admin can CRUD skills."""
        for action in ["read", "create", "update", "delete"]:
            assert has_permission(["admin"], "skills", action), (
                f"admin should have skills.{action}"
            )


class TestOwnerPermissions:
    def test_owner_can_manage_members(self):
        assert has_permission(["owner"], "members", "read")
        assert has_permission(["owner"], "members", "invite")
        assert has_permission(["owner"], "members", "update")
        assert has_permission(["owner"], "members", "delete")

    def test_owner_can_delete_workflows(self):
        assert has_permission(["owner"], "workflows", "delete")

    def test_owner_has_all_task_permissions(self):
        for action in ["read", "create", "update", "delete", "execute"]:
            assert has_permission(["owner"], "tasks", action), (
                f"owner should have tasks.{action}"
            )

    def test_owner_inherits_skill_permissions(self):
        """Owner inherits all admin skill permissions."""
        for action in ["read", "create", "update", "delete"]:
            assert has_permission(["owner"], "skills", action), (
                f"owner should have skills.{action}"
            )


class TestSystemPermissions:
    def test_system_can_read_write_alerts(self):
        assert has_permission(["system"], "alerts", "read")
        assert has_permission(["system"], "alerts", "create")
        assert has_permission(["system"], "alerts", "update")

    def test_system_can_read_and_execute_tasks_and_workflows(self):
        assert has_permission(["system"], "tasks", "read")
        assert has_permission(["system"], "tasks", "execute")
        assert has_permission(["system"], "workflows", "read")
        assert has_permission(["system"], "workflows", "execute")

    def test_system_can_read_integrations(self):
        assert has_permission(["system"], "integrations", "read")
        assert has_permission(["system"], "integrations", "execute")

    def test_system_cannot_delete_most_resources(self):
        for resource in ["tasks", "alerts", "integrations"]:
            assert not has_permission(["system"], resource, "delete"), (
                f"system should NOT delete {resource}"
            )

    def test_system_can_delete_workflows(self):
        """Workers need workflows.delete for MCP cleanup during generation."""
        assert has_permission(["system"], "workflows", "delete")

    def test_system_cannot_manage_members(self):
        assert not has_permission(["system"], "members", "read")
        assert not has_permission(["system"], "members", "invite")

    def test_system_cannot_create_api_keys(self):
        assert not has_permission(["system"], "api_keys", "create")

    def test_system_can_read_create_update_skills(self):
        """Workers need skills access for Hydra/Kea pipelines."""
        assert has_permission(["system"], "skills", "read")
        assert has_permission(["system"], "skills", "create")
        assert has_permission(["system"], "skills", "update")

    def test_system_cannot_delete_skills(self):
        assert not has_permission(["system"], "skills", "delete")


class TestMultiRoleAndEdgeCases:
    def test_multi_role_union_combines_permissions(self):
        # viewer alone cannot create; analyst alone can; union can
        assert not has_permission(["viewer"], "tasks", "create")
        assert has_permission(["viewer", "analyst"], "tasks", "create")

    def test_unknown_role_has_no_permissions(self):
        assert not has_permission(["ghost"], "tasks", "read")

    def test_empty_roles_has_no_permissions(self):
        assert not has_permission([], "tasks", "read")

    def test_unknown_permission_returns_false(self):
        assert not has_permission(["owner"], "billing", "charge")

    def test_unknown_action_returns_false(self):
        assert not has_permission(["owner"], "tasks", "teleport")
