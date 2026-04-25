"""Unit tests for Vectra AI NDR integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.vectra.actions import (
    AddNoteAction,
    AddTagsAction,
    GetDetectionAction,
    GetEntityAction,
    HealthCheckAction,
    ListAssignmentsAction,
    ListDetectionsAction,
    MarkDetectionAction,
    RemoveTagsAction,
    ResolveAssignmentAction,
    UnmarkDetectionAction,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_credentials():
    """Standard Vectra credentials."""
    return {"api_token": "test-vectra-token-abc123"}


@pytest.fixture
def mock_settings():
    """Standard Vectra settings."""
    return {"base_url": "https://brain.vectra.example.com", "timeout": 30}


def _make_action(action_class, action_id="test", credentials=None, settings=None):
    """Helper to instantiate an action with sensible defaults."""
    return action_class(
        integration_id="vectra",
        action_id=action_id,
        credentials=credentials or {},
        settings=settings or {},
    )


def _mock_json_response(data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock httpx.Response with .json() and .status_code."""
    resp = MagicMock()
    resp.json.return_value = data
    resp.status_code = status_code
    resp.text = str(data)
    resp.raise_for_status = MagicMock()
    return resp


def _mock_http_status_error(
    status_code: int = 500, text: str = "error"
) -> httpx.HTTPStatusError:
    """Create a realistic HTTPStatusError for testing error paths."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.text = text
    mock_response.headers = {}
    mock_request = MagicMock(spec=httpx.Request)
    mock_request.url = "https://brain.vectra.example.com/api/v2.5/test"
    return httpx.HTTPStatusError(
        message=f"Server error {status_code}",
        request=mock_request,
        response=mock_response,
    )


# ============================================================================
# HealthCheckAction Tests
# ============================================================================


class TestHealthCheckAction:
    """Tests for HealthCheckAction."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = _make_action(
            HealthCheckAction, "health_check", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=_mock_json_response({"results": []})
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["healthy"] is True
        assert "integration_id" in result
        assert result["integration_id"] == "vectra"

    @pytest.mark.asyncio
    async def test_missing_api_token(self, mock_settings):
        action = _make_action(
            HealthCheckAction, "health_check", credentials={}, settings=mock_settings
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "api_token" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_base_url(self, mock_credentials):
        action = _make_action(
            HealthCheckAction, "health_check", credentials=mock_credentials, settings={}
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "base_url" in result["error"]

    @pytest.mark.asyncio
    async def test_http_error(self, mock_credentials, mock_settings):
        action = _make_action(
            HealthCheckAction, "health_check", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            side_effect=_mock_http_status_error(401, "Unauthorized")
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["data"]["healthy"] is False

    @pytest.mark.asyncio
    async def test_connection_error(self, mock_credentials, mock_settings):
        action = _make_action(
            HealthCheckAction, "health_check", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["data"]["healthy"] is False

    @pytest.mark.asyncio
    async def test_auth_header_set(self, mock_credentials, mock_settings):
        action = _make_action(
            HealthCheckAction, "health_check", mock_credentials, mock_settings
        )
        headers = action.get_http_headers()

        assert headers["Authorization"] == "Token test-vectra-token-abc123"

    @pytest.mark.asyncio
    async def test_auth_header_empty_without_token(self, mock_settings):
        action = _make_action(
            HealthCheckAction, "health_check", credentials={}, settings=mock_settings
        )
        headers = action.get_http_headers()

        assert "Authorization" not in headers


# ============================================================================
# GetEntityAction Tests
# ============================================================================


class TestGetEntityAction:
    """Tests for GetEntityAction."""

    @pytest.mark.asyncio
    async def test_get_host_success(self, mock_credentials, mock_settings):
        action = _make_action(
            GetEntityAction, "get_entity", mock_credentials, mock_settings
        )
        entity_data = {
            "id": 123,
            "name": "test-host-01",
            "threat": 80,
            "certainty": 90,
            "tags": ["important"],
        }
        action.http_request = AsyncMock(return_value=_mock_json_response(entity_data))

        result = await action.execute(entity_type="host", entity_id=123)

        assert result["status"] == "success"
        assert result["data"]["id"] == 123
        assert result["data"]["name"] == "test-host-01"
        action.http_request.assert_called_once()
        call_url = action.http_request.call_args.kwargs["url"]
        assert "/api/v2.5/hosts/123" in call_url

    @pytest.mark.asyncio
    async def test_get_account_success(self, mock_credentials, mock_settings):
        action = _make_action(
            GetEntityAction, "get_entity", mock_credentials, mock_settings
        )
        entity_data = {"id": 456, "name": "admin@corp.local"}
        action.http_request = AsyncMock(return_value=_mock_json_response(entity_data))

        result = await action.execute(entity_type="account", entity_id=456)

        assert result["status"] == "success"
        call_url = action.http_request.call_args.kwargs["url"]
        assert "/api/v2.5/accounts/456" in call_url

    @pytest.mark.asyncio
    async def test_missing_entity_type(self, mock_credentials, mock_settings):
        action = _make_action(
            GetEntityAction, "get_entity", mock_credentials, mock_settings
        )

        result = await action.execute(entity_id=123)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "entity_type" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_entity_id(self, mock_credentials, mock_settings):
        action = _make_action(
            GetEntityAction, "get_entity", mock_credentials, mock_settings
        )

        result = await action.execute(entity_type="host")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "entity_id" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_entity_type(self, mock_credentials, mock_settings):
        action = _make_action(
            GetEntityAction, "get_entity", mock_credentials, mock_settings
        )

        result = await action.execute(entity_type="invalid", entity_id=123)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "host" in result["error"] or "account" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_entity_id_non_integer(self, mock_credentials, mock_settings):
        action = _make_action(
            GetEntityAction, "get_entity", mock_credentials, mock_settings
        )

        result = await action.execute(entity_type="host", entity_id="not-a-number")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_negative_entity_id(self, mock_credentials, mock_settings):
        action = _make_action(
            GetEntityAction, "get_entity", mock_credentials, mock_settings
        )

        result = await action.execute(entity_type="host", entity_id=-1)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_entity_not_found_returns_success(
        self, mock_credentials, mock_settings
    ):
        action = _make_action(
            GetEntityAction, "get_entity", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            side_effect=_mock_http_status_error(404, "Not found")
        )

        result = await action.execute(entity_type="host", entity_id=999)

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["entity_type"] == "host"
        assert result["data"]["entity_id"] == 999

    @pytest.mark.asyncio
    async def test_http_error_non_404(self, mock_credentials, mock_settings):
        action = _make_action(
            GetEntityAction, "get_entity", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            side_effect=_mock_http_status_error(500, "Internal")
        )

        result = await action.execute(entity_type="host", entity_id=123)

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_case_insensitive_entity_type(self, mock_credentials, mock_settings):
        action = _make_action(
            GetEntityAction, "get_entity", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(return_value=_mock_json_response({"id": 1}))

        result = await action.execute(entity_type="HOST", entity_id=1)

        assert result["status"] == "success"


# ============================================================================
# ListDetectionsAction Tests
# ============================================================================


class TestListDetectionsAction:
    """Tests for ListDetectionsAction."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = _make_action(
            ListDetectionsAction, "list_detections", mock_credentials, mock_settings
        )
        api_response = {
            "results": [
                {"id": 1, "category": "COMMAND_AND_CONTROL"},
                {"id": 2, "category": "LATERAL_MOVEMENT"},
            ],
            "next": None,
        }
        action.http_request = AsyncMock(return_value=_mock_json_response(api_response))

        result = await action.execute(entity_type="host", entity_id=100)

        assert result["status"] == "success"
        assert result["data"]["total_detections"] == 2
        assert len(result["data"]["detections"]) == 2

    @pytest.mark.asyncio
    async def test_pagination(self, mock_credentials, mock_settings):
        action = _make_action(
            ListDetectionsAction, "list_detections", mock_credentials, mock_settings
        )
        page1 = _mock_json_response(
            {
                "results": [{"id": 1}],
                "next": "https://brain.vectra.example.com/api/v2.2/search/detections?page=2",
            }
        )
        page2 = _mock_json_response(
            {
                "results": [{"id": 2}],
                "next": None,
            }
        )
        action.http_request = AsyncMock(side_effect=[page1, page2])

        result = await action.execute(entity_type="host", entity_id=100)

        assert result["status"] == "success"
        assert result["data"]["total_detections"] == 2
        assert action.http_request.call_count == 2

    @pytest.mark.asyncio
    async def test_account_uses_linked_account_query(
        self, mock_credentials, mock_settings
    ):
        action = _make_action(
            ListDetectionsAction, "list_detections", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=_mock_json_response({"results": [], "next": None})
        )

        await action.execute(entity_type="account", entity_id=50)

        call_params = action.http_request.call_args.kwargs["params"]
        assert "linked_account" in call_params["query_string"]

    @pytest.mark.asyncio
    async def test_missing_entity_type(self, mock_credentials, mock_settings):
        action = _make_action(
            ListDetectionsAction, "list_detections", mock_credentials, mock_settings
        )

        result = await action.execute(entity_id=100)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_entity_id(self, mock_credentials, mock_settings):
        action = _make_action(
            ListDetectionsAction, "list_detections", mock_credentials, mock_settings
        )

        result = await action.execute(entity_type="host")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_entity_type(self, mock_credentials, mock_settings):
        action = _make_action(
            ListDetectionsAction, "list_detections", mock_credentials, mock_settings
        )

        result = await action.execute(entity_type="server", entity_id=1)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_empty_results(self, mock_credentials, mock_settings):
        action = _make_action(
            ListDetectionsAction, "list_detections", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=_mock_json_response({"results": [], "next": None})
        )

        result = await action.execute(entity_type="host", entity_id=100)

        assert result["status"] == "success"
        assert result["data"]["total_detections"] == 0
        assert result["data"]["detections"] == []

    @pytest.mark.asyncio
    async def test_http_error(self, mock_credentials, mock_settings):
        action = _make_action(
            ListDetectionsAction, "list_detections", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(503))

        result = await action.execute(entity_type="host", entity_id=100)

        assert result["status"] == "error"


# ============================================================================
# GetDetectionAction Tests
# ============================================================================


class TestGetDetectionAction:
    """Tests for GetDetectionAction."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = _make_action(
            GetDetectionAction, "get_detection", mock_credentials, mock_settings
        )
        detection_data = {
            "id": 14153,
            "category": "INFO",
            "detection": "New Host",
            "certainty": 50,
            "threat": 30,
        }
        action.http_request = AsyncMock(
            return_value=_mock_json_response(detection_data)
        )

        result = await action.execute(detection_id=14153)

        assert result["status"] == "success"
        assert result["data"]["id"] == 14153
        assert result["data"]["category"] == "INFO"
        call_url = action.http_request.call_args.kwargs["url"]
        assert "/api/v2.5/detections/14153" in call_url

    @pytest.mark.asyncio
    async def test_missing_detection_id(self, mock_credentials, mock_settings):
        action = _make_action(
            GetDetectionAction, "get_detection", mock_credentials, mock_settings
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "detection_id" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_detection_id(self, mock_credentials, mock_settings):
        action = _make_action(
            GetDetectionAction, "get_detection", mock_credentials, mock_settings
        )

        result = await action.execute(detection_id="abc")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_not_found(self, mock_credentials, mock_settings):
        action = _make_action(
            GetDetectionAction, "get_detection", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(404))

        result = await action.execute(detection_id=99999)

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["detection_id"] == 99999

    @pytest.mark.asyncio
    async def test_server_error(self, mock_credentials, mock_settings):
        action = _make_action(
            GetDetectionAction, "get_detection", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(500))

        result = await action.execute(detection_id=123)

        assert result["status"] == "error"


# ============================================================================
# MarkDetectionAction Tests
# ============================================================================


class TestMarkDetectionAction:
    """Tests for MarkDetectionAction."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = _make_action(
            MarkDetectionAction, "mark_detection", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=_mock_json_response({"_meta": {"modified": 1}})
        )

        result = await action.execute(detection_id=100)

        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["method"] == "PATCH"
        assert call_kwargs["json_data"]["mark_as_fixed"] == "True"
        assert call_kwargs["json_data"]["detectionIdList"] == [100]

    @pytest.mark.asyncio
    async def test_missing_detection_id(self, mock_credentials, mock_settings):
        action = _make_action(
            MarkDetectionAction, "mark_detection", mock_credentials, mock_settings
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_detection_id(self, mock_credentials, mock_settings):
        action = _make_action(
            MarkDetectionAction, "mark_detection", mock_credentials, mock_settings
        )

        result = await action.execute(detection_id="not-a-number")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_http_error(self, mock_credentials, mock_settings):
        action = _make_action(
            MarkDetectionAction, "mark_detection", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            side_effect=_mock_http_status_error(403, "Forbidden")
        )

        result = await action.execute(detection_id=100)

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_missing_credentials(self, mock_settings):
        action = _make_action(
            MarkDetectionAction,
            "mark_detection",
            credentials={},
            settings=mock_settings,
        )

        result = await action.execute(detection_id=100)

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ============================================================================
# UnmarkDetectionAction Tests
# ============================================================================


class TestUnmarkDetectionAction:
    """Tests for UnmarkDetectionAction."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = _make_action(
            UnmarkDetectionAction, "unmark_detection", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=_mock_json_response({"_meta": {"modified": 1}})
        )

        result = await action.execute(detection_id=100)

        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["method"] == "PATCH"
        assert call_kwargs["json_data"]["mark_as_fixed"] == "False"

    @pytest.mark.asyncio
    async def test_missing_detection_id(self, mock_credentials, mock_settings):
        action = _make_action(
            UnmarkDetectionAction, "unmark_detection", mock_credentials, mock_settings
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_http_error(self, mock_credentials, mock_settings):
        action = _make_action(
            UnmarkDetectionAction, "unmark_detection", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(500))

        result = await action.execute(detection_id=100)

        assert result["status"] == "error"


# ============================================================================
# AddNoteAction Tests
# ============================================================================


class TestAddNoteAction:
    """Tests for AddNoteAction."""

    @pytest.mark.asyncio
    async def test_success_host(self, mock_credentials, mock_settings):
        action = _make_action(
            AddNoteAction, "add_note", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=_mock_json_response({"id": 1, "note": "Suspicious activity"})
        )

        result = await action.execute(
            object_type="host", object_id=10, note="Suspicious activity"
        )

        assert result["status"] == "success"
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["method"] == "POST"
        assert call_kwargs["json_data"]["note"] == "Suspicious activity"
        assert "/api/v2.5/hosts/10/notes" in call_kwargs["url"]

    @pytest.mark.asyncio
    async def test_success_detection(self, mock_credentials, mock_settings):
        action = _make_action(
            AddNoteAction, "add_note", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=_mock_json_response({"id": 2, "note": "FP"})
        )

        result = await action.execute(object_type="detection", object_id=99, note="FP")

        assert result["status"] == "success"
        call_url = action.http_request.call_args.kwargs["url"]
        assert "/api/v2.5/detections/99/notes" in call_url

    @pytest.mark.asyncio
    async def test_missing_object_type(self, mock_credentials, mock_settings):
        action = _make_action(
            AddNoteAction, "add_note", mock_credentials, mock_settings
        )

        result = await action.execute(object_id=10, note="test")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_object_id(self, mock_credentials, mock_settings):
        action = _make_action(
            AddNoteAction, "add_note", mock_credentials, mock_settings
        )

        result = await action.execute(object_type="host", note="test")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_note(self, mock_credentials, mock_settings):
        action = _make_action(
            AddNoteAction, "add_note", mock_credentials, mock_settings
        )

        result = await action.execute(object_type="host", object_id=10)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_object_type(self, mock_credentials, mock_settings):
        action = _make_action(
            AddNoteAction, "add_note", mock_credentials, mock_settings
        )

        result = await action.execute(
            object_type="container", object_id=10, note="test"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_object_id(self, mock_credentials, mock_settings):
        action = _make_action(
            AddNoteAction, "add_note", mock_credentials, mock_settings
        )

        result = await action.execute(object_type="host", object_id="abc", note="test")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_http_error(self, mock_credentials, mock_settings):
        action = _make_action(
            AddNoteAction, "add_note", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            side_effect=_mock_http_status_error(400, "Bad Request")
        )

        result = await action.execute(object_type="host", object_id=10, note="test")

        assert result["status"] == "error"


# ============================================================================
# ListAssignmentsAction Tests
# ============================================================================


class TestListAssignmentsAction:
    """Tests for ListAssignmentsAction."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = _make_action(
            ListAssignmentsAction, "list_assignments", mock_credentials, mock_settings
        )
        api_response = {
            "results": [
                {"id": 1, "assigned_by": "admin", "assigned_to": "analyst1"},
                {"id": 2, "assigned_by": "admin", "assigned_to": "analyst2"},
            ],
            "next": None,
        }
        action.http_request = AsyncMock(return_value=_mock_json_response(api_response))

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_assignments"] == 2
        assert len(result["data"]["assignments"]) == 2

    @pytest.mark.asyncio
    async def test_pagination(self, mock_credentials, mock_settings):
        action = _make_action(
            ListAssignmentsAction, "list_assignments", mock_credentials, mock_settings
        )
        page1 = _mock_json_response(
            {
                "results": [{"id": 1}],
                "next": "https://brain.vectra.example.com/api/v2.5/assignments?page=2",
            }
        )
        page2 = _mock_json_response(
            {
                "results": [{"id": 2}],
                "next": None,
            }
        )
        action.http_request = AsyncMock(side_effect=[page1, page2])

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_assignments"] == 2

    @pytest.mark.asyncio
    async def test_empty_results(self, mock_credentials, mock_settings):
        action = _make_action(
            ListAssignmentsAction, "list_assignments", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(
            return_value=_mock_json_response({"results": [], "next": None})
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_assignments"] == 0

    @pytest.mark.asyncio
    async def test_missing_credentials(self, mock_settings):
        action = _make_action(
            ListAssignmentsAction,
            "list_assignments",
            credentials={},
            settings=mock_settings,
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_error(self, mock_credentials, mock_settings):
        action = _make_action(
            ListAssignmentsAction, "list_assignments", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(500))

        result = await action.execute()

        assert result["status"] == "error"


# ============================================================================
# ResolveAssignmentAction Tests
# ============================================================================


class TestResolveAssignmentAction:
    """Tests for ResolveAssignmentAction."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = _make_action(
            ResolveAssignmentAction,
            "resolve_assignment",
            mock_credentials,
            mock_settings,
        )

        # Mock outcomes lookup (paginated)
        outcomes_resp = _mock_json_response(
            {
                "results": [
                    {"id": 10, "title": "Benign True Positive"},
                    {"id": 20, "title": "Malicious True Positive"},
                ],
                "next": None,
            }
        )
        # Mock resolve response
        resolve_resp = _mock_json_response(
            {
                "assignment": {
                    "id": 5,
                    "resolved_by": "admin",
                    "outcome": {"title": "Benign True Positive"},
                },
            }
        )
        action.http_request = AsyncMock(side_effect=[outcomes_resp, resolve_resp])

        result = await action.execute(
            assignment_id=5,
            outcome="Benign True Positive",
            note="Confirmed benign",
        )

        assert result["status"] == "success"
        assert result["data"]["id"] == 5

    @pytest.mark.asyncio
    async def test_invalid_outcome(self, mock_credentials, mock_settings):
        action = _make_action(
            ResolveAssignmentAction,
            "resolve_assignment",
            mock_credentials,
            mock_settings,
        )

        outcomes_resp = _mock_json_response(
            {
                "results": [{"id": 10, "title": "Benign True Positive"}],
                "next": None,
            }
        )
        action.http_request = AsyncMock(return_value=outcomes_resp)

        result = await action.execute(assignment_id=5, outcome="NonExistentOutcome")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "NonExistentOutcome" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_assignment_id(self, mock_credentials, mock_settings):
        action = _make_action(
            ResolveAssignmentAction,
            "resolve_assignment",
            mock_credentials,
            mock_settings,
        )

        result = await action.execute(outcome="Benign True Positive")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "assignment_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_outcome(self, mock_credentials, mock_settings):
        action = _make_action(
            ResolveAssignmentAction,
            "resolve_assignment",
            mock_credentials,
            mock_settings,
        )

        result = await action.execute(assignment_id=5)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "outcome" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_assignment_id(self, mock_credentials, mock_settings):
        action = _make_action(
            ResolveAssignmentAction,
            "resolve_assignment",
            mock_credentials,
            mock_settings,
        )

        result = await action.execute(
            assignment_id="abc", outcome="Benign True Positive"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_with_detection_ids_and_triage(self, mock_credentials, mock_settings):
        action = _make_action(
            ResolveAssignmentAction,
            "resolve_assignment",
            mock_credentials,
            mock_settings,
        )

        outcomes_resp = _mock_json_response(
            {
                "results": [{"id": 10, "title": "Benign True Positive"}],
                "next": None,
            }
        )
        resolve_resp = _mock_json_response(
            {
                "assignment": {"id": 5, "outcome": {"title": "Benign True Positive"}},
            }
        )
        action.http_request = AsyncMock(side_effect=[outcomes_resp, resolve_resp])

        result = await action.execute(
            assignment_id=5,
            outcome="Benign True Positive",
            triage_as="false_positive",
            detection_ids="100,200,300",
        )

        assert result["status"] == "success"
        resolve_call = action.http_request.call_args_list[1]
        payload = resolve_call.kwargs["json_data"]
        assert payload["detection_ids"] == [100, 200, 300]
        assert payload["triage_as"] == "false_positive"

    @pytest.mark.asyncio
    async def test_default_note(self, mock_credentials, mock_settings):
        action = _make_action(
            ResolveAssignmentAction,
            "resolve_assignment",
            mock_credentials,
            mock_settings,
        )

        outcomes_resp = _mock_json_response(
            {
                "results": [{"id": 10, "title": "Benign True Positive"}],
                "next": None,
            }
        )
        resolve_resp = _mock_json_response({"assignment": {"id": 5}})
        action.http_request = AsyncMock(side_effect=[outcomes_resp, resolve_resp])

        await action.execute(assignment_id=5, outcome="Benign True Positive")

        resolve_call = action.http_request.call_args_list[1]
        payload = resolve_call.kwargs["json_data"]
        assert payload["note"] == "Resolved via Analysi"


# ============================================================================
# AddTagsAction Tests
# ============================================================================


class TestAddTagsAction:
    """Tests for AddTagsAction."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = _make_action(
            AddTagsAction, "add_tags", mock_credentials, mock_settings
        )

        # Mock GET existing tags, then PATCH to update
        get_resp = _mock_json_response({"tags": ["existing-tag"]})
        patch_resp = _mock_json_response(
            {"tags": ["existing-tag", "new-tag-1", "new-tag-2"]}
        )
        action.http_request = AsyncMock(side_effect=[get_resp, patch_resp])

        result = await action.execute(
            entity_type="host", entity_id=10, tags="new-tag-1, new-tag-2"
        )

        assert result["status"] == "success"
        # Verify PATCH payload contains merged tags
        patch_call = action.http_request.call_args_list[1]
        merged_tags = patch_call.kwargs["json_data"]["tags"]
        assert "existing-tag" in merged_tags
        assert "new-tag-1" in merged_tags
        assert "new-tag-2" in merged_tags

    @pytest.mark.asyncio
    async def test_deduplication(self, mock_credentials, mock_settings):
        action = _make_action(
            AddTagsAction, "add_tags", mock_credentials, mock_settings
        )

        get_resp = _mock_json_response({"tags": ["tag-a", "tag-b"]})
        patch_resp = _mock_json_response({"tags": ["tag-a", "tag-b"]})
        action.http_request = AsyncMock(side_effect=[get_resp, patch_resp])

        await action.execute(entity_type="host", entity_id=10, tags="tag-a")

        patch_call = action.http_request.call_args_list[1]
        merged_tags = patch_call.kwargs["json_data"]["tags"]
        # tag-a should appear only once
        assert merged_tags.count("tag-a") == 1

    @pytest.mark.asyncio
    async def test_missing_entity_type(self, mock_credentials, mock_settings):
        action = _make_action(
            AddTagsAction, "add_tags", mock_credentials, mock_settings
        )

        result = await action.execute(entity_id=10, tags="tag1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_entity_id(self, mock_credentials, mock_settings):
        action = _make_action(
            AddTagsAction, "add_tags", mock_credentials, mock_settings
        )

        result = await action.execute(entity_type="host", tags="tag1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_tags(self, mock_credentials, mock_settings):
        action = _make_action(
            AddTagsAction, "add_tags", mock_credentials, mock_settings
        )

        result = await action.execute(entity_type="host", entity_id=10)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_entity_type(self, mock_credentials, mock_settings):
        action = _make_action(
            AddTagsAction, "add_tags", mock_credentials, mock_settings
        )

        result = await action.execute(entity_type="firewall", entity_id=10, tags="tag1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_empty_tags_string(self, mock_credentials, mock_settings):
        action = _make_action(
            AddTagsAction, "add_tags", mock_credentials, mock_settings
        )

        result = await action.execute(entity_type="host", entity_id=10, tags=",,,")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_http_error(self, mock_credentials, mock_settings):
        action = _make_action(
            AddTagsAction, "add_tags", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(500))

        result = await action.execute(entity_type="host", entity_id=10, tags="tag1")

        assert result["status"] == "error"


# ============================================================================
# RemoveTagsAction Tests
# ============================================================================


class TestRemoveTagsAction:
    """Tests for RemoveTagsAction."""

    @pytest.mark.asyncio
    async def test_success(self, mock_credentials, mock_settings):
        action = _make_action(
            RemoveTagsAction, "remove_tags", mock_credentials, mock_settings
        )

        get_resp = _mock_json_response({"tags": ["keep-me", "remove-me", "also-keep"]})
        patch_resp = _mock_json_response({"tags": ["keep-me", "also-keep"]})
        action.http_request = AsyncMock(side_effect=[get_resp, patch_resp])

        result = await action.execute(
            entity_type="host", entity_id=10, tags="remove-me"
        )

        assert result["status"] == "success"
        patch_call = action.http_request.call_args_list[1]
        remaining_tags = patch_call.kwargs["json_data"]["tags"]
        assert "remove-me" not in remaining_tags
        assert "keep-me" in remaining_tags
        assert "also-keep" in remaining_tags

    @pytest.mark.asyncio
    async def test_remove_multiple_tags(self, mock_credentials, mock_settings):
        action = _make_action(
            RemoveTagsAction, "remove_tags", mock_credentials, mock_settings
        )

        get_resp = _mock_json_response({"tags": ["a", "b", "c", "d"]})
        patch_resp = _mock_json_response({"tags": ["a", "d"]})
        action.http_request = AsyncMock(side_effect=[get_resp, patch_resp])

        result = await action.execute(entity_type="account", entity_id=20, tags="b, c")

        assert result["status"] == "success"
        patch_call = action.http_request.call_args_list[1]
        remaining_tags = patch_call.kwargs["json_data"]["tags"]
        assert remaining_tags == ["a", "d"]

    @pytest.mark.asyncio
    async def test_remove_nonexistent_tag(self, mock_credentials, mock_settings):
        action = _make_action(
            RemoveTagsAction, "remove_tags", mock_credentials, mock_settings
        )

        get_resp = _mock_json_response({"tags": ["tag1", "tag2"]})
        patch_resp = _mock_json_response({"tags": ["tag1", "tag2"]})
        action.http_request = AsyncMock(side_effect=[get_resp, patch_resp])

        result = await action.execute(
            entity_type="host", entity_id=10, tags="nonexistent"
        )

        assert result["status"] == "success"
        patch_call = action.http_request.call_args_list[1]
        remaining_tags = patch_call.kwargs["json_data"]["tags"]
        assert remaining_tags == ["tag1", "tag2"]

    @pytest.mark.asyncio
    async def test_missing_entity_type(self, mock_credentials, mock_settings):
        action = _make_action(
            RemoveTagsAction, "remove_tags", mock_credentials, mock_settings
        )

        result = await action.execute(entity_id=10, tags="tag1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_tags(self, mock_credentials, mock_settings):
        action = _make_action(
            RemoveTagsAction, "remove_tags", mock_credentials, mock_settings
        )

        result = await action.execute(entity_type="host", entity_id=10)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_invalid_entity_type(self, mock_credentials, mock_settings):
        action = _make_action(
            RemoveTagsAction, "remove_tags", mock_credentials, mock_settings
        )

        result = await action.execute(entity_type="switch", entity_id=10, tags="tag1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_http_error(self, mock_credentials, mock_settings):
        action = _make_action(
            RemoveTagsAction, "remove_tags", mock_credentials, mock_settings
        )
        action.http_request = AsyncMock(side_effect=_mock_http_status_error(500))

        result = await action.execute(entity_type="host", entity_id=10, tags="tag1")

        assert result["status"] == "error"


# ============================================================================
# Cross-cutting: Credential Validation for All Actions
# ============================================================================


class TestCredentialValidation:
    """Verify all action classes reject missing credentials consistently."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "action_cls",
        [
            HealthCheckAction,
            GetEntityAction,
            ListDetectionsAction,
            GetDetectionAction,
            MarkDetectionAction,
            UnmarkDetectionAction,
            AddNoteAction,
            ListAssignmentsAction,
            ResolveAssignmentAction,
            AddTagsAction,
            RemoveTagsAction,
        ],
    )
    async def test_missing_api_token_returns_config_error(
        self, action_cls, mock_settings
    ):
        action = _make_action(
            action_cls, "test", credentials={}, settings=mock_settings
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "action_cls",
        [
            HealthCheckAction,
            GetEntityAction,
            ListDetectionsAction,
            GetDetectionAction,
            MarkDetectionAction,
            UnmarkDetectionAction,
            AddNoteAction,
            ListAssignmentsAction,
            ResolveAssignmentAction,
            AddTagsAction,
            RemoveTagsAction,
        ],
    )
    async def test_missing_base_url_returns_config_error(
        self, action_cls, mock_credentials
    ):
        action = _make_action(
            action_cls, "test", credentials=mock_credentials, settings={}
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
