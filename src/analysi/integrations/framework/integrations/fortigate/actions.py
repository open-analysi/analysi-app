"""FortiGate Firewall integration actions.

This module provides actions for managing FortiGate Firewall including:
- Health check (test connectivity)
- Block IP (add IP to firewall deny policy)
- Unblock IP (remove IP from deny policy)
- List policies (list firewall IPv4 policies)

FortiGate supports two authentication modes:
1. API Key (Bearer token) -- preferred, stateless
2. Session-based (username/password login with CSRF token)

This migration uses API key auth exclusively via ``get_http_headers()``.
Session-based auth with login/logout/CSRF is intentionally not migrated
because API key auth is the modern and recommended approach for automation.
"""

import ipaddress
import socket
import struct
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ADDRESS_NAME_TEMPLATE,
    BASE_URL_PATH,
    CREDENTIAL_API_KEY,
    DEFAULT_ADDRESS_TYPE,
    DEFAULT_PER_PAGE_LIMIT,
    DEFAULT_POLICY_LIMIT,
    DEFAULT_TIMEOUT,
    ENDPOINT_ADD_ADDRESS,
    ENDPOINT_BANNED_IPS,
    ENDPOINT_GET_ADDRESS,
    ENDPOINT_GET_POLICY,
    ENDPOINT_LIST_POLICIES,
    ENDPOINT_POLICY_ADDRESS,
    ENDPOINT_POLICY_ADDRESS_ENTRY,
    ERR_ADDRESS_NOT_AVAILABLE,
    ERR_INVALID_ADDRESS_TYPE,
    ERR_MISSING_CREDENTIALS,
    ERR_POLICY_NOT_DENY,
    ERR_POLICY_NOT_FOUND,
    ERR_UNEXPECTED_RESPONSE,
    ERROR_TYPE_AUTHENTICATION,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    MSG_HEALTH_CHECK_PASSED,
    MSG_IP_ALREADY_BLOCKED,
    MSG_IP_ALREADY_UNBLOCKED,
    MSG_IP_BLOCKED,
    MSG_IP_UNBLOCKED,
    SETTINGS_TIMEOUT,
    SETTINGS_URL,
    SETTINGS_VDOM,
    SETTINGS_VERIFY_CERT,
    VALID_ADDRESS_TYPES,
)

logger = get_logger(__name__)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_base_url(device_url: str) -> str:
    """Build the base API URL from the device URL.

    Strips trailing slashes and appends the FortiGate API v2 path.
    """
    url = device_url.strip().rstrip("/").rstrip("\\")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return f"{url}{BASE_URL_PATH}"

def _get_net_mask(net_size: int) -> str:
    """Convert CIDR prefix length to dotted-decimal subnet mask."""
    host_bits = 32 - net_size
    return socket.inet_ntoa(struct.pack("!I", (1 << 32) - (1 << host_bits)))

def _get_net_size(net_mask: str) -> int:
    """Convert dotted-decimal subnet mask to CIDR prefix length."""
    octets = net_mask.split(".")
    binary_str = ""
    for octet in octets:
        binary_str += bin(int(octet))[2:].zfill(8)
    return len(binary_str.rstrip("0"))

def _parse_ip_address(ip_addr: str) -> tuple[str, int, str]:
    """Parse IP address string into (ip, net_size, net_mask).

    Supports:
    - Simple IP: 123.123.123.123
    - CIDR notation: 123.123.0.0/16
    - IP + subnet mask: 123.123.0.0 255.255.0.0
    """
    ip_addr = ip_addr.strip()

    if "/" in ip_addr:
        ip, net_size_str = ip_addr.split("/", 1)
        net_size = int(net_size_str) if net_size_str else 32
        net_mask = _get_net_mask(net_size)
    elif " " in ip_addr:
        ip, net_mask = ip_addr.split(None, 1)
        net_size = _get_net_size(net_mask)
    else:
        ip = ip_addr
        net_size = 32
        net_mask = "255.255.255.255"

    return ip, net_size, net_mask

def _validate_ip(ip_addr: str) -> bool:
    """Validate an IP address string."""
    try:
        ip, net_size, _ = _parse_ip_address(ip_addr)
        ipaddress.ip_address(ip)
        return 0 < net_size <= 32
    except (ValueError, TypeError):
        return False

def _build_address_name(ip: str, net_size: int) -> str:
    """Build the FortiGate address object name (matches the upstream convention)."""
    return ADDRESS_NAME_TEMPLATE.format(ip=ip, net_size=net_size)

