"""
Unified Analysi MCP Server.

Single MCP server replacing cy-script-assistant + workflow-builder with
25 tools following consistent verb_resource naming:

  list_*  (plural)   = browse many, lightweight
  get_*   (singular) = fetch specific, full details
  create/update/delete = CRUD (singular)
  run_*   = execute something
  compile/compose/validate = specialized verbs
  add_*/remove_* = mutate sub-resources
"""

import time
from collections.abc import Sequence
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from analysi.config.logging import get_logger
from analysi.mcp import integration_tools
from analysi.mcp.rate_limit import check_mcp_rate_limit
from analysi.mcp.tools import cy_tools, schema_tools, task_tools, workflow_tools

logger = get_logger(__name__)

# Disable DNS rebinding protection for embedded servers.
# MCP 1.26.0 auto-enables this for localhost, which blocks Docker
# container-to-container requests (Host: api:8000) with HTTP 421.
# Since these servers are embedded in FastAPI, our middleware handles security.
_NO_DNS_REBINDING_PROTECTION = TransportSecuritySettings(
    enable_dns_rebinding_protection=False
)


def create_analysi_mcp_server() -> FastMCP:
    """Create unified Analysi MCP server with 25 tools.

    Merges cy-script-assistant (task/script/integration tools) and
    workflow-builder (workflow composition/execution tools) into a single
    server with consistent naming.

    Returns:
        Configured FastMCP Server instance
    """
    server = FastMCP(
        "analysi",
        stateless_http=True,
        streamable_http_path="/",
        transport_security=_NO_DNS_REBINDING_PROTECTION,
    )

    _register_task_tools(server)
    _register_script_tools(server)
    _register_integration_tools(server)
    _register_validation_tools(server)
    _register_workflow_crud_tools(server)
    _register_workflow_structure_tools(server)
    _register_workflow_execution_tools(server)
    _register_discovery_tools(server)

    _install_tool_call_logging(server)

    return server


def _install_tool_call_logging(server: FastMCP) -> None:
    """Wrap server.call_tool to log every MCP tool invocation.

    Mirrors the REST middleware pattern: tool_call_start, tool_call_complete,
    tool_call_error with timing information.
    """
    original_call_tool = server.call_tool
    mcp_logger = logger.bind(api="mcp")

    async def logged_call_tool(
        name: str, arguments: dict[str, Any]
    ) -> Sequence | dict[str, Any]:
        # Summarise arguments for logging (avoid dumping large scripts/data)
        arg_keys = list(arguments.keys()) if arguments else []

        mcp_logger.info("tool_call_start", tool=name, arg_keys=arg_keys)

        start = time.time()
        try:
            result = await original_call_tool(name, arguments)
            elapsed = round(time.time() - start, 4)

            mcp_logger.info("tool_call_complete", tool=name, execution_time=elapsed)
            return result
        except Exception:
            elapsed = round(time.time() - start, 4)
            mcp_logger.error(
                "tool_call_error",
                tool=name,
                execution_time=elapsed,
                exc_info=True,
            )
            raise

    server.call_tool = logged_call_tool  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Task tools (4): list_tasks, get_task, create_task, update_task
# ---------------------------------------------------------------------------


def _register_task_tools(server: FastMCP) -> None:
    """Register task CRUD tools (4 tools)."""

    @server.tool()
    async def list_tasks(
        function: str | None = None,
        scope: str | None = None,
        limit: int | None = None,
        categories: list[str] | None = None,
    ) -> dict:
        """List task summaries without scripts for efficient browsing.

        Returns lightweight summaries (no scripts). Use get_task()
        to fetch full details for specific tasks.

        Args:
            function: Optional function filter (e.g., "search", "reasoning")
            scope: Optional scope filter (e.g., "processing", "input")
            limit: Max number of tasks to return. Use a small value (e.g., 5)
                   to sample tasks for understanding patterns. Omit to return all.
            categories: Optional categories filter (AND semantics)
        """
        return await workflow_tools.list_task_summaries(
            function=function, scope=scope, limit=limit, categories=categories
        )

    @server.tool()
    async def get_task(task_ids: list[str]) -> dict:
        """Get full task details, including scripts, for the specified tasks.

        Use after browsing with list_tasks() to get full details only for
        tasks you need. Accepts both UUIDs and cy_names.

        Args:
            task_ids: List of task IDs (UUIDs) or cy_names (max 10 recommended)

        Returns:
            Full task details including scripts for selected tasks
        """
        return await workflow_tools.get_task_details(task_ids=task_ids)

    @server.tool()
    async def create_task(
        name: str,
        script: str,
        description: str | None = None,
        cy_name: str | None = None,
        app: str = "default",
        status: str = "enabled",
        visible: bool = False,
        system_only: bool = False,
        categories: list[str] | None = None,
        tags: list[str] | None = None,
        directive: str | None = None,
        function: str | None = None,
        scope: str | None = None,
        mode: str = "saved",
        llm_config: dict | None = None,
        data_samples: list | None = None,
    ) -> dict:
        """Create new task with Cy script.

        Supports all task fields including component metadata (app, status,
        visible, categories), AI configuration (directive, llm_config), and
        test data (data_samples).
        """
        return await task_tools.create_task(
            name=name,
            script=script,
            description=description,
            cy_name=cy_name,
            app=app,
            status=status,
            visible=visible,
            system_only=system_only,
            categories=categories,
            tags=tags,
            directive=directive,
            function=function,
            scope=scope,
            mode=mode,
            llm_config=llm_config,
            data_samples=data_samples,
        )

    @server.tool()
    async def update_task(
        task_id: str,
        script: str,
        data_samples: list | None = None,
        directive: str | None = None,
        description: str | None = None,
    ) -> dict:
        """Update task's Cy script, directive, description, or data_samples.

        Args:
            task_id: Task UUID (component_id)
            script: New Cy script content
            data_samples: Optional updated test data samples
            directive: Optional updated system directive for LLM calls
            description: Optional updated task description
        """
        return await task_tools.update_task_script(
            task_id,
            script,
            data_samples=data_samples,
            directive=directive,
            description=description,
        )


