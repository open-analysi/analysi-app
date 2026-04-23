"""Unit tests for IntegrationExecutionService."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analysi.services.integration_execution_service import IntegrationExecutionService


class TestIntegrationExecutionService:
    """Unit tests for IntegrationExecutionService."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def service(self, mock_session):
        """Create an IntegrationExecutionService instance."""
        return IntegrationExecutionService(mock_session)

    @pytest.mark.asyncio
    async def test_execute_tool_success_with_mocked_framework(
        self, service, mock_session
    ):
        """Mock framework action execution, verify service logic."""
        # Mock database query for integration
        mock_integration = MagicMock()
        mock_integration.integration_type = "splunk"
        mock_integration.enabled = True
        mock_integration.settings = {"host": "localhost"}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_integration
        mock_session.execute.return_value = mock_result

        # Mock framework and action execution
        with (
            patch.object(service.framework, "get_integration") as mock_get_integration,
            patch.object(service.loader, "load_action") as mock_load_action,
        ):
            # Mock manifest
            mock_action = MagicMock()
            mock_action.id = "health_check"
            mock_manifest = MagicMock()
            mock_manifest.actions = [mock_action]
            mock_get_integration.return_value = mock_manifest

            # Mock action execution
            mock_action_instance = AsyncMock()
            mock_action_instance.execute.return_value = {
                "status": "success",
                "data": {"healthy": True},
            }
            mock_load_action.return_value = mock_action_instance

            result = await service.execute_tool(
                tenant_id="default",
                integration_id="splunk",
                action_id="health_check",
                arguments={},
                timeout_seconds=30,
                capture_schema=False,
            )

            assert result["status"] == "success"
            assert result["output"]["healthy"] is True
            assert result["error"] is None
            assert "execution_time_ms" in result

    @pytest.mark.asyncio
    async def test_execute_tool_parameter_validation(self, service, mock_session):
        """Test parameter validation before execution."""
        # Mock database query for integration
        mock_integration = MagicMock()
        mock_integration.integration_type = "virustotal"
        mock_integration.enabled = True
        mock_integration.settings = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_integration
        mock_session.execute.return_value = mock_result

        # Mock framework
        with (
            patch.object(service.framework, "get_integration") as mock_get_integration,
            patch.object(service.loader, "load_action") as mock_load_action,
        ):
            # Mock manifest
            mock_action = MagicMock()
            mock_action.id = "ip_reputation"
            mock_manifest = MagicMock()
            mock_manifest.actions = [mock_action]
            mock_get_integration.return_value = mock_manifest

            # Mock action execution
            mock_action_instance = AsyncMock()
            mock_action_instance.execute.return_value = {
                "status": "success",
                "data": {"reputation": "clean"},
            }
            mock_load_action.return_value = mock_action_instance

            result = await service.execute_tool(
                tenant_id="default",
                integration_id="virustotal",
                action_id="ip_reputation",
                arguments={"ip": "8.8.8.8"},
                timeout_seconds=30,
            )

            assert result["status"] == "success"
            # Verify action was called with correct arguments
            mock_action_instance.execute.assert_called_once_with(ip="8.8.8.8")

    @pytest.mark.asyncio
    async def test_execute_tool_integration_not_configured(self, service, mock_session):
        """Test error when integration not configured for tenant."""
        # Mock database query returning no integration
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await service.execute_tool(
            tenant_id="nonexistent_tenant",
            integration_id="splunk",
            action_id="health_check",
            arguments={},
        )

        assert result["status"] == "error"
        assert "not found" in result["error"]
        assert result["output"] is None

    @pytest.mark.asyncio
    async def test_execute_tool_action_not_found(self, service, mock_session):
        """Test error when action doesn't exist."""
        # Mock database query for integration
        mock_integration = MagicMock()
        mock_integration.integration_type = "splunk"
        mock_integration.enabled = True
        mock_integration.settings = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_integration
        mock_session.execute.return_value = mock_result

        # Mock framework with no matching action
        with patch.object(service.framework, "get_integration") as mock_get_integration:
            mock_action = MagicMock()
            mock_action.id = "health_check"
            mock_manifest = MagicMock()
            mock_manifest.actions = [mock_action]
            mock_get_integration.return_value = mock_manifest

            result = await service.execute_tool(
                tenant_id="default",
                integration_id="splunk",
                action_id="nonexistent_action",
                arguments={},
            )

            assert result["status"] == "error"
            assert "not found" in result["error"]
            assert result["output"] is None

    @pytest.mark.asyncio
    async def test_execute_tool_timeout_handling(self, service, mock_session):
        """Test timeout logic with asyncio.wait_for."""
        # Mock database query for integration
        mock_integration = MagicMock()
        mock_integration.integration_type = "splunk"
        mock_integration.enabled = True
        mock_integration.settings = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_integration
        mock_session.execute.return_value = mock_result

        # Mock framework
        with (
            patch.object(service.framework, "get_integration") as mock_get_integration,
            patch.object(service.loader, "load_action") as mock_load_action,
        ):
            mock_action = MagicMock()
            mock_action.id = "health_check"
            mock_manifest = MagicMock()
            mock_manifest.actions = [mock_action]
            mock_get_integration.return_value = mock_manifest

            # Mock action that takes too long
            async def slow_execute(**kwargs):
                await asyncio.sleep(10)  # Longer than timeout
                return {"status": "success"}

            mock_action_instance = AsyncMock()
            mock_action_instance.execute = slow_execute
            mock_load_action.return_value = mock_action_instance

            result = await service.execute_tool(
                tenant_id="default",
                integration_id="splunk",
                action_id="health_check",
                arguments={},
                timeout_seconds=0.1,  # Very short timeout
            )

            assert result["status"] == "timeout"
            assert "timed out" in result["error"]
            assert result["output"] is None

    @pytest.mark.asyncio
    async def test_execute_tool_framework_exception(self, service, mock_session):
        """Test handling of framework execution exceptions."""
        # Mock database query for integration
        mock_integration = MagicMock()
        mock_integration.integration_type = "splunk"
        mock_integration.enabled = True
        mock_integration.settings = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_integration
        mock_session.execute.return_value = mock_result

        # Mock framework
        with (
            patch.object(service.framework, "get_integration") as mock_get_integration,
            patch.object(service.loader, "load_action") as mock_load_action,
        ):
            mock_action = MagicMock()
            mock_action.id = "health_check"
            mock_manifest = MagicMock()
            mock_manifest.actions = [mock_action]
            mock_get_integration.return_value = mock_manifest

            # Mock action that raises exception
            mock_action_instance = AsyncMock()
            mock_action_instance.execute.side_effect = Exception("Framework error")
            mock_load_action.return_value = mock_action_instance

            result = await service.execute_tool(
                tenant_id="default",
                integration_id="splunk",
                action_id="health_check",
                arguments={},
            )

            assert result["status"] == "error"
            assert "Framework error" in result["error"]
            assert result["output"] is None

    @pytest.mark.asyncio
    async def test_schema_capture_with_dict_output(self, service, mock_session):
        """Test genson schema generation from dict output."""
        # Mock database query for integration
        mock_integration = MagicMock()
        mock_integration.integration_type = "splunk"
        mock_integration.enabled = True
        mock_integration.settings = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_integration
        mock_session.execute.return_value = mock_result

        # Mock framework
        with (
            patch.object(service.framework, "get_integration") as mock_get_integration,
            patch.object(service.loader, "load_action") as mock_load_action,
        ):
            mock_action = MagicMock()
            mock_action.id = "health_check"
            mock_manifest = MagicMock()
            mock_manifest.actions = [mock_action]
            mock_get_integration.return_value = mock_manifest

            # Mock action returning dict
            mock_action_instance = AsyncMock()
            mock_action_instance.execute.return_value = {
                "status": "success",
                "data": {"healthy": True, "version": "9.0"},
            }
            mock_load_action.return_value = mock_action_instance

            result = await service.execute_tool(
                tenant_id="default",
                integration_id="splunk",
                action_id="health_check",
                arguments={},
                capture_schema=True,
            )

            assert result["status"] == "success"
            assert result["output_schema"] is not None
            assert "type" in result["output_schema"]

    @pytest.mark.asyncio
    async def test_schema_capture_with_list_output(self, service, mock_session):
        """Test genson schema generation from list output."""
        # Mock database query for integration
        mock_integration = MagicMock()
        mock_integration.integration_type = "splunk"
        mock_integration.enabled = True
        mock_integration.settings = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_integration
        mock_session.execute.return_value = mock_result

        # Mock framework
        with (
            patch.object(service.framework, "get_integration") as mock_get_integration,
            patch.object(service.loader, "load_action") as mock_load_action,
        ):
            mock_action = MagicMock()
            mock_action.id = "list_data"
            mock_manifest = MagicMock()
            mock_manifest.actions = [mock_action]
            mock_get_integration.return_value = mock_manifest

            # Mock action returning list
            mock_action_instance = AsyncMock()
            mock_action_instance.execute.return_value = {
                "status": "success",
                "data": [{"id": 1, "name": "test"}],
            }
            mock_load_action.return_value = mock_action_instance

            result = await service.execute_tool(
                tenant_id="default",
                integration_id="splunk",
                action_id="list_data",
                arguments={},
                capture_schema=True,
            )

            assert result["status"] == "success"
            assert result["output_schema"] is not None

    @pytest.mark.asyncio
    async def test_schema_capture_with_primitive_output(self, service, mock_session):
        """Test schema generation for string/int/bool outputs."""
        # Mock database query for integration
        mock_integration = MagicMock()
        mock_integration.integration_type = "splunk"
        mock_integration.enabled = True
        mock_integration.settings = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_integration
        mock_session.execute.return_value = mock_result

        # Mock framework
        with (
            patch.object(service.framework, "get_integration") as mock_get_integration,
            patch.object(service.loader, "load_action") as mock_load_action,
        ):
            mock_action = MagicMock()
            mock_action.id = "get_status"
            mock_manifest = MagicMock()
            mock_manifest.actions = [mock_action]
            mock_get_integration.return_value = mock_manifest

            # Mock action returning string
            mock_action_instance = AsyncMock()
            mock_action_instance.execute.return_value = "healthy"
            mock_load_action.return_value = mock_action_instance

            result = await service.execute_tool(
                tenant_id="default",
                integration_id="splunk",
                action_id="get_status",
                arguments={},
                capture_schema=True,
            )

            assert result["status"] == "success"
            assert result["output_schema"] is not None

    @pytest.mark.asyncio
    async def test_execution_time_measurement(self, service, mock_session):
        """Test execution_time_ms calculation accuracy."""
        # Mock database query for integration
        mock_integration = MagicMock()
        mock_integration.integration_type = "splunk"
        mock_integration.enabled = True
        mock_integration.settings = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_integration
        mock_session.execute.return_value = mock_result

        # Mock framework
        with (
            patch.object(service.framework, "get_integration") as mock_get_integration,
            patch.object(service.loader, "load_action") as mock_load_action,
        ):
            mock_action = MagicMock()
            mock_action.id = "health_check"
            mock_manifest = MagicMock()
            mock_manifest.actions = [mock_action]
            mock_get_integration.return_value = mock_manifest

            # Mock action with delay
            async def delayed_execute(**kwargs):
                await asyncio.sleep(0.1)
                return {"status": "success"}

            mock_action_instance = AsyncMock()
            mock_action_instance.execute = delayed_execute
            mock_load_action.return_value = mock_action_instance

            result = await service.execute_tool(
                tenant_id="default",
                integration_id="splunk",
                action_id="health_check",
                arguments={},
            )

            assert result["status"] == "success"
            assert result["execution_time_ms"] >= 100  # At least 100ms
            assert result["execution_time_ms"] < 1000  # Less than 1s
