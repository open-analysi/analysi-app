"""Unit tests for Freshservice ITSM integration actions."""

from unittest.mock import AsyncMock, patch

import pytest

from analysi.integrations.framework.integrations.freshservice.actions import (
    AddNoteAction,
    CreateTicketAction,
    GetTicketAction,
    HealthCheckAction,
    ListTicketsAction,
    UpdateTicketAction,
    _get_base_url,
)

# Default test credentials and settings
TEST_CREDENTIALS = {"api_key": "test-fs-key"}
TEST_SETTINGS = {"domain": "testcompany", "timeout": 30}


# ============================================================================
# Helper function tests
# ============================================================================


class TestGetBaseUrl:
    """Test _get_base_url helper."""

    def test_simple_subdomain(self):
        assert _get_base_url("mycompany") == "https://mycompany.freshservice.com"

    def test_full_domain(self):
        assert (
            _get_base_url("mycompany.freshservice.com")
            == "https://mycompany.freshservice.com"
        )

    def test_with_https_prefix(self):
        assert (
            _get_base_url("https://mycompany.freshservice.com")
            == "https://mycompany.freshservice.com"
        )

    def test_with_http_prefix(self):
        assert (
            _get_base_url("http://mycompany.freshservice.com")
            == "https://mycompany.freshservice.com"
        )

    def test_with_trailing_slash(self):
        assert _get_base_url("mycompany/") == "https://mycompany.freshservice.com"

    def test_strips_whitespace(self):
        assert _get_base_url("  mycompany  ") == "https://mycompany.freshservice.com"


# ============================================================================
# Health Check Action tests
# ============================================================================


