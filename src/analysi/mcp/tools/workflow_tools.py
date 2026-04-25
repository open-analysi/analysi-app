"""
Workflow MCP Tools - AI-driven workflow composition with type validation.

This module provides MCP tools for creating and validating typed workflows.
All tools are async and return JSON-serializable dicts for AI consumption.
"""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from analysi.config.settings import settings
from analysi.constants import WorkflowConstants
from analysi.mcp.audit import log_mcp_audit
from analysi.schemas.workflow import (
    NodeKind,
    WorkflowCreate,
    WorkflowEdgeCreate,
    WorkflowNodeCreate,
)
from analysi.services.task import TaskService
from analysi.services.workflow import NodeTemplateService, WorkflowService


async def _get_db_session():
    """Create database session for workflow MCP tools."""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    return async_session()


async def create_workflow(
    name: str,
    description: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    io_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create complete workflow with nodes and edges in single operation.




    Args:
        name: Workflow name
        description: Workflow description
        nodes: List of node definitions with kind, name, task_id, etc.
        edges: List of edge definitions with source/target node IDs and ports
        io_schema: Optional input/output schema for workflow

    Returns:
        {
            "workflow_id": str,
            "validation": {
                "valid": bool,
                "errors": list[dict],
                "warnings": list[dict]
            },
            "success": bool
        }
    """
    from analysi.mcp.context import (
        check_mcp_permission,
        get_mcp_actor_user_id,
        get_tenant,
    )

    check_mcp_permission("workflows", "create")
    tenant = get_tenant()
    created_by = get_mcp_actor_user_id()

    async with await _get_db_session() as session:
        try:
            service = WorkflowService(session)

            # Build WorkflowCreate schema using Pydantic models
            # Ensure at least one node is marked as entry node (Rodos requirement)
            has_start_node = any(node.get("is_start_node", False) for node in nodes)
            if not has_start_node and len(nodes) > 0:
                # Automatically mark first node as entry node
                nodes[0]["is_start_node"] = True

            node_creates = [WorkflowNodeCreate(**node) for node in nodes]
            edge_creates = [
                WorkflowEdgeCreate(
                    edge_id=edge.get(
                        "edge_id", f"edge-{i}"
                    ),  # Generate edge_id if not provided
                    from_node_id=edge.get("source_node_id", ""),
                    to_node_id=edge.get("target_node_id", ""),
                    alias=edge.get("alias"),
                )
                for i, edge in enumerate(edges)
            ]

            # Provide default io_schema with properties (required by Rodos)
            if io_schema is None:
                io_schema = {
                    "input": {
                        "type": "object",
                        "properties": {
                            "input_data": {
                                "type": "object",
                                "description": "Workflow input",
                            }
                        },
                    },
                    "output": {"type": "object"},
                }

            # Provide default data_samples (required by Rodos)
            # Create a sample that matches the input schema with correct types
            input_properties = io_schema.get("input", {}).get("properties", {})
            default_sample: dict[str, Any] = {}
            for prop_name, prop_schema in input_properties.items():
                prop_type = prop_schema.get("type", "string")
                # Generate appropriate default values based on type
                if prop_type == "string":
                    default_sample[prop_name] = "example_value"
                elif prop_type == "number" or prop_type == "integer":
                    default_sample[prop_name] = 0
                elif prop_type == "boolean":
                    default_sample[prop_name] = False
                elif prop_type == "array":
                    default_sample[prop_name] = []
                elif prop_type == "object":
                    default_sample[prop_name] = {}
                else:
                    default_sample[prop_name] = None

            workflow_data = WorkflowCreate(
                name=name,
                description=description,
                io_schema=io_schema,
                data_samples=[default_sample] if default_sample else [{}],
                nodes=node_creates,
                edges=edge_creates,
            )

            # MCP is trusted internal code — pass created_by directly (not via schema)
            workflow_response = await service.create_workflow(
                tenant, workflow_data, audit_context=None, created_by=created_by
            )

            # Log MCP audit with full arguments
            await log_mcp_audit(
                session=session,
                tenant_id=tenant,
                action="workflow.create",
                resource_type="workflow",
                resource_id=str(workflow_response.id),
                tool_name="create_workflow",
                arguments={
                    "name": name,
                    "description": description,
                    "nodes_count": len(nodes),
                    "edges_count": len(edges),
                },
                actor_id=created_by,
            )
            await session.commit()

            # Run type validation (conditionally based on feature flag)
            validation_result = None
            if settings.ENABLE_WORKFLOW_TYPE_VALIDATION:
                try:
                    input_schema = workflow_response.io_schema.get(
                        "input", {"type": "object"}
                    )
                    validation_result = await service.validate_workflow_types(
                        tenant, workflow_response.id, input_schema
                    )
                except Exception as e:
                    validation_result = {
                        "status": "error",
                        "errors": [{"error": f"Validation failed: {e!s}"}],
                        "warnings": [],
                    }
            else:
                validation_result = {
                    "status": "skipped",
                    "errors": [],
                    "warnings": [{"message": "Type validation is disabled"}],
                }

            return {
                "workflow_id": workflow_response.id,
                "success": True,
                "validation": {
                    "valid": validation_result.get("status") == "valid",
                    "errors": validation_result.get("errors", []),
                    "warnings": validation_result.get("warnings", []),
                },
            }

        except Exception as e:
            return {
                "workflow_id": None,
                "success": False,
                "error": f"Failed to create workflow: {e!s}",
            }


async def validate_workflow_types(
    workflow_id: str, strict_input: bool = True
) -> dict[str, Any]:
    """
    Run type validation on existing workflow.

    Validates that task outputs properly connect to task inputs, catching composition
    errors before workflow execution.

    **Note**: Type validation is controlled by ENABLE_WORKFLOW_TYPE_VALIDATION flag.
    When disabled, this function returns a skipped status.



    Args:
        workflow_id: Workflow ID to validate
        strict_input: If True (default), enforce strict field validation - tasks cannot
                     access input fields that don't exist in the input schema.

                     **When to use strict_input=True (recommended):**
                     - Validating Task A → Task B connections (most workflows)
                     - Workflows with well-defined input/output contracts
                     - Catching typos in field names (e.g., "coutry" vs "country")
                     - Production workflows where errors should be caught early

                     **When to use strict_input=False:**
                     - Tasks consuming external API responses with unknown/dynamic fields
                     - Data from third-party systems without complete schemas
                     - Exploratory development where input structure isn't finalized
                     - Tasks that extract fields from unstructured data

                     **Example of strict validation:**
                     ```
                     Task 1 output: {ip_address, threat_score, country}
                     Task 2 script: score = input["threat_score"]  # ✓ Valid
                                   typo = input["threat_scroe"]   # ✗ Error (typo caught!)
                     ```

    Returns:
        {
            "valid": bool,
            "errors": list[dict],  # Type mismatches, field access errors, etc.
            "warnings": list[dict]  # Potential issues, unused outputs, etc.
        }
    """
    from analysi.mcp.context import check_mcp_permission, get_tenant

    check_mcp_permission("workflows", "read")
    tenant = get_tenant()

    # Check feature flag first
    if not settings.ENABLE_WORKFLOW_TYPE_VALIDATION:
        return {
            "valid": True,
            "errors": [],
            "warnings": [{"message": "Type validation is disabled"}],
        }

    async with await _get_db_session() as session:
        try:
            workflow_uuid = UUID(workflow_id)
            service = WorkflowService(session)

            # Get workflow first
            workflow_response = await service.get_workflow(tenant, workflow_uuid)
            if not workflow_response:
                return {
                    "valid": False,
                    "errors": [{"error": f"Workflow '{workflow_id}' not found"}],
                    "warnings": [],
                }

            # Run type validation using service method
            # get_workflow without slim=True returns WorkflowResponse
            assert hasattr(workflow_response, "io_schema")
            input_schema = workflow_response.io_schema.get("input", {"type": "object"})
            validation_result = await service.validate_workflow_types(
                tenant, workflow_uuid, input_schema, strict_input
            )

            # validation_result is a dict with status, errors, warnings
            return {
                "valid": validation_result.get("status") == "valid",
                "errors": validation_result.get("errors", []),
                "warnings": validation_result.get("warnings", []),
            }

        except ValueError:
            return {
                "valid": False,
                "errors": [{"error": f"Invalid workflow ID format: '{workflow_id}'"}],
                "warnings": [],
            }
        except Exception as e:
            return {
                "valid": False,
                "errors": [{"error": f"Validation failed: {e!s}"}],
                "warnings": [],
            }


async def add_node(
    workflow_id: str,
    node_id: str,
    kind: str,
    name: str,
    task_id: str | None = None,
    node_template_id: str | None = None,
    schemas: dict[str, Any] | None = None,
    is_start_node: bool = False,
) -> dict[str, Any]:
    """Add node to existing workflow. task_id accepts UUID or cy_name."""
    from analysi.mcp.context import check_mcp_permission, get_tenant
    from analysi.schemas.workflow import AddNodeRequest
    from analysi.services.task import TaskService

    check_mcp_permission("workflows", "update")
    tenant = get_tenant()

    async with await _get_db_session() as session:
        try:
            service = WorkflowService(session)

            # Resolve task_id: accept UUID or cy_name
            resolved_task_id: UUID | None = None
            if task_id:
                try:
                    # Try parsing as UUID first
                    resolved_task_id = UUID(task_id)
                except ValueError:
                    # Not a UUID - try resolving as cy_name
                    task_service = TaskService(session)
                    task = await task_service.get_task_by_cy_name(task_id, tenant)
                    if task:
                        resolved_task_id = task.component_id
                    else:
                        return {"success": False, "error": f"Task not found: {task_id}"}

            node_request = AddNodeRequest(
                node_id=node_id,
                kind=NodeKind(kind),
                name=name,
                is_start_node=is_start_node,
                task_id=resolved_task_id,
                node_template_id=UUID(node_template_id) if node_template_id else None,
                foreach_config=None,
                schemas=schemas
                or {"input": {"type": "object"}, "output": {"type": "object"}},
            )

            node = await service.add_node(tenant, UUID(workflow_id), node_request)

            await log_mcp_audit(
                session=session,
                tenant_id=tenant,
                action="workflow.add_node",
                resource_type="workflow",
                resource_id=workflow_id,
                tool_name="add_node",
                arguments={"node_id": node_id, "kind": kind, "name": name},
            )
            await session.commit()

            return {
                "success": True,
                "node_id": node.node_id,
                "workflow_id": workflow_id,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


async def add_edge(
    workflow_id: str,
    source_node_id: str,
    target_node_id: str,
    source_output: str = "default",
    target_input: str = "default",
    edge_id: str | None = None,
    alias: str | None = None,
) -> dict[str, Any]:
    """Add edge connecting two nodes."""
    from analysi.mcp.context import check_mcp_permission, get_tenant
    from analysi.schemas.workflow import AddEdgeRequest

    check_mcp_permission("workflows", "update")
    tenant = get_tenant()

    async with await _get_db_session() as session:
        try:
            service = WorkflowService(session)

            # Generate edge_id if not provided
            generated_edge_id = edge_id or f"edge-{source_node_id}-{target_node_id}"

            edge_request = AddEdgeRequest(
                edge_id=generated_edge_id,
                from_node_id=source_node_id,
                to_node_id=target_node_id,
                alias=alias,
            )

            edge = await service.add_edge(tenant, UUID(workflow_id), edge_request)

            await log_mcp_audit(
                session=session,
                tenant_id=tenant,
                action="workflow.add_edge",
                resource_type="workflow",
                resource_id=workflow_id,
                tool_name="add_edge",
                arguments={"from": source_node_id, "to": target_node_id},
            )
            await session.commit()

            return {
                "success": True,
                "edge_id": edge.edge_id,
                "workflow_id": workflow_id,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


async def list_task_summaries(
    function: str | None = None,
    scope: str | None = None,
    limit: int | None = None,
    categories: list[str] | None = None,
) -> dict[str, Any]:
    """
    List task summaries without scripts for efficient browsing.

    Returns lightweight summaries (no scripts). Use get_task_details()
    to fetch full details for specific tasks.

    Args:
        function: Optional function filter (e.g., "search", "reasoning", "extraction")
        scope: Optional scope filter (e.g., "processing", "input")
        limit: Max number of tasks to return. Use a small value (e.g., 5) to
               sample tasks for understanding patterns like naming conventions.
               Omit to return all tasks.
        categories: Optional categories filter (AND semantics)
    """
    from analysi.mcp.context import check_mcp_permission, get_tenant

    check_mcp_permission("tasks", "read")
    tenant = get_tenant()

    async with await _get_db_session() as session:
        try:
            service = TaskService(session)

            # Use service to list tasks
            tasks, metadata = await service.list_tasks(
                tenant_id=tenant,
                skip=0,
                limit=limit if limit is not None else 1000,
                function=function,
                scope=scope,
                status=None,  # No status filter for workflow nodes
                categories=categories,
            )

            # Convert to lightweight summaries (NO scripts)
            summaries = [
                {
                    "id": str(task.component.id),
                    "cy_name": task.component.cy_name,
                    "name": task.component.name,
                    "description": task.component.description,
                    "function": task.function,
                    "scope": task.scope,
                }
                for task in tasks
            ]

            return {
                "tasks": summaries,
                "total": metadata["total"],
                "note": "Use get_task(task_ids=[...]) to fetch scripts for selected tasks",
            }

        except Exception as e:
            return {"tasks": [], "total": 0, "error": str(e)}


async def get_task_details(
    task_ids: list[str],
) -> dict[str, Any]:
    """
    Get full task details, including scripts, for the specified tasks.

    This is the second step in progressive disclosure - after browsing summaries
    with list_task_summaries(), fetch full details only for interesting tasks.



    Args:
        task_ids: List of task IDs (UUIDs) OR cy_names to fetch details for (max 10 recommended)

    Returns:
        {
            "tasks": list[dict],  # Full task details with scripts
            "count": int
        }

    Example:
        # After reviewing summaries, get details by UUID
        details = await get_task_details(
            task_ids=["14ee7282-3910-4ef7-b378-c2c8371fef37"]
        )

        # OR get details by cy_name (preferred)
        details = await get_task_details(
            task_ids=["virustotal_ip_reputation", "abuseipdb_ip_reputation"]
        )
    """
    from analysi.mcp.context import check_mcp_permission, get_tenant

    check_mcp_permission("tasks", "read")
    tenant = get_tenant()

    async with await _get_db_session() as session:
        try:
            service = TaskService(session)

            # Fetch each task by ID or cy_name
            tasks_details = []
            for identifier in task_ids:
                try:
                    task = None

                    # Try to parse as UUID first
                    try:
                        task_uuid = UUID(identifier)
                        task = await service.get_task(task_uuid, tenant)
                    except ValueError:
                        # Not a UUID, try as cy_name
                        task = await service.get_task_by_cy_name(identifier, tenant)

                    if task:
                        tasks_details.append(
                            {
                                "id": str(task.component.id),
                                "cy_name": task.component.cy_name,
                                "name": task.component.name,
                                "description": task.component.description,
                                "function": task.function,
                                "scope": task.scope,
                                "script": task.script,
                                "directive": task.directive,
                                "data_samples": task.data_samples,
                            }
                        )
                except Exception:
                    # Task not found - skip
                    continue

            return {"tasks": tasks_details, "count": len(tasks_details)}

        except Exception as e:
            return {"tasks": [], "count": 0, "error": str(e)}


async def list_available_tasks(
    function: str | None = None,
    scope: str | None = None,
) -> dict[str, Any]:
    """
    List tasks that can be used as workflow nodes (LEGACY - use list_task_summaries instead).

    DEPRECATED: This returns all tasks with full scripts, causing context pollution.
    Use list_task_summaries() + get_task_details() for progressive disclosure.



    Args:
        function: Optional function filter (e.g., "alert_enrichment")
        scope: Optional scope filter (e.g., "tenant", "system")

    Returns:
        {
            "tasks": list[dict],  # Task summaries with id, name, function, schemas
            "total": int
        }
    """
    from analysi.mcp.context import get_tenant

    tenant = get_tenant()

    async with await _get_db_session() as session:
        try:
            service = TaskService(session)

            # Use service to list tasks (same as task_tools.py pattern)
            tasks, metadata = await service.list_tasks(
                tenant_id=tenant,
                skip=0,
                limit=1000,  # High limit for MCP tool usage
                function=function,
                scope=scope,
                status=None,  # No status filter for workflow nodes
            )

            # Convert task responses to dicts
            tasks_list = [
                {
                    "id": str(task.component.id),
                    "name": task.component.name,
                    "description": task.component.description,
                    "function": task.function,
                    "scope": task.scope,
                    "script": task.script,
                }
                for task in tasks
            ]

            return {"tasks": tasks_list, "total": metadata["total"]}

        except Exception as e:
            return {"tasks": [], "total": 0, "error": str(e)}


async def list_available_templates(
    kind: str | None = None,
) -> dict[str, Any]:
    """
    List NodeTemplates (system + tenant-specific).



    Args:
        kind: Optional kind filter (e.g., "trigger", "filter")

    Returns:
        {
            "templates": list[dict],  # Template summaries with id, name, kind, schemas
            "total": int
        }
    """
    from analysi.mcp.context import check_mcp_permission, get_tenant

    check_mcp_permission("workflows", "read")
    tenant = get_tenant()

    async with await _get_db_session() as session:
        try:
            service = NodeTemplateService(session)

            # Use service to list templates
            templates, metadata = await service.list_templates(
                tenant_id=tenant,
                skip=0,
                limit=1000,  # High limit for MCP tool usage
                enabled_only=True,  # Only show enabled templates
                name_filter=None,
            )

            # Filter by kind if specified
            if kind:
                templates = [t for t in templates if t.kind == kind]

            # Convert template responses to dicts
            templates_list = [
                {
                    "id": template.id,
                    "name": template.name,
                    "description": template.description,
                    "kind": template.kind,
                    "type": template.type,
                    "input_schema": template.input_schema,
                    "output_schema": template.output_schema,
                }
                for template in templates
            ]

            return {"templates": templates_list, "total": len(templates_list)}

        except Exception as e:
            return {"templates": [], "total": 0, "error": str(e)}


async def get_workflow(
    workflow_id: str,
    include_validation: bool = True,
    slim: bool = True,
) -> dict[str, Any]:
    """
    Retrieve complete workflow definition with optional validation.



    Args:
        workflow_id: Workflow ID
        include_validation: Whether to include type validation results
        slim: If True (default), return minimal verbosity response without timestamps,
              UUIDs, and template code. Optimized for LLM consumption.

    Returns:
        {
            "workflow": dict,  # Complete workflow definition (slim or full based on parameter)
            "validation": dict | None  # Validation results if requested
        }
    """
    from analysi.mcp.context import check_mcp_permission, get_tenant

    check_mcp_permission("workflows", "read")
    tenant = get_tenant()

    async with await _get_db_session() as session:
        try:
            workflow_uuid = UUID(workflow_id)
            service = WorkflowService(session)

            # Get workflow from service (returns dict if slim=True, WorkflowResponse if slim=False)
            workflow_response = await service.get_workflow(
                tenant, workflow_uuid, slim=slim
            )

            if not workflow_response:
                return {
                    "workflow": None,
                    "error": f"Workflow '{workflow_id}' not found for tenant '{tenant}'",
                }

            # Convert to dict if it's a Pydantic model (slim=False case)
            if hasattr(workflow_response, "model_dump"):
                workflow_dict = workflow_response.model_dump(mode="json")
            else:
                # Already a dict (slim=True case)
                workflow_dict = workflow_response

            # Optionally include validation results (controlled by feature flag)
            validation_result = None
            if include_validation:
                if settings.ENABLE_WORKFLOW_TYPE_VALIDATION:
                    try:
                        # io_schema is available on both WorkflowResponse (attr) and dict (key)
                        io_schema = (
                            workflow_response.io_schema
                            if hasattr(workflow_response, "io_schema")
                            else workflow_response.get("io_schema", {})  # type: ignore[union-attr]
                        )
                        input_schema = io_schema.get("input", {"type": "object"})
                        validation_result = await service.validate_workflow_types(
                            tenant, workflow_uuid, input_schema
                        )
                    except Exception as e:
                        # Validation error - include in response but don't fail
                        validation_result = {
                            "status": "error",
                            "error": f"Validation failed: {e!s}",
                        }
                else:
                    validation_result = {
                        "status": "skipped",
                        "errors": [],
                        "warnings": [{"message": "Type validation is disabled"}],
                    }

            return {
                "workflow": workflow_dict,
                "validation": validation_result,
            }

        except ValueError:
            return {
                "workflow": None,
                "error": f"Invalid workflow ID format: '{workflow_id}'",
            }
        except Exception as e:
            return {
                "workflow": None,
                "error": f"Failed to retrieve workflow: {e!s}",
            }


async def compose_workflow(
    composition: list[Any],
    name: str,
    description: str,
    execute: bool = False,
    data_samples: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Compose workflow from array-based format.

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
    from analysi.mcp.context import (
        check_mcp_permission,
        get_mcp_actor_user_id,
        get_tenant,
    )

    check_mcp_permission("workflows", "create")
    tenant = get_tenant()
    created_by = get_mcp_actor_user_id()

    async with await _get_db_session() as session:
        try:
            from analysi.services.workflow_composer.service import (
                WorkflowComposerService,
            )

            composer = WorkflowComposerService(session)

            # Call the compose_workflow method (no service-level audit)
            result = await composer.compose_workflow(
                composition=composition,
                workflow_name=name,
                workflow_description=description,
                tenant_id=tenant,
                created_by=str(created_by),
                execute=execute,
                audit_context=None,
                data_samples=data_samples,
            )

            # Log MCP audit with full arguments (only if workflow was created)
            if result.workflow_id:
                await log_mcp_audit(
                    session=session,
                    tenant_id=tenant,
                    action="workflow.create",
                    resource_type="workflow",
                    resource_id=str(result.workflow_id),
                    tool_name="compose_workflow",
                    arguments={
                        "name": name,
                        "description": description,
                        "composition": composition,
                        "execute": execute,
                    },
                    actor_id=created_by,
                )
                await session.commit()

            # Convert to MCP-friendly format
            response: dict[str, Any] = {
                "status": result.status,
                "plan": None,
                "workflow_id": str(result.workflow_id) if result.workflow_id else None,
                "workflow_run_id": getattr(result, "workflow_run_id", None),
                "questions": [],
                "errors": [],
                "warnings": [],
            }

            # Add plan if available
            if result.plan:
                response["plan"] = {
                    "nodes": result.plan.nodes,
                    "edges": result.plan.edges,
                    "inferred_input_schema": result.plan.inferred_input_schema,
                    "inferred_output_schema": result.plan.inferred_output_schema,
                }

            # Add questions
            if result.questions:
                response["questions"] = [
                    {
                        "question_id": q.question_id,
                        "question_type": q.question_type,
                        "message": q.message,
                        "options": q.options,
                        "suggested": q.suggested,
                        "context": q.context,
                    }
                    for q in result.questions
                ]

            # Add errors
            if result.errors:
                response["errors"] = [
                    {
                        "error_type": e.error_type,
                        "message": e.message,
                        "context": e.context,
                    }
                    for e in result.errors
                ]

            # Add warnings
            if result.warnings:
                response["warnings"] = [
                    {
                        "message": w.message,
                        "context": w.context,
                    }
                    for w in result.warnings
                ]

            return response

        except Exception as e:
            return {
                "status": "error",
                "plan": None,
                "workflow_id": None,
                "workflow_run_id": None,
                "questions": [],
                "errors": [
                    {
                        "error_type": "system_error",
                        "message": f"Failed to compose workflow: {e!s}",
                        "context": {},
                    }
                ],
                "warnings": [],
            }


async def list_workflows(limit: int | None = None) -> dict[str, Any]:
    """
    List workflows with readable compositions (cy_names and template shortcuts).

    Composition arrays contain human-readable identifiers instead of UUIDs:
    - Task nodes: cy_names (e.g., "ip_reputation_check")
    - Template nodes: shortcuts (e.g., "identity", "merge")
    - Parallel branches: nested arrays (e.g., ["task1", ["task2", "task3"], "merge"])

    Args:
        limit: Optional limit on number of workflows to return

    Returns:
        {"workflows": [{"workflow_id": str, "name": str, "description": str,
                        "composition": list, "created_by": str, "created_at": str,
                        "status": str}],
         "total": int}
    """
    from analysi.mcp.context import check_mcp_permission, get_tenant

    check_mcp_permission("workflows", "read")
    tenant = get_tenant()

    async with await _get_db_session() as session:
        try:
            from analysi.services.workflow import WorkflowService

            service = WorkflowService(session)

            # Use WorkflowService to get workflows (it handles eager loading properly)
            workflows, metadata = await service.list_workflows(
                tenant_id=tenant,
                skip=0,
                limit=limit if limit else 1000,  # Default to 1000 if no limit specified
            )

            workflow_list = []
            for workflow in workflows:
                # Reconstruct composition from nodes and edges
                # The repository should have eagerly loaded these relationships
                # Use parallel-aware reconstruction to preserve workflow structure
                composition = _reconstruct_composition_with_parallel(workflow)

                workflow_list.append(
                    {
                        "workflow_id": str(workflow.id),
                        "name": workflow.name,
                        "description": workflow.description or "",
                        "composition": composition,
                        "created_by": (
                            str(workflow.created_by) if workflow.created_by else None
                        ),
                        "created_at": workflow.created_at.isoformat(),
                        "status": workflow.status,
                    }
                )

            return {
                "workflows": workflow_list,
                "total": metadata["total"],
            }

        except Exception as e:
            # Return empty result on error
            return {
                "workflows": [],
                "total": 0,
                "error": str(e),
            }


async def execute_workflow(
    workflow_id: str,
    input_data: Any = None,
    timeout_seconds: int = 300,
    poll_interval_seconds: int = 5,
) -> dict[str, Any]:
    """
    Execute workflow and block until completion (BLOCKING operation).

    Starts workflow execution and polls until complete, failed, or timeout.

    Args:
        workflow_id: Workflow UUID to execute
        input_data: Input data for workflow (default: {})
        timeout_seconds: Maximum time to wait for completion (default: 300s = 5min)
        poll_interval_seconds: How often to poll for status (default: 5s)

    Returns:
        {"workflow_run_id": str, "status": str, "workflow_id": str,
         "output": Any | None, "error": str | None, "execution_time_ms": int}
    """
    import asyncio
    import time

    from analysi.mcp.context import check_mcp_permission, get_tenant
    from analysi.services.storage import StorageManager
    from analysi.services.workflow_execution import WorkflowExecutionService

    check_mcp_permission("workflows", "execute")

    tenant = get_tenant()
    start_time = time.time()

    # Default input_data to empty dict if not provided
    if input_data is None:
        input_data = {}

    async with await _get_db_session() as session:
        try:
            workflow_uuid = UUID(workflow_id)
            service = WorkflowExecutionService()

            # Start the workflow
            start_result = await service.start_workflow(
                session=session,
                tenant_id=tenant,
                workflow_id=workflow_uuid,
                input_data=input_data,
            )

            # Log MCP audit for workflow execution
            await log_mcp_audit(
                session=session,
                tenant_id=tenant,
                action="workflow.execute",
                resource_type="workflow",
                resource_id=workflow_id,
                tool_name="execute_workflow",
                arguments={
                    "workflow_id": workflow_id,
                    "input_data": input_data,
                    "timeout_seconds": timeout_seconds,
                },
            )

            # Commit to persist workflow_run and audit
            await session.commit()

            # workflow_run_id is already a UUID object from start_workflow
            workflow_run_id = start_result["workflow_run_id"]
            if isinstance(workflow_run_id, str):
                workflow_run_id = UUID(workflow_run_id)

            # Enqueue durable ARQ job
            from analysi.common.arq_enqueue import enqueue_or_fail
            from analysi.models.workflow_execution import WorkflowRun

            await enqueue_or_fail(
                "analysi.jobs.workflow_run_job.execute_workflow_run",
                str(workflow_run_id),
                tenant,
                model_class=WorkflowRun,
                row_id=workflow_run_id,
            )

            # Poll for completion
            elapsed: float = 0
            while elapsed < timeout_seconds:
                # Wait before polling
                await asyncio.sleep(poll_interval_seconds)
                elapsed = time.time() - start_time

                # Get status using new session
                async with await _get_db_session() as poll_session:
                    status_result = await service.get_workflow_run_status(
                        session=poll_session,
                        tenant_id=tenant,
                        workflow_run_id=workflow_run_id,
                    )

                    if "error" in status_result:
                        return {
                            "workflow_run_id": str(workflow_run_id),
                            "status": "error",
                            "workflow_id": workflow_id,
                            "error": status_result["error"],
                            "execution_time_ms": int(elapsed * 1000),
                        }

                    current_status = status_result["status"]

                    # Check if workflow finished
                    if current_status in [
                        WorkflowConstants.Status.COMPLETED,
                        WorkflowConstants.Status.FAILED,
                    ]:
                        # Get full details with output
                        workflow_run = await service.get_workflow_run_details(
                            session=poll_session,
                            tenant_id=tenant,
                            workflow_run_id=workflow_run_id,
                        )

                        if not workflow_run:
                            return {
                                "workflow_run_id": str(workflow_run_id),
                                "status": "error",
                                "workflow_id": workflow_id,
                                "error": "Workflow run not found after completion",
                                "execution_time_ms": int(elapsed * 1000),
                            }

                        # Get output from storage if completed
                        output = None
                        if (
                            current_status == WorkflowConstants.Status.COMPLETED
                            and workflow_run.output_location
                        ):
                            storage_manager = StorageManager()
                            output_content = await storage_manager.retrieve(
                                storage_type=workflow_run.output_type or "inline",
                                location=workflow_run.output_location,
                                content_type="application/json",
                            )
                            if output_content:
                                import json

                                output = json.loads(output_content)

                        return {
                            "workflow_run_id": str(workflow_run_id),
                            "status": current_status,
                            "workflow_id": workflow_id,
                            "output": output,
                            "error": (
                                workflow_run.error_message
                                if current_status == WorkflowConstants.Status.FAILED
                                else None
                            ),
                            "execution_time_ms": int(elapsed * 1000),
                        }

            # Timeout reached
            return {
                "workflow_run_id": str(workflow_run_id),
                "status": "timeout",
                "workflow_id": workflow_id,
                "error": f"Workflow execution exceeded timeout of {timeout_seconds}s",
                "execution_time_ms": int(elapsed * 1000),
            }

        except ValueError as e:
            elapsed = time.time() - start_time
            if "not found" in str(e):
                return {
                    "workflow_run_id": None,
                    "status": "error",
                    "workflow_id": workflow_id,
                    "error": f"Workflow '{workflow_id}' not found for tenant '{tenant}'",
                    "execution_time_ms": int(elapsed * 1000),
                }
            return {
                "workflow_run_id": None,
                "status": "error",
                "workflow_id": workflow_id,
                "error": str(e),
                "execution_time_ms": int(elapsed * 1000),
            }
        except Exception as e:
            elapsed = time.time() - start_time
            return {
                "workflow_run_id": None,
                "status": "error",
                "workflow_id": workflow_id,
                "error": f"Failed to execute workflow: {e!s}",
                "execution_time_ms": int(elapsed * 1000),
            }


def _get_node_identifier(node: Any) -> str:
    """
    Get human-readable identifier for a workflow node.

    - For task nodes: returns task.component.cy_name
    - For template nodes: returns shortcut (e.g., "identity", "merge", "collect")
    - For other nodes: returns node_id

    Args:
        node: WorkflowNode instance

    Returns:
        Human-readable node identifier string
    """
    # Use cy_name for task nodes
    if (
        node.kind == "task"
        and node.task is not None
        and node.task.component is not None
    ):
        # Task relationship is eagerly loaded, cy_name is on component table
        return node.task.component.cy_name

    # For template nodes, map template name back to shortcut
    if node.node_template is not None:
        template_name = node.node_template.name

        # Map system template names to shortcuts
        # Based on TEMPLATE_SHORTCUTS in workflow_composer/resolvers.py
        template_to_shortcut = {
            "system_identity": "identity",
            "system_merge": "merge",
            "system_collect": "collect",
        }

        shortcut = template_to_shortcut.get(template_name)
        if shortcut:
            return shortcut

    # Fallback to node_id for other nodes
    return node.node_id


def _reconstruct_composition(workflow: Any) -> list[str]:
    """
    Reconstruct composition array from workflow nodes and edges.

    Returns a list of node identifiers in topological order:
    - For task nodes: returns task.cy_name (e.g., "ip_reputation_check")
    - For template nodes: returns node_id (e.g., "identity", "merge", "collect")
    - For other nodes: returns node_id

    Future enhancement: reconstruct nested arrays for parallel branches.

    Args:
        workflow: Workflow model instance with eagerly loaded nodes, edges, and task relationships

    Returns:
        List of node identifiers (cy_names for tasks, node_ids for templates/others)
    """
    if not workflow.nodes:
        return []

    # Build UUID to node_id mapping
    uuid_to_node = {node.id: node for node in workflow.nodes}

    # Build adjacency map using UUIDs
    edges_from: dict[
        Any, list[Any]
    ] = {}  # Maps node UUID -> list of successor node UUIDs
    edges_to: dict[
        Any, list[Any]
    ] = {}  # Maps node UUID -> list of predecessor node UUIDs
    for edge in workflow.edges:
        if edge.from_node_uuid not in edges_from:
            edges_from[edge.from_node_uuid] = []
        edges_from[edge.from_node_uuid].append(edge.to_node_uuid)

        if edge.to_node_uuid not in edges_to:
            edges_to[edge.to_node_uuid] = []
        edges_to[edge.to_node_uuid].append(edge.from_node_uuid)

    # Find start nodes (nodes with no predecessors or marked as start)
    start_nodes = []
    for node in workflow.nodes:
        if node.is_start_node or node.id not in edges_to:
            start_nodes.append(node)

    # Simple topological sort to get linear order
    # For now, we just return node_ids in execution order
    composition: list[str] = []
    visited: set[Any] = set()

    def visit(node_uuid: Any) -> None:
        if node_uuid in visited:
            return
        visited.add(node_uuid)

        # Find the node
        node = uuid_to_node.get(node_uuid)
        if node:
            # Use helper function to get identifier (handles tasks, templates, and other nodes)
            composition.append(_get_node_identifier(node))

            # Visit successors
            if node_uuid in edges_from:
                for successor_uuid in edges_from[node_uuid]:
                    visit(successor_uuid)

    # Start from start nodes
    for start_node in start_nodes:
        visit(start_node.id)

    return composition


def _detect_branch_points(
    edges_from: dict[Any, list[Any]], uuid_to_node: dict[Any, Any]
) -> set[Any]:
    """
    Detect branch points in the workflow DAG.

    A branch point is a node with 2+ outgoing edges (fan-out).

    Args:
        edges_from: Map of node UUID -> list of successor UUIDs
        uuid_to_node: Map of UUID -> WorkflowNode

    Returns:
        Set of node UUIDs that are branch points
    """
    branch_points = set()

    for node_uuid, successors in edges_from.items():
        if len(successors) >= 2:
            branch_points.add(node_uuid)

    return branch_points


def _detect_merge_points(
    edges_to: dict[Any, list[Any]], uuid_to_node: dict[Any, Any]
) -> set[Any]:
    """
    Detect merge points in the workflow DAG.

    A merge point is a node with 2+ incoming edges (fan-in).

    Args:
        edges_to: Map of node UUID -> list of predecessor UUIDs
        uuid_to_node: Map of UUID -> WorkflowNode

    Returns:
        Set of node UUIDs that are merge points
    """
    merge_points = set()

    for node_uuid, predecessors in edges_to.items():
        if len(predecessors) >= 2:
            merge_points.add(node_uuid)

    return merge_points


def _group_parallel_branches(
    branch_point: Any,
    merge_point: Any,
    edges_from: dict[Any, list[Any]],
    edges_to: dict[Any, list[Any]],
    uuid_to_node: dict[Any, Any],
) -> list[list[str]]:
    """
    Group parallel branches between a branch point and merge point.

    Performs BFS/DFS from branch point to merge point, collecting
    all nodes in each parallel path.

    Args:
        branch_point: UUID of node where branches diverge
        merge_point: UUID of node where branches converge
        edges_from: Adjacency map (successors)
        edges_to: Reverse adjacency map (predecessors)
        uuid_to_node: Node lookup map

    Returns:
        List of parallel branches, each branch is a list of node identifiers
        Example: [["task_a", "task_b"], ["task_c"]] for 2 parallel branches
    """
    # Get immediate successors of branch point (the parallel branch heads)
    branch_heads = edges_from.get(branch_point, [])

    if not branch_heads:
        return []

    branches = []

    # For each branch head, traverse until we reach the merge point
    for head_uuid in branch_heads:
        branch_nodes = []

        # BFS to collect all nodes from head to merge point (excluding merge)
        visited = set()
        queue = [head_uuid]

        while queue:
            current = queue.pop(0)

            # Skip if already visited or if we've reached the merge point
            if current in visited or current == merge_point:
                continue

            visited.add(current)

            # Add this node to the branch
            node = uuid_to_node.get(current)
            if node:
                identifier = _get_node_identifier(node)
                branch_nodes.append(identifier)

            # Add successors to queue
            successors = edges_from.get(current, [])
            for successor in successors:
                if successor not in visited:
                    queue.append(successor)

        if branch_nodes:
            branches.append(branch_nodes)

    return branches


def _reconstruct_composition_with_parallel(workflow: Any) -> list:  # noqa: C901
    """
    Reconstruct composition array from workflow with parallel branch support.

    Returns a list that can contain:
    - Strings: node identifiers (task cy_names or template node_ids)
    - Nested lists: parallel branches

    Example outputs:
    - Linear: ["identity", "task1", "task2"]
    - Parallel: ["identity", ["task1", "task2"], "merge"]
    - Complex: ["start", ["branch1", ["nested1", "nested2"]], "merge"]

    Algorithm:
    1. Build adjacency maps and identify nodes
    2. Detect branch points (nodes with 2+ successors)
    3. Detect merge points (nodes with 2+ predecessors)
    4. Traverse DAG, creating nested arrays for parallel sections
    5. Return hierarchical composition structure

    Args:
        workflow: Workflow model instance with eagerly loaded relationships

    Returns:
        Composition list with nested arrays for parallel branches
    """
    if not workflow.nodes:
        return []

    # Build UUID to node mapping
    uuid_to_node = {node.id: node for node in workflow.nodes}

    # Build adjacency maps using UUIDs
    edges_from: dict[
        Any, list[Any]
    ] = {}  # Maps node UUID -> list of successor node UUIDs
    edges_to: dict[
        Any, list[Any]
    ] = {}  # Maps node UUID -> list of predecessor node UUIDs
    for edge in workflow.edges:
        if edge.from_node_uuid not in edges_from:
            edges_from[edge.from_node_uuid] = []
        edges_from[edge.from_node_uuid].append(edge.to_node_uuid)

        if edge.to_node_uuid not in edges_to:
            edges_to[edge.to_node_uuid] = []
        edges_to[edge.to_node_uuid].append(edge.from_node_uuid)

    # Detect branch and merge points
    branch_points = _detect_branch_points(edges_from, uuid_to_node)
    merge_points = _detect_merge_points(edges_to, uuid_to_node)

    # If no branches detected, fall back to flat composition
    if not branch_points or not merge_points:
        return _reconstruct_composition(workflow)

    # Find start nodes
    start_nodes = []
    for node in workflow.nodes:
        if node.is_start_node or node.id not in edges_to:
            start_nodes.append(node)

    # Traverse with parallel detection
    composition: list[Any] = []
    visited: set[Any] = set()

    # Map branch points to their corresponding merge points
    # For simplicity, we'll find the nearest merge point for each branch
    branch_to_merge = {}
    for branch_uuid in branch_points:
        # Find the first merge point reachable from this branch
        # Use BFS to find merge point
        queue = [branch_uuid]
        visited_search = {branch_uuid}

        while queue:
            current = queue.pop(0)
            successors = edges_from.get(current, [])

            for successor in successors:
                if successor in merge_points:
                    branch_to_merge[branch_uuid] = successor
                    break

                if successor not in visited_search:
                    visited_search.add(successor)
                    queue.append(successor)

            if branch_uuid in branch_to_merge:
                break

    def traverse_with_parallel(node_uuid: Any) -> None:
        """Traverse DAG and build composition with parallel support."""
        if node_uuid in visited:
            return

        visited.add(node_uuid)

        node = uuid_to_node.get(node_uuid)
        if not node:
            return

        # Check if this is a branch point
        if node_uuid in branch_points and node_uuid in branch_to_merge:
            # Add the branch point node itself
            composition.append(_get_node_identifier(node))

            # Group parallel branches
            merge_point = branch_to_merge[node_uuid]
            branches = _group_parallel_branches(
                branch_point=node_uuid,
                merge_point=merge_point,
                edges_from=edges_from,
                edges_to=edges_to,
                uuid_to_node=uuid_to_node,
            )

            if branches:
                # Add parallel section as nested array
                # If branches contain single elements, flatten them
                if len(branches) > 1:
                    # Multiple parallel branches
                    if all(len(branch) == 1 for branch in branches):
                        # All branches are single tasks
                        composition.append([branch[0] for branch in branches])
                    else:
                        # Some branches have multiple tasks
                        composition.append(
                            [
                                branch if len(branch) > 1 else branch[0]
                                for branch in branches
                            ]
                        )
                else:
                    # Single branch (shouldn't happen, but handle gracefully)
                    composition.extend(branches[0] if branches else [])

            # Mark all branch nodes as visited
            for successor in edges_from.get(node_uuid, []):
                visited.add(successor)
                # Also visit intermediate nodes
                queue = [successor]
                while queue:
                    current = queue.pop(0)
                    if current == merge_point:
                        break
                    visited.add(current)
                    queue.extend(edges_from.get(current, []))

            # Continue from merge point
            traverse_with_parallel(merge_point)

        else:
            # Regular node (not a branch point)
            composition.append(_get_node_identifier(node))

            # Visit successors
            successors = edges_from.get(node_uuid, [])
            for successor_uuid in successors:
                traverse_with_parallel(successor_uuid)

    # Start traversal from start nodes
    for start_node in start_nodes:
        traverse_with_parallel(start_node.id)

    return composition


async def remove_node(workflow_id: str, node_id: str) -> dict[str, Any]:
    """Remove node from workflow (cascades edges)."""
    from analysi.mcp.context import check_mcp_permission, get_tenant

    check_mcp_permission("workflows", "update")
    tenant = get_tenant()

    async with await _get_db_session() as session:
        try:
            service = WorkflowService(session)
            deleted = await service.remove_node(tenant, UUID(workflow_id), node_id)

            if deleted:
                await log_mcp_audit(
                    session=session,
                    tenant_id=tenant,
                    action="workflow.remove_node",
                    resource_type="workflow",
                    resource_id=workflow_id,
                    tool_name="remove_node",
                    arguments={"node_id": node_id},
                )
                await session.commit()

            return {"success": deleted, "node_id": node_id if deleted else None}

        except Exception as e:
            return {"success": False, "error": str(e)}


async def remove_edge(workflow_id: str, edge_id: str) -> dict[str, Any]:
    """Remove edge from workflow."""
    from analysi.mcp.context import check_mcp_permission, get_tenant

    check_mcp_permission("workflows", "update")
    tenant = get_tenant()

    async with await _get_db_session() as session:
        try:
            service = WorkflowService(session)
            deleted = await service.remove_edge(tenant, UUID(workflow_id), edge_id)

            if deleted:
                await log_mcp_audit(
                    session=session,
                    tenant_id=tenant,
                    action="workflow.remove_edge",
                    resource_type="workflow",
                    resource_id=workflow_id,
                    tool_name="remove_edge",
                    arguments={"edge_id": edge_id},
                )
                await session.commit()

            return {"success": deleted, "edge_id": edge_id if deleted else None}

        except Exception as e:
            return {"success": False, "error": str(e)}


async def update_workflow(
    workflow_id: str,
    name: str | None = None,
    description: str | None = None,
    io_schema: dict[str, Any] | None = None,
    data_samples: list[Any] | None = None,
) -> dict[str, Any]:
    """Update workflow metadata including io_schema and data_samples."""
    from analysi.mcp.context import check_mcp_permission, get_tenant
    from analysi.schemas.workflow import WorkflowUpdate

    check_mcp_permission("workflows", "update")
    tenant = get_tenant()

    async with await _get_db_session() as session:
        try:
            service = WorkflowService(session)

            update_data = WorkflowUpdate(
                name=name,
                description=description,
                io_schema=io_schema,
                data_samples=data_samples,
            )

            workflow = await service.update_workflow_metadata(
                tenant, UUID(workflow_id), update_data
            )

            await log_mcp_audit(
                session=session,
                tenant_id=tenant,
                action="workflow.update",
                resource_type="workflow",
                resource_id=workflow_id,
                tool_name="update_workflow",
                arguments={
                    "name": name,
                    "description": description,
                    "io_schema": io_schema,
                    "data_samples": data_samples,
                },
            )
            await session.commit()

            return {
                "success": True,
                "workflow_id": str(workflow.id),
                "name": workflow.name,
                "description": workflow.description,
                "io_schema": workflow.io_schema,
                "data_samples": workflow.data_samples,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


async def update_node(
    workflow_id: str,
    node_id: str,
    name: str | None = None,
    schemas: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update node properties."""
    from analysi.mcp.context import check_mcp_permission, get_tenant
    from analysi.schemas.workflow import WorkflowNodeUpdate

    check_mcp_permission("workflows", "update")
    tenant = get_tenant()

    async with await _get_db_session() as session:
        try:
            service = WorkflowService(session)

            update_data = WorkflowNodeUpdate(name=name, schemas=schemas)

            node = await service.update_node(
                tenant, UUID(workflow_id), node_id, update_data
            )

            await log_mcp_audit(
                session=session,
                tenant_id=tenant,
                action="workflow.update_node",
                resource_type="workflow",
                resource_id=workflow_id,
                tool_name="update_node",
                arguments={"node_id": node_id, "name": name},
            )
            await session.commit()

            return {
                "success": True,
                "node_id": node.node_id,
                "name": node.name,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


async def delete_workflow(workflow_id: str) -> dict[str, Any]:
    """Delete workflow."""
    from analysi.mcp.context import check_mcp_permission, get_tenant

    check_mcp_permission("workflows", "delete")
    tenant = get_tenant()

    async with await _get_db_session() as session:
        try:
            service = WorkflowService(session)
            deleted = await service.delete_workflow(tenant, UUID(workflow_id))

            if deleted:
                await log_mcp_audit(
                    session=session,
                    tenant_id=tenant,
                    action="workflow.delete",
                    resource_type="workflow",
                    resource_id=workflow_id,
                    tool_name="delete_workflow",
                    arguments={},
                )
                await session.commit()

            return {"success": deleted, "workflow_id": workflow_id if deleted else None}

        except Exception as e:
            return {"success": False, "error": str(e)}


async def start_workflow(
    workflow_id: str,
    input_data: Any = None,
) -> dict[str, Any]:
    """Start workflow execution (non-blocking, returns immediately)."""
    from analysi.mcp.context import check_mcp_permission, get_tenant
    from analysi.services.workflow_execution import WorkflowExecutionService

    check_mcp_permission("workflows", "execute")
    tenant = get_tenant()

    if input_data is None:
        input_data = {}

    async with await _get_db_session() as session:
        try:
            service = WorkflowExecutionService()

            start_result = await service.start_workflow(
                session=session,
                tenant_id=tenant,
                workflow_id=UUID(workflow_id),
                input_data=input_data,
            )

            await log_mcp_audit(
                session=session,
                tenant_id=tenant,
                action="workflow.start",
                resource_type="workflow",
                resource_id=workflow_id,
                tool_name="start_workflow",
                arguments={"input_keys": list(input_data.keys()) if input_data else []},
            )
            await session.commit()

            # Enqueue durable ARQ job
            from analysi.common.arq_enqueue import enqueue_or_fail
            from analysi.models.workflow_execution import WorkflowRun

            workflow_run_id = start_result["workflow_run_id"]
            await enqueue_or_fail(
                "analysi.jobs.workflow_run_job.execute_workflow_run",
                str(workflow_run_id),
                tenant,
                model_class=WorkflowRun,
                row_id=workflow_run_id,
            )

            return {
                "success": True,
                "workflow_run_id": str(workflow_run_id),
                "workflow_id": workflow_id,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}


async def get_workflow_run_status(workflow_run_id: str) -> dict[str, Any]:
    """Get lightweight status of workflow run."""
    from analysi.mcp.context import check_mcp_permission, get_tenant
    from analysi.services.workflow_execution import WorkflowExecutionService

    check_mcp_permission("workflows", "read")
    tenant = get_tenant()

    async with await _get_db_session() as session:
        try:
            service = WorkflowExecutionService()

            result = await service.get_workflow_run_status(
                session=session,
                tenant_id=tenant,
                workflow_run_id=UUID(workflow_run_id),
            )

            return result

        except Exception as e:
            return {"error": str(e)}


async def get_workflow_run(workflow_run_id: str) -> dict[str, Any]:
    """Get full workflow run details."""
    from analysi.mcp.context import check_mcp_permission, get_tenant
    from analysi.services.workflow_execution import WorkflowExecutionService

    check_mcp_permission("workflows", "read")
    tenant = get_tenant()

    async with await _get_db_session() as session:
        try:
            service = WorkflowExecutionService()

            workflow_run = await service.get_workflow_run_details(
                session=session,
                tenant_id=tenant,
                workflow_run_id=UUID(workflow_run_id),
            )

            if not workflow_run:
                return {"error": f"Workflow run {workflow_run_id} not found"}

            return {
                "workflow_run_id": str(workflow_run.id),
                "workflow_id": str(workflow_run.workflow_id),
                "status": workflow_run.status,
                "created_at": (
                    workflow_run.created_at.isoformat()
                    if workflow_run.created_at
                    else None
                ),
                "started_at": (
                    workflow_run.started_at.isoformat()
                    if workflow_run.started_at
                    else None
                ),
                "completed_at": (
                    workflow_run.completed_at.isoformat()
                    if workflow_run.completed_at
                    else None
                ),
                "error_message": workflow_run.error_message,
            }

        except Exception as e:
            return {"error": str(e)}


async def list_workflow_runs(
    workflow_id: str,
    limit: int = 20,
) -> dict[str, Any]:
    """List execution history for a workflow."""
    from analysi.mcp.context import check_mcp_permission, get_tenant
    from analysi.services.workflow_execution import WorkflowExecutionService

    check_mcp_permission("workflows", "read")
    tenant = get_tenant()

    async with await _get_db_session() as session:
        try:
            service = WorkflowExecutionService()

            runs = await service.list_workflow_runs(
                session=session,
                tenant_id=tenant,
                workflow_id=UUID(workflow_id),
                limit=limit,
            )

            return {
                "runs": [
                    {
                        "workflow_run_id": str(run.id),
                        "status": run.status,
                        "created_at": (
                            run.created_at.isoformat() if run.created_at else None
                        ),
                    }
                    for run in runs
                ],
                "total": len(runs),
            }

        except Exception as e:
            return {"runs": [], "total": 0, "error": str(e)}
