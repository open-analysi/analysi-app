"""Unit tests for Kea Coordination Client."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.alert_analysis.clients import KeaCoordinationClient


class TestKeaCoordinationClient:
    """Test HTTP client for Kea Coordination API endpoints."""

    def test_client_initialization(self):
        """Test client initializes with correct base URL."""
        client = KeaCoordinationClient(base_url="http://api:8000")
        assert client.base_url == "http://api:8000"

    @pytest.mark.asyncio
    async def test_create_group_with_generation_success(self):
        """Test successful analysis group + generation creation."""
        client = KeaCoordinationClient(base_url="http://test:8000")

        # Mock response data
        mock_response = {
            "analysis_group": {
                "id": "group-123",
                "title": "Suspicious Login",
                "tenant_id": "default",
            },
            "workflow_generation": {
                "id": "gen-456",
                "status": "running",
                "workflow_id": None,
            },
        }

        # Mock httpx client
        with patch(
            "analysi.alert_analysis.clients.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response_obj = MagicMock()  # Use MagicMock for response (not async)
            mock_response_obj.status_code = 201
            mock_response_obj.json.return_value = mock_response
            mock_client.post.return_value = mock_response_obj

            # Act
            result = await client.create_group_with_generation(
                tenant_id="default", title="Suspicious Login"
            )

            # Assert
            assert result == mock_response
            assert result["analysis_group"]["id"] == "group-123"
            assert result["workflow_generation"]["status"] == "running"

            # Verify correct API call
            mock_client.post.assert_called_once_with(
                "http://test:8000/v1/default/analysis-groups/with-workflow-generation",
                json={"title": "Suspicious Login"},
            )

    @pytest.mark.asyncio
    async def test_create_group_with_generation_http_error(self):
        """Test error handling for HTTP errors."""
        client = KeaCoordinationClient(base_url="http://test:8000")

        with patch(
            "analysi.alert_analysis.clients.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 500
            mock_response_obj.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Server error", request=None, response=mock_response_obj
            )
            mock_client.post.return_value = mock_response_obj

            # Act & Assert
            with pytest.raises(httpx.HTTPStatusError):
                await client.create_group_with_generation(
                    tenant_id="default", title="Test"
                )

    @pytest.mark.asyncio
    async def test_get_active_workflow_success(self):
        """Test getting active workflow for a group."""
        client = KeaCoordinationClient(base_url="http://test:8000")

        mock_response = {"routing_rule": {"workflow_id": "workflow-789"}}

        with patch(
            "analysi.alert_analysis.clients.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response
            mock_client.get.return_value = mock_response_obj

            # Act
            result = await client.get_active_workflow(
                tenant_id="default", group_title="Suspicious Login"
            )

            # Assert
            assert result == mock_response
            assert result["routing_rule"]["workflow_id"] == "workflow-789"

            # Verify correct API call - now uses title query param
            mock_client.get.assert_called_once_with(
                "http://test:8000/v1/default/analysis-groups/active-workflow",
                params={"title": "Suspicious Login"},
            )

    @pytest.mark.asyncio
    async def test_get_active_workflow_no_workflow(self):
        """Test getting active workflow when no workflow exists."""
        client = KeaCoordinationClient(base_url="http://test:8000")

        mock_response = {"routing_rule": None}

        with patch(
            "analysi.alert_analysis.clients.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response
            mock_client.get.return_value = mock_response_obj

            # Act
            result = await client.get_active_workflow(
                tenant_id="default", group_title="Unknown Rule"
            )

            # Assert
            assert result["routing_rule"] is None

    @pytest.mark.asyncio
    async def test_get_active_workflow_http_error(self):
        """Test error handling for get_active_workflow."""
        client = KeaCoordinationClient(base_url="http://test:8000")

        with patch(
            "analysi.alert_analysis.clients.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 404
            mock_response_obj.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Not found", request=None, response=mock_response_obj
            )
            mock_client.get.return_value = mock_response_obj

            # Act & Assert
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_active_workflow(
                    tenant_id="default", group_title="Fake Rule"
                )

    @pytest.mark.asyncio
    async def test_client_timeout_configuration(self):
        """Test that client uses configured timeout."""
        client = KeaCoordinationClient(base_url="http://test:8000")

        with patch(
            "analysi.alert_analysis.clients.InternalAsyncClient"
        ) as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 201
            # Use proper response structure
            mock_response_obj.json.return_value = {
                "analysis_group": {"id": "test-id"},
                "workflow_generation": {"status": "running"},
            }
            mock_client.post.return_value = mock_response_obj

            await client.create_group_with_generation(tenant_id="default", title="Test")

            # Verify httpx.AsyncClient was created with timeout object
            # The client uses httpx.Timeout(30.0, connect=5.0)
            mock_client_class.assert_called_once()
            call_args = mock_client_class.call_args
            assert call_args is not None
            timeout_arg = call_args.kwargs.get("timeout")
            assert timeout_arg is not None
            # Verify it's a Timeout object with correct values
            assert isinstance(timeout_arg, httpx.Timeout)
            assert timeout_arg.read == 30.0
            assert timeout_arg.connect == 5.0
