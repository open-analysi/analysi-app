"""Integration tests for tenant isolation in MCP operations."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.mcp.context import set_tenant
from analysi.mcp.tools import task_tools
from analysi.models.auth import SYSTEM_USER_ID
from analysi.repositories.task import TaskRepository


@pytest.mark.asyncio
@pytest.mark.integration
class TestTenantIsolation:
    """Test multi-tenant security and isolation."""

    @pytest.mark.asyncio
    async def test_tenant_isolation_tasks(self, integration_test_session: AsyncSession):
        """Verify strict tenant isolation for task operations."""
        tenant_a = f"tenant-a-{uuid4().hex[:8]}"
        tenant_b = f"tenant-b-{uuid4().hex[:8]}"
        task_repo = TaskRepository(integration_test_session)

        # Create tasks for tenant A
        task_a1 = await task_repo.create(
            {
                "tenant_id": tenant_a,
                "name": "Task A1",
                "script": "return 'a1'",
                "created_by": str(SYSTEM_USER_ID),
            }
        )
        task_a2 = await task_repo.create(
            {
                "tenant_id": tenant_a,
                "name": "Task A2",
                "script": "return 'a2'",
                "created_by": str(SYSTEM_USER_ID),
            }
        )

        # Create tasks for tenant B
        task_b1 = await task_repo.create(
            {
                "tenant_id": tenant_b,
                "name": "Task B1",
                "script": "return 'b1'",
                "created_by": str(SYSTEM_USER_ID),
            }
        )
        await integration_test_session.commit()

        # List tasks for tenant A
        set_tenant(tenant_a)
        result_a = await task_tools.list_tasks()

        # Should only see tenant A tasks
        task_ids_a = [t["id"] for t in result_a["tasks"]]
        assert str(task_a1.component_id) in task_ids_a
        assert str(task_a2.component_id) in task_ids_a
        assert str(task_b1.component_id) not in task_ids_a

        # List tasks for tenant B
        set_tenant(tenant_b)
        result_b = await task_tools.list_tasks()

        # Should only see tenant B tasks
        task_ids_b = [t["id"] for t in result_b["tasks"]]
        assert str(task_b1.component_id) in task_ids_b
        assert str(task_a1.component_id) not in task_ids_b
        assert str(task_a2.component_id) not in task_ids_b

    @pytest.mark.asyncio
    async def test_tenant_validation_invalid(self):
        """Verify invalid tenant returns 403."""
        # Invalid tenant patterns
        invalid_tenants = [
            "../path-traversal",
            "<script>xss</script>",
            "tenant;drop table",
            "tenant|ls",
        ]

        from analysi.middleware.tenant import validate_tenant_permissions

        for invalid_tenant in invalid_tenants:
            # Should fail validation
            is_valid = validate_tenant_permissions(invalid_tenant)
            assert is_valid is False

    @pytest.mark.asyncio
    async def test_tenant_validation_malicious(self):
        """Verify malicious tenant IDs are blocked."""
        from analysi.middleware.tenant import extract_tenant_from_path

        # Malicious paths that should be rejected
        malicious_paths = [
            "/v1/../admin/tasks",
            "/v1/%2e%2e%2fadmin/tasks",
            "/v1/<script>/tasks",
            "/v1/tenant;rm -rf/tasks",
        ]

        for path in malicious_paths:
            tenant = extract_tenant_from_path(path)
            # Should either return None or fail validation
            if tenant:
                from analysi.middleware.tenant import validate_tenant_permissions

                is_valid = validate_tenant_permissions(tenant)
                assert is_valid is False
