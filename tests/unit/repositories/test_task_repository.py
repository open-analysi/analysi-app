"""Unit tests for TaskRepository."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.models.task import Task
from analysi.repositories.task import TaskRepository


class TestTaskRepository:
    """Test TaskRepository operations."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.fixture
    def repository(self, mock_session):
        """Create a TaskRepository instance with mock session."""
        return TaskRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_task_success(self, repository, mock_session):
        """Test successful task creation."""
        task_data = {
            "tenant_id": "default",
            "name": "Test Task",
            "description": "Test description",
            "script": "TASK test: RETURN 'hello'",
            "function": "reasoning",
            "scope": "processing",
        }

        # Mock the session operations
        mock_component = MagicMock()
        mock_component.id = "test-component-id"
        mock_task = MagicMock(spec=Task)
        mock_task.id = "test-task-id"

        # Configure mocks
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        # Mock ComponentRepository for cy_name generation
        mock_comp_repo = MagicMock()
        mock_comp_repo.generate_cy_name.return_value = "test_task"
        mock_comp_repo.ensure_unique_cy_name = AsyncMock(return_value="test_task")

        # Mock Task constructor to return our mock
        with (
            patch("analysi.repositories.task.Task", return_value=mock_task),
            patch("analysi.repositories.task.Component", return_value=mock_component),
            patch(
                "analysi.repositories.component.ComponentRepository",
                return_value=mock_comp_repo,
            ),
        ):
            result = await repository.create(task_data)

            # Verify calls
            mock_session.add.assert_called()
            mock_session.flush.assert_called_once()
            mock_session.commit.assert_called_once()
            assert (
                mock_session.refresh.call_count == 3
            )  # Called for task, component, and task+component relationship
            assert result == mock_task

    @pytest.mark.asyncio
    async def test_get_task_by_id_success(self, repository, mock_session):
        """Test retrieving task by ID and tenant."""
        task_id = uuid.uuid4()
        tenant_id = "default"

        # Mock task
        mock_task = MagicMock(spec=Task)

        # Mock query result - new implementation uses scalar_one_or_none
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_id(task_id, tenant_id)

        # Verify the result
        assert result == mock_task
        # Verify refresh was called to load component relationship
        mock_session.refresh.assert_called_with(mock_task, ["component"])

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, repository, mock_session):
        """Test retrieving non-existent task returns None."""
        task_id = uuid.uuid4()
        tenant_id = "default"

        # Mock query result to return None - new implementation uses scalar_one_or_none
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_id(task_id, tenant_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_task_wrong_tenant(self, repository, mock_session):
        """Test retrieving task with wrong tenant returns None."""
        task_id = uuid.uuid4()
        wrong_tenant = "wrong-tenant"

        # Mock query result to return None for wrong tenant - new implementation uses scalar_one_or_none
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repository.get_by_id(task_id, wrong_tenant)

        assert result is None

    @pytest.mark.asyncio
    async def test_update_task_success(self, repository, mock_session):
        """Test successful task update."""
        task = MagicMock(spec=Task)
        task.component = MagicMock()
        update_data = {"name": "Updated Name", "description": "Updated description"}

        # Mock session operations
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        result = await repository.update(task, update_data)

        mock_session.commit.assert_called_once()
        # Now calls refresh 3 times: once for component relationship, once for task, once for component relationship again
        assert mock_session.refresh.call_count == 3
        assert result == task

    @pytest.mark.asyncio
    async def test_delete_task_success(self, repository, mock_session):
        """Test successful task deletion."""
        task = MagicMock(spec=Task)
        task.component = MagicMock()

        # Mock session operations
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        await repository.delete(task)

        # Now deletes the component (cascade deletes task)
        mock_session.delete.assert_called_once_with(task.component)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_tasks_with_pagination(self, repository, mock_session):
        """Test listing tasks with pagination."""
        tenant_id = "default"

        # Mock the query results
        mock_tasks = [MagicMock(spec=Task) for _ in range(10)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_tasks

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 25

        mock_session.execute.side_effect = [mock_count_result, mock_result]

        tasks, total = await repository.list_with_filters(tenant_id, skip=0, limit=10)

        assert len(tasks) == 10
        assert total == 25
        assert tasks == mock_tasks

    @pytest.mark.asyncio
    async def test_list_tasks_filter_by_function(self, repository, mock_session):
        """Test filtering tasks by function."""
        tenant_id = "default"

        # Mock the query results
        mock_tasks = [MagicMock(spec=Task) for _ in range(5)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_tasks

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 5

        mock_session.execute.side_effect = [mock_count_result, mock_result]

        tasks, total = await repository.list_with_filters(
            tenant_id, function="reasoning"
        )

        assert len(tasks) == 5
        assert total == 5

    @pytest.mark.asyncio
    async def test_list_tasks_filter_by_scope(self, repository, mock_session):
        """Test filtering tasks by scope."""
        tenant_id = "default"

        # Mock the query results
        mock_tasks = [MagicMock(spec=Task) for _ in range(3)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_tasks

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 3

        mock_session.execute.side_effect = [mock_count_result, mock_result]

        tasks, total = await repository.list_with_filters(tenant_id, scope="processing")

        assert len(tasks) == 3
        assert total == 3

    @pytest.mark.asyncio
    async def test_search_tasks_by_name(self, repository, mock_session):
        """Test searching tasks by name."""
        tenant_id = "default"
        query = "security"

        # Mock the query results
        mock_tasks = [MagicMock(spec=Task) for _ in range(2)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_tasks

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 2

        mock_session.execute.side_effect = [mock_count_result, mock_result]

        tasks, total = await repository.search(tenant_id, query)

        assert len(tasks) == 2
        assert total == 2

    @pytest.mark.asyncio
    async def test_search_tasks_by_description(self, repository, mock_session):
        """Test searching tasks by description."""
        tenant_id = "default"
        query = "alert analysis"

        # Mock the query results
        mock_tasks = [MagicMock(spec=Task) for _ in range(1)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_tasks

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_session.execute.side_effect = [mock_count_result, mock_result]

        tasks, total = await repository.search(tenant_id, query)

        assert len(tasks) == 1
        assert total == 1

    @pytest.mark.asyncio
    async def test_search_empty_results(self, repository, mock_session):
        """Test search returning empty results."""
        tenant_id = "default"
        query = "nonexistent"

        # Mock empty query results
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_session.execute.side_effect = [mock_count_result, mock_result]

        tasks, total = await repository.search(tenant_id, query)

        assert len(tasks) == 0
        assert total == 0

    @pytest.mark.asyncio
    async def test_create_task_duplicate_name(self, repository, mock_session):
        """Test handling duplicate task names per tenant."""
        task_data = {
            "tenant_id": "default",
            "name": "Duplicate Task",  # This will be used for component
            "script": "TASK test: RETURN 'hello'",
            "function": "reasoning",
        }

        # Mock the Component and Task creation
        mock_component = MagicMock()
        mock_component.id = "test-component-id"
        mock_task = MagicMock(spec=Task)
        mock_task.id = "test-task-id"

        # Mock session operations
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        # Mock ComponentRepository for cy_name generation
        mock_comp_repo = MagicMock()
        mock_comp_repo.generate_cy_name.return_value = "duplicate_task"
        mock_comp_repo.ensure_unique_cy_name = AsyncMock(return_value="duplicate_task")

        # Mock database constraint error on duplicate
        from sqlalchemy.exc import IntegrityError

        mock_session.commit = AsyncMock(
            side_effect=IntegrityError("Duplicate key", "orig", "params")
        )

        with (
            patch("analysi.repositories.task.Task", return_value=mock_task),
            patch("analysi.repositories.task.Component", return_value=mock_component),
            patch(
                "analysi.repositories.component.ComponentRepository",
                return_value=mock_comp_repo,
            ),
        ):
            with pytest.raises(IntegrityError):
                await repository.create(task_data)

    @pytest.mark.asyncio
    async def test_update_non_existent_task(self, repository, mock_session):
        """Test updating non-existent task."""
        task = MagicMock(spec=Task)
        task.id = uuid.uuid4()
        task.component = MagicMock()
        update_data = {"name": "Updated"}

        # Mock session operations - update should still work even if task doesn't exist
        # The repository doesn't validate existence, that's handled by the service
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        result = await repository.update(task, update_data)

        mock_session.commit.assert_called_once()
        # Now calls refresh 3 times: once for component relationship, once for task, once for component relationship again
        assert mock_session.refresh.call_count == 3
        assert result == task

    @pytest.mark.asyncio
    async def test_delete_non_existent_task(self, repository, mock_session):
        """Test deleting non-existent task."""
        task = MagicMock(spec=Task)
        task.id = uuid.uuid4()
        task.component = MagicMock()

        # Mock session operations - delete should work even if task doesn't exist
        # The repository doesn't validate existence, that's handled by the service
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        await repository.delete(task)

        # Now deletes the component (cascade deletes task)
        mock_session.delete.assert_called_once_with(task.component)
        mock_session.commit.assert_called_once()


class TestTaskLookupAppFiltering:
    """Regression: task lookups must work regardless of app value.

    Same class of bug as the skill lookup issue found in Delos — content
    packs install tasks with app='foundation' or app='examples', so
    filtering by app='default' would miss them.
    """

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.fixture
    def repository(self, mock_session):
        return TaskRepository(mock_session)

    @pytest.mark.asyncio
    async def test_get_task_by_cy_name_no_app_filter_by_default(
        self, repository, mock_session
    ):
        """get_task_by_cy_name without app arg must NOT filter by app."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        await repository.get_task_by_cy_name("tenant-1", "splunk_ip_event_search")

        call_args = mock_session.execute.call_args
        stmt = call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))

        assert "app" not in compiled.lower() or "app =" not in compiled, (
            f"get_task_by_cy_name should not filter by app when app=None. Query: {compiled}"
        )