# ============================================================================
# ACTION CLASSES
# ============================================================================

class _FortiGateBase(IntegrationAction):
    """Shared base for all FortiGate actions.

    Provides API-Key Bearer auth, configurable timeout, and SSL verification.
    """

    def get_http_headers(self) -> dict[str, str]:
        """Return API key Bearer auth header."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY, "")
        if api_key:
            return {"Authorization": f"Bearer {api_key}"}
        return {}

    def get_timeout(self) -> int | float:
        """Return configured timeout."""
        return self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

    def get_verify_ssl(self) -> bool:
        """Return SSL verification setting."""
        return self.settings.get(SETTINGS_VERIFY_CERT, True)

class _FortiGateFirewallBase(_FortiGateBase):
    """Shared helpers for FortiGate firewall policy actions (block/unblock).

    Provides address-existence checks, policy lookup, and address-in-policy
    checks that both BlockIpAction and UnblockIpAction need.
    """

    async def _check_address_exists(
        self,
        base_url: str,
        addr_name: str,
        vdom_params: dict | None,
    ) -> bool:
        """Check if a FortiGate address object exists."""
        try:
            await self.http_request(
                url=f"{base_url}{ENDPOINT_GET_ADDRESS.format(name=addr_name)}",
                params=vdom_params,
            )
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return False
            raise

    async def _get_policy_id(
        self,
        base_url: str,
        policy_name: str,
        vdom: str,
        vdom_params: dict | None,
    ) -> int:
        """Look up a policy by name and return its ID.

        Raises an error if:
        - Policy not found (or multiple with same name)
        - Policy action is not 'deny'
        """
        params = {"key": "name", "pattern": policy_name}
        if vdom_params:
            params.update(vdom_params)

        response = await self.http_request(
            url=f"{base_url}{ENDPOINT_GET_POLICY}",
            params=params,
        )

        resp_json = response.json()
        policies = resp_json.get("results", [])

        if len(policies) != 1:
            raise PolicyError(ERR_POLICY_NOT_FOUND.format(vdom=vdom or "default"))

        policy = policies[0]
        policy_id = policy.get("policyid")
        if not policy_id:
            raise PolicyError(
                f"Unable to find policy ID for given policy name under virtual domain {vdom or 'default'}"
            )

        if policy.get("action") != "deny":
            raise PolicyError(ERR_POLICY_NOT_DENY)

        return policy_id

    async def _is_address_in_policy(
        self,
        base_url: str,
        policy_id: int,
        address_type: str,
        addr_name: str,
        vdom_params: dict | None,
    ) -> bool:
        """Check if an address entry is already in the policy."""
        try:
            response = await self.http_request(
                url=f"{base_url}{ENDPOINT_POLICY_ADDRESS_ENTRY.format(policy_id=policy_id, address_type=address_type, name=addr_name)}",
                params=vdom_params,
            )
            resp_json = response.json()
            return bool(resp_json.get("results"))
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return False
            raise

class HealthCheckAction(_FortiGateBase):
    """Test connectivity to the FortiGate device.

    Validates credentials by querying the banned IPs monitoring endpoint.
    This matches the upstream connector's test_connectivity behavior.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity to FortiGate."""
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                ERR_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        device_url = self.settings.get(SETTINGS_URL)
        if not device_url:
            return self.error_result(
                "Missing required setting: url",
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url = _get_base_url(device_url)
        vdom = self.settings.get(SETTINGS_VDOM, "")
        params = {"vdom": vdom} if vdom else None

        try:
            response = await self.http_request(
                url=f"{base_url}{ENDPOINT_BANNED_IPS}",
                params=params,
            )

            if not response.text:
                return self.error_result(
                    ERR_UNEXPECTED_RESPONSE,
                    error_type=ERROR_TYPE_CONFIGURATION,
                )

            return self.success_result(
                data={"message": MSG_HEALTH_CHECK_PASSED, "healthy": True},
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return self.error_result(
                    "Authentication failed. Check API key.",
                    error_type=ERROR_TYPE_AUTHENTICATION,
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class BlockIpAction(_FortiGateFirewallBase):
    """Block an IP address by adding it to a firewall deny policy.

    This action uses a multi-step approach:
    1. Create an address entry 'Analysi Addr {ip}_{net_bits}' if not present.
    2. Look up the deny policy by name and get its ID.
    3. Add the address entry to the policy's source/destination address list.

    The policy must exist and have action "deny".
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Block an IP address on FortiGate."""
        # Validate required parameters
        ip_addr = kwargs.get("ip")
        if not ip_addr:
            return self.error_result(
                "Missing required parameter: ip",
                error_type=ERROR_TYPE_VALIDATION,
            )

        policy_name = kwargs.get("policy")
        if not policy_name:
            return self.error_result(
                "Missing required parameter: policy",
                error_type=ERROR_TYPE_VALIDATION,
            )

        # Validate credentials
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                ERR_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        device_url = self.settings.get(SETTINGS_URL)
        if not device_url:
            return self.error_result(
                "Missing required setting: url",
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        # Parse and validate IP
        if not _validate_ip(ip_addr):
            return self.error_result(
                f"Invalid IP address format: {ip_addr}",
                error_type=ERROR_TYPE_VALIDATION,
            )

        address_type = kwargs.get("address_type", DEFAULT_ADDRESS_TYPE)
        if address_type not in VALID_ADDRESS_TYPES:
            return self.error_result(
                ERR_INVALID_ADDRESS_TYPE.format(address_type=address_type),
                error_type=ERROR_TYPE_VALIDATION,
            )

        vdom = kwargs.get("vdom") or self.settings.get(SETTINGS_VDOM, "")
        base_url = _get_base_url(device_url)

        try:
            ip, net_size, net_mask = _parse_ip_address(ip_addr)
            addr_name = _build_address_name(ip, net_size)
            vdom_params = {"vdom": vdom} if vdom else None

            # Step 1: Check if address object exists
            addr_exists = await self._check_address_exists(
                base_url, addr_name, vdom_params
            )

            # Step 2: Create address object if it does not exist
            if not addr_exists:
                await self._create_address(
                    base_url, addr_name, ip, net_mask, vdom_params
                )

            # Step 3: Look up policy by name and get ID
            policy_id = await self._get_policy_id(
                base_url, policy_name, vdom, vdom_params
            )

            # Step 4: Check if already blocked
            already_blocked = await self._is_address_in_policy(
                base_url, policy_id, address_type, addr_name, vdom_params
            )
            if already_blocked:
                return self.success_result(
                    data={
                        "message": MSG_IP_ALREADY_BLOCKED,
                        "ip": ip_addr,
                        "policy": policy_name,
                        "address_type": address_type,
                    },
                )

            # Step 5: Add address to policy
            await self.http_request(
                url=f"{base_url}{ENDPOINT_POLICY_ADDRESS.format(policy_id=policy_id, address_type=address_type)}",
                method="POST",
                json_data={"name": addr_name},
                params=vdom_params,
            )

            return self.success_result(
                data={
                    "message": MSG_IP_BLOCKED,
                    "ip": ip_addr,
                    "policy": policy_name,
                    "address_type": address_type,
                    "address_name": addr_name,
                },
            )

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

    async def _create_address(
        self,
        base_url: str,
        addr_name: str,
        ip: str,
        net_mask: str,
        vdom_params: dict | None,
    ) -> None:
        """Create a FortiGate address object."""
        await self.http_request(
            url=f"{base_url}{ENDPOINT_ADD_ADDRESS}",
            method="POST",
            json_data={
                "name": addr_name,
                "type": "ipmask",
                "subnet": f"{ip} {net_mask}",
            },
            params=vdom_params,
        )

class UnblockIpAction(_FortiGateFirewallBase):
    """Unblock an IP address by removing it from a firewall deny policy.

    This action:
    1. Validates the address object exists on the device.
    2. Checks if the address is in the policy's address list.
    3. Removes the address entry from the policy (does NOT delete the address object).
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Unblock an IP address on FortiGate."""
        # Validate required parameters
        ip_addr = kwargs.get("ip")
        if not ip_addr:
            return self.error_result(
                "Missing required parameter: ip",
                error_type=ERROR_TYPE_VALIDATION,
            )

        policy_name = kwargs.get("policy")
        if not policy_name:
            return self.error_result(
                "Missing required parameter: policy",
                error_type=ERROR_TYPE_VALIDATION,
            )

        # Validate credentials
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                ERR_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        device_url = self.settings.get(SETTINGS_URL)
        if not device_url:
            return self.error_result(
                "Missing required setting: url",
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        # Parse and validate IP
        if not _validate_ip(ip_addr):
            return self.error_result(
                f"Invalid IP address format: {ip_addr}",
                error_type=ERROR_TYPE_VALIDATION,
            )

        address_type = kwargs.get("address_type", DEFAULT_ADDRESS_TYPE)
        if address_type not in VALID_ADDRESS_TYPES:
            return self.error_result(
                ERR_INVALID_ADDRESS_TYPE.format(address_type=address_type),
                error_type=ERROR_TYPE_VALIDATION,
            )

        vdom = kwargs.get("vdom") or self.settings.get(SETTINGS_VDOM, "")
        base_url = _get_base_url(device_url)

        try:
            ip, net_size, _ = _parse_ip_address(ip_addr)
            addr_name = _build_address_name(ip, net_size)
            vdom_params = {"vdom": vdom} if vdom else None

            # Step 1: Validate address exists
            addr_exists = await self._check_address_exists(
                base_url, addr_name, vdom_params
            )
            if not addr_exists:
                return self.error_result(
                    ERR_ADDRESS_NOT_AVAILABLE,
                    error_type=ERROR_TYPE_VALIDATION,
                )

            # Step 2: Look up policy
            policy_id = await self._get_policy_id(
                base_url, policy_name, vdom, vdom_params
            )

            # Step 3: Check if address is in the policy
            in_policy = await self._is_address_in_policy(
                base_url, policy_id, address_type, addr_name, vdom_params
            )
            if not in_policy:
                return self.success_result(
                    data={
                        "message": MSG_IP_ALREADY_UNBLOCKED,
                        "ip": ip_addr,
                        "policy": policy_name,
                        "address_type": address_type,
                    },
                )

            # Step 4: Remove address from policy
            await self.http_request(
                url=f"{base_url}{ENDPOINT_POLICY_ADDRESS_ENTRY.format(policy_id=policy_id, address_type=address_type, name=addr_name)}",
                method="DELETE",
                params=vdom_params,
            )

            return self.success_result(
                data={
                    "message": MSG_IP_UNBLOCKED,
                    "ip": ip_addr,
                    "policy": policy_name,
                    "address_type": address_type,
                },
            )

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class ListPoliciesAction(_FortiGateBase):
    """List configured IPv4 firewall policies.

    Supports pagination with a configurable limit and optional
    virtual domain (vdom) filtering.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List firewall policies."""
        # Validate credentials
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return self.error_result(
                ERR_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        device_url = self.settings.get(SETTINGS_URL)
        if not device_url:
            return self.error_result(
                "Missing required setting: url",
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        # Parse limit
        limit = kwargs.get("limit", DEFAULT_POLICY_LIMIT)
        if isinstance(limit, str):
            try:
                limit = int(limit)
            except (ValueError, TypeError):
                return self.error_result(
                    "Please provide a valid integer value in the 'limit' parameter",
                    error_type=ERROR_TYPE_VALIDATION,
                )
        if limit is not None and limit <= 0:
            return self.error_result(
                "Please provide a valid non-zero positive integer value in 'limit' parameter",
                error_type=ERROR_TYPE_VALIDATION,
            )

        vdom = kwargs.get("vdom") or self.settings.get(SETTINGS_VDOM, "")
        base_url = _get_base_url(device_url)

        try:
            policies = await self._paginate_policies(base_url, vdom, limit)

            return self.success_result(
                data={
                    "policies": policies,
                    "total_policies": len(policies),
                },
            )

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

    async def _paginate_policies(
        self,
        base_url: str,
        vdom: str,
        limit: int | None,
    ) -> list[dict[str, Any]]:
        """Fetch policies with pagination."""
        all_policies: list[dict[str, Any]] = []
        skip = 0
        page_size = (
            min(limit, DEFAULT_PER_PAGE_LIMIT) if limit else DEFAULT_PER_PAGE_LIMIT
        )

        while True:
            params: dict[str, Any] = {
                "count": page_size,
                "start": skip,
            }
            if vdom:
                params["vdom"] = vdom

            response = await self.http_request(
                url=f"{base_url}{ENDPOINT_LIST_POLICIES}",
                params=params,
            )

            resp_json = response.json()
            results = resp_json.get("results", [])

            if not results:
                break

            all_policies.extend(results)

            if limit and len(all_policies) >= limit:
                return all_policies[:limit]

            # If fewer results than page size, we've reached the end
            if len(results) < page_size:
                break

            skip += DEFAULT_PER_PAGE_LIMIT

        return all_policies

# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================

class PolicyError(Exception):
    """Raised when a firewall policy lookup fails."""
