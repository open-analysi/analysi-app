"""Unit tests for Abnormal Security integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.abnormalsecurity.actions import (
    GetThreatDetailsAction,
    GetThreatStatusAction,
    HealthCheckAction,
    ListAbuseMailboxesAction,
    ListThreatsAction,
    UpdateThreatStatusAction,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

DEFAULT_CREDENTIALS = {"access_token": "test-abnsec-token-abc123"}
DEFAULT_SETTINGS = {
    "base_url": "https://api.abnormalplatform.com/v1",
    "timeout": 30,
}


def _make_action(cls, credentials=None, settings=None):
    """Create an action instance for testing."""
    return cls(
        integration_id="abnormalsecurity",
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
# AUTH HEADERS & BASE CONFIG
# ============================================================================


class TestBaseConfig:
    """Verify get_http_headers and base configuration helpers."""

    def test_headers_with_token(self):
        action = _make_action(HealthCheckAction)
        headers = action.get_http_headers()
        assert headers["Authorization"] == "Bearer test-abnsec-token-abc123"
        assert headers["Content-Type"] == "application/json"

    def test_headers_without_token(self):
        action = _make_action(HealthCheckAction, credentials={})
        headers = action.get_http_headers()
        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"

    def test_base_url_from_settings(self):
        action = _make_action(HealthCheckAction)
        assert action.base_url == "https://api.abnormalplatform.com/v1"

    def test_base_url_trailing_slash_stripped(self):
        action = _make_action(
            HealthCheckAction,
            settings={"base_url": "https://api.abnormalplatform.com/v1/"},
        )
        assert action.base_url == "https://api.abnormalplatform.com/v1"

    def test_base_url_custom(self):
        action = _make_action(
            HealthCheckAction,
            settings={"base_url": "https://custom.abnormal.example/api"},
        )
        assert action.base_url == "https://custom.abnormal.example/api"

    def test_timeout_default(self):
        action = _make_action(HealthCheckAction, settings={})
        assert action.get_timeout() == 60

    def test_timeout_custom(self):
        action = _make_action(HealthCheckAction, settings={"timeout": 120})
        assert action.get_timeout() == 120


# ============================================================================
# HEALTH CHECK
# ============================================================================


class TestHealthCheckAction:
    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        resp = _mock_response({"threats": [{"threatId": "abc-123"}]})
        action.http_request = AsyncMock(return_value=resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert result["data"]["threats_accessible"] is True
        assert "integration_id" in result
        action.http_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_success_no_threats(self, action):
        resp = _mock_response({"threats": []})
        action.http_request = AsyncMock(return_value=resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert result["data"]["threats_accessible"] is False

    @pytest.mark.asyncio
    async def test_missing_access_token(self):
        action = _make_action(HealthCheckAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "access_token" in result["error"]

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
# LIST THREATS
# ============================================================================


class TestListThreatsAction:
    @pytest.fixture
    def action(self):
        return _make_action(ListThreatsAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        threats = [{"threatId": "aaa"}, {"threatId": "bbb"}]
        resp = _mock_response({"threats": threats})
        action.http_request = AsyncMock(return_value=resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_threats"] == 2
        assert len(result["data"]["threats"]) == 2
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_success_with_limit(self, action):
        threats = [{"threatId": "aaa"}, {"threatId": "bbb"}, {"threatId": "ccc"}]
        resp = _mock_response({"threats": threats})
        action.http_request = AsyncMock(return_value=resp)

        result = await action.execute(limit=2)

        assert result["status"] == "success"
        assert result["data"]["total_threats"] == 2
        assert len(result["data"]["threats"]) == 2

    @pytest.mark.asyncio
    async def test_success_empty(self, action):
        resp = _mock_response({"threats": []})
        action.http_request = AsyncMock(return_value=resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_threats"] == 0
        assert result["data"]["threats"] == []

    @pytest.mark.asyncio
    async def test_pagination(self, action):
        page1 = _mock_response(
            {
                "threats": [{"threatId": f"t-{i}"} for i in range(3)],
                "nextPageNumber": 2,
            }
        )
        page2 = _mock_response(
            {
                "threats": [{"threatId": f"t-{i}"} for i in range(3, 5)],
            }
        )
        action.http_request = AsyncMock(side_effect=[page1, page2])

        result = await action.execute(limit=5)

        assert result["status"] == "success"
        assert result["data"]["total_threats"] == 5
        assert action.http_request.call_count == 2

    @pytest.mark.asyncio
    async def test_missing_access_token(self):
        action = _make_action(ListThreatsAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_invalid_limit(self, action):
        result = await action.execute(limit="abc")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_zero_limit(self, action):
        result = await action.execute(limit=0)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Internal Server Error")
        )
        result = await action.execute()

        assert result["status"] == "error"


# ============================================================================
# GET THREAT DETAILS
# ============================================================================


class TestGetThreatDetailsAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetThreatDetailsAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        messages = [
            {
                "threatId": "threat-1",
                "subject": "Phishing attempt",
                "fromAddress": "attacker@attacker.example",
                "attackType": "Phishing: Credential",
            }
        ]
        resp = _mock_response({"messages": messages})
        action.http_request = AsyncMock(return_value=resp)

        result = await action.execute(threat_id="threat-1")

        assert result["status"] == "success"
        assert result["data"]["threat_id"] == "threat-1"
        assert result["data"]["total_messages"] == 1
        assert result["data"]["messages"][0]["subject"] == "Phishing attempt"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_threat_id(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "threat_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetThreatDetailsAction, credentials={})
        result = await action.execute(threat_id="threat-1")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404, "Not Found"))
        result = await action.execute(threat_id="nonexistent")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["threat_id"] == "nonexistent"
        assert result["data"]["messages"] == []

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Internal Server Error")
        )
        result = await action.execute(threat_id="threat-1")

        assert result["status"] == "error"


# ============================================================================
# LIST ABUSE MAILBOXES
# ============================================================================


class TestListAbuseMailboxesAction:
    @pytest.fixture
    def action(self):
        return _make_action(ListAbuseMailboxesAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        campaigns = [
            {"campaignId": "camp-1"},
            {"campaignId": "camp-2"},
        ]
        resp = _mock_response({"campaigns": campaigns})
        action.http_request = AsyncMock(return_value=resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_campaigns"] == 2
        assert len(result["data"]["campaigns"]) == 2
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_success_empty(self, action):
        resp = _mock_response({"campaigns": []})
        action.http_request = AsyncMock(return_value=resp)

        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["total_campaigns"] == 0

    @pytest.mark.asyncio
    async def test_missing_access_token(self):
        action = _make_action(ListAbuseMailboxesAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Server Error")
        )
        result = await action.execute()

        assert result["status"] == "error"


# ============================================================================
# UPDATE THREAT STATUS
# ============================================================================


class TestUpdateThreatStatusAction:
    @pytest.fixture
    def action(self):
        return _make_action(UpdateThreatStatusAction)

    @pytest.mark.asyncio
    async def test_remediate_success(self, action):
        resp_data = {
            "action_id": "action-uuid-123",
            "status_url": "https://api.abnormalplatform.com/v1/threats/t1/actions/action-uuid-123",
        }
        action.http_request = AsyncMock(return_value=_mock_response(resp_data))

        result = await action.execute(threat_id="t1", action="remediate")

        assert result["status"] == "success"
        assert result["data"]["action_id"] == "action-uuid-123"
        assert "integration_id" in result

        # Verify POST was made with correct payload
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["method"] == "POST"
        assert call_kwargs["json_data"] == {"action": "remediate"}

    @pytest.mark.asyncio
    async def test_unremediate_success(self, action):
        resp_data = {"action_id": "action-uuid-456"}
        action.http_request = AsyncMock(return_value=_mock_response(resp_data))

        result = await action.execute(threat_id="t1", action="unremediate")

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_missing_threat_id(self, action):
        result = await action.execute(action="remediate")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "threat_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_action(self, action):
        result = await action.execute(threat_id="t1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "action" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_action(self, action):
        result = await action.execute(threat_id="t1", action="delete")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "delete" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(UpdateThreatStatusAction, credentials={})
        result = await action.execute(threat_id="t1", action="remediate")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404, "Not Found"))
        result = await action.execute(threat_id="nonexistent", action="remediate")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["threat_id"] == "nonexistent"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Internal Server Error")
        )
        result = await action.execute(threat_id="t1", action="remediate")

        assert result["status"] == "error"


# ============================================================================
# GET THREAT STATUS
# ============================================================================


class TestGetThreatStatusAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetThreatStatusAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        resp_data = {
            "status": "done",
            "description": "The request was completed successfully",
        }
        action.http_request = AsyncMock(return_value=_mock_response(resp_data))

        result = await action.execute(threat_id="t1", action_id="a1")

        assert result["status"] == "success"
        assert result["data"]["status"] == "done"
        assert result["data"]["description"] == "The request was completed successfully"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_threat_id(self, action):
        result = await action.execute(action_id="a1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "threat_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_action_id(self, action):
        result = await action.execute(threat_id="t1")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "action_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetThreatStatusAction, credentials={})
        result = await action.execute(threat_id="t1", action_id="a1")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_returns_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404, "Not Found"))
        result = await action.execute(threat_id="t1", action_id="nonexistent")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["threat_id"] == "t1"
        assert result["data"]["action_id"] == "nonexistent"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_mock_http_error(500, "Server Error")
        )
        result = await action.execute(threat_id="t1", action_id="a1")

        assert result["status"] == "error"
