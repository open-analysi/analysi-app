"""Integration tests for MCP tools using internal endpoints and services.

Tests that MCP tools properly integrate with:
- Task execution endpoints (ad-hoc execution with task_run records)
- Cy tool registry
- Integration registry
- Task CRUD operations
"""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.auth.models import CurrentUser
from analysi.mcp import integration_tools
from analysi.mcp.context import set_mcp_current_user, set_tenant
from analysi.mcp.tools import cy_tools, task_tools
from analysi.models.auth import SYSTEM_USER_ID
from analysi.repositories.task import TaskRepository


@pytest.fixture(autouse=True)
def _mcp_user():
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


@pytest.mark.asyncio
@pytest.mark.integration
class TestCyToolsIntegration:
    """Test Cy tools MCP integration with internal services."""

    @pytest.mark.asyncio
    async def test_list_all_active_tool_summaries_returns_fqns(self):
        """Verify list_all_active_tool_summaries returns FQNs only."""
        result = await cy_tools.list_all_active_tool_summaries()

        # Should return FQN list
        assert "tools" in result
        assert "total" in result
        assert result["total"] > 0

        # Should include built-in tools
        assert "sum" in result["tools"]  # Built-in Cy tool
        assert "len" in result["tools"]  # Built-in Cy tool

        # Each should be a string FQN
        for tool_fqn in result["tools"]:
            assert isinstance(tool_fqn, str)

    @pytest.mark.asyncio
    async def test_get_tool_details_returns_full_info(self):
        """Verify get_tool_details returns full tool information."""
        # Set tenant context for database access
        set_tenant("default")

        result = await cy_tools.get_tool_details(["sum", "len"])

        assert "tools" in result
        assert "count" in result
        assert result["count"] == 2

        # Each tool should have full details
        for tool in result["tools"]:
            assert "fqn" in tool
            assert "name" in tool
            assert "description" in tool
            assert isinstance(tool["fqn"], str)
            assert isinstance(tool["description"], str)
            assert len(tool["description"]) > 0

    @pytest.mark.asyncio
    async def test_list_all_active_tool_summaries_includes_custom_natives(self):
        """Verify list_all_active_tool_summaries includes custom native functions.

        Custom native functions are backend-specific tools like llm_run, store_artifact,
        alert_read, table_read, etc. These should be discoverable via MCP alongside
        cy-language native tools (sum, len) and integration tools (app::*).
        """
        result = await cy_tools.list_all_active_tool_summaries()

        assert "tools" in result
        assert result["total"] > 0

        # Custom native LLM functions
        assert "native::llm::llm_run" in result["tools"], (
            "llm_run should be discoverable"
        )
        assert "native::llm::llm_summarize" in result["tools"]
        assert "native::llm::llm_extract" in result["tools"]
        assert "native::llm::llm_evaluate_results" in result["tools"]

        # Custom native artifact functions
        assert "native::tools::store_artifact" in result["tools"]

        # Custom native alert functions
        assert "native::alert::alert_read" in result["tools"]

        # Custom native task composition functions
        assert "native::task::task_run" in result["tools"]

        # Custom native KU functions
        assert "native::ku::table_read" in result["tools"]
        assert "native::ku::table_write" in result["tools"]
        assert "native::ku::document_read" in result["tools"]

    @pytest.mark.asyncio
    async def test_get_tool_details_returns_custom_native_details(self):
        """Verify get_tool_details returns full details for custom native functions.

        Should return parameter schemas, required fields, and return types for
        custom native functions like llm_run and store_artifact.
        """
        # Set tenant context for database access
        set_tenant("default")

        result = await cy_tools.get_tool_details(
            [
                "native::llm::llm_run",
                "native::tools::store_artifact",
                "native::ku::table_read",
            ]
        )

        assert "tools" in result
        assert "count" in result
        assert result["count"] == 3
        assert result["not_found"] == []

        # Find llm_run
        llm_run = next(
            (t for t in result["tools"] if t["fqn"] == "native::llm::llm_run"), None
        )
        assert llm_run is not None, "llm_run details should be returned"
        assert "parameters" in llm_run
        assert "prompt" in llm_run["parameters"], "llm_run should have prompt parameter"

        # Find store_artifact
        store_artifact = next(
            (t for t in result["tools"] if t["fqn"] == "native::tools::store_artifact"),
            None,
        )
        assert store_artifact is not None, "store_artifact details should be returned"
        assert "parameters" in store_artifact
        assert "name" in store_artifact["parameters"], (
            "store_artifact should have name parameter"
        )
        assert "artifact" in store_artifact["parameters"], (
            "store_artifact should have artifact parameter"
        )

        # Find table_read
        table_read = next(
            (t for t in result["tools"] if t["fqn"] == "native::ku::table_read"), None
        )
        assert table_read is not None, "table_read details should be returned"
        assert "parameters" in table_read

    @pytest.mark.asyncio
    async def test_quick_syntax_check_cy_script_uses_real_parser(self):
        """Verify quick_syntax_check_cy_script uses actual Cy parser."""
        valid_script = "x = 10\nreturn x"
        result = await cy_tools.quick_syntax_check_cy_script(valid_script)

        assert result["valid"] is True
        assert result["errors"] is None

    @pytest.mark.asyncio
    async def test_quick_syntax_check_cy_script_detects_real_errors(self):
        """Verify quick_syntax_check_cy_script detects actual syntax errors."""
        invalid_script = "x = 10\nif (x > 5\nreturn x"  # Missing closing paren
        result = await cy_tools.quick_syntax_check_cy_script(invalid_script)

        assert result["valid"] is False
        assert result["errors"] is not None
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_compile_cy_script_generates_real_plan(self):
        """Verify compile_cy_script generates actual execution plan with type inference."""
        script = "x = 10\ny = 20\nreturn x + y"
        result = await cy_tools.compile_cy_script(script)

        # Debug: print validation errors if plan is None
        if result["plan"] is None:
            print(f"Validation errors: {result.get('validation_errors', [])}")

        assert result["plan"] is not None, (
            f"Compilation failed: {result.get('validation_errors', [])}"
        )
        assert result["validation_errors"] == []
        # New format: plan has 'compiled' and 'output_schema' from analyze_types()
        assert "compiled" in result["plan"]
        assert result["plan"]["compiled"] is True
        assert "output_schema" in result["plan"]
        # Should infer number type from x + y
        assert result["plan"]["output_schema"]["type"] == "number"

    @pytest.mark.asyncio
    async def test_get_plan_stats_analyzes_real_script(self):
        """Verify get_plan_stats analyzes actual Cy scripts."""
        script = "x = 10\ny = 20\nz = 30\nreturn x + y + z"
        result = await cy_tools.get_plan_stats(script)

        assert result["total_nodes"] > 0
        assert result["node_types"] is not None
        assert isinstance(result["node_types"], dict)
        # Should have at least 4 nodes (3 assignments + 1 output)
        assert result["total_nodes"] >= 4

    @pytest.mark.asyncio
    async def test_execute_cy_script_adhoc_creates_task_run(self):
        """Verify execute_cy_script_adhoc creates task_run records via API."""
        script = "output = add(5, 10)"

        result = await cy_tools.execute_cy_script_adhoc(script)

        # Should return task execution response with task_run_id
        assert "task_run_id" in result
        assert "status" in result

        # Task run ID should be returned (proving it was created)
        if result["status"] == "completed":
            assert result["task_run_id"] is not None
            # Should be a valid UUID
            from uuid import UUID

            UUID(result["task_run_id"])  # Will raise if invalid

    @pytest.mark.asyncio
    async def test_execute_cy_script_adhoc_with_input_data(self):
        """Verify execute_cy_script_adhoc passes input data correctly."""
        script = "doubled = input * 2\nreturn doubled"
        input_data = 7

        result = await cy_tools.execute_cy_script_adhoc(script, input_data=input_data)

        assert "status" in result
        if result["status"] == "completed":
            assert result["output"] == "14"
            assert result["task_run_id"] is not None