# ---------------------------------------------------------------------------
# Script tools (4): compile_script, run_script, list_tools, get_tool
# ---------------------------------------------------------------------------


def _register_script_tools(server: FastMCP) -> None:
    """Register Cy script tools (4 tools)."""

    @server.tool()
    async def compile_script(script: str) -> dict:
        """Compile Cy script to execution plan and validate.

        Full compilation with type checking and integration tool schema
        validation. Loads integration tool schemas from database.

        Args:
            script: Cy script source code
        """
        return await cy_tools.compile_cy_script(script)

    @server.tool()
    async def run_script(script: str, input_data: dict | None = None) -> dict:
        """Execute Cy script as ad-hoc task for testing (no Task record created).

        Args:
            script: Cy script source code
            input_data: Optional test input data
        """
        await check_mcp_rate_limit("run_script")
        return await cy_tools.execute_cy_script_adhoc(script, input_data=input_data)

    @server.tool()
    async def list_tools() -> dict:
        """List all active tool FQNs for progressive disclosure.

        Returns lightweight list of tool names only (native + configured
        integrations). Use get_tool() to fetch full information for
        selected tools.
        """
        return await cy_tools.list_all_active_tool_summaries()

    @server.tool()
    async def get_tool(tool_fqns: list[str]) -> dict:
        """Get detailed information for selected tools by their FQNs.

        Use after browsing with list_tools().

        Args:
            tool_fqns: List of tool FQNs (e.g., ["llm_run", "app::virustotal::ip_reputation"])
        """
        return await cy_tools.get_tool_details(tool_fqns)


# ---------------------------------------------------------------------------
# Integration tools (3): list_integrations, list_integration_tools,
#                         run_integration_tool
# ---------------------------------------------------------------------------


def _register_integration_tools(server: FastMCP) -> None:
    """Register integration discovery tools (3 tools).

    Merges old get_integration_tools + search_integration_tools into single
    list_integration_tools with optional filter params.
    """

    @server.tool()
    async def list_integrations(configured_only: bool = True) -> dict:
        """List available integrations with basic metadata.

        Args:
            configured_only: If True (default), only return integrations
                            configured for the tenant. Reduces results from
                            ~36 to ~5-10. Set False to see all available.

        Returns:
            Integrations list with count and filtered flag
        """
        return await integration_tools.list_integrations(configured_only)

    @server.tool()
    async def list_integration_tools(
        integration_type: str | None = None,
        query: str = "",
        category: str = "",
    ) -> dict:
        """List tools available for integrations.

        Two modes:
        - By type: Pass integration_type to get all tools for that integration
          (e.g., integration_type="virustotal" returns ip_reputation, domain_reputation, etc.)
        - By search: Pass query and/or category to search across all integration tools

        Args:
            integration_type: Integration TYPE (e.g., "splunk", "virustotal").
                            NOT instance ID like "splunk-local".
            query: Search query to match against tool names/descriptions
            category: Filter by category (e.g., "threat_intel", "enrichment")

        Returns:
            Integration tools with parameters, descriptions, and Cy usage examples
        """
        if integration_type:
            return await integration_tools.get_integration_tools(integration_type)
        return await integration_tools.search_integration_tools(
            query=query, archetype="", category=category
        )

    @server.tool()
    async def run_integration_tool(
        integration_id: str,
        action_id: str,
        arguments: dict,
        capture_schema: bool = False,
        timeout_seconds: int = 30,
    ) -> dict:
        """Execute an integration tool and return results.

        For testing integration tools before writing Cy scripts.

        IMPORTANT: Requires integration INSTANCE ID (e.g., "splunk-prod"),
        NOT the type. Use list_integrations(configured_only=True) to get IDs.

        Args:
            integration_id: Integration INSTANCE ID (e.g., "splunk-prod")
            action_id: Action identifier (e.g., "ip_reputation")
            arguments: Tool-specific arguments
            capture_schema: If True, generate JSON schema from output
            timeout_seconds: Execution timeout in seconds (default: 30)
        """
        await check_mcp_rate_limit("run_integration_tool")
        return await integration_tools.execute_integration_tool(
            integration_id,
            action_id,
            arguments,
            capture_schema,
            timeout_seconds,
        )


