"""
Unit tests for Alert Analysis API Clients.
Tests the BackendAPIClient and its methods.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.alert_analysis.clients import BackendAPIClient
from analysi.common.retry_config import RetryableHTTPError


@pytest.mark.asyncio
class TestBackendAPIClient:
    """Test the Backend API Client."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = BackendAPIClient()
        self.tenant_id = "test-tenant"
        self.workflow_id = "workflow-123"
        self.workflow_name = "Alert Analysis Workflow"
        self.workflow_run_id = "run-456"
        self.alert_id = "alert-789"

    @patch("analysi.alert_analysis.clients.InternalAsyncClient")
    @pytest.mark.asyncio
    async def test_get_workflow_by_name_found(self, mock_client_class):
        """Test finding a workflow by name."""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "other-workflow", "name": "Other Workflow"},
            {"id": self.workflow_id, "name": self.workflow_name},
        ]

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Act
        result = await self.client.get_workflow_by_name(
            self.tenant_id, self.workflow_name
        )

        # Assert
        assert result == self.workflow_id
        mock_client.get.assert_called_once_with(
            f"{self.client.base_url}/v1/{self.tenant_id}/workflows"
        )

    @patch("analysi.alert_analysis.clients.InternalAsyncClient")
    @pytest.mark.asyncio
    async def test_get_workflow_by_name_not_found(self, mock_client_class):
        """Test workflow not found by name."""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "other-workflow", "name": "Other Workflow"},
        ]

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Act
        result = await self.client.get_workflow_by_name(
            self.tenant_id, "Nonexistent Workflow"
        )

        # Assert
        assert result is None

    @patch("analysi.alert_analysis.clients.InternalAsyncClient")
    @pytest.mark.asyncio
    async def test_execute_workflow_success(self, mock_client_class):
        """Test successful workflow execution."""
        # Arrange
        input_data = {"alert_id": self.alert_id, "severity": "high"}
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            "workflow_run_id": self.workflow_run_id,
            "status": "pending",
        }

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Act
        result = await self.client.execute_workflow(
            self.tenant_id, self.workflow_id, input_data
        )

        # Assert
        assert result == self.workflow_run_id
        mock_client.post.assert_called_once_with(
            f"{self.client.base_url}/v1/{self.tenant_id}/workflows/{self.workflow_id}/run",
            json={"input_data": input_data},
        )

    @patch("analysi.alert_analysis.clients.InternalAsyncClient")
    @pytest.mark.asyncio
    async def test_execute_workflow_server_error(self, mock_client_class):
        """Test workflow execution with server error."""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Act & Assert
        with pytest.raises(RetryableHTTPError) as exc_info:
            await self.client.execute_workflow(
                self.tenant_id, self.workflow_id, {"alert_id": self.alert_id}
            )

        assert "Server error: 500" in str(exc_info.value)

    @patch("analysi.alert_analysis.clients.InternalAsyncClient")
    @pytest.mark.asyncio
    async def test_execute_workflow_rate_limit(self, mock_client_class):
        """Test workflow execution with rate limiting."""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 429

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Act & Assert
        with pytest.raises(RetryableHTTPError) as exc_info:
            await self.client.execute_workflow(
                self.tenant_id, self.workflow_id, {"alert_id": self.alert_id}
            )

        assert "Server error: 429" in str(exc_info.value)

    @patch("analysi.alert_analysis.clients.InternalAsyncClient")
    @pytest.mark.asyncio
    async def test_get_workflow_status_completed(self, mock_client_class):
        """Test getting workflow status when completed."""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "completed",
            "progress": "Workflow completed successfully",
        }

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Act
        result = await self.client.get_workflow_status(
            self.tenant_id, self.workflow_run_id
        )

        # Assert
        assert result == "completed"
        mock_client.get.assert_called_once_with(
            f"{self.client.base_url}/v1/{self.tenant_id}/workflow-runs/{self.workflow_run_id}/status"
        )

    @patch("analysi.alert_analysis.clients.InternalAsyncClient")
    @pytest.mark.asyncio
    async def test_get_workflow_status_running(self, mock_client_class):
        """Test getting workflow status when still running."""
        # Arrange
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "running",
            "progress": "Executing node 2 of 5",
        }

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Act
        result = await self.client.get_workflow_status(
            self.tenant_id, self.workflow_run_id
        )

        # Assert
        assert result == "running"

    @patch("analysi.alert_analysis.clients.InternalAsyncClient")
    @pytest.mark.asyncio
    async def test_api_client_connection_error(self, mock_client_class):
        """Test handling connection errors."""
        # Arrange
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Act & Assert
        with pytest.raises(RetryableHTTPError) as exc_info:
            await self.client.get_workflow_by_name(self.tenant_id, self.workflow_name)

        assert "Connection refused" in str(exc_info.value)

    @patch("analysi.alert_analysis.clients.InternalAsyncClient")
    @pytest.mark.asyncio
    async def test_api_client_timeout(self, mock_client_class):
        """Test handling timeout errors."""
        # Arrange
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("Request timeout")
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Act & Assert
        with pytest.raises(RetryableHTTPError) as exc_info:
            await self.client.execute_workflow(
                self.tenant_id, self.workflow_id, {"alert_id": self.alert_id}
            )

        assert "Request timeout" in str(exc_info.value)
