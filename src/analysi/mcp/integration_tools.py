"""
MCP tools for discovering integrations and their actions for Cy script development.

These tools help users explore available integrations and their Cy-compatible tools.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from analysi.config.settings import settings
from analysi.models.integration import Integration
from analysi.services.integration_registry_service import IntegrationRegistryService


async def _get_db_session():
    """Create database session for integration MCP tools."""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    return async_session()


class IntegrationDiscoveryTools:
    """Tools for discovering integrations and their actions."""

    def __init__(self):
        """Initialize with registry service."""
        self.registry = IntegrationRegistryService.get_instance()

    async def list_integrations(self, configured_only: bool = True) -> dict:
        """
        List all available integrations with their basic information.

        Returns a list of integrations showing their ID, name, description,
        archetypes (ThreatIntel, AI, SIEM, etc.), and available tools.



        Args:
            configured_only: If True, only return actual configured integration
                            instances from the database (e.g., "splunk-local", "echo-edr-main").
                            If False, return available integration types from the framework.

        Returns:
            dict with:
                - integrations: List of integration summaries
                - count: Total number of integrations
                - filtered: Whether results were filtered by configuration

        Example:
            # Get configured integration instances (recommended for execute_integration_tool)
            configured = await list_integrations(configured_only=True)
            # Returns: [{"integration_id": "splunk-local", "integration_type": "splunk", ...}]

            # Get all available integration types from framework
            all_types = await list_integrations(configured_only=False)
            # Returns: [{"integration_id": "splunk", "integration_type": "splunk", ...}]
        """
        from analysi.mcp.context import get_tenant

        # Filter by configured integrations if requested
        if configured_only:
            tenant = get_tenant()

            # Query database for actual configured integration instances
            async with await _get_db_session() as session:
                stmt = (
                    select(Integration)
                    .where(Integration.tenant_id == tenant)
                    .where(Integration.enabled == True)  # noqa: E712
                )
                result = await session.execute(stmt)
                db_integrations = result.scalars().all()

            # Get framework manifests for metadata
            framework_integrations = {
                i["integration_type"]: i
                for i in await self.registry.list_integrations()
            }

            # Format database integrations with framework metadata
            result = {
                "integrations": [
                    {
                        "integration_id": db_int.integration_id,  # Actual DB ID like "splunk-local"
                        "integration_type": db_int.integration_type,  # Framework type like "splunk"
                        "name": db_int.name,
                        "description": db_int.description
                        or framework_integrations.get(db_int.integration_type, {}).get(
                            "description", ""
                        ),
                        "archetypes": framework_integrations.get(
                            db_int.integration_type, {}
                        ).get("archetypes", []),
                        "enabled": db_int.enabled,
                    }
                    for db_int in db_integrations
                ],
                "count": len(db_integrations),
                "filtered": True,
            }
        else:
            # Return framework integration types
            integrations = await self.registry.list_integrations()

            result = {
                "integrations": [
                    {
                        "integration_id": integration[
                            "integration_type"
                        ],  # Framework type
                        "integration_type": integration["integration_type"],
                        "name": integration["display_name"],
                        "description": integration["description"],
                        "archetypes": integration.get("archetypes", []),
                        "action_count": integration.get("action_count", 0),
                    }
                    for integration in integrations
                ],
                "count": len(integrations),
                "filtered": False,
            }

        return result

    async def get_integration_tools(self, integration_type: str) -> dict:
        """
        Get detailed information about an integration's tools.

        This shows all available tools (Cy-compatible actions) for an integration,
        including their parameters, descriptions, and usage examples.

        Args:
            integration_type: The integration TYPE (e.g., "virustotal", "splunk", "echo_edr")
                             Use the `integration_type` field from list_integrations(),
                             NOT the `integration_id` field (instance name).

        Returns:
            dict with:
                - integration_id: Integration type identifier
                - name: Display name
                - description: Integration description
                - tools: List of Cy-compatible tools with params and examples
        """
        # Use framework registry directly to get manifest
        manifest = self.registry.framework.get_integration(integration_type)

        if not manifest:
            available = [m.id for m in self.registry.framework.list_integrations()]
            return {
                "error": f"Integration type '{integration_type}' not found. Make sure you are using the integration type (e.g., 'splunk', 'virustotal'), not the instance ID (e.g., 'splunk-local').",
                "available_types": available,
            }

        # Format Cy-callable actions only (those with cy_name set)
        tools = []
        for action in manifest.actions:
            if not action.cy_name:
                continue

            # Extract params_schema from metadata
            params_schema = action.metadata.get("params_schema", {})
            params = params_schema.get("properties", {})
            required_params = params_schema.get("required", [])

            # Build parameter descriptions
            param_info = {}
            for param_name, param_spec in params.items():
                param_info[param_name] = {
                    "type": param_spec.get("type", "string"),
                    "description": param_spec.get("description", ""),
                    "required": param_name in required_params,
                }

            tools.append(
                {
                    "action_id": action.id,
                    "name": action.name or action.id,
                    "description": action.description or "",
                    "parameters": param_info,
                    "cy_usage": self._generate_cy_usage_example(
                        integration_type, action.id, params, required_params
                    ),
                }
            )

        return {
            "integration_id": manifest.id,
            "name": manifest.name,
            "description": manifest.description or "",
            "archetypes": manifest.archetypes,
            "tools": tools,
        }

    async def search_integration_tools(
        self, query: str = "", archetype: str = "", category: str = ""
    ) -> dict:
        """
        Search for integration tools by query, archetype, or category.

        Args:
            query: Search query to match against tool names/descriptions
            archetype: Filter by archetype (e.g., "ThreatIntel", "AI", "SIEM")
            category: Filter by category (e.g., "threat_intel", "enrichment")

        Returns:
            dict with matching tools and their Cy usage examples
        """
        manifests = self.registry.framework.list_integrations()
        matching_tools = []

        query_lower = query.lower() if query else ""

        for manifest in manifests:
            # Filter by archetype if specified
            if archetype and archetype not in manifest.archetypes:
                continue

            # Search Cy-callable actions (those with cy_name set)
            for action in manifest.actions:
                if not action.cy_name:
                    continue

                # Filter by category if specified
                if category and category not in (action.categories or []):
                    continue

                # Filter by query if specified
                if query_lower:
                    tool_text = (
                        f"{action.name} {action.description} "
                        f"{' '.join(action.categories or [])}"
                    ).lower()
                    if query_lower not in tool_text:
                        continue

                # Extract params for Cy example
                params_schema = action.metadata.get("params_schema", {})
                params = params_schema.get("properties", {})
                required_params = params_schema.get("required", [])

                # Add to results
                matching_tools.append(
                    {
                        "integration_type": manifest.id,  # This is the TYPE (e.g., "splunk", "virustotal")
                        "integration_name": manifest.name,
                        "action_id": action.id,
                        "name": action.name or action.id,
                        "description": action.description or "",
                        "categories": action.categories or [],
                        "cy_usage": self._generate_cy_usage_example(
                            manifest.id, action.id, params, required_params
                        ),
                    }
                )

        return {
            "tools": matching_tools,
            "count": len(matching_tools),
            "filters_applied": {
                "query": query or "none",
                "archetype": archetype or "none",
                "category": category or "none",
            },
        }

    def _generate_cy_usage_example(
        self, integration_id: str, action_id: str, params: dict, required_params: list
    ) -> str:
        """
        Generate a Cy script usage example for a tool.

        Args:
            integration_id: The integration identifier
            action_id: The action identifier
            params: Parameter schema properties
            required_params: List of required parameter names

        Returns:
            Example Cy script snippet showing how to call the action using app:: namespace
        """
        # Build example parameters using proper Cy named argument syntax
        param_parts = []
        for param_name in required_params:
            if param_name in params:
                param_type = params[param_name].get("type", "string")
                if param_type == "string":
                    # String parameters use quotes
                    param_parts.append(f'{param_name}="<{param_name}>"')
                elif param_type == "integer" or param_type == "number":
                    # Integer/number parameters are bare numbers
                    param_parts.append(f"{param_name}=0")
                elif param_type == "boolean":
                    # Boolean parameters use capitalized True/False
                    param_parts.append(f"{param_name}=True")
                elif param_type == "array":
                    # Array parameters use []
                    param_parts.append(f"{param_name}=[]")
                elif param_type == "object":
                    # Object parameters use {}
                    param_parts.append(f"{param_name}={{}}")
                else:
                    # Default to string placeholder
                    param_parts.append(f'{param_name}="<{param_name}>"')

        # Format using Cy app:: namespace syntax (not call_action!)
        params_str = ", ".join(param_parts)
        return f"result = app::{integration_id}::{action_id}({params_str})"

    async def execute_integration_tool(
        self,
        integration_id: str,
        action_id: str,
        arguments: dict,
        capture_schema: bool = False,
        timeout_seconds: int = 30,
    ) -> dict:
        """
        Execute an integration tool and return results.

        Enables testing integration tools before writing Cy scripts.
        Optionally captures JSON schema of output for schema discovery.

        IMPORTANT: This function requires the integration INSTANCE ID (e.g., "splunk-prod",
        "virustotal-main"), NOT the integration type (e.g., "splunk", "virustotal").
        Get instance IDs from list_integrations(configured_only=True).



        Args:
            integration_id: Integration INSTANCE ID (e.g., "splunk-prod", "virustotal-main", "echo-edr-1")
                           This is the `integration_id` field from list_integrations(configured_only=True),
                           NOT the `integration_type` field.
            action_id: Action identifier (e.g., "ip_reputation", "health_check")
            arguments: Tool-specific arguments
            capture_schema: If True, generate JSON schema from output
            timeout_seconds: Execution timeout in seconds

        Returns:
            dict with:
                - status: "success" | "error" | "timeout"
                - output: Raw tool output (if successful)
                - output_schema: JSON Schema (if capture_schema=True)
                - error: Error message (if failed)
                - execution_time_ms: Execution time in milliseconds

        Example:
            # Test Splunk production instance health check
            result = await execute_integration_tool(
                integration_id="splunk-prod",  # Instance ID, not type!
                action_id="health_check",
                arguments={}
            )

            # Test VirusTotal main instance with schema capture
            result = await execute_integration_tool(
                integration_id="virustotal-main",  # Instance ID, not type!
                action_id="ip_reputation",
                arguments={"ip": "8.8.8.8"},
                capture_schema=True
            )
        """
        from analysi.mcp.context import get_tenant
        from analysi.services.integration_execution_service import (
            IntegrationExecutionService,
        )

        tenant = get_tenant()

        # Create database session
        async with await _get_db_session() as session:
            service = IntegrationExecutionService(session)
            result = await service.execute_tool(
                tenant_id=tenant,
                integration_id=integration_id,
                action_id=action_id,
                arguments=arguments,
                timeout_seconds=timeout_seconds,
                capture_schema=capture_schema,
            )
            return result


# Singleton instance
_integration_tools = IntegrationDiscoveryTools()


# Exported functions for MCP server registration
async def list_integrations(configured_only: bool = True) -> dict:
    """
    List all available integrations.



    Args:
        configured_only: If True, only return integrations configured for the tenant

    Returns:
        dict with integrations list, count, and filtered flag
    """
    from analysi.mcp.context import check_mcp_permission

    check_mcp_permission("integrations", "read")
    return await _integration_tools.list_integrations(configured_only)


async def get_integration_tools(integration_type: str) -> dict:
    """
    Get tools for a specific integration type.

    Args:
        integration_type: The integration TYPE (e.g., "splunk", "virustotal")
                         from the `integration_type` field in list_integrations(),
                         NOT the instance ID like "splunk-local".

    Returns:
        dict with integration tools, parameters, and Cy usage examples
    """
    from analysi.mcp.context import check_mcp_permission

    check_mcp_permission("integrations", "read")
    return await _integration_tools.get_integration_tools(integration_type)


async def search_integration_tools(
    query: str = "", archetype: str = "", category: str = ""
) -> dict:
    """Search for integration tools."""
    from analysi.mcp.context import check_mcp_permission

    check_mcp_permission("integrations", "read")
    return await _integration_tools.search_integration_tools(query, archetype, category)


async def execute_integration_tool(
    integration_id: str,
    action_id: str,
    arguments: dict,
    capture_schema: bool = False,
    timeout_seconds: int = 30,
) -> dict:
    """
    Execute an integration tool and return results.

    IMPORTANT: Requires integration INSTANCE ID (e.g., "splunk-prod"),
    NOT the type (e.g., "splunk"). Get instance IDs from list_integrations(configured_only=True).



    Args:
        integration_id: Integration INSTANCE ID (e.g., "splunk-prod", "virustotal-main")
                       from the `integration_id` field in list_integrations(configured_only=True)
        action_id: Action identifier (e.g., "ip_reputation", "health_check")
        arguments: Tool-specific arguments
        capture_schema: If True, generate JSON schema from output
        timeout_seconds: Execution timeout in seconds

    Returns:
        dict with status, output, optional schema, error, and execution_time_ms
    """
    from analysi.mcp.context import check_mcp_permission

    check_mcp_permission("integrations", "execute")
    return await _integration_tools.execute_integration_tool(
        integration_id, action_id, arguments, capture_schema, timeout_seconds
    )
