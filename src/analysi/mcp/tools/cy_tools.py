"""MCP tools for Cy script validation, compilation, and analysis."""

import asyncio

from cy_language.compiler import compile_cy_program
from cy_language.parser import Parser
from cy_language.ui.tools import default_registry

from analysi.constants import TaskConstants
from analysi.mcp.context import get_tenant
from analysi.mcp.utils.cy_helpers import load_tool_registry_for_tenant


async def quick_syntax_check_cy_script(script: str) -> dict:
    """
    Quick syntax check for Cy script.

    Only validates basic syntax - does NOT check types or if symbols/references exist.
    Use compile_cy_script() for full validation with type checking and symbol resolution.

    Args:
        script: Cy script source code

    Returns:
        {
            "valid": bool,
            "errors": list[str] | None
        }
    """
    from analysi.mcp.context import check_mcp_permission

    check_mcp_permission("tasks", "read")
    try:
        parser = Parser()
        parser.parse_only(script)
        return {"valid": True, "errors": None}
    except Exception as e:
        error_msg = str(e)
        return {"valid": False, "errors": [error_msg]}


async def compile_cy_script(script: str) -> dict:
    """
    Compile Cy script to execution plan and validate.

    Loads integration tool schemas from database to validate tool registry.


    Args:
        script: Cy script source code

    Returns:
        {
            "plan": dict | None,
            "validation_errors": list[str] | None,
            "tools_loaded": int  # Number of integration tools loaded
        }
    """
    from analysi.mcp.context import check_mcp_permission

    check_mcp_permission("tasks", "read")
    try:
        # Get tenant from request context
        tenant = get_tenant()

        # Load integration tool registry from database using DRY helper
        tool_registry_dict = await load_tool_registry_for_tenant(tenant)
        tools_loaded = len(tool_registry_dict) if tool_registry_dict else 0

        # Convert dict to ToolRegistry object (same as Rodos)
        tool_registry = None
        if tool_registry_dict:
            from cy_language.tool_signature import ToolRegistry

            tool_registry = ToolRegistry.from_dict(tool_registry_dict)

        # Use cy-language analyze_types for validation with tool registry
        # This is the same approach used by Rodos for type propagation
        from cy_language import analyze_types

        try:
            # Compile and infer types with integration tools
            inferred_schema = analyze_types(
                script,
                input_schema={"type": "object"},  # Generic input for compilation check
                tool_registry=tool_registry,
            )

            # If analyze_types succeeds, compilation was successful
            # Return a simplified plan representation
            return {
                "plan": {"compiled": True, "output_schema": inferred_schema},
                "validation_errors": [],
                "tools_loaded": tools_loaded,
            }
        except TypeError as e:
            return {
                "plan": None,
                "validation_errors": [f"Type error: {e}"],
                "tools_loaded": tools_loaded,
            }
        except SyntaxError as e:
            return {
                "plan": None,
                "validation_errors": [f"Syntax error: {e}"],
                "tools_loaded": tools_loaded,
            }

    except Exception as e:
        return {"plan": None, "validation_errors": [str(e)], "tools_loaded": 0}


async def analyze_dependencies(script: str) -> dict:
    """
    Analyze Cy script for parallelizable operations.

    Args:
        script: Cy script source code

    Returns:
        {
            "parallel_groups": list[list[str]],
            "can_parallelize": bool
        }
    """
    try:
        parser = Parser()
        ast = parser.parse_only(script)
        plan = compile_cy_program(ast)

        # Simplified analysis — return node count and structure
        node_count = len(plan.nodes)

        return {
            "parallel_groups": [[]],
            "can_parallelize": False,
            "note": "Full dependency analysis not yet available in cy-language 0.6.0",
            "node_count": node_count,
        }
    except Exception as e:
        return {"parallel_groups": [], "can_parallelize": False, "error": str(e)}


