"""Unit tests for Mimecast integration actions.

Tests mock at the IntegrationAction.http_request level and the OAuth2 token
helper so retry behaviour is transparent and tests stay fast (< 0.1s each).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from analysi.integrations.framework.integrations.mimecast.actions import (
    AddManagedUrlAction,
    BlockSenderAction,
    DecodeUrlAction,
    GetEmailAction,
    GetManagedUrlAction,
    HealthCheckAction,
    ListUrlsAction,
    SearchMessagesAction,
    UnblockSenderAction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_CREDENTIALS = {"client_id": "test-client-id", "client_secret": "test-secret"}
OAUTH_MODULE = (
    "analysi.integrations.framework.integrations.mimecast.actions._get_oauth_token"
)


def _json_response(data: dict, status_code: int = 200) -> MagicMock:
    """Build a fake httpx.Response for http_request mock."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    return resp


def _http_status_error(status_code: int, body: str = "") -> httpx.HTTPStatusError:
    """Build a fake httpx.HTTPStatusError."""
    request = MagicMock(spec=httpx.Request)
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = body
    return httpx.HTTPStatusError(
        message=f"HTTP {status_code}",
        request=request,
        response=response,
    )


def _make_action(cls, action_id: str, credentials=None, settings=None):
    """Create an action instance with optional credential/settings override."""
    return cls(
        integration_id="mimecast",
        action_id=action_id,
        settings=settings or {},
        credentials=credentials if credentials is not None else VALID_CREDENTIALS,
    )


# ===========================================================================
# HealthCheckAction
# ===========================================================================


