"""Unit tests for Cisco Webex integration actions.

All actions use the base-class ``http_request()`` helper which applies
``integration_retry_policy`` automatically. Tests mock at the
``IntegrationAction.http_request`` level so retry behaviour is transparent.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.ciscowebex.actions import (
    CreateRoomAction,
    GetUserAction,
    HealthCheckAction,
    ListRoomsAction,
    ListUsersAction,
    SendMessageAction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_CREDENTIALS = {"bot_token": "test-webex-bot-token"}
_DEFAULT_SETTINGS = {"timeout": 30}


def _make_action(cls, credentials=None, settings=None):
    """Create an action instance with sensible defaults."""
    return cls(
        integration_id="ciscowebex",
        action_id=cls.__name__,
        credentials=credentials
        if credentials is not None
        else dict(_DEFAULT_CREDENTIALS),
        settings=settings if settings is not None else dict(_DEFAULT_SETTINGS),
    )


def _json_response(data, status_code: int = 200) -> MagicMock:
    """Build a fake httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    return resp


def _http_status_error(status_code: int = 404) -> httpx.HTTPStatusError:
    """Create an httpx.HTTPStatusError with the given status code."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    request = MagicMock(spec=httpx.Request)
    return httpx.HTTPStatusError(
        f"HTTP {status_code}",
        request=request,
        response=response,
    )


# ===========================================================================
# HealthCheckAction
# ===========================================================================


class TestHealthCheckAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(HealthCheckAction)
        action.http_request = AsyncMock(
            return_value=_json_response(
                {
                    "id": "bot-123",
                    "displayName": "Security Bot",
                    "emails": ["bot@example.com"],
                    "orgId": "org-456",
                }
            )
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["healthy"] is True
        assert result["integration_id"] == "ciscowebex"
        assert result["data"]["bot_id"] == "bot-123"
        assert result["data"]["display_name"] == "Security Bot"
        assert result["data"]["emails"] == ["bot@example.com"]
        assert result["data"]["org_id"] == "org-456"
        action.http_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_bot_token(self):
        action = _make_action(HealthCheckAction, credentials={})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_api_error(self):
        action = _make_action(HealthCheckAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(401))

        result = await action.execute()

        assert result["status"] == "error"
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_server_error(self):
        action = _make_action(HealthCheckAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        result = await action.execute()

        assert result["status"] == "error"
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_connection_error(self):
        action = _make_action(HealthCheckAction)
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["healthy"] is False


# ===========================================================================
# SendMessageAction
# ===========================================================================


class TestSendMessageAction:
    @pytest.mark.asyncio
    async def test_success_to_room(self):
        action = _make_action(SendMessageAction)
        action.http_request = AsyncMock(
            return_value=_json_response(
                {
                    "id": "msg-123",
                    "roomId": "room-456",
                    "personEmail": "bot@example.com",
                    "created": "2026-04-26T00:00:00Z",
                }
            )
        )

        result = await action.execute(room_id="room-456", text="Hello, world!")

        assert result["status"] == "success"
        assert result["data"]["message_id"] == "msg-123"
        assert result["data"]["room_id"] == "room-456"
        # Verify POST method and payload
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["method"] == "POST"
        assert call_kwargs["json_data"]["roomId"] == "room-456"
        assert call_kwargs["json_data"]["text"] == "Hello, world!"

    @pytest.mark.asyncio
    async def test_success_to_person_email(self):
        action = _make_action(SendMessageAction)
        action.http_request = AsyncMock(
            return_value=_json_response(
                {
                    "id": "msg-789",
                    "personEmail": "user@example.com",
                    "created": "2026-04-26T00:00:00Z",
                }
            )
        )

        result = await action.execute(
            to_person_email="user@example.com", text="Direct message"
        )

        assert result["status"] == "success"
        assert result["data"]["message_id"] == "msg-789"
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["json_data"]["toPersonEmail"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_success_with_markdown(self):
        action = _make_action(SendMessageAction)
        action.http_request = AsyncMock(
            return_value=_json_response({"id": "msg-md", "roomId": "room-1"})
        )

        result = await action.execute(room_id="room-1", markdown="**bold text**")

        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["json_data"]["markdown"] == "**bold text**"

    @pytest.mark.asyncio
    async def test_missing_bot_token(self):
        action = _make_action(SendMessageAction, credentials={})

        result = await action.execute(room_id="room-1", text="Hello")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_missing_destination(self):
        """Neither room_id nor to_person_email provided."""
        action = _make_action(SendMessageAction)

        result = await action.execute(text="Hello")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "room_id" in result["error"] or "to_person_email" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_message_body(self):
        """Neither text nor markdown provided."""
        action = _make_action(SendMessageAction)

        result = await action.execute(room_id="room-1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "text" in result["error"] or "markdown" in result["error"]

    @pytest.mark.asyncio
    async def test_server_error(self):
        action = _make_action(SendMessageAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        result = await action.execute(room_id="room-1", text="Hello")

        assert result["status"] == "error"


# ===========================================================================
# ListRoomsAction
# ===========================================================================


class TestListRoomsAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(ListRoomsAction)
        rooms = [
            {"id": "room-1", "title": "General", "type": "group"},
            {"id": "room-2", "title": "Alerts", "type": "group"},
        ]
        action.http_request = AsyncMock(return_value=_json_response({"items": rooms}))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_rooms"] == 2
        assert len(result["data"]["rooms"]) == 2
        assert result["integration_id"] == "ciscowebex"

    @pytest.mark.asyncio
    async def test_success_with_room_type_filter(self):
        action = _make_action(ListRoomsAction)
        action.http_request = AsyncMock(
            return_value=_json_response({"items": [{"id": "r-1", "type": "direct"}]})
        )

        result = await action.execute(room_type="direct")

        assert result["status"] == "success"
        assert result["data"]["total_rooms"] == 1
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["params"]["type"] == "direct"

    @pytest.mark.asyncio
    async def test_success_empty_list(self):
        action = _make_action(ListRoomsAction)
        action.http_request = AsyncMock(return_value=_json_response({"items": []}))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_rooms"] == 0
        assert result["data"]["rooms"] == []

    @pytest.mark.asyncio
    async def test_missing_bot_token(self):
        action = _make_action(ListRoomsAction, credentials={})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_server_error(self):
        action = _make_action(ListRoomsAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        result = await action.execute()

        assert result["status"] == "error"


# ===========================================================================
# CreateRoomAction
# ===========================================================================


class TestCreateRoomAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(CreateRoomAction)
        action.http_request = AsyncMock(
            return_value=_json_response(
                {
                    "id": "room-new",
                    "title": "Incident Response",
                    "type": "group",
                    "created": "2026-04-26T00:00:00Z",
                }
            )
        )

        result = await action.execute(title="Incident Response")

        assert result["status"] == "success"
        assert result["data"]["room_id"] == "room-new"
        assert result["data"]["title"] == "Incident Response"
        assert result["data"]["room_type"] == "group"
        # Verify POST method and payload
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["method"] == "POST"
        assert call_kwargs["json_data"]["title"] == "Incident Response"

    @pytest.mark.asyncio
    async def test_missing_bot_token(self):
        action = _make_action(CreateRoomAction, credentials={})

        result = await action.execute(title="Test Room")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_missing_title(self):
        action = _make_action(CreateRoomAction)

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "title" in result["error"]

    @pytest.mark.asyncio
    async def test_server_error(self):
        action = _make_action(CreateRoomAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        result = await action.execute(title="Test Room")

        assert result["status"] == "error"


# ===========================================================================
# GetUserAction
# ===========================================================================


class TestGetUserAction:
    @pytest.mark.asyncio
    async def test_success_by_person_id(self):
        action = _make_action(GetUserAction)
        user_data = {
            "id": "person-123",
            "displayName": "Alice Smith",
            "emails": ["alice@example.com"],
            "orgId": "org-789",
            "created": "2024-06-15T10:00:00Z",
            "lastActivity": "2025-01-01T12:00:00Z",
            "status": "active",
        }
        action.http_request = AsyncMock(return_value=_json_response(user_data))

        result = await action.execute(person_id="person-123")

        assert result["status"] == "success"
        assert result["data"]["person_id"] == "person-123"
        assert result["data"]["display_name"] == "Alice Smith"
        assert result["data"]["emails"] == ["alice@example.com"]
        assert result["data"]["org_id"] == "org-789"
        assert result["data"]["status"] == "active"

    @pytest.mark.asyncio
    async def test_success_by_email(self):
        action = _make_action(GetUserAction)
        user_data = {
            "id": "person-456",
            "displayName": "Bob Jones",
            "emails": ["bob@example.com"],
            "orgId": "org-789",
        }
        action.http_request = AsyncMock(
            return_value=_json_response({"items": [user_data]})
        )

        result = await action.execute(email="bob@example.com")

        assert result["status"] == "success"
        assert result["data"]["person_id"] == "person-456"
        assert result["data"]["display_name"] == "Bob Jones"
        # Verify email search params
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["params"]["email"] == "bob@example.com"

    @pytest.mark.asyncio
    async def test_email_search_no_results(self):
        """Email search returns empty items list."""
        action = _make_action(GetUserAction)
        action.http_request = AsyncMock(return_value=_json_response({"items": []}))

        result = await action.execute(email="unknown@example.com")

        assert result["status"] == "success"
        assert result["data"]["not_found"] is True

    @pytest.mark.asyncio
    async def test_missing_bot_token(self):
        action = _make_action(GetUserAction, credentials={})

        result = await action.execute(person_id="person-123")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_missing_person_id_and_email(self):
        """Neither person_id nor email provided."""
        action = _make_action(GetUserAction)

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "person_id" in result["error"] or "email" in result["error"]

    @pytest.mark.asyncio
    async def test_not_found_returns_success(self):
        """HTTP 404 for person_id lookup returns success with not_found."""
        action = _make_action(GetUserAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(person_id="nonexistent")

        assert result["status"] == "success"
        assert result["data"]["not_found"] is True

    @pytest.mark.asyncio
    async def test_server_error(self):
        action = _make_action(GetUserAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        result = await action.execute(person_id="person-123")

        assert result["status"] == "error"


# ===========================================================================
# ListUsersAction
# ===========================================================================


class TestListUsersAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(ListUsersAction)
        users = [
            {"id": "u-1", "displayName": "Alice", "emails": ["alice@example.com"]},
            {"id": "u-2", "displayName": "Bob", "emails": ["bob@example.com"]},
        ]
        action.http_request = AsyncMock(return_value=_json_response({"items": users}))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_users"] == 2
        assert len(result["data"]["users"]) == 2
        assert result["integration_id"] == "ciscowebex"

    @pytest.mark.asyncio
    async def test_success_with_email_filter(self):
        action = _make_action(ListUsersAction)
        action.http_request = AsyncMock(
            return_value=_json_response(
                {"items": [{"id": "u-1", "displayName": "Alice"}]}
            )
        )

        result = await action.execute(email="alice@example.com")

        assert result["status"] == "success"
        assert result["data"]["total_users"] == 1
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["params"]["email"] == "alice@example.com"

    @pytest.mark.asyncio
    async def test_success_with_display_name_filter(self):
        action = _make_action(ListUsersAction)
        action.http_request = AsyncMock(return_value=_json_response({"items": []}))

        result = await action.execute(display_name="Ali")

        assert result["status"] == "success"
        assert result["data"]["total_users"] == 0
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["params"]["displayName"] == "Ali"

    @pytest.mark.asyncio
    async def test_success_empty_list(self):
        action = _make_action(ListUsersAction)
        action.http_request = AsyncMock(return_value=_json_response({"items": []}))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_users"] == 0
        assert result["data"]["users"] == []

    @pytest.mark.asyncio
    async def test_missing_bot_token(self):
        action = _make_action(ListUsersAction, credentials={})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_server_error(self):
        action = _make_action(ListUsersAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        result = await action.execute()

        assert result["status"] == "error"
