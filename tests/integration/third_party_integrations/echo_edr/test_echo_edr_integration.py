"""
Integration tests for Echo EDR integration.

Tests IT-01 (Manifest Scanning) and IT-04 (Action Loading) from TEST_PLAN.md
using the real Echo EDR integration.
"""

import pytest

from analysi.integrations.framework.loader import IntegrationLoader
from analysi.integrations.framework.registry import (
    IntegrationRegistryService as IntegrationRegistryService,
)


@pytest.mark.integration
class TestEchoEDRManifestLoading:
    """Test IT-01: Manifest scanning and loading with Echo EDR."""

    def test_it_01_1_echo_edr_manifest_loads(self):
        """IT-01.1: Verify Echo EDR manifest loads from filesystem."""
        registry = IntegrationRegistryService()

        # Verify Echo EDR was loaded
        echo = registry.get_integration("echo_edr")

        assert echo is not None, "Echo EDR integration should be loaded"
        assert echo.id == "echo_edr"
        assert echo.name == "Echo EDR"
        assert echo.version == "1.0.0"

    def test_it_01_2_echo_edr_in_registry_list(self):
        """IT-01.2: Verify Echo EDR appears in list of all integrations."""
        registry = IntegrationRegistryService()

        all_integrations = registry.list_integrations()

        # Should have at least Echo EDR
        assert len(all_integrations) >= 1

        # Find Echo EDR
        echo = next((i for i in all_integrations if i.id == "echo_edr"), None)
        assert echo is not None, "Echo EDR should be in registry list"

    def test_it_01_5_echo_edr_actions_importable(self):
        """IT-01.5: Verify Echo EDR actions.py can be imported without errors."""
        # This will raise ImportError if there are syntax errors
        from analysi.integrations.framework.integrations.echo_edr import actions

        # Verify classes exist
        assert hasattr(actions, "HealthCheckAction")
        assert hasattr(actions, "PullProcessesAction")
        assert hasattr(actions, "PullBrowserHistoryAction")
        assert hasattr(actions, "IsolateHostAction")

    def test_echo_edr_has_required_fields(self):
        """Verify Echo EDR manifest has all required fields for Naxos framework."""
        registry = IntegrationRegistryService()
        echo = registry.get_integration("echo_edr")

        assert echo is not None

        # Check manifest structure
        manifest_dict = echo.model_dump()

        # Verify credential_schema exists
        assert "credential_schema" in manifest_dict
        assert "properties" in manifest_dict["credential_schema"]
        assert "api_key" in manifest_dict["credential_schema"]["properties"]

        # Verify settings_schema exists
        assert "settings_schema" in manifest_dict
        assert "properties" in manifest_dict["settings_schema"]
        assert "api_url" in manifest_dict["settings_schema"]["properties"]

        # Verify integration_id_config exists (moved from settings_schema in Naxos)
        assert "integration_id_config" in manifest_dict
        assert "default" in manifest_dict["integration_id_config"]
        assert "pattern" in manifest_dict["integration_id_config"]