# ---------------------------------------------------------------------------
# Validation tools (1): validate_alert (OCSF Detection Finding)
# ---------------------------------------------------------------------------


def _register_validation_tools(server: FastMCP) -> None:
    """Register schema validation tools (1 tool)."""

    @server.tool()
    async def validate_alert(alert_data: dict) -> dict:
        """Validate a JSON alert against the OCSF Detection Finding v1.8.0 schema.

        Checks for class_uid==2004, required fields (severity_id, time,
        metadata with product/version, finding_info with title/uid),
        and integer enum ranges (severity_id, disposition_id, etc.).

        OCSF is extensible -- extra fields produce warnings, not errors.

        Args:
            alert_data: Dictionary representation of an OCSF alert

        Returns:
            Validation result with valid (bool), errors, warnings,
            and alert_structure
        """
        return await schema_tools.validate_ocsf_alert(alert_data)


# ---------------------------------------------------------------------------
# Workflow CRUD tools (5): compose_workflow, get_workflow, list_workflows,
#                           update_workflow, delete_workflow
# ---------------------------------------------------------------------------


def _register_workflow_crud_tools(server: FastMCP) -> None:
    """Register workflow CRUD tools (5 tools)."""

    @server.tool()
    async def compose_workflow(
        composition: list,
        name: str,
        description: str,
        execute: bool = False,
        data_samples: list[dict] | None = None,
    ) -> dict:
        """Compose workflow from array-based format.

        Resolves cy_names to tasks, validates DAG structure and type
        compatibility, and generates questions for missing aggregation.

        Args:
            composition: Workflow steps as an ordered array. Each element is either:
                - A string: task cy_name (e.g., "enrich_ip") or built-in template
                  ("identity", "merge", "collect")
                - A nested array of strings: tasks to run in parallel

                Examples:
                    Sequential:  ["identity", "task1", "task2"]
                    Parallel:    ["identity", ["task1", "task2"], "merge", "task3"]
        """
        return await workflow_tools.compose_workflow(
            composition=composition,
            name=name,
            description=description,
            execute=execute,
            data_samples=data_samples,
        )

    @server.tool()
    async def get_workflow(workflow_id: str, include_validation: bool = True) -> dict:
        """Retrieve complete workflow definition with optional validation.

        Args:
            workflow_id: Workflow UUID
            include_validation: Whether to include type validation results
        """
        return await workflow_tools.get_workflow(
            workflow_id=workflow_id,
            include_validation=include_validation,
        )

    @server.tool()
    async def list_workflows(limit: int | None = None) -> dict:
        """List workflows with thin representations for easy discovery.

        Returns lightweight metadata including workflow_id, name, description,
        composition array, and timestamps.

        Args:
            limit: Optional limit on number of workflows to return
        """
        return await workflow_tools.list_workflows(limit=limit)

    @server.tool()
    async def update_workflow(
        workflow_id: str,
        name: str | None = None,
        description: str | None = None,
        io_schema: dict | None = None,
        data_samples: list | None = None,
    ) -> dict:
        """Update workflow metadata (name, description, io_schema, data_samples).

        Args:
            workflow_id: Workflow UUID
            name: Optional new name
            description: Optional new description
            io_schema: Optional new IO schema
            data_samples: Optional new data samples
        """
        return await workflow_tools.update_workflow(
            workflow_id=workflow_id,
            name=name,
            description=description,
            io_schema=io_schema,
            data_samples=data_samples,
        )

    @server.tool()
    async def delete_workflow(workflow_id: str) -> dict:
        """Delete workflow and all its nodes/edges.

        Args:
            workflow_id: Workflow UUID
        """
        return await workflow_tools.delete_workflow(workflow_id=workflow_id)


# ---------------------------------------------------------------------------
# Workflow structure tools (4): add_workflow_node, add_workflow_edge,
#                                remove_workflow_node, remove_workflow_edge
# ---------------------------------------------------------------------------


