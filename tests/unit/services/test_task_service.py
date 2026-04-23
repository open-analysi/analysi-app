"""Unit tests for TaskService."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.models.auth import SYSTEM_USER_ID
from analysi.models.task import Task
from analysi.repositories.task import TaskRepository
from analysi.schemas.task import TaskCreate, TaskUpdate
from analysi.services.task import TaskService


class TestTaskService:
    """Test TaskService business logic."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.fixture
    def mock_repository(self):
        """Create a mock TaskRepository."""
        return AsyncMock(spec=TaskRepository)

    @pytest.fixture
    def service(self, mock_session, mock_repository):
        """Create a TaskService instance with mocks."""
        service = TaskService(mock_session)
        service.repository = mock_repository
        # Skip tool validation — these tests verify CRUD logic, not Cy script analysis
        service._validate_script_tools = AsyncMock(return_value=None)
        return service

    @pytest.mark.asyncio
    async def test_create_task_with_defaults(self, service, mock_repository):
        """Test creating task with minimal fields."""
        tenant_id = "default"
        task_data = TaskCreate(
            name="Test Task",
            script="TASK test: RETURN 'hello'",
            created_by=str(SYSTEM_USER_ID),
        )

        # Mock the repository call
        mock_task = MagicMock(spec=Task)
        mock_repository.create.return_value = mock_task

        result = await service.create_task(tenant_id, task_data)

        # Verify repository was called with correct data
        mock_repository.create.assert_called_once()
        call_args = mock_repository.create.call_args[0][0]
        assert call_args["tenant_id"] == tenant_id
        assert call_args["name"] == "Test Task"
        assert call_args["script"] == "TASK test: RETURN 'hello'"
        assert result == mock_task

    @pytest.mark.asyncio
    async def test_create_task_with_full_data(self, service, mock_repository):
        """Test creating task with all optional fields."""
        tenant_id = "customer-123"
        task_data = TaskCreate(
            name="Full Task",
            description="Complete task with all fields",
            script="TASK full: RETURN 'complete'",
            llm_config={"model": "gpt-4", "temperature": 0.7},
            function="reasoning",
            scope="processing",
            created_by=str(SYSTEM_USER_ID),
        )

        # Mock the repository call
        mock_task = MagicMock(spec=Task)
        mock_repository.create.return_value = mock_task

        result = await service.create_task(tenant_id, task_data)

        # Verify repository was called with correct data
        mock_repository.create.assert_called_once()
        call_args = mock_repository.create.call_args[0][0]
        assert call_args["tenant_id"] == tenant_id
        assert call_args["name"] == "Full Task"
        assert call_args["description"] == "Complete task with all fields"
        assert call_args["script"] == "TASK full: RETURN 'complete'"
        assert call_args["llm_config"] == {"model": "gpt-4", "temperature": 0.7}
        assert call_args["function"] == "reasoning"
        assert call_args["scope"] == "processing"
        assert result == mock_task

    @pytest.mark.asyncio
    async def test_get_task_success(self, service, mock_repository):
        """Test retrieving task by ID."""
        task_id = uuid.uuid4()
        tenant_id = "default"

        # Mock the repository call
        mock_task = MagicMock(spec=Task)
        mock_task.id = task_id
        mock_repository.get_by_id.return_value = mock_task

        result = await service.get_task(task_id, tenant_id)

        mock_repository.get_by_id.assert_called_once_with(task_id, tenant_id)
        assert result == mock_task

    @pytest.mark.asyncio
    async def test_update_task_partial(self, service, mock_repository):
        """Test updating only specific fields."""
        task_id = uuid.uuid4()
        tenant_id = "default"
        update_data = TaskUpdate(name="Updated Name")

        # Mock getting the task first
        mock_task = MagicMock(spec=Task)
        mock_repository.get_by_id.return_value = mock_task
        mock_repository.update.return_value = mock_task

        result = await service.update_task(task_id, tenant_id, update_data)

        mock_repository.get_by_id.assert_called_once_with(task_id, tenant_id)
        mock_repository.update.assert_called_once()
        assert result == mock_task

    @pytest.mark.asyncio
    async def test_update_task_script(self, service, mock_repository):
        """Test updating script field."""
        task_id = uuid.uuid4()
        tenant_id = "default"
        update_data = TaskUpdate(script="TASK updated: RETURN 'new'")

        # Mock getting the task first
        mock_task = MagicMock(spec=Task)
        mock_repository.get_by_id.return_value = mock_task
        mock_repository.update.return_value = mock_task

        result = await service.update_task(task_id, tenant_id, update_data)

        mock_repository.get_by_id.assert_called_once_with(task_id, tenant_id)
        mock_repository.update.assert_called_once()
        assert result == mock_task

    @pytest.mark.asyncio
    async def test_delete_task_success(self, service, mock_repository):
        """Test successful task deletion."""
        task_id = uuid.uuid4()
        tenant_id = "default"

        # Mock getting the task first
        mock_task = MagicMock(spec=Task)
        mock_repository.get_by_id.return_value = mock_task
        mock_repository.delete.return_value = None

        result = await service.delete_task(task_id, tenant_id)

        mock_repository.get_by_id.assert_called_once_with(task_id, tenant_id)
        mock_repository.delete.assert_called_once_with(mock_task)
        assert result is True

    @pytest.mark.asyncio
    async def test_list_tasks_calculates_pagination(self, service, mock_repository):
        """Test that list_tasks correctly calculates pagination."""
        tenant_id = "default"

        # Mock the repository response
        mock_tasks = [MagicMock(spec=Task) for _ in range(5)]
        mock_repository.list_with_filters.return_value = (mock_tasks, 25)

        result = await service.list_tasks(tenant_id, skip=10, limit=5)

        mock_repository.list_with_filters.assert_called_once_with(
            tenant_id=tenant_id,
            skip=10,
            limit=5,
            function=None,
            scope=None,
            status=None,
            cy_name=None,
            categories=None,
            app=None,
            name_filter=None,
        )
        tasks, pagination = result
        assert tasks == mock_tasks
        assert pagination["total"] == 25
        assert pagination["skip"] == 10
        assert pagination["limit"] == 5

    @pytest.mark.asyncio
    async def test_search_tasks_combines_fields(self, service, mock_repository):
        """Test searching across name, description, and tags."""
        tenant_id = "default"
        query = "security alert"

        # Mock the repository response
        mock_tasks = [MagicMock(spec=Task) for _ in range(3)]
        mock_repository.search.return_value = (mock_tasks, 3)

        result = await service.search_tasks(tenant_id, query)

        mock_repository.search.assert_called_once_with(
            tenant_id=tenant_id, query=query, skip=0, limit=100, categories=None
        )
        tasks, pagination = result
        assert tasks == mock_tasks
        assert pagination["total"] == 3

    @pytest.mark.asyncio
    async def test_create_task_invalid_script(self, service, mock_repository):
        """Test validation of empty script - should be handled by Pydantic."""

        # This should raise a validation error before reaching the service
        with pytest.raises(ValueError):
            TaskCreate(name="Invalid Task", script="")  # Empty script should be invalid

    @pytest.mark.asyncio
    async def test_update_task_not_found(self, service, mock_repository):
        """Test updating non-existent task returns None."""
        task_id = uuid.uuid4()
        tenant_id = "default"
        update_data = TaskUpdate(name="Updated")

        # Mock repository to return None
        mock_repository.get_by_id.return_value = None

        result = await service.update_task(task_id, tenant_id, update_data)

        mock_repository.get_by_id.assert_called_once_with(task_id, tenant_id)
        mock_repository.update.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_task_not_found(self, service, mock_repository):
        """Test deleting non-existent task returns False."""
        task_id = uuid.uuid4()
        tenant_id = "default"

        # Mock repository to return None
        mock_repository.get_by_id.return_value = None

        result = await service.delete_task(task_id, tenant_id)

        mock_repository.get_by_id.assert_called_once_with(task_id, tenant_id)
        mock_repository.delete.assert_not_called()
        assert result is False

    @pytest.mark.asyncio
    async def test_list_tasks_invalid_page(self, service, mock_repository):
        """Test handling out of range pagination."""
        tenant_id = "default"

        # Mock repository to return empty results for out of range
        mock_repository.list_with_filters.return_value = ([], 100)

        result = await service.list_tasks(tenant_id, skip=1000, limit=10)

        tasks, pagination = result
        assert tasks == []
        assert pagination["total"] == 100