@pytest.mark.integration
class TestEchoEDRActionLoading:
    """Test IT-04: Action loading and execution with Echo EDR."""

    @pytest.mark.asyncio
    async def test_it_04_1_load_and_execute_health_check(self):
        """IT-04.1: Load health_check action and execute it."""
        loader = IntegrationLoader()

        # Load health_check action
        action = await loader.load_action(
            integration_id="echo_edr",
            action_id="health_check",
            action_metadata={"type": "connector", "purpose": "health_monitoring"},
            settings={"api_url": "http://test-server:8000"},
            credentials={"api_key": "test-key-123"},
        )

        assert action is not None
        assert action.integration_id == "echo_edr"
        assert action.action_id == "health_check"
        assert action._action_type == "connector"

        # Execute it (will fail to connect, but should return proper error structure)
        result = await action.execute()

        assert "status" in result
        # Should be error since test-server doesn't exist
        assert result["status"] == "error"
        assert result["error_type"] == "ConnectionError"
        assert "error" in result
        assert "data" in result

    @pytest.mark.asyncio
    async def test_it_04_2_load_and_execute_tool_action(self):
        """IT-04.2: Load tool action (isolate_host) and execute it."""
        loader = IntegrationLoader()

        # Load isolate_host tool action
        action = await loader.load_action(
            integration_id="echo_edr",
            action_id="isolate_host",
            action_metadata={"type": "tool", "categories": ["response", "containment"]},
            settings={"api_url": "http://test-server:8000"},
            credentials={"api_key": "test-key-123"},
        )

        assert action is not None
        assert action._action_type == "tool"

        # Execute it
        result = await action.execute(hostname="test-host")

        assert result["status"] == "success"
        assert result["hostname"] == "test-host"

    @pytest.mark.asyncio
    async def test_it_04_3_load_nonexistent_action_class(self):
        """IT-04.3: Attempt to load action with missing implementation."""
        loader = IntegrationLoader()

        # Try to load an action that doesn't exist
        with pytest.raises(ValueError, match="Action class.*not found"):
            await loader.load_action(
                integration_id="echo_edr",
                action_id="nonexistent_action",
                action_metadata={"type": "connector"},
                settings={},
                credentials={},
            )

    @pytest.mark.asyncio
    async def test_it_04_4_settings_injection(self):
        """IT-04.4: Verify settings are injected correctly into action."""
        loader = IntegrationLoader()

        settings = {
            "api_url": "http://custom-server:9000",
            "timeout": 60,
            "custom_field": "custom_value",
        }

        action = await loader.load_action(
            integration_id="echo_edr",
            action_id="health_check",
            action_metadata={"type": "connector"},
            settings=settings,
            credentials={},
        )

        # Verify settings were injected
        assert action.settings == settings
        assert action.settings["api_url"] == "http://custom-server:9000"
        assert action.settings["timeout"] == 60
        assert action.settings["custom_field"] == "custom_value"

    @pytest.mark.asyncio
    async def test_it_04_5_credentials_injection(self):
        """IT-04.5: Verify credentials are injected correctly into action."""
        loader = IntegrationLoader()

        credentials = {
            "api_key": "super-secret-key-12345",
            "additional_field": "additional_value",
        }

        action = await loader.load_action(
            integration_id="echo_edr",
            action_id="health_check",
            action_metadata={"type": "connector"},
            settings={},
            credentials=credentials,
        )

        # Verify credentials were injected
        assert action.credentials == credentials
        assert action.credentials["api_key"] == "super-secret-key-12345"
        assert action.credentials["additional_field"] == "additional_value"


@pytest.mark.integration
class TestEchoEDREDRArchetype:
    """Test Echo EDR implements EDR archetype correctly."""

    def test_echo_edr_implements_edr_archetype(self):
        """Verify Echo EDR implements the EDR archetype."""
        registry = IntegrationRegistryService()
        echo = registry.get_integration("echo_edr")

        assert echo is not None
        assert "EDR" in echo.archetypes

    def test_echo_edr_archetype_mappings_complete(self):
        """Verify all 8 required EDR archetype methods are mapped."""
        registry = IntegrationRegistryService()
        echo = registry.get_integration("echo_edr")

        assert echo is not None
        assert "EDR" in echo.archetype_mappings

        edr_mappings = echo.archetype_mappings["EDR"]

        # Verify all 8 required methods
        required_methods = [
            "pull_processes",
            "pull_network_connections",
            "pull_browser_history",
            "pull_terminal_history",
            "isolate_host",
            "release_host",
            "scan_host",
            "get_host_details",
        ]

        for method in required_methods:
            assert method in edr_mappings, f"Missing EDR method: {method}"

    def test_echo_edr_archetype_actions_exist(self):
        """Verify all mapped archetype actions exist in actions list."""
        registry = IntegrationRegistryService()
        echo = registry.get_integration("echo_edr")

        assert echo is not None

        edr_mappings = echo.archetype_mappings["EDR"]
        action_ids = {action.id for action in echo.actions}

        # Verify each mapped action exists
        for method, action_id in edr_mappings.items():
            assert action_id in action_ids, (
                f"Archetype mapping {method} → {action_id} points to non-existent action"
            )

    def test_resolve_edr_archetype_method(self):
        """Test resolving EDR archetype method to action ID."""
        registry = IntegrationRegistryService()

        # Resolve pull_processes method
        action_id = registry.resolve_archetype_action(
            "echo_edr", "EDR", "pull_processes"
        )

        assert action_id == "pull_processes"

        # Resolve isolate_host method
        action_id = registry.resolve_archetype_action("echo_edr", "EDR", "isolate_host")

        assert action_id == "isolate_host"


