"""Check Point Firewall integration actions.

This module provides actions for managing Check Point Firewall including:
- Health check (test connectivity)
- Block IP (create host/network + access rule to drop traffic)
- Unblock IP (delete access rule for IP/subnet)
- List policies (show configured security policy packages)
- List layers (show access layers)
- List hosts (show host objects)
- Add host / Delete host
- Add network / Delete network
- Update group members
- Install policy
- Add user / Delete user
- Logout session

Check Point uses a session-based management API:
1. POST /login with username/password to get a session ID (sid)
2. Attach the sid as X-chkp-sid header on all subsequent requests
3. Mutating operations require a publish + optional install-policy step
4. POST /logout when done

All actions share the ``_CheckPointBase`` class which handles session
login/logout lifecycle around each ``execute()`` call.
"""

import asyncio
import re
import socket
import struct
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    BASE_URL_PATH,
    CREDENTIAL_PASSWORD,
    CREDENTIAL_USERNAME,
    DEFAULT_TIMEOUT,
    ENDPOINT_ADD_ACCESS_RULE,
    ENDPOINT_ADD_HOST,
    ENDPOINT_ADD_NETWORK,
    ENDPOINT_ADD_USER,
    ENDPOINT_DELETE_ACCESS_RULE,
    ENDPOINT_DELETE_HOST,
    ENDPOINT_DELETE_NETWORK,
    ENDPOINT_DELETE_USER,
    ENDPOINT_INSTALL_POLICY,
    ENDPOINT_LOGIN,
    ENDPOINT_LOGOUT,
    ENDPOINT_PUBLISH,
    ENDPOINT_SET_GROUP,
    ENDPOINT_SHOW_ACCESS_LAYERS,
    ENDPOINT_SHOW_ACCESS_RULEBASE,
    ENDPOINT_SHOW_HOSTS,
    ENDPOINT_SHOW_NETWORKS,
    ENDPOINT_SHOW_PACKAGES,
    ENDPOINT_SHOW_SESSION,
    ENDPOINT_SHOW_TASK,
    ERR_MISSING_CREDENTIALS,
    ERR_NO_IP_ADDRESS,
    ERR_NO_NAME_OR_UID,
    ERR_NO_SUBNET,
    ERR_NO_SUBNET_MASK,
    ERR_NO_VALID_MEMBERS,
    ERR_NO_VALID_TARGETS,
    ERR_PUBLISH_FAILED,
    ERROR_TYPE_AUTHENTICATION,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_PUBLISH,
    ERROR_TYPE_VALIDATION,
    MSG_GROUP_UPDATED,
    MSG_HEALTH_CHECK_PASSED,
    MSG_HOST_ADDED,
    MSG_HOST_DELETED,
    MSG_IP_ALREADY_BLOCKED,
    MSG_IP_BLOCKED,
    MSG_IP_NOT_BLOCKED,
    MSG_IP_UNBLOCKED,
    MSG_NETWORK_ADDED,
    MSG_NETWORK_DELETED,
    MSG_POLICY_INSTALLED,
    MSG_USER_ADDED,
    MSG_USER_DELETED,
    OBJECT_NAME_TEMPLATE,
    PUBLISH_MAX_RETRIES,
    PUBLISH_POLL_INTERVAL,
    SESSION_HEADER,
    SETTINGS_DOMAIN,
    SETTINGS_TIMEOUT,
    SETTINGS_URL,
    SETTINGS_VERIFY_CERT,
)

logger = get_logger(__name__)

# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================

class CheckPointSessionError(Exception):
    """Raised when session login/management fails."""

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_base_url(device_url: str) -> str:
    """Build the base API URL from the management server URL.

    Ensures trailing slash and appends the web_api path.
    """
    url = device_url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return f"{url}/{BASE_URL_PATH}"

def _get_net_size(net_mask: str) -> str:
    """Convert dotted-decimal subnet mask to CIDR prefix length string."""
    octets = net_mask.split(".")
    binary_str = ""
    for octet in octets:
        binary_str += bin(int(octet))[2:].zfill(8)
    return str(len(binary_str.rstrip("0")))

def _get_net_mask(net_size: str) -> str:
    """Convert CIDR prefix length string to dotted-decimal subnet mask."""
    host_bits = 32 - int(net_size)
    return socket.inet_ntoa(struct.pack("!I", (1 << 32) - (1 << host_bits)))

