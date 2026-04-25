"""Unit tests for BMC Remedy ITSM integration actions."""

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.bmcremedy.actions import (
    AddCommentAction,
    CreateTicketAction,
    GetTicketAction,
    HealthCheckAction,
    ListTicketsAction,
    SetStatusAction,
    UpdateTicketAction,
    _obtain_jwt_token,
)

# ---------------------------------------------------------------------------
# Common fixtures
# ---------------------------------------------------------------------------

VALID_CREDENTIALS = {
    "username": "remedy_user",
    "password": "remedy_pass",
}

VALID_SETTINGS = {
    "base_url": "https://remedy.example.com",
    "timeout": 30,
    "verify_ssl": False,
}


def _make_mock_response(
    status_code: int = 200,
    json_data: dict | None = None,
    text: str = "",
    headers: dict | None = None,
) -> MagicMock:
    """Build a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text or json.dumps(json_data or {})
    resp.json.return_value = json_data or {}
    resp.content = (text or json.dumps(json_data or {})).encode()
    resp.headers = httpx.Headers(headers or {})
    return resp


def _token_response(token: str = "test-jwt-token") -> MagicMock:
    """Mock response for /api/jwt/login."""
    return _make_mock_response(status_code=200, text=token)


def _logout_response() -> MagicMock:
    """Mock response for /api/jwt/logout."""
    return _make_mock_response(status_code=204)


# ============================================================================
# HealthCheckAction
# ============================================================================


class TestHealthCheckAction:
    """Test BMC Remedy health check action."""

    @pytest.fixture
    def action(self):
        return HealthCheckAction(
            integration_id="bmcremedy",
            action_id="health_check",
            settings=VALID_SETTINGS,
            credentials=VALID_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Successful health check obtains JWT token and logs out."""
        action.http_request = AsyncMock(
            side_effect=[_token_response(), _logout_response()]
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert "integration_id" in result
        assert action.http_request.call_count == 2  # login + logout

    @pytest.mark.asyncio
    async def test_missing_base_url(self):
        """Missing base_url returns configuration error."""
        action = HealthCheckAction(
            integration_id="bmcremedy",
            action_id="health_check",
            settings={"timeout": 30},
            credentials=VALID_CREDENTIALS,
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert "base_url" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Missing username/password returns configuration error."""
        action = HealthCheckAction(
            integration_id="bmcremedy",
            action_id="health_check",
            settings=VALID_SETTINGS,
            credentials={},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert "credentials" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_auth_failure_401(self, action):
        """401 during token acquisition returns auth error."""
        mock_response = _make_mock_response(status_code=401)
        mock_request = MagicMock(spec=httpx.Request)
        mock_request.url = "https://remedy.example.com/api/jwt/login"
        exc = httpx.HTTPStatusError(
            "401 Unauthorized",
            request=mock_request,
            response=mock_response,
        )
        action.http_request = AsyncMock(side_effect=exc)

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "AuthenticationError"

    @pytest.mark.asyncio
    async def test_connection_error(self, action):
        """Connection error returns error result."""
        action.http_request = AsyncMock(
            side_effect=Exception("Connection refused"),
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]

    @pytest.mark.asyncio
    async def test_logout_failure_does_not_crash(self, action):
        """Failed logout is silently logged, does not affect result."""
        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                Exception("logout failed"),
            ]
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True


# ============================================================================
# CreateTicketAction
# ============================================================================


class TestCreateTicketAction:
    """Test BMC Remedy create ticket action."""

    @pytest.fixture
    def action(self):
        return CreateTicketAction(
            integration_id="bmcremedy",
            action_id="create_ticket",
            settings=VALID_SETTINGS,
            credentials=VALID_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success_with_individual_params(self, action):
        """Create ticket with individual parameters."""
        create_response = _make_mock_response(
            status_code=201,
            headers={
                "Location": "https://remedy.example.com/api/arsys/v1/entry/HPD:IncidentInterface_Create/000000000000001"
            },
        )
        detail_response = _make_mock_response(
            json_data={
                "values": {"Incident Number": "INC000000000001", "Status": "New"}
            },
        )

        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),  # login
                create_response,  # POST create
                detail_response,  # GET details
                _logout_response(),  # logout
            ]
        )

        result = await action.execute(
            first_name="John",
            last_name="Doe",
            description="Test incident",
            service_type="User Service Restoration",
            reported_source="Direct Input",
        )

        assert result["status"] == "success"
        assert result["data"]["incident_number"] == "INC000000000001"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_success_with_fields_dict(self, action):
        """Create ticket using the 'fields' parameter."""
        create_response = _make_mock_response(
            status_code=201,
            headers={
                "Location": "https://remedy.example.com/api/arsys/v1/entry/HPD:IncidentInterface_Create/000000000000002"
            },
        )
        detail_response = _make_mock_response(
            json_data={"values": {"Incident Number": "INC000000000002"}},
        )

        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                create_response,
                detail_response,
                _logout_response(),
            ]
        )

        result = await action.execute(
            fields={"First_Name": "Jane", "Last_Name": "Smith", "Description": "Test"},
        )

        assert result["status"] == "success"
        assert result["data"]["incident_number"] == "INC000000000002"

    @pytest.mark.asyncio
    async def test_invalid_fields_json_string(self, action):
        """Invalid JSON in fields parameter returns validation error."""
        result = await action.execute(fields="{invalid json")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "Invalid JSON" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_location_header(self, action):
        """Missing location header after creation returns error."""
        create_response = _make_mock_response(status_code=201, headers={})

        action.http_request = AsyncMock(
            side_effect=[_token_response(), create_response, _logout_response()]
        )

        result = await action.execute(fields={"First_Name": "Test"})

        assert result["status"] == "error"
        assert "location" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Missing credentials returns configuration error."""
        action = CreateTicketAction(
            integration_id="bmcremedy",
            action_id="create_ticket",
            settings=VALID_SETTINGS,
            credentials={},
        )

        result = await action.execute(first_name="Test")

        assert result["status"] == "error"
        assert "credentials" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        """API error during creation returns error result."""
        mock_response = _make_mock_response(status_code=400)
        mock_request = MagicMock(spec=httpx.Request)
        mock_request.url = (
            "https://remedy.example.com/api/arsys/v1/entry/HPD:IncidentInterface_Create"
        )
        exc = httpx.HTTPStatusError(
            "400 Bad Request",
            request=mock_request,
            response=mock_response,
        )
        action.http_request = AsyncMock(
            side_effect=[_token_response(), exc, _logout_response()]
        )

        result = await action.execute(fields={"First_Name": "Test"})

        assert result["status"] == "error"


# ============================================================================
# GetTicketAction
# ============================================================================


class TestGetTicketAction:
    """Test BMC Remedy get ticket action."""

    @pytest.fixture
    def action(self):
        return GetTicketAction(
            integration_id="bmcremedy",
            action_id="get_ticket",
            settings=VALID_SETTINGS,
            credentials=VALID_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Successful get ticket returns incident data."""
        ticket_data = {
            "entries": [
                {"values": {"Incident Number": "INC000000000001", "Status": "Assigned"}}
            ],
        }
        work_log_data = {
            "entries": [{"values": {"Work Log Type": "General Information"}}],
        }

        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                _make_mock_response(json_data=ticket_data),
                _make_mock_response(json_data=work_log_data),
                _logout_response(),
            ]
        )

        result = await action.execute(id="INC000000000001")

        assert result["status"] == "success"
        assert result["data"]["ticket_availability"] is True
        assert result["data"]["id"] == "INC000000000001"
        assert "work_details" in result["data"]["ticket_data"]
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_not_found(self, action):
        """Incident not found returns success with not_found flag."""
        empty_response = {"entries": []}

        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                _make_mock_response(json_data=empty_response),
                _make_mock_response(json_data=empty_response),
                _logout_response(),
            ]
        )

        result = await action.execute(id="INC999999999999")

        assert result["status"] == "success"
        assert result["data"]["ticket_availability"] is False

    @pytest.mark.asyncio
    async def test_missing_id(self, action):
        """Missing id parameter returns validation error."""
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_http_404(self, action):
        """HTTP 404 returns success with not_found."""
        mock_response = _make_mock_response(status_code=404)
        mock_request = MagicMock(spec=httpx.Request)
        mock_request.url = (
            "https://remedy.example.com/api/arsys/v1/entry/HPD:IncidentInterface"
        )
        exc = httpx.HTTPStatusError(
            "404 Not Found",
            request=mock_request,
            response=mock_response,
        )
        action.http_request = AsyncMock(
            side_effect=[_token_response(), exc, _logout_response()]
        )

        result = await action.execute(id="INC000000000001")

        assert result["status"] == "success"
        assert result["data"]["ticket_availability"] is False

    @pytest.mark.asyncio
    async def test_work_log_failure_does_not_crash(self, action):
        """Failed work log fetch is handled gracefully."""
        ticket_data = {
            "entries": [{"values": {"Incident Number": "INC000000000001"}}],
        }

        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                _make_mock_response(json_data=ticket_data),
                Exception("work log endpoint error"),
                _logout_response(),
            ]
        )

        result = await action.execute(id="INC000000000001")

        assert result["status"] == "success"
        assert result["data"]["ticket_availability"] is True


# ============================================================================
# UpdateTicketAction
# ============================================================================


class TestUpdateTicketAction:
    """Test BMC Remedy update ticket action."""

    @pytest.fixture
    def action(self):
        return UpdateTicketAction(
            integration_id="bmcremedy",
            action_id="update_ticket",
            settings=VALID_SETTINGS,
            credentials=VALID_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Successful ticket update."""
        resolve_data = {
            "entries": [
                {
                    "_links": {
                        "self": [
                            {
                                "href": "https://remedy.example.com/api/arsys/v1/entry/HPD:IncidentInterface/000000000000001"
                            }
                        ]
                    },
                }
            ],
        }

        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                _make_mock_response(json_data=resolve_data),  # resolve URL
                _make_mock_response(status_code=204),  # PUT update
                _logout_response(),
            ]
        )

        result = await action.execute(
            id="INC000000000001",
            fields={"Status": "In Progress"},
        )

        assert result["status"] == "success"
        assert result["data"]["id"] == "INC000000000001"
        assert "updated" in result["data"]["message"].lower()
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_id(self, action):
        """Missing id parameter returns validation error."""
        result = await action.execute(fields={"Status": "Assigned"})

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_no_fields(self, action):
        """Empty fields dict returns validation error."""
        result = await action.execute(id="INC000000000001", fields={})

        assert result["status"] == "error"
        assert "No fields" in result["error"]

    @pytest.mark.asyncio
    async def test_incident_not_found(self, action):
        """Non-existent incident returns error."""
        resolve_data = {"entries": []}

        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                _make_mock_response(json_data=resolve_data),
                _logout_response(),
            ]
        )

        result = await action.execute(
            id="INC999999999999",
            fields={"Status": "Assigned"},
        )

        assert result["status"] == "error"
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_invalid_fields_json(self, action):
        """Invalid JSON in fields returns validation error."""
        result = await action.execute(id="INC000000000001", fields="{bad json}")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_http_404(self, action):
        """HTTP 404 returns success with not_found."""
        resolve_data = {
            "entries": [
                {
                    "_links": {
                        "self": [
                            {
                                "href": "https://remedy.example.com/api/arsys/v1/entry/HPD:IncidentInterface/000000000000001"
                            }
                        ]
                    },
                }
            ],
        }
        mock_response = _make_mock_response(status_code=404)
        mock_request = MagicMock(spec=httpx.Request)
        mock_request.url = "https://remedy.example.com/api/arsys/v1/entry/HPD:IncidentInterface/000000000000001"
        exc = httpx.HTTPStatusError(
            "404 Not Found",
            request=mock_request,
            response=mock_response,
        )
        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                _make_mock_response(json_data=resolve_data),
                exc,
                _logout_response(),
            ]
        )

        result = await action.execute(
            id="INC000000000001",
            fields={"Status": "Assigned"},
        )

        assert result["status"] == "success"
        assert result["data"]["id"] == "INC000000000001"


