"""
Cisco Meraki network security integration actions.
Uses REST API with API key authentication (X-Cisco-Meraki-API-Key header).
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.integrations.ciscomeraki.constants import (
    API_PATH,
    AUTH_HEADER,
    CLIENT_POLICY,
    CREDENTIAL_API_KEY,
    DEFAULT_BASE_URL,
    DEFAULT_PER_PAGE,
    DEFAULT_TIMEOUT,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    GET_DEVICE,
    LIST_DEVICE_CLIENTS,
    LIST_DEVICES,
    LIST_NETWORKS,
    LIST_ORGANIZATIONS,
    MAX_TIMESPAN,
    MIN_TIMESPAN,
    POLICY_BLOCKED,
    POLICY_NORMAL,
    SETTINGS_BASE_URL,
    SETTINGS_ORGANIZATION_ID,
    SETTINGS_TIMEOUT,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_api_url(base_url: str, endpoint: str) -> str:
    """Build full Meraki API URL from base URL and endpoint path."""
    return f"{base_url.rstrip('/')}{API_PATH}{endpoint}"

# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

class HealthCheckAction(IntegrationAction):
    """Verify Cisco Meraki API connectivity by listing organizations."""

    def get_http_headers(self) -> dict[str, str]:
        api_key = self.credentials.get(CREDENTIAL_API_KEY, "")
        return (
            {AUTH_HEADER: api_key, "Content-Type": "application/json"}
            if api_key
            else {}
        )

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                "Missing required credential: api_key",
                error_type=ERROR_TYPE_CONFIGURATION,
                data={"healthy": False},
            )

        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            url = _build_api_url(base_url, LIST_ORGANIZATIONS)
            response = await self.http_request(url=url, timeout=timeout)
            orgs = response.json()

            return self.success_result(
                data={
                    "healthy": True,
                    "organizations_accessible": len(orgs)
                    if isinstance(orgs, list)
                    else 0,
                }
            )
        except httpx.HTTPStatusError as e:
            self.log_error("health_check_failed", error=e)
            return self.error_result(e, data={"healthy": False})
        except Exception as e:
            self.log_error("health_check_failed", error=e)
            return self.error_result(e, data={"healthy": False})

class ListNetworksAction(IntegrationAction):
    """List all networks in a Meraki organization."""

    def get_http_headers(self) -> dict[str, str]:
        api_key = self.credentials.get(CREDENTIAL_API_KEY, "")
        return (
            {AUTH_HEADER: api_key, "Content-Type": "application/json"}
            if api_key
            else {}
        )

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                "Missing required credential: api_key",
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        organization_id = kwargs.get("organization_id") or self.settings.get(
            SETTINGS_ORGANIZATION_ID
        )
        if not organization_id:
            return self.error_result(
                "Missing required parameter: organization_id",
                error_type=ERROR_TYPE_VALIDATION,
            )

        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            url = _build_api_url(
                base_url,
                LIST_NETWORKS.format(organization_id=organization_id),
            )
            response = await self.http_request(
                url=url,
                params={"perPage": DEFAULT_PER_PAGE},
                timeout=timeout,
            )
            networks = response.json()

            return self.success_result(
                data={
                    "networks": networks if isinstance(networks, list) else [],
                    "total_networks": len(networks)
                    if isinstance(networks, list)
                    else 0,
                }
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "ciscomeraki_list_networks_not_found",
                    organization_id=organization_id,
                )
                return self.success_result(
                    not_found=True,
                    data={
                        "organization_id": organization_id,
                        "networks": [],
                        "total_networks": 0,
                    },
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class ListDevicesAction(IntegrationAction):
    """List all devices in a Meraki network."""

    def get_http_headers(self) -> dict[str, str]:
        api_key = self.credentials.get(CREDENTIAL_API_KEY, "")
        return (
            {AUTH_HEADER: api_key, "Content-Type": "application/json"}
            if api_key
            else {}
        )

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                "Missing required credential: api_key",
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        network_id = kwargs.get("network_id")
        if not network_id:
            return self.error_result(
                "Missing required parameter: network_id",
                error_type=ERROR_TYPE_VALIDATION,
            )

        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            url = _build_api_url(
                base_url,
                LIST_DEVICES.format(network_id=network_id),
            )
            response = await self.http_request(url=url, timeout=timeout)
            devices = response.json()

            return self.success_result(
                data={
                    "devices": devices if isinstance(devices, list) else [],
                    "total_devices": len(devices) if isinstance(devices, list) else 0,
                }
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "ciscomeraki_list_devices_not_found", network_id=network_id
                )
                return self.success_result(
                    not_found=True,
                    data={"network_id": network_id, "devices": [], "total_devices": 0},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class GetDeviceAction(IntegrationAction):
    """Get details for a specific device by serial number."""

    def get_http_headers(self) -> dict[str, str]:
        api_key = self.credentials.get(CREDENTIAL_API_KEY, "")
        return (
            {AUTH_HEADER: api_key, "Content-Type": "application/json"}
            if api_key
            else {}
        )

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                "Missing required credential: api_key",
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        network_id = kwargs.get("network_id")
        serial = kwargs.get("serial")
        if not network_id:
            return self.error_result(
                "Missing required parameter: network_id",
                error_type=ERROR_TYPE_VALIDATION,
            )
        if not serial:
            return self.error_result(
                "Missing required parameter: serial",
                error_type=ERROR_TYPE_VALIDATION,
            )

        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            url = _build_api_url(
                base_url,
                GET_DEVICE.format(network_id=network_id, serial=serial),
            )
            response = await self.http_request(url=url, timeout=timeout)
            device = response.json()

            return self.success_result(data=device)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("ciscomeraki_get_device_not_found", serial=serial)
                return self.success_result(
                    not_found=True,
                    data={"serial": serial, "network_id": network_id},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class GetClientsAction(IntegrationAction):
    """List clients connected to a specific device."""

    def get_http_headers(self) -> dict[str, str]:
        api_key = self.credentials.get(CREDENTIAL_API_KEY, "")
        return (
            {AUTH_HEADER: api_key, "Content-Type": "application/json"}
            if api_key
            else {}
        )

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                "Missing required credential: api_key",
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        serial = kwargs.get("serial")
        if not serial:
            return self.error_result(
                "Missing required parameter: serial",
                error_type=ERROR_TYPE_VALIDATION,
            )

        # Validate optional timespan parameter
        timespan = kwargs.get("timespan")
        if timespan is not None:
            try:
                timespan = int(timespan)
            except (ValueError, TypeError):
                return self.error_result(
                    "Parameter 'timespan' must be a valid integer",
                    error_type=ERROR_TYPE_VALIDATION,
                )
            if not (MIN_TIMESPAN <= timespan <= MAX_TIMESPAN):
                return self.error_result(
                    f"Parameter 'timespan' must be between {MIN_TIMESPAN} and {MAX_TIMESPAN} seconds",
                    error_type=ERROR_TYPE_VALIDATION,
                )

        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            url = _build_api_url(
                base_url,
                LIST_DEVICE_CLIENTS.format(serial=serial),
            )
            params: dict[str, Any] = {}
            if timespan is not None:
                params["timespan"] = timespan

            response = await self.http_request(url=url, params=params, timeout=timeout)
            clients = response.json()

            return self.success_result(
                data={
                    "clients": clients if isinstance(clients, list) else [],
                    "total_clients": len(clients) if isinstance(clients, list) else 0,
                }
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("ciscomeraki_get_clients_not_found", serial=serial)
                return self.success_result(
                    not_found=True,
                    data={"serial": serial, "clients": [], "total_clients": 0},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class BlockClientAction(IntegrationAction):
    """Block a client on a Meraki network by setting its policy to Blocked."""

    def get_http_headers(self) -> dict[str, str]:
        api_key = self.credentials.get(CREDENTIAL_API_KEY, "")
        return (
            {AUTH_HEADER: api_key, "Content-Type": "application/json"}
            if api_key
            else {}
        )

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                "Missing required credential: api_key",
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        network_id = kwargs.get("network_id")
        client_id = kwargs.get("client_id")
        if not network_id:
            return self.error_result(
                "Missing required parameter: network_id",
                error_type=ERROR_TYPE_VALIDATION,
            )
        if not client_id:
            return self.error_result(
                "Missing required parameter: client_id",
                error_type=ERROR_TYPE_VALIDATION,
            )

        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            url = _build_api_url(
                base_url,
                CLIENT_POLICY.format(network_id=network_id, client_id=client_id),
            )
            response = await self.http_request(
                url=url,
                method="PUT",
                json_data={"devicePolicy": POLICY_BLOCKED},
                timeout=timeout,
            )
            result_data = response.json()

            return self.success_result(
                data={
                    "client_id": client_id,
                    "network_id": network_id,
                    "policy": POLICY_BLOCKED,
                    "details": result_data,
                }
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "ciscomeraki_block_client_not_found",
                    client_id=client_id,
                    network_id=network_id,
                )
                return self.success_result(
                    not_found=True,
                    data={"client_id": client_id, "network_id": network_id},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class UnblockClientAction(IntegrationAction):
    """Unblock a client on a Meraki network by setting its policy to Normal."""

    def get_http_headers(self) -> dict[str, str]:
        api_key = self.credentials.get(CREDENTIAL_API_KEY, "")
        return (
            {AUTH_HEADER: api_key, "Content-Type": "application/json"}
            if api_key
            else {}
        )

    async def execute(self, **kwargs) -> dict[str, Any]:
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                "Missing required credential: api_key",
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        network_id = kwargs.get("network_id")
        client_id = kwargs.get("client_id")
        if not network_id:
            return self.error_result(
                "Missing required parameter: network_id",
                error_type=ERROR_TYPE_VALIDATION,
            )
        if not client_id:
            return self.error_result(
                "Missing required parameter: client_id",
                error_type=ERROR_TYPE_VALIDATION,
            )

        base_url = self.settings.get(SETTINGS_BASE_URL, DEFAULT_BASE_URL)
        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            url = _build_api_url(
                base_url,
                CLIENT_POLICY.format(network_id=network_id, client_id=client_id),
            )
            response = await self.http_request(
                url=url,
                method="PUT",
                json_data={"devicePolicy": POLICY_NORMAL},
                timeout=timeout,
            )
            result_data = response.json()

            return self.success_result(
                data={
                    "client_id": client_id,
                    "network_id": network_id,
                    "policy": POLICY_NORMAL,
                    "details": result_data,
                }
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info(
                    "ciscomeraki_unblock_client_not_found",
                    client_id=client_id,
                    network_id=network_id,
                )
                return self.success_result(
                    not_found=True,
                    data={"client_id": client_id, "network_id": network_id},
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)