async def visualize_plan(script: str) -> dict:
    """
    Generate GraphViz visualization of execution plan.

    Args:
        script: Cy script source code

    Returns:
        {
            "graphviz": str  # DOT format
        }
    """
    try:
        parser = Parser()
        ast = parser.parse_only(script)
        plan = compile_cy_program(ast)

        # Return JSON plan representation
        import json

        plan_dict = json.loads(plan.to_json())

        return {
            "graphviz": None,
            "note": "GraphViz visualization not yet available in cy-language 0.6.0",
            "plan_json": plan_dict,
        }
    except Exception as e:
        return {"graphviz": None, "error": str(e)}


async def get_plan_stats(script: str) -> dict:
    """
    Get statistics about execution plan.

    Args:
        script: Cy script source code

    Returns:
        {
            "total_nodes": int,
            "node_types": dict[str, int]
        }
    """
    from analysi.mcp.context import check_mcp_permission

    check_mcp_permission("tasks", "read")
    try:
        parser = Parser()
        ast = parser.parse_only(script)
        plan = compile_cy_program(ast)

        # Calculate stats manually since PlanVisualizer is not exported
        total_nodes = len(plan.nodes)
        node_types: dict[str, int] = {}
        for node in plan.nodes:
            node_type = type(node).__name__
            node_types[node_type] = node_types.get(node_type, 0) + 1

        return {
            "total_nodes": total_nodes,
            "node_types": node_types,
        }
    except Exception as e:
        return {"total_nodes": 0, "node_types": {}, "error": str(e)}


async def list_all_active_tool_summaries() -> dict:
    """
    List all active tool FQNs (Fully Qualified Names) for progressive disclosure.

    Returns lightweight list of tool names only. Use get_tool_details() to fetch
    full information for selected tools.

    Combines tools from load_tool_registry_async() (custom native + integration tools)
    with cy-language native tools (sum, len, etc.) for complete tool discovery.



    Returns:
        {
            "tools": list[str],  # List of FQNs (e.g., ["sum", "len", "native::llm::llm_run", "app::virustotal::ip_reputation"])
            "total": int,
            "note": "Use get_tool_details(tool_fqns=[...]) to fetch full details for selected tools"
        }

    Example:
        # Step 1: Get lightweight list of all available tools
        summaries = await list_all_active_tool_summaries()
        # Returns: {"tools": ["sum", "len", "native::llm::llm_run", "native::tools::store_artifact", "app::virustotal::ip_reputation", ...]}

        # Step 2: Get details for interesting tools
        details = await get_tool_details(["native::llm::llm_run", "app::virustotal::ip_reputation"])
    """
    from analysi.mcp.context import check_mcp_permission

    check_mcp_permission("tasks", "read")
    try:
        tenant = get_tenant()
        tool_fqns = []

        # SOURCE 1: cy-language native tools (sum, len, str, etc.)
        # These use simple names and are always available
        base_tools = default_registry.get_tool_descriptions()
        for tool in base_tools:
            tool_fqns.append(tool["name"])

        # SOURCE 2: Custom native + integration tools from registry
        # Uses DRY helper - same source as compile_cy_script()
        tool_registry_dict = await load_tool_registry_for_tenant(tenant)

        # Add all tools from registry (native::*, app::*)
        if tool_registry_dict:
            tool_fqns.extend(tool_registry_dict.keys())

        return {
            "tools": tool_fqns,
            "total": len(tool_fqns),
            "note": "Use get_tool_details(tool_fqns=[...]) to fetch full details for selected tools",
        }
    except Exception as e:
        return {"tools": [], "total": 0, "error": str(e)}


