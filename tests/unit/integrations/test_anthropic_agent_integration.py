"""Unit tests for anthropic_agent integration.

Tests the anthropic_agent integration that provides OAuth tokens for Claude Code SDK.
"""

from analysi.integrations.framework.integrations.anthropic_agent.actions import (
    health_check,
)


class TestAnthropicAgentHealthCheck:
    """Test anthropic_agent health_check action."""

    def test_health_check_success(self):
        """Test health check returns healthy with valid token."""
        credentials = {"oauth_token": "sk-ant-valid-token-12345"}
        settings = {"max_turns": 100, "permission_mode": "bypassPermissions"}
        params = {}

        result = health_check(credentials, settings, params)

        assert isinstance(result, dict)
        assert result["status"] == "success"
        assert result["data"]["status"] == "healthy"
        assert result["data"]["token_configured"] is True
        # Token should be partially masked
        assert result["data"]["token_prefix"] == "sk-ant-val..."
        assert "timestamp" in result

    def test_health_check_missing_token(self):
        """Test health check returns error when no token configured."""
        credentials = {}  # No oauth_token
        settings = {}
        params = {}

        result = health_check(credentials, settings, params)

        assert result["status"] == "error"
        assert result["error_type"] == "configuration_error"
        assert (
            "oauth_token" in result["error"].lower()
            or "missing" in result["error"].lower()
        )
        assert result["data"]["error"] == "OAuth token not configured"

    def test_health_check_empty_token(self):
        """Test health check returns error for empty token."""
        credentials = {"oauth_token": ""}
        settings = {}
        params = {}

        result = health_check(credentials, settings, params)

        assert result["status"] == "error"
        assert (
            "oauth_token" in result["error"].lower()
            or "missing" in result["error"].lower()
        )

    def test_health_check_invalid_format(self):
        """Test health check returns error for invalid token format."""
        credentials = {"oauth_token": "invalid-token-no-prefix"}
        settings = {}
        params = {}

        result = health_check(credentials, settings, params)

        assert result["status"] == "error"
        assert result["error_type"] == "validation_error"
        assert "sk-ant-" in result["error"]
        assert result["data"]["error"] == "Invalid token format"

    def test_health_check_returns_settings(self):
        """Test health check includes settings in response."""
        credentials = {"oauth_token": "sk-ant-valid-12345"}
        settings = {"max_turns": 200, "permission_mode": "requirePermissions"}
        params = {}

        result = health_check(credentials, settings, params)

        assert result["status"] == "success"
        assert result["data"]["settings"]["max_turns"] == 200
        assert result["data"]["settings"]["permission_mode"] == "requirePermissions"

    def test_health_check_uses_default_settings(self):
        """Test health check uses default settings when not provided."""
        credentials = {"oauth_token": "sk-ant-valid-12345"}
        settings = {}  # Empty settings
        params = {}

        result = health_check(credentials, settings, params)

        assert result["status"] == "success"
        # Should use defaults
        assert result["data"]["settings"]["max_turns"] == 100
        assert result["data"]["settings"]["permission_mode"] == "bypassPermissions"


class TestAnthropicAgentManifest:
    """Test anthropic_agent manifest configuration."""

    @staticmethod
    def _get_manifest_path():
        """Get path to manifest.json relative to project root."""
        import os
        from pathlib import Path

        # Find project root by looking for pyproject.toml
        current = Path(__file__).resolve()
        while current.parent != current:
            if (current / "pyproject.toml").exists():
                return (
                    current
                    / "src"
                    / "analysi"
                    / "integrations"
                    / "framework"
                    / "integrations"
                    / "anthropic_agent"
                    / "manifest.json"
                )
            current = current.parent
        # Fallback
        return (
            Path(os.environ.get("ANALYSI_ROOT", "."))
            / "src"
            / "analysi"
            / "integrations"
            / "framework"
            / "integrations"
            / "anthropic_agent"
            / "manifest.json"
        )

    def test_manifest_loads_correctly(self):
        """Test that manifest can be loaded by the registry."""
        import json

        manifest_path = self._get_manifest_path()

        assert manifest_path.exists(), f"Manifest not found at {manifest_path}"

        with open(manifest_path) as f:
            manifest = json.load(f)

        assert manifest is not None
        assert "id" in manifest

    def test_manifest_has_required_fields(self):
        """Test manifest contains all required fields."""
        import json

        manifest_path = self._get_manifest_path()

        with open(manifest_path) as f:
            manifest = json.load(f)

        # Required fields
        assert manifest["id"] == "anthropic_agent"
        assert "name" in manifest
        assert "version" in manifest
        assert "archetypes" in manifest
        assert "AgenticFramework" in manifest["archetypes"]

        # Credential schema
        assert "credential_schema" in manifest
        cred_schema = manifest["credential_schema"]
        assert "properties" in cred_schema
        assert "oauth_token" in cred_schema["properties"]

        # Settings schema
        assert "settings_schema" in manifest
        settings_schema = manifest["settings_schema"]
        assert "properties" in settings_schema
        assert "max_turns" in settings_schema["properties"]
        assert "permission_mode" in settings_schema["properties"]

    def test_manifest_oauth_token_is_password_type(self):
        """Test oauth_token is marked as password for secure handling."""
        import json

        manifest_path = self._get_manifest_path()

        with open(manifest_path) as f:
            manifest = json.load(f)

        oauth_token_schema = manifest["credential_schema"]["properties"]["oauth_token"]
        assert oauth_token_schema["format"] == "password"
        # oauth_token is optional (no "required" key) — only api_key is required
        assert "required" not in oauth_token_schema

    def test_manifest_has_health_check_action(self):
        """Test manifest declares health_check action."""
        import json

        manifest_path = self._get_manifest_path()

        with open(manifest_path) as f:
            manifest = json.load(f)

        assert "actions" in manifest
        action_ids = [a["id"] for a in manifest["actions"]]
        assert "health_check" in action_ids
