"""
Unit tests for Splunk manifest validation.

Tests manifest.json structure, loading, and validation for Splunk integration.
Following TDD - these tests will fail until implementations are complete.
"""

import json
from pathlib import Path

import pytest

from analysi.integrations.framework.validators import ManifestValidator


class TestSplunkManifestValidation:
    """Test Splunk manifest validation."""

    @pytest.fixture
    def splunk_manifest_path(self):
        """Get path to Splunk manifest."""
        return (
            Path(__file__).parent.parent.parent.parent.parent
            / "src"
            / "analysi"
            / "integrations"
            / "framework"
            / "integrations"
            / "splunk"
            / "manifest.json"
        )

    @pytest.fixture
    def splunk_manifest_data(self, splunk_manifest_path):
        """Load Splunk manifest data."""
        with open(splunk_manifest_path) as f:
            return json.load(f)

    def test_valid_splunk_manifest_loads_successfully(self, splunk_manifest_path):
        """Test: Valid Splunk manifest loads successfully.

        Goal: Verify the Splunk manifest.json file is valid and loads without errors.
        """
        validator = ManifestValidator()

        manifest, errors = validator.validate_manifest(splunk_manifest_path)

        # Print errors for debugging
        if errors:
            print(f"\nManifest errors: {errors}")

        # Manifest should load
        assert manifest is not None, (
            f"Manifest should load successfully. Errors: {errors}"
        )
        assert manifest.id == "splunk", f"Expected id='splunk', got {manifest.id}"

        # Should have no critical errors
        critical_errors = [e for e in errors if e.severity == "error"]
        assert len(critical_errors) == 0, (
            f"Should have no critical errors, got: {critical_errors}"
        )

        # Should have 13 actions (3 connector-category + 10 tool actions including alerts_to_ocsf)
        assert len(manifest.actions) == 13, (
            f"Expected 13 actions, got {len(manifest.actions)}"
        )

    def test_splunk_manifest_declares_siem_archetype_correctly(
        self, splunk_manifest_data
    ):
        """Test: Splunk manifest declares SIEM archetype correctly.

        Goal: Ensure Splunk integration properly declares SIEM archetype with correct priority.
        """
        # Check archetypes field (plural, array)
        assert "archetypes" in splunk_manifest_data, (
            "Manifest should have archetypes field"
        )
        assert "SIEM" in splunk_manifest_data["archetypes"], (
            f"Expected SIEM in archetypes, got {splunk_manifest_data.get('archetypes')}"
        )

        # Check priority
        assert "priority" in splunk_manifest_data, "Manifest should have priority field"
        assert splunk_manifest_data["priority"] == 90, (
            f"Expected priority 90, got {splunk_manifest_data.get('priority')}"
        )

    def test_splunk_credential_schema_validation(self, splunk_manifest_data):
        """Test: Splunk credential schema validation.

        Goal: Verify Splunk credential schema requires username and password.
        """
        assert "credential_schema" in splunk_manifest_data, (
            "Manifest should have credential_schema"
        )

        schema = splunk_manifest_data["credential_schema"]
        assert schema["type"] == "object", "Credential schema should be object type"

        # Check username field
        assert "username" in schema["properties"], (
            "Schema should have username property"
        )
        username_field = schema["properties"]["username"]
        assert username_field["required"] is True, "Username should be required"

        # Check password field
        assert "password" in schema["properties"], (
            "Schema should have password property"
        )
        password_field = schema["properties"]["password"]
        assert password_field["format"] == "password", (
            "Password should have format='password'"
        )
        assert password_field["required"] is True, "Password should be required"

    def test_splunk_tool_actions_have_correct_cy_name_format(
        self, splunk_manifest_data
    ):
        """Test: Splunk tool actions have correct cy_name format.

        Goal: Ensure all Splunk tool actions use short cy_name (not full path).
        The framework automatically adds the 'app::{integration_type}::' prefix,
        so cy_name should be just the action name, not the full path.
        """
        actions = splunk_manifest_data["actions"]

        # Filter for tool actions (those with cy_name)
        tool_actions = [a for a in actions if a.get("cy_name")]

        # All 13 actions have cy_name
        assert len(tool_actions) == 13, (
            f"Expected 13 tools with cy_name, got {len(tool_actions)}"
        )

        # Check each tool has correctly formatted cy_name (short name, not full path)
        for action in tool_actions:
            assert "cy_name" in action, f"Tool {action['id']} should have cy_name field"

            cy_name = action["cy_name"]
            # cy_name should match action_id (short name without namespace prefix)
            assert cy_name == action["id"], (
                f"Expected cy_name='{action['id']}' (short name), got '{cy_name}'. "
                f"Framework adds 'app::splunk::' prefix automatically."
            )

            # Verify it does NOT contain namespace prefixes
            invalid_prefixes = ["app::", "app:", "arc::", "arc:"]
            for prefix in invalid_prefixes:
                assert prefix not in cy_name, (
                    f"cy_name '{cy_name}' should not contain '{prefix}' - framework adds namespace automatically"
                )

    def test_splunk_manifest_has_default_schedules(self, splunk_manifest_data):
        """Test: Splunk manifest has default schedules.

        Goal: Verify default schedules are defined for health_check and pull_alerts.
        """
        assert "default_schedules" in splunk_manifest_data, (
            "Manifest should have default_schedules"
        )

        schedules = splunk_manifest_data["default_schedules"]

        # Should have 3 default schedules (health_check, pull_alerts, sourcetype_discovery)
        assert len(schedules) == 3, (
            f"Expected 3 default schedules, got {len(schedules)}"
        )

        # Check health_check schedule
        health_check_schedule = next(
            (s for s in schedules if s["action_id"] == "health_check"), None
        )
        assert health_check_schedule is not None, "Should have health_check schedule"
        assert health_check_schedule["schedule"] == "every/5m", (
            f"Expected every/5m, got {health_check_schedule['schedule']}"
        )
        assert health_check_schedule["enabled"] is True, (
            "Health check should be enabled"
        )

        # Check pull_alerts schedule
        pull_alerts_schedule = next(
            (s for s in schedules if s["action_id"] == "pull_alerts"), None
        )
        assert pull_alerts_schedule is not None, "Should have pull_alerts schedule"
        assert pull_alerts_schedule["schedule"] == "every/1m", (
            f"Expected every/1m, got {pull_alerts_schedule['schedule']}"
        )
        assert pull_alerts_schedule["enabled"] is True, "Pull alerts should be enabled"

        # Check sourcetype_discovery schedule
        discovery_schedule = next(
            (s for s in schedules if s["action_id"] == "sourcetype_discovery"), None
        )
        assert discovery_schedule is not None, (
            "Should have sourcetype_discovery schedule"
        )
        assert discovery_schedule["schedule"] == "every/24h", (
            f"Expected every/24h, got {discovery_schedule['schedule']}"
        )
        assert discovery_schedule["enabled"] is True, (
            "Sourcetype discovery should be enabled"
        )

    def test_invalid_splunk_manifest_fails_validation(self):
        """Test: Invalid Splunk manifest fails validation.

        Goal: Ensure manifest validation catches malformed manifests.
        """
        validator = ManifestValidator()

        # Create invalid manifest (missing required fields)
        import tempfile

        invalid_manifest = {
            "id": "splunk",
            # Missing: name, version, archetype, actions, etc.
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(invalid_manifest, f)
            temp_path = Path(f.name)

        try:
            manifest, errors = validator.validate_manifest(temp_path)

            # Should have validation errors for missing required fields
            assert len(errors) > 0, "Should have validation errors for missing fields"

            # Should have error messages about missing fields
            error_messages = [e.message for e in errors]
            # Expect errors about missing required fields
            assert any(
                "name" in msg.lower() or "required" in msg.lower()
                for msg in error_messages
            ), "Should have error about missing required fields"
        finally:
            temp_path.unlink()


class TestSplunkManifestActions:
    """Test Splunk manifest action definitions."""

    @pytest.fixture
    def splunk_manifest_data(self):
        """Load Splunk manifest data."""
        manifest_path = (
            Path(__file__).parent.parent.parent.parent.parent
            / "src"
            / "analysi"
            / "integrations"
            / "framework"
            / "integrations"
            / "splunk"
            / "manifest.json"
        )
        with open(manifest_path) as f:
            return json.load(f)

    def test_splunk_has_13_actions(self, splunk_manifest_data):
        """Splunk manifest defines 13 unified actions."""
        actions = splunk_manifest_data["actions"]
        assert len(actions) == 13, f"Expected 13 actions, got {len(actions)}"

        action_ids = [a["id"] for a in actions]
        for expected in [
            "health_check",
            "pull_alerts",
            "alerts_to_ocsf",
            "update_notable",
            "spl_run",
            "sourcetype_discovery",
        ]:
            assert expected in action_ids, f"Missing action {expected}"

    def test_splunk_actions_have_expected_categories(self, splunk_manifest_data):
        """Key actions have their domain categories set."""
        actions = {a["id"]: a for a in splunk_manifest_data["actions"]}

        assert "health_monitoring" in actions["health_check"]["categories"]
        assert "alert_ingestion" in actions["pull_alerts"]["categories"]
        assert "knowledge_building" in actions["sourcetype_discovery"]["categories"]

    def test_splunk_all_actions_have_categories(self, splunk_manifest_data):
        """Test: All Splunk actions have categories field."""
        actions = splunk_manifest_data["actions"]

        for action in actions:
            assert "categories" in action, (
                f"Action {action['id']} should have categories field"
            )
            assert isinstance(action["categories"], list), (
                f"Action {action['id']} categories should be list"
            )
            assert len(action["categories"]) > 0, (
                f"Action {action['id']} should have at least one category"
            )
