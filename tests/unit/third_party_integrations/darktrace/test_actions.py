"""Unit tests for Darktrace integration actions."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.darktrace.actions import (
    AcknowledgeBreachAction,
    GetBreachCommentsAction,
    GetBreachConnectionsAction,
    GetDeviceDescriptionAction,
    GetDeviceModelBreachesAction,
    GetDeviceTagsAction,
    GetTaggedDevicesAction,
    HealthCheckAction,
    PostCommentAction,
    PostTagAction,
    UnacknowledgeBreachAction,
)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

DEFAULT_CREDENTIALS = {
    "public_token": "test-public-token",
    "private_token": "test-private-token",
}

DEFAULT_SETTINGS = {
    "base_url": "https://darktrace.example.com",
    "timeout": 30,
}


def _make_action(cls, credentials=None, settings=None):
    """Create an action instance for testing."""
    return cls(
        integration_id="darktrace",
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
        action.http_request = AsyncMock(
            return_value=_mock_response({"subnets": ["10.0.0.0/8"]})
        )
        result = await action.execute()

        assert result["status"] == "success"
        assert result["data"]["healthy"] is True
        assert "summary_statistics" in result["data"]
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_empty_response(self, action):
        action.http_request = AsyncMock(return_value=_mock_response({}))
        result = await action.execute()

        assert result["status"] == "error"
        assert "empty" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(HealthCheckAction, credentials={})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "public_token" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_base_url(self):
        action = _make_action(HealthCheckAction, settings={"timeout": 30})
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert "base_url" in result["error"]

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
# GET DEVICE DESCRIPTION
# ============================================================================


class TestGetDeviceDescriptionAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetDeviceDescriptionAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        device_data = {
            "data": {
                "devices": {
                    "did": 1234,
                    "ip": "10.0.0.5",
                    "hostname": "workstation-01",
                    "macaddress": "AA:BB:CC:DD:EE:FF",
                    "typename": "Desktop",
                    "devicelabel": "CEO Laptop",
                }
            }
        }
        action.http_request = AsyncMock(return_value=_mock_response(device_data))

        result = await action.execute(device_id=1234)

        assert result["status"] == "success"
        assert result["data"]["data"]["devices"]["did"] == 1234
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_device_id(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "device_id" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_device_id(self, action):
        result = await action.execute(device_id="not_a_number")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "integer" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetDeviceDescriptionAction, credentials={})
        result = await action.execute(device_id=1234)

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))

        result = await action.execute(device_id=9999)

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["device_id"] == 9999

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))

        result = await action.execute(device_id=1234)

        assert result["status"] == "error"


# ============================================================================
# GET DEVICE MODEL BREACHES
# ============================================================================


class TestGetDeviceModelBreachesAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetDeviceModelBreachesAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        summary_data = {
            "data": {
                "modelbreaches": [
                    {
                        "pbid": 100,
                        "score": 80,
                        "time": 1700000000,
                        "acknowledged": False,
                        "model": {"then": {"name": "Test Model"}},
                    },
                    {
                        "pbid": 101,
                        "score": 50,
                        "time": 1700001000,
                        "acknowledged": True,
                        "model": {"then": {"name": "Other Model"}},
                    },
                ]
            }
        }
        action.http_request = AsyncMock(return_value=_mock_response(summary_data))

        result = await action.execute(device_id=1234)

        assert result["status"] == "success"
        assert result["data"]["total"] == 2
        assert len(result["data"]["model_breaches"]) == 2
        assert result["data"]["model_breaches"][0]["pbid"] == 100

    @pytest.mark.asyncio
    async def test_missing_device_id(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetDeviceModelBreachesAction, credentials={})
        result = await action.execute(device_id=1234)

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))

        result = await action.execute(device_id=9999)

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["model_breaches"] == []


# ============================================================================
# GET DEVICE TAGS
# ============================================================================


class TestGetDeviceTagsAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetDeviceTagsAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        tags_data = [
            {"name": "Admin", "tid": 1},
            {"name": "Security Device", "tid": 2},
        ]
        action.http_request = AsyncMock(return_value=_mock_response(tags_data))

        result = await action.execute(device_id=1234)

        assert result["status"] == "success"
        assert len(result["data"]["tags"]) == 2
        assert result["data"]["tags"][0]["name"] == "Admin"
        assert result["data"]["device_id"] == 1234

    @pytest.mark.asyncio
    async def test_missing_device_id(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetDeviceTagsAction, credentials={})
        result = await action.execute(device_id=1234)

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))

        result = await action.execute(device_id=9999)

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["tags"] == []


# ============================================================================
# GET TAGGED DEVICES
# ============================================================================


class TestGetTaggedDevicesAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetTaggedDevicesAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        response_data = {
            "entities": [{"entityValue": "10.0.0.5"}],
            "devices": [
                {
                    "did": 1234,
                    "hostname": "workstation-01",
                    "ip": "10.0.0.5",
                    "macaddress": "AA:BB:CC:DD:EE:FF",
                    "devicelabel": "CEO Laptop",
                }
            ],
        }
        action.http_request = AsyncMock(return_value=_mock_response(response_data))

        result = await action.execute(tag="Admin")

        assert result["status"] == "success"
        assert result["data"]["tag"] == "Admin"
        assert result["data"]["total"] == 1
        assert result["data"]["devices"][0]["did"] == 1234
        assert result["data"]["devices"][0]["hostname"] == "workstation-01"

    @pytest.mark.asyncio
    async def test_missing_tag(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "tag" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetTaggedDevicesAction, credentials={})
        result = await action.execute(tag="Admin")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))

        result = await action.execute(tag="NonExistent")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["devices"] == []


# ============================================================================
# POST TAG
# ============================================================================


class TestPostTagAction:
    @pytest.fixture
    def action(self):
        return _make_action(PostTagAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response({"response": "success"})
        )

        result = await action.execute(device_id=1234, tag="Admin")

        assert result["status"] == "success"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_with_duration(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response({"response": "success"})
        )

        result = await action.execute(device_id=1234, tag="Admin", duration=3600)

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_missing_device_id(self, action):
        result = await action.execute(tag="Admin")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "device_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_tag(self, action):
        result = await action.execute(device_id=1234)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "tag" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(PostTagAction, credentials={})
        result = await action.execute(device_id=1234, tag="Admin")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))

        result = await action.execute(device_id=1234, tag="Admin")

        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_invalid_duration(self, action):
        result = await action.execute(
            device_id=1234, tag="Admin", duration="not_a_number"
        )

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "duration" in result["error"]


# ============================================================================
# POST COMMENT
# ============================================================================


class TestPostCommentAction:
    @pytest.fixture
    def action(self):
        return _make_action(PostCommentAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response({"response": "success", "message": "ok"})
        )

        result = await action.execute(model_breach_id=12345, message="Investigated")

        assert result["status"] == "success"
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_model_breach_id(self, action):
        result = await action.execute(message="Investigated")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "model_breach_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_message(self, action):
        result = await action.execute(model_breach_id=12345)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "message" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(PostCommentAction, credentials={})
        result = await action.execute(model_breach_id=12345, message="Test")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))

        result = await action.execute(model_breach_id=99999, message="Test")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))

        result = await action.execute(model_breach_id=12345, message="Test")

        assert result["status"] == "error"


# ============================================================================
# ACKNOWLEDGE BREACH
# ============================================================================


class TestAcknowledgeBreachAction:
    @pytest.fixture
    def action(self):
        return _make_action(AcknowledgeBreachAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response({"response": "success"})
        )

        result = await action.execute(model_breach_id=12345)

        assert result["status"] == "success"
        assert result["data"]["model_breach_id"] == 12345
        assert result["data"]["acknowledged"] is True
        assert "integration_id" in result

    @pytest.mark.asyncio
    async def test_missing_model_breach_id(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "model_breach_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(AcknowledgeBreachAction, credentials={})
        result = await action.execute(model_breach_id=12345)

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))

        result = await action.execute(model_breach_id=99999)

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))

        result = await action.execute(model_breach_id=12345)

        assert result["status"] == "error"


# ============================================================================
# UNACKNOWLEDGE BREACH
# ============================================================================


class TestUnacknowledgeBreachAction:
    @pytest.fixture
    def action(self):
        return _make_action(UnacknowledgeBreachAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        action.http_request = AsyncMock(
            return_value=_mock_response({"response": "success"})
        )

        result = await action.execute(model_breach_id=12345)

        assert result["status"] == "success"
        assert result["data"]["model_breach_id"] == 12345
        assert result["data"]["acknowledged"] is False

    @pytest.mark.asyncio
    async def test_missing_model_breach_id(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(UnacknowledgeBreachAction, credentials={})
        result = await action.execute(model_breach_id=12345)

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))

        result = await action.execute(model_breach_id=99999)

        assert result["status"] == "success"
        assert result["not_found"] is True


# ============================================================================
# GET BREACH COMMENTS
# ============================================================================


class TestGetBreachCommentsAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetBreachCommentsAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        comments_data = [
            {
                "username": "admin",
                "message": "Investigating",
                "time": 1700000000000,
            },
            {
                "username": "analyst",
                "message": "False positive",
                "time": 1700001000000,
            },
        ]
        action.http_request = AsyncMock(return_value=_mock_response(comments_data))

        result = await action.execute(model_breach_id=12345)

        assert result["status"] == "success"
        assert result["data"]["model_breach_id"] == 12345
        assert result["data"]["total"] == 2
        assert len(result["data"]["comments"]) == 2

    @pytest.mark.asyncio
    async def test_missing_model_breach_id(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetBreachCommentsAction, credentials={})
        result = await action.execute(model_breach_id=12345)

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))

        result = await action.execute(model_breach_id=99999)

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["comments"] == []


# ============================================================================
# GET BREACH CONNECTIONS
# ============================================================================


class TestGetBreachConnectionsAction:
    @pytest.fixture
    def action(self):
        return _make_action(GetBreachConnectionsAction)

    @pytest.mark.asyncio
    async def test_success(self, action):
        connections_data = [
            {
                "action": "connection",
                "time": 1700000000,
                "protocol": "TCP",
                "applicationprotocol": "HTTP",
                "sourceDevice": {"ip": "10.0.0.5", "hostname": "ws-01"},
                "destinationDevice": {"ip": "1.2.3.4", "hostname": "attacker.example"},
                "sourcePort": 55000,
                "destinationPort": 80,
            },
            {
                "action": "connection",
                "time": 1700001000,
                "protocol": "UDP",
                "applicationprotocol": "DNS",
                "sourceDevice": {"ip": "10.0.0.5", "hostname": "ws-01"},
                "destinationDevice": {"ip": "8.8.8.8", "hostname": "dns.google"},
                "sourcePort": 53000,
                "destinationPort": 53,
            },
            {
                "action": "modelbreach",
                "time": 1700000000,
            },
        ]
        action.http_request = AsyncMock(return_value=_mock_response(connections_data))

        result = await action.execute(model_breach_id=12345)

        assert result["status"] == "success"
        assert result["data"]["model_breach_id"] == 12345
        # Should filter out the "modelbreach" action entry
        assert result["data"]["total"] == 2
        conns = result["data"]["connections"]
        assert conns[0]["proto"] == "TCP - HTTP"
        assert conns[0]["src_ip"] == "10.0.0.5"
        assert conns[0]["dest_ip"] == "1.2.3.4"
        assert conns[0]["dest_port"] == 80
        assert conns[1]["proto"] == "UDP - DNS"

    @pytest.mark.asyncio
    async def test_missing_model_breach_id(self, action):
        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        action = _make_action(GetBreachConnectionsAction, credentials={})
        result = await action.execute(model_breach_id=12345)

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_404_not_found(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(404))

        result = await action.execute(model_breach_id=99999)

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["connections"] == []

    @pytest.mark.asyncio
    async def test_http_error(self, action):
        action.http_request = AsyncMock(side_effect=_mock_http_error(500))

        result = await action.execute(model_breach_id=12345)

        assert result["status"] == "error"


# ============================================================================
# HMAC SIGNATURE VERIFICATION
# ============================================================================


class TestDarktraceBaseSignature:
    """Test the HMAC signature generation in _DarktraceBase."""

    @pytest.fixture
    def action(self):
        return _make_action(HealthCheckAction)

    def test_signature_with_params(self, action):
        sig = action._create_signature(
            "/test/endpoint",
            "2026-04-26T00:00:00+00:00",
            query_data={"key": "value"},
        )
        # Should be a 40-char hex string (SHA1 digest)
        assert len(sig) == 40
        assert all(c in "0123456789abcdef" for c in sig)

    def test_signature_without_params(self, action):
        sig = action._create_signature(
            "/test/endpoint",
            "2026-04-26T00:00:00+00:00",
        )
        assert len(sig) == 40

    def test_signature_with_json(self, action):
        sig = action._create_signature(
            "/test/endpoint",
            "2026-04-26T00:00:00+00:00",
            query_data={"message": "hello"},
            is_json=True,
        )
        assert len(sig) == 40

    def test_different_params_produce_different_sigs(self, action):
        sig1 = action._create_signature(
            "/endpoint",
            "2026-04-26T00:00:00+00:00",
            query_data={"key": "value1"},
        )
        sig2 = action._create_signature(
            "/endpoint",
            "2026-04-26T00:00:00+00:00",
            query_data={"key": "value2"},
        )
        assert sig1 != sig2

    def test_build_auth_headers(self, action):
        headers = action._build_auth_headers("/test", {"key": "value"})

        assert "DTAPI-Token" in headers
        assert headers["DTAPI-Token"] == "test-public-token"
        assert "DTAPI-Date" in headers
        assert "DTAPI-Signature" in headers

    def test_build_auth_headers_urlencoded(self, action):
        headers = action._build_auth_headers("/test", {"key": "value"}, urlencoded=True)

        assert "Content-Type" in headers
        assert "urlencoded" in headers["Content-Type"]
