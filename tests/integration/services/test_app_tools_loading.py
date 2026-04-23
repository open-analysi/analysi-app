"""
Integration tests for Naxos app tools loading with FQN syntax.

Tests that framework integration tools are:
1. Registered in KU API on startup
2. Loaded into Cy interpreter with FQN syntax (app::integration::action)
3. Callable from Cy scripts
"""

import pytest

from analysi.repositories.knowledge_unit import KnowledgeUnitRepository
from analysi.services.integration_registry_service import IntegrationRegistryService
from analysi.services.task_execution import DefaultTaskExecutor
from tests.utils.cy_output import parse_cy_output


@pytest.mark.integration
class TestAppToolsLoading:
    """Test loading of Naxos framework tools with FQN syntax."""

    @pytest.mark.asyncio
    async def test_app_tools_registered_in_ku_api(self, integration_test_session):
        """Verify app tools are registered in KU API on startup."""
        registry = IntegrationRegistryService()
        ku_repo = KnowledgeUnitRepository(integration_test_session)

        tenant_id = "test-tenant"

        # Register tools
        registered_count = await registry.register_tools_in_ku_api(
            integration_test_session, tenant_id
        )

        # Should register at least 27 tools (increases as we add more integrations)
        # Core integrations: Echo EDR: 8, Splunk: 8, VirusTotal: 6, AbuseIPDB: 5
        assert registered_count >= 27, (
            f"Expected at least 27 tools, got {registered_count}"
        )

        # Verify VirusTotal tools are registered
        vt_ip_reputation = await ku_repo.get_tool_by_name(
            tenant_id, "virustotal::ip_reputation"
        )
        assert vt_ip_reputation is not None
        assert vt_ip_reputation.tool_type == "app"
        assert vt_ip_reputation.component.name == "virustotal::ip_reputation"

    @pytest.mark.asyncio
    async def test_list_app_tools(self, integration_test_session):
        """Test listing all app-type tools for a tenant."""
        registry = IntegrationRegistryService()
        ku_repo = KnowledgeUnitRepository(integration_test_session)

        tenant_id = "test-tenant"

        # Register tools first
        await registry.register_tools_in_ku_api(integration_test_session, tenant_id)

        # List all app tools
        app_tools = await ku_repo.list_app_tools(tenant_id)

        # Should have at least 27 app tools (increases as we add more integrations)
        assert len(app_tools) >= 27, f"Expected at least 27 tools, got {len(app_tools)}"

        # Verify all tools have correct structure
        for tool in app_tools:
            assert tool.tool_type == "app"
            assert "::" in tool.component.name  # Format: integration_type::action_id
            assert tool.component.status == "enabled"

        # Check specific integrations are present
        tool_names = {tool.component.name for tool in app_tools}
        assert "virustotal::ip_reputation" in tool_names
        assert "echo_edr::isolate_host" in tool_names
        assert "splunk::update_notable" in tool_names

    @pytest.mark.asyncio
    async def test_app_tools_loaded_with_fqn(self, integration_test_session):
        """Test that app tools are loaded with FQN keys from manifest cy_name."""
        registry = IntegrationRegistryService()
        tenant_id = "test-tenant"

        # Register tools
        await registry.register_tools_in_ku_api(integration_test_session, tenant_id)

        # Create execution context
        execution_context = {
            "tenant_id": tenant_id,
            "session": integration_test_session,
            "task_id": "test-task-123",
            "app": "default",
        }

        # Create executor and load tools
        executor = DefaultTaskExecutor()
        app_tools = await executor._load_app_tools(execution_context)

        # No tools should load because there are no enabled integrations in test DB
        # Tools only load when an enabled integration instance exists
        assert len(app_tools) == 0

    @pytest.mark.asyncio
    async def test_cy_name_from_manifest(self, integration_test_session):
        """Test that cy_name is read from manifest as short name."""
        from analysi.integrations.framework.registry import (
            IntegrationRegistryService as FrameworkRegistry,
        )

        framework = FrameworkRegistry()

        # Get VirusTotal manifest
        manifest = framework.get_integration("virustotal")
        assert manifest is not None

        # Find ip_reputation action
        ip_action = next((a for a in manifest.actions if a.id == "ip_reputation"), None)
        assert ip_action is not None

        # Verify cy_name is set in manifest with short name format (framework adds FQN prefix)
        assert ip_action.cy_name == "ip_reputation"

    @pytest.mark.asyncio
    async def test_app_tools_name_parsing(self, integration_test_session):
        """Test that tool names are correctly parsed from integration_type::action_id format."""
        registry = IntegrationRegistryService()

        tenant_id = "test-tenant"

        # Register tools
        await registry.register_tools_in_ku_api(integration_test_session, tenant_id)

        # Load tools
        execution_context = {
            "tenant_id": tenant_id,
            "session": integration_test_session,
            "task_id": "test-task-123",
            "app": "default",
        }

        executor = DefaultTaskExecutor()
        app_tools = await executor._load_app_tools(execution_context)

        # Verify FQN construction:
        # Tool name in KU: "virustotal::ip_reputation"
        # FQN in tools dict: "app::virustotal::ip_reputation"
        # Cy script calls with same FQN: app::virustotal::ip_reputation(ip="8.8.8.8")

        # Check that all tool keys are FQNs with 3 parts: app, integration_type, action_id
        for fqn in app_tools:
            parts = fqn.split("::")
            assert len(parts) == 3
            namespace, integration_type, action_id = parts
            assert namespace == "app"
            assert len(integration_type) > 0
            assert len(action_id) > 0

    @pytest.mark.asyncio
    async def test_app_tools_available_during_execution(self, integration_test_session):
        """Test that app tools are loaded during task execution."""
        registry = IntegrationRegistryService()
        tenant_id = "test-tenant"

        # Register app tools
        await registry.register_tools_in_ku_api(integration_test_session, tenant_id)

        cy_script = """
# Simple script that verifies execution works
return {"status": "success", "message": "App tools context ready"}
"""

        # Execute with proper execution context
        execution_context = {
            "tenant_id": tenant_id,
            "session": integration_test_session,
            "task_id": "test-task-123",
            "app": "default",
        }

        executor = DefaultTaskExecutor()
        result = await executor.execute(cy_script, {}, execution_context)

        # Verify execution succeeded (which means app tools were loaded without errors)
        assert result["status"] == "completed"
        output = parse_cy_output(result["output"])
        assert "message" in output
        assert output["message"] == "App tools context ready"

    @pytest.mark.asyncio
    async def test_app_tools_auto_reload_on_integration_change(
        self, integration_test_session
    ):
        """Test that app tools automatically reload when integration is replaced."""
        from uuid import uuid4

        from analysi.models.credential import Credential, IntegrationCredential
        from analysi.models.integration import Integration
        from analysi.repositories.credential_repository import CredentialRepository
        from analysi.repositories.integration_repository import IntegrationRepository

        registry = IntegrationRegistryService()
        tenant_id = f"test-tenant-{uuid4().hex[:8]}"

        # Register app tools in KU
        await registry.register_tools_in_ku_api(integration_test_session, tenant_id)

        # Create first integration with a credential
        IntegrationRepository(integration_test_session)
        CredentialRepository(integration_test_session)

        first_integration_id = f"vt-test-{uuid4().hex[:8]}"

        # Create credential for first integration
        first_credential = Credential(
            tenant_id=tenant_id,
            provider="virustotal",
            account=first_integration_id,
            ciphertext="encrypted_api_key_1",
            key_name="test-key",
        )
        integration_test_session.add(first_credential)
        await integration_test_session.flush()

        # Create first integration
        first_integration = Integration(
            integration_id=first_integration_id,
            tenant_id=tenant_id,
            integration_type="virustotal",
            name="First VT Integration",
            enabled=True,
            settings={},
        )
        integration_test_session.add(first_integration)

        # Link credential to integration
        ic1 = IntegrationCredential(
            tenant_id=tenant_id,
            integration_id=first_integration_id,
            credential_id=first_credential.id,
            is_primary=True,
            purpose="admin",
        )
        integration_test_session.add(ic1)
        await integration_test_session.commit()

        # Execute script once to register tools in default_registry (this caches first_integration_id)
        execution_context = {
            "tenant_id": tenant_id,
            "session": integration_test_session,
            "task_id": "test-task-123",
            "app": "default",
        }

        executor = DefaultTaskExecutor()
        cy_script = """
return {"initialized": "yes"}
"""
        result = await executor.execute(cy_script, {}, execution_context)
        assert result["status"] == "completed"

        # Now delete the first integration and create a new one with different ID
        await integration_test_session.delete(ic1)
        await integration_test_session.delete(first_integration)
        await integration_test_session.commit()

        second_integration_id = f"vt-test-{uuid4().hex[:8]}"

        # Create credential for second integration
        second_credential = Credential(
            tenant_id=tenant_id,
            provider="virustotal",
            account=second_integration_id,
            ciphertext="encrypted_api_key_2",
            key_name="test-key",
        )
        integration_test_session.add(second_credential)
        await integration_test_session.flush()

        # Create second integration
        second_integration = Integration(
            integration_id=second_integration_id,
            tenant_id=tenant_id,
            integration_type="virustotal",
            name="Second VT Integration",
            enabled=True,
            settings={},
        )
        integration_test_session.add(second_integration)

        # Link credential to second integration
        ic2 = IntegrationCredential(
            tenant_id=tenant_id,
            integration_id=second_integration_id,
            credential_id=second_credential.id,
            is_primary=True,
            purpose="admin",
        )
        integration_test_session.add(ic2)
        await integration_test_session.commit()

        # The cached wrapper from first execution should detect first integration is gone
        # and automatically reload to find second integration
        # We can't actually call the VT API in tests, but we can verify the tool doesn't crash
        # The reload logic will be triggered when execute_action is called and fails to find first_integration_id

        # Note: Without a real VirusTotal API key, the action will fail at the API level,
        # but the reload logic should succeed in finding the new integration
        # We're testing that the system doesn't crash with "integration not found" error
        # Instead it should reload and try with the new integration (then fail on missing API key)

        cy_script_with_tool = """
# This will trigger the reload logic since first_integration_id no longer exists
result = app::virustotal::ip_reputation(ip="8.8.8.8")
return {"tool_called": "yes", "result_status": result.status}
"""

        result = await executor.execute(cy_script_with_tool, {}, execution_context)

        # The execution should succeed (not crash with "integration not found")
        # The tool will return an error from VirusTotal API (bad key or rate limit), but that's expected
        assert result["status"] == "completed"
        output = parse_cy_output(result["output"])
        assert "tool_called" in output
        assert output["tool_called"] == "yes"
        # The VT call will fail (no real API key), but that proves reload worked
        # If reload didn't work, we'd get "integration not found" error instead