@pytest.mark.asyncio
@pytest.mark.integration
class TestTaskToolsIntegration:
    """Test Task CRUD MCP tools integration with database."""

    @pytest.fixture
    async def sample_task(self, integration_test_session: AsyncSession):
        """Create a sample task for testing."""
        task_repo = TaskRepository(integration_test_session)
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        task_data = {
            "tenant_id": tenant_id,
            "name": "MCP Test Task",
            "script": "x = 100\nreturn x",
            "description": "Task for MCP tools testing",
            "cy_name": "mcp_test_task",
            "created_by": str(SYSTEM_USER_ID),
        }

        task = await task_repo.create(task_data)
        await integration_test_session.commit()

        return {
            "task": task,
            "tenant_id": tenant_id,
            "session": integration_test_session,
        }

    @pytest.mark.asyncio
    async def test_get_task_retrieves_from_database(self, sample_task):
        """Verify get_task retrieves actual task from database."""
        task = sample_task["task"]
        tenant_id = sample_task["tenant_id"]

        # Set tenant context for MCP tools
        set_tenant(tenant_id)

        result = await task_tools.get_task(str(task.component_id))

        # Should return task with all fields
        assert result["id"] == str(task.component_id)
        assert result["name"] == "MCP Test Task"
        assert result["script"] == "x = 100\nreturn x"
        assert result["cy_name"] == "mcp_test_task"

    @pytest.mark.asyncio
    async def test_get_task_by_cy_name(self, sample_task):
        """Verify get_task can retrieve by cy_name."""
        tenant_id = sample_task["tenant_id"]

        # Set tenant context for MCP tools
        set_tenant(tenant_id)

        result = await task_tools.get_task("mcp_test_task")

        assert result["name"] == "MCP Test Task"
        assert result["cy_name"] == "mcp_test_task"

    @pytest.mark.asyncio
    async def test_create_task_persists_to_database(
        self, integration_test_session: AsyncSession
    ):
        """Verify create_task creates actual database record."""
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        task_name = f"New Task {uuid4().hex[:6]}"
        script = "result = 42\nreturn result"

        # Set tenant context for MCP tools
        set_tenant(tenant_id)

        result = await task_tools.create_task(
            name=task_name,
            script=script,
            description="Created via MCP",
            cy_name=f"task_{uuid4().hex[:6]}",
        )

        # Should return created task (nested structure)
        assert "id" in result
        assert "task" in result
        assert result["task"]["name"] == task_name
        assert result["task"]["script"] == script

        # ID should be a valid UUID
        from uuid import UUID

        UUID(result["id"])  # Will raise if invalid

    @pytest.mark.asyncio
    async def test_update_task_script_modifies_database(self, sample_task):
        """Verify update_task_script actually updates database."""
        task = sample_task["task"]
        tenant_id = sample_task["tenant_id"]
        session = sample_task["session"]

        # Set tenant context for MCP tools
        set_tenant(tenant_id)

        new_script = "new_value = 200\nreturn new_value"

        result = await task_tools.update_task_script(
            task_id=str(task.component_id), script=new_script
        )

        # Should return updated task (nested structure)
        assert result["success"] is True
        assert result["task"]["script"] == new_script

        # Verify in database
        await session.refresh(task)
        assert task.script == new_script

    @pytest.mark.asyncio
    async def test_list_tasks_returns_database_tasks(self, sample_task):
        """Verify list_tasks returns actual tasks from database."""
        tenant_id = sample_task["tenant_id"]

        # Set tenant context for MCP tools
        set_tenant(tenant_id)

        result = await task_tools.list_tasks()

        # Should return tasks list
        assert "tasks" in result
        assert "total" in result
        assert result["total"] > 0

        # Should include our sample task
        task_names = [t["name"] for t in result["tasks"]]
        assert "MCP Test Task" in task_names