class TestTaskServiceValidateScriptTools:
    """Tests for TaskService._validate_script_tools()."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_validate_script_returns_none_on_syntax_error(self, mock_session):
        """Syntax errors should return None (non-blocking)."""
        service = TaskService(mock_session)

        with patch(
            "analysi.services.cy_tool_registry.load_tool_registry_async"
        ) as mock_reg:
            mock_reg.return_value = {}
            # A script with obvious syntax issues
            result = await service._validate_script_tools("x = [", "test-tenant")
        assert result is None

    @pytest.mark.asyncio
    async def test_validate_script_with_cy_builtin_does_not_raise(self, mock_session):
        """cy-language built-in functions (sum, len, etc.) should not be flagged."""
        service = TaskService(mock_session)

        with (
            patch(
                "analysi.services.cy_tool_registry.load_tool_registry_async"
            ) as mock_reg,
            patch("cy_language.analyze_script") as mock_analyze,
            patch("cy_language.native_functions.default_registry") as mock_registry,
        ):
            mock_reg.return_value = {}
            mock_analyze.return_value = {"tools_used": ["native::tools::sum"]}
            mock_registry.get_tools_dict.return_value = {"sum": lambda x: x}

            result = await service._validate_script_tools(
                "total = sum([1, 2, 3])\nreturn total", "test-tenant"
            )
        # Should not raise, returns analysis result
        assert result is not None

    @pytest.mark.asyncio
    async def test_validate_script_raises_for_unknown_tools(self, mock_session):
        """Unknown tools should raise ValueError."""
        service = TaskService(mock_session)

        with (
            patch(
                "analysi.services.cy_tool_registry.load_tool_registry_async"
            ) as mock_reg,
            patch("cy_language.analyze_script") as mock_analyze,
            patch("cy_language.native_functions.default_registry") as mock_registry,
        ):
            mock_reg.return_value = {}
            mock_analyze.return_value = {"tools_used": ["app::nonexistent::tool"]}
            mock_registry.get_tools_dict.return_value = {}

            with pytest.raises(ValueError, match="unknown tools"):
                await service._validate_script_tools(
                    "x = app::nonexistent::tool()", "test-tenant"
                )

    @pytest.mark.asyncio
    async def test_validate_script_passes_for_known_tools(self, mock_session):
        """Tools in the registry should not raise."""
        service = TaskService(mock_session)

        with (
            patch(
                "analysi.services.cy_tool_registry.load_tool_registry_async"
            ) as mock_reg,
            patch("cy_language.analyze_script") as mock_analyze,
            patch("cy_language.native_functions.default_registry") as mock_registry,
        ):
            mock_reg.return_value = {"app::virustotal::ip_reputation": {}}
            mock_analyze.return_value = {
                "tools_used": ["app::virustotal::ip_reputation"]
            }
            mock_registry.get_tools_dict.return_value = {}

            result = await service._validate_script_tools(
                "x = app::virustotal::ip_reputation(ip='1.2.3.4')", "test-tenant"
            )
        assert result is not None

    @pytest.mark.asyncio
    async def test_validate_script_passes_for_ingest_functions_by_bare_name(
        self, mock_session
    ):
        """Ingest/checkpoint functions referenced by bare name should be accepted.

        Regression: scripts calling get_checkpoint, set_checkpoint, ingest_alerts,
        or default_lookback were rejected because the registry stores them as
        native::ingest::get_checkpoint but analyze_script reports the bare name.
        """
        service = TaskService(mock_session)

        with (
            patch(
                "analysi.services.cy_tool_registry.load_tool_registry_async"
            ) as mock_reg,
            patch("cy_language.analyze_script") as mock_analyze,
            patch("cy_language.native_functions.default_registry") as mock_registry,
        ):
            # Registry has FQN form
            mock_reg.return_value = {
                "native::ingest::get_checkpoint": {},
                "native::ingest::set_checkpoint": {},
                "native::ingest::ingest_alerts": {},
                "native::ingest::default_lookback": {},
            }
            # analyze_script reports bare names
            mock_analyze.return_value = {
                "tools_used": [
                    "default_lookback",
                    "get_checkpoint",
                    "ingest_alerts",
                    "set_checkpoint",
                ]
            }
            mock_registry.get_tools_dict.return_value = {}

            result = await service._validate_script_tools(
                "ts = default_lookback()", "test-tenant"
            )
        assert result is not None


class TestTaskServiceGetTaskByCyName:
    """Tests for TaskService.get_task_by_cy_name()."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_returns_task_when_found(self, mock_session):
        service = TaskService(mock_session)
        mock_task = MagicMock(spec=Task)

        service._validate_script_tools = AsyncMock(return_value=None)
        service.repository.list_with_filters = AsyncMock(return_value=([mock_task], 1))

        result = await service.get_task_by_cy_name(
            "virustotal_ip_reputation", "default"
        )
        assert result == mock_task

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, mock_session):
        service = TaskService(mock_session)

        service._validate_script_tools = AsyncMock(return_value=None)
        service.repository.list_with_filters = AsyncMock(return_value=([], 0))

        result = await service.get_task_by_cy_name("nonexistent_task", "default")
        assert result is None