# ============================================================================
# ListTicketsAction
# ============================================================================


class TestListTicketsAction:
    """Test BMC Remedy list tickets action."""

    @pytest.fixture
    def action(self):
        return ListTicketsAction(
            integration_id="bmcremedy",
            action_id="list_tickets",
            settings=VALID_SETTINGS,
            credentials=VALID_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Successful list with results."""
        list_data = {
            "entries": [
                {
                    "values": {
                        "Incident Number": "INC000000000001",
                        "Status": "Assigned",
                    }
                },
                {"values": {"Incident Number": "INC000000000002", "Status": "New"}},
            ],
        }

        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                _make_mock_response(json_data=list_data),
                _logout_response(),
            ]
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_tickets"] == 2
        assert len(result["data"]["tickets"]) == 2
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_with_query(self, action):
        """List with query parameter."""
        list_data = {
            "entries": [
                {
                    "values": {
                        "Incident Number": "INC000000000001",
                        "Status": "Assigned",
                    }
                },
            ],
        }

        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                _make_mock_response(json_data=list_data),
                _logout_response(),
            ]
        )

        result = await action.execute(query="'Status'=\"Assigned\"")

        assert result["status"] == "success"
        assert result["data"]["total_tickets"] == 1

    @pytest.mark.asyncio
    async def test_with_limit(self, action):
        """List with limit parameter truncates results."""
        list_data = {
            "entries": [
                {"values": {"Incident Number": f"INC{i:015d}"}} for i in range(5)
            ],
        }

        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                _make_mock_response(json_data=list_data),
                _logout_response(),
            ]
        )

        result = await action.execute(limit=3)

        assert result["status"] == "success"
        assert result["data"]["total_tickets"] == 3

    @pytest.mark.asyncio
    async def test_invalid_limit(self, action):
        """Non-integer limit returns validation error."""
        result = await action.execute(limit="abc")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_negative_limit(self, action):
        """Negative limit returns validation error."""
        result = await action.execute(limit=-5)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_empty_results(self, action):
        """Empty results return success with zero count."""
        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                _make_mock_response(json_data={"entries": []}),
                _logout_response(),
            ]
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_tickets"] == 0
        assert result["data"]["tickets"] == []

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Missing credentials returns configuration error."""
        action = ListTicketsAction(
            integration_id="bmcremedy",
            action_id="list_tickets",
            settings=VALID_SETTINGS,
            credentials={},
        )

        result = await action.execute()

        assert result["status"] == "error"


# ============================================================================
# SetStatusAction
# ============================================================================


class TestSetStatusAction:
    """Test BMC Remedy set status action."""

    @pytest.fixture
    def action(self):
        return SetStatusAction(
            integration_id="bmcremedy",
            action_id="set_status",
            settings=VALID_SETTINGS,
            credentials=VALID_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Successful status change."""
        resolve_data = {
            "entries": [
                {
                    "_links": {
                        "self": [
                            {
                                "href": "https://remedy.example.com/api/arsys/v1/entry/HPD:IncidentInterface/000000000000001"
                            }
                        ]
                    },
                }
            ],
        }

        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                _make_mock_response(json_data=resolve_data),
                _make_mock_response(status_code=204),
                _logout_response(),
            ]
        )

        result = await action.execute(id="INC000000000001", status="Resolved")

        assert result["status"] == "success"
        assert result["data"]["new_status"] == "Resolved"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_with_optional_params(self, action):
        """Status change with assignee and resolution."""
        resolve_data = {
            "entries": [
                {
                    "_links": {
                        "self": [
                            {
                                "href": "https://remedy.example.com/api/arsys/v1/entry/HPD:IncidentInterface/000000000000001"
                            }
                        ]
                    },
                }
            ],
        }

        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                _make_mock_response(json_data=resolve_data),
                _make_mock_response(status_code=204),
                _logout_response(),
            ]
        )

        result = await action.execute(
            id="INC000000000001",
            status="Resolved",
            status_reason="No Further Action Required",
            assignee="John Doe",
            resolution="Issue was resolved by rebooting.",
        )

        assert result["status"] == "success"

        # Verify the PUT body included optional fields
        put_call = action.http_request.call_args_list[2]
        body = put_call.kwargs.get("json_data", {})
        assert body["values"]["Status"] == "Resolved"
        assert body["values"]["Status_Reason"] == "No Further Action Required"
        assert body["values"]["Assignee"] == "John Doe"
        assert body["values"]["Resolution"] == "Issue was resolved by rebooting."

    @pytest.mark.asyncio
    async def test_missing_id(self, action):
        """Missing id returns validation error."""
        result = await action.execute(status="Resolved")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_status(self, action):
        """Missing status returns validation error."""
        result = await action.execute(id="INC000000000001")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_incident_not_found(self, action):
        """Non-existent incident returns error."""
        resolve_data = {"entries": []}

        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                _make_mock_response(json_data=resolve_data),
                _logout_response(),
            ]
        )

        result = await action.execute(id="INC999999999999", status="Resolved")

        assert result["status"] == "error"
        assert "not found" in result["error"].lower()


# ============================================================================
# AddCommentAction
# ============================================================================


class TestAddCommentAction:
    """Test BMC Remedy add comment action."""

    @pytest.fixture
    def action(self):
        return AddCommentAction(
            integration_id="bmcremedy",
            action_id="add_comment",
            settings=VALID_SETTINGS,
            credentials=VALID_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_success(self, action):
        """Successful comment addition."""
        resolve_data = {
            "entries": [
                {
                    "_links": {
                        "self": [
                            {
                                "href": "https://remedy.example.com/api/arsys/v1/entry/HPD:IncidentInterface/000000000000001"
                            }
                        ]
                    },
                }
            ],
        }

        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                _make_mock_response(json_data=resolve_data),  # resolve
                _make_mock_response(status_code=201),  # POST comment
                _logout_response(),
            ]
        )

        result = await action.execute(
            id="INC000000000001",
            work_info_type="General Information",
            comment="This is a test comment.",
        )

        assert result["status"] == "success"
        assert result["data"]["id"] == "INC000000000001"
        assert "comment added" in result["data"]["message"].lower()
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_with_description(self, action):
        """Comment with short description."""
        resolve_data = {
            "entries": [
                {
                    "_links": {
                        "self": [
                            {
                                "href": "https://remedy.example.com/api/arsys/v1/entry/HPD:IncidentInterface/000000000000001"
                            }
                        ]
                    },
                }
            ],
        }

        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                _make_mock_response(json_data=resolve_data),
                _make_mock_response(status_code=201),
                _logout_response(),
            ]
        )

        result = await action.execute(
            id="INC000000000001",
            work_info_type="Customer Communication",
            comment="Detailed notes here",
            description="Short summary",
        )

        assert result["status"] == "success"

        # Verify the POST body includes both fields
        post_call = action.http_request.call_args_list[2]
        body = post_call.kwargs.get("json_data", {})
        assert body["values"]["Detailed Description"] == "Detailed notes here"
        assert body["values"]["Description"] == "Short summary"

    @pytest.mark.asyncio
    async def test_missing_id(self, action):
        """Missing id returns validation error."""
        result = await action.execute(work_info_type="General Information")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_work_info_type(self, action):
        """Missing work_info_type returns validation error."""
        result = await action.execute(id="INC000000000001")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_incident_not_found(self, action):
        """Non-existent incident returns error."""
        resolve_data = {"entries": []}

        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                _make_mock_response(json_data=resolve_data),
                _logout_response(),
            ]
        )

        result = await action.execute(
            id="INC999999999999",
            work_info_type="General Information",
            comment="Test comment",
        )

        assert result["status"] == "error"
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_http_404(self, action):
        """HTTP 404 on comment endpoint returns success with not_found."""
        resolve_data = {
            "entries": [
                {
                    "_links": {
                        "self": [
                            {
                                "href": "https://remedy.example.com/api/arsys/v1/entry/HPD:IncidentInterface/000000000000001"
                            }
                        ]
                    },
                }
            ],
        }
        mock_response = _make_mock_response(status_code=404)
        mock_request = MagicMock(spec=httpx.Request)
        mock_request.url = "https://remedy.example.com/api/arsys/v1/entry/HPD:WorkLog"
        exc = httpx.HTTPStatusError(
            "404 Not Found",
            request=mock_request,
            response=mock_response,
        )
        action.http_request = AsyncMock(
            side_effect=[
                _token_response(),
                _make_mock_response(json_data=resolve_data),
                exc,
                _logout_response(),
            ]
        )

        result = await action.execute(
            id="INC000000000001",
            work_info_type="General Information",
        )

        assert result["status"] == "success"
        assert result["data"]["id"] == "INC000000000001"


# ============================================================================
# Token helper
# ============================================================================


class TestObtainJwtToken:
    """Test the JWT token acquisition helper."""

    @pytest.mark.asyncio
    async def test_login_failed_message_in_header(self):
        """x-ar-messages with login failed raises exception."""
        action = HealthCheckAction(
            integration_id="bmcremedy",
            action_id="health_check",
            settings=VALID_SETTINGS,
            credentials=VALID_CREDENTIALS,
        )
        resp = _make_mock_response(
            status_code=200,
            text="some-token",
            headers={
                "x-ar-messages": json.dumps([{"messageText": "Login failed for user"}])
            },
        )
        action.http_request = AsyncMock(return_value=resp)

        with pytest.raises(Exception, match="Login failed"):
            await _obtain_jwt_token(
                action,
                "https://remedy.example.com",
                "user",
                "pass",
            )

    @pytest.mark.asyncio
    async def test_empty_token_raises(self):
        """Empty token response raises exception."""
        action = HealthCheckAction(
            integration_id="bmcremedy",
            action_id="health_check",
            settings=VALID_SETTINGS,
            credentials=VALID_CREDENTIALS,
        )
        resp = _make_mock_response(status_code=200, text="   ")
        action.http_request = AsyncMock(return_value=resp)

        with pytest.raises(Exception, match="Failed to generate JWT token"):
            await _obtain_jwt_token(
                action,
                "https://remedy.example.com",
                "user",
                "pass",
            )
