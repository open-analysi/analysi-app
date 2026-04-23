"""
Unit tests for Splunk action loader.

Tests dynamic action loading for Splunk integration.
Following TDD - these tests will fail until implementations are complete.
"""

import pytest

from analysi.integrations.framework.integrations.splunk.actions import (
    GetIndexStatsAction,
    HealthCheckAction,
    ListDatamodelsAction,
    ListIndexesAction,
    ListSavedSearchesAction,
    PullAlertsAction,
    SendEventsAction,
    SourcetypeDiscoveryAction,
    UpdateNotableAction,
)
from analysi.integrations.framework.loader import IntegrationLoader


class TestSplunkActionLoader:
    """Test loading Splunk actions via IntegrationLoader."""

    @pytest.mark.asyncio
    async def test_load_splunk_health_check_action(self):
        """Test: Load Splunk HealthCheckAction via loader.

        Goal: Verify IntegrationLoader can dynamically instantiate Splunk health_check action.
        """
        loader = IntegrationLoader()

        action = await loader.load_action(
            integration_id="splunk",
            action_id="health_check",
            action_metadata={"type": "connector", "purpose": "health_monitoring"},
            settings={"host": "splunk.example.com", "port": 8089},
            credentials={"username": "admin", "password": "changeme"},
        )

        # Should be correct action class
        assert isinstance(action, HealthCheckAction), (
            f"Expected HealthCheckAction, got {type(action)}"
        )

        # Should have credentials and settings injected
        assert action.credentials == {"username": "admin", "password": "changeme"}
        assert action.settings == {"host": "splunk.example.com", "port": 8089}
        assert action.integration_id == "splunk"
        assert action.action_id == "health_check"

    @pytest.mark.asyncio
    async def test_load_all_splunk_actions(self):
        """Test: Load all 9 Splunk actions via loader.

        Goal: Ensure loader can instantiate all Splunk actions dynamically.
        """
        loader = IntegrationLoader()

        # Define all 9 Splunk actions with their expected classes
        action_configs = [
            (
                "health_check",
                HealthCheckAction,
                {"type": "connector", "purpose": "health_monitoring"},
            ),
            (
                "pull_alerts",
                PullAlertsAction,
                {"type": "connector", "purpose": "alert_ingestion"},
            ),
            ("update_notable", UpdateNotableAction, {"type": "tool"}),
            ("send_events", SendEventsAction, {"type": "tool"}),
            ("list_datamodels", ListDatamodelsAction, {"type": "tool"}),
            ("list_saved_searches", ListSavedSearchesAction, {"type": "tool"}),
            ("get_index_stats", GetIndexStatsAction, {"type": "tool"}),
            ("sourcetype_discovery", SourcetypeDiscoveryAction, {"type": "tool"}),
            ("list_indexes", ListIndexesAction, {"type": "tool"}),
        ]

        for action_id, expected_class, metadata in action_configs:
            action = await loader.load_action(
                integration_id="splunk",
                action_id=action_id,
                action_metadata=metadata,
                settings={},
                credentials={},
            )

            assert isinstance(action, expected_class), (
                f"Action {action_id} should be {expected_class.__name__}, got {type(action).__name__}"
            )

            # Verify base class
            from analysi.integrations.framework.base import IntegrationAction

            assert isinstance(action, IntegrationAction), (
                f"Action {action_id} should inherit from IntegrationAction"
            )

    @pytest.mark.asyncio
    async def test_splunk_action_loader_with_invalid_action_id(self):
        """Test: Splunk action loader with invalid action_id.

        Goal: Verify loader handles unknown action_id gracefully.
        """
        loader = IntegrationLoader()

        with pytest.raises(ValueError, match="Action class .* not found"):
            await loader.load_action(
                integration_id="splunk",
                action_id="nonexistent_action",
                action_metadata={"type": "tool"},
                settings={},
                credentials={},
            )

    @pytest.mark.asyncio
    async def test_splunk_action_receives_credential_injection(self):
        """Test: Splunk action receives credential injection.

        Goal: Ensure loaded actions receive decrypted credentials.
        """
        loader = IntegrationLoader()

        credentials = {"username": "splunk_admin", "password": "secure_password_123"}

        action = await loader.load_action(
            integration_id="splunk",
            action_id="health_check",
            action_metadata={"type": "connector"},
            settings={},
            credentials=credentials,
        )

        # Verify credentials were injected
        assert action.credentials == credentials
        assert action.credentials["username"] == "splunk_admin"
        assert action.credentials["password"] == "secure_password_123"

    @pytest.mark.asyncio
    async def test_splunk_action_receives_settings_hierarchy(self):
        """Test: Splunk action receives settings hierarchy.

        Goal: Verify actions receive both integration settings and instance settings.
        """
        loader = IntegrationLoader()

        settings = {"host": "splunk.production.com", "port": 8089, "verify_ssl": True}

        action = await loader.load_action(
            integration_id="splunk",
            action_id="pull_alerts",
            action_metadata={"type": "connector"},
            settings=settings,
            credentials={},
        )

        # Verify settings were injected
        assert action.settings == settings
        assert action.settings.get("host") == "splunk.production.com"
        assert action.settings.get("port") == 8089
        assert action.settings.get("verify_ssl") is True

    @pytest.mark.asyncio
    async def test_splunk_tool_action_loading(self):
        """Test: Splunk tool actions load correctly."""
        loader = IntegrationLoader()

        # Test one tool action specifically
        action = await loader.load_action(
            integration_id="splunk",
            action_id="update_notable",
            action_metadata={"type": "tool", "categories": ["response", "siem"]},
            settings={},
            credentials={"username": "admin", "password": "pass"},
        )

        assert isinstance(action, UpdateNotableAction)
        assert action.action_id == "update_notable"
        assert action.integration_id == "splunk"

    @pytest.mark.asyncio
    async def test_splunk_connector_action_loading(self):
        """Test: Splunk connector actions load correctly."""
        loader = IntegrationLoader()

        # Test connector action specifically
        action = await loader.load_action(
            integration_id="splunk",
            action_id="pull_alerts",
            action_metadata={"type": "connector", "purpose": "alert_ingestion"},
            settings={"host": "localhost"},
            credentials={"username": "admin", "password": "pass"},
        )

        assert isinstance(action, PullAlertsAction)
        assert action.action_id == "pull_alerts"
        assert action.integration_id == "splunk"
