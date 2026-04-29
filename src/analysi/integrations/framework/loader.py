"""
Dynamic loader for integration actions.

Loads action implementations from integration folders.
"""

from typing import Any

from analysi.common.safe_import import UnsafeModulePathError, safe_import_module
from analysi.integrations.framework.base import IntegrationAction


class IntegrationLoader:
    """
    Dynamic loader for Integration Framework.

    Loads action implementations from integration folders.
    Classification (connector vs tool) comes from manifest, not code.
    """

    async def load_action(
        self,
        integration_id: str,
        action_id: str,
        action_metadata: dict[str, Any],
        settings: dict[str, Any],
        credentials: dict[str, Any],
        ctx: dict[str, Any] | None = None,
    ) -> IntegrationAction:
        """
        Load and instantiate an action.

        Args:
            integration_id: Integration folder name (e.g., "virustotal")
            action_id: Action identifier (e.g., "health_check", "lookup_ip")
            action_metadata: Action definition from manifest (type, purpose, etc.)
            settings: Integration settings from instance
            credentials: Decrypted credentials from Vault
            ctx: Execution context (tenant_id, job_id, run_id, etc.)

        Returns:
            IntegrationAction instance
        """
        # 1. Build module path. ``integration_id`` originates from manifest
        # registration; safe_import_module enforces an analysi.* allowlist and
        # rejects anything that isn't a well-formed dotted Python identifier,
        # so a hostile manifest cannot pivot us into arbitrary site-packages.
        module_path = (
            f"analysi.integrations.framework.integrations.{integration_id}.actions"
        )

        # 2. Import actions module
        try:
            module = safe_import_module(module_path)
        except UnsafeModulePathError as e:
            raise ValueError(
                f"Refusing to load actions for integration '{integration_id}': "
                f"invalid module path ({e})"
            ) from e
        except ImportError as e:
            raise ValueError(
                f"Failed to import actions module for integration '{integration_id}': {e!s}"
            )

        # 3. Find action class - check for explicit class name in manifest first
        if action_metadata.get("class"):
            class_name = action_metadata["class"]
        else:
            # Fall back to naming convention
            class_name = self._to_class_name(action_id)

        action_class = getattr(module, class_name, None)

        if action_class is None:
            raise ValueError(
                f"Action class '{class_name}' not found in module '{module_path}'"
            )

        # 4. Instantiate with settings, credentials, and context
        action_instance = action_class(
            integration_id=integration_id,
            action_id=action_id,
            settings=settings,
            credentials=credentials,
            ctx=ctx,
        )

        # 5. Set metadata from manifest
        action_instance._action_type = action_metadata.get("type")  # legacy compat
        action_instance._categories = action_metadata.get("categories", [])

        return action_instance

    def _to_class_name(self, action_id: str) -> str:
        """
        Convert action_id to class name.

        Examples:
            health_check → HealthCheckAction
            lookup_ip → LookupIpAction

        Args:
            action_id: Action identifier

        Returns:
            Class name
        """
        # Split by underscore, capitalize each part, add Action suffix
        parts = action_id.split("_")
        class_name = "".join(word.capitalize() for word in parts) + "Action"
        return class_name
