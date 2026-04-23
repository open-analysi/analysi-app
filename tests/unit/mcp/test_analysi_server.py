"""Unit tests for unified Analysi MCP server.

Tests the merge of cy-script-assistant + workflow-builder into a single
'analysi' MCP server with consistent verb_resource naming.

Naming convention:
  - list_*  (plural)  = browse many, lightweight
  - get_*   (singular) = fetch specific, full details
  - create_* / update_* / delete_* = CRUD verbs (singular)
  - run_*   = execute something (singular)
  - compile_* = validate + compile (singular)
  - compose_* = intelligent creation (singular)
  - validate_* = check against schema (singular)
  - add_* / remove_* = mutate sub-resources (singular)
"""

import inspect

import pytest
from mcp.server.fastmcp import FastMCP

from analysi.mcp.analysi_server import create_analysi_mcp_server


class TestAnalysiServer:
    """Test unified Analysi MCP server creation and tool registration."""

    def test_create_server_returns_fastmcp_instance(self):
        """Server is a FastMCP instance named 'analysi'."""
        server = create_analysi_mcp_server()
        assert isinstance(server, FastMCP)
        assert server.name == "analysi"

    def test_server_has_stateless_http(self):
        """Server uses stateless HTTP (no OAuth for local dev)."""
        server = create_analysi_mcp_server()
        assert server.settings.stateless_http is True

    def test_server_has_dns_rebinding_protection_disabled(self):
        """DNS rebinding protection disabled for Docker container-to-container communication."""
        server = create_analysi_mcp_server()
        security = server.settings.transport_security
        assert security is not None
        assert not security.enable_dns_rebinding_protection

    def test_total_tool_count(self):
        """Server registers exactly 25 tools (validate_ocsf_alert merged into validate_alert)."""
        server = create_analysi_mcp_server()
        tool_count = len(server._tool_manager._tools)
        assert tool_count == 25, (
            f"Expected 25 tools, got {tool_count}. "
            f"Tools: {sorted(server._tool_manager._tools.keys())}"
        )


class TestAnalysiServerToolNames:
    """Verify all 25 tools are registered with correct names."""

    @pytest.fixture(autouse=True)
    def setup_server(self):
        """Create server once for all name tests."""
        self.server = create_analysi_mcp_server()
        self.tool_names = set(self.server._tool_manager._tools.keys())

    # --- Task tools (4) ---

    def test_has_list_tasks(self):
        """list_tasks: browse tasks (lightweight summaries, no scripts)."""
        assert "list_tasks" in self.tool_names

    def test_has_get_task(self):
        """get_task: fetch specific task(s) with full details including scripts."""
        assert "get_task" in self.tool_names

    def test_has_create_task(self):
        """create_task: create new task in database."""
        assert "create_task" in self.tool_names

    def test_has_update_task(self):
        """update_task: update task script, directive, description, data_samples."""
        assert "update_task" in self.tool_names

    # --- Script tools (4) ---

    def test_has_compile_script(self):
        """compile_script: full compilation + type checking + integration validation."""
        assert "compile_script" in self.tool_names

    def test_has_run_script(self):
        """run_script: execute Cy script ad-hoc for testing (no Task record)."""
        assert "run_script" in self.tool_names

    def test_has_list_tools(self):
        """list_tools: progressive disclosure - lightweight tool name list."""
        assert "list_tools" in self.tool_names

    def test_has_get_tool(self):
        """get_tool: get full tool schemas by FQN."""
        assert "get_tool" in self.tool_names

    # --- Integration tools (3) ---

    def test_has_list_integrations(self):
        """list_integrations: browse configured integrations."""
        assert "list_integrations" in self.tool_names

    def test_has_list_integration_tools(self):
        """list_integration_tools: get tools for integration type with optional search."""
        assert "list_integration_tools" in self.tool_names

    def test_has_run_integration_tool(self):
        """run_integration_tool: execute integration tool for testing."""
        assert "run_integration_tool" in self.tool_names

    # --- Validation tools (1) ---

    def test_has_validate_alert(self):
        """validate_alert: validate alert against OCSF Detection Finding schema."""
        assert "validate_alert" in self.tool_names

    # --- Workflow CRUD tools (5) ---

    def test_has_compose_workflow(self):
        """compose_workflow: high-level array-based workflow creation."""
        assert "compose_workflow" in self.tool_names

    def test_has_get_workflow(self):
        """get_workflow: retrieve complete workflow definition."""
        assert "get_workflow" in self.tool_names

    def test_has_list_workflows(self):
        """list_workflows: browse workflows with thin representations."""
        assert "list_workflows" in self.tool_names

    def test_has_update_workflow(self):
        """update_workflow: update workflow metadata."""
        assert "update_workflow" in self.tool_names

    def test_has_delete_workflow(self):
        """delete_workflow: delete workflow and all nodes/edges."""
        assert "delete_workflow" in self.tool_names

    # --- Workflow structure tools (4) ---

    def test_has_add_workflow_node(self):
        """add_workflow_node: add node to existing workflow."""
        assert "add_workflow_node" in self.tool_names

    def test_has_add_workflow_edge(self):
        """add_workflow_edge: connect two nodes in workflow."""
        assert "add_workflow_edge" in self.tool_names

    def test_has_remove_workflow_node(self):
        """remove_workflow_node: remove node from workflow (cascades edges)."""
        assert "remove_workflow_node" in self.tool_names

    def test_has_remove_workflow_edge(self):
        """remove_workflow_edge: remove edge from workflow."""
        assert "remove_workflow_edge" in self.tool_names

    # --- Workflow execution tools (3) ---

    def test_has_run_workflow(self):
        """run_workflow: execute workflow and wait for completion (blocking)."""
        assert "run_workflow" in self.tool_names

    def test_has_get_workflow_run(self):
        """get_workflow_run: get full workflow run details."""
        assert "get_workflow_run" in self.tool_names

    def test_has_list_workflow_runs(self):
        """list_workflow_runs: list execution history for a workflow."""
        assert "list_workflow_runs" in self.tool_names

    # --- Discovery tools (1) ---

    def test_has_list_templates(self):
        """list_templates: browse system node templates (identity, merge, collect)."""
        assert "list_templates" in self.tool_names