async def get_tool_details(tool_fqns: list[str]) -> dict:
    """
    Get detailed information for selected tools by their FQNs.

    Use this after browsing summaries with list_all_active_tool_summaries() to get
    full details only for interesting tools.

    Combines cy-language native tools with tools from load_tool_registry_async()
    for complete coverage.

    Args:
        tool_fqns: List of tool FQNs to fetch details for (max 20 recommended)
                  Examples:
                  - cy-language native: "sum", "len"
                  - Custom native tools: "native::llm::llm_run", "native::tools::store_artifact"
                  - Integration tools: "app::virustotal::ip_reputation"

    Returns:
        {
            "tools": list[dict],  # Full tool details with parameters, descriptions, usage examples
            "count": int,
            "not_found": list[str]  # FQNs that weren't found
        }

    Example:
        # Get details for specific tools
        details = await get_tool_details([
            "sum",
            "native::llm::llm_run",
            "app::virustotal::ip_reputation",
            "app::splunk::spl_run"
        ])
    """
    from analysi.mcp.context import check_mcp_permission

    check_mcp_permission("tasks", "read")
    try:
        tenant = get_tenant()
        tool_details = []
        not_found = []

        # Build maps for all tool sources
        # SOURCE 1: cy-language native tools
        native_tools_map = {
            tool["name"]: tool for tool in default_registry.get_tool_descriptions()
        }

        # SOURCE 2: Custom native + integration tools from registry
        tool_registry_dict = await load_tool_registry_for_tenant(tenant)

        # Fetch details for requested tools
        for tool_fqn in tool_fqns:
            # Check if it's a cy-language native tool
            if tool_fqn in native_tools_map:
                native_tool = native_tools_map[tool_fqn]
                tool_details.append(
                    {
                        "fqn": tool_fqn,
                        "name": native_tool["name"],
                        "description": native_tool["description"],
                        "parameters": {},  # cy-language tools have simpler parameter handling
                        "usage_example": f"{native_tool['name']}()",
                        "category": "native",
                    }
                )
            # Check if it's in the tool registry (custom native or integration)
            elif tool_fqn in tool_registry_dict:
                tool_spec = tool_registry_dict[tool_fqn]

                # Extract parameter info from registry
                params = tool_spec.get("parameters", {})
                required_params = tool_spec.get("required", [])

                # Build parameter info with required flag
                param_info = {}
                for param_name, param_spec in params.items():
                    param_info[param_name] = {
                        "type": param_spec.get("type", "string"),
                        "description": param_spec.get("description", ""),
                        "required": param_name in required_params,
                    }

                # Generate usage example
                if required_params:
                    param_examples = ", ".join(f'{k}="<{k}>"' for k in required_params)
                    usage_example = f"result = {tool_fqn}({param_examples})"
                else:
                    usage_example = f"result = {tool_fqn}()"

                # Determine category from FQN
                if tool_fqn.startswith("app::"):
                    category = "integration"
                    # Extract integration name from FQN: app::virustotal::ip_reputation -> virustotal
                    integration_name = (
                        tool_fqn.split("::")[1] if "::" in tool_fqn else ""
                    )
                elif tool_fqn.startswith("native::"):
                    category = "custom_native"
                    integration_name = None
                else:
                    category = "native"
                    integration_name = None

                # Generate human-readable name from FQN
                name = tool_fqn.split("::")[-1].replace("_", " ").title()

                # Get description from tool spec (preferred) or fall back to return_type description
                description = tool_spec.get("description", "") or tool_spec.get(
                    "return_type", {}
                ).get("description", "")

                tool_detail = {
                    "fqn": tool_fqn,
                    "name": name,
                    "description": description,
                    "parameters": param_info,
                    "usage_example": usage_example,
                    "category": category,
                }

                # Add integration field for app tools
                if integration_name:
                    tool_detail["integration"] = integration_name

                tool_details.append(tool_detail)
            else:
                not_found.append(tool_fqn)

        return {
            "tools": tool_details,
            "count": len(tool_details),
            "not_found": not_found,
        }
    except Exception as e:
        return {"tools": [], "count": 0, "not_found": tool_fqns, "error": str(e)}


