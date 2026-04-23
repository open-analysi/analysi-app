"""Unit tests for Tanium REST integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.tanium.actions import (
    ExecuteActionAction,
    GetQuestionResultsAction,
    GetSystemStatusAction,
    HealthCheckAction,
    ListPackagesAction,
    ListSavedQuestionsAction,
    RunQueryAction,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def credentials_token():
    """Credentials using API token auth."""
    return {"api_token": "test-api-token-12345"}


@pytest.fixture
def credentials_userpass():
    """Credentials using username/password auth."""
    return {"username": "admin", "password": "s3cret"}


@pytest.fixture
def settings():
    """Default integration settings."""
    return {
        "base_url": "https://tanium.example.com",
        "timeout": 30,
        "verify_ssl": False,
    }


def create_action(
    action_class, action_id="test_action", credentials=None, settings=None
):
    """Helper to create action instances with required parameters."""
    return action_class(
        integration_id="tanium",
        action_id=action_id,
        credentials=credentials or {},
        settings=settings or {},
    )


def _mock_json_response(data, status_code=200):
    """Build a mock httpx.Response with a .json() return value."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


def _mock_http_status_error(status_code=401, message="Unauthorized"):
    """Build a mock httpx.HTTPStatusError for testing error paths."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.text = message
    mock_request = MagicMock(spec=httpx.Request)
    return httpx.HTTPStatusError(
        message=message,
        request=mock_request,
        response=mock_response,
    )


# ============================================================================
# HealthCheckAction Tests
# ============================================================================


class TestHealthCheckAction:
    """Tests for HealthCheckAction."""

    @pytest.mark.asyncio
    async def test_success_with_api_token(self, credentials_token, settings):
        """Health check succeeds with API token auth."""
        action = create_action(
            HealthCheckAction, "health_check", credentials_token, settings
        )

        # With API token, only the saved_questions call is made (no login)
        saved_questions_resp = _mock_json_response({"data": [{"id": 1, "name": "Q1"}]})
        action.http_request = AsyncMock(return_value=saved_questions_resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["healthy"] is True
        assert result["data"]["base_url"] == "https://tanium.example.com"
        assert "integration_id" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_success_with_username_password(self, credentials_userpass, settings):
        """Health check succeeds with username/password auth."""
        action = create_action(
            HealthCheckAction, "health_check", credentials_userpass, settings
        )

        login_resp = _mock_json_response({"data": {"session": "tok-abc123"}})
        saved_questions_resp = _mock_json_response({"data": [{"id": 1}]})
        action.http_request = AsyncMock(side_effect=[login_resp, saved_questions_resp])

        result = await action.execute()

        assert result["status"] == "success"
        assert result["healthy"] is True

    @pytest.mark.asyncio
    async def test_missing_credentials(self, settings):
        """Health check fails when no credentials are provided."""
        action = create_action(HealthCheckAction, "health_check", {}, settings)

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_missing_base_url(self, credentials_token):
        """Health check fails when base_url is missing."""
        action = create_action(HealthCheckAction, "health_check", credentials_token, {})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "base_url" in result["error"]

    @pytest.mark.asyncio
    async def test_auth_failure(self, credentials_userpass, settings):
        """Health check fails when authentication fails."""
        action = create_action(
            HealthCheckAction, "health_check", credentials_userpass, settings
        )

        action.http_request = AsyncMock(side_effect=_mock_http_status_error(401))

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"
        assert result.get("healthy") is False

    @pytest.mark.asyncio
    async def test_connection_error(self, credentials_token, settings):
        """Health check fails on network error."""
        action = create_action(
            HealthCheckAction, "health_check", credentials_token, settings
        )

        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result.get("healthy") is False


# ============================================================================
# RunQueryAction Tests
# ============================================================================


class TestRunQueryAction:
    """Tests for RunQueryAction."""

    @pytest.mark.asyncio
    async def test_success(self, credentials_token, settings):
        """Successfully run a query and get question ID."""
        action = create_action(RunQueryAction, "run_query", credentials_token, settings)

        parse_resp = _mock_json_response(
            {
                "data": [
                    {
                        "question_text": "Get Computer Name from all machines",
                        "selects": [],
                    }
                ]
            }
        )
        question_resp = _mock_json_response({"data": {"id": 42}})
        action.http_request = AsyncMock(side_effect=[parse_resp, question_resp])

        result = await action.execute(query_text="Get Computer Name from all machines")

        assert result["status"] == "success"
        assert result["data"]["question_id"] == 42
        assert result["data"]["query_text"] == "Get Computer Name from all machines"

    @pytest.mark.asyncio
    async def test_with_group_name(self, credentials_token, settings):
        """Query scoped to a computer group."""
        action = create_action(RunQueryAction, "run_query", credentials_token, settings)

        parse_resp = _mock_json_response(
            {
                "data": [
                    {"question_text": "Get IP Address from all machines", "selects": []}
                ]
            }
        )
        group_resp = _mock_json_response({"data": {"id": 10, "name": "Servers"}})
        question_resp = _mock_json_response({"data": {"id": 99}})
        action.http_request = AsyncMock(
            side_effect=[parse_resp, group_resp, question_resp]
        )

        result = await action.execute(
            query_text="Get IP Address from all machines",
            group_name="Servers",
        )

        assert result["status"] == "success"
        assert result["data"]["question_id"] == 99
        assert result["data"]["group_name"] == "Servers"

    @pytest.mark.asyncio
    async def test_missing_query_text(self, credentials_token, settings):
        """Fails with validation error when query_text is missing."""
        action = create_action(RunQueryAction, "run_query", credentials_token, settings)

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "query_text" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_timeout_seconds(self, credentials_token, settings):
        """Fails when timeout_seconds is not a valid integer."""
        action = create_action(RunQueryAction, "run_query", credentials_token, settings)

        result = await action.execute(
            query_text="Get Computer Name", timeout_seconds="abc"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_negative_timeout_seconds(self, credentials_token, settings):
        """Fails when timeout_seconds is negative."""
        action = create_action(RunQueryAction, "run_query", credentials_token, settings)

        result = await action.execute(
            query_text="Get Computer Name", timeout_seconds=-5
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_parse_failure(self, credentials_token, settings):
        """Fails when question cannot be parsed."""
        action = create_action(RunQueryAction, "run_query", credentials_token, settings)

        parse_resp = _mock_json_response({"data": []})
        action.http_request = AsyncMock(return_value=parse_resp)

        result = await action.execute(query_text="bad query syntax")

        assert result["status"] == "error"
        assert "parsed" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_http_error(self, credentials_token, settings):
        """Handles HTTP errors from the Tanium API."""
        action = create_action(RunQueryAction, "run_query", credentials_token, settings)

        action.http_request = AsyncMock(
            side_effect=_mock_http_status_error(500, "Server Error")
        )

        result = await action.execute(query_text="Get Computer Name")

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# GetQuestionResultsAction Tests
# ============================================================================


class TestGetQuestionResultsAction:
    """Tests for GetQuestionResultsAction."""

    @pytest.mark.asyncio
    async def test_success(self, credentials_token, settings):
        """Successfully retrieve question results."""
        action = create_action(
            GetQuestionResultsAction,
            "get_question_results",
            credentials_token,
            settings,
        )

        results_resp = _mock_json_response(
            {
                "data": {
                    "result_sets": [
                        {
                            "row_count": 5,
                            "columns": [{"name": "Computer Name"}],
                            "rows": [
                                {"data": [{"text": "HOST-01"}]},
                            ],
                        }
                    ]
                }
            }
        )
        action.http_request = AsyncMock(return_value=results_resp)

        result = await action.execute(question_id=42)

        assert result["status"] == "success"
        assert result["data"]["question_id"] == 42
        assert result["data"]["row_count"] == 5
        assert len(result["data"]["result_sets"]) == 1

    @pytest.mark.asyncio
    async def test_missing_question_id(self, credentials_token, settings):
        """Fails when question_id is not provided."""
        action = create_action(
            GetQuestionResultsAction,
            "get_question_results",
            credentials_token,
            settings,
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "question_id" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_question_id(self, credentials_token, settings):
        """Fails when question_id is not a valid integer."""
        action = create_action(
            GetQuestionResultsAction,
            "get_question_results",
            credentials_token,
            settings,
        )

        result = await action.execute(question_id="not-a-number")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_question_not_found(self, credentials_token, settings):
        """Returns success with not_found=True for 404."""
        action = create_action(
            GetQuestionResultsAction,
            "get_question_results",
            credentials_token,
            settings,
        )

        action.http_request = AsyncMock(
            side_effect=_mock_http_status_error(404, "Not Found")
        )

        result = await action.execute(question_id=99999)

        assert result["status"] == "success"
        assert result.get("not_found") is True
        assert result["data"]["question_id"] == 99999
        assert result["data"]["row_count"] == 0

    @pytest.mark.asyncio
    async def test_http_error(self, credentials_token, settings):
        """Handles non-404 HTTP errors."""
        action = create_action(
            GetQuestionResultsAction,
            "get_question_results",
            credentials_token,
            settings,
        )

        action.http_request = AsyncMock(
            side_effect=_mock_http_status_error(500, "Server Error")
        )

        result = await action.execute(question_id=42)

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# ListSavedQuestionsAction Tests
# ============================================================================


class TestListSavedQuestionsAction:
    """Tests for ListSavedQuestionsAction."""

    @pytest.mark.asyncio
    async def test_success(self, credentials_token, settings):
        """Successfully list saved questions."""
        action = create_action(
            ListSavedQuestionsAction,
            "list_saved_questions",
            credentials_token,
            settings,
        )

        resp = _mock_json_response(
            {
                "data": [
                    {"id": 1, "name": "All Processes"},
                    {"id": 2, "name": "IP Addresses"},
                ]
            }
        )
        action.http_request = AsyncMock(return_value=resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["count"] == 2
        assert len(result["data"]["saved_questions"]) == 2

    @pytest.mark.asyncio
    async def test_empty_list(self, credentials_token, settings):
        """Returns empty list when no saved questions exist."""
        action = create_action(
            ListSavedQuestionsAction,
            "list_saved_questions",
            credentials_token,
            settings,
        )

        resp = _mock_json_response({"data": []})
        action.http_request = AsyncMock(return_value=resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["count"] == 0

    @pytest.mark.asyncio
    async def test_http_error(self, credentials_token, settings):
        """Handles HTTP errors."""
        action = create_action(
            ListSavedQuestionsAction,
            "list_saved_questions",
            credentials_token,
            settings,
        )

        action.http_request = AsyncMock(
            side_effect=_mock_http_status_error(403, "Forbidden")
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# GetSystemStatusAction Tests
# ============================================================================


class TestGetSystemStatusAction:
    """Tests for GetSystemStatusAction."""

    @pytest.mark.asyncio
    async def test_success(self, credentials_token, settings):
        """Successfully retrieve system status."""
        action = create_action(
            GetSystemStatusAction, "get_system_status", credentials_token, settings
        )

        resp = _mock_json_response(
            {
                "data": {
                    "version": "7.5.4.1158",
                    "active_questions": 12,
                    "registered_count": 500,
                }
            }
        )
        action.http_request = AsyncMock(return_value=resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["version"] == "7.5.4.1158"
        assert result["data"]["registered_count"] == 500

    @pytest.mark.asyncio
    async def test_http_error(self, credentials_token, settings):
        """Handles HTTP errors."""
        action = create_action(
            GetSystemStatusAction, "get_system_status", credentials_token, settings
        )

        action.http_request = AsyncMock(
            side_effect=_mock_http_status_error(500, "Server Error")
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# ExecuteActionAction Tests
# ============================================================================


class TestExecuteActionAction:
    """Tests for ExecuteActionAction."""

    @pytest.mark.asyncio
    async def test_success(self, credentials_token, settings):
        """Successfully execute a Tanium action."""
        action = create_action(
            ExecuteActionAction, "execute_action", credentials_token, settings
        )

        pkg_resp = _mock_json_response({"data": {"id": 10, "name": "Kill Process"}})
        ag_resp = _mock_json_response({"data": {"id": 5, "name": "Default"}})
        execute_resp = _mock_json_response(
            {"data": {"id": 100, "name": "Kill Notepad", "status": "Active"}}
        )
        action.http_request = AsyncMock(side_effect=[pkg_resp, ag_resp, execute_resp])

        result = await action.execute(
            action_name="Kill Notepad",
            action_group="Default",
            package_name="Kill Process",
            expire_seconds=300,
        )

        assert result["status"] == "success"
        assert result["data"]["id"] == 100

    @pytest.mark.asyncio
    async def test_with_package_parameters(self, credentials_token, settings):
        """Execute action with package parameters."""
        action = create_action(
            ExecuteActionAction, "execute_action", credentials_token, settings
        )

        pkg_resp = _mock_json_response({"data": {"id": 10}})
        ag_resp = _mock_json_response({"data": {"id": 5}})
        execute_resp = _mock_json_response({"data": {"id": 101}})
        action.http_request = AsyncMock(side_effect=[pkg_resp, ag_resp, execute_resp])

        result = await action.execute(
            action_name="Test Action",
            action_group="Default",
            package_name="Test Package",
            package_parameters={"process_name": "notepad.exe"},
        )

        assert result["status"] == "success"
        # Verify the package parameters were included in the request
        call_args = action.http_request.call_args_list[2]
        payload = call_args.kwargs.get("json_data", {})
        assert "parameters" in payload.get("package_spec", {})

    @pytest.mark.asyncio
    async def test_with_target_group(self, credentials_token, settings):
        """Execute action scoped to a target computer group."""
        action = create_action(
            ExecuteActionAction, "execute_action", credentials_token, settings
        )

        pkg_resp = _mock_json_response({"data": {"id": 10}})
        ag_resp = _mock_json_response({"data": {"id": 5}})
        grp_resp = _mock_json_response({"data": {"id": 20, "name": "Servers"}})
        execute_resp = _mock_json_response({"data": {"id": 102}})
        action.http_request = AsyncMock(
            side_effect=[pkg_resp, ag_resp, grp_resp, execute_resp]
        )

        result = await action.execute(
            action_name="Test Action",
            action_group="Default",
            package_name="Test Package",
            group_name="Servers",
        )

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_missing_action_name(self, credentials_token, settings):
        """Fails when action_name is missing."""
        action = create_action(
            ExecuteActionAction, "execute_action", credentials_token, settings
        )

        result = await action.execute(
            action_group="Default",
            package_name="Package",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "action_name" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_action_group(self, credentials_token, settings):
        """Fails when action_group is missing."""
        action = create_action(
            ExecuteActionAction, "execute_action", credentials_token, settings
        )

        result = await action.execute(
            action_name="Test",
            package_name="Package",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "action_group" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_package_name(self, credentials_token, settings):
        """Fails when package_name is missing."""
        action = create_action(
            ExecuteActionAction, "execute_action", credentials_token, settings
        )

        result = await action.execute(
            action_name="Test",
            action_group="Default",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "package_name" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_expire_seconds(self, credentials_token, settings):
        """Fails when expire_seconds is not valid."""
        action = create_action(
            ExecuteActionAction, "execute_action", credentials_token, settings
        )

        result = await action.execute(
            action_name="Test",
            action_group="Default",
            package_name="Package",
            expire_seconds="bad",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_package_not_found(self, credentials_token, settings):
        """Fails when the package does not exist."""
        action = create_action(
            ExecuteActionAction, "execute_action", credentials_token, settings
        )

        pkg_resp = _mock_json_response({"data": None})
        action.http_request = AsyncMock(return_value=pkg_resp)

        result = await action.execute(
            action_name="Test",
            action_group="Default",
            package_name="NonExistent",
        )

        assert result["status"] == "error"
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_action_group_not_found(self, credentials_token, settings):
        """Fails when the action group does not exist."""
        action = create_action(
            ExecuteActionAction, "execute_action", credentials_token, settings
        )

        pkg_resp = _mock_json_response({"data": {"id": 10}})
        ag_resp = _mock_json_response({"data": None})
        action.http_request = AsyncMock(side_effect=[pkg_resp, ag_resp])

        result = await action.execute(
            action_name="Test",
            action_group="NonExistent",
            package_name="Package",
        )

        assert result["status"] == "error"
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_http_error(self, credentials_token, settings):
        """Handles HTTP errors."""
        action = create_action(
            ExecuteActionAction, "execute_action", credentials_token, settings
        )

        action.http_request = AsyncMock(
            side_effect=_mock_http_status_error(500, "Server Error")
        )

        result = await action.execute(
            action_name="Test",
            action_group="Default",
            package_name="Package",
        )

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# ListPackagesAction Tests
# ============================================================================


class TestListPackagesAction:
    """Tests for ListPackagesAction."""

    @pytest.mark.asyncio
    async def test_success(self, credentials_token, settings):
        """Successfully list packages."""
        action = create_action(
            ListPackagesAction, "list_packages", credentials_token, settings
        )

        resp = _mock_json_response(
            {
                "data": [
                    {"id": 1, "name": "Kill Process", "display_name": "Kill Process"},
                    {"id": 2, "name": "Reboot", "display_name": "Reboot Machine"},
                ]
            }
        )
        action.http_request = AsyncMock(return_value=resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["count"] == 2
        assert len(result["data"]["packages"]) == 2

    @pytest.mark.asyncio
    async def test_empty_list(self, credentials_token, settings):
        """Returns empty list when no packages exist."""
        action = create_action(
            ListPackagesAction, "list_packages", credentials_token, settings
        )

        resp = _mock_json_response({"data": []})
        action.http_request = AsyncMock(return_value=resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["count"] == 0

    @pytest.mark.asyncio
    async def test_http_error(self, credentials_token, settings):
        """Handles HTTP errors."""
        action = create_action(
            ListPackagesAction, "list_packages", credentials_token, settings
        )

        action.http_request = AsyncMock(
            side_effect=_mock_http_status_error(403, "Forbidden")
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"


# ============================================================================
# Auth Helper Tests (via HealthCheckAction as driver)
# ============================================================================


class TestAuthHelpers:
    """Tests for the session token authentication flow."""

    @pytest.mark.asyncio
    async def test_api_token_used_directly(self, credentials_token, settings):
        """When api_token is provided, no login call is made."""
        action = create_action(
            HealthCheckAction, "health_check", credentials_token, settings
        )

        resp = _mock_json_response({"data": []})
        action.http_request = AsyncMock(return_value=resp)

        result = await action.execute()

        assert result["status"] == "success"
        # Only one call (saved_questions), not two (login + saved_questions)
        assert action.http_request.call_count == 1
        # Verify session header uses the api_token
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["headers"]["session"] == "test-api-token-12345"

    @pytest.mark.asyncio
    async def test_username_password_login(self, credentials_userpass, settings):
        """Username/password triggers login, then uses returned session token."""
        action = create_action(
            HealthCheckAction, "health_check", credentials_userpass, settings
        )

        login_resp = _mock_json_response({"data": {"session": "session-from-login"}})
        saved_q_resp = _mock_json_response({"data": []})
        action.http_request = AsyncMock(side_effect=[login_resp, saved_q_resp])

        result = await action.execute()

        assert result["status"] == "success"
        # Two calls: login + saved_questions
        assert action.http_request.call_count == 2
        # First call is login POST
        first_call = action.http_request.call_args_list[0]
        assert "/session/login" in first_call.kwargs.get("url", "")
        assert first_call.kwargs.get("method") == "POST"
        # Second call uses the session token from login
        second_call = action.http_request.call_args_list[1]
        assert second_call.kwargs["headers"]["session"] == "session-from-login"

    @pytest.mark.asyncio
    async def test_login_failure_propagates(self, credentials_userpass, settings):
        """Login failure propagates as error result."""
        action = create_action(
            HealthCheckAction, "health_check", credentials_userpass, settings
        )

        action.http_request = AsyncMock(
            side_effect=_mock_http_status_error(401, "Bad creds")
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_login_returns_no_session(self, credentials_userpass, settings):
        """Error when login succeeds but no session token is returned."""
        action = create_action(
            HealthCheckAction, "health_check", credentials_userpass, settings
        )

        login_resp = _mock_json_response({"data": {}})  # Missing "session" key
        action.http_request = AsyncMock(return_value=login_resp)

        result = await action.execute()

        assert result["status"] == "error"
        assert "session token" in result["error"].lower()
