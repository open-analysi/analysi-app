"""
Manifest validation for Integrations Framework.

Validates manifest.json files against schema and archetype requirements.
"""

import importlib
import json
from pathlib import Path

from analysi.integrations.framework.models import (
    Archetype,
    IntegrationManifest,
)
from analysi.integrations.framework.models import (
    ValidationError as ManifestValidationError,
)

# Archetype definitions from NAXOS_INTEGRATION_ARCHETYPES.md
# Note: required_methods lists core methods - implementations may provide additional optional methods
ARCHETYPE_DEFINITIONS = {
    Archetype.THREAT_INTEL: {
        "required_methods": [
            # Core threat intelligence lookups - at least one should be implemented
        ]
    },
    Archetype.SIEM: {
        "required_methods": [
            # Core SIEM operations - flexible as different SIEMs have different capabilities
        ]
    },
    Archetype.EDR: {
        "required_methods": [
            # Core EDR operations - flexible as different EDRs have different capabilities
        ]
    },
    Archetype.SOAR: {
        "required_methods": [
            # SOAR orchestration operations
        ]
    },
    Archetype.TICKETING_SYSTEM: {
        "required_methods": [
            # Ticketing operations - flexible as different systems have different APIs
        ]
    },
    Archetype.COMMUNICATION: {
        "required_methods": [
            # Communication operations - flexible for different platforms
        ]
    },
    Archetype.NOTIFICATION: {
        "required_methods": [
            # Notification operations - alias for Communication archetype
            # Kept for backward compatibility
        ]
    },
    Archetype.CLOUD_PROVIDER: {
        "required_methods": [
            # Cloud provider operations - flexible for different cloud platforms
        ]
    },
    Archetype.NETWORK_SECURITY: {
        "required_methods": [
            # Network security operations - flexible for different firewall/security platforms
        ]
    },
    Archetype.IDENTITY_PROVIDER: {
        "required_methods": [
            # Identity management operations - flexible for different identity systems
        ]
    },
    Archetype.VULNERABILITY_MANAGEMENT: {
        "required_methods": [
            # Vulnerability management operations
        ]
    },
    Archetype.SANDBOX: {
        "required_methods": [
            # Malware analysis sandbox operations
        ]
    },
    Archetype.EMAIL_SECURITY: {
        "required_methods": [
            # Email security operations
        ]
    },
    Archetype.CLOUD_STORAGE: {
        "required_methods": [
            # Cloud storage operations
        ]
    },
    Archetype.DATABASE_ENRICHMENT: {
        "required_methods": [
            # Database enrichment operations (Shodan, Censys, etc.)
        ]
    },
    Archetype.FORENSICS_TOOLS: {
        "required_methods": [
            # Forensics and investigation operations
        ]
    },
    Archetype.GEOLOCATION: {
        "required_methods": [
            # Geolocation lookup operations
        ]
    },
    Archetype.AI: {
        "required_methods": [
            # LLM and AI operations - flexible for different AI providers
        ]
    },
    Archetype.LAKEHOUSE: {
        "required_methods": [
            # Data warehouse/lakehouse operations - flexible for different platforms
            # Core operations: execute_query, get_query_status, list_tables
        ]
    },
    Archetype.DNS: {
        "required_methods": [
            # DNS resolution and record lookup operations
            # Core operations: resolve_domain, reverse_lookup, get_mx_records,
            # get_txt_records, get_ns_records, get_soa_record
        ]
    },
    Archetype.AGENTIC_FRAMEWORK: {
        "required_methods": [
            # Agentic execution framework operations (Claude Code SDK, etc.)
            # Core operations: health_check (validates credentials)
        ]
    },
    Archetype.ALERT_SOURCE: {
        "required_methods": [
            # Integrations that produce security alerts must provide:
            "pull_alerts",  # Fetch raw alert events from the source
            "alerts_to_ocsf",  # Normalize raw alerts to OCSF format
        ]
    },
    Archetype.MAC_OUI_REGISTRY: {
        "required_methods": [
            # MAC address OUI vendor lookups
        ]
    },
    Archetype.QR_DECODER: {
        "required_methods": [
            # QR / barcode decoding from image artifacts
        ]
    },
    Archetype.TOR_EXIT_LIST: {
        "required_methods": [
            # Tor exit node / anonymizer detection
        ]
    },
    Archetype.URL_SHORTENING_TOOLS: {
        "required_methods": [
            # URL shortening and expansion services
        ]
    },
    Archetype.WHOIS: {
        "required_methods": [
            # WHOIS / RDAP registration data lookups
        ]
    },
}