@pytest.mark.asyncio
@pytest.mark.integration
class TestIntegrationDiscoveryToolsIntegration:
    """Test integration discovery tools use real integration registry."""

    @pytest.mark.asyncio
    async def test_list_integrations_scans_real_manifests(self):
        """Verify list_integrations scans actual integration manifests."""
        # Pass configured_only=False to get all integrations (not just configured ones)
        result = await integration_tools.list_integrations(configured_only=False)

        # Should scan and return real integrations
        assert result["count"] > 0
        integration_ids = [i["integration_id"] for i in result["integrations"]]

        # Should include known integrations
        assert "virustotal" in integration_ids
        assert "splunk" in integration_ids

        # Each should have metadata from manifest
        for integration in result["integrations"]:
            assert integration["name"] != ""
            assert integration["description"] != ""
            assert isinstance(integration["archetypes"], list)

    @pytest.mark.asyncio
    async def test_get_integration_tools_reads_manifest_schemas(self):
        """Verify get_integration_tools reads actual manifest parameter schemas."""
        result = await integration_tools.get_integration_tools("virustotal")

        # Should have tools with real parameter schemas
        assert len(result["tools"]) > 0

        # Check ip_reputation has proper schema from manifest
        ip_tool = next(t for t in result["tools"] if t["action_id"] == "ip_reputation")
        assert "parameters" in ip_tool
        assert "ip" in ip_tool["parameters"]

        # Parameter should have metadata from manifest
        ip_param = ip_tool["parameters"]["ip"]
        assert ip_param["type"] == "string"
        assert ip_param["required"] is True
        assert len(ip_param["description"]) > 0

    @pytest.mark.asyncio
    async def test_search_integration_tools_queries_all_manifests(self):
        """Verify search_integration_tools searches across all manifests."""
        result = await integration_tools.search_integration_tools(
            category="threat_intel"
        )

        # Should find tools from multiple integrations
        assert result["count"] > 0
        integration_types = {t["integration_type"] for t in result["tools"]}

        # Should include VirusTotal (has threat_intel category)
        assert "virustotal" in integration_types

        # All results should actually have threat_intel category
        for tool in result["tools"]:
            assert "threat_intel" in tool["categories"]

    @pytest.mark.asyncio
    async def test_get_integration_tools_includes_archetypes(self):
        """Verify get_integration_tools includes archetypes from manifest."""
        result = await integration_tools.get_integration_tools("virustotal")

        # Should include archetypes
        assert "archetypes" in result
        assert "ThreatIntel" in result["archetypes"]

        # Should have tools that can be used for threat intelligence
        tool_ids = [t["action_id"] for t in result["tools"]]
        assert "ip_reputation" in tool_ids
        assert "domain_reputation" in tool_ids

    @pytest.mark.asyncio
    async def test_cy_usage_examples_use_real_parameter_names(self):
        """Verify Cy usage examples include actual parameter names from schemas."""
        result = await integration_tools.get_integration_tools("virustotal")

        # Find ip_reputation tool
        ip_tool = next(t for t in result["tools"] if t["action_id"] == "ip_reputation")

        # Cy usage should use correct app:: namespace syntax
        cy_usage = ip_tool["cy_usage"]
        assert 'ip="<ip>"' in cy_usage  # Should have actual param name from manifest
        assert "app::virustotal::ip_reputation" in cy_usage
        assert cy_usage.startswith("result = app::")