class TestHealthCheckAction:
    """Test Freshservice health check action."""

    @pytest.fixture
    def action(self):
        return HealthCheckAction(
            integration_id="freshservice",
            action_id="health_check",
            settings=TEST_SETTINGS,
            credentials=TEST_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_health_check_success(self, action):
        """Test successful health check."""
        mock_response = {"tickets": [{"id": 1, "subject": "Test ticket"}]}

        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await action.execute()

        assert result["status"] == "success"
        assert result["healthy"] is True
        assert result["data"]["healthy"] is True
        assert result["data"]["domain"] == "testcompany"
        assert result["data"]["tickets_accessible"] is True

    @pytest.mark.asyncio
    async def test_health_check_missing_api_key(self):
        """Test health check with missing API key."""
        action = HealthCheckAction(
            integration_id="freshservice",
            action_id="health_check",
            settings=TEST_SETTINGS,
            credentials={},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert "api_key" in result["error"]
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_health_check_missing_domain(self):
        """Test health check with missing domain."""
        action = HealthCheckAction(
            integration_id="freshservice",
            action_id="health_check",
            settings={},
            credentials=TEST_CREDENTIALS,
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert "domain" in result["error"]
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_health_check_api_error(self, action):
        """Test health check with API error."""
        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            side_effect=Exception("Authentication failed - invalid API key"),
        ):
            result = await action.execute()

        assert result["status"] == "error"
        assert "Authentication failed" in result["error"]
        assert result["healthy"] is False


# ============================================================================
# Create Ticket Action tests
# ============================================================================


class TestCreateTicketAction:
    """Test Freshservice create ticket action."""

    @pytest.fixture
    def action(self):
        return CreateTicketAction(
            integration_id="freshservice",
            action_id="create_ticket",
            settings=TEST_SETTINGS,
            credentials=TEST_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_create_ticket_success(self, action):
        """Test successful ticket creation."""
        mock_response = {
            "ticket": {
                "id": 42,
                "subject": "Security Incident",
                "description": "<p>Suspicious activity detected</p>",
                "status": 2,
                "priority": 3,
                "requester_id": 100,
            }
        }

        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            result = await action.execute(
                subject="Security Incident",
                description="Suspicious activity detected",
                priority=3,
                status=2,
                requester_id=100,
            )

        assert result["status"] == "success"
        assert result["ticket_id"] == 42
        assert "42" in result["message"]
        assert result["data"]["subject"] == "Security Incident"

        # Verify the request was made with correct auth
        call_kwargs = mock_req.call_args
        assert call_kwargs.kwargs["method"] == "POST"

    @pytest.mark.asyncio
    async def test_create_ticket_with_email(self, action):
        """Test ticket creation with email instead of requester_id."""
        mock_response = {
            "ticket": {
                "id": 43,
                "subject": "Test",
                "status": 2,
            }
        }

        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            result = await action.execute(
                subject="Test",
                description="Test description",
                email="user@example.com",
            )

        assert result["status"] == "success"
        # Verify email was in the payload
        call_data = mock_req.call_args.kwargs["data"]
        assert call_data["email"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_create_ticket_with_custom_fields(self, action):
        """Test ticket creation with custom fields."""
        mock_response = {"ticket": {"id": 44, "subject": "Custom ticket"}}

        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            result = await action.execute(
                subject="Custom ticket",
                description="With custom fields",
                custom_fields={"cf_severity": "critical"},
            )

        assert result["status"] == "success"
        call_data = mock_req.call_args.kwargs["data"]
        assert call_data["custom_fields"]["cf_severity"] == "critical"

    @pytest.mark.asyncio
    async def test_create_ticket_missing_subject(self, action):
        """Test ticket creation with missing subject."""
        result = await action.execute(description="No subject provided")

        assert result["status"] == "error"
        assert "subject" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_create_ticket_missing_description(self, action):
        """Test ticket creation with missing description."""
        result = await action.execute(subject="No description")

        assert result["status"] == "error"
        assert "description" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_create_ticket_missing_credentials(self):
        """Test ticket creation with missing credentials."""
        action = CreateTicketAction(
            integration_id="freshservice",
            action_id="create_ticket",
            settings=TEST_SETTINGS,
            credentials={},
        )

        result = await action.execute(subject="Test", description="Test")

        assert result["status"] == "error"
        assert "api_key" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_create_ticket_api_error(self, action):
        """Test ticket creation with API error."""
        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            side_effect=Exception("Bad request: description is required"),
        ):
            result = await action.execute(subject="Test", description="Test")

        assert result["status"] == "error"
        assert "Bad request" in result["error"]


# ============================================================================
# Get Ticket Action tests
# ============================================================================


class TestGetTicketAction:
    """Test Freshservice get ticket action."""

    @pytest.fixture
    def action(self):
        return GetTicketAction(
            integration_id="freshservice",
            action_id="get_ticket",
            settings=TEST_SETTINGS,
            credentials=TEST_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_get_ticket_success(self, action):
        """Test successful ticket retrieval."""
        mock_response = {
            "ticket": {
                "id": 42,
                "subject": "Security Incident",
                "description_text": "Suspicious activity detected",
                "status": 2,
                "priority": 3,
                "requester_id": 100,
                "responder_id": 200,
                "group_id": 10,
                "type": "Incident",
                "category": "Security",
                "sub_category": "Malware",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2025-01-02T00:00:00Z",
            }
        }

        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await action.execute(ticket_id="42")

        assert result["status"] == "success"
        assert result["ticket_id"] == 42
        assert result["subject"] == "Security Incident"
        assert result["ticket_status"] == 2
        assert result["priority"] == 3
        assert result["category"] == "Security"

    @pytest.mark.asyncio
    async def test_get_ticket_not_found(self, action):
        """Test ticket retrieval when ticket does not exist (404)."""
        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            side_effect=Exception("Resource not found"),
        ):
            result = await action.execute(ticket_id="99999")

        # 404 should return success with not_found flag (not crash Cy scripts)
        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["ticket_id"] == "99999"

    @pytest.mark.asyncio
    async def test_get_ticket_missing_ticket_id(self, action):
        """Test get ticket with missing ticket_id."""
        result = await action.execute()

        assert result["status"] == "error"
        assert "ticket_id" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_get_ticket_missing_credentials(self):
        """Test get ticket with missing credentials."""
        action = GetTicketAction(
            integration_id="freshservice",
            action_id="get_ticket",
            settings=TEST_SETTINGS,
            credentials={},
        )

        result = await action.execute(ticket_id="42")

        assert result["status"] == "error"
        assert "api_key" in result["error"]

    @pytest.mark.asyncio
    async def test_get_ticket_api_error(self, action):
        """Test get ticket with non-404 API error."""
        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            side_effect=Exception("Authentication failed - invalid API key"),
        ):
            result = await action.execute(ticket_id="42")

        assert result["status"] == "error"
        assert "Authentication failed" in result["error"]


# ============================================================================
# Update Ticket Action tests
# ============================================================================


class TestUpdateTicketAction:
    """Test Freshservice update ticket action."""

    @pytest.fixture
    def action(self):
        return UpdateTicketAction(
            integration_id="freshservice",
            action_id="update_ticket",
            settings=TEST_SETTINGS,
            credentials=TEST_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_update_ticket_status(self, action):
        """Test updating ticket status."""
        mock_response = {
            "ticket": {
                "id": 42,
                "status": 4,
            }
        }

        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            result = await action.execute(ticket_id="42", status=4)

        assert result["status"] == "success"
        assert result["ticket_id"] == "42"
        assert "42" in result["message"]

        call_data = mock_req.call_args.kwargs["data"]
        assert call_data["status"] == 4

    @pytest.mark.asyncio
    async def test_update_ticket_priority(self, action):
        """Test updating ticket priority."""
        mock_response = {"ticket": {"id": 42, "priority": 4}}

        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            result = await action.execute(ticket_id="42", priority=4)

        assert result["status"] == "success"
        call_data = mock_req.call_args.kwargs["data"]
        assert call_data["priority"] == 4

    @pytest.mark.asyncio
    async def test_update_ticket_multiple_fields(self, action):
        """Test updating multiple ticket fields at once."""
        mock_response = {
            "ticket": {
                "id": 42,
                "status": 3,
                "priority": 2,
                "category": "Security",
            }
        }

        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            result = await action.execute(
                ticket_id="42",
                status=3,
                priority=2,
                category="Security",
                responder_id=200,
            )

        assert result["status"] == "success"
        call_data = mock_req.call_args.kwargs["data"]
        assert call_data["status"] == 3
        assert call_data["priority"] == 2
        assert call_data["category"] == "Security"
        assert call_data["responder_id"] == 200

    @pytest.mark.asyncio
    async def test_update_ticket_with_custom_fields(self, action):
        """Test updating ticket with custom fields."""
        mock_response = {"ticket": {"id": 42}}

        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            result = await action.execute(
                ticket_id="42",
                custom_fields={"cf_severity": "high"},
            )

        assert result["status"] == "success"
        call_data = mock_req.call_args.kwargs["data"]
        assert call_data["custom_fields"]["cf_severity"] == "high"

    @pytest.mark.asyncio
    async def test_update_ticket_no_fields(self, action):
        """Test update with no fields provided."""
        result = await action.execute(ticket_id="42")

        assert result["status"] == "error"
        assert "No fields provided" in result["error"]
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_update_ticket_missing_ticket_id(self, action):
        """Test update with missing ticket_id."""
        result = await action.execute(status=3)

        assert result["status"] == "error"
        assert "ticket_id" in result["error"]

    @pytest.mark.asyncio
    async def test_update_ticket_not_found(self, action):
        """Test update when ticket does not exist."""
        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            side_effect=Exception("Resource not found"),
        ):
            result = await action.execute(ticket_id="99999", status=3)

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["ticket_id"] == "99999"

    @pytest.mark.asyncio
    async def test_update_ticket_api_error(self, action):
        """Test update with API error."""
        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            side_effect=Exception("Access forbidden - insufficient permissions"),
        ):
            result = await action.execute(ticket_id="42", status=3)

        assert result["status"] == "error"
        assert "forbidden" in result["error"]


# ============================================================================
# Add Note Action tests
# ============================================================================


class TestAddNoteAction:
    """Test Freshservice add note action."""

    @pytest.fixture
    def action(self):
        return AddNoteAction(
            integration_id="freshservice",
            action_id="add_note",
            settings=TEST_SETTINGS,
            credentials=TEST_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_add_note_success(self, action):
        """Test successful note addition."""
        mock_response = {
            "conversation": {
                "id": 555,
                "body": "<p>Investigation update</p>",
                "private": True,
            }
        }

        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            result = await action.execute(
                ticket_id="42", body="<p>Investigation update</p>"
            )

        assert result["status"] == "success"
        assert result["ticket_id"] == "42"
        assert result["note_id"] == 555
        assert "42" in result["message"]

        # Verify private defaults to True
        call_data = mock_req.call_args.kwargs["data"]
        assert call_data["private"] is True

    @pytest.mark.asyncio
    async def test_add_note_public(self, action):
        """Test adding a public note."""
        mock_response = {
            "conversation": {
                "id": 556,
                "body": "Public update",
                "private": False,
            }
        }

        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            result = await action.execute(
                ticket_id="42", body="Public update", private=False
            )

        assert result["status"] == "success"
        call_data = mock_req.call_args.kwargs["data"]
        assert call_data["private"] is False

    @pytest.mark.asyncio
    async def test_add_note_missing_ticket_id(self, action):
        """Test add note with missing ticket_id."""
        result = await action.execute(body="Some note")

        assert result["status"] == "error"
        assert "ticket_id" in result["error"]

    @pytest.mark.asyncio
    async def test_add_note_missing_body(self, action):
        """Test add note with missing body."""
        result = await action.execute(ticket_id="42")

        assert result["status"] == "error"
        assert "body" in result["error"]

    @pytest.mark.asyncio
    async def test_add_note_ticket_not_found(self, action):
        """Test add note when ticket does not exist."""
        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            side_effect=Exception("Resource not found"),
        ):
            result = await action.execute(ticket_id="99999", body="Note")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["ticket_id"] == "99999"

    @pytest.mark.asyncio
    async def test_add_note_missing_credentials(self):
        """Test add note with missing credentials."""
        action = AddNoteAction(
            integration_id="freshservice",
            action_id="add_note",
            settings=TEST_SETTINGS,
            credentials={},
        )

        result = await action.execute(ticket_id="42", body="Note")

        assert result["status"] == "error"
        assert "api_key" in result["error"]

    @pytest.mark.asyncio
    async def test_add_note_api_error(self, action):
        """Test add note with API error."""
        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            side_effect=Exception("HTTP 500: Internal Server Error"),
        ):
            result = await action.execute(ticket_id="42", body="Note")

        assert result["status"] == "error"
        assert "500" in result["error"]