def _break_ip_addr(ip_addr: str) -> tuple[str, str, str]:
    """Parse IP address string into (ip, net_size, net_mask).

    Supports:
    - Simple IP: 123.123.123.123 -> (ip, "32", "255.255.255.255")
    - CIDR notation: 123.123.0.0/16 -> (ip, "16", mask)
    - IP + subnet mask: 123.123.0.0 255.255.0.0 -> (ip, size, mask)
    """
    ip_addr = ip_addr.strip()

    if "/" in ip_addr:
        ip, net_size = ip_addr.split("/", 1)
        net_mask = _get_net_mask(net_size)
    elif " " in ip_addr:
        ip, net_mask = ip_addr.split(None, 1)
        net_size = _get_net_size(net_mask)
    else:
        ip = ip_addr
        net_size = "32"
        net_mask = "255.255.255.255"

    return ip, net_size, net_mask

def _is_valid_ip(ip_addr: str) -> bool:
    """Validate an IP address string with optional subnet.

    Matches the upstream connector's _is_ip validation logic.
    """
    try:
        ip, net_size, net_mask = _break_ip_addr(ip_addr)
    except Exception:
        return False

    # Validate IP octets
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    for part in parts:
        try:
            val = int(part)
            if val < 0 or val > 255:
                return False
        except ValueError:
            return False

    # Validate subnet mask pattern
    subnet_re = re.compile(
        r"^((128|192|224|240|248|252|254)\.0\.0\.0)"
        r"|(255\.(((0|128|192|224|240|248|252|254)\.0\.0)"
        r"|(255\.(((0|128|192|224|240|248|252|254)\.0)"
        r"|255\.(0|128|192|224|240|248|252|254|255)))))$"
    )
    if net_mask and not subnet_re.match(net_mask):
        return False

    if net_size:
        try:
            size_int = int(net_size)
        except (ValueError, TypeError):
            return False
        if not (0 < size_int <= 32):
            return False

    return True

def _parse_comma_list(value: str | None) -> list[str]:
    """Parse a comma-separated string into a cleaned list, filtering empty strings."""
    if not value:
        return []
    items = [x.strip() for x in value.split(",")]
    return list(filter(None, items))

# ============================================================================
# BASE CLASS
# ============================================================================

class _CheckPointBase(IntegrationAction):
    """Shared base for all Check Point actions.

    Manages the session-based authentication lifecycle:
    - Login to get session ID
    - Set X-chkp-sid header on all requests
    - Logout when done

    All POST requests to the Check Point web_api use JSON body
    (``json_data`` parameter in ``self.http_request()``).
    """

    def get_timeout(self) -> int | float:
        """Return configured timeout (default: 60s matching upstream)."""
        return self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

    def get_verify_ssl(self) -> bool:
        """Return SSL verification setting from settings."""
        return self.settings.get(SETTINGS_VERIFY_CERT, False)

    def _validate_credentials(self) -> str | None:
        """Validate required credentials and settings are present.

        Returns an error message if credentials are missing, else None.
        """
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)

        if not url or not username or not password:
            return ERR_MISSING_CREDENTIALS
        return None

    async def _login(self, base_url: str) -> str:
        """Authenticate and return the session ID.

        Raises httpx.HTTPStatusError on failure.
        """
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        domain = self.settings.get(SETTINGS_DOMAIN)

        body: dict[str, str] = {"user": username, "password": password}
        if domain:
            body["domain"] = domain

        response = await self.http_request(
            url=f"{base_url}{ENDPOINT_LOGIN}",
            method="POST",
            json_data=body,
            headers={"content-Type": "application/json"},
        )
        resp_json = response.json()
        sid = resp_json.get("sid")
        if not sid:
            raise CheckPointSessionError("Login succeeded but no session ID returned")
        return sid

    async def _logout(self, base_url: str, sid: str) -> None:
        """Logout the session. Failures are logged but not raised."""
        try:
            await self.http_request(
                url=f"{base_url}{ENDPOINT_LOGOUT}",
                method="POST",
                json_data={},
                headers={
                    "content-Type": "application/json",
                    SESSION_HEADER: sid,
                },
            )
        except Exception as e:
            self.log_warning("checkpoint_logout_failed", error=str(e))

    async def _api_call(
        self, base_url: str, sid: str, endpoint: str, body: dict | None = None
    ) -> dict[str, Any]:
        """Make an authenticated API call to Check Point.

        All Check Point management API calls are POST requests with JSON body.
        Returns the parsed JSON response.
        """
        response = await self.http_request(
            url=f"{base_url}{endpoint}",
            method="POST",
            json_data=body or {},
            headers={
                "content-Type": "application/json",
                SESSION_HEADER: sid,
            },
        )
        return response.json()

    async def _publish_and_wait(self, base_url: str, sid: str) -> bool:
        """Publish session changes and wait for the task to complete.

        Mirrors the upstream connector's _publish_and_wait method:
        - POST to /publish to start the publish task
        - Poll /show-task until status is 'succeeded' or max retries
        """
        resp_json = await self._api_call(base_url, sid, ENDPOINT_PUBLISH)
        task_id = resp_json.get("task-id")
        if not task_id:
            return False

        for _ in range(PUBLISH_MAX_RETRIES):
            await asyncio.sleep(PUBLISH_POLL_INTERVAL)

            try:
                task_resp = await self._api_call(
                    base_url, sid, ENDPOINT_SHOW_TASK, {"task-id": task_id}
                )
            except Exception:
                continue

            tasks = task_resp.get("tasks", [{}])
            if tasks and tasks[0].get("status") == "succeeded":
                return True

        return False