class ManifestValidator:
    """Validates integration manifests."""

    def __init__(self):
        self.errors: list[ManifestValidationError] = []

    def validate_manifest(
        self, manifest_path: Path
    ) -> tuple[IntegrationManifest | None, list[ManifestValidationError]]:
        """
        Validate manifest.json file.

        Args:
            manifest_path: Path to manifest.json

        Returns:
            Tuple of (manifest, errors)
        """
        self.errors = []

        # 1. Load and parse JSON
        if not manifest_path.exists():
            self.errors.append(
                ManifestValidationError(
                    field="manifest_path",
                    message=f"Manifest file not found: {manifest_path}",
                    severity="error",
                )
            )
            return None, self.errors

        try:
            with open(manifest_path) as f:
                manifest_data = json.load(f)
        except json.JSONDecodeError as e:
            self.errors.append(
                ManifestValidationError(
                    field="json", message=f"Invalid JSON: {e!s}", severity="error"
                )
            )
            return None, self.errors
        except Exception as e:
            self.errors.append(
                ManifestValidationError(
                    field="file",
                    message=f"Error reading manifest: {e!s}",
                    severity="error",
                )
            )
            return None, self.errors

        # 2. Validate against Pydantic schema
        try:
            manifest = IntegrationManifest(**manifest_data)
        except Exception as e:
            self.errors.append(
                ManifestValidationError(
                    field="schema",
                    message=f"Schema validation failed: {e!s}",
                    severity="error",
                )
            )
            return None, self.errors

        # 3. Validate archetype declarations and mappings
        if manifest.archetypes:
            archetype_errors = self.validate_archetype_mappings(manifest)
            self.errors.extend(archetype_errors)

        # 4. Validate action cy_names don't contain namespace prefixes
        cy_name_errors = self.validate_cy_names(manifest)
        self.errors.extend(cy_name_errors)

        # 5. Validate action classes exist in actions.py
        action_class_errors = self.validate_action_classes(manifest, manifest_path)
        self.errors.extend(action_class_errors)

        # 6. Validate credential requirements are consistent
        credential_errors = self.validate_credentials(manifest)
        self.errors.extend(credential_errors)

        return manifest, self.errors

    def validate_archetype_mappings(
        self, manifest: IntegrationManifest
    ) -> list[ManifestValidationError]:
        """
        Validate that all required archetype methods are mapped.

        Args:
            manifest: Parsed manifest

        Returns:
            List of validation errors
        """
        errors = []

        # For each declared archetype
        for archetype in manifest.archetypes:
            # 1. Check if archetype is defined
            if archetype not in ARCHETYPE_DEFINITIONS:
                errors.append(
                    ManifestValidationError(
                        field=f"archetypes.{archetype}",
                        message=f"Unknown archetype: {archetype}",
                        severity="error",
                    )
                )
                continue

            # 2. Check archetype is in archetype_mappings
            if archetype not in manifest.archetype_mappings:
                errors.append(
                    ManifestValidationError(
                        field=f"archetype_mappings.{archetype}",
                        message=f"Missing archetype_mappings for archetype: {archetype}",
                        severity="error",
                    )
                )
                continue

            # 3. Check all required methods are mapped
            archetype_def = ARCHETYPE_DEFINITIONS[archetype]
            required_methods = archetype_def.get("required_methods", [])
            mappings = manifest.archetype_mappings[archetype]

            for method in required_methods:
                if method not in mappings:
                    errors.append(
                        ManifestValidationError(
                            field=f"archetype_mappings.{archetype}.{method}",
                            message=f"Missing required method mapping: {method}",
                            severity="error",
                        )
                    )

            # 4. Verify ALL mapped action IDs exist in actions list (required or not)
            for method, action_id in mappings.items():
                if not self.validate_action_exists(manifest, action_id):
                    errors.append(
                        ManifestValidationError(
                            field=f"archetype_mappings.{archetype}.{method}",
                            message=f"Mapped action '{action_id}' not found in actions list",
                            severity="error",
                        )
                    )

        return errors

    def validate_cy_names(
        self, manifest: IntegrationManifest
    ) -> list[ManifestValidationError]:
        """
        Validate that action cy_names don't contain namespace prefixes.

        The cy_name should be just the action name (e.g., "spl_run"),
        not the full path (e.g., "app:splunk::spl_run").
        The framework adds the namespace prefix automatically.

        Args:
            manifest: Parsed manifest

        Returns:
            List of validation errors
        """
        errors = []

        for action in manifest.actions:
            cy_name = action.cy_name
            if not cy_name:
                continue

            # Check for namespace prefixes that shouldn't be in cy_name
            invalid_prefixes = ["app::", "app:", "arc::", "arc:"]
            for prefix in invalid_prefixes:
                if cy_name.startswith(prefix) or prefix in cy_name:
                    errors.append(
                        ManifestValidationError(
                            field=f"actions.{action.id}.cy_name",
                            message=f"cy_name '{cy_name}' should not contain namespace prefix '{prefix}'. "
                            f"Use just the action name (e.g., '{cy_name.split('::')[-1]}'). "
                            f"The framework adds 'app::{manifest.id}::' automatically.",
                            severity="error",
                        )
                    )
                    break  # Only report first issue per action

        return errors

    def validate_action_exists(
        self, manifest: IntegrationManifest, action_id: str
    ) -> bool:
        """
        Check if action ID exists in manifest actions list.

        Args:
            manifest: Parsed manifest
            action_id: Action identifier to check

        Returns:
            True if action exists
        """
        return any(action.id == action_id for action in manifest.actions)

    def validate_action_classes(
        self, manifest: IntegrationManifest, manifest_path: Path
    ) -> list[ManifestValidationError]:
        """
        Validate that action classes exist in actions.py module.

        For each action in the manifest, verifies that the corresponding
        action class exists in the integration's actions.py file following
        the naming convention: action_id -> ActionIdAction (PascalCase + "Action")

        Args:
            manifest: Parsed manifest
            manifest_path: Path to manifest.json (used to locate actions.py)

        Returns:
            List of validation errors
        """
        errors = []

        # Get the integration directory (parent of manifest.json)
        integration_dir = manifest_path.parent
        actions_file = integration_dir / "actions.py"

        # Skip validation if actions.py doesn't exist
        # (some integrations might not have actions yet)
        if not actions_file.exists():
            return errors

        # Construct the module path for dynamic import
        # e.g., analysi.integrations.framework.integrations.virustotal.actions
        module_path = (
            f"analysi.integrations.framework.integrations.{manifest.id}.actions"
        )

        # Try to import the actions module
        try:
            actions_module = importlib.import_module(module_path)
        except ImportError as e:
            errors.append(
                ManifestValidationError(
                    field="actions_module",
                    message=f"Failed to import actions module '{module_path}': {e!s}",
                    severity="error",
                )
            )
            return errors

        # Validate each action has a corresponding class
        for action in manifest.actions:
            # Check if action has explicit 'class' field (for custom class names)
            # Note: 'class' is accessible through model_dump() since extra="allow"
            action_dict = action.model_dump()
            if action_dict.get("class"):
                expected_class_name = action_dict["class"]
            else:
                # Convert action_id to expected class name
                # e.g., test_connectivity -> TestConnectivityAction
                expected_class_name = self._action_id_to_class_name(action.id)

            # Check if class exists in module
            if not hasattr(actions_module, expected_class_name):
                errors.append(
                    ManifestValidationError(
                        field=f"actions.{action.id}.class",
                        message=f"Action class '{expected_class_name}' not found in module '{module_path}'. "
                        f"Expected class name for action_id '{action.id}' is '{expected_class_name}' "
                        f"(convert to PascalCase and append 'Action').",
                        severity="error",
                    )
                )

        return errors

    @staticmethod
    def _action_id_to_class_name(action_id: str) -> str:
        """
        Convert action_id to expected class name.

        Examples:
            test_connectivity -> TestConnectivityAction
            get_attributes -> GetAttributesAction
            lookup_ip -> LookupIpAction

        Args:
            action_id: Action identifier (snake_case)

        Returns:
            Expected class name (PascalCase + "Action")
        """
        # Split by underscore and capitalize each word
        parts = action_id.split("_")
        pascal_case = "".join(word.capitalize() for word in parts)
        return f"{pascal_case}Action"

    def validate_credentials(
        self, manifest: IntegrationManifest
    ) -> list[ManifestValidationError]:
        """
        Validate credential requirements are consistent with credential schema.

        Checks:
        - If requires_credentials=false, credential_schema should be empty or optional-only
        - If requires_credentials=true, credential_schema should have at least one property (warning)

        Args:
            manifest: Parsed manifest

        Returns:
            List of validation errors/warnings
        """
        errors = []

        # Get credential schema from manifest
        credential_schema = manifest.credential_schema

        # If no credential schema defined, skip validation
        if not credential_schema:
            return errors

        # Get properties from schema
        properties = credential_schema.get("properties", {})
        required_fields = credential_schema.get("required", [])

        # Check if integration requires credentials
        if not manifest.requires_credentials:
            # Integration claims no credentials needed
            # Verify credential_schema is empty or all fields are optional
            if properties:
                # Check if any properties are required
                has_required = False
                for prop_name, prop_def in properties.items():
                    if prop_name in required_fields or prop_def.get("required", False):
                        has_required = True
                        break

                if has_required:
                    errors.append(
                        ManifestValidationError(
                            field="requires_credentials",
                            message="Integration has requires_credentials=false but credential_schema has required properties. "
                            "For credential-free integrations, credential_schema should have empty properties or only optional fields.",
                            severity="error",
                        )
                    )
        else:
            # Integration requires credentials
            # Warn if credential_schema is empty (might be misconfigured)
            if not properties:
                errors.append(
                    ManifestValidationError(
                        field="credential_schema",
                        message="Integration has requires_credentials=true but credential_schema has no properties. "
                        "Consider setting requires_credentials=false if no credentials are needed, "
                        "or add credential properties if authentication is required.",
                        severity="warning",
                    )
                )

        return errors
