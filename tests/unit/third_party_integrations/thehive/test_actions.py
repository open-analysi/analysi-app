"""Unit tests for TheHive integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.thehive.actions import (
    AddTtpAction,
    CreateAlertAction,
    CreateObservableAction,
    CreateTaskAction,
    CreateTaskLogAction,
    CreateTicketAction,
    GetAlertAction,
    GetObservablesAction,
    GetTicketAction,
    HealthCheckAction,
    ListAlertsAction,
    ListTicketsAction,
    SearchTaskAction,
    SearchTicketAction,
    UpdateTaskAction,
    UpdateTicketAction,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

DEFAULT_CREDENTIALS = {"api_key": "test-hive-key"}
DEFAULT_SETTINGS = {
    "base_url": "https://thehive.example.com:9000",
    "timeout": 30,
}


def _make_action(cls, credentials=None, settings=None):
    """Create an action instance for testing."""
    return cls(
        integration_id="thehive",
        action_id=cls.__name__,
        settings=DEFAULT_SETTINGS.copy() if settings is None else settings,
        credentials=DEFAULT_CREDENTIALS.copy() if credentials is None else credentials,
    )


def _mock_response(json_data, status_code=200):
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = json_data
    resp.status_code = status_code
    resp.text = str(json_data)
    return resp


def _mock_http_error(status_code, message="error"):
    """Create a mock httpx.HTTPStatusError."""
    request = MagicMock(spec=httpx.Request)
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = message
    return httpx.HTTPStatusError(message, request=request, response=response)


# ============================================================================
# HEALTH CHECK
# ============================================================================


class TestHealthCheckAction:
    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        action.http_request = AsyncMock(return_value=_mock_response([]))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(HealthCheckAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "api_key" in result["error"]

    @pytest.mark.asyncio
    async def test_connection_error(self, action):
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(401, "Unauthorized")
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert "HTTPStatusError" in result["error_type"]


# ============================================================================
# CREATE TICKET
# ============================================================================


class TestCreateTicketAction:
    @pytest.fixture
    def action(self):
        return _make_action(CreateTicketAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_response = {
            "_id": "AWQfCcret-_WVPphkhQq",
            "caseId": 22,
            "title": "Test Case",
            "description": "Test description",
            "severity": 2,
            "tlp": 2,
            "status": "Open",
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_response))

        result = await action.execute(title="Test Case", description="Test description")

        assert result["status"] == "success"
        assert result["data"]["caseId"] == 22
        assert result["data"]["title"] == "Test Case"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_title(self, action):
        result = await action.execute(description="desc")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "title" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_description(self, action):
        result = await action.execute(title="Title")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "description" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(CreateTicketAction, credentials={})
        result = await action.execute(title="Title", description="Desc")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_invalid_severity(self, action):
        result = await action.execute(
            title="Test", description="Test", severity="Critical"
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "severity" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_invalid_tlp(self, action):
        result = await action.execute(title="Test", description="Test", tlp="Black")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "tlp" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_with_optional_fields(self, action):
        api_response = {"_id": "abc123", "caseId": 5, "owner": "analyst1"}
        action.http_request = AsyncMock(return_value=_mock_response(api_response))

        result = await action.execute(
            title="Test",
            description="Desc",
            severity="High",
            tlp="Red",
            owner="analyst1",
            fields='{"customField": "value"}',
        )

        assert result["status"] == "success"
        # Verify the request body
        call_kwargs = action.http_request.call_args.kwargs
        json_data = call_kwargs["json_data"]
        assert json_data["severity"] == 3  # High
        assert json_data["tlp"] == 3  # Red
        assert json_data["owner"] == "analyst1"
        assert json_data["customField"] == "value"

    @pytest.mark.asyncio
    async def test_invalid_fields_json(self, action):
        result = await action.execute(
            title="Test", description="Desc", fields="not-valid-json"
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Internal Server Error")
        )
        result = await action.execute(title="Test", description="Desc")
        assert result["status"] == "error"


# ============================================================================
# GET TICKET
# ============================================================================


class TestGetTicketAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetTicketAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_response = {
            "_id": "AWGxGFw138eA2eAzW_e6",
            "caseId": 31,
            "title": "Test Case",
            "status": "Open",
            "severity": 3,
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_response))

        result = await action.execute(id="AWGxGFw138eA2eAzW_e6")

        assert result["status"] == "success"
        assert result["data"]["caseId"] == 31
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_id(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetTicketAction, credentials={})
        result = await action.execute(id="abc")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404, "Not Found"))
        result = await action.execute(id="nonexistent")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["id"] == "nonexistent"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Server Error")
        )
        result = await action.execute(id="abc")
        assert result["status"] == "error"


# ============================================================================
# UPDATE TICKET
# ============================================================================


class TestUpdateTicketAction:
    @pytest.fixture
    def action(self):
        return _make_action(UpdateTicketAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_response = {
            "_id": "AWQfCcret-_WVPphkhQq",
            "caseId": 125,
            "severity": 1,
            "status": "Open",
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_response))

        result = await action.execute(
            id="AWQfCcret-_WVPphkhQq",
            fields='{"severity": 1}',
        )

        assert result["status"] == "success"
        assert result["data"]["severity"] == 1
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_id(self, action):
        result = await action.execute(fields='{"severity": 1}')
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_fields(self, action):
        result = await action.execute(id="abc")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(UpdateTicketAction, credentials={})
        result = await action.execute(id="abc", fields='{"severity": 1}')
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_invalid_fields_json(self, action):
        result = await action.execute(id="abc", fields="not-json")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500, "Error"))
        result = await action.execute(id="abc", fields='{"severity": 1}')
        assert result["status"] == "error"


# ============================================================================
# LIST TICKETS
# ============================================================================


class TestListTicketsAction:
    @pytest.fixture
    def action(self):
        return _make_action(ListTicketsAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        tickets = [
            {"_id": "id1", "caseId": 1, "title": "Case 1"},
            {"_id": "id2", "caseId": 2, "title": "Case 2"},
        ]
        action.http_request = AsyncMock(return_value=_mock_response(tickets))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["count"] == 2
        assert len(result["data"]["tickets"]) == 2
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ListTicketsAction, credentials={})
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500, "Error"))
        result = await action.execute()
        assert result["status"] == "error"


# ============================================================================
# SEARCH TICKET
# ============================================================================


class TestSearchTicketAction:
    @pytest.fixture
    def action(self):
        return _make_action(SearchTicketAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        results_data = [{"_id": "id1", "title": "Matching Case"}]
        action.http_request = AsyncMock(return_value=_mock_response(results_data))

        result = await action.execute(search_ticket='{"_string": "test"}')

        assert result["status"] == "success"
        assert result["data"]["count"] == 1
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_search_query(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_json_query(self, action):
        result = await action.execute(search_ticket="not-json")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(SearchTicketAction, credentials={})
        result = await action.execute(search_ticket='{"_string": "test"}')
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# CREATE ALERT
# ============================================================================


class TestCreateAlertAction:
    @pytest.fixture
    def action(self):
        return _make_action(CreateAlertAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_response = {
            "_id": "alert123",
            "title": "Test Alert",
            "type": "external",
            "source": "SIEM",
            "sourceRef": "REF-001",
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_response))

        result = await action.execute(
            title="Test Alert",
            description="Alert desc",
            type="external",
            source="SIEM",
            source_ref="REF-001",
        )

        assert result["status"] == "success"
        assert result["data"]["title"] == "Test Alert"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_title(self, action):
        result = await action.execute(
            description="d", type="t", source="s", source_ref="r"
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "title" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_description(self, action):
        result = await action.execute(title="t", type="t", source="s", source_ref="r")
        assert result["status"] == "error"
        assert "description" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_type(self, action):
        result = await action.execute(
            title="t", description="d", source="s", source_ref="r"
        )
        assert result["status"] == "error"
        assert "type" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_source(self, action):
        result = await action.execute(
            title="t", description="d", type="t", source_ref="r"
        )
        assert result["status"] == "error"
        assert "source" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_source_ref(self, action):
        result = await action.execute(title="t", description="d", type="t", source="s")
        assert result["status"] == "error"
        assert "source_ref" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(CreateAlertAction, credentials={})
        result = await action.execute(
            title="t", description="d", type="t", source="s", source_ref="r"
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_with_tags_and_artifacts(self, action):
        action.http_request = AsyncMock(return_value=_mock_response({"_id": "a1"}))

        result = await action.execute(
            title="Alert",
            description="Desc",
            type="external",
            source="SIEM",
            source_ref="REF-001",
            tags="malware, phishing",
            artifacts='[{"dataType": "ip", "data": "1.2.3.4"}]',
        )

        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args.kwargs
        json_data = call_kwargs["json_data"]
        assert json_data["tags"] == ["malware", "phishing"]
        assert len(json_data["artifacts"]) == 1

    @pytest.mark.asyncio
    async def test_invalid_artifacts(self, action):
        result = await action.execute(
            title="Alert",
            description="Desc",
            type="external",
            source="SIEM",
            source_ref="REF-001",
            artifacts="not-a-json-list",
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_artifacts_not_list(self, action):
        result = await action.execute(
            title="Alert",
            description="Desc",
            type="external",
            source="SIEM",
            source_ref="REF-001",
            artifacts='{"key": "value"}',
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"


# ============================================================================
# GET ALERT
# ============================================================================


class TestGetAlertAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetAlertAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_response = {"_id": "alert123", "title": "Alert", "status": "New"}
        action.http_request = AsyncMock(return_value=_mock_response(api_response))

        result = await action.execute(id="alert123")

        assert result["status"] == "success"
        assert result["data"]["title"] == "Alert"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_id(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetAlertAction, credentials={})
        result = await action.execute(id="alert123")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404, "Not Found"))
        result = await action.execute(id="nonexistent")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["id"] == "nonexistent"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500, "Error"))
        result = await action.execute(id="alert123")
        assert result["status"] == "error"


# ============================================================================
# LIST ALERTS
# ============================================================================


class TestListAlertsAction:
    @pytest.fixture
    def action(self):
        return _make_action(ListAlertsAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        alerts = [{"_id": "a1"}, {"_id": "a2"}, {"_id": "a3"}]
        action.http_request = AsyncMock(return_value=_mock_response(alerts))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["count"] == 3
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ListAlertsAction, credentials={})
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# CREATE TASK
# ============================================================================


class TestCreateTaskAction:
    @pytest.fixture
    def action(self):
        return _make_action(CreateTaskAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_response = {"_id": "task123", "title": "Investigate", "status": "Waiting"}
        action.http_request = AsyncMock(return_value=_mock_response(api_response))

        result = await action.execute(
            id="case123", title="Investigate", status="Waiting"
        )

        assert result["status"] == "success"
        assert result["data"]["title"] == "Investigate"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_case_id(self, action):
        result = await action.execute(title="Task", status="Waiting")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_title(self, action):
        result = await action.execute(id="case1", status="Waiting")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_status(self, action):
        result = await action.execute(id="case1", title="Task")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_status(self, action):
        result = await action.execute(id="case1", title="Task", status="InvalidStatus")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "status" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(CreateTaskAction, credentials={})
        result = await action.execute(id="case1", title="Task", status="Waiting")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# UPDATE TASK
# ============================================================================


class TestUpdateTaskAction:
    @pytest.fixture
    def action(self):
        return _make_action(UpdateTaskAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_response = {"_id": "task123", "title": "Updated", "status": "InProgress"}
        action.http_request = AsyncMock(return_value=_mock_response(api_response))

        result = await action.execute(
            task_id="task123", task_title="Updated", task_status="InProgress"
        )

        assert result["status"] == "success"
        assert result["data"]["title"] == "Updated"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_task_id(self, action):
        result = await action.execute(task_title="Title")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_status(self, action):
        result = await action.execute(task_id="task1", task_status="BadStatus")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(UpdateTaskAction, credentials={})
        result = await action.execute(task_id="task1")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# SEARCH TASK
# ============================================================================


class TestSearchTaskAction:
    @pytest.fixture
    def action(self):
        return _make_action(SearchTaskAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        results_data = [{"_id": "task1", "title": "Found Task"}]
        action.http_request = AsyncMock(return_value=_mock_response(results_data))

        result = await action.execute(search_task='{"_string": "investigate"}')

        assert result["status"] == "success"
        assert result["data"]["count"] == 1
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_query(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_json(self, action):
        result = await action.execute(search_task="bad-json")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(SearchTaskAction, credentials={})
        result = await action.execute(search_task='{"_string": "test"}')
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# CREATE TASK LOG
# ============================================================================


class TestCreateTaskLogAction:
    @pytest.fixture
    def action(self):
        return _make_action(CreateTaskLogAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_response = {"_id": "log1", "message": "Investigation started"}
        action.http_request = AsyncMock(return_value=_mock_response(api_response))

        result = await action.execute(task_id="task1", message="Investigation started")

        assert result["status"] == "success"
        assert result["data"]["message"] == "Investigation started"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_task_id(self, action):
        result = await action.execute(message="msg")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_message(self, action):
        result = await action.execute(task_id="task1")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(CreateTaskLogAction, credentials={})
        result = await action.execute(task_id="task1", message="msg")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# GET OBSERVABLES
# ============================================================================


class TestGetObservablesAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetObservablesAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        observables = [
            {"_id": "obs1", "dataType": "ip", "data": "1.2.3.4"},
            {"_id": "obs2", "dataType": "domain", "data": "attacker.example"},
        ]
        action.http_request = AsyncMock(return_value=_mock_response(observables))

        result = await action.execute(ticket_id="case123")

        assert result["status"] == "success"
        assert result["data"]["count"] == 2
        assert len(result["data"]["observables"]) == 2
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_filtered_by_data_type(self, action):
        observables = [
            {"_id": "obs1", "dataType": "ip", "data": "1.2.3.4"},
            {"_id": "obs2", "dataType": "domain", "data": "attacker.example"},
        ]
        action.http_request = AsyncMock(return_value=_mock_response(observables))

        result = await action.execute(ticket_id="case123", data_type="ip")

        assert result["status"] == "success"
        assert result["data"]["count"] == 1
        assert result["data"]["observables"][0]["dataType"] == "ip"

    @pytest.mark.asyncio
    async def test_missing_ticket_id(self, action):
        result = await action.execute()
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_data_type(self, action):
        result = await action.execute(ticket_id="case1", data_type="invalid_type")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetObservablesAction, credentials={})
        result = await action.execute(ticket_id="case1")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# CREATE OBSERVABLE
# ============================================================================


class TestCreateObservableAction:
    @pytest.fixture
    def action(self):
        return _make_action(CreateObservableAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_response = {
            "_id": "obs123",
            "dataType": "ip",
            "data": "1.2.3.4",
            "tlp": 2,
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_response))

        result = await action.execute(id="case1", data_type="ip", data="1.2.3.4")

        assert result["status"] == "success"
        assert result["data"]["dataType"] == "ip"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_id(self, action):
        result = await action.execute(data_type="ip", data="1.2.3.4")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_data_type(self, action):
        result = await action.execute(id="case1", data="1.2.3.4")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_data_type(self, action):
        result = await action.execute(id="case1", data_type="invalid", data="x")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_file_type_not_supported(self, action):
        result = await action.execute(id="case1", data_type="file", data="x")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "not supported" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_missing_data_for_non_file(self, action):
        result = await action.execute(id="case1", data_type="ip")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(CreateObservableAction, credentials={})
        result = await action.execute(id="case1", data_type="ip", data="1.2.3.4")
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_invalid_ticket_type(self, action):
        result = await action.execute(
            id="case1", data_type="ip", data="1.2.3.4", ticket_type="Invalid"
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_alert_ticket_type(self, action):
        api_response = {"_id": "obs1", "dataType": "ip", "data": "1.2.3.4"}
        action.http_request = AsyncMock(return_value=_mock_response(api_response))

        result = await action.execute(
            id="alert1", data_type="ip", data="1.2.3.4", ticket_type="Alert"
        )

        assert result["status"] == "success"
        call_url = action.http_request.call_args.kwargs["url"]
        assert "/api/alert/alert1/artifact" in call_url

    @pytest.mark.asyncio
    async def test_list_response_extracts_first(self, action):
        """API may return a list; action should extract first item."""
        action.http_request = AsyncMock(
            return_value=_mock_response([{"_id": "obs1"}, {"_id": "obs2"}])
        )

        result = await action.execute(id="case1", data_type="ip", data="1.2.3.4")

        assert result["status"] == "success"
        assert result["data"]["_id"] == "obs1"

    @pytest.mark.asyncio
    async def test_failure_response_from_api(self, action):
        """TheHive may return success with embedded failure."""
        action.http_request = AsyncMock(
            return_value=_mock_response(
                {"failure": [{"type": "DuplicateError", "message": "Already exists"}]}
            )
        )

        result = await action.execute(id="case1", data_type="ip", data="1.2.3.4")

        assert result["status"] == "error"
        assert "DuplicateError" in result["error"]

    @pytest.mark.asyncio
    async def test_with_optional_params(self, action):
        action.http_request = AsyncMock(return_value=_mock_response({"_id": "obs1"}))

        result = await action.execute(
            id="case1",
            data_type="domain",
            data="attacker.example",
            tlp="Red",
            tags="tag1, tag2",
            description="Malicious domain",
            ioc=True,
            sighted=True,
        )

        assert result["status"] == "success"
        json_data = action.http_request.call_args.kwargs["json_data"]
        assert json_data["tlp"] == 3  # Red
        assert json_data["tags"] == ["tag1", "tag2"]
        assert json_data["message"] == "Malicious domain"
        assert json_data["ioc"] is True
        assert json_data["sighted"] is True


# ============================================================================
# ADD TTP
# ============================================================================


class TestAddTtpAction:
    @pytest.fixture
    def action(self):
        return _make_action(AddTtpAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        api_response = {
            "_id": "proc1",
            "caseId": "case1",
            "patternId": "T1059",
            "tactic": "execution",
        }
        action.http_request = AsyncMock(return_value=_mock_response(api_response))

        result = await action.execute(
            id="case1", pattern_id="T1059", tactic="execution"
        )

        assert result["status"] == "success"
        assert result["data"]["patternId"] == "T1059"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_id(self, action):
        result = await action.execute(pattern_id="T1059", tactic="execution")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_pattern_id(self, action):
        result = await action.execute(id="case1", tactic="execution")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_tactic(self, action):
        result = await action.execute(id="case1", pattern_id="T1059")
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_tactic(self, action):
        result = await action.execute(
            id="case1", pattern_id="T1059", tactic="invalid-tactic"
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "tactic" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(AddTtpAction, credentials={})
        result = await action.execute(
            id="case1", pattern_id="T1059", tactic="execution"
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_with_optional_params(self, action):
        action.http_request = AsyncMock(return_value=_mock_response({"_id": "proc1"}))

        result = await action.execute(
            id="case1",
            pattern_id="T1059",
            tactic="execution",
            occur_date=1700000000000,
            description="PowerShell execution observed",
        )

        assert result["status"] == "success"
        json_data = action.http_request.call_args.kwargs["json_data"]
        assert json_data["occurDate"] == 1700000000000
        assert json_data["description"] == "PowerShell execution observed"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500, "Error"))
        result = await action.execute(
            id="case1", pattern_id="T1059", tactic="execution"
        )
        assert result["status"] == "error"
