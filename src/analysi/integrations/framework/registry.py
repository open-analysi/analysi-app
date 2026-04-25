"""
Integration Registry Service.

Scans integrations folder and provides discovery methods.
"""

from pathlib import Path

from analysi.config.logging import get_logger
from analysi.integrations.framework.models import IntegrationManifest, ValidationError
from analysi.integrations.framework.validators import ManifestValidator

logger = get_logger(__name__)


class IntegrationRegistryService:
    """Registry for Integrations Framework."""

    def __init__(self, integrations_path: Path | None = None):
        """
        Initialize registry.

        Args:
            integrations_path: Path to integrations folder (default: auto-detect)
        """
        self.integrations_path = integrations_path or self._default_path()
        self.registry: dict[str, IntegrationManifest] = {}
        self.validation_errors: dict[
            str, list[ValidationError]
        ] = {}  # Track all validation errors
        self.validator = ManifestValidator()
        # Auto-load manifests on init
        self._load_all_manifests()

    def _default_path(self) -> Path:
        """Get default integrations path."""
        # Resolve to src/analysi/integrations/framework/integrations/
        current_file = Path(__file__).resolve()
        return current_file.parent / "integrations"

    def _load_all_manifests(self):
        """Scan integrations folder and load manifests."""
        self.registry = {}
        self.validation_errors = {}

        if not self.integrations_path.exists():
            logger.warning(
                "integrations_path_not_found", path=str(self.integrations_path)
            )
            return

        logger.debug("loading_integrations", path=str(self.integrations_path))
        loaded_count = 0
        failed_count = 0

        # 1. Iterate through integration folders
        for integration_dir in self.integrations_path.iterdir():
            if not integration_dir.is_dir():
                continue

            # Skip hidden directories and __pycache__
            if (
                integration_dir.name.startswith(".")
                or integration_dir.name == "__pycache__"
            ):
                continue

            # 2. Load manifest.json file
            manifest_path = integration_dir / "manifest.json"
            if not manifest_path.exists():
                logger.debug("manifest_not_found", integration=integration_dir.name)
                continue

            # 3. Validate each manifest
            manifest, errors = self.validator.validate_manifest(manifest_path)

            # Categorize errors
            critical_errors = [e for e in errors if e.severity == "error"]
            warnings = [e for e in errors if e.severity == "warning"]

            # Store all validation errors for API access
            if errors:
                integration_id = manifest.id if manifest else integration_dir.name
                self.validation_errors[integration_id] = errors

            # Log validation results
            if critical_errors:
                logger.error(
                    "integration_validation_failed",
                    integration=integration_dir.name,
                    error_count=len(critical_errors),
                    warning_count=len(warnings),
                    errors=[
                        {"field": e.field, "message": e.message}
                        for e in critical_errors
                    ],
                )
                failed_count += 1
            elif warnings:
                logger.warning(
                    "integration_validation_warnings",
                    integration=manifest.id,
                    warning_count=len(warnings),
                    warnings=[
                        {"field": e.field, "message": e.message} for e in warnings
                    ],
                )

            # Only register if no critical errors
            if manifest and not critical_errors:
                # 4. Store in registry
                self.registry[manifest.id] = manifest
                logger.debug(
                    "integration_loaded",
                    integration_id=manifest.id,
                    name=manifest.name,
                    archetypes=manifest.archetypes,
                    priority=manifest.priority,
                    action_count=len(manifest.actions),
                )
                loaded_count += 1

        logger.info(
            "integration_registry_initialized",
            loaded_count=loaded_count,
            failed_count=failed_count,
            total_integrations=loaded_count + failed_count,
        )

    def get_integration(self, integration_id: str) -> IntegrationManifest | None:
        """
        Get integration by ID.

        Args:
            integration_id: Integration identifier

        Returns:
            Manifest or None if not found
        """
        return self.registry.get(integration_id)

    def list_integrations(self) -> list[IntegrationManifest]:
        """
        List all registered integrations.

        Returns:
            List of manifests
        """
        return list(self.registry.values())

    def list_by_archetype(self, archetype: str) -> list[IntegrationManifest]:
        """
        List integrations implementing archetype, sorted by priority (highest first).

        Args:
            archetype: Archetype name (e.g., "ThreatIntel")

        Returns:
            List of manifests sorted by priority descending
        """
        # Filter integrations that implement this archetype
        matching = [
            manifest
            for manifest in self.registry.values()
            if archetype in manifest.archetypes
        ]

        # Sort by priority (highest first)
        return sorted(matching, key=lambda m: m.priority, reverse=True)

    def get_primary_integration_for_archetype(
        self, archetype: str
    ) -> IntegrationManifest | None:
        """
        Get highest-priority integration for archetype (for archetype routing).

        Args:
            archetype: Archetype name

        Returns:
            Highest priority manifest or None
        """
        # Get all integrations for this archetype, sorted by priority
        by_archetype = self.list_by_archetype(archetype)

        # Return first (highest priority) or None
        return by_archetype[0] if by_archetype else None

    def resolve_archetype_action(
        self, integration_id: str, archetype: str, method: str
    ) -> str | None:
        """
        Resolve archetype abstract method to concrete action ID.

        Used for: threatintel::lookup_ip() → resolve to action_id

        Args:
            integration_id: Integration identifier
            archetype: Archetype name
            method: Abstract method name

        Returns:
            action_id (e.g., "lookup_ip") or None
        """
        # Get integration manifest
        manifest = self.get_integration(integration_id)
        if not manifest:
            return None

        # Check if integration implements this archetype
        if archetype not in manifest.archetypes:
            return None

        # Look up method mapping
        archetype_mappings = manifest.archetype_mappings.get(archetype, {})
        return archetype_mappings.get(method)

    def get_validation_errors(
        self, integration_id: str | None = None
    ) -> dict[str, list[ValidationError]]:
        """
        Get validation errors for integrations.

        Args:
            integration_id: Specific integration ID, or None for all errors

        Returns:
            Dict mapping integration_id to list of validation errors
        """
        if integration_id:
            return {integration_id: self.validation_errors.get(integration_id, [])}
        return self.validation_errors

    def reload(self):
        """Reload all manifests from disk."""
        self._load_all_manifests()


# Module-level singleton — manifests are static files, no need to re-scan on every call.
_registry_instance: IntegrationRegistryService | None = None


def get_registry(integrations_path: Path | None = None) -> IntegrationRegistryService:
    """Return the cached registry singleton (first call loads from disk)."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = IntegrationRegistryService(integrations_path)
    return _registry_instance