class TestTaskServiceAuditLogging:
    """Tests for TaskService._log_audit()."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_log_audit_skipped_when_no_context(self, mock_session):
        """Audit logging should be skipped when audit_context is None."""
        service = TaskService(mock_session)
        # Should not raise when no audit context
        await service._log_audit(
            tenant_id="test",
            action="task.create",
            resource_id="some-id",
            audit_context=None,
        )

    @pytest.mark.asyncio
    async def test_log_audit_called_with_context(self, mock_session):
        """Audit logging should call the repository when context is provided."""
        from analysi.schemas.audit_context import AuditContext

        service = TaskService(mock_session)
        audit_ctx = AuditContext(
            actor_id="user-123",
            actor_type="user",
            source="api",
        )

        with patch("analysi.services.task.ActivityAuditRepository") as mock_repo_class:
            mock_repo = mock_repo_class.return_value
            mock_repo.create = AsyncMock()

            await service._log_audit(
                tenant_id="test",
                action="task.create",
                resource_id="res-id",
                audit_context=audit_ctx,
                details={"task_name": "Test Task"},
            )
            mock_repo.create.assert_called_once()


class TestTaskServiceListWithFilters:
    """Tests for TaskService.list_tasks() with various filters."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session):
        service = TaskService(mock_session)
        service._validate_script_tools = AsyncMock(return_value=None)
        service.repository = AsyncMock(spec=TaskRepository)
        return service

    @pytest.mark.asyncio
    async def test_list_tasks_with_function_filter(self, service):
        service.repository.list_with_filters.return_value = ([], 0)
        tasks, _ = await service.list_tasks("test", function="reasoning")
        service.repository.list_with_filters.assert_called_once_with(
            tenant_id="test",
            skip=0,
            limit=100,
            function="reasoning",
            scope=None,
            status=None,
            cy_name=None,
            categories=None,
            app=None,
            name_filter=None,
        )

    @pytest.mark.asyncio
    async def test_list_tasks_with_cy_name_filter(self, service):
        mock_task = MagicMock(spec=Task)
        service.repository.list_with_filters.return_value = ([mock_task], 1)

        tasks, pagination = await service.list_tasks("test", cy_name="my_task")
        assert len(tasks) == 1
        assert pagination["total"] == 1

    @pytest.mark.asyncio
    async def test_list_tasks_with_status_filter(self, service):
        service.repository.list_with_filters.return_value = ([], 0)
        await service.list_tasks("test", status="enabled")
        service.repository.list_with_filters.assert_called_once_with(
            tenant_id="test",
            skip=0,
            limit=100,
            function=None,
            scope=None,
            status="enabled",
            cy_name=None,
            categories=None,
            app=None,
            name_filter=None,
        )

    @pytest.mark.asyncio
    async def test_search_tasks_with_pagination(self, service):
        service.repository.search.return_value = ([], 0)
        await service.search_tasks("test", "query", skip=5, limit=20)
        service.repository.search.assert_called_once_with(
            tenant_id="test",
            query="query",
            skip=5,
            limit=20,
            categories=None,
        )
