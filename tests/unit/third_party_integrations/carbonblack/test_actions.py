"""Unit tests for Carbon Black Cloud integration actions."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.carbonblack.actions import (
    BanHashAction,
    GetAlertAction,
    GetBinaryAction,
    GetDeviceAction,
    HealthCheckAction,
    QuarantineDeviceAction,
    SearchAlertsAction,
    SearchDevicesAction,
    SearchProcessesAction,
    UnbanHashAction,
    UnquarantineDeviceAction,
)

# ============================================================================
# Fixtures
# ============================================================================

VALID_SHA256 = "a" * 64


@pytest.fixture
def mock_credentials():
    """Mock Carbon Black Cloud credentials."""
    return {
        "api_key": "test_api_key",
        "api_id": "test_api_id",
    }


@pytest.fixture
def mock_settings():
    """Mock integration settings."""
    return {
        "org_key": "TESTORGKEY",
        "base_url": "https://defense-test.conferdeploy.net",
        "timeout": 30,
    }


def create_action(action_class, action_id="test", credentials=None, settings=None):
    """Create action instance for testing."""
    return action_class(
        integration_id="carbonblack",
        action_id=action_id,
        credentials=credentials or {},
        settings=settings or {},
    )


def mock_http_response(json_data=None, status_code=200):
    """Create a mock HTTP response."""
    resp = MagicMock()
    resp.json.return_value = json_data or {}
    resp.status_code = status_code
    resp.text = str(json_data)
    resp.raise_for_status = MagicMock()
    return resp


def mock_http_error(status_code, body=None):
    """Create a mock HTTPStatusError with realistic request/response."""
    request = httpx.Request("GET", "https://test.example.com/api")
    response = httpx.Response(
        status_code=status_code,
        request=request,
        json=body or {},
    )
    return httpx.HTTPStatusError(
        f"{status_code} Error",
        request=request,
        response=response,
    )


# ============================================================================
# HealthCheckAction Tests
# ============================================================================


class TestHealthCheckAction:
    """Tests for health check action."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = create_action(
            HealthCheckAction, "health_check", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=mock_http_response({"num_found": 42, "results": []})
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["healthy"] is True
        assert result["data"]["num_found"] == 42
        assert "integration_id" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_missing_credentials(self, mock_settings):
        action = create_action(HealthCheckAction, "health_check", {}, mock_settings)

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_missing_api_key(self, mock_settings):
        action = create_action(
            HealthCheckAction,
            "health_check",
            {"api_id": "id", "org_key": "key"},
            mock_settings,
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_auth_failure(self, mock_credentials, mock_settings):
        action = create_action(
            HealthCheckAction, "health_check", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=mock_http_error(401))

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "AuthenticationError"
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_forbidden(self, mock_credentials, mock_settings):
        action = create_action(
            HealthCheckAction, "health_check", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=mock_http_error(403))

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "AuthenticationError"

    @pytest.mark.asyncio
    async def test_connection_error(self, mock_credentials, mock_settings):
        action = create_action(
            HealthCheckAction, "health_check", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["healthy"] is False


# ============================================================================
# GetDeviceAction Tests
# ============================================================================


class TestGetDeviceAction:
    """Tests for get device action."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = create_action(
            GetDeviceAction, "get_device", mock_credentials, mock_settings
        )
        device_data = {
            "id": 12345,
            "name": "TEST-HOST-01",
            "os": "WINDOWS",
            "quarantined": False,
        }
        action.http_request = AsyncMock(
            return_value=mock_http_response({"results": [device_data], "num_found": 1})
        )

        result = await action.execute(device_id="12345")

        assert result["status"] == "success"
        assert result["data"]["id"] == 12345
        assert result["data"]["name"] == "TEST-HOST-01"

    @pytest.mark.asyncio
    async def test_missing_device_id(self, mock_credentials, mock_settings):
        action = create_action(
            GetDeviceAction, "get_device", mock_credentials, mock_settings
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "device_id" in result["error"]

    @pytest.mark.asyncio
    async def test_device_not_found(self, mock_credentials, mock_settings):
        action = create_action(
            GetDeviceAction, "get_device", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=mock_http_response({"results": [], "num_found": 0})
        )

        result = await action.execute(device_id="99999")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["device_id"] == "99999"

    @pytest.mark.asyncio
    async def test_http_404(self, mock_credentials, mock_settings):
        action = create_action(
            GetDeviceAction, "get_device", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=mock_http_error(404))

        result = await action.execute(device_id="99999")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_server_error(self, mock_credentials, mock_settings):
        action = create_action(
            GetDeviceAction, "get_device", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=mock_http_error(500))

        result = await action.execute(device_id="12345")

        assert result["status"] == "error"


# ============================================================================
# SearchDevicesAction Tests
# ============================================================================


class TestSearchDevicesAction:
    """Tests for search devices action."""

    @pytest.mark.asyncio
    async def test_success_with_query(self, mock_credentials, mock_settings):
        action = create_action(
            SearchDevicesAction, "search_devices", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=mock_http_response(
                {
                    "results": [
                        {"id": 1, "name": "HOST-A"},
                        {"id": 2, "name": "HOST-B"},
                    ],
                    "num_found": 2,
                }
            )
        )

        result = await action.execute(query="os_version:Windows*", rows=10)

        assert result["status"] == "success"
        assert len(result["data"]["devices"]) == 2
        assert result["data"]["num_found"] == 2
        assert result["data"]["rows"] == 10

    @pytest.mark.asyncio
    async def test_success_with_criteria(self, mock_credentials, mock_settings):
        action = create_action(
            SearchDevicesAction, "search_devices", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=mock_http_response({"results": [], "num_found": 0})
        )

        result = await action.execute(criteria={"os": ["WINDOWS"]})

        assert result["status"] == "success"
        assert result["data"]["devices"] == []
        assert result["data"]["num_found"] == 0

    @pytest.mark.asyncio
    async def test_empty_search(self, mock_credentials, mock_settings):
        action = create_action(
            SearchDevicesAction, "search_devices", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=mock_http_response({"results": [], "num_found": 0})
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["devices"] == []

    @pytest.mark.asyncio
    async def test_rows_capped_at_max(self, mock_credentials, mock_settings):
        action = create_action(
            SearchDevicesAction, "search_devices", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=mock_http_response({"results": [], "num_found": 0})
        )

        result = await action.execute(rows=99999)

        assert result["status"] == "success"
        # MAX_SEARCH_ROWS is 10000
        assert result["data"]["rows"] == 10000

    @pytest.mark.asyncio
    async def test_api_error(self, mock_credentials, mock_settings):
        action = create_action(
            SearchDevicesAction, "search_devices", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=mock_http_error(500))

        result = await action.execute(query="*")

        assert result["status"] == "error"


# ============================================================================
# QuarantineDeviceAction Tests
# ============================================================================


class TestQuarantineDeviceAction:
    """Tests for quarantine device action."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = create_action(
            QuarantineDeviceAction,
            "quarantine_device",
            mock_credentials,
            mock_settings,
        )
        action.http_request = AsyncMock(return_value=mock_http_response({}))

        result = await action.execute(device_id="12345")

        assert result["status"] == "success"
        assert result["data"]["device_id"] == "12345"
        assert result["data"]["action"] == "quarantine"

        # Verify correct request body
        call_kwargs = action.http_request.call_args
        body = call_kwargs.kwargs.get("json_data") or call_kwargs[1].get("json_data")
        assert body["action_type"] == "QUARANTINE"
        assert "12345" in body["device_id"]

    @pytest.mark.asyncio
    async def test_missing_device_id(self, mock_credentials, mock_settings):
        action = create_action(
            QuarantineDeviceAction,
            "quarantine_device",
            mock_credentials,
            mock_settings,
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "device_id" in result["error"]

    @pytest.mark.asyncio
    async def test_api_error(self, mock_credentials, mock_settings):
        action = create_action(
            QuarantineDeviceAction,
            "quarantine_device",
            mock_credentials,
            mock_settings,
        )
        action.http_request = AsyncMock(side_effect=mock_http_error(500))

        result = await action.execute(device_id="12345")

        assert result["status"] == "error"


# ============================================================================
# UnquarantineDeviceAction Tests
# ============================================================================


class TestUnquarantineDeviceAction:
    """Tests for unquarantine device action."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = create_action(
            UnquarantineDeviceAction,
            "unquarantine_device",
            mock_credentials,
            mock_settings,
        )
        action.http_request = AsyncMock(return_value=mock_http_response({}))

        result = await action.execute(device_id="12345")

        assert result["status"] == "success"
        assert result["data"]["device_id"] == "12345"
        assert result["data"]["action"] == "unquarantine"

        # Verify correct request body
        call_kwargs = action.http_request.call_args
        body = call_kwargs.kwargs.get("json_data") or call_kwargs[1].get("json_data")
        assert body["action_type"] == "UNQUARANTINE"

    @pytest.mark.asyncio
    async def test_missing_device_id(self, mock_credentials, mock_settings):
        action = create_action(
            UnquarantineDeviceAction,
            "unquarantine_device",
            mock_credentials,
            mock_settings,
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_api_error(self, mock_credentials, mock_settings):
        action = create_action(
            UnquarantineDeviceAction,
            "unquarantine_device",
            mock_credentials,
            mock_settings,
        )
        action.http_request = AsyncMock(side_effect=mock_http_error(403))

        result = await action.execute(device_id="12345")

        assert result["status"] == "error"


# ============================================================================
# GetAlertAction Tests
# ============================================================================


class TestGetAlertAction:
    """Tests for get alert action."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = create_action(
            GetAlertAction, "get_alert", mock_credentials, mock_settings
        )
        alert_data = {
            "id": "alert-123",
            "type": "CB_ANALYTICS",
            "severity": 5,
            "device_name": "TEST-HOST",
        }
        action.http_request = AsyncMock(return_value=mock_http_response(alert_data))

        result = await action.execute(alert_id="alert-123")

        assert result["status"] == "success"
        assert result["data"]["id"] == "alert-123"
        assert result["data"]["severity"] == 5

    @pytest.mark.asyncio
    async def test_missing_alert_id(self, mock_credentials, mock_settings):
        action = create_action(
            GetAlertAction, "get_alert", mock_credentials, mock_settings
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "alert_id" in result["error"]

    @pytest.mark.asyncio
    async def test_alert_not_found(self, mock_credentials, mock_settings):
        action = create_action(
            GetAlertAction, "get_alert", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=mock_http_error(404))

        result = await action.execute(alert_id="nonexistent")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["alert_id"] == "nonexistent"

    @pytest.mark.asyncio
    async def test_server_error(self, mock_credentials, mock_settings):
        action = create_action(
            GetAlertAction, "get_alert", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=mock_http_error(500))

        result = await action.execute(alert_id="alert-123")

        assert result["status"] == "error"


# ============================================================================
# SearchAlertsAction Tests
# ============================================================================


class TestSearchAlertsAction:
    """Tests for search alerts action."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = create_action(
            SearchAlertsAction, "search_alerts", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=mock_http_response(
                {
                    "results": [
                        {"id": "alert-1", "severity": 8},
                        {"id": "alert-2", "severity": 5},
                    ],
                    "num_found": 2,
                }
            )
        )

        result = await action.execute(
            query="severity:HIGH",
            rows=10,
        )

        assert result["status"] == "success"
        assert len(result["data"]["alerts"]) == 2
        assert result["data"]["num_found"] == 2

    @pytest.mark.asyncio
    async def test_with_criteria(self, mock_credentials, mock_settings):
        action = create_action(
            SearchAlertsAction, "search_alerts", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=mock_http_response({"results": [], "num_found": 0})
        )

        result = await action.execute(
            criteria={"minimum_severity": 5, "type": ["CB_ANALYTICS"]}
        )

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_with_sort(self, mock_credentials, mock_settings):
        action = create_action(
            SearchAlertsAction, "search_alerts", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=mock_http_response({"results": [], "num_found": 0})
        )

        result = await action.execute(sort={"field": "severity", "order": "DESC"})

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_api_error(self, mock_credentials, mock_settings):
        action = create_action(
            SearchAlertsAction, "search_alerts", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=mock_http_error(500))

        result = await action.execute(query="*")

        assert result["status"] == "error"


# ============================================================================
# SearchProcessesAction Tests
# ============================================================================


class TestSearchProcessesAction:
    """Tests for search processes action."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = create_action(
            SearchProcessesAction, "search_processes", mock_credentials, mock_settings
        )
        # Two calls: job creation, then results (with contacted==completed)
        job_response = mock_http_response({"job_id": "job-abc-123"})
        results_response = mock_http_response(
            {
                "results": [
                    {"process_guid": "proc-1", "process_name": "cmd.exe"},
                ],
                "num_found": 1,
                "num_available": 1,
                "contacted": 5,
                "completed": 5,
            }
        )
        action.http_request = AsyncMock(side_effect=[job_response, results_response])

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await action.execute(query="process_name:cmd.exe")

        assert result["status"] == "success"
        assert len(result["data"]["processes"]) == 1
        assert result["data"]["job_id"] == "job-abc-123"
        assert result["data"]["num_found"] == 1

    @pytest.mark.asyncio
    async def test_missing_query_and_criteria(self, mock_credentials, mock_settings):
        action = create_action(
            SearchProcessesAction, "search_processes", mock_credentials, mock_settings
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_job_creation_failure(self, mock_credentials, mock_settings):
        action = create_action(
            SearchProcessesAction, "search_processes", mock_credentials, mock_settings
        )
        # Job response missing job_id
        action.http_request = AsyncMock(
            return_value=mock_http_response({"error": "bad query"})
        )

        result = await action.execute(query="bad query")

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPError"

    @pytest.mark.asyncio
    async def test_api_error(self, mock_credentials, mock_settings):
        action = create_action(
            SearchProcessesAction, "search_processes", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=mock_http_error(500))

        result = await action.execute(query="process_name:*")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_search_processes_polls_until_complete(
        self, mock_credentials, mock_settings
    ):
        """Verify polling retries until contacted == completed."""
        action = create_action(
            SearchProcessesAction, "search_processes", mock_credentials, mock_settings
        )
        job_response = mock_http_response({"job_id": "job-poll-1"})
        # First poll: incomplete (contacted=5, completed=2)
        incomplete_response = mock_http_response(
            {
                "results": [],
                "num_found": 0,
                "num_available": 0,
                "contacted": 5,
                "completed": 2,
            }
        )
        # Second poll: complete (contacted=5, completed=5)
        complete_response = mock_http_response(
            {
                "results": [
                    {"process_guid": "proc-1", "process_name": "powershell.exe"},
                    {"process_guid": "proc-2", "process_name": "powershell.exe"},
                ],
                "num_found": 2,
                "num_available": 2,
                "contacted": 5,
                "completed": 5,
            }
        )
        action.http_request = AsyncMock(
            side_effect=[job_response, incomplete_response, complete_response]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await action.execute(query="process_name:powershell.exe")

        assert result["status"] == "success"
        assert len(result["data"]["processes"]) == 2
        assert result["data"]["num_found"] == 2
        assert result["data"]["job_id"] == "job-poll-1"
        # job creation + 2 result polls = 3 http calls
        assert action.http_request.call_count == 3
        # sleep called once (between first incomplete and second poll)
        mock_sleep.assert_called_once_with(1.0)

    @pytest.mark.asyncio
    async def test_search_processes_max_polls_exceeded(
        self, mock_credentials, mock_settings
    ):
        """Verify best-effort results returned when max polls exceeded."""
        from analysi.integrations.framework.integrations.carbonblack.constants import (
            PROCESS_MAX_POLLS,
        )

        action = create_action(
            SearchProcessesAction, "search_processes", mock_credentials, mock_settings
        )
        job_response = mock_http_response({"job_id": "job-timeout-1"})
        # Always return incomplete results
        incomplete_response = mock_http_response(
            {
                "results": [
                    {"process_guid": "proc-partial", "process_name": "svchost.exe"},
                ],
                "num_found": 10,
                "num_available": 1,
                "contacted": 5,
                "completed": 2,
            }
        )
        action.http_request = AsyncMock(
            side_effect=[job_response] + [incomplete_response] * PROCESS_MAX_POLLS
        )

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await action.execute(query="process_name:svchost.exe")

        # Should still return success with partial/best-effort data
        assert result["status"] == "success"
        assert len(result["data"]["processes"]) == 1
        assert result["data"]["job_id"] == "job-timeout-1"
        # sleep called PROCESS_MAX_POLLS times (once per loop iteration)
        assert mock_sleep.call_count == PROCESS_MAX_POLLS


# ============================================================================
# BanHashAction Tests
# ============================================================================


class TestBanHashAction:
    """Tests for ban hash action."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = create_action(
            BanHashAction, "ban_hash", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=mock_http_response(
                {"id": "override-1", "sha256_hash": VALID_SHA256.upper()}
            )
        )

        result = await action.execute(sha256_hash=VALID_SHA256)

        assert result["status"] == "success"
        assert result["data"]["sha256_hash"] == VALID_SHA256
        assert result["data"]["action"] == "ban"

        # Verify request body
        call_kwargs = action.http_request.call_args
        body = call_kwargs.kwargs.get("json_data") or call_kwargs[1].get("json_data")
        assert body["override_type"] == "SHA256"
        assert body["override_list"] == "BLACK_LIST"

    @pytest.mark.asyncio
    async def test_missing_hash(self, mock_credentials, mock_settings):
        action = create_action(
            BanHashAction, "ban_hash", mock_credentials, mock_settings
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "sha256_hash" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_hash_length(self, mock_credentials, mock_settings):
        action = create_action(
            BanHashAction, "ban_hash", mock_credentials, mock_settings
        )

        result = await action.execute(sha256_hash="abc123")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "64 characters" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_hash_chars(self, mock_credentials, mock_settings):
        action = create_action(
            BanHashAction, "ban_hash", mock_credentials, mock_settings
        )

        result = await action.execute(sha256_hash="g" * 64)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "hexadecimal" in result["error"]

    @pytest.mark.asyncio
    async def test_with_custom_description(self, mock_credentials, mock_settings):
        action = create_action(
            BanHashAction, "ban_hash", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(return_value=mock_http_response({}))

        result = await action.execute(
            sha256_hash=VALID_SHA256,
            description="Ransomware detected",
            filename="malware.exe",
        )

        assert result["status"] == "success"

        call_kwargs = action.http_request.call_args
        body = call_kwargs.kwargs.get("json_data") or call_kwargs[1].get("json_data")
        assert body["description"] == "Ransomware detected"
        assert body["filename"] == "malware.exe"

    @pytest.mark.asyncio
    async def test_api_error(self, mock_credentials, mock_settings):
        action = create_action(
            BanHashAction, "ban_hash", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=mock_http_error(500))

        result = await action.execute(sha256_hash=VALID_SHA256)

        assert result["status"] == "error"


# ============================================================================
# UnbanHashAction Tests
# ============================================================================


class TestUnbanHashAction:
    """Tests for unban hash action."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = create_action(
            UnbanHashAction, "unban_hash", mock_credentials, mock_settings
        )
        # First call: search for override; second call: delete it
        search_response = mock_http_response(
            {"results": [{"id": "override-1", "sha256_hash": VALID_SHA256.upper()}]}
        )
        delete_response = mock_http_response({})
        action.http_request = AsyncMock(side_effect=[search_response, delete_response])

        result = await action.execute(sha256_hash=VALID_SHA256)

        assert result["status"] == "success"
        assert result["data"]["sha256_hash"] == VALID_SHA256
        assert result["data"]["action"] == "unban"
        assert action.http_request.call_count == 2

    @pytest.mark.asyncio
    async def test_hash_not_banned(self, mock_credentials, mock_settings):
        action = create_action(
            UnbanHashAction, "unban_hash", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=mock_http_response({"results": []})
        )

        result = await action.execute(sha256_hash=VALID_SHA256)

        assert result["status"] == "success"
        assert result["data"]["already_unbanned"] is True

    @pytest.mark.asyncio
    async def test_missing_hash(self, mock_credentials, mock_settings):
        action = create_action(
            UnbanHashAction, "unban_hash", mock_credentials, mock_settings
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_hash(self, mock_credentials, mock_settings):
        action = create_action(
            UnbanHashAction, "unban_hash", mock_credentials, mock_settings
        )

        result = await action.execute(sha256_hash="not_a_hash")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_api_error(self, mock_credentials, mock_settings):
        action = create_action(
            UnbanHashAction, "unban_hash", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=mock_http_error(500))

        result = await action.execute(sha256_hash=VALID_SHA256)

        assert result["status"] == "error"


# ============================================================================
# GetBinaryAction Tests
# ============================================================================


class TestGetBinaryAction:
    """Tests for get binary metadata action."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = create_action(
            GetBinaryAction, "get_binary", mock_credentials, mock_settings
        )
        binary_data = {
            "sha256": VALID_SHA256.upper(),
            "file_size": 1024,
            "os_type": "WINDOWS",
            "architecture": ["amd64"],
            "available_for_download": True,
        }
        action.http_request = AsyncMock(return_value=mock_http_response(binary_data))

        result = await action.execute(sha256_hash=VALID_SHA256)

        assert result["status"] == "success"
        assert result["data"]["sha256"] == VALID_SHA256.upper()
        assert result["data"]["file_size"] == 1024

    @pytest.mark.asyncio
    async def test_missing_hash(self, mock_credentials, mock_settings):
        action = create_action(
            GetBinaryAction, "get_binary", mock_credentials, mock_settings
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_binary_not_found(self, mock_credentials, mock_settings):
        action = create_action(
            GetBinaryAction, "get_binary", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=mock_http_error(404))

        result = await action.execute(sha256_hash=VALID_SHA256)

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["sha256_hash"] == VALID_SHA256

    @pytest.mark.asyncio
    async def test_invalid_hash(self, mock_credentials, mock_settings):
        action = create_action(
            GetBinaryAction, "get_binary", mock_credentials, mock_settings
        )

        result = await action.execute(sha256_hash="short")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_server_error(self, mock_credentials, mock_settings):
        action = create_action(
            GetBinaryAction, "get_binary", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=mock_http_error(500))

        result = await action.execute(sha256_hash=VALID_SHA256)

        assert result["status"] == "error"


# ============================================================================
# Auth Mixin Tests
# ============================================================================


class TestCarbonBlackAuthMixin:
    """Tests for the shared auth mixin used by all actions."""

    @pytest.mark.asyncio
    async def test_auth_token_format(self, mock_credentials, mock_settings):
        """Verify auth header uses {api_key}/{api_id} format."""
        action = create_action(
            HealthCheckAction, "health_check", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=mock_http_response({"results": [], "num_found": 0})
        )

        await action.execute()

        call_kwargs = action.http_request.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert headers["X-Auth-Token"] == "test_api_key/test_api_id"

    @pytest.mark.asyncio
    async def test_url_uses_base_url_from_settings(
        self, mock_credentials, mock_settings
    ):
        """Verify request URL uses base_url from settings."""
        action = create_action(
            HealthCheckAction, "health_check", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=mock_http_response({"results": [], "num_found": 0})
        )

        await action.execute()

        call_args = action.http_request.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url")
        assert url.startswith("https://defense-test.conferdeploy.net")

    @pytest.mark.asyncio
    async def test_url_defaults_when_no_base_url(self, mock_credentials):
        """Verify default base URL when not set in settings."""
        action = create_action(
            HealthCheckAction,
            "health_check",
            mock_credentials,
            {"org_key": "TESTORGKEY"},
        )
        action.http_request = AsyncMock(
            return_value=mock_http_response({"results": [], "num_found": 0})
        )

        await action.execute()

        call_args = action.http_request.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url")
        assert url.startswith("https://defense.conferdeploy.net")

    @pytest.mark.asyncio
    async def test_org_key_in_url(self, mock_credentials, mock_settings):
        """Verify org_key is substituted into the URL path."""
        action = create_action(
            HealthCheckAction, "health_check", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=mock_http_response({"results": [], "num_found": 0})
        )

        await action.execute()

        call_args = action.http_request.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url")
        assert "TESTORGKEY" in url


# ============================================================================
# Envelope / Result Format Tests
# ============================================================================


class TestResultEnvelope:
    """Verify all actions produce standardized result envelopes."""

    @pytest.mark.asyncio
    async def test_success_result_envelope(self, mock_credentials, mock_settings):
        """Verify success_result contains standard fields."""
        action = create_action(
            GetDeviceAction, "get_device", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=mock_http_response({"results": [{"id": 1}], "num_found": 1})
        )

        result = await action.execute(device_id="1")

        assert result["status"] == "success"
        assert "integration_id" in result
        assert result["integration_id"] == "carbonblack"
        assert "action_id" in result
        assert "timestamp" in result
        assert "data" in result

    @pytest.mark.asyncio
    async def test_error_result_envelope(self, mock_credentials, mock_settings):
        """Verify error_result contains standard fields."""
        action = create_action(
            GetDeviceAction, "get_device", mock_credentials, mock_settings
        )

        result = await action.execute()  # Missing device_id

        assert result["status"] == "error"
        assert "integration_id" in result
        assert result["integration_id"] == "carbonblack"
        assert "action_id" in result
        assert "timestamp" in result
        assert "error" in result
        assert "error_type" in result
