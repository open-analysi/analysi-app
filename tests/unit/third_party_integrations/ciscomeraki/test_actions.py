"""Unit tests for Cisco Meraki integration actions.

All actions use the base-class ``http_request()`` helper which applies
``integration_retry_policy`` automatically. Tests mock at the
``IntegrationAction.http_request`` level so retry behaviour is transparent.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from analysi.integrations.framework.integrations.ciscomeraki.actions import (
    BlockClientAction,
    GetClientsAction,
    GetDeviceAction,
    HealthCheckAction,
    ListDevicesAction,
    ListNetworksAction,
    UnblockClientAction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_CREDENTIALS = {"api_key": "test-meraki-api-key"}
_DEFAULT_SETTINGS = {"base_url": "https://api.meraki.com", "timeout": 30}


def _make_action(cls, credentials=None, settings=None):
    """Create an action instance with sensible defaults."""
    return cls(
        integration_id="ciscomeraki",
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
            return_value=_json_response([{"id": "123", "name": "Test Org"}])
        )

        result = await action.execute()

        assert result["status"] == "success"
        assert result["integration_id"] == "ciscomeraki"
        assert result["data"]["healthy"] is True
        assert result["data"]["organizations_accessible"] == 1
        action.http_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(HealthCheckAction, credentials={})

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"
        assert result["data"]["healthy"] is False

    @pytest.mark.asyncio
    async def test_api_error(self):
        action = _make_action(HealthCheckAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(401))

        result = await action.execute()

        assert result["status"] == "error"
        assert result["data"]["healthy"] is False

    @pytest.mark.asyncio
    async def test_connection_error(self):
        action = _make_action(HealthCheckAction)
        action.http_request = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = await action.execute()

        assert result["status"] == "error"
        assert result["data"]["healthy"] is False


# ===========================================================================
# ListNetworksAction
# ===========================================================================


class TestListNetworksAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(ListNetworksAction)
        networks = [
            {"id": "N_1", "name": "Office Network"},
            {"id": "N_2", "name": "Guest Network"},
        ]
        action.http_request = AsyncMock(return_value=_json_response(networks))

        result = await action.execute(organization_id="org-123")

        assert result["status"] == "success"
        assert result["data"]["total_networks"] == 2
        assert len(result["data"]["networks"]) == 2
        assert result["integration_id"] == "ciscomeraki"

    @pytest.mark.asyncio
    async def test_uses_default_org_id_from_settings(self):
        action = _make_action(
            ListNetworksAction,
            settings={**_DEFAULT_SETTINGS, "organization_id": "default-org"},
        )
        action.http_request = AsyncMock(return_value=_json_response([]))

        result = await action.execute()

        assert result["status"] == "success"
        # Verify the request used the org from settings
        call_url = action.http_request.call_args.kwargs.get(
            "url", action.http_request.call_args[1].get("url", "")
        )
        assert "default-org" in call_url

    @pytest.mark.asyncio
    async def test_missing_organization_id(self):
        action = _make_action(ListNetworksAction)

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "organization_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(ListNetworksAction, credentials={})

        result = await action.execute(organization_id="org-123")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_not_found_returns_success(self):
        action = _make_action(ListNetworksAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(organization_id="nonexistent")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["total_networks"] == 0


# ===========================================================================
# ListDevicesAction
# ===========================================================================


class TestListDevicesAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(ListDevicesAction)
        devices = [
            {"serial": "Q2XX-1111-2222", "name": "Main AP", "model": "MR42"},
            {"serial": "Q2XX-3333-4444", "name": "Switch", "model": "MS220"},
        ]
        action.http_request = AsyncMock(return_value=_json_response(devices))

        result = await action.execute(network_id="N_123")

        assert result["status"] == "success"
        assert result["data"]["total_devices"] == 2
        assert len(result["data"]["devices"]) == 2

    @pytest.mark.asyncio
    async def test_missing_network_id(self):
        action = _make_action(ListDevicesAction)

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "network_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(ListDevicesAction, credentials={})

        result = await action.execute(network_id="N_123")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_not_found_returns_success(self):
        action = _make_action(ListDevicesAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(network_id="N_bogus")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["total_devices"] == 0

    @pytest.mark.asyncio
    async def test_server_error_propagates(self):
        action = _make_action(ListDevicesAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        result = await action.execute(network_id="N_123")

        assert result["status"] == "error"


# ===========================================================================
# GetDeviceAction
# ===========================================================================


class TestGetDeviceAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(GetDeviceAction)
        device = {
            "serial": "Q2XX-1111-2222",
            "name": "Branch AP",
            "model": "MR42",
            "networkId": "N_123",
            "lanIp": "192.168.1.10",
        }
        action.http_request = AsyncMock(return_value=_json_response(device))

        result = await action.execute(network_id="N_123", serial="Q2XX-1111-2222")

        assert result["status"] == "success"
        assert result["data"]["serial"] == "Q2XX-1111-2222"
        assert result["data"]["model"] == "MR42"

    @pytest.mark.asyncio
    async def test_missing_network_id(self):
        action = _make_action(GetDeviceAction)

        result = await action.execute(serial="Q2XX-1111-2222")

        assert result["status"] == "error"
        assert "network_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_serial(self):
        action = _make_action(GetDeviceAction)

        result = await action.execute(network_id="N_123")

        assert result["status"] == "error"
        assert "serial" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(GetDeviceAction, credentials={})

        result = await action.execute(network_id="N_123", serial="Q2XX-1111-2222")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_not_found_returns_success(self):
        action = _make_action(GetDeviceAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(network_id="N_123", serial="NONEXIST")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["serial"] == "NONEXIST"


# ===========================================================================
# GetClientsAction
# ===========================================================================


class TestGetClientsAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(GetClientsAction)
        clients = [
            {"id": "k12345", "mac": "00:11:22:33:44:55", "description": "Laptop"},
            {"id": "k67890", "mac": "AA:BB:CC:DD:EE:FF", "description": "Phone"},
        ]
        action.http_request = AsyncMock(return_value=_json_response(clients))

        result = await action.execute(serial="Q2XX-1111-2222")

        assert result["status"] == "success"
        assert result["data"]["total_clients"] == 2
        assert len(result["data"]["clients"]) == 2

    @pytest.mark.asyncio
    async def test_with_timespan(self):
        action = _make_action(GetClientsAction)
        action.http_request = AsyncMock(return_value=_json_response([]))

        result = await action.execute(serial="Q2XX-1111-2222", timespan=3600)

        assert result["status"] == "success"
        # Verify timespan was passed in params
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["params"]["timespan"] == 3600

    @pytest.mark.asyncio
    async def test_invalid_timespan_not_integer(self):
        action = _make_action(GetClientsAction)

        result = await action.execute(serial="Q2XX-1111-2222", timespan="not-a-number")

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    @pytest.mark.asyncio
    async def test_timespan_below_minimum(self):
        action = _make_action(GetClientsAction)

        result = await action.execute(serial="Q2XX-1111-2222", timespan=100)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "300" in result["error"]

    @pytest.mark.asyncio
    async def test_timespan_above_maximum(self):
        action = _make_action(GetClientsAction)

        result = await action.execute(serial="Q2XX-1111-2222", timespan=3_000_000)

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "2592000" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_serial(self):
        action = _make_action(GetClientsAction)

        result = await action.execute()

        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"
        assert "serial" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(GetClientsAction, credentials={})

        result = await action.execute(serial="Q2XX-1111-2222")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_not_found_returns_success(self):
        action = _make_action(GetClientsAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(serial="NONEXIST")

        assert result["status"] == "success"
        assert result["not_found"] is True
        assert result["data"]["total_clients"] == 0


# ===========================================================================
# BlockClientAction
# ===========================================================================


class TestBlockClientAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(BlockClientAction)
        policy_response = {"mac": "00:11:22:33:44:55", "devicePolicy": "Blocked"}
        action.http_request = AsyncMock(return_value=_json_response(policy_response))

        result = await action.execute(network_id="N_123", client_id="k12345")

        assert result["status"] == "success"
        assert result["data"]["policy"] == "Blocked"
        assert result["data"]["client_id"] == "k12345"
        assert result["data"]["network_id"] == "N_123"
        # Verify PUT method used
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["method"] == "PUT"
        assert call_kwargs["json_data"]["devicePolicy"] == "Blocked"

    @pytest.mark.asyncio
    async def test_missing_network_id(self):
        action = _make_action(BlockClientAction)

        result = await action.execute(client_id="k12345")

        assert result["status"] == "error"
        assert "network_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_client_id(self):
        action = _make_action(BlockClientAction)

        result = await action.execute(network_id="N_123")

        assert result["status"] == "error"
        assert "client_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(BlockClientAction, credentials={})

        result = await action.execute(network_id="N_123", client_id="k12345")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_not_found_returns_success(self):
        action = _make_action(BlockClientAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(network_id="N_123", client_id="bogus")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_server_error_propagates(self):
        action = _make_action(BlockClientAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        result = await action.execute(network_id="N_123", client_id="k12345")

        assert result["status"] == "error"


# ===========================================================================
# UnblockClientAction
# ===========================================================================


class TestUnblockClientAction:
    @pytest.mark.asyncio
    async def test_success(self):
        action = _make_action(UnblockClientAction)
        policy_response = {"mac": "00:11:22:33:44:55", "devicePolicy": "Normal"}
        action.http_request = AsyncMock(return_value=_json_response(policy_response))

        result = await action.execute(network_id="N_123", client_id="k12345")

        assert result["status"] == "success"
        assert result["data"]["policy"] == "Normal"
        assert result["data"]["client_id"] == "k12345"
        # Verify PUT method with Normal policy
        call_kwargs = action.http_request.call_args.kwargs
        assert call_kwargs["method"] == "PUT"
        assert call_kwargs["json_data"]["devicePolicy"] == "Normal"

    @pytest.mark.asyncio
    async def test_missing_network_id(self):
        action = _make_action(UnblockClientAction)

        result = await action.execute(client_id="k12345")

        assert result["status"] == "error"
        assert "network_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_client_id(self):
        action = _make_action(UnblockClientAction)

        result = await action.execute(network_id="N_123")

        assert result["status"] == "error"
        assert "client_id" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        action = _make_action(UnblockClientAction, credentials={})

        result = await action.execute(network_id="N_123", client_id="k12345")

        assert result["status"] == "error"
        assert result["error_type"] == "ConfigurationError"

    @pytest.mark.asyncio
    async def test_not_found_returns_success(self):
        action = _make_action(UnblockClientAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(404))

        result = await action.execute(network_id="N_123", client_id="bogus")

        assert result["status"] == "success"
        assert result["not_found"] is True

    @pytest.mark.asyncio
    async def test_server_error_propagates(self):
        action = _make_action(UnblockClientAction)
        action.http_request = AsyncMock(side_effect=_http_status_error(500))

        result = await action.execute(network_id="N_123", client_id="k12345")

        assert result["status"] == "error"