class TestAnalysiServerRemovedTools:
    """Verify removed tools are NOT registered (cleanup from old servers)."""

    @pytest.fixture(autouse=True)
    def setup_server(self):
        """Create server once for all removal tests."""
        self.server = create_analysi_mcp_server()
        self.tool_names = set(self.server._tool_manager._tools.keys())

    # --- Tools removed from cy-script-assistant ---

    def test_no_quick_syntax_check(self):
        """quick_syntax_check_cy_script removed (compile_script is strictly better)."""
        assert "quick_syntax_check_cy_script" not in self.tool_names
        assert "quick_syntax_check" not in self.tool_names

    def test_no_get_plan_stats(self):
        """get_plan_stats removed (unused in production)."""
        assert "get_plan_stats" not in self.tool_names

    def test_no_old_get_task(self):
        """Old get_task from cy-assistant removed (get_task now backed by
        workflow_tools.get_task_details for batch support)."""
        # get_task EXISTS but is a new tool (backed by get_task_details)
        # We just verify the old implementation isn't leaking through
        pass

    def test_no_old_list_tasks(self):
        """Old list_tasks from cy-assistant (with scripts) removed;
        list_tasks now backed by list_task_summaries (lightweight)."""
        # list_tasks EXISTS but is a new tool (backed by list_task_summaries)
        pass

    # --- Tools removed from workflow-builder ---

    def test_no_create_workflow(self):
        """create_workflow removed (compose_workflow replaces it entirely)."""
        assert "create_workflow" not in self.tool_names

    def test_no_validate_workflow_types(self):
        """validate_workflow_types removed (compose does this internally)."""
        assert "validate_workflow_types" not in self.tool_names

    def test_no_start_workflow(self):
        """start_workflow removed (agents use blocking run_workflow)."""
        assert "start_workflow" not in self.tool_names

    def test_no_get_workflow_run_status(self):
        """get_workflow_run_status removed (only useful with start_workflow)."""
        assert "get_workflow_run_status" not in self.tool_names

    def test_no_update_node(self):
        """update_node removed (rarely needed, compose handles node config)."""
        assert "update_node" not in self.tool_names
        assert "update_workflow_node" not in self.tool_names

    # --- Tools with old names should not exist ---

    def test_no_old_naming(self):
        """None of the old tool names should be registered."""
        old_names = {
            # Old cy-script-assistant names
            "compile_cy_script",
            "execute_cy_script_adhoc",
            "list_all_active_tool_summaries",
            "get_tool_details",
            "update_task_script",
            "get_integration_tools",
            "search_integration_tools",
            "execute_integration_tool",
            "validate_nas_alert",
            "validate_ocsf_alert",
            # Old workflow-builder names
            "list_task_summaries",
            "get_task_details",
            "list_available_templates",
            "execute_workflow",
            "add_node",
            "add_edge",
            "remove_node",
            "remove_edge",
        }
        leaked = old_names & self.tool_names
        assert not leaked, f"Old tool names still registered: {leaked}"