@pytest.mark.integration
class TestEchoEDRMultiInstance:
    """Test multi-instance support for Echo EDR integration."""

    @pytest.mark.asyncio
    async def test_multiple_instances_same_tenant(self):
        """
        Test loading actions for multiple instances of same integration type
        within the same tenant (e.g., prod vs dev Echo EDR servers).
        """
        loader = IntegrationLoader()

        # Instance 1: Production Echo EDR
        action_prod = await loader.load_action(
            integration_id="echo_edr",
            action_id="health_check",
            action_metadata={"type": "connector", "purpose": "health_monitoring"},
            settings={"api_url": "http://echo-prod:8000", "environment": "production"},
            credentials={"api_key": "prod-key-12345"},
            ctx={"tenant_id": "tenant-acme", "integration_id": "echo-prod"},
        )

        # Instance 2: Development Echo EDR (same tenant, different instance)
        action_dev = await loader.load_action(
            integration_id="echo_edr",
            action_id="health_check",
            action_metadata={"type": "connector", "purpose": "health_monitoring"},
            settings={"api_url": "http://echo-dev:8000", "environment": "development"},
            credentials={"api_key": "dev-key-67890"},
            ctx={"tenant_id": "tenant-acme", "integration_id": "echo-dev"},
        )

        # Verify both actions are independent instances
        assert action_prod is not action_dev
        assert action_prod.settings["api_url"] == "http://echo-prod:8000"
        assert action_dev.settings["api_url"] == "http://echo-dev:8000"
        assert action_prod.credentials["api_key"] == "prod-key-12345"
        assert action_dev.credentials["api_key"] == "dev-key-67890"
        assert action_prod.tenant_id == "tenant-acme"
        assert action_dev.tenant_id == "tenant-acme"

    @pytest.mark.asyncio
    async def test_multiple_tenants_same_integration_type(self):
        """
        Test loading actions for different tenants using the same
        integration type (multi-tenancy isolation).
        """
        loader = IntegrationLoader()

        # Tenant 1: ACME Corp
        action_acme = await loader.load_action(
            integration_id="echo_edr",
            action_id="health_check",
            action_metadata={"type": "connector", "purpose": "health_monitoring"},
            settings={"api_url": "http://acme-edr:8000"},
            credentials={"api_key": "acme-key"},
            ctx={"tenant_id": "tenant-acme", "integration_id": "echo-edr-main"},
        )

        # Tenant 2: Beta Inc
        action_beta = await loader.load_action(
            integration_id="echo_edr",
            action_id="health_check",
            action_metadata={"type": "connector", "purpose": "health_monitoring"},
            settings={"api_url": "http://beta-edr:8000"},
            credentials={"api_key": "beta-key"},
            ctx={"tenant_id": "tenant-beta", "integration_id": "echo-edr-main"},
        )

        # Verify tenant isolation
        assert action_acme is not action_beta
        assert action_acme.tenant_id == "tenant-acme"
        assert action_beta.tenant_id == "tenant-beta"
        assert action_acme.settings["api_url"] == "http://acme-edr:8000"
        assert action_beta.settings["api_url"] == "http://beta-edr:8000"
        assert action_acme.credentials["api_key"] == "acme-key"
        assert action_beta.credentials["api_key"] == "beta-key"

    @pytest.mark.asyncio
    async def test_action_execution_isolation_between_instances(self):
        """
        Test that executing actions on different instances doesn't
        interfere with each other (settings/credentials isolation).
        """
        loader = IntegrationLoader()

        # Load two instances with different API URLs
        action1 = await loader.load_action(
            integration_id="echo_edr",
            action_id="health_check",
            action_metadata={"type": "connector", "purpose": "health_monitoring"},
            settings={"api_url": "http://instance1:8000"},
            credentials={"api_key": "key1"},
            ctx={"tenant_id": "tenant1", "integration_id": "echo1"},
        )

        action2 = await loader.load_action(
            integration_id="echo_edr",
            action_id="health_check",
            action_metadata={"type": "connector", "purpose": "health_monitoring"},
            settings={"api_url": "http://instance2:8000"},
            credentials={"api_key": "key2"},
            ctx={"tenant_id": "tenant1", "integration_id": "echo2"},
        )

        # Execute both (will fail to connect, but should use different URLs)
        result1 = await action1.execute()
        result2 = await action2.execute()

        # Verify each action used its own settings (new error format)
        assert result1["status"] == "error"  # Can't connect to test servers
        assert result2["status"] == "error"
        assert "instance1:8000" in result1["data"]["endpoint"]
        assert "instance2:8000" in result2["data"]["endpoint"]

    @pytest.mark.asyncio
    async def test_different_actions_same_integration_different_instances(self):
        """
        Test loading different actions from same integration type
        across different instances.
        """
        loader = IntegrationLoader()

        # Instance 1: Execute health_check
        health_action = await loader.load_action(
            integration_id="echo_edr",
            action_id="health_check",
            action_metadata={"type": "connector", "purpose": "health_monitoring"},
            settings={"api_url": "http://instance1:8000"},
            credentials={"api_key": "key1"},
            ctx={"tenant_id": "tenant1", "integration_id": "echo-instance1"},
        )

        # Instance 2: Execute isolate_host (different action, different instance)
        isolate_action = await loader.load_action(
            integration_id="echo_edr",
            action_id="isolate_host",
            action_metadata={"type": "tool", "categories": ["response"]},
            settings={"api_url": "http://instance2:8000"},
            credentials={"api_key": "key2"},
            ctx={"tenant_id": "tenant1", "integration_id": "echo-instance2"},
        )

        # Verify both loaded correctly
        assert health_action.action_id == "health_check"
        assert isolate_action.action_id == "isolate_host"
        assert health_action._action_type == "connector"
        assert isolate_action._action_type == "tool"
        assert health_action.settings["api_url"] == "http://instance1:8000"
        assert isolate_action.settings["api_url"] == "http://instance2:8000"

    @pytest.mark.asyncio
    async def test_context_preservation_across_instances(self):
        """
        Test that execution context is properly preserved for each
        instance (job_id, run_id, etc.).
        """
        loader = IntegrationLoader()

        # Instance 1 with specific context
        ctx1 = {
            "tenant_id": "tenant-acme",
            "integration_id": "echo-prod",
            "job_id": "job-123",
            "run_id": "run-456",
        }
        action1 = await loader.load_action(
            integration_id="echo_edr",
            action_id="health_check",
            action_metadata={"type": "connector", "purpose": "health_monitoring"},
            settings={"api_url": "http://prod:8000"},
            credentials={"api_key": "prod-key"},
            ctx=ctx1,
        )

        # Instance 2 with different context
        ctx2 = {
            "tenant_id": "tenant-acme",
            "integration_id": "echo-dev",
            "job_id": "job-789",
            "run_id": "run-012",
        }
        action2 = await loader.load_action(
            integration_id="echo_edr",
            action_id="health_check",
            action_metadata={"type": "connector", "purpose": "health_monitoring"},
            settings={"api_url": "http://dev:8000"},
            credentials={"api_key": "dev-key"},
            ctx=ctx2,
        )

        # Verify context is preserved independently
        assert action1.ctx == ctx1
        assert action2.ctx == ctx2
        assert action1.job_id == "job-123"
        assert action2.job_id == "job-789"
        assert action1.run_id == "run-456"
        assert action2.run_id == "run-012"
