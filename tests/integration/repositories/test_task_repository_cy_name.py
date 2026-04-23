"""Integration tests for TaskRepository cy_name functionality."""

import uuid

import pytest

from analysi.models.auth import SYSTEM_USER_ID
from analysi.repositories.task import TaskRepository
from analysi.services.task import TaskService


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskRepositoryCyName:
    """Test TaskRepository cy_name operations with real database."""

    @pytest.fixture
    def tenant_id(self):
        """Create unique tenant ID for each test."""
        return f"test-tenant-{uuid.uuid4().hex[:8]}"

    @pytest.fixture
    async def repository(self, integration_test_session):
        """Create TaskRepository with test session."""
        return TaskRepository(integration_test_session)

    @pytest.fixture
    async def service(self, integration_test_session):
        """Create TaskService with test session."""
        return TaskService(integration_test_session)

    @pytest.mark.asyncio
    async def test_create_task_with_cy_name(self, repository, tenant_id):
        """Test creating task with explicit cy_name."""
        task_data = {
            "tenant_id": tenant_id,
            "name": "My Test Task",
            "cy_name": "my_custom_cy_name",
            "description": "Test task with cy_name",
            "script": "TASK test: RETURN 'hello'",
            "function": "reasoning",
            "scope": "processing",
            "created_by": str(SYSTEM_USER_ID),
        }

        task = await repository.create(task_data)

        assert task is not None
        assert task.component.cy_name == "my_custom_cy_name"
        assert task.component.name == "My Test Task"

    @pytest.mark.asyncio
    async def test_create_task_auto_generate_cy_name(self, repository, tenant_id):
        """Test creating task without cy_name auto-generates one."""
        task_data = {
            "tenant_id": tenant_id,
            "name": "Incident Response Playbook",
            "description": "Test task without cy_name",
            "script": "TASK test: RETURN 'hello'",
            "function": "reasoning",
            "scope": "processing",
            "created_by": str(SYSTEM_USER_ID),
        }

        task = await repository.create(task_data)

        assert task is not None
        assert task.component.cy_name == "incident_response_playbook"
        assert task.component.name == "Incident Response Playbook"

    @pytest.mark.asyncio
    async def test_cy_name_unique_constraint(self, repository, tenant_id):
        """Test unique constraint on (tenant_id, app, cy_name)."""
        # Create first task with cy_name
        task_data1 = {
            "tenant_id": tenant_id,
            "name": "Task One",
            "cy_name": "duplicate_name",
            "app": "default",
            "script": "TASK one: RETURN '1'",
            "created_by": str(SYSTEM_USER_ID),
        }
        task1 = await repository.create(task_data1)
        assert task1.component.cy_name == "duplicate_name"

        # Try to create second task with same cy_name
        task_data2 = {
            "tenant_id": tenant_id,
            "name": "Task Two",
            "cy_name": "duplicate_name",
            "app": "default",
            "script": "TASK two: RETURN '2'",
            "created_by": str(SYSTEM_USER_ID),
        }

        # This should raise ValueError due to duplicate cy_name
        with pytest.raises(ValueError) as exc_info:
            await repository.create(task_data2)
        assert "already exists" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_cy_name_unique_per_tenant(self, repository):
        """Test that same cy_name can exist for different tenants."""
        tenant1 = f"tenant-{uuid.uuid4().hex[:8]}"
        tenant2 = f"tenant-{uuid.uuid4().hex[:8]}"

        # Create task for tenant1
        task_data1 = {
            "tenant_id": tenant1,
            "name": "Shared Task",
            "cy_name": "shared_task",
            "script": "TASK one: RETURN '1'",
            "created_by": str(SYSTEM_USER_ID),
        }
        task1 = await repository.create(task_data1)

        # Create task with same cy_name for tenant2 - should succeed
        task_data2 = {
            "tenant_id": tenant2,
            "name": "Shared Task",
            "cy_name": "shared_task",
            "script": "TASK two: RETURN '2'",
            "created_by": str(SYSTEM_USER_ID),
        }
        task2 = await repository.create(task_data2)

        assert task1.component.cy_name == "shared_task"
        assert task2.component.cy_name == "shared_task"
        assert task1.component.tenant_id != task2.component.tenant_id

    @pytest.mark.asyncio
    async def test_list_tasks_by_cy_name(self, repository, tenant_id):
        """Test filtering tasks by cy_name."""
        # Create multiple tasks
        tasks_data = [
            {
                "tenant_id": tenant_id,
                "name": "Task Alpha",
                "cy_name": "task_alpha",
                "script": "TASK alpha: RETURN 'a'",
                "created_by": str(SYSTEM_USER_ID),
            },
            {
                "tenant_id": tenant_id,
                "name": "Task Beta",
                "cy_name": "task_beta",
                "script": "TASK beta: RETURN 'b'",
                "created_by": str(SYSTEM_USER_ID),
            },
            {
                "tenant_id": tenant_id,
                "name": "Task Gamma",
                "cy_name": "task_gamma",
                "script": "TASK gamma: RETURN 'g'",
                "created_by": str(SYSTEM_USER_ID),
            },
        ]

        for task_data in tasks_data:
            await repository.create(task_data)

        # Filter by cy_name
        tasks, total = await repository.list_with_filters(
            tenant_id=tenant_id, cy_name="task_beta"
        )

        assert total == 1
        assert len(tasks) == 1
        assert tasks[0].component.cy_name == "task_beta"
        assert tasks[0].component.name == "Task Beta"

    @pytest.mark.asyncio
    async def test_get_task_by_cy_name(self, repository, tenant_id):
        """Test retrieving task by cy_name."""
        # Create task
        task_data = {
            "tenant_id": tenant_id,
            "name": "Retrievable Task",
            "cy_name": "retrievable_task",
            "script": "TASK retrieve: RETURN 'found'",
            "created_by": str(SYSTEM_USER_ID),
        }
        created_task = await repository.create(task_data)

        # Retrieve by cy_name
        retrieved_task = await repository.get_task_by_cy_name(
            tenant_id=tenant_id, cy_name="retrievable_task", app="default"
        )

        assert retrieved_task is not None
        assert retrieved_task.component.cy_name == "retrievable_task"
        assert retrieved_task.component.name == "Retrievable Task"
        assert retrieved_task.component.id == created_task.component.id

    @pytest.mark.asyncio
    async def test_cy_name_with_reserved_word(self, repository, tenant_id):
        """Test that reserved words in names are handled correctly."""
        task_data = {
            "tenant_id": tenant_id,
            "name": "table",  # Reserved word
            "description": "Task with reserved word name",
            "script": "TASK table: RETURN 'data'",
            "created_by": str(SYSTEM_USER_ID),
        }

        task = await repository.create(task_data)

        # Should have been transformed to avoid reserved word
        assert task.component.cy_name == "task_table"
        assert task.component.name == "table"
