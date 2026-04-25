"""
Unit tests for OpenAI manifest validation.

Tests manifest.json structure, loading, and validation for OpenAI integration.
Following TDD - these tests will fail until implementations are complete.
"""

import json
from pathlib import Path

import pytest

from analysi.integrations.framework.validators import ManifestValidator


class TestOpenAIManifestValidation:
    """Test OpenAI manifest validation."""

    @pytest.fixture
    def openai_manifest_path(self):
        """Get path to OpenAI manifest."""
        return (
            Path(__file__).parent.parent.parent.parent.parent
            / "src"
            / "analysi"
            / "integrations"
            / "framework"
            / "integrations"
            / "openai"
            / "manifest.json"
        )

    @pytest.fixture
    def openai_manifest_data(self, openai_manifest_path):
        """Load OpenAI manifest data."""
        with open(openai_manifest_path) as f:
            return json.load(f)

    def test_valid_openai_manifest_loads_successfully(self, openai_manifest_path):
        """Test: Valid OpenAI manifest loads successfully.

        Goal: Verify the OpenAI manifest.json file is valid and loads without errors.
        """
        validator = ManifestValidator()

        manifest, errors = validator.validate_manifest(openai_manifest_path)

        # Manifest should load
        assert manifest is not None, "Manifest should load successfully"
        assert manifest.id == "openai", f"Expected id='openai', got {manifest.id}"

        # Should have no critical errors
        critical_errors = [e for e in errors if e.severity == "error"]
        assert len(critical_errors) == 0, (
            f"Should have no critical errors, got: {critical_errors}"
        )

        # Should have 4 actions: health_check + AI archetype tools (llm_run, llm_chat, llm_embed)
        assert len(manifest.actions) == 4, (
            f"Expected 4 actions, got {len(manifest.actions)}"
        )

    def test_openai_manifest_declares_ai_archetype_correctly(
        self, openai_manifest_data
    ):
        """Test: OpenAI manifest declares AI archetype correctly.

        Goal: Ensure OpenAI integration properly declares AI archetype (newly added archetype #17).
        """
        # Check archetypes field (plural, array)
        assert "archetypes" in openai_manifest_data, (
            "Manifest should have archetypes field"
        )
        assert "AI" in openai_manifest_data["archetypes"], (
            f"Expected AI in archetypes, got {openai_manifest_data.get('archetypes')}"
        )

        # Check priority
        assert "priority" in openai_manifest_data, "Manifest should have priority field"
        assert openai_manifest_data["priority"] == 80, (
            f"Expected priority 80, got {openai_manifest_data.get('priority')}"
        )

    def test_openai_credential_schema_validation(self, openai_manifest_data):
        """Test: OpenAI credential schema validation.

        Goal: Verify OpenAI credential schema requires api_key.
        """
        assert "credential_schema" in openai_manifest_data, (
            "Manifest should have credential_schema"
        )

        schema = openai_manifest_data["credential_schema"]
        assert schema["type"] == "object", "Credential schema should be object type"

        # Check api_key field
        assert "api_key" in schema["properties"], "Schema should have api_key property"
        api_key_field = schema["properties"]["api_key"]
        assert api_key_field["required"] is True, "API key should be required"
        assert api_key_field["format"] == "password", (
            "API key should have format='password'"
        )

    def test_openai_manifest_has_ai_archetype_actions(self, openai_manifest_data):
        """Test: OpenAI manifest has AI archetype actions implemented.

        Goal: Verify AI archetype actions (llm_run, llm_chat, llm_embed) are
        present as real actions, not just future_actions.
        """
        actions = openai_manifest_data["actions"]
        action_ids = {a["id"] for a in actions}

        assert "llm_run" in action_ids, "Should have llm_run action"
        assert "llm_chat" in action_ids, "Should have llm_chat action"
        assert "llm_embed" in action_ids, "Should have llm_embed action"

    def test_openai_has_health_check_action(self, openai_manifest_data):
        """Test: OpenAI has health_check action with health_monitoring category."""
        actions = openai_manifest_data["actions"]
        health_checks = [a for a in actions if a["id"] == "health_check"]

        assert len(health_checks) == 1, "Should have exactly one health_check action"

        health_check = health_checks[0]
        # type/purpose replaced by categories
        assert "health_monitoring" in health_check.get("categories", []), (
            "Should have health_monitoring category"
        )

    def test_openai_manifest_has_default_schedule(self, openai_manifest_data):
        """Test: OpenAI manifest has default schedule for health_check."""
        assert "default_schedules" in openai_manifest_data, (
            "Manifest should have default_schedules"
        )

        schedules = openai_manifest_data["default_schedules"]

        # Should have 1 default schedule
        assert len(schedules) == 1, f"Expected 1 default schedule, got {len(schedules)}"

        health_check_schedule = schedules[0]
        assert health_check_schedule["action_id"] == "health_check", (
            "Schedule should be for health_check"
        )
        assert health_check_schedule["schedule"] == "every/5m", (
            f"Expected every/5m, got {health_check_schedule['schedule']}"
        )
        assert health_check_schedule["enabled"] is True, (
            "Health check should be enabled"
        )