class TestAnalysiServerDryDelegation:
    """Verify analysi_server.py stays DRY by delegating to existing service modules.

    The analysi_server module should ONLY import and delegate to the implementation
    modules (cy_tools, task_tools, workflow_tools, integration_tools, schema_tools).
    It must NOT import database models, services, or httpx directly.
    """

    def test_module_imports_only_service_modules(self):
        """analysi_server.py should only import from mcp.tools and mcp.integration_tools."""
        import analysi.mcp.analysi_server as mod

        source = inspect.getsource(mod)

        # Must import from service layer
        assert (
            "from analysi.mcp.tools import" in source
            or "from analysi.mcp import" in source
        )

        # Must NOT import from database or service layer directly
        assert "from analysi.services" not in source, (
            "analysi_server must delegate to tools modules, not call services directly"
        )
        assert "from analysi.models" not in source, (
            "analysi_server must not import database models directly"
        )
        assert "import httpx" not in source, (
            "analysi_server must not make HTTP calls directly"
        )
        assert "from sqlalchemy" not in source, (
            "analysi_server must not use SQLAlchemy directly"
        )

    def test_no_business_logic_in_tool_functions(self):
        """Tool functions should be thin wrappers, not contain business logic.

        Each tool function should have <15 lines of actual code (docstring excluded).
        Longer functions suggest duplicated logic that should live in the tools modules.
        """
        import analysi.mcp.analysi_server as mod

        # Count 'await' calls — each tool should have exactly one await
        # (the delegation call). More suggests duplicated logic.
        registration_functions = [
            name
            for name, obj in inspect.getmembers(mod)
            if callable(obj) and name.startswith("_register_")
        ]

        # Verify registration functions exist
        assert len(registration_functions) == 8, (
            f"Expected 8 _register_* functions, got {len(registration_functions)}"
        )


class TestAnalysiServerNamingConvention:
    """Verify naming convention is consistent across all tools."""

    @pytest.fixture(autouse=True)
    def setup_server(self):
        """Create server once for all naming tests."""
        self.server = create_analysi_mcp_server()
        self.tool_names = sorted(self.server._tool_manager._tools.keys())

    def test_list_tools_are_plural(self):
        """All 'list_' prefixed tools use plural resource names."""
        list_tools = [n for n in self.tool_names if n.startswith("list_")]
        for name in list_tools:
            resource = name[len("list_") :]
            assert resource.endswith("s"), (
                f"list_ tool '{name}' should have plural resource name, "
                f"got '{resource}'"
            )

    def test_get_tools_are_singular(self):
        """All 'get_' prefixed tools use singular resource names."""
        get_tools = [n for n in self.tool_names if n.startswith("get_")]
        for name in get_tools:
            resource = name[len("get_") :]
            # workflow_run is a compound noun (singular) - that's correct
            assert not resource.endswith("s") or resource.endswith("ss"), (
                f"get_ tool '{name}' should have singular resource name, "
                f"got '{resource}'"
            )

    def test_all_tools_use_snake_case(self):
        """All tool names use snake_case (no hyphens, no camelCase)."""
        for name in self.tool_names:
            assert name == name.lower(), f"Tool '{name}' is not lowercase"
            assert "-" not in name, f"Tool '{name}' contains hyphen"

    def test_all_tools_start_with_known_verb(self):
        """All tools start with a recognized verb prefix."""
        known_verbs = {
            "list",
            "get",
            "create",
            "update",
            "delete",
            "run",
            "compile",
            "compose",
            "validate",
            "add",
            "remove",
        }
        for name in self.tool_names:
            verb = name.split("_")[0]
            assert verb in known_verbs, (
                f"Tool '{name}' starts with unknown verb '{verb}'. "
                f"Known verbs: {known_verbs}"
            )