# ============================================================================
# List Tickets Action tests
# ============================================================================


class TestListTicketsAction:
    """Test Freshservice list tickets action."""

    @pytest.fixture
    def action(self):
        return ListTicketsAction(
            integration_id="freshservice",
            action_id="list_tickets",
            settings=TEST_SETTINGS,
            credentials=TEST_CREDENTIALS,
        )

    @pytest.mark.asyncio
    async def test_list_tickets_success(self, action):
        """Test successful ticket listing."""
        mock_response = {
            "tickets": [
                {
                    "id": 1,
                    "subject": "First ticket",
                    "status": 2,
                    "priority": 1,
                    "requester_id": 100,
                    "responder_id": None,
                    "group_id": 10,
                    "type": "Incident",
                    "created_at": "2025-01-01T00:00:00Z",
                    "updated_at": "2025-01-01T12:00:00Z",
                },
                {
                    "id": 2,
                    "subject": "Second ticket",
                    "status": 3,
                    "priority": 2,
                    "requester_id": 101,
                    "responder_id": 200,
                    "group_id": 10,
                    "type": "Service Request",
                    "created_at": "2025-01-02T00:00:00Z",
                    "updated_at": "2025-01-02T06:00:00Z",
                },
            ]
        }

        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await action.execute()

        assert result["status"] == "success"
        assert result["total_tickets"] == 2
        assert len(result["tickets"]) == 2
        assert result["tickets"][0]["id"] == 1
        assert result["tickets"][0]["subject"] == "First ticket"
        assert result["tickets"][1]["id"] == 2

    @pytest.mark.asyncio
    async def test_list_tickets_with_filters(self, action):
        """Test listing tickets with filter parameters."""
        mock_response = {"tickets": []}

        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            result = await action.execute(
                filter="new_and_my_open",
                per_page=10,
                page=2,
                order_by="created_at",
                order_type="desc",
            )

        assert result["status"] == "success"
        assert result["total_tickets"] == 0

        call_params = mock_req.call_args.kwargs["params"]
        assert call_params["filter"] == "new_and_my_open"
        assert call_params["per_page"] == 10
        assert call_params["page"] == 2
        assert call_params["order_by"] == "created_at"
        assert call_params["order_type"] == "desc"

    @pytest.mark.asyncio
    async def test_list_tickets_empty_result(self, action):
        """Test listing tickets when no tickets found."""
        mock_response = {"tickets": []}

        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await action.execute()

        assert result["status"] == "success"
        assert result["total_tickets"] == 0
        assert result["tickets"] == []

    @pytest.mark.asyncio
    async def test_list_tickets_missing_credentials(self):
        """Test listing tickets with missing credentials."""
        action = ListTicketsAction(
            integration_id="freshservice",
            action_id="list_tickets",
            settings=TEST_SETTINGS,
            credentials={},
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert "api_key" in result["error"]

    @pytest.mark.asyncio
    async def test_list_tickets_api_error(self, action):
        """Test listing tickets with API error."""
        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            side_effect=Exception("Authentication failed - invalid API key"),
        ):
            result = await action.execute()

        assert result["status"] == "error"
        assert "Authentication failed" in result["error"]

    @pytest.mark.asyncio
    async def test_list_tickets_default_pagination(self, action):
        """Test that default pagination parameters are applied."""
        mock_response = {"tickets": []}

        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            await action.execute()

        call_params = mock_req.call_args.kwargs["params"]
        assert call_params["per_page"] == 30
        assert call_params["page"] == 1


# ============================================================================
# Cross-cutting credential and configuration tests
# ============================================================================


class TestCredentialValidation:
    """Test credential validation across all actions."""

    @pytest.mark.asyncio
    async def test_missing_domain_in_settings(self):
        """Test that missing domain returns configuration error."""
        action = CreateTicketAction(
            integration_id="freshservice",
            action_id="create_ticket",
            settings={},  # No domain
            credentials=TEST_CREDENTIALS,
        )

        result = await action.execute(subject="Test", description="Test")

        assert result["status"] == "error"
        assert "domain" in result["error"]
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_custom_timeout_from_settings(self):
        """Test that custom timeout from settings is used."""
        action = HealthCheckAction(
            integration_id="freshservice",
            action_id="health_check",
            settings={"domain": "testcompany", "timeout": 60},
            credentials=TEST_CREDENTIALS,
        )

        mock_response = {"tickets": []}

        with patch(
            "analysi.integrations.framework.integrations.freshservice.actions._make_freshservice_request",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_req:
            await action.execute()

        assert mock_req.call_args.kwargs["timeout"] == 60
