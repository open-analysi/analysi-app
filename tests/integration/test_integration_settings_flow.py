"""
Integration tests for integration settings flow.
"""

from uuid import uuid4

import pytest

from analysi.repositories.integration_repository import IntegrationRepository
from analysi.schemas.integration import IntegrationCreate, IntegrationUpdate
from analysi.services.integration_service import IntegrationService


@pytest.mark.integration
class TestIntegrationSettingsFlow:
    """Test the complete integration settings flow."""

    @pytest.fixture
    async def integration_service(self, integration_test_session):
        """Create IntegrationService for testing."""

        integration_repo = IntegrationRepository(integration_test_session)

        return IntegrationService(
            integration_repo=integration_repo,
        )

    @pytest.fixture
    async def splunk_integration(self, integration_test_session):
        """Create a Splunk integration with settings."""
        repo = IntegrationRepository(integration_test_session)
        integration = await repo.create_integration(
            tenant_id="test-tenant",
            integration_id="splunk-test",
            integration_type="splunk",
            name="Test Splunk",
            description="Test Splunk with connector settings",
            settings={
                "host": "splunk.test.com",
                "port": 8089,
                "verify_ssl": False,
                "connectors": {
                    "pull_alerts": {"enabled": True, "max_results": 500},
                    "send_events": {
                        "enabled": False,
                        "port": 8088,
                        "hec_token": "test-token",
                    },
                },
            },
            enabled=True,
        )
        await integration_test_session.commit()
        return integration

    @pytest.mark.asyncio
    async def test_create_integration_with_typed_settings(self, integration_service):
        """Test creating integration with Pydantic-validated settings."""
        # Arrange
        data = IntegrationCreate(
            integration_id="splunk-typed",
            integration_type="splunk",
            name="Typed Splunk",
            description="Splunk with typed settings",
            settings={
                "host": "splunk.example.com",
                "port": 8089,
                "connectors": {
                    "pull_alerts": {
                        "enabled": True,
                        "credential_id": str(uuid4()),  # Must be string for JSON
                    }
                },
            },
        )

        # Act
        result = await integration_service.create_integration("test-tenant", data)

        # Assert
        assert result.integration_id == "splunk-typed"
        assert result.settings["host"] == "splunk.example.com"
        assert result.settings["port"] == 8089
        assert "connectors" in result.settings
        assert result.settings["connectors"]["pull_alerts"]["enabled"] is True

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Python validation removed - Naxos framework uses manifest-based validation"
    )
    async def test_create_integration_invalid_settings_fails(self, integration_service):
        """Test that invalid settings are rejected.

        NOTE: This test is skipped because all integrations now use Naxos framework
        with manifest-based validation. Python Pydantic validation has been removed.
        Settings validation is now performed by the manifest's JSON schema.
        """
        from pydantic import ValidationError

        # Act & Assert - port out of range
        with pytest.raises(ValidationError) as exc_info:
            IntegrationCreate(
                integration_id="splunk-invalid",
                integration_type="splunk",
                name="Invalid Splunk",
                settings={
                    "host": "splunk.example.com",
                    "port": 70000,  # Invalid port
                },
            )

        # Check that the error contains information about invalid settings
        error_str = str(exc_info.value)
        assert "Invalid settings" in error_str or "port" in error_str.lower()

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Python validation removed - Naxos framework uses manifest-based validation"
    )
    async def test_create_integration_missing_required_field_fails(
        self, integration_service
    ):
        """Test that missing required fields are rejected.

        NOTE: This test is skipped because all integrations now use Naxos framework
        with manifest-based validation. Python Pydantic validation has been removed.
        Settings validation is now performed by the manifest's JSON schema.
        """
        from pydantic import ValidationError

        # Act & Assert - missing host
        with pytest.raises(ValidationError) as exc_info:
            IntegrationCreate(
                integration_id="splunk-no-host",
                integration_type="splunk",
                name="No Host Splunk",
                settings={
                    "port": 8089  # Missing required host
                },
            )

        # Check that the error contains information about the missing field
        error_str = str(exc_info.value)
        assert "Invalid settings" in error_str or "host" in error_str.lower()

    @pytest.mark.asyncio
    async def test_update_integration_settings_validation(
        self, integration_service, splunk_integration
    ):
        """Test that settings are validated on update."""
        # Arrange
        update_data = IntegrationUpdate(
            settings={
                "host": "new.splunk.com",
                "port": 9000,
                "connectors": {"health_check": {"enabled": True, "timeout": 45}},
            }
        )

        # Act
        result = await integration_service.update_integration(
            "test-tenant", "splunk-test", update_data
        )

        # Assert
        assert result is not None
        assert result.settings["host"] == "new.splunk.com"
        assert result.settings["port"] == 9000
        assert result.settings["connectors"]["health_check"]["timeout"] == 45

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Python validation removed - Naxos framework uses manifest-based validation"
    )
    async def test_update_integration_invalid_settings_fails(
        self, integration_service, splunk_integration
    ):
        """Test that invalid settings are rejected on update.

        NOTE: This test is skipped because all integrations now use Naxos framework
        with manifest-based validation. Python Pydantic validation has been removed.
        Settings validation is now performed by the manifest's JSON schema.
        """
        # Arrange - invalid port
        update_data = IntegrationUpdate(
            settings={
                "host": "splunk.test.com",
                "port": -1,  # Invalid port
            }
        )

        # Act & Assert
        with pytest.raises(ValueError) as exc_info:
            await integration_service.update_integration(
                "test-tenant", "splunk-test", update_data
            )

        assert "Invalid settings" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_connector_specific_override_preserved(
        self, integration_test_session, splunk_integration
    ):
        """Test that connector-specific overrides are preserved."""
        # Arrange
        repo = IntegrationRepository(integration_test_session)

        # Act
        integration = await repo.get_integration("test-tenant", "splunk-test")

        # Assert
        assert integration is not None
        settings = integration.settings

        # Base settings
        assert settings["host"] == "splunk.test.com"
        assert settings["port"] == 8089

        # Connector overrides
        assert settings["connectors"]["pull_alerts"]["enabled"] is True
        assert settings["connectors"]["pull_alerts"]["max_results"] == 500
        assert settings["connectors"]["send_events"]["port"] == 8088
        assert settings["connectors"]["send_events"]["hec_token"] == "test-token"

    @pytest.mark.asyncio
    async def test_echo_edr_settings_validation(self, integration_service):
        """Test Echo EDR integration with different settings structure."""
        # Arrange
        data = IntegrationCreate(
            integration_id="echo-test",
            integration_type="echo_edr",
            name="Test Echo EDR",
            settings={
                "api_url": "https://api.echoedr.test",
                "timeout": 45,
                "connectors": {
                    "isolate_endpoint": {
                        "enabled": True,
                        "require_approval": True,
                        "auto_reconnect_hours": 24,
                    }
                },
            },
        )

        # Act
        result = await integration_service.create_integration("test-tenant", data)

        # Assert
        assert result.integration_id == "echo-test"
        assert result.settings["api_url"] == "https://api.echoedr.test"
        assert result.settings["timeout"] == 45
        assert (
            result.settings["connectors"]["isolate_endpoint"]["require_approval"]
            is True
        )

    @pytest.mark.asyncio
    async def test_settings_hierarchy_in_database(self, integration_test_session):
        """Test that settings hierarchy is correctly stored in database."""
        # Arrange
        repo = IntegrationRepository(integration_test_session)

        # Create integration with complex settings
        await repo.create_integration(
            tenant_id="test-tenant",
            integration_id="splunk-hierarchy",
            integration_type="splunk",
            name="Hierarchy Test",
            settings={
                "host": "base.splunk.com",
                "port": 8089,
                "verify_ssl": True,
                "connectors": {
                    "pull_alerts": {
                        "enabled": True,
                        "host": "alerts.splunk.com",  # Override host
                        "port": 8090,  # Override port
                        "credential_id": str(uuid4()),
                    },
                    "send_events": {
                        "enabled": True,
                        "port": 8088,  # Override port only
                        # host will use base setting
                    },
                },
            },
            enabled=True,
        )
        await integration_test_session.commit()

        # Act - retrieve and check
        retrieved = await repo.get_integration("test-tenant", "splunk-hierarchy")

        # Assert
        assert retrieved is not None
        settings = retrieved.settings

        # Base settings
        assert settings["host"] == "base.splunk.com"
        assert settings["port"] == 8089
        assert settings["verify_ssl"] is True

        # Connector overrides
        pull_alerts = settings["connectors"]["pull_alerts"]
        assert pull_alerts["host"] == "alerts.splunk.com"  # Overridden
        assert pull_alerts["port"] == 8090  # Overridden

        send_events = settings["connectors"]["send_events"]
        assert send_events["port"] == 8088  # Overridden
        assert "host" not in send_events  # Uses base

    @pytest.mark.asyncio
    async def test_partial_settings_update(
        self, integration_service, splunk_integration
    ):
        """Test that settings update replaces the whole settings dict."""
        # Arrange - settings update is a full replace, not a deep merge
        update_data = IntegrationUpdate(
            settings={
                "host": "splunk.test.com",
                "port": 8089,
                "connectors": {"health_check": {"enabled": True, "timeout": 15}},
            }
        )

        # Act
        result = await integration_service.update_integration(
            "test-tenant", "splunk-test", update_data
        )

        # Assert
        assert result is not None

        # New connector present
        assert result.settings["connectors"]["health_check"]["timeout"] == 15

        # Settings is a full replace — only the connectors we sent are present
        assert "pull_alerts" not in result.settings["connectors"]
        assert "send_events" not in result.settings["connectors"]
