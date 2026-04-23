"""
Shared utility for loading Cy language tool registry from database.

This module provides a single source of truth for loading integration tool schemas
that can be used by both:
- MCP compile_cy_script tool (for validation without execution)
- Rodos type propagation (for workflow type inference)
- Task execution (for runtime tool availability)

Following DRY (Don't Repeat Yourself) principle.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysi.config.logging import get_logger
from analysi.models.component import Component
from analysi.models.knowledge_unit import KUTool, KUType


async def load_tool_registry_async(
    session: AsyncSession, tenant_id: str
) -> dict[str, Any]:
    """
    Load tool schemas for Cy: custom native and integration tools.

    Loads tools from THREE sources:
    1. Database (KUTool table) - tenant-specific configured integration tools
    2. Framework manifests - all available Naxos integration tools (echo_edr, etc.)
    3. Custom native functions - backend-specific tools (llm_run, store_artifact, etc.)

    Note: cy-language native tools (sum, len, etc.) are NOT included here because they
    use simple names that don't conform to ToolRegistry's FQN format (namespace::category::name).
    Those tools are handled separately by cy-language runtime and don't need registry validation.

    This ensures compile-time validation has access to integration and custom native tools.

    Args:
        session: Database session (async)
        tenant_id: Tenant identifier

    Returns:
        Tool registry dict mapping FQN to schema info:
        {
            "native::llm::llm_run": {"parameters": {...}, "required": ["prompt"], ...},
            "native::tools::store_artifact": {"parameters": {...}, "required": ["name", "artifact"], ...},
            "app::virustotal::ip_reputation": {
                "parameters": {"ip": {"type": "string"}},
                "required": ["ip"],
                "return_type": {"type": "object", "properties": {...}}
            },
            ...
        }

    Example usage:
        # In MCP tools
        async with await _get_db_session() as session:
            tool_registry_dict = await load_tool_registry_async(session, tenant)

        # In Rodos type propagation
        tool_registry_dict = await load_tool_registry_async(session, tenant_id)

        # Convert to ToolRegistry object for cy-language
        from cy_language.tool_signature import ToolRegistry
        tool_registry = ToolRegistry.from_dict(tool_registry_dict)
    """
    # Build tool_registry
    tool_registry = {}

    # SOURCE 1: Load tools from database (KUTool table)
    # These are tenant-specific configured tools
    stmt = (
        select(KUTool)
        .join(Component, KUTool.component_id == Component.id)
        .where(
            Component.tenant_id == tenant_id,
            Component.ku_type == KUType.TOOL,
            KUTool.tool_type == "app",
            Component.status == "enabled",
        )
    )
    result = await session.execute(stmt)
    tools = result.scalars().all()

    for tool in tools:
        # Refresh to load component relationship
        await session.refresh(tool, ["component"])

        # Tool FQN is stored in component.name (e.g., "virustotal::ip_reputation")
        # Cy expects "app::virustotal::ip_reputation"
        tool_name_parts = tool.component.name.split("::")
        if len(tool_name_parts) == 2:
            integration_type, action_id = tool_name_parts
            fqn = f"app::{integration_type}::{action_id}"
        else:
            # Skip malformed tool names
            continue

        # Extract parameters from input_schema
        input_schema = tool.input_schema or {}
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        # Build parameters dict (Cy expects param_name -> type_schema)
        parameters = {}
        for param_name, param_schema in properties.items():
            parameters[param_name] = param_schema

        # Extract return type from output_schema
        return_type = tool.output_schema or {}

        # Add to registry
        tool_registry[fqn] = {
            "description": tool.component.description or "",
            "parameters": parameters,
            "required": required,
            "return_type": return_type,
        }

    # SOURCE 2: Load tools from framework manifests (Naxos integrations)
    # These are ALL available framework tools (echo_edr, splunk, etc.)
    from analysi.services.integration_registry_service import (
        IntegrationRegistryService,
    )

    registry_service = IntegrationRegistryService.get_instance()
    framework = registry_service.framework
    manifests = framework.list_integrations()

    logger = get_logger(__name__)

    # Pre-compute native tool short names to detect collisions.
    # AI archetype integrations (anthropic, openai, gemini) expose llm_run/llm_chat
    # as framework tools, but native::llm::llm_run already handles them.
    # Registering both causes AmbiguousToolError in the Cy compiler.
    from analysi.services.native_tools_registry import get_native_short_names

    native_short_names = get_native_short_names()

    for manifest in manifests:
        # Find tool actions in manifest
        for action in manifest.actions:
            if not action.cy_name:
                continue

            # Build FQN: app::integration_id::action_id
            fqn = f"app::{manifest.id}::{action.id}"

            # Skip framework tools whose short name collides with a native function.
            # Native functions are the canonical Cy-callable path; framework tools
            # are accessible via the REST API tool-execution endpoint.
            short_name = action.cy_name or action.id
            if short_name in native_short_names:
                logger.debug(
                    "skipping_framework_tool_native_collision",
                    fqn=fqn,
                    short_name=short_name,
                )
                continue

            # Framework manifests take precedence over database for framework tools
            # Database registration may have stale or incomplete schemas
            # Manifest is the source of truth for framework integrations

            # Extract parameter schema from action metadata
            params_schema = action.metadata.get("params_schema", {})
            properties = params_schema.get("properties", {})
            required = params_schema.get("required", [])

            # Debug logging for echo_edr tools
            if manifest.id == "echo_edr":
                logger.info(
                    "framework_tool_loading",
                    manifest_id=manifest.id,
                    action_id=action.id,
                    fqn=fqn,
                    has_params_schema=params_schema is not None
                    and len(params_schema) > 0,
                    param_count=len(properties),
                    param_names=list(properties.keys()),
                    required_params=required,
                )

            # Build parameters dict (Cy expects param_name -> type_schema)
            parameters = {}
            for param_name, param_spec in properties.items():
                parameters[param_name] = param_spec

            # Extract return type from result_schema
            return_type = action.metadata.get("result_schema", {})

            # Add to registry
            tool_registry[fqn] = {
                "description": action.description or "",
                "parameters": parameters,
                "required": required,
                "return_type": return_type,
            }

    # SOURCE 3: Add custom native functions using DRY registry
    # These are runtime functions that need to be in the registry for compile-time validation
    # Instead of manually hardcoding 200+ lines, we use the native_tools_registry module
    # which extracts signatures from actual function implementations
    from analysi.services.native_tools_registry import get_native_tools_registry

    native_tools = get_native_tools_registry()
    tool_registry.update(native_tools)

    return tool_registry