class TestHealthCheckAction:
    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction, "health_check")

    @pytest.mark.asyncio
    async def test_success(self, action):
        mock_response = _json_response(
            {"meta": {"status": 200}, "data": [], "fail": []}
        )
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="test-token"):
            result = await action.execute()

        assert result["status"] == "success"
        assert result["integration_id"] == "mimecast"
        assert result["action_id"] == "health_check"
        assert result["data"]["healthy"] is True
        assert result["healthy"] is True

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(HealthCheckAction, "health_check", credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert "Missing required credentials" in result["error"]
        assert result["error_type"] == "ConfigurationError"
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        with patch(
            OAUTH_MODULE,
            new_callable=AsyncMock,
            side_effect=Exception("Connection refused"),
        ):
            result = await action.execute()

        assert result["status"] == "error"
        assert "Connection refused" in result["error"]
        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_oauth_token_passed_in_headers(self, action):
        mock_response = _json_response(
            {"meta": {"status": 200}, "data": [], "fail": []}
        )
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(
            OAUTH_MODULE, new_callable=AsyncMock, return_value="my-bearer-token"
        ):
            await action.execute()

        call_kwargs = action.http_request.call_args.kwargs
        assert "Bearer my-bearer-token" in call_kwargs["headers"]["Authorization"]


# ===========================================================================
# DecodeUrlAction
# ===========================================================================


class TestDecodeUrlAction:
    @pytest.fixture
    def action(self):
        return _make_action(DecodeUrlAction, "decode_url")

    @pytest.mark.asyncio
    async def test_success(self, action):
        decode_data = {
            "data": [{"url": "https://example.com/original", "success": True}],
            "fail": [],
        }
        mock_response = _json_response(decode_data)
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            result = await action.execute(
                url="https://sandbox-api.mimecast.com/s/encoded"
            )

        assert result["status"] == "success"
        assert result["data"]["url"] == "https://example.com/original"
        assert result["data"]["success"] is True

    @pytest.mark.asyncio
    async def test_missing_url(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "url" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(DecodeUrlAction, "decode_url", credentials={})
        result = await action.execute(url="https://test.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            result = await action.execute(url="https://test.com")

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"

    @pytest.mark.asyncio
    async def test_json_body_structure(self, action):
        mock_response = _json_response({"data": [{"url": "decoded"}], "fail": []})
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            await action.execute(url="https://mimecast.com/encoded")

        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["json_data"] == {
            "data": [{"url": "https://mimecast.com/encoded"}]
        }


# ===========================================================================
# GetEmailAction
# ===========================================================================


class TestGetEmailAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetEmailAction, "get_email")

    @pytest.mark.asyncio
    async def test_success(self, action):
        email_data = {
            "data": [
                {
                    "deliveredMessage": [
                        {
                            "messageInfo": {
                                "fromEnvelope": "sender@example.com",
                                "fromHeader": "sender@example.com",
                                "subject": "Test Subject",
                            },
                            "deliveryMetaInfo": {
                                "emailAddress": "recipient@example.com",
                                "deliveryEvent": "Email Delivered",
                            },
                        }
                    ]
                }
            ],
            "fail": [],
        }
        mock_response = _json_response(email_data)
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            result = await action.execute(id="test-email-id-123")

        assert result["status"] == "success"
        assert "deliveredMessage" in result["data"]

    @pytest.mark.asyncio
    async def test_missing_id(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "id" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            result = await action.execute(id="nonexistent-id")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["id"] == "nonexistent-id"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetEmailAction, "get_email", credentials={})
        result = await action.execute(id="some-id")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_server_error(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            result = await action.execute(id="some-id")

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"


# ===========================================================================
# ListUrlsAction
# ===========================================================================


class TestListUrlsAction:
    @pytest.fixture
    def action(self):
        return _make_action(ListUrlsAction, "list_urls")

    @pytest.mark.asyncio
    async def test_success(self, action):
        url_list = {
            "data": [
                {
                    "id": "url-1",
                    "domain": "evil.com",
                    "action": "block",
                    "matchType": "explicit",
                },
                {
                    "id": "url-2",
                    "domain": "test.com",
                    "action": "permit",
                    "matchType": "domain",
                },
            ],
            "meta": {"pagination": {"pageSize": 100}},
            "fail": [],
        }
        mock_response = _json_response(url_list)
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["num_urls"] == 2
        assert len(result["data"]["urls"]) == 2

    @pytest.mark.asyncio
    async def test_with_max_results(self, action):
        url_list = {
            "data": [
                {"id": "url-1", "domain": "a.com", "action": "block"},
                {"id": "url-2", "domain": "b.com", "action": "block"},
                {"id": "url-3", "domain": "c.com", "action": "permit"},
            ],
            "meta": {"pagination": {"pageSize": 100}},
            "fail": [],
        }
        mock_response = _json_response(url_list)
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            result = await action.execute(max_results=2)

        assert result["status"] == "success"
        assert result["data"]["num_urls"] == 2
        assert len(result["data"]["urls"]) == 2

    @pytest.mark.asyncio
    async def test_invalid_max_results(self, action):
        result = await action.execute(max_results="abc")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_zero_max_results(self, action):
        result = await action.execute(max_results=0)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(ListUrlsAction, "list_urls", credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# BlockSenderAction
# ===========================================================================


class TestBlockSenderAction:
    @pytest.fixture
    def action(self):
        return _make_action(BlockSenderAction, "block_sender")

    @pytest.mark.asyncio
    async def test_success(self, action):
        resp = {
            "data": [
                {"sender": "bad@evil.com", "to": "user@company.com", "type": "block"}
            ],
            "fail": [],
        }
        mock_response = _json_response(resp)
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            result = await action.execute(sender="bad@evil.com", to="user@company.com")

        assert result["status"] == "success"
        assert result["data"]["sender"] == "bad@evil.com"

    @pytest.mark.asyncio
    async def test_sends_block_action(self, action):
        mock_response = _json_response({"data": [{}], "fail": []})
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            await action.execute(sender="bad@evil.com", to="user@company.com")

        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["json_data"]["data"][0]["action"] == "block"

    @pytest.mark.asyncio
    async def test_missing_sender(self, action):
        result = await action.execute(to="user@company.com")

        assert result["status"] == "error"
        assert "sender" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_to(self, action):
        result = await action.execute(sender="bad@evil.com")

        assert result["status"] == "error"
        assert "to" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(BlockSenderAction, "block_sender", credentials={})
        result = await action.execute(sender="bad@evil.com", to="user@company.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_http_status_error(403, "Forbidden")
        )

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            result = await action.execute(sender="bad@evil.com", to="user@company.com")

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"


# ===========================================================================
# UnblockSenderAction
# ===========================================================================


class TestUnblockSenderAction:
    @pytest.fixture
    def action(self):
        return _make_action(UnblockSenderAction, "unblock_sender")

    @pytest.mark.asyncio
    async def test_success(self, action):
        resp = {
            "data": [
                {
                    "sender": "sender@example.com",
                    "to": "user@company.com",
                    "type": "permit",
                }
            ],
            "fail": [],
        }
        mock_response = _json_response(resp)
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            result = await action.execute(
                sender="sender@example.com", to="user@company.com"
            )

        assert result["status"] == "success"
        assert result["data"]["sender"] == "sender@example.com"

    @pytest.mark.asyncio
    async def test_sends_permit_action(self, action):
        mock_response = _json_response({"data": [{}], "fail": []})
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            await action.execute(sender="sender@example.com", to="user@company.com")

        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["json_data"]["data"][0]["action"] == "permit"

    @pytest.mark.asyncio
    async def test_missing_sender(self, action):
        result = await action.execute(to="user@company.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_to(self, action):
        result = await action.execute(sender="sender@example.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(UnblockSenderAction, "unblock_sender", credentials={})
        result = await action.execute(sender="s@e.com", to="u@c.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# SearchMessagesAction
# ===========================================================================


class TestSearchMessagesAction:
    @pytest.fixture
    def action(self):
        return _make_action(SearchMessagesAction, "search_messages")

    @pytest.mark.asyncio
    async def test_success(self, action):
        search_resp = {
            "data": [
                {
                    "trackedEmails": [
                        {
                            "id": "email-1",
                            "status": "delivered",
                            "fromEnv": {"emailAddress": "sender@example.com"},
                            "to": {"emailAddress": "recipient@example.com"},
                            "subject": "Test Email",
                        }
                    ]
                }
            ],
            "fail": [],
        }
        mock_response = _json_response(search_resp)
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            result = await action.execute(from_address="sender@example.com")

        assert result["status"] == "success"
        assert result["data"]["num_emails"] == 1
        assert len(result["data"]["tracked_emails"]) == 1

    @pytest.mark.asyncio
    async def test_search_with_all_params(self, action):
        search_resp = {"data": [{"trackedEmails": []}], "fail": []}
        mock_response = _json_response(search_resp)
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            await action.execute(
                message_id="<msg-id@example.com>",
                search_reason="investigation",
                from_address="sender@example.com",
                to_address="recipient@example.com",
                subject="Test",
                sender_ip="192.168.1.1",
                start="2025-01-01T00:00:00+0000",
                end="2025-01-02T00:00:00+0000",
            )

        call_kwargs = action.http_request.call_args.kwargs
        search_data = call_kwargs["json_data"]["data"][0]
        assert search_data["messageId"] == "<msg-id@example.com>"
        assert search_data["searchReason"] == "investigation"
        assert (
            search_data["advancedTrackAndTraceOptions"]["from"] == "sender@example.com"
        )
        assert (
            search_data["advancedTrackAndTraceOptions"]["to"] == "recipient@example.com"
        )
        assert search_data["advancedTrackAndTraceOptions"]["subject"] == "Test"
        assert search_data["advancedTrackAndTraceOptions"]["senderIp"] == "192.168.1.1"
        assert search_data["start"] == "2025-01-01T00:00:00+0000"
        assert search_data["end"] == "2025-01-02T00:00:00+0000"

    @pytest.mark.asyncio
    async def test_no_results(self, action):
        search_resp = {"data": [{"trackedEmails": []}], "fail": []}
        mock_response = _json_response(search_resp)
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            result = await action.execute(from_address="nobody@example.com")

        assert result["status"] == "success"
        assert result["data"]["num_emails"] == 0
        assert result["data"]["tracked_emails"] == []

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(SearchMessagesAction, "search_messages", credentials={})
        result = await action.execute(from_address="test@test.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            result = await action.execute(from_address="test@test.com")

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"


# ===========================================================================
# GetManagedUrlAction
# ===========================================================================


class TestGetManagedUrlAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetManagedUrlAction, "get_managed_url")

    @pytest.mark.asyncio
    async def test_found(self, action):
        url_list = {
            "data": [
                {"id": "url-abc", "domain": "evil.com", "action": "block"},
                {"id": "url-xyz", "domain": "test.com", "action": "permit"},
            ],
            "meta": {"pagination": {"pageSize": 100}},
            "fail": [],
        }
        mock_response = _json_response(url_list)
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            result = await action.execute(id="url-abc")

        assert result["status"] == "success"
        assert result["data"]["id"] == "url-abc"
        assert result["data"]["domain"] == "evil.com"

    @pytest.mark.asyncio
    async def test_not_found(self, action):
        url_list = {
            "data": [{"id": "url-other", "domain": "other.com"}],
            "meta": {"pagination": {"pageSize": 100}},
            "fail": [],
        }
        mock_response = _json_response(url_list)
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            result = await action.execute(id="nonexistent-url-id")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["id"] == "nonexistent-url-id"

    @pytest.mark.asyncio
    async def test_missing_id(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "id" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetManagedUrlAction, "get_managed_url", credentials={})
        result = await action.execute(id="some-id")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"


# ===========================================================================
# AddManagedUrlAction
# ===========================================================================


class TestAddManagedUrlAction:
    @pytest.fixture
    def action(self):
        return _make_action(AddManagedUrlAction, "add_managed_url")

    @pytest.mark.asyncio
    async def test_success_block(self, action):
        resp = {
            "data": [
                {
                    "id": "new-url-id",
                    "domain": "evil.com",
                    "action": "block",
                    "matchType": "explicit",
                    "scheme": "https",
                }
            ],
            "fail": [],
        }
        mock_response = _json_response(resp)
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            result = await action.execute(url="https://evil.com/phishing")

        assert result["status"] == "success"
        assert result["data"]["id"] == "new-url-id"
        assert result["data"]["action"] == "block"

    @pytest.mark.asyncio
    async def test_default_values_in_payload(self, action):
        mock_response = _json_response({"data": [{}], "fail": []})
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            await action.execute(url="https://evil.com")

        call_kwargs = action.http_request.call_args.kwargs
        url_data = call_kwargs["json_data"]["data"][0]
        assert url_data["action"] == "block"
        assert url_data["matchType"] == "explicit"
        assert url_data["disableLogClick"] is False
        assert url_data["disableRewrite"] is False
        assert url_data["disableUserAwareness"] is False

    @pytest.mark.asyncio
    async def test_custom_options(self, action):
        mock_response = _json_response({"data": [{}], "fail": []})
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            await action.execute(
                url="https://test.com",
                action="permit",
                match_type="domain",
                comment="Safe domain",
                disable_log_click=True,
            )

        call_kwargs = action.http_request.call_args.kwargs
        url_data = call_kwargs["json_data"]["data"][0]
        assert url_data["action"] == "permit"
        assert url_data["matchType"] == "domain"
        assert url_data["comment"] == "Safe domain"
        assert url_data["disableLogClick"] is True

    @pytest.mark.asyncio
    async def test_missing_url(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert "url" in result["error"].lower()
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(AddManagedUrlAction, "add_managed_url", credentials={})
        result = await action.execute(url="https://evil.com")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_api_error(self, action):
        action.http_request = AsyncMock(
            side_effect=_http_status_error(400, "Bad Request")
        )

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            result = await action.execute(url="https://evil.com")

        assert result["status"] == "error"
        assert result["error_type"] == "HTTPStatusError"


# ===========================================================================
# Cross-cutting: result envelope + OAuth2 headers
# ===========================================================================


class TestResultEnvelope:
    """Verify all actions produce the standard result envelope."""

    @pytest.mark.asyncio
    async def test_success_envelope(self):
        action = _make_action(HealthCheckAction, "health_check")
        mock_response = _json_response({"meta": {}, "data": [], "fail": []})
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            result = await action.execute()

        assert "status" in result
        assert "timestamp" in result
        assert "integration_id" in result
        assert "action_id" in result
        assert "data" in result
        assert result["integration_id"] == "mimecast"
        assert result["action_id"] == "health_check"

    @pytest.mark.asyncio
    async def test_error_envelope(self):
        action = _make_action(DecodeUrlAction, "decode_url")
        result = await action.execute()  # Missing url param

        assert "status" in result
        assert "timestamp" in result
        assert "integration_id" in result
        assert "action_id" in result
        assert "error" in result
        assert "error_type" in result
        assert result["status"] == "error"
        assert result["integration_id"] == "mimecast"


class TestOAuth2Integration:
    """Verify OAuth2 token flow is used correctly across actions."""

    @pytest.mark.asyncio
    async def test_token_used_in_authorization_header(self):
        action = _make_action(DecodeUrlAction, "decode_url")
        mock_response = _json_response({"data": [{"url": "decoded"}], "fail": []})
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(
            OAUTH_MODULE, new_callable=AsyncMock, return_value="oauth2-bearer-token"
        ):
            await action.execute(url="https://test.com")

        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "Bearer oauth2-bearer-token"
        assert call_kwargs["headers"]["Content-Type"] == "application/json"
        assert "x-request-id" in call_kwargs["headers"]

    @pytest.mark.asyncio
    async def test_base_url_from_settings(self):
        action = _make_action(
            DecodeUrlAction,
            "decode_url",
            settings={"base_url": "https://eu-api.mimecast.com"},
        )
        mock_response = _json_response({"data": [{"url": "decoded"}], "fail": []})
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            await action.execute(url="https://test.com")

        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["url"].startswith("https://eu-api.mimecast.com")

    @pytest.mark.asyncio
    async def test_timeout_from_settings(self):
        action = _make_action(
            DecodeUrlAction,
            "decode_url",
            settings={"timeout": 60},
        )
        mock_response = _json_response({"data": [{"url": "decoded"}], "fail": []})
        action.http_request = AsyncMock(return_value=mock_response)

        with patch(OAUTH_MODULE, new_callable=AsyncMock, return_value="token"):
            await action.execute(url="https://test.com")

        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["timeout"] == 60
