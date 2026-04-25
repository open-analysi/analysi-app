"""
Unit tests for Echo EDR integration actions.

Adapted from tests/unit/connectors/test_echo_edr_connector.py for the
Integrations Framework format.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.echo_edr.actions import (
    GetHostDetailsAction,
    HealthCheckAction,
    IsolateHostAction,
    PullBrowserHistoryAction,
    PullNetworkConnectionsAction,
    PullProcessesAction,
    PullTerminalHistoryAction,
    ReleaseHostAction,
    ScanHostAction,
)


def _mock_response(status_code=200, json_data=None, text="ok"):
    """Create a mock httpx response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_data if json_data is not None else {}
    return resp


class TestHealthCheckAction:
    """Test Echo EDR health check action."""

    @pytest.fixture
    def health_check_action(self):
        """Create health check action instance."""
        return HealthCheckAction(
            integration_id="echo_edr",
            action_id="health_check",
            settings={"api_url": "http://test-echo-server:8000"},
            credentials={"api_key": "test-api-key-12345"},
        )

    @pytest.mark.asyncio
    async def test_health_check_success(self, health_check_action):
        """Test successful health check - uses new standardized result format."""
        mock_resp = _mock_response(200)

        with patch.object(
            health_check_action,
            "http_request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ) as mock_req:
            result = await health_check_action.execute()

            # New standardized format
            assert result["status"] == "success"
            assert result["integration_id"] == "echo_edr"
            assert result["action_id"] == "health_check"
            assert "timestamp" in result
            assert "data" in result

            # Data payload
            assert result["data"]["healthy"]
            assert "successful" in result["data"]["message"]
            assert result["data"]["endpoint"] == "http://test-echo-server:8000"
            assert result["data"]["api_version"] == "1.0"

            # Verify the health endpoint was called with auth header
            mock_req.assert_called_once()
            call_kwargs = mock_req.call_args
            assert "/__health" in call_kwargs[0][0]
            headers = call_kwargs.kwargs.get("headers", {})
            assert headers.get("Authorization") == "Bearer test-api-key-12345"

    @pytest.mark.asyncio
    async def test_health_check_failure_non_200(self, health_check_action):
        """Test health check with non-200 response - new error format."""
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500

        with patch.object(
            health_check_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=httpx.HTTPStatusError(
                "Internal Server Error", request=MagicMock(), response=mock_resp
            ),
        ):
            result = await health_check_action.execute()

            assert result["status"] == "error"
            assert result["error_type"] == "HealthCheckFailed"
            assert "failed with status 500" in result["error"]
            assert result["data"]["endpoint"] == "http://test-echo-server:8000"
            assert result["data"]["status_code"] == 500

    @pytest.mark.asyncio
    async def test_health_check_connection_error(self, health_check_action):
        """Test health check with connection error - new error format."""
        with patch.object(
            health_check_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            result = await health_check_action.execute()

            assert result["status"] == "error"
            assert result["error_type"] == "ConnectionError"
            assert "Connection refused" in result["error"]
            assert result["data"]["endpoint"] == "http://test-echo-server:8000"

    @pytest.mark.asyncio
    async def test_health_check_without_credentials(self):
        """Test health check without credentials - new success format."""
        action = HealthCheckAction(
            integration_id="echo_edr",
            action_id="health_check",
            settings={"api_url": "http://test-echo-server:8000"},
            credentials={},  # No credentials
        )

        mock_resp = _mock_response(200)

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            result = await action.execute()

            assert result["status"] == "success"
            assert result["data"]["healthy"]

            # Verify no auth header was sent
            call_kwargs = mock_req.call_args
            headers = call_kwargs.kwargs.get("headers", {})
            assert "Authorization" not in headers

    @pytest.mark.asyncio
    async def test_health_check_with_default_url(self):
        """Test health check with default URL when not in settings."""
        action = HealthCheckAction(
            integration_id="echo_edr",
            action_id="health_check",
            settings={},  # No api_url
            credentials={"api_key": "test-key"},
        )

        mock_resp = _mock_response(200)

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            await action.execute()

            # Verify it used the default URL
            call_kwargs = mock_req.call_args
            assert "http://echo-server:8000/__health" in call_kwargs[0][0]
            headers = call_kwargs.kwargs.get("headers", {})
            assert headers.get("Authorization") == "Bearer test-key"

    @pytest.mark.asyncio
    async def test_health_check_timeout(self, health_check_action):
        """Test health check with timeout - new error format."""
        with patch.object(
            health_check_action,
            "http_request",
            new_callable=AsyncMock,
            side_effect=httpx.TimeoutException("Request timed out"),
        ):
            result = await health_check_action.execute()

            assert result["status"] == "error"
            assert "Request timed out" in result["error"]


class TestDataCollectionActions:
    """Test Echo EDR data collection actions."""

    @pytest.mark.asyncio
    async def test_pull_processes(self):
        """Test pull processes action."""
        action = PullProcessesAction(
            integration_id="echo_edr",
            action_id="pull_processes",
            settings={"api_url": "http://test-echo-server:8000/echo_edr"},
            credentials={"api_key": "test-key"},
        )

        mock_resp = _mock_response(
            200,
            json_data=[
                {
                    "timestamp": "2025-01-01T12:00:00Z",
                    "process_name": "chrome.exe",
                    "process_id": 1234,
                }
            ],
        )

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            result = await action.execute(ip="192.168.1.100")

            assert result["status"] == "success"
            assert "data" in result
            assert "records" in result["data"]
            assert "count" in result["data"]
            assert isinstance(result["data"]["records"], list)

            # Verify HTTP call
            mock_req.assert_called_once()
            call_url = mock_req.call_args[0][0]
            assert "/devices/ip/192.168.1.100/processes" in call_url

    @pytest.mark.asyncio
    async def test_pull_browser_history(self):
        """Test pull browser history action."""
        action = PullBrowserHistoryAction(
            integration_id="echo_edr",
            action_id="pull_browser_history",
            settings={"api_url": "http://test-echo-server:8000/echo_edr"},
            credentials={"api_key": "test-key"},
        )

        mock_resp = _mock_response(
            200,
            json_data=[
                {
                    "visit_time": "2025-01-01T12:00:00Z",
                    "url": "https://example.com",
                    "title": "Example",
                }
            ],
        )

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            result = await action.execute(ip="192.168.1.100")

            assert result["status"] == "success"
            assert "data" in result
            assert "records" in result["data"]
            assert "count" in result["data"]

            # Verify HTTP call
            mock_req.assert_called_once()
            call_url = mock_req.call_args[0][0]
            assert "/devices/ip/192.168.1.100/browser_history" in call_url

    @pytest.mark.asyncio
    async def test_pull_network_connections(self):
        """Test pull network connections action."""
        action = PullNetworkConnectionsAction(
            integration_id="echo_edr",
            action_id="pull_network_connections",
            settings={"api_url": "http://test-echo-server:8000/echo_edr"},
            credentials={"api_key": "test-key"},
        )

        mock_resp = _mock_response(
            200,
            json_data=[
                {
                    "timestamp": "2025-01-01T12:00:00Z",
                    "remote_address": "93.184.216.34",
                    "remote_port": 443,
                    "protocol": "TCP",
                }
            ],
        )

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            result = await action.execute(ip="192.168.1.100")

            assert result["status"] == "success"
            assert "data" in result
            assert "records" in result["data"]
            assert result["data"]["count"] >= 0

            # Verify HTTP call
            mock_req.assert_called_once()
            call_url = mock_req.call_args[0][0]
            assert "/devices/ip/192.168.1.100/network_action" in call_url

    @pytest.mark.asyncio
    async def test_pull_terminal_history(self):
        """Test pull terminal history action."""
        action = PullTerminalHistoryAction(
            integration_id="echo_edr",
            action_id="pull_terminal_history",
            settings={"api_url": "http://test-echo-server:8000/echo_edr"},
            credentials={"api_key": "test-key"},
        )

        mock_resp = _mock_response(
            200,
            json_data=[
                {
                    "timestamp": "2025-01-01T12:00:00Z",
                    "command": "ls -la",
                    "user": "john.doe",
                }
            ],
        )

        with patch.object(
            action, "http_request", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_req:
            result = await action.execute(ip="192.168.1.100")

            assert result["status"] == "success"
            assert "data" in result
            assert "records" in result["data"]
            assert result["data"]["ip"] == "192.168.1.100"

            # Verify HTTP call
            mock_req.assert_called_once()
            call_url = mock_req.call_args[0][0]
            assert "/devices/ip/192.168.1.100/terminal_history" in call_url


class TestEDRToolActions:
    """Test Echo EDR tool actions (response capabilities)."""

    @pytest.mark.asyncio
    async def test_isolate_host(self):
        """Test isolate host action."""
        action = IsolateHostAction(
            integration_id="echo_edr",
            action_id="isolate_host",
            settings={"api_url": "http://test-echo-server:8000"},
            credentials={"api_key": "test-key"},
        )

        result = await action.execute(hostname="workstation-01")

        assert result["status"] == "success"
        assert result["hostname"] == "workstation-01"
        assert "isolated" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_release_host(self):
        """Test release host action."""
        action = ReleaseHostAction(
            integration_id="echo_edr",
            action_id="release_host",
            settings={"api_url": "http://test-echo-server:8000"},
            credentials={"api_key": "test-key"},
        )

        result = await action.execute(hostname="workstation-01")

        assert result["status"] == "success"
        assert result["hostname"] == "workstation-01"
        assert "released" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_scan_host(self):
        """Test scan host action."""
        action = ScanHostAction(
            integration_id="echo_edr",
            action_id="scan_host",
            settings={"api_url": "http://test-echo-server:8000"},
            credentials={"api_key": "test-key"},
        )

        result = await action.execute(hostname="workstation-01", scan_type="full")

        assert result["status"] == "success"
        assert result["hostname"] == "workstation-01"
        assert result["scan_type"] == "full"
        assert "scan_id" in result

    @pytest.mark.asyncio
    async def test_get_host_details(self):
        """Test get host details action."""
        action = GetHostDetailsAction(
            integration_id="echo_edr",
            action_id="get_host_details",
            settings={"api_url": "http://test-echo-server:8000"},
            credentials={"api_key": "test-key"},
        )

        result = await action.execute(hostname="workstation-01")

        assert result["status"] == "success"
        assert result["hostname"] == "workstation-01"
        assert "ip_address" in result
        assert "os" in result
        assert "agent_version" in result