# ============================================================================
# ACTION CLASSES
# ============================================================================

class HealthCheckAction(_CheckPointBase):
    """Test connectivity to the Check Point Management Server.

    Validates credentials by logging in and checking the session.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity to Check Point."""
        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = _get_base_url(self.settings[SETTINGS_URL])

        try:
            sid = await self._login(base_url)

            # Verify the session is valid
            await self._api_call(base_url, sid, ENDPOINT_SHOW_SESSION)

            # Clean up
            await self._logout(base_url, sid)

            return self.success_result(
                data={"message": MSG_HEALTH_CHECK_PASSED, "healthy": True},
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return self.error_result(
                    "Authentication failed. Check username and password.",
                    error_type=ERROR_TYPE_AUTHENTICATION,
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class BlockIpAction(_CheckPointBase):
    """Block an IP/subnet on Check Point Firewall.

    Multi-step process (mirrors upstream connector):
    1. Login to get session ID
    2. Check for existing network object for the IP/subnet
    3. Create the host/network object if it does not exist
    4. Check if a drop rule already exists in the specified layer
    5. Create an access rule at the top of the layer to drop traffic
    6. Publish the session
    7. Optionally install the policy
    8. Logout
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Block an IP address on Check Point."""
        # Validate required parameters
        ip_addr = kwargs.get("ip")
        if not ip_addr:
            return self.error_result(
                "Missing required parameter: ip",
                error_type=ERROR_TYPE_VALIDATION,
            )

        layer = kwargs.get("layer")
        if not layer:
            return self.error_result(
                "Missing required parameter: layer",
                error_type=ERROR_TYPE_VALIDATION,
            )

        policy = kwargs.get("policy")
        if not policy:
            return self.error_result(
                "Missing required parameter: policy",
                error_type=ERROR_TYPE_VALIDATION,
            )

        # Validate credentials
        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        # Validate IP format
        if not _is_valid_ip(ip_addr):
            return self.error_result(
                f"Invalid IP address format: {ip_addr}",
                error_type=ERROR_TYPE_VALIDATION,
            )

        try:
            return await self._block_ip_with_session(kwargs, ip_addr, layer, policy)
        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

    async def _block_ip_with_session(
        self,
        kwargs: dict[str, Any],
        ip_addr: str,
        layer: str,
        policy: str,
    ) -> dict[str, Any]:
        """Execute the block IP workflow within a session."""
        skip_install_policy = kwargs.get("skip_install_policy", False)
        object_name_param = kwargs.get("object_name")

        base_url = _get_base_url(self.settings[SETTINGS_URL])
        ip, net_size, net_mask = _break_ip_addr(ip_addr)
        object_name = OBJECT_NAME_TEMPLATE.format(ip=ip, net_size=net_size)

        sid = await self._login(base_url)

        try:
            # Resolve the object name (create if needed)
            object_name = await self._resolve_object(
                base_url, sid, object_name, ip, net_size, object_name_param
            )

            # Check if rule already exists
            rule_exists = await self._check_for_rule(base_url, sid, object_name, layer)

            if rule_exists is None:
                return self.error_result(
                    "Failed to check existing rules",
                    error_type=ERROR_TYPE_VALIDATION,
                )

            if rule_exists:
                return self.success_result(
                    data={
                        "message": MSG_IP_ALREADY_BLOCKED,
                        "ip": ip_addr,
                        "layer": layer,
                        "policy": policy,
                    },
                )

            # Create the drop rule
            rule_resp = await self._api_call(
                base_url,
                sid,
                ENDPOINT_ADD_ACCESS_RULE,
                {
                    "position": "top",
                    "layer": layer,
                    "action": "Drop",
                    "destination": object_name,
                    "name": object_name,
                },
            )

            # Publish
            if not await self._publish_and_wait(base_url, sid):
                return self.error_result(
                    ERR_PUBLISH_FAILED, error_type=ERROR_TYPE_PUBLISH
                )

            # Optionally install policy
            if not skip_install_policy:
                await self._api_call(
                    base_url, sid, ENDPOINT_INSTALL_POLICY, {"policy-package": policy}
                )

            object_type = "subnet" if net_size != "32" else "IP"

            return self.success_result(
                data={
                    "message": MSG_IP_BLOCKED.format(object_type=object_type),
                    "ip": ip_addr,
                    "layer": layer,
                    "policy": policy,
                    "rule": rule_resp,
                },
            )

        finally:
            await self._logout(base_url, sid)

    async def _resolve_object(
        self,
        base_url: str,
        sid: str,
        object_name: str,
        ip: str,
        net_size: str,
        object_name_param: str | None,
    ) -> str:
        """Resolve or create the network object for the given IP.

        Returns the final object name to use for the access rule.
        """
        existing_name = await self._check_for_object(
            base_url, sid, object_name, ip, net_size
        )

        if existing_name is None:
            raise CheckPointSessionError("Failed to check existing objects")

        if existing_name == object_name:
            return object_name
        if existing_name != "":
            return existing_name
        if object_name_param:
            return object_name_param

        await self._create_object(base_url, sid, object_name, ip, net_size)
        return object_name

    async def _check_for_object(
        self,
        base_url: str,
        sid: str,
        name: str,
        ip: str,
        net_size: str,
    ) -> str | None:
        """Check if a host/network object exists for the given IP.

        Returns:
        - The object name if found (may differ from ``name``)
        - Empty string "" if not found
        - None if an error occurred
        """
        endpoint = ENDPOINT_SHOW_HOSTS if net_size == "32" else ENDPOINT_SHOW_NETWORKS
        body = {"details-level": "full"}

        try:
            resp_json = await self._api_call(base_url, sid, endpoint, body)
        except Exception:
            return None

        for net_obj in resp_json.get("objects", []):
            if name == net_obj.get("name"):
                return name

            if net_size == "32":
                if ip == net_obj.get("ipv4-address"):
                    return net_obj.get("name", "")
            else:
                if ip == net_obj.get("subnet4") and net_size == str(
                    net_obj.get("mask-length4", "")
                ):
                    return net_obj.get("name", "")

        return ""

    async def _check_for_rule(
        self,
        base_url: str,
        sid: str,
        name: str,
        layer: str,
    ) -> bool | None:
        """Check if a rule with the given name exists in the layer.

        Returns True/False or None on error.
        """
        try:
            resp_json = await self._api_call(
                base_url, sid, ENDPOINT_SHOW_ACCESS_RULEBASE, {"name": layer}
            )
        except Exception:
            return None

        return any(name == rule.get("name") for rule in resp_json.get("rulebase", []))

    async def _create_object(
        self,
        base_url: str,
        sid: str,
        name: str,
        ip: str,
        net_size: str,
    ) -> dict[str, Any]:
        """Create a host or network object."""
        body: dict[str, Any] = {"name": name}

        if net_size == "32":
            endpoint = ENDPOINT_ADD_HOST
            body["ip-address"] = ip
        else:
            endpoint = ENDPOINT_ADD_NETWORK
            body["subnet"] = ip
            body["mask-length"] = net_size

        return await self._api_call(base_url, sid, endpoint, body)

class UnblockIpAction(_CheckPointBase):
    """Unblock an IP/subnet on Check Point Firewall.

    Multi-step process (mirrors upstream connector):
    1. Login to get session ID
    2. Check if a drop rule exists for the IP in the specified layer
    3. Delete the access rule if it exists
    4. Publish the session
    5. Install the policy
    6. Logout
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Unblock an IP address on Check Point."""
        # Validate required parameters
        ip_addr = kwargs.get("ip")
        if not ip_addr:
            return self.error_result(
                "Missing required parameter: ip",
                error_type=ERROR_TYPE_VALIDATION,
            )

        layer = kwargs.get("layer")
        if not layer:
            return self.error_result(
                "Missing required parameter: layer",
                error_type=ERROR_TYPE_VALIDATION,
            )

        policy = kwargs.get("policy")
        if not policy:
            return self.error_result(
                "Missing required parameter: policy",
                error_type=ERROR_TYPE_VALIDATION,
            )

        # Validate credentials
        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        # Validate IP
        if not _is_valid_ip(ip_addr):
            return self.error_result(
                f"Invalid IP address format: {ip_addr}",
                error_type=ERROR_TYPE_VALIDATION,
            )

        base_url = _get_base_url(self.settings[SETTINGS_URL])

        try:
            ip, net_size, net_mask = _break_ip_addr(ip_addr)
            object_name = OBJECT_NAME_TEMPLATE.format(ip=ip, net_size=net_size)

            sid = await self._login(base_url)

            try:
                # Check if rule exists
                rule_exists = await self._check_for_rule(
                    base_url, sid, object_name, layer
                )

                if rule_exists is None:
                    return self.error_result(
                        "Failed to check existing rules",
                        error_type=ERROR_TYPE_VALIDATION,
                    )

                if not rule_exists:
                    return self.success_result(
                        data={
                            "message": MSG_IP_NOT_BLOCKED,
                            "ip": ip_addr,
                            "layer": layer,
                            "policy": policy,
                        },
                    )

                # Delete the rule
                delete_resp = await self._api_call(
                    base_url,
                    sid,
                    ENDPOINT_DELETE_ACCESS_RULE,
                    {"layer": layer, "name": object_name},
                )

                # Publish
                if not await self._publish_and_wait(base_url, sid):
                    return self.error_result(
                        ERR_PUBLISH_FAILED,
                        error_type=ERROR_TYPE_PUBLISH,
                    )

                # Install policy
                await self._api_call(
                    base_url,
                    sid,
                    ENDPOINT_INSTALL_POLICY,
                    {"policy-package": policy},
                )

                object_type = "subnet" if net_size != "32" else "IP"

                return self.success_result(
                    data={
                        "message": MSG_IP_UNBLOCKED.format(object_type=object_type),
                        "ip": ip_addr,
                        "layer": layer,
                        "policy": policy,
                        "rule": delete_resp,
                    },
                )

            finally:
                await self._logout(base_url, sid)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

    async def _check_for_rule(
        self,
        base_url: str,
        sid: str,
        name: str,
        layer: str,
    ) -> bool | None:
        """Check if a rule exists. Returns True/False or None on error."""
        try:
            resp_json = await self._api_call(
                base_url, sid, ENDPOINT_SHOW_ACCESS_RULEBASE, {"name": layer}
            )
        except Exception:
            return None

        return any(name == rule.get("name") for rule in resp_json.get("rulebase", []))

class ListPoliciesAction(_CheckPointBase):
    """List security policy packages on Check Point."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List policy packages."""
        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = _get_base_url(self.settings[SETTINGS_URL])

        try:
            sid = await self._login(base_url)

            try:
                resp_json = await self._api_call(base_url, sid, ENDPOINT_SHOW_PACKAGES)

                packages = resp_json.get("packages", [])

                return self.success_result(
                    data={
                        "packages": packages,
                        "total_packages": len(packages),
                        "raw_response": resp_json,
                    },
                )

            finally:
                await self._logout(base_url, sid)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class ListLayersAction(_CheckPointBase):
    """List access layers on Check Point."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List access layers."""
        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = _get_base_url(self.settings[SETTINGS_URL])

        try:
            sid = await self._login(base_url)

            try:
                resp_json = await self._api_call(
                    base_url, sid, ENDPOINT_SHOW_ACCESS_LAYERS
                )

                layers = resp_json.get("access-layers", [])

                return self.success_result(
                    data={
                        "access_layers": layers,
                        "total_layers": len(layers),
                        "raw_response": resp_json,
                    },
                )

            finally:
                await self._logout(base_url, sid)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class ListHostsAction(_CheckPointBase):
    """List host objects on Check Point."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List host objects."""
        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = _get_base_url(self.settings[SETTINGS_URL])

        try:
            sid = await self._login(base_url)

            try:
                resp_json = await self._api_call(base_url, sid, ENDPOINT_SHOW_HOSTS)

                total = resp_json.get("total", 0)
                objects = resp_json.get("objects", [])

                return self.success_result(
                    data={
                        "hosts": objects,
                        "total_hosts": total,
                        "raw_response": resp_json,
                    },
                )

            finally:
                await self._logout(base_url, sid)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class AddHostAction(_CheckPointBase):
    """Add a host object on Check Point.

    Supports IPv4 and/or IPv6 addresses. The ``ip`` parameter is used first;
    if both IPv4 and IPv6 are needed, use ``ipv4`` and ``ipv6`` explicitly.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Add a host object."""
        name = kwargs.get("name")
        if not name:
            return self.error_result(
                "Missing required parameter: name",
                error_type=ERROR_TYPE_VALIDATION,
            )

        ip = kwargs.get("ip")
        ipv4 = kwargs.get("ipv4")
        ipv6 = kwargs.get("ipv6")
        comments = kwargs.get("comments")
        groups = kwargs.get("groups")

        if not ip and not ipv4 and not ipv6:
            return self.error_result(
                ERR_NO_IP_ADDRESS,
                error_type=ERROR_TYPE_VALIDATION,
            )

        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = _get_base_url(self.settings[SETTINGS_URL])

        try:
            sid = await self._login(base_url)

            try:
                body: dict[str, Any] = {"name": name}

                if comments:
                    body["comments"] = comments

                if groups:
                    groups_list = _parse_comma_list(groups)
                    if groups_list:
                        body["groups"] = groups_list

                if ip:
                    body["ip-address"] = ip
                elif ipv4 and ipv6:
                    body["ipv4-address"] = ipv4
                    body["ipv6-address"] = ipv6
                elif ipv4:
                    body["ipv4-address"] = ipv4
                elif ipv6:
                    body["ipv6-address"] = ipv6

                resp_json = await self._api_call(base_url, sid, ENDPOINT_ADD_HOST, body)

                if not await self._publish_and_wait(base_url, sid):
                    return self.error_result(
                        ERR_PUBLISH_FAILED,
                        error_type=ERROR_TYPE_PUBLISH,
                    )

                return self.success_result(
                    data={
                        "message": MSG_HOST_ADDED,
                        "host": resp_json,
                    },
                )

            finally:
                await self._logout(base_url, sid)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class DeleteHostAction(_CheckPointBase):
    """Delete a host object on Check Point.

    Specify either ``uid`` or ``name``. UID takes priority.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Delete a host object."""
        name = kwargs.get("name")
        uid = kwargs.get("uid")

        if not name and not uid:
            return self.error_result(
                ERR_NO_NAME_OR_UID,
                error_type=ERROR_TYPE_VALIDATION,
            )

        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = _get_base_url(self.settings[SETTINGS_URL])

        try:
            sid = await self._login(base_url)

            try:
                body = {"uid": uid} if uid else {"name": name}

                resp_json = await self._api_call(
                    base_url, sid, ENDPOINT_DELETE_HOST, body
                )

                if not await self._publish_and_wait(base_url, sid):
                    return self.error_result(
                        ERR_PUBLISH_FAILED,
                        error_type=ERROR_TYPE_PUBLISH,
                    )

                return self.success_result(
                    data={
                        "message": MSG_HOST_DELETED,
                        "result": resp_json,
                    },
                )

            finally:
                await self._logout(base_url, sid)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class AddNetworkAction(_CheckPointBase):
    """Add a network object on Check Point.

    Requires at least one subnet parameter and a mask length or mask.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Add a network object."""
        name = kwargs.get("name")
        if not name:
            return self.error_result(
                "Missing required parameter: name",
                error_type=ERROR_TYPE_VALIDATION,
            )

        # Validate subnet provided
        if (
            not kwargs.get("subnet")
            and not kwargs.get("subnet_v4")
            and not kwargs.get("subnet_v6")
        ):
            return self.error_result(ERR_NO_SUBNET, error_type=ERROR_TYPE_VALIDATION)

        # Validate mask provided
        if not any(
            [
                kwargs.get("subnet_mask_length"),
                kwargs.get("subnet_mask_length_v4"),
                kwargs.get("subnet_mask_length_v6"),
                kwargs.get("subnet_mask"),
            ]
        ):
            return self.error_result(
                ERR_NO_SUBNET_MASK, error_type=ERROR_TYPE_VALIDATION
            )

        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = _get_base_url(self.settings[SETTINGS_URL])

        try:
            sid = await self._login(base_url)

            try:
                body = self._build_network_body(name, kwargs)

                resp_json = await self._api_call(
                    base_url, sid, ENDPOINT_ADD_NETWORK, body
                )

                if not await self._publish_and_wait(base_url, sid):
                    return self.error_result(
                        ERR_PUBLISH_FAILED,
                        error_type=ERROR_TYPE_PUBLISH,
                    )

                return self.success_result(
                    data={
                        "message": MSG_NETWORK_ADDED,
                        "network": resp_json,
                    },
                )

            finally:
                await self._logout(base_url, sid)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

    @staticmethod
    def _build_network_body(name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Build the API request body for add-network."""
        body: dict[str, Any] = {"name": name}

        comments = kwargs.get("comments")
        groups = kwargs.get("groups")
        if comments:
            body["comments"] = comments
        if groups:
            groups_list = _parse_comma_list(groups)
            if groups_list:
                body["groups"] = groups_list

        # Subnet
        subnet = kwargs.get("subnet")
        subnet_v4 = kwargs.get("subnet_v4")
        subnet_v6 = kwargs.get("subnet_v6")
        if subnet:
            body["subnet"] = subnet
        elif subnet_v4 and subnet_v6:
            body["subnet4"] = subnet_v4
            body["subnet6"] = subnet_v6
        elif subnet_v4:
            body["subnet4"] = subnet_v4
        elif subnet_v6:
            body["subnet6"] = subnet_v6

        # Mask
        mask_len = kwargs.get("subnet_mask_length")
        mask_v4 = kwargs.get("subnet_mask_length_v4")
        mask_v6 = kwargs.get("subnet_mask_length_v6")
        subnet_mask = kwargs.get("subnet_mask")
        if mask_len:
            body["mask-length"] = mask_len
        elif mask_v4 and mask_v6:
            body["mask-length4"] = mask_v4
            body["mask-length6"] = mask_v6
        elif mask_v4:
            body["mask-length4"] = mask_v4
        elif mask_v6:
            body["mask-length6"] = mask_v6
        elif subnet_mask:
            body["subnet-mask"] = subnet_mask

        return body

class DeleteNetworkAction(_CheckPointBase):
    """Delete a network object on Check Point.

    Specify either ``uid`` or ``name``. UID takes priority.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Delete a network object."""
        name = kwargs.get("name")
        uid = kwargs.get("uid")

        if not name and not uid:
            return self.error_result(
                ERR_NO_NAME_OR_UID,
                error_type=ERROR_TYPE_VALIDATION,
            )

        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = _get_base_url(self.settings[SETTINGS_URL])

        try:
            sid = await self._login(base_url)

            try:
                body = {"uid": uid} if uid else {"name": name}

                resp_json = await self._api_call(
                    base_url, sid, ENDPOINT_DELETE_NETWORK, body
                )

                if not await self._publish_and_wait(base_url, sid):
                    return self.error_result(
                        ERR_PUBLISH_FAILED,
                        error_type=ERROR_TYPE_PUBLISH,
                    )

                return self.success_result(
                    data={
                        "message": MSG_NETWORK_DELETED,
                        "result": resp_json,
                    },
                )

            finally:
                await self._logout(base_url, sid)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class UpdateGroupMembersAction(_CheckPointBase):
    """Update group members on Check Point.

    The ``action`` parameter determines whether to add, remove, or set members.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Update group members."""
        name = kwargs.get("name")
        uid = kwargs.get("uid")
        members = kwargs.get("members")
        action = kwargs.get("action")

        if not name and not uid:
            return self.error_result(
                ERR_NO_NAME_OR_UID,
                error_type=ERROR_TYPE_VALIDATION,
            )

        if not members:
            return self.error_result(
                "Missing required parameter: members",
                error_type=ERROR_TYPE_VALIDATION,
            )

        if not action:
            return self.error_result(
                "Missing required parameter: action",
                error_type=ERROR_TYPE_VALIDATION,
            )

        members_list = _parse_comma_list(members)
        if not members_list:
            return self.error_result(
                ERR_NO_VALID_MEMBERS,
                error_type=ERROR_TYPE_VALIDATION,
            )

        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = _get_base_url(self.settings[SETTINGS_URL])

        try:
            sid = await self._login(base_url)

            try:
                # Build members payload matching upstream logic
                if action in ("add", "remove"):
                    members_object = {action: members_list}
                else:
                    members_object = members_list

                body: dict[str, Any] = {"members": members_object}
                if uid:
                    body["uid"] = uid
                else:
                    body["name"] = name

                resp_json = await self._api_call(
                    base_url, sid, ENDPOINT_SET_GROUP, body
                )

                if not await self._publish_and_wait(base_url, sid):
                    return self.error_result(
                        ERR_PUBLISH_FAILED,
                        error_type=ERROR_TYPE_PUBLISH,
                    )

                return self.success_result(
                    data={
                        "message": MSG_GROUP_UPDATED,
                        "group": resp_json,
                    },
                )

            finally:
                await self._logout(base_url, sid)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class InstallPolicyAction(_CheckPointBase):
    """Install a policy package to target gateways on Check Point."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Install a policy package."""
        policy = kwargs.get("policy")
        if not policy:
            return self.error_result(
                "Missing required parameter: policy",
                error_type=ERROR_TYPE_VALIDATION,
            )

        targets = kwargs.get("targets")
        if not targets:
            return self.error_result(
                "Missing required parameter: targets",
                error_type=ERROR_TYPE_VALIDATION,
            )

        access = kwargs.get("access")

        targets_list = _parse_comma_list(targets)
        if not targets_list:
            return self.error_result(
                ERR_NO_VALID_TARGETS,
                error_type=ERROR_TYPE_VALIDATION,
            )

        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = _get_base_url(self.settings[SETTINGS_URL])

        try:
            sid = await self._login(base_url)

            try:
                body: dict[str, Any] = {
                    "policy-package": policy,
                    "targets": targets_list,
                }
                if access:
                    body["access"] = access

                resp_json = await self._api_call(
                    base_url, sid, ENDPOINT_INSTALL_POLICY, body
                )

                return self.success_result(
                    data={
                        "message": MSG_POLICY_INSTALLED,
                        "result": resp_json,
                    },
                )

            finally:
                await self._logout(base_url, sid)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class AddUserAction(_CheckPointBase):
    """Add a user on Check Point."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Add a user."""
        name = kwargs.get("name")
        if not name:
            return self.error_result(
                "Missing required parameter: name",
                error_type=ERROR_TYPE_VALIDATION,
            )

        template = kwargs.get("template")
        if not template:
            return self.error_result(
                "Missing required parameter: template",
                error_type=ERROR_TYPE_VALIDATION,
            )

        email = kwargs.get("email")
        phone_number = kwargs.get("phone_number")
        comments = kwargs.get("comments")

        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = _get_base_url(self.settings[SETTINGS_URL])

        try:
            sid = await self._login(base_url)

            try:
                body: dict[str, Any] = {"name": name, "template": template}
                if email:
                    body["email"] = email
                if phone_number:
                    body["phone-number"] = phone_number
                if comments:
                    body["comments"] = comments

                resp_json = await self._api_call(base_url, sid, ENDPOINT_ADD_USER, body)

                if not await self._publish_and_wait(base_url, sid):
                    return self.error_result(
                        ERR_PUBLISH_FAILED,
                        error_type=ERROR_TYPE_PUBLISH,
                    )

                return self.success_result(
                    data={
                        "message": MSG_USER_ADDED,
                        "user": resp_json,
                    },
                )

            finally:
                await self._logout(base_url, sid)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class DeleteUserAction(_CheckPointBase):
    """Delete a user on Check Point.

    Specify either ``uid`` or ``name``. UID takes priority.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Delete a user."""
        name = kwargs.get("name")
        uid = kwargs.get("uid")

        if not name and not uid:
            return self.error_result(
                ERR_NO_NAME_OR_UID,
                error_type=ERROR_TYPE_VALIDATION,
            )

        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = _get_base_url(self.settings[SETTINGS_URL])

        try:
            sid = await self._login(base_url)

            try:
                body = {"uid": uid} if uid else {"name": name}

                resp_json = await self._api_call(
                    base_url, sid, ENDPOINT_DELETE_USER, body
                )

                if not await self._publish_and_wait(base_url, sid):
                    return self.error_result(
                        ERR_PUBLISH_FAILED,
                        error_type=ERROR_TYPE_PUBLISH,
                    )

                return self.success_result(
                    data={
                        "message": MSG_USER_DELETED,
                        "result": resp_json,
                    },
                )

            finally:
                await self._logout(base_url, sid)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class LogoutSessionAction(_CheckPointBase):
    """Logout a specific session or the current session on Check Point."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Logout a session."""
        session_id = kwargs.get("session_id")

        cred_error = self._validate_credentials()
        if cred_error:
            return self.error_result(cred_error, error_type=ERROR_TYPE_CONFIGURATION)

        base_url = _get_base_url(self.settings[SETTINGS_URL])

        try:
            sid = await self._login(base_url)

            # Logout the specified session (or current if not specified)
            target_sid = session_id if session_id else sid

            try:
                await self.http_request(
                    url=f"{base_url}{ENDPOINT_LOGOUT}",
                    method="POST",
                    json_data={},
                    headers={
                        "content-Type": "application/json",
                        SESSION_HEADER: target_sid,
                    },
                )

                return self.success_result(
                    data={
                        "message": "Successfully logged out of session",
                        "session_id": target_sid,
                    },
                )

            finally:
                # If we logged out a different session, clean up our own
                if session_id and session_id != sid:
                    await self._logout(base_url, sid)

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)
