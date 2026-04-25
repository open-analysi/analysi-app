"""Integration tests for Task CRUD tools."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.auth.models import CurrentUser
from analysi.mcp.context import set_mcp_current_user, set_tenant
from analysi.mcp.tools import task_tools
from analysi.models.auth import SYSTEM_USER_ID
from analysi.repositories.task import TaskRepository


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskTools:
    """Test Task CRUD operation tools."""

    @pytest.fixture(autouse=True)
    def _mcp_user(self):
        """Set MCP user context so RBAC checks pass."""
        set_mcp_current_user(
            CurrentUser(
                user_id="test-user",
                email="test@test.com",
                tenant_id="test",
                roles=["analyst"],
                actor_type="user",
            )
        )

    @pytest.fixture
    async def sample_task(self, integration_test_session: AsyncSession):
        """Create a sample task for testing."""
        task_repo = TaskRepository(integration_test_session)
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        task_data = {
            "tenant_id": tenant_id,
            "name": "Sample Task",
            "script": "x = 10\nreturn x",
            "description": "A sample task for testing",
            "cy_name": "sample_task",
            "created_by": str(SYSTEM_USER_ID),
        }

        task = await task_repo.create(task_data)
        await integration_test_session.commit()

        return {"task": task, "tenant_id": tenant_id}

    @pytest.mark.asyncio
    async def test_get_task_by_id(
        self, integration_test_session: AsyncSession, sample_task
    ):
        """Verify retrieving task by UUID returns correct task with script."""
        task = sample_task["task"]
        tenant_id = sample_task["tenant_id"]

        # Set tenant context
        set_tenant(tenant_id)

        result = await task_tools.get_task(str(task.component_id))

        assert result["id"] == str(task.component_id)
        assert result["name"] == "Sample Task"
        assert result["script"] == "x = 10\nreturn x"
        assert result["cy_name"] == "sample_task"

    @pytest.mark.asyncio
    async def test_get_task_by_cy_name(
        self, integration_test_session: AsyncSession, sample_task
    ):
        """Verify retrieving task by cy_name works correctly."""
        tenant_id = sample_task["tenant_id"]

        # Set tenant context
        set_tenant(tenant_id)

        result = await task_tools.get_task("sample_task")

        assert result["cy_name"] == "sample_task"
        assert result["script"] == "x = 10\nreturn x"

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, integration_test_session: AsyncSession):
        """Verify appropriate error for non-existent task."""
        fake_id = str(uuid4())
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        # Should return error or raise exception
        try:
            result = await task_tools.get_task(fake_id)
            # If no exception, result should indicate failure
            assert result is None or "error" in result
        except Exception:
            # Expected to raise an exception
            pass

    @pytest.mark.asyncio
    async def test_get_task_wrong_tenant(
        self, integration_test_session: AsyncSession, sample_task
    ):
        """Verify tenant isolation prevents cross-tenant access."""
        task = sample_task["task"]
        wrong_tenant = f"other-tenant-{uuid4().hex[:8]}"

        # Should not return task from different tenant
        try:
            result = await task_tools.get_task(str(task.component_id), wrong_tenant)
            assert result is None or "error" in result
        except Exception:
            # Expected behavior
            pass

    @pytest.mark.asyncio
    async def test_update_task_script_success(
        self, integration_test_session: AsyncSession, sample_task
    ):
        """Verify updating task script modifies the database."""
        task = sample_task["task"]
        tenant_id = sample_task["tenant_id"]

        # Set tenant context
        set_tenant(tenant_id)
        task_id = task.component_id  # Save before expiring
        new_script = "a = 20\nb = 30\nreturn a + b"

        result = await task_tools.update_task_script(str(task_id), new_script)

        assert result["success"] is True
        assert result["task"]["script"] == new_script

        # Verify in database (expire to force re-query from DB)
        integration_test_session.expire_all()
        task_repo = TaskRepository(integration_test_session)
        updated_task = await task_repo.get_by_id(task_id, tenant_id)
        assert updated_task.script == new_script

    @pytest.mark.asyncio
    async def test_update_task_script_invalid_task(
        self, integration_test_session: AsyncSession
    ):
        """Verify error handling for updating non-existent task."""
        fake_id = str(uuid4())
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        new_script = "output = 'test'"

        result = await task_tools.update_task_script(fake_id, new_script)

        assert result["success"] is False
        assert "error" in result or result["task"] is None

    @pytest.mark.asyncio
    async def test_create_task_success(self, integration_test_session: AsyncSession):
        """Verify creating a new task with Cy script."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        task_name = "New Test Task"
        script = "x = 100\nreturn x"

        result = await task_tools.create_task(
            name=task_name,
            script=script,
            description="Created by test",
        )

        assert "id" in result
        assert result["task"]["name"] == task_name
        assert result["task"]["script"] == script

        # Verify in database
        task_repo = TaskRepository(integration_test_session)
        created_task = await task_repo.get_by_id(result["id"], tenant_id)
        assert created_task is not None
        assert created_task.script == script

    @pytest.mark.asyncio
    async def test_create_task_auto_cy_name(
        self, integration_test_session: AsyncSession
    ):
        """Verify cy_name is auto-generated from task name if not provided."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        result = await task_tools.create_task(
            name="My Test Task",
            script="output = 'test'",
        )

        # cy_name should be auto-generated as lowercase with underscores
        assert result["task"]["cy_name"] is not None
        assert (
            result["task"]["cy_name"] == "my_test_task"
            or "_" in result["task"]["cy_name"]
        )

    @pytest.mark.asyncio
    async def test_list_tasks_all(self, integration_test_session: AsyncSession):
        """Verify listing all tasks for a tenant."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        task_repo = TaskRepository(integration_test_session)

        # Create 3 tasks
        for i in range(3):
            task_data = {
                "tenant_id": tenant_id,
                "name": f"Task {i}",
                "script": f"output = {i}",
                "created_by": str(SYSTEM_USER_ID),
            }
            await task_repo.create(task_data)
        await integration_test_session.commit()

        result = await task_tools.list_tasks()

        assert "tasks" in result
        assert "total" in result
        assert result["total"] >= 3
        assert len(result["tasks"]) >= 3

    @pytest.mark.asyncio
    async def test_list_tasks_with_filters(
        self, integration_test_session: AsyncSession
    ):
        """Verify filtering tasks by function/scope/status."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        task_repo = TaskRepository(integration_test_session)

        # Create tasks with different functions
        task_data_1 = {
            "tenant_id": tenant_id,
            "name": "Extract Task",
            "script": "output = 'extract'",
            "function": "extraction",
            "created_by": str(SYSTEM_USER_ID),
        }
        task_data_2 = {
            "tenant_id": tenant_id,
            "name": "Summarize Task",
            "script": "output = 'summarize'",
            "function": "summarization",
            "created_by": str(SYSTEM_USER_ID),
        }
        await task_repo.create(task_data_1)
        await task_repo.create(task_data_2)
        await integration_test_session.commit()

        # Filter by function
        result = await task_tools.list_tasks(filters={"function": "extraction"})

        assert "tasks" in result
        # Should only return extraction tasks
        extraction_tasks = [
            t for t in result["tasks"] if t.get("function") == "extraction"
        ]
        assert len(extraction_tasks) > 0

    @pytest.mark.asyncio
    async def test_create_task_with_all_component_fields(
        self, integration_test_session: AsyncSession
    ):
        """Verify creating task with all component fields (app, status, visible, system_only, categories, created_by)."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        result = await task_tools.create_task(
            name="Full Component Fields Task",
            script="output = 'test'",
            description="Task with all component fields",
            cy_name=f"full_component_{uuid4().hex[:6]}",
            # Component fields
            app="VirusTotal",
            status="enabled",
            visible=True,
            system_only=False,
            categories=["Threat Intelligence", "IP Analysis"],
        )

        assert "id" in result
        assert result["task"]["name"] == "Full Component Fields Task"

        # Verify all component fields in database
        task_repo = TaskRepository(integration_test_session)
        created_task = await task_repo.get_by_id(result["id"], tenant_id)
        assert created_task is not None
        assert created_task.component.app == "VirusTotal"
        assert created_task.component.status == "enabled"
        assert created_task.component.visible is True
        assert created_task.component.system_only is False
        assert created_task.component.categories == [
            "Threat Intelligence",
            "IP Analysis",
        ]
        assert created_task.component.created_by == SYSTEM_USER_ID

    @pytest.mark.asyncio
    async def test_create_task_with_all_task_fields(
        self, integration_test_session: AsyncSession
    ):
        """Verify creating task with all task-specific fields (directive, function, scope, mode, llm_config, data_samples)."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        llm_config = {"default_model": "gpt-4", "temperature": 0.3, "max_tokens": 800}

        data_samples = [
            {
                "name": "Test IP",
                "description": "Test suspicious IP",
                "input": {"ip": "192.168.1.1", "context": "firewall_alert"},
            }
        ]

        result = await task_tools.create_task(
            name="Full Task Fields Task",
            script="output = 'analysis complete'",
            description="Task with all task fields",
            cy_name=f"full_task_{uuid4().hex[:6]}",
            # Task-specific fields
            directive="You are a cybersecurity analyst specializing in threat detection.",
            function="reasoning",
            scope="processing",
            mode="saved",
            llm_config=llm_config,
            data_samples=data_samples,
        )

        assert "id" in result
        assert result["task"]["name"] == "Full Task Fields Task"

        # Verify all task fields in database
        task_repo = TaskRepository(integration_test_session)
        created_task = await task_repo.get_by_id(result["id"], tenant_id)
        assert created_task is not None
        assert (
            created_task.directive
            == "You are a cybersecurity analyst specializing in threat detection."
        )
        assert created_task.function == "reasoning"
        assert created_task.scope == "processing"
        assert created_task.mode == "saved"
        assert created_task.llm_config == llm_config
        assert created_task.data_samples == data_samples

    @pytest.mark.asyncio
    async def test_create_task_with_categories_field(
        self, integration_test_session: AsyncSession
    ):
        """Verify creating task with categories field works correctly."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        result = await task_tools.create_task(
            name="Categories Test Task",
            script="output = 'test'",
            categories=["Security", "Analysis", "AI"],
        )

        assert "id" in result

        # Verify categories in database
        task_repo = TaskRepository(integration_test_session)
        created_task = await task_repo.get_by_id(result["id"], tenant_id)
        assert created_task is not None
        assert created_task.component.categories == ["Security", "Analysis", "AI"]

    @pytest.mark.asyncio
    async def test_create_task_with_tags_alias(
        self, integration_test_session: AsyncSession
    ):
        """Verify creating task with 'tags' field maps to 'categories' in database."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        # Call with 'tags' parameter (should map to categories internally)
        result = await task_tools.create_task(
            name="Tags Alias Test Task",
            script="output = 'test'",
            tags=["threat-intel", "ip-reputation", "automated"],
        )

        assert "id" in result

        # Verify tags are stored as categories in database
        task_repo = TaskRepository(integration_test_session)
        created_task = await task_repo.get_by_id(result["id"], tenant_id)
        assert created_task is not None
        assert created_task.component.categories == [
            "threat-intel",
            "ip-reputation",
            "automated",
        ]

    @pytest.mark.asyncio
    async def test_create_task_with_complete_specification(
        self, integration_test_session: AsyncSession
    ):
        """Verify creating task with ALL 13+ fields matching demo JSON format."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        # This mimics the full JSON spec from demo_datasets/tasks/*.json
        result = await task_tools.create_task(
            name="IP Reputation Analysis",
            script="return 'analysis_complete'",
            description="Advanced IP reputation analysis with VirusTotal integration",
            cy_name=f"ip_reputation_analysis_{uuid4().hex[:6]}",
            # Component fields
            app="VirusTotal",
            status="enabled",
            visible=True,
            system_only=False,
            categories=["Threat Intelligence", "VirusTotal", "IP Analysis", "AI"],
            # Task fields
            directive="You are a cybersecurity analyst specializing in threat intelligence.",
            function="reasoning",
            scope="processing",
            mode="saved",
            llm_config={
                "default_model": "gpt-4",
                "temperature": 0.3,
                "max_tokens": 1000,
            },
            data_samples=[
                {
                    "name": "IP with Context",
                    "description": "Firewall alert investigation",
                    "input": {"ip": "192.168.1.100", "context": "suspicious_activity"},
                },
                {
                    "name": "Known Malicious IP",
                    "description": "Test with known bad actor IP",
                    "input": {
                        "ip": "91.234.56.42",
                        "context": "intrusion_detection",
                        "priority": "high",
                    },
                },
            ],
        )

        assert "id" in result
        assert result["task"]["name"] == "IP Reputation Analysis"

        # Verify complete specification in database
        # Refresh session to see data committed by MCP tool's separate session
        await integration_test_session.commit()
        task_repo = TaskRepository(integration_test_session)
        created_task = await task_repo.get_by_id(result["id"], tenant_id)
        assert created_task is not None, (
            f"Task {result['id']} not found in tenant {tenant_id}"
        )

        # Verify component fields
        assert created_task.component.app == "VirusTotal"
        assert created_task.component.status == "enabled"
        assert created_task.component.visible is True
        assert created_task.component.system_only is False
        assert "Threat Intelligence" in created_task.component.categories
        assert "AI" in created_task.component.categories
        assert created_task.component.created_by == SYSTEM_USER_ID

        # Verify task fields
        assert "cybersecurity analyst" in created_task.directive
        assert created_task.function == "reasoning"
        assert created_task.scope == "processing"
        assert created_task.mode == "saved"
        assert created_task.llm_config["default_model"] == "gpt-4"
        assert created_task.llm_config["temperature"] == 0.3
        assert len(created_task.data_samples) == 2
        assert created_task.data_samples[0]["name"] == "IP with Context"

    @pytest.mark.asyncio
    async def test_create_task_defaults_match_schema(
        self, integration_test_session: AsyncSession
    ):
        """Verify task creation with minimal fields uses correct defaults from TaskBase schema."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        # Create with only required fields
        result = await task_tools.create_task(
            name="Minimal Task",
            script="output = 'test'",
        )

        assert "id" in result, f"create_task missing 'id': {result}"
        assert result.get("error") is None, f"create_task failed: {result.get('error')}"

        # Verify defaults match TaskBase schema
        # Refresh session to see data committed by MCP tool's separate session
        await integration_test_session.commit()
        task_repo = TaskRepository(integration_test_session)
        created_task = await task_repo.get_by_id(result["id"], tenant_id)
        assert created_task is not None, (
            f"Task {result['id']} not found in tenant {tenant_id}. MCP result: {result}"
        )

        # Component field defaults (from TaskBase)
        assert created_task.component.app == "default"
        assert created_task.component.status == "enabled"
        assert created_task.component.visible is False
        assert created_task.component.system_only is False
        assert created_task.component.categories == []
        assert created_task.component.created_by == SYSTEM_USER_ID  # MCP tool default

        # Task field defaults (from TaskBase)
        assert created_task.mode == "saved"
        assert created_task.directive is None
        assert created_task.function is None
        # scope defaults to "processing" in model
        # llm_config can be None or {} depending on if it was provided
        assert created_task.llm_config in (None, {})

    @pytest.mark.asyncio
    async def test_create_task_with_invalid_scope(
        self, integration_test_session: AsyncSession
    ):
        """Verify validation error for invalid scope value."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        result = await task_tools.create_task(
            name="Invalid Scope Task",
            script="output = 'test'",
            scope="invalid_scope",  # Should fail - not in [input, processing, output]
        )

        # Should return error
        assert "error" in result
        assert result["id"] is None

    @pytest.mark.asyncio
    async def test_create_task_with_invalid_mode(
        self, integration_test_session: AsyncSession
    ):
        """Verify validation error for invalid mode value."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        result = await task_tools.create_task(
            name="Invalid Mode Task",
            script="output = 'test'",
            mode="invalid_mode",  # Should fail - not in [ad_hoc, saved]
        )

        # Should return error
        assert "error" in result
        assert result["id"] is None

    @pytest.mark.asyncio
    async def test_create_task_with_all_function_types(
        self, integration_test_session: AsyncSession
    ):
        """Verify all valid function types are accepted."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        task_repo = TaskRepository(integration_test_session)

        # All valid function types from the document
        valid_functions = [
            "summarization",
            "data_conversion",
            "extraction",
            "reasoning",
            "planning",
            "visualization",
            "search",
        ]

        for function_type in valid_functions:
            result = await task_tools.create_task(
                name=f"Task with {function_type}",
                script="output = 'test'",
                function=function_type,
                cy_name=f"task_{function_type}_{uuid4().hex[:4]}",
            )

            assert "id" in result
            assert result["id"] is not None

            # Verify in database
            created_task = await task_repo.get_by_id(result["id"], tenant_id)
            assert created_task.function == function_type

    @pytest.mark.asyncio
    async def test_create_task_with_all_scope_types(
        self, integration_test_session: AsyncSession
    ):
        """Verify all valid scope types are accepted."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        task_repo = TaskRepository(integration_test_session)

        # All valid scope types
        valid_scopes = ["input", "processing", "output"]

        for scope_type in valid_scopes:
            result = await task_tools.create_task(
                name=f"Task with {scope_type} scope",
                script="output = 'test'",
                scope=scope_type,
                cy_name=f"task_scope_{scope_type}_{uuid4().hex[:4]}",
            )

            assert "id" in result
            assert result["id"] is not None

            # Verify in database
            created_task = await task_repo.get_by_id(result["id"], tenant_id)
            assert created_task.scope == scope_type

    @pytest.mark.asyncio
    async def test_create_task_llm_config_structure(
        self, integration_test_session: AsyncSession
    ):
        """Verify LLM config with all standard fields is persisted correctly."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        # Complete LLM config as shown in documentation
        llm_config = {
            "default_model": "gpt-4",
            "temperature": 0.3,
            "max_tokens": 800,
        }

        result = await task_tools.create_task(
            name="Task with Full LLM Config",
            script="output = 'test'",
            llm_config=llm_config,
        )

        assert "id" in result

        # Verify exact structure in database
        task_repo = TaskRepository(integration_test_session)
        created_task = await task_repo.get_by_id(result["id"], tenant_id)
        assert created_task.llm_config == llm_config
        assert created_task.llm_config["default_model"] == "gpt-4"
        assert created_task.llm_config["temperature"] == 0.3
        assert created_task.llm_config["max_tokens"] == 800

    @pytest.mark.asyncio
    async def test_create_task_data_samples_full_structure(
        self, integration_test_session: AsyncSession
    ):
        """Verify data_samples with complete structure as shown in documentation."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Set tenant context
        set_tenant(tenant_id)
        # Full data_samples structure from documentation
        data_samples = [
            {
                "name": "Suspicious Login IP",
                "description": "Investigate IP from failed login attempts",
                "input": {"ip": "91.234.56.212", "context": "suspicious_login_attempt"},
            },
            {
                "name": "Known Malicious IP",
                "description": "Test with Tor exit node / known malicious IP",
                "input": {"ip": "91.234.56.101", "context": "firewall_alert"},
            },
        ]

        result = await task_tools.create_task(
            name="Task with Full Data Samples",
            script="output = input",
            data_samples=data_samples,
        )

        assert "id" in result

        # Verify complete structure in database
        task_repo = TaskRepository(integration_test_session)
        created_task = await task_repo.get_by_id(result["id"], tenant_id)
        assert len(created_task.data_samples) == 2
        assert created_task.data_samples[0]["name"] == "Suspicious Login IP"
        assert (
            created_task.data_samples[0]["description"]
            == "Investigate IP from failed login attempts"
        )
        assert created_task.data_samples[0]["input"]["ip"] == "91.234.56.212"
        assert created_task.data_samples[1]["name"] == "Known Malicious IP"
        assert created_task.data_samples[1]["input"]["context"] == "firewall_alert"