def _register_workflow_structure_tools(server: FastMCP) -> None:
    """Register workflow mutation tools (4 tools)."""

    @server.tool()
    async def add_workflow_node(
        workflow_id: str,
        node_label: str,
        kind: str,
        name: str,
        task_id_or_cy_name: str | None = None,
        node_template_id: str | None = None,
        schemas: dict | None = None,
        is_start_node: bool = False,
    ) -> dict:
        """Add node to existing workflow.

        Args:
            workflow_id: Workflow UUID
            node_label: Node identifier within workflow
            kind: Node kind ("task" or "transformation")
            name: Human-readable node name
            task_id_or_cy_name: Task UUID or cy_name (for task nodes)
            node_template_id: Template UUID (for transformation nodes)
            schemas: Optional node schemas
            is_start_node: Whether this is the entry node
        """
        return await workflow_tools.add_node(
            workflow_id=workflow_id,
            node_id=node_label,
            kind=kind,
            name=name,
            task_id=task_id_or_cy_name,
            node_template_id=node_template_id,
            schemas=schemas,
            is_start_node=is_start_node,
        )

    @server.tool()
    async def add_workflow_edge(
        workflow_id: str,
        from_node: str,
        to_node: str,
        source_output: str = "default",
        target_input: str = "default",
        edge_id: str | None = None,
        alias: str | None = None,
    ) -> dict:
        """Connect two nodes in a workflow.

        Args:
            workflow_id: Workflow UUID
            from_node: Source node label
            to_node: Target node label
            source_output: Source output pin name
            target_input: Target input pin name
            edge_id: Optional edge identifier
            alias: Optional edge alias
        """
        return await workflow_tools.add_edge(
            workflow_id=workflow_id,
            source_node_id=from_node,
            target_node_id=to_node,
            source_output=source_output,
            target_input=target_input,
            edge_id=edge_id,
            alias=alias,
        )

    @server.tool()
    async def remove_workflow_node(workflow_id: str, node_label: str) -> dict:
        """Remove node from workflow. Cascades to remove connected edges.

        Args:
            workflow_id: Workflow UUID
            node_label: Node identifier to remove
        """
        return await workflow_tools.remove_node(
            workflow_id=workflow_id, node_id=node_label
        )

    @server.tool()
    async def remove_workflow_edge(workflow_id: str, edge_id: str) -> dict:
        """Remove edge from workflow.

        Args:
            workflow_id: Workflow UUID
            edge_id: Edge identifier to remove
        """
        return await workflow_tools.remove_edge(
            workflow_id=workflow_id, edge_id=edge_id
        )


# ---------------------------------------------------------------------------
# Workflow execution tools (3): run_workflow, get_workflow_run,
#                                list_workflow_runs
# ---------------------------------------------------------------------------


def _register_workflow_execution_tools(server: FastMCP) -> None:
    """Register workflow execution tools (3 tools)."""

    @server.tool()
    async def run_workflow(
        workflow_id: str,
        input_data: dict | None = None,
        timeout_seconds: int = 300,
    ) -> dict:
        """Execute an existing workflow and wait for completion (BLOCKING).

        Polls until workflow completes, fails, or times out.

        Args:
            workflow_id: Workflow UUID
            input_data: Optional input data for the workflow
            timeout_seconds: Maximum wait time (default: 300s)
        """
        await check_mcp_rate_limit("run_workflow")
        return await workflow_tools.execute_workflow(
            workflow_id=workflow_id,
            input_data=input_data,
            timeout_seconds=timeout_seconds,
        )

    @server.tool()
    async def get_workflow_run(workflow_run_id: str) -> dict:
        """Get full workflow run details including node outputs.

        Args:
            workflow_run_id: Workflow run UUID
        """
        return await workflow_tools.get_workflow_run(workflow_run_id=workflow_run_id)

    @server.tool()
    async def list_workflow_runs(workflow_id: str, limit: int = 20) -> dict:
        """List execution history for a workflow.

        Args:
            workflow_id: Workflow UUID
            limit: Maximum number of runs to return (default: 20)
        """
        return await workflow_tools.list_workflow_runs(
            workflow_id=workflow_id, limit=limit
        )


# ---------------------------------------------------------------------------
# Discovery tools (1): list_templates
# ---------------------------------------------------------------------------


def _register_discovery_tools(server: FastMCP) -> None:
    """Register discovery tools (1 tool)."""

    @server.tool()
    async def list_templates(kind: str | None = None) -> dict:
        """List system node templates (identity, merge, collect).

        Args:
            kind: Optional filter by template kind
        """
        return await workflow_tools.list_available_templates(kind=kind)