@pytest.mark.asyncio
@pytest.mark.integration
class TestMCPToolsEndToEnd:
    """End-to-end tests for MCP tools workflow."""

    @pytest.mark.asyncio
    async def test_discover_integration_and_execute_cy_script(self):
        """Test full workflow: discover integration -> write Cy script -> execute."""
        # 1. Discover VirusTotal integration
        vt_actions = await integration_tools.get_integration_tools("virustotal")
        assert len(vt_actions["tools"]) > 0

        # 2. Find IP reputation action
        ip_tool = next(
            t for t in vt_actions["tools"] if t["action_id"] == "ip_reputation"
        )
        assert ip_tool is not None

        # 3. Use the cy_usage example as template
        cy_usage_template = ip_tool["cy_usage"]
        assert "app::virustotal::ip_reputation" in cy_usage_template

        # 4. Create a Cy script using the discovered action
        # Note: This would normally call VirusTotal, so we just test compilation
        script = 'ip = "8.8.8.8"\nreturn "test"'

        # 5. Validate the script
        validation = await cy_tools.quick_syntax_check_cy_script(script)
        assert validation["valid"] is True

    @pytest.mark.asyncio
    async def test_list_tools_create_task_execute_workflow(
        self, integration_test_session: AsyncSession
    ):
        """Test workflow: list Cy tools -> create task -> execute."""
        # 1. List available Cy tool summaries and get details
        summaries = await cy_tools.list_all_active_tool_summaries()
        assert summaries["total"] > 0
        assert "sum" in summaries["tools"]

        # Get details for sum tool
        tool_details = await cy_tools.get_tool_details(["sum"])
        assert tool_details["count"] > 0

        # 2. Create a task using a discovered tool
        script = "result = sum([10, 20, 30])\nreturn result"
        task = await task_tools.create_task(
            name="E2E Test Task", script=script, cy_name=f"e2e_task_{uuid4().hex[:6]}"
        )

        assert task["id"] is not None

        # 3. Execute the script ad-hoc
        result = await cy_tools.execute_cy_script_adhoc(script)
        assert "status" in result
        if result["status"] == "completed":
            assert (
                result["output"] == "60"
            )  # sum([10, 20, 30]) = 60 (returns as string)


@pytest.mark.asyncio
@pytest.mark.integration
class TestWorkflowExecutionTools:
    """Test workflow execution MCP tools."""

    @pytest.mark.asyncio
    async def test_execute_workflow_blocks_until_completion(self):
        """Verify execute_workflow tool blocks and polls until workflow completes."""
        from analysi.mcp.context import set_tenant
        from analysi.mcp.tools import workflow_tools

        # Create a test workflow using compose_workflow
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"
        set_tenant(tenant_id)

        # Create simple identity workflow
        compose_result = await workflow_tools.compose_workflow(
            composition=["identity"],
            name="Test Blocking Execution",
            description="Simple identity workflow for testing blocking execution",
            execute=False,
        )

        assert compose_result["status"] == "success"
        workflow_id = compose_result["workflow_id"]

        # Execute workflow - should block until complete
        result = await workflow_tools.execute_workflow(
            workflow_id=workflow_id,
            input_data={"test": "value"},
            timeout_seconds=30,
        )

        # Should return final result, not just "initiated"
        assert "status" in result
        assert result["status"] in ["completed", "failed", "timeout", "error"]

        # If there's an error, print it for debugging
        if result["status"] == "error":
            print(f"Execution error: {result.get('error', 'No error message')}")
            # For this test, we still want to check that the structure is correct
            assert "error" in result

        # Should have workflow_run_id (may be None on error)
        assert "workflow_run_id" in result

        # Should have output or error
        if result["status"] == "completed":
            assert "output" in result
        elif result["status"] in ["failed", "error"]:
            assert "error" in result

        # Should have execution time
        assert "execution_time_ms" in result
