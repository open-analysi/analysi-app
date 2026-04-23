"""
Unit tests for ManifestValidator.

Tests UT-03.1 through UT-03.10 from TEST_PLAN.md
"""

import json
import tempfile
from pathlib import Path

from analysi.integrations.framework.models import (
    ActionDefinition,
    IntegrationManifest,
)
from analysi.integrations.framework.validators import ManifestValidator


class TestManifestValidator:
    """Test ManifestValidator validation logic."""

    def test_ut_03_1_valid_manifest_file(self):
        """UT-03.1: Validate well-formed manifest.json, verify no errors returned."""
        validator = ManifestValidator()

        manifest_data = {
            "id": "test-integration",
            "app": "test-app",
            "name": "Test Integration",
            "version": "1.0.0",
            "archetypes": [],
            "priority": 50,
            "archetype_mappings": {},
            "actions": [
                {
                    "id": "health_check",
                    "type": "connector",
                    "purpose": "health_monitoring",
                }
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            assert manifest is not None
            assert manifest.id == "test-integration"
            # Should have no critical errors
            critical_errors = [e for e in errors if e.severity == "error"]
            assert len(critical_errors) == 0
        finally:
            temp_path.unlink()

    def test_ut_03_2_malformed_json(self):
        """UT-03.2: Validate manifest with malformed JSON, verify parse error."""
        validator = ManifestValidator()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid json,,,")
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            assert manifest is None
            assert len(errors) > 0
            assert any("Invalid JSON" in e.message for e in errors)
        finally:
            temp_path.unlink()

    def test_ut_03_3_unknown_archetype(self):
        """UT-03.3: Validate manifest with unknown archetype, verify validation error."""
        validator = ManifestValidator()

        manifest_data = {
            "id": "test",
            "app": "test",
            "name": "Test",
            "version": "1.0.0",
            "archetypes": ["UnknownArchetype"],
            "priority": 50,
            "archetype_mappings": {"UnknownArchetype": {}},
            "actions": [],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            assert manifest is not None  # Manifest parses
            # But should have validation error for unknown archetype
            assert len(errors) > 0
            assert any("Unknown archetype" in e.message for e in errors)
        finally:
            temp_path.unlink()

    def test_ut_03_4_valid_threatintel_archetype(self):
        """UT-03.4: Validate manifest declaring ThreatIntel archetype with all required methods mapped."""
        validator = ManifestValidator()

        manifest_data = {
            "id": "virustotal",
            "app": "virustotal",
            "name": "VirusTotal",
            "version": "1.0.0",
            "archetypes": ["ThreatIntel"],
            "priority": 80,
            "archetype_mappings": {
                "ThreatIntel": {
                    "lookup_ip": "lookup_ip_action",
                    "lookup_domain": "lookup_domain_action",
                    "lookup_file_hash": "lookup_hash_action",
                    "lookup_url": "lookup_url_action",
                }
            },
            "actions": [
                {
                    "id": "lookup_ip_action",
                    "type": "tool",
                    "categories": ["investigation"],
                },
                {
                    "id": "lookup_domain_action",
                    "type": "tool",
                    "categories": ["investigation"],
                },
                {
                    "id": "lookup_hash_action",
                    "type": "tool",
                    "categories": ["investigation"],
                },
                {
                    "id": "lookup_url_action",
                    "type": "tool",
                    "categories": ["investigation"],
                },
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            assert manifest is not None
            # Should have no critical errors
            critical_errors = [e for e in errors if e.severity == "error"]
            assert len(critical_errors) == 0
        finally:
            temp_path.unlink()

    def test_ut_03_5_missing_required_method_mapping(self):
        """UT-03.5: Validate manifest declaring ThreatIntel with empty mappings.

        Note: With flexible archetype approach, required_methods are optional.
        This test now verifies that empty mappings are accepted (no errors).
        """
        validator = ManifestValidator()

        manifest_data = {
            "id": "partial-threatintel",
            "app": "partial",
            "name": "Partial ThreatIntel",
            "version": "1.0.0",
            "archetypes": ["ThreatIntel"],
            "priority": 50,
            "archetype_mappings": {
                "ThreatIntel": {
                    # Empty mappings are now allowed (flexible archetypes)
                }
            },
            "actions": [],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            assert manifest is not None
            # With flexible archetypes, empty mappings are allowed - no errors expected
            critical_errors = [e for e in errors if e.severity == "error"]
            assert len(critical_errors) == 0
        finally:
            temp_path.unlink()

    def test_ut_03_6_mapping_to_nonexistent_action(self):
        """UT-03.6: Validate manifest with archetype mapping to non-existent action, verify error.

        This test validates that mappings pointing to non-existent actions are caught,
        regardless of whether methods are "required" or not.
        """
        validator = ManifestValidator()

        manifest_data = {
            "id": "broken-mapping",
            "app": "broken",
            "name": "Broken Mapping",
            "version": "1.0.0",
            "archetypes": ["ThreatIntel"],
            "priority": 50,
            "archetype_mappings": {
                "ThreatIntel": {
                    "lookup_ip": "nonexistent_action",  # Action doesn't exist - should error
                }
            },
            "actions": [
                {
                    "id": "lookup_domain_action",
                    "type": "tool",
                    "categories": ["investigation"],
                },
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            assert manifest is not None
            # Should have error for non-existent action
            assert len(errors) > 0
            assert any("nonexistent_action" in e.message for e in errors)
        finally:
            temp_path.unlink()

    def test_ut_03_7_connector_with_valid_purpose(self):
        """UT-03.7: Validate manifest with connector action having valid purpose."""
        validator = ManifestValidator()

        manifest_data = {
            "id": "test",
            "app": "test",
            "name": "Test",
            "version": "1.0.0",
            "archetypes": [],
            "priority": 50,
            "archetype_mappings": {},
            "actions": [
                {
                    "id": "health_check",
                    "type": "connector",
                    "purpose": "health_monitoring",
                },
                {
                    "id": "pull_alerts",
                    "type": "connector",
                    "purpose": "alert_ingestion",
                },
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            assert manifest is not None
            critical_errors = [e for e in errors if e.severity == "error"]
            assert len(critical_errors) == 0
        finally:
            temp_path.unlink()

    def test_ut_03_8_connector_with_invalid_purpose(self):
        """UT-03.8: Validate manifest with connector action having invalid purpose, verify error."""
        validator = ManifestValidator()

        manifest_data = {
            "id": "test",
            "app": "test",
            "name": "Test",
            "version": "1.0.0",
            "archetypes": [],
            "priority": 50,
            "archetype_mappings": {},
            "actions": [
                {
                    "id": "bad_connector",
                    "categories": ["health_monitoring"],
                }
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            # type/purpose are removed. This test now verifies
            # that a manifest with only basic action fields (no name, no description)
            # still parses but may produce warnings.
            assert manifest is not None  # Should parse since categories is valid
        finally:
            temp_path.unlink()

    def test_ut_03_9_multiple_archetypes_complete_mappings(self):
        """UT-03.9: Validate manifest with multiple archetypes, all mappings complete."""
        validator = ManifestValidator()

        manifest_data = {
            "id": "multi-archetype",
            "app": "multi",
            "name": "Multi Archetype",
            "version": "1.0.0",
            "archetypes": ["ThreatIntel", "SIEM"],
            "priority": 70,
            "archetype_mappings": {
                "ThreatIntel": {
                    "lookup_ip": "lookup_ip_action",
                    "lookup_domain": "lookup_domain_action",
                    "lookup_file_hash": "lookup_hash_action",
                    "lookup_url": "lookup_url_action",
                },
                "SIEM": {
                    "query_events": "query_action",
                    "create_alert": "create_alert_action",
                    "get_alerts": "get_notables_action",
                },
            },
            "actions": [
                {
                    "id": "lookup_ip_action",
                    "type": "tool",
                    "categories": ["investigation"],
                },
                {
                    "id": "lookup_domain_action",
                    "type": "tool",
                    "categories": ["investigation"],
                },
                {
                    "id": "lookup_hash_action",
                    "type": "tool",
                    "categories": ["investigation"],
                },
                {
                    "id": "lookup_url_action",
                    "type": "tool",
                    "categories": ["investigation"],
                },
                {
                    "id": "query_action",
                    "type": "connector",
                    "purpose": "alert_ingestion",
                },
                {
                    "id": "create_alert_action",
                    "type": "connector",
                    "purpose": "alert_output",
                },
                {
                    "id": "get_notables_action",
                    "type": "connector",
                    "purpose": "alert_ingestion",
                },
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            assert manifest is not None
            critical_errors = [e for e in errors if e.severity == "error"]
            assert len(critical_errors) == 0
        finally:
            temp_path.unlink()

    def test_ut_03_10_duplicate_action_ids(self):
        """UT-03.10: Validate manifest with duplicate action IDs, verify error."""
        # Note: Pydantic doesn't enforce unique action IDs by default
        # This test verifies current behavior - we may want to add custom validation later
        validator = ManifestValidator()

        manifest_data = {
            "id": "duplicate-actions",
            "app": "duplicate",
            "name": "Duplicate Actions",
            "version": "1.0.0",
            "archetypes": [],
            "priority": 50,
            "archetype_mappings": {},
            "actions": [
                {
                    "id": "health_check",
                    "type": "connector",
                    "purpose": "health_monitoring",
                },
                {
                    "id": "health_check",
                    "type": "connector",
                    "purpose": "health_monitoring",
                },  # Duplicate
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            # Currently Pydantic allows duplicates - manifest will parse successfully
            # We should add custom validation for this in the future
            assert manifest is not None
            # TODO: Add custom validation to catch duplicate action IDs
        finally:
            temp_path.unlink()


class TestValidateActionExists:
    """Test validate_action_exists helper method."""

    def test_action_exists(self):
        """Verify action exists in manifest."""
        validator = ManifestValidator()
        manifest = IntegrationManifest(
            id="test",
            app="test",
            name="Test",
            version="1.0.0",
            archetypes=[],
            priority=50,
            archetype_mappings={},
            actions=[
                ActionDefinition(id="health_check", categories=["health_monitoring"]),
                ActionDefinition(id="lookup_ip", categories=["investigation"]),
            ],
        )

        assert validator.validate_action_exists(manifest, "health_check") is True
        assert validator.validate_action_exists(manifest, "lookup_ip") is True
        assert validator.validate_action_exists(manifest, "nonexistent") is False


class TestManifestParameterSchemas:
    """Test that all integration manifests have proper params_schema definitions."""

    def test_all_integration_manifests_have_params_schema(self):
        """Verify all actions in all integration manifests have params_schema defined."""
        from analysi.integrations.framework.registry import IntegrationRegistryService

        registry = IntegrationRegistryService()
        integrations_without_schemas = []

        for integration in registry.list_integrations():
            for action in integration.actions:
                # Check if params_schema exists in metadata
                params_schema = action.metadata.get("params_schema")

                if params_schema is None:
                    integrations_without_schemas.append(
                        f"{integration.id}::{action.id}"
                    )

        # All actions should have params_schema
        assert len(integrations_without_schemas) == 0, (
            "The following actions are missing params_schema:\n"
            + "\n".join(f"  - {item}" for item in integrations_without_schemas)
        )

    def test_params_schema_structure(self):
        """Verify params_schema has correct structure (type, properties, required)."""
        from analysi.integrations.framework.registry import IntegrationRegistryService

        registry = IntegrationRegistryService()
        invalid_schemas = []

        for integration in registry.list_integrations():
            for action in integration.actions:
                params_schema = action.metadata.get("params_schema", {})

                # Should be a dict
                if not isinstance(params_schema, dict):
                    invalid_schemas.append(
                        f"{integration.id}::{action.id} - params_schema is not a dict"
                    )
                    continue

                # Should have 'type' field
                if "type" not in params_schema:
                    invalid_schemas.append(
                        f"{integration.id}::{action.id} - params_schema missing 'type' field"
                    )

                # Should have 'properties' field (even if empty)
                if "properties" not in params_schema:
                    invalid_schemas.append(
                        f"{integration.id}::{action.id} - params_schema missing 'properties' field"
                    )

                # 'required' should be a list if present
                if "required" in params_schema and not isinstance(
                    params_schema["required"], list
                ):
                    invalid_schemas.append(
                        f"{integration.id}::{action.id} - params_schema 'required' is not a list"
                    )

        assert len(invalid_schemas) == 0, (
            "The following actions have invalid params_schema structure:\n"
            + "\n".join(f"  - {item}" for item in invalid_schemas)
        )

    def test_virustotal_params_schema_completeness(self):
        """Verify VirusTotal integration has complete params_schema for all tools."""
        from analysi.integrations.framework.registry import IntegrationRegistryService

        registry = IntegrationRegistryService()
        virustotal = registry.get_integration("virustotal")

        expected_actions_with_params = {
            "ip_reputation": ["ip"],
            "domain_reputation": ["domain"],
            "url_reputation": ["url"],
            "file_reputation": ["file_hash"],
            "submit_url_analysis": ["url"],
            "get_analysis_report": ["analysis_id"],
        }

        for action_id, expected_params in expected_actions_with_params.items():
            action = next((a for a in virustotal.actions if a.id == action_id), None)
            assert action is not None, f"Action {action_id} not found"

            params_schema = action.metadata.get("params_schema", {})
            properties = params_schema.get("properties", {})
            required = params_schema.get("required", [])

            # Verify expected parameters are in properties
            for param in expected_params:
                assert param in properties, (
                    f"{action_id} missing parameter '{param}' in params_schema"
                )

            # Verify expected parameters are required
            for param in expected_params:
                assert param in required, (
                    f"{action_id} parameter '{param}' should be required"
                )

    def test_splunk_spl_run_params_schema(self):
        """Verify Splunk spl_run action has correct params_schema."""
        from analysi.integrations.framework.registry import IntegrationRegistryService

        registry = IntegrationRegistryService()
        splunk = registry.get_integration("splunk")

        spl_run = next((a for a in splunk.actions if a.id == "spl_run"), None)
        assert spl_run is not None, "spl_run action not found"

        params_schema = spl_run.metadata.get("params_schema", {})
        properties = params_schema.get("properties", {})
        required = params_schema.get("required", [])

        # Should have spl_query (required)
        assert "spl_query" in properties
        assert "spl_query" in required
        assert properties["spl_query"]["type"] == "string"

        # Should have timeout (optional)
        assert "timeout" in properties
        assert (
            "timeout" not in required
            or properties["timeout"].get("default") is not None
        )

    def test_echo_edr_host_actions_params_schema(self):
        """Verify Echo EDR host-related actions have hostname parameter."""
        from analysi.integrations.framework.registry import IntegrationRegistryService

        registry = IntegrationRegistryService()
        echo_edr = registry.get_integration("echo_edr")

        host_actions = ["isolate_host", "release_host", "scan_host", "get_host_details"]

        for action_id in host_actions:
            action = next((a for a in echo_edr.actions if a.id == action_id), None)
            assert action is not None, f"Action {action_id} not found"

            params_schema = action.metadata.get("params_schema", {})
            properties = params_schema.get("properties", {})
            required = params_schema.get("required", [])

            # All host actions should require hostname
            assert "hostname" in properties, f"{action_id} missing 'hostname' parameter"
            assert "hostname" in required, f"{action_id} should require 'hostname'"


class TestCyNameValidation:
    """Test cy_name validation to prevent namespace prefix duplication."""

    def test_valid_cy_name_without_prefix(self):
        """Verify cy_names without namespace prefixes pass validation."""
        validator = ManifestValidator()

        manifest_data = {
            "id": "test-integration",
            "app": "test",
            "name": "Test Integration",
            "version": "1.0.0",
            "archetypes": [],
            "priority": 50,
            "archetype_mappings": {},
            "actions": [
                {
                    "id": "test_action",
                    "type": "tool",
                    "categories": ["testing"],
                    "cy_name": "test_action",
                    "params_schema": {"type": "object", "properties": {}},
                }
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            assert manifest is not None
            critical_errors = [e for e in errors if e.severity == "error"]
            assert len(critical_errors) == 0
        finally:
            temp_path.unlink()

    def test_cy_name_with_app_double_colon_prefix_rejected(self):
        """Verify cy_names with 'app::' prefix are rejected."""
        validator = ManifestValidator()

        manifest_data = {
            "id": "test-integration",
            "app": "test",
            "name": "Test Integration",
            "version": "1.0.0",
            "archetypes": [],
            "priority": 50,
            "archetype_mappings": {},
            "actions": [
                {
                    "id": "test_action",
                    "type": "tool",
                    "categories": ["testing"],
                    "cy_name": "app::test::test_action",
                    "params_schema": {"type": "object", "properties": {}},
                }
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            assert manifest is not None
            # Should have validation error for namespace prefix
            assert len(errors) > 0
            assert any(
                "app::" in e.message
                and "should not contain namespace prefix" in e.message
                for e in errors
            )
        finally:
            temp_path.unlink()

    def test_cy_name_with_app_single_colon_prefix_rejected(self):
        """Verify cy_names with 'app:' prefix are rejected."""
        validator = ManifestValidator()

        manifest_data = {
            "id": "test-integration",
            "app": "test",
            "name": "Test Integration",
            "version": "1.0.0",
            "archetypes": [],
            "priority": 50,
            "archetype_mappings": {},
            "actions": [
                {
                    "id": "test_action",
                    "type": "tool",
                    "categories": ["testing"],
                    "cy_name": "app:test:test_action",
                    "params_schema": {"type": "object", "properties": {}},
                }
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            assert manifest is not None
            # Should have validation error for namespace prefix
            assert len(errors) > 0
            assert any(
                "app:" in e.message
                and "should not contain namespace prefix" in e.message
                for e in errors
            )
        finally:
            temp_path.unlink()

    def test_cy_name_with_arc_double_colon_prefix_rejected(self):
        """Verify cy_names with 'arc::' prefix are rejected."""
        validator = ManifestValidator()

        manifest_data = {
            "id": "test-integration",
            "app": "test",
            "name": "Test Integration",
            "version": "1.0.0",
            "archetypes": [],
            "priority": 50,
            "archetype_mappings": {},
            "actions": [
                {
                    "id": "test_action",
                    "type": "tool",
                    "categories": ["testing"],
                    "cy_name": "arc::ThreatIntel::lookup_ip",
                    "params_schema": {"type": "object", "properties": {}},
                }
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            assert manifest is not None
            # Should have validation error for namespace prefix
            assert len(errors) > 0
            assert any(
                "arc::" in e.message
                and "should not contain namespace prefix" in e.message
                for e in errors
            )
        finally:
            temp_path.unlink()

    def test_action_without_cy_name_no_error(self):
        """Verify actions without cy_name don't trigger validation errors."""
        validator = ManifestValidator()

        manifest_data = {
            "id": "test-integration",
            "app": "test",
            "name": "Test Integration",
            "version": "1.0.0",
            "archetypes": [],
            "priority": 50,
            "archetype_mappings": {},
            "actions": [
                {
                    "id": "connector_action",
                    "type": "connector",
                    "purpose": "health_monitoring",
                    # No metadata/cy_name - this is valid for connector actions
                }
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            assert manifest is not None
            critical_errors = [e for e in errors if e.severity == "error"]
            assert len(critical_errors) == 0
        finally:
            temp_path.unlink()

    def test_cy_name_error_message_provides_guidance(self):
        """Verify error message for malformed cy_name provides helpful guidance."""
        validator = ManifestValidator()

        manifest_data = {
            "id": "splunk",
            "app": "splunk",
            "name": "Splunk",
            "version": "1.0.0",
            "archetypes": [],
            "priority": 50,
            "archetype_mappings": {},
            "actions": [
                {
                    "id": "spl_run",
                    "type": "tool",
                    "categories": ["query"],
                    "cy_name": "app:splunk::spl_run",
                    "params_schema": {"type": "object", "properties": {}},
                }
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            assert manifest is not None
            assert len(errors) > 0

            # Find the cy_name error
            cy_name_error = next((e for e in errors if "cy_name" in e.field), None)
            assert cy_name_error is not None

            # Error message should contain:
            # 1. The problematic cy_name
            # 2. The invalid prefix
            # 3. Suggestion to use short name
            # 4. Explanation that framework adds prefix automatically
            assert "app:splunk::spl_run" in cy_name_error.message
            assert "should not contain namespace prefix" in cy_name_error.message
            assert "spl_run" in cy_name_error.message
            assert "framework adds" in cy_name_error.message
        finally:
            temp_path.unlink()

    def test_all_splunk_cy_names_valid(self):
        """Verify all Splunk action cy_names are valid after fix."""
        from analysi.integrations.framework.registry import IntegrationRegistryService

        registry = IntegrationRegistryService()
        splunk = registry.get_integration("splunk")

        invalid_prefixes = ["app::", "app:", "arc::", "arc:"]
        invalid_cy_names = []

        for action in splunk.actions:
            cy_name = action.metadata.get("cy_name") if action.metadata else None
            if not cy_name:
                continue

            # Check for invalid prefixes
            for prefix in invalid_prefixes:
                if prefix in cy_name:
                    invalid_cy_names.append(
                        f"{action.id}: {cy_name} (contains '{prefix}')"
                    )
                    break

        assert len(invalid_cy_names) == 0, (
            "Found Splunk actions with invalid cy_names:\n"
            + "\n".join(f"  - {item}" for item in invalid_cy_names)
        )


class TestActionClassValidation:
    """Test action class existence validation."""

    def test_action_id_to_class_name_conversion(self):
        """Verify action_id to class name conversion."""
        from analysi.integrations.framework.validators import ManifestValidator

        validator = ManifestValidator()

        # Test various conversions
        assert (
            validator._action_id_to_class_name("test_connectivity")
            == "TestConnectivityAction"
        )
        assert (
            validator._action_id_to_class_name("get_attributes")
            == "GetAttributesAction"
        )
        assert validator._action_id_to_class_name("lookup_ip") == "LookupIpAction"
        assert (
            validator._action_id_to_class_name("submit_url_analysis")
            == "SubmitUrlAnalysisAction"
        )
        assert validator._action_id_to_class_name("spl_run") == "SplRunAction"

    def test_action_classes_exist_validation_passes(self):
        """Verify validation passes when all action classes exist."""
        validator = ManifestValidator()

        # Use AD LDAP which we know has correct class names
        # Path(__file__) points to tests/unit/integrations/framework/test_validators.py
        # We need to go up 5 levels to project root, then to src/
        test_file_path = Path(__file__).resolve()
        project_root = test_file_path.parent.parent.parent.parent.parent
        manifest_path = (
            project_root
            / "src"
            / "analysi"
            / "integrations"
            / "framework"
            / "integrations"
            / "ad_ldap"
            / "manifest.json"
        )

        manifest, errors = validator.validate_manifest(manifest_path)

        # Print errors for debugging
        if errors:
            for e in errors:
                print(f"Error: {e.field} - {e.message} ({e.severity})")

        assert manifest is not None, (
            f"Manifest failed to load. Errors: {[e.message for e in errors]}"
        )
        # Check no errors related to missing action classes
        class_errors = [
            e for e in errors if "class" in e.field and "not found" in e.message
        ]
        assert len(class_errors) == 0

    def test_action_classes_missing_detected(self):
        """Verify validation detects missing action classes."""
        validator = ManifestValidator()

        # Create a temporary manifest with non-existent action
        manifest_data = {
            "id": "test_missing_class",
            "app": "test",
            "name": "Test Missing Class",
            "version": "1.0.0",
            "archetypes": [],
            "priority": 50,
            "archetype_mappings": {},
            "actions": [
                {"id": "nonexistent_action", "type": "tool", "categories": ["testing"]}
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            # Create a dummy integration directory structure
            integration_dir = temp_path.parent / "test_missing_class"
            integration_dir.mkdir(exist_ok=True)

            # Move manifest to integration dir
            manifest_in_dir = integration_dir / "manifest.json"
            temp_path.rename(manifest_in_dir)

            # Create empty actions.py
            actions_file = integration_dir / "actions.py"
            actions_file.write_text("# Empty actions file\n")

            # Validate - should fail because NonexistentActionAction class doesn't exist
            manifest, errors = validator.validate_manifest(manifest_in_dir)

            # Should have error about missing class
            [e for e in errors if "class" in e.field]
            # Note: Will fail to import module since it's not in the proper package structure
            # So we expect either import error or class not found error
            assert len(errors) > 0

        finally:
            # Cleanup
            if integration_dir.exists():
                import shutil

                shutil.rmtree(integration_dir)


class TestArchetypeMappingActionIdFormat:
    """Test archetype_mappings use correct action ID format (no 'tools.' prefix)."""

    def test_archetype_mapping_with_valid_action_id(self):
        """Verify archetype_mappings using raw action IDs pass validation."""
        validator = ManifestValidator()

        manifest_data = {
            "id": "ad_ldap",
            "app": "ad_ldap",
            "name": "AD LDAP",
            "version": "1.0.0",
            "archetypes": ["IdentityProvider"],
            "priority": 70,
            "archetype_mappings": {
                "IdentityProvider": {
                    "get_user_details": "get_attributes",  # Correct: raw action ID
                }
            },
            "actions": [
                {
                    "id": "get_attributes",
                    "type": "tool",
                    "categories": ["identity"],
                    "cy_name": "get_attributes",
                    "params_schema": {"type": "object", "properties": {}},
                }
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            assert manifest is not None
            critical_errors = [e for e in errors if e.severity == "error"]
            assert len(critical_errors) == 0
        finally:
            temp_path.unlink()

    def test_archetype_mapping_with_tools_prefix_rejected(self):
        """Verify archetype_mappings using 'tools.' prefix are rejected."""
        validator = ManifestValidator()

        manifest_data = {
            "id": "ad_ldap",
            "app": "ad_ldap",
            "name": "AD LDAP",
            "version": "1.0.0",
            "archetypes": ["IdentityProvider"],
            "priority": 70,
            "archetype_mappings": {
                "IdentityProvider": {
                    "get_user_details": "tools.get_attributes",  # Incorrect: has "tools." prefix
                }
            },
            "actions": [
                {
                    "id": "get_attributes",
                    "type": "tool",
                    "categories": ["identity"],
                    "cy_name": "get_attributes",
                    "params_schema": {"type": "object", "properties": {}},
                }
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            assert manifest is not None
            # Should have validation error for non-existent action
            assert len(errors) > 0
            assert any(
                "tools.get_attributes" in e.message
                and "not found in actions list" in e.message
                for e in errors
            )
            assert any(
                "archetype_mappings.IdentityProvider.get_user_details" in e.field
                for e in errors
            )
        finally:
            temp_path.unlink()

    def test_archetype_mapping_multiple_methods_with_tools_prefix(self):
        """Verify multiple archetype mappings with 'tools.' prefix are all caught."""
        validator = ManifestValidator()

        manifest_data = {
            "id": "ad_ldap",
            "app": "ad_ldap",
            "name": "AD LDAP",
            "version": "1.0.0",
            "archetypes": ["IdentityProvider"],
            "priority": 70,
            "archetype_mappings": {
                "IdentityProvider": {
                    "get_user_details": "tools.get_attributes",  # Incorrect
                    "disable_user": "tools.disable_account",  # Incorrect
                    "enable_user": "enable_account",  # Correct
                }
            },
            "actions": [
                {"id": "get_attributes", "type": "tool", "categories": ["identity"]},
                {"id": "disable_account", "type": "tool", "categories": ["identity"]},
                {"id": "enable_account", "type": "tool", "categories": ["identity"]},
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest_data, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            assert manifest is not None
            # Should have 2 validation errors (for the two incorrect mappings)
            assert len(errors) >= 2
            assert any("tools.get_attributes" in e.message for e in errors)
            assert any("tools.disable_account" in e.message for e in errors)
        finally:
            temp_path.unlink()
