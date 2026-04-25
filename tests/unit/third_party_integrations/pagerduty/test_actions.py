"""Unit tests for PagerDuty integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.pagerduty.actions import (
    CreateIncidentAction,
    GetOncallUserAction,
    GetUserInfoAction,
    HealthCheckAction,
    ListEscalationsAction,
    ListOncallsAction,
    ListServicesAction,
    ListTeamsAction,
    ListUsersAction,
    _build_array_params,
    _parse_csv_ids,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

DEFAULT_CREDENTIALS = {"api_token": "test-pd-token-abc123"}
DEFAULT_SETTINGS = {
    "base_url": "https://api.pagerduty.com",
    "timeout": 30,
}


def _make_action(cls, credentials=None, settings=None):
    """Create an action instance for testing."""
    return cls(
        integration_id="pagerduty",
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
# HELPER TESTS
# ============================================================================


class TestParseCsvIds:
    def test_parses_comma_separated(self):
        assert _parse_csv_ids("A,B,C") == ["A", "B", "C"]

    def test_trims_whitespace(self):
        assert _parse_csv_ids(" A , B , C ") == ["A", "B", "C"]

    def test_returns_empty_for_none(self):
        assert _parse_csv_ids(None) == []

    def test_returns_empty_for_empty_string(self):
        assert _parse_csv_ids("") == []

    def test_filters_blanks(self):
        assert _parse_csv_ids("A,,B, ,C") == ["A", "B", "C"]


class TestBuildArrayParams:
    def test_builds_bracket_key(self):
        result = _build_array_params("team_ids", ["A", "B"])
        assert result == {"team_ids[]": ["A", "B"]}

    def test_empty_values(self):
        assert _build_array_params("team_ids", []) == {}


# ============================================================================
# HEALTH CHECK
# ============================================================================


class TestHealthCheckAction:
    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        action.http_request = AsyncMock(return_value=_mock_response({"incidents": []}))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert "integration_id" in result
        action.http_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_api_token(self):
        action = _make_action(HealthCheckAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "api_token" in result["error"]

    @pytest.mark.asyncio
    async def test_connection_error(self, action):
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_http_401_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(401, "Unauthorized")
        )
        result = await action.execute()

        assert result["status"] == "error"
        assert "HTTPStatusError" in result["error_type"]


# ============================================================================
# LIST TEAMS
# ============================================================================


class TestListTeamsAction:
    @pytest.fixture
    def action(self):
        return _make_action(ListTeamsAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response(
                {
                    "teams": [
                        {"id": "P3Y9EUF", "name": "IT", "type": "team"},
                        {"id": "PABCDEF", "name": "Eng", "type": "team"},
                    ],
                    "more": False,
                }
            )
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_teams"] == 2
        assert len(result["data"]["teams"]) == 2
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ListTeamsAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Internal Server Error")
        )
        result = await action.execute()

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_pagination(self, action):
        """Test that multiple pages are combined."""
        page1 = _mock_response(
            {
                "teams": [{"id": "T1", "name": "Team1"}],
                "more": True,
            }
        )
        page2 = _mock_response(
            {
                "teams": [{"id": "T2", "name": "Team2"}],
                "more": False,
            }
        )
        action.http_request = AsyncMock(side_effect=[page1, page2])

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_teams"] == 2
        assert action.http_request.call_count == 2


# ============================================================================
# LIST ONCALLS
# ============================================================================


class TestListOncallsAction:
    @pytest.fixture
    def action(self):
        return _make_action(ListOncallsAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response(
                {
                    "oncalls": [
                        {
                            "escalation_level": 1,
                            "user": {"id": "PG4RNZ3", "summary": "Test User"},
                            "escalation_policy": {"id": "PE0BI2T"},
                        }
                    ],
                    "more": False,
                }
            )
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_oncalls"] == 1
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ListOncallsAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(403, "Forbidden"))
        result = await action.execute()

        assert result["status"] == "error"


# ============================================================================
# LIST SERVICES
# ============================================================================


class TestListServicesAction:
    @pytest.fixture
    def action(self):
        return _make_action(ListServicesAction)

    @pytest.mark.asyncio
    async def test_success_no_filter(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response(
                {
                    "services": [
                        {"id": "P85HN53", "name": "API Service", "status": "active"}
                    ],
                    "more": False,
                }
            )
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_services"] == 1
        assert result["data"]["services"][0]["name"] == "API Service"

    @pytest.mark.asyncio
    async def test_success_with_team_filter(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response({"services": [{"id": "S1"}], "more": False})
        )

        result = await action.execute(team_ids="P3Y9EUF,PABCDEF")

        assert result["status"] == "success"
        # Verify team_ids[] params were passed
        call_kwargs = action.http_request.call_args.kwargs
        assert "team_ids[]" in call_kwargs["params"]

    @pytest.mark.asyncio
    async def test_invalid_team_ids(self, action):
        result = await action.execute(team_ids="  ,  , ")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "team_ids" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ListServicesAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# LIST USERS
# ============================================================================


class TestListUsersAction:
    @pytest.fixture
    def action(self):
        return _make_action(ListUsersAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response(
                {
                    "users": [
                        {
                            "id": "PDQZBR8",
                            "name": "Test User",
                            "email": "test@example.com",
                        }
                    ],
                    "more": False,
                }
            )
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_users"] == 1
        assert result["data"]["users"][0]["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_with_team_filter(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response({"users": [], "more": False})
        )

        result = await action.execute(team_ids="P3Y9EUF")

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_invalid_team_ids(self, action):
        result = await action.execute(team_ids="  ")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ListUsersAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# LIST ESCALATION POLICIES
# ============================================================================


class TestListEscalationsAction:
    @pytest.fixture
    def action(self):
        return _make_action(ListEscalationsAction)

    @pytest.mark.asyncio
    async def test_success_no_filter(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response(
                {
                    "escalation_policies": [
                        {"id": "PEEMY9J", "name": "Default", "num_loops": 0}
                    ],
                    "more": False,
                }
            )
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_policies"] == 1
        assert result["data"]["escalation_policies"][0]["name"] == "Default"

    @pytest.mark.asyncio
    async def test_with_user_and_team_filter(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response(
                {"escalation_policies": [{"id": "P1"}], "more": False}
            )
        )

        result = await action.execute(user_ids="PG4RNZ3,P9GBXBY", team_ids="P3Y9EUF")

        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args.kwargs
        assert "user_ids[]" in call_kwargs["params"]
        assert "team_ids[]" in call_kwargs["params"]

    @pytest.mark.asyncio
    async def test_invalid_team_ids(self, action):
        result = await action.execute(team_ids=" , ")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_user_ids(self, action):
        result = await action.execute(user_ids=" , ")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ListEscalationsAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# CREATE INCIDENT
# ============================================================================


class TestCreateIncidentAction:
    @pytest.fixture
    def action(self):
        return _make_action(CreateIncidentAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response(
                {
                    "incident": {
                        "id": "PTX014C",
                        "title": "Test Incident",
                        "incident_key": "test-inc-key-001",
                        "status": "triggered",
                        "service": {"id": "PZ020AS"},
                    }
                }
            )
        )

        result = await action.execute(
            title="Test Incident",
            description="Fix it",
            service_id="PZ020AS",
            email="test@example.com",
        )

        assert result["status"] == "success"
        assert result["data"]["incident"]["id"] == "PTX014C"
        assert result["data"]["incident_key"] == "test-inc-key-001"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_with_escalation_and_assignee(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response(
                {"incident": {"id": "P1", "incident_key": "key1"}}
            )
        )

        result = await action.execute(
            title="Incident",
            description="Details",
            service_id="SVC1",
            email="user@example.com",
            escalation_id="ESC1",
            assignee_id="USR1",
        )

        assert result["status"] == "success"
        # Verify the body included escalation_policy and assignments
        call_kwargs = action.http_request.call_args.kwargs
        body = call_kwargs["json_data"]
        assert body["incident"]["escalation_policy"]["id"] == "ESC1"
        assert body["incident"]["assignments"][0]["assignee"]["id"] == "USR1"

    @pytest.mark.asyncio
    async def test_missing_title(self, action):
        result = await action.execute(
            description="Desc", service_id="SVC1", email="e@e.com"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "title" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_description(self, action):
        result = await action.execute(title="Title", service_id="SVC1", email="e@e.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "description" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_service_id(self, action):
        result = await action.execute(
            title="Title", description="Desc", email="e@e.com"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "service_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_email(self, action):
        result = await action.execute(
            title="Title", description="Desc", service_id="SVC1"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "email" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(CreateIncidentAction, credentials={})
        result = await action.execute(
            title="T", description="D", service_id="S", email="e@e.com"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(400, "Bad Request")
        )
        result = await action.execute(
            title="T", description="D", service_id="S", email="e@e.com"
        )

        assert result["status"] == "error"


# ============================================================================
# GET ONCALL USER
# ============================================================================


class TestGetOncallUserAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetOncallUserAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        oncall_resp = _mock_response(
            {
                "oncalls": [
                    {
                        "escalation_level": 1,
                        "user": {"id": "PG4RNZ3", "summary": "User1"},
                        "escalation_policy": {"id": "PE0BI2T"},
                    },
                ]
            }
        )
        user_resp = _mock_response(
            {
                "user": {
                    "id": "PG4RNZ3",
                    "name": "Full User 1",
                    "email": "user1@example.com",
                }
            }
        )
        action.http_request = AsyncMock(side_effect=[oncall_resp, user_resp])

        result = await action.execute(escalation_id="PE0BI2T")

        assert result["status"] == "success"
        assert result["data"]["total_users"] == 1
        # Verify user was enriched with full details
        assert result["data"]["oncalls"][0]["user"]["name"] == "Full User 1"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_escalation_id(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "escalation_id" in result["error"]

    @pytest.mark.asyncio
    async def test_not_found_404(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404, "Not found"))
        result = await action.execute(escalation_id="NONEXIST")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["total_users"] == 0

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetOncallUserAction, credentials={})
        result = await action.execute(escalation_id="PE0BI2T")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Server Error")
        )
        result = await action.execute(escalation_id="PE0BI2T")

        assert result["status"] == "error"


# ============================================================================
# GET USER INFO
# ============================================================================


class TestGetUserInfoAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetUserInfoAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response(
                {
                    "user": {
                        "id": "P9GBXBY",
                        "name": "Test User",
                        "email": "test@example.com",
                        "role": "admin",
                        "time_zone": "America/Los_Angeles",
                    }
                }
            )
        )

        result = await action.execute(user_id="P9GBXBY")

        assert result["status"] == "success"
        assert result["data"]["user"]["name"] == "Test User"
        assert result["data"]["name"] == "Test User"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_user_id(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "user_id" in result["error"]

    @pytest.mark.asyncio
    async def test_not_found_404(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404, "Not found"))
        result = await action.execute(user_id="NONEXIST")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["user"] == {}

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetUserInfoAction, credentials={})
        result = await action.execute(user_id="P9GBXBY")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(403, "Forbidden"))
        result = await action.execute(user_id="P9GBXBY")

        assert result["status"] == "error"
