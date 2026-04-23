"""Integration test to verify cy_name is properly stored in database."""

import uuid

import pytest
from sqlalchemy import select

from analysi.models.component import Component
from analysi.repositories.task import TaskRepository
from analysi.schemas.task import TaskCreate
from analysi.services.task import TaskService


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskCyNameDatabaseIntegration:
    """Test cy_name handling in database through API and directly."""

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
        """Create TaskService with session."""
        return TaskService(integration_test_session)

    @pytest.mark.asyncio
    async def test_post_request_creates_correct_cy_name_in_db(
        self, service, integration_test_session, tenant_id
    ):
        """Test that POST request creates the correct cy_name in database."""
        # Test 1: Create task with explicit cy_name
        task_data1 = TaskCreate(
            name="My Task With Spaces",
            cy_name="explicit_cy_name",
            script="return 'test'",
            description="Task with explicit cy_name",
        )

        created_task1 = await service.create_task(tenant_id, task_data1)

        # Query database directly to verify cy_name
        stmt = select(Component).where(Component.id == created_task1.component_id)
        result = await integration_test_session.execute(stmt)
        component1 = result.scalar_one()

        assert component1.cy_name == "explicit_cy_name"
        assert component1.name == "My Task With Spaces"
        print(f"✅ Explicit cy_name stored: {component1.cy_name}")

        # Test 2: Create task without cy_name (auto-generated)
        task_data2 = TaskCreate(
            name="Another Complex Task Name",
            script="return 'auto-generated'",
            description="Task with auto-generated cy_name",
        )

        created_task2 = await service.create_task(tenant_id, task_data2)

        # Query database directly
        stmt = select(Component).where(Component.id == created_task2.component_id)
        result = await integration_test_session.execute(stmt)
        component2 = result.scalar_one()

        assert component2.cy_name == "another_complex_task_name"
        assert component2.name == "Another Complex Task Name"
        print(f"✅ Auto-generated cy_name stored: {component2.cy_name}")

    @pytest.mark.asyncio
    async def test_cy_name_uniqueness_in_database(
        self, service, integration_test_session, tenant_id
    ):
        """Test that cy_name uniqueness is enforced at database level."""
        # Create first task
        task_data1 = TaskCreate(
            name="First Task", cy_name="unique_name", script="return 1"
        )
        await service.create_task(tenant_id, task_data1)

        # Try to create second task with same cy_name
        task_data2 = TaskCreate(
            name="Second Task",
            cy_name="unique_name",  # Same cy_name
            script="return 2",
        )

        with pytest.raises(ValueError) as exc_info:
            await service.create_task(tenant_id, task_data2)

        assert "already exists" in str(exc_info.value)
        print("✅ Duplicate cy_name properly rejected")

        # Verify only one component with this cy_name exists
        stmt = select(Component).where(
            Component.tenant_id == tenant_id, Component.cy_name == "unique_name"
        )
        result = await integration_test_session.execute(stmt)
        components = result.scalars().all()
        assert len(components) == 1
        assert components[0].name == "First Task"

    @pytest.mark.asyncio
    async def test_cy_name_auto_generation_handles_conflicts(
        self, service, integration_test_session, tenant_id
    ):
        """Test that auto-generated cy_names handle conflicts properly."""
        # Create first task
        task_data1 = TaskCreate(name="Test Task", script="return 1")
        created_task1 = await service.create_task(tenant_id, task_data1)

        # Get component from DB
        stmt = select(Component).where(Component.id == created_task1.component_id)
        result = await integration_test_session.execute(stmt)
        component1 = result.scalar_one()
        assert component1.cy_name == "test_task"

        # Create second task with same name (should get numbered suffix)
        task_data2 = TaskCreate(
            name="Test Task",  # Same name
            script="return 2",
        )
        created_task2 = await service.create_task(tenant_id, task_data2)

        # Get component from DB
        stmt = select(Component).where(Component.id == created_task2.component_id)
        result = await integration_test_session.execute(stmt)
        component2 = result.scalar_one()

        # Should have a numbered suffix
        assert component2.cy_name.startswith("test_task")
        assert component2.cy_name != "test_task"  # Different from first
        assert component2.cy_name in ["test_task_2", "test_task_1"]  # Common patterns
        print(f"✅ Conflict handled: {component1.cy_name} → {component2.cy_name}")

    @pytest.mark.asyncio
    async def test_cy_name_update_in_database(
        self, service, integration_test_session, tenant_id
    ):
        """Test that cy_name can be updated in the database."""
        from analysi.schemas.task import TaskUpdate

        # Create task
        task_data = TaskCreate(
            name="Original Name", cy_name="original_cy_name", script="return 'test'"
        )
        created_task = await service.create_task(tenant_id, task_data)

        # Update cy_name
        update_data = TaskUpdate(cy_name="updated_cy_name")
        await service.update_task(created_task.component_id, tenant_id, update_data)

        # Verify in database
        stmt = select(Component).where(Component.id == created_task.component_id)
        result = await integration_test_session.execute(stmt)
        component = result.scalar_one()

        assert component.cy_name == "updated_cy_name"
        assert component.name == "Original Name"  # Name unchanged
        print(f"✅ cy_name updated: original_cy_name → {component.cy_name}")

    @pytest.mark.asyncio
    async def test_task_run_finds_task_by_cy_name(
        self, service, repository, integration_test_session, tenant_id
    ):
        """Test that task_run can find tasks by cy_name in database."""
        # Create task with specific cy_name
        task_data = TaskCreate(
            name="Runnable Task",
            cy_name="my_runnable_task",
            script="return {'result': 'success'}",
        )
        created_task = await service.create_task(tenant_id, task_data)

        # Use repository method to find by cy_name
        found_task = await repository.get_task_by_cy_name(
            tenant_id=tenant_id, cy_name="my_runnable_task", app="default"
        )

        assert found_task is not None
        assert found_task.component.cy_name == "my_runnable_task"
        assert found_task.component.name == "Runnable Task"
        assert found_task.id == created_task.id
        print(f"✅ Task found by cy_name: {found_task.component.cy_name}")

        # Verify it's the same task
        assert found_task.script == "return {'result': 'success'}"

    @pytest.mark.asyncio
    async def test_cy_name_special_characters_handling(
        self, service, integration_test_session, tenant_id
    ):
        """Test that special characters in names are properly handled for cy_name."""
        test_cases = [
            ("Task-With-Dashes", "task_with_dashes"),
            ("Task.With.Dots", "task_with_dots"),
            ("Task With  Multiple   Spaces", "task_with_multiple_spaces"),
            ("UPPERCASE TASK", "uppercase_task"),
            ("123 Task Starting With Number", "n123_task_starting_with_number"),
            ("Task_Already_With_Underscores", "task_already_with_underscores"),
        ]

        for name, expected_cy_name in test_cases:
            task_data = TaskCreate(name=name, script=f"return '{name}'")
            created_task = await service.create_task(tenant_id, task_data)

            # Query database
            stmt = select(Component).where(Component.id == created_task.component_id)
            result = await integration_test_session.execute(stmt)
            component = result.scalar_one()

            assert component.cy_name == expected_cy_name
            print(f"✅ '{name}' → '{component.cy_name}'")