async def execute_cy_script_adhoc(script: str, input_data: dict | None = None) -> dict:
    """
    Execute Cy script as ad-hoc task through proper task execution service.

    Validates the script before execution and creates a task_run record in the database.

    Args:
        script: Cy script source code
        input_data: Optional input data for the script

    Returns:
        {
            "task_run_id": str,
            "status": str,
            "output": str | None,
            "error": str | None,
            "execution_time_ms": int | None
        }
    """
    import os

    from analysi.mcp.context import check_mcp_permission

    check_mcp_permission("tasks", "execute")

    try:
        # Step 1: Validate syntax only (don't check tool availability)
        # Tool validation happens at execution time when integration tools are loaded
        validation = await quick_syntax_check_cy_script(script)

        if not validation["valid"]:
            return {
                "task_run_id": None,
                "status": "failed",
                "output": None,
                "error": f"Syntax validation failed: {validation['errors']}",
                "execution_time_ms": None,
                "validation_errors": validation["errors"],
            }

        # Step 2: Execute the script (backend will validate tool availability)
        # Get API base URL from environment variables or use defaults
        backend_api_host = os.getenv("BACKEND_API_HOST", "api")
        backend_api_port = int(os.getenv("BACKEND_API_PORT", 8000))
        api_base = f"http://{backend_api_host}:{backend_api_port}"
        tenant = get_tenant()  # Use MCP context instead of environment variable

        # Call the ad-hoc execution endpoint
        from analysi.common.internal_auth import internal_auth_headers
        from analysi.common.internal_client import InternalAsyncClient

        async with InternalAsyncClient(
            timeout=30.0, headers=internal_auth_headers()
        ) as client:
            response = await client.post(
                f"{api_base}/v1/{tenant}/tasks/run",
                json={
                    "cy_script": script,
                    "input": input_data,
                    "executor_config": None,
                },
            )

            if response.status_code != 202:
                return {
                    "task_run_id": None,
                    "status": "failed",
                    "output": None,
                    "error": f"HTTP {response.status_code}: {response.text}",
                    "execution_time_ms": None,
                }

            result = response.json()
            task_run_id = result.get("trid")  # API returns "trid" for task run ID

            # Poll for completion
            # 60s allows concurrent test suites where the API event loop handles many
            # background tasks simultaneously (e.g. isolation/concurrent test groups).
            max_wait: float = 60  # seconds
            poll_interval: float = 0.5  # seconds
            elapsed: float = 0

            while elapsed < max_wait:
                status_response = await client.get(
                    f"{api_base}/v1/{tenant}/task-runs/{task_run_id}"
                )

                if status_response.status_code != 200:
                    break

                task_run = status_response.json()
                status = task_run.get("status")

                if status in [
                    TaskConstants.Status.COMPLETED,
                    TaskConstants.Status.FAILED,
                ]:
                    # Extract output from output_location if inline
                    output = (
                        task_run.get("output_location")
                        if task_run.get("output_type") == "inline"
                        else task_run.get("output")
                    )

                    # Parse duration to milliseconds if present
                    duration_str = task_run.get("duration")
                    execution_time_ms = None
                    if duration_str:
                        # Parse ISO 8601 duration PT0.637647S to milliseconds
                        import re

                        match = re.search(r"PT([\d.]+)S", duration_str)
                        if match:
                            execution_time_ms = int(float(match.group(1)) * 1000)

                    return {
                        "task_run_id": str(task_run_id),
                        "status": status,
                        "output": output,
                        "error": task_run.get(
                            "error_message"
                        ),  # Currently always None - see TODO
                        "execution_time_ms": execution_time_ms,
                    }

                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

            # Timeout
            return {
                "task_run_id": str(task_run_id),
                "status": "timeout",
                "output": None,
                "error": f"Execution timed out after {max_wait} seconds",
                "execution_time_ms": None,
            }

    except Exception as e:
        return {
            "task_run_id": None,
            "status": "error",
            "output": None,
            "error": str(e),
            "execution_time_ms": None,
        }
