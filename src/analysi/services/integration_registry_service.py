"""
Integration registry service — lists available integration types and their actions.

Uses framework manifest scanning. All actions are unified — no connector/tool distinction.
"""

from typing import Any

from analysi.config.logging import get_logger
from analysi.integrations.framework.registry import (
    get_registry,
)

logger = get_logger(__name__)


class IntegrationRegistryService:
    """Integration registry backed by framework manifest scanning."""

    _instance: "IntegrationRegistryService | None" = None

    def __init__(self):
        """Initialize registry service with cached framework backend."""
        self.framework = get_registry()

    @classmethod
    def get_instance(cls) -> "IntegrationRegistryService":
        """Return a cached singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def list_integrations(self) -> list[dict[str, Any]]:
        """List all available integration types with action counts."""
        result = []
        for manifest in self.framework.list_integrations():
            result.append(
                {
                    "integration_type": manifest.id,
                    "display_name": manifest.name,
                    "description": manifest.description or "",
                    "action_count": len(manifest.actions),
                    "archetypes": manifest.archetypes,
                    "priority": manifest.priority,
                    "integration_id_config": manifest.integration_id_config,
                    "requires_credentials": manifest.requires_credentials,
                }
            )
        return result

    async def get_integration(self, integration_type: str) -> dict[str, Any] | None:
        """Get detailed information about a specific integration type."""
        manifest = self.framework.get_integration(integration_type)
        if not manifest:
            return None

        actions = [
            {
                "action_id": action.id,
                "name": action.name or action.id.replace("_", " ").title(),
                "description": action.description or "",
                "categories": action.categories or [],
                "cy_name": action.cy_name,
                "enabled": action.enabled,
                "params_schema": action.metadata.get(
                    "params_schema", {"type": "object", "properties": {}}
                ),
                "result_schema": action.metadata.get(
                    "result_schema", {"type": "object"}
                ),
            }
            for action in manifest.actions
        ]

        return {
            "integration_type": manifest.id,
            "display_name": manifest.name,
            "description": manifest.description or "",
            "credential_schema": manifest.credential_schema
            or {"type": "object", "properties": {}},
            "settings_schema": manifest.settings_schema
            or {"type": "object", "properties": {}},
            "integration_id_config": manifest.integration_id_config,
            "requires_credentials": manifest.requires_credentials,
            "archetypes": manifest.archetypes,
            "priority": manifest.priority,
            "archetype_mappings": manifest.archetype_mappings,
            "actions": actions,
        }

    def validate_integration_settings(
        self, integration_type: str, settings: dict
    ) -> tuple[bool, str]:
        """Validate integration settings using Pydantic models (if available).

        For Naxos framework integrations, returns True (validation via manifest schema).
        """
        try:
            from analysi.schemas.integration_settings import (
                validate_integration_settings,
            )

            # Returns None for Naxos framework integrations
            validate_integration_settings(integration_type, settings)
            return True, ""
        except ValueError as e:
            return False, str(e)
        except Exception as e:
            # Fallback for any other errors
            return False, f"Settings validation failed: {e!s}"

    async def register_tools_in_ku_api(self, session, tenant_id: str) -> int:
        """
        Register all framework tool actions as KU Tools.

        Scans all integration manifests and creates KU Tool entries for tool-type actions.
        This makes framework tools discoverable by Cy scripts.

        Args:
            session: Database session
            tenant_id: Tenant to register tools for

        Returns:
            Number of tools registered
        """
        from analysi.repositories.knowledge_unit import KnowledgeUnitRepository

        ku_repo = KnowledgeUnitRepository(session)
        registered_count = 0

        # Get all manifests
        manifests = self.framework.list_integrations()

        for manifest in manifests:
            # Find actions with cy_name set (Cy-callable tools)
            tool_actions = [action for action in manifest.actions if action.cy_name]

            for tool_def in tool_actions:
                # Create unique tool name: integration_type + tool_id
                tool_name = f"{manifest.id}::{tool_def.id}"

                # Check if already exists
                existing = await ku_repo.get_tool_by_name(tenant_id, tool_name)
                if existing:
                    logger.info("tool_already_registered_skipping", tool_name=tool_name)
                    continue

                # Create KU Tool
                await ku_repo.create_tool_ku(
                    tenant_id=tenant_id,
                    name=tool_name,
                    description=tool_def.description
                    or f"{manifest.name} - {tool_def.name}",
                    tool_type="app",  # Framework integration tools are type "app"
                    categories=tool_def.categories or [],
                    status="enabled",
                    input_schema=tool_def.metadata.get("params_schema", {}),
                    output_schema=tool_def.metadata.get("result_schema", {}),
                )
                registered_count += 1
                logger.info("registered_framework_tool", tool_name=tool_name)

        return registered_count
