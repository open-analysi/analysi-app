"""
Unit tests for integration settings module.

NOTE: All integrations now use Naxos framework with manifest-based validation.
These tests verify that the legacy functions return None (no Python validation).
"""

from analysi.schemas.integration_settings import (
    get_settings_model,
    validate_integration_settings,
)


class TestNaxosFrameworkIntegrations:
    """Test that all integrations use manifest-based validation."""

    def test_get_settings_model_returns_none(self):
        """Test that get_settings_model returns None for all integrations."""
        assert get_settings_model("splunk") is None
        assert get_settings_model("echo_edr") is None
        assert get_settings_model("openai") is None
        assert get_settings_model("virustotal") is None
        assert get_settings_model("unknown") is None

    def test_validate_integration_settings_returns_none(self):
        """Test that validate_integration_settings returns None for all integrations."""
        settings_dict = {"host": "example.com", "port": 8089}

        assert validate_integration_settings("splunk", settings_dict) is None
        assert validate_integration_settings("echo_edr", {}) is None
        assert validate_integration_settings("openai", {}) is None
        assert validate_integration_settings("virustotal", {}) is None
