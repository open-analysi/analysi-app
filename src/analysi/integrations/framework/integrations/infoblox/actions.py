"""Infoblox DDI integration actions.

This module provides actions for managing Infoblox Grid Manager DNS/DHCP/IPAM:
- Health check (test connectivity)
- Block IP (add IP to RPZ as No Such Domain rule)
- Unblock IP (remove IP from RPZ)
- Block domain (add domain to RPZ as No Such Domain rule)
- Unblock domain (remove domain from RPZ)
- List RPZ (list Response Policy Zones)
- List hosts (list DNS A/AAAA records)
- List network view (list available network views)
- Get network info (get network ranges)
- Get system info (get lease/host info for IP/hostname)

Infoblox uses HTTP basic auth with session cookies. The connector authenticates
with username/password via basic auth on the first request, and subsequent
requests use the session cookie set by the server. This migration uses
basic auth on every request via get_http_headers() for stateless operation.
"""

import ipaddress
import socket
from datetime import UTC, datetime
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    BASE_ENDPOINT,
    BLOCK_POLICY_RULE,
    CREDENTIAL_PASSWORD,
    CREDENTIAL_USERNAME,
    DEFAULT_MAX_RESULTS,
    DEFAULT_NETWORK_VIEW,
    DEFAULT_TIMEOUT,
    ENDPOINT_DOMAIN_RPZ,
    ENDPOINT_IP_RPZ,
    ENDPOINT_LEASE,
    ENDPOINT_NETWORK,
    ENDPOINT_NETWORK_VIEW,
    ENDPOINT_RECORDS_IPV4,
    ENDPOINT_RECORDS_IPV6,
    ENDPOINT_RP_ZONE_DETAILS,
    ENDPOINT_SCHEMA,
    ERR_DOMAIN_EXISTS_NOT_BLOCKED,
    ERR_DOMAIN_NOT_BLOCKED,
    ERR_IP_EXISTS_NOT_BLOCKED,
    ERR_IP_NOT_BLOCKED,
    ERR_MISSING_CREDENTIALS,
    ERR_RPZ_NOT_EXISTS,
    ERR_RPZ_POLICY_RULE,
    ERROR_TYPE_AUTHENTICATION,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    LEASE_RETURN_FIELDS,
    LIST_HOSTS_RETURN_FIELDS_V4,
    LIST_HOSTS_RETURN_FIELDS_V6,
    LIST_RP_ZONE_RETURN_FIELDS,
    MSG_DOMAIN_ALREADY_BLOCKED,
    MSG_DOMAIN_ALREADY_UNBLOCKED,
    MSG_DOMAIN_BLOCKED,
    MSG_DOMAIN_UNBLOCKED,
    MSG_HEALTH_CHECK_PASSED,
    MSG_IP_ALREADY_BLOCKED,
    MSG_IP_ALREADY_UNBLOCKED,
    MSG_IP_BLOCKED,
    MSG_IP_UNBLOCKED,
    RECORD_A_RETURN_FIELDS,
    RECORD_AAAA_RETURN_FIELDS,
    SETTINGS_TIMEOUT,
    SETTINGS_URL,
    SETTINGS_VERIFY_CERT,
)

logger = get_logger(__name__)

# Date format
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _build_api_url(device_url: str, endpoint: str) -> str:
    """Build the full API URL from device URL and endpoint."""
    url = device_url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    return f"{url}{BASE_ENDPOINT}{endpoint}"

def _is_ipv6(address: str) -> bool:
    """Check if the given address is a valid IPv6 address."""
    try:
        socket.inet_pton(socket.AF_INET6, address)
        return True
    except OSError:
        return False

def _is_ipv4(address: str) -> bool:
    """Check if the given address is a valid IPv4 address."""
    try:
        socket.inet_pton(socket.AF_INET, address)
        return True
    except OSError:
        return False

def _is_ip(address: str) -> bool:
    """Check if the given address is a valid IPv4 or IPv6 address."""
    return _is_ipv4(address) or _is_ipv6(address)

def _validate_ip_cidr(cidr_ip: str) -> bool:
    """Validate an IP address optionally with CIDR notation.

    Supports:
    - Simple IP: 10.0.0.1
    - CIDR: 10.0.0.0/24
    - IPv6: 2001:db8::1
    - IPv6 CIDR: 2001:db8::/32
    """
    try:
        if "/" not in cidr_ip:
            # Bare IP address -- just validate it
            return _is_ipv4(cidr_ip) or _is_ipv6(cidr_ip)

        ip_str, prefix_str = cidr_ip.split("/", 1)
        prefix = int(prefix_str)

        if not (_is_ipv4(ip_str) or _is_ipv6(ip_str)):
            return False

        if ":" in ip_str:
            return 0 <= prefix <= 128
        return 0 <= prefix <= 32
    except (ValueError, TypeError):
        return False

def _encode_domain(domain: str) -> str:
    """Encode domain name to IDNA format if applicable."""
    try:
        return domain.encode("idna").decode("utf-8")
    except (UnicodeError, UnicodeDecodeError):
        return domain

def _epoch_to_str(epoch: int | float) -> str:
    """Convert epoch seconds to a UTC formatted date string."""
    return datetime.fromtimestamp(epoch, tz=UTC).strftime(_DATE_FORMAT)

# ============================================================================
# BASE CLASS
# ============================================================================

class _InfobloxBase(IntegrationAction):
    """Shared base for all Infoblox DDI actions.

    Provides HTTP basic auth via username/password, configurable timeout,
    and SSL verification.
    """

    def get_http_headers(self) -> dict[str, str]:
        """Return empty headers; auth is handled via httpx auth parameter."""
        return {}

    def get_timeout(self) -> int | float:
        """Return configured timeout."""
        return self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

    def get_verify_ssl(self) -> bool:
        """Return SSL verification setting."""
        return self.settings.get(SETTINGS_VERIFY_CERT, False)

    def _validate_credentials(self) -> tuple[str, str, str] | None:
        """Validate and return (url, username, password) or None if missing."""
        url = self.settings.get(SETTINGS_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        if url and username and password:
            return url, username, password
        return None

    async def _infoblox_request(
        self,
        endpoint: str,
        device_url: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Make a request to the Infoblox WAPI.

        Uses HTTP basic auth via the ``auth`` parameter supported by
        ``self.http_request()`` from the framework base class.
        """
        url = _build_api_url(device_url, endpoint)
        username = self.credentials.get(CREDENTIAL_USERNAME, "")
        password = self.credentials.get(CREDENTIAL_PASSWORD, "")

        kwargs: dict[str, Any] = {
            "url": url,
            "auth": (username, password),
        }
        if method != "GET":
            kwargs["method"] = method
        if params:
            kwargs["params"] = params
        if data:
            kwargs["json_data"] = data

        return await self.http_request(**kwargs)

    async def _paged_request(
        self,
        endpoint: str,
        device_url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Make paged GET requests to Infoblox WAPI.

        Infoblox returns results with ``next_page_id`` for pagination.
        """
        if params is None:
            params = {}

        params["_paging"] = 1
        params["_return_as_object"] = 1
        params["_max_results"] = DEFAULT_MAX_RESULTS

        response = await self._infoblox_request(endpoint, device_url, params=params)
        resp_json = response.json()

        combined = resp_json.get("result", [])
        next_page_id = resp_json.get("next_page_id")

        while next_page_id:
            page_params = {
                "_page_id": next_page_id,
                "_paging": 1,
                "_return_as_object": 1,
            }
            response = await self._infoblox_request(
                endpoint, device_url, params=page_params
            )
            resp_json = response.json()
            combined.extend(resp_json.get("result", []))
            next_page_id = resp_json.get("next_page_id")

        return combined

# ============================================================================
# RPZ BASE CLASS
# ============================================================================

class _InfobloxRpzBase(_InfobloxBase):
    """Shared helpers for RPZ block/unblock actions.

    Provides RPZ validation and rule lookup logic.
    """

    async def _get_rpz_details(
        self, device_url: str, zone_params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Get Response Policy Zone details."""
        zone_params["_return_fields"] = LIST_RP_ZONE_RETURN_FIELDS
        return await self._paged_request(
            ENDPOINT_RP_ZONE_DETAILS, device_url, params=zone_params
        )

    async def _validate_rpz(self, device_url: str, fqdn: str, view: str) -> str | None:
        """Validate that RPZ exists and has GIVEN policy.

        Returns None on success, error message on failure.
        """
        zone_params: dict[str, Any] = {"fqdn": fqdn, "view": view}
        rpz_list = await self._get_rpz_details(device_url, zone_params)

        if not rpz_list:
            return ERR_RPZ_NOT_EXISTS.format(fqdn=fqdn)

        rpz = rpz_list[0]
        if rpz.get("rpz_policy") != BLOCK_POLICY_RULE:
            return ERR_RPZ_POLICY_RULE.format(rule=rpz.get("rpz_policy"))

        return None

# ============================================================================
# ACTION CLASSES
# ============================================================================

class HealthCheckAction(_InfobloxBase):
    """Test connectivity to the Infoblox Grid Manager.

    Validates credentials by querying the schema endpoint.
    This matches the upstream connector's test_asset_connectivity behavior.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity to Infoblox."""
        creds = self._validate_credentials()
        if not creds:
            return self.error_result(
                ERR_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        device_url, _, _ = creds

        try:
            await self._infoblox_request(ENDPOINT_SCHEMA, device_url)

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

class BlockIpAction(_InfobloxRpzBase):
    """Block an IP/CIDR by adding an RPZ rule.

    Creates a 'Block IP Address (No Such Domain)' RPZ rule with the
    specified IP address in the given Response Policy Zone.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Block an IP address via Infoblox RPZ."""
        ip = kwargs.get("ip")
        if not ip:
            return self.error_result(
                "Missing required parameter: ip",
                error_type=ERROR_TYPE_VALIDATION,
            )

        rp_zone = kwargs.get("rp_zone")
        if not rp_zone:
            return self.error_result(
                "Missing required parameter: rp_zone",
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = self._validate_credentials()
        if not creds:
            return self.error_result(
                ERR_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        device_url, _, _ = creds

        if not _validate_ip_cidr(ip):
            return self.error_result(
                f"Invalid IP/CIDR format: {ip}",
                error_type=ERROR_TYPE_VALIDATION,
            )

        view = kwargs.get("network_view", DEFAULT_NETWORK_VIEW)
        comment = kwargs.get("comment")

        try:
            # Step 1: Validate RPZ exists with GIVEN policy
            rpz_error = await self._validate_rpz(device_url, rp_zone, view)
            if rpz_error:
                return self.error_result(rpz_error)

            rpz_rule_name = f"{ip.lower()}.{rp_zone}"

            # Step 2: Check if rule already exists
            check_params: dict[str, Any] = {
                "name": rpz_rule_name,
                "zone": rp_zone,
                "view": view,
            }
            response = await self._infoblox_request(
                ENDPOINT_IP_RPZ, device_url, params=check_params
            )
            existing_rules = response.json()

            if existing_rules:
                # Rule exists - check if it's already a block rule
                if (existing_rules[0].get("canonical") or "") != "":
                    return self.error_result(ERR_IP_EXISTS_NOT_BLOCKED)

                return self.success_result(
                    data={
                        "message": MSG_IP_ALREADY_BLOCKED,
                        "ip": ip,
                        "rp_zone": rp_zone,
                    },
                )

            # Step 3: Create block rule
            api_data: dict[str, Any] = {
                "name": rpz_rule_name,
                "rp_zone": rp_zone,
                "canonical": "",
                "view": view,
            }
            if comment:
                api_data["comment"] = comment

            response = await self._infoblox_request(
                ENDPOINT_IP_RPZ, device_url, method="POST", data=api_data
            )

            return self.success_result(
                data={
                    "message": MSG_IP_BLOCKED,
                    "ip": ip,
                    "rp_zone": rp_zone,
                    "reference_link": response.json() if response.text else None,
                },
            )

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class UnblockIpAction(_InfobloxRpzBase):
    """Unblock an IP/CIDR by removing the RPZ rule.

    Removes the 'Block IP Address (No Such Domain)' RPZ rule for the
    specified IP address from the given Response Policy Zone.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Unblock an IP address via Infoblox RPZ."""
        ip = kwargs.get("ip")
        if not ip:
            return self.error_result(
                "Missing required parameter: ip",
                error_type=ERROR_TYPE_VALIDATION,
            )

        rp_zone = kwargs.get("rp_zone")
        if not rp_zone:
            return self.error_result(
                "Missing required parameter: rp_zone",
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = self._validate_credentials()
        if not creds:
            return self.error_result(
                ERR_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        device_url, _, _ = creds

        view = kwargs.get("network_view", DEFAULT_NETWORK_VIEW)

        try:
            # Step 1: Validate RPZ
            rpz_error = await self._validate_rpz(device_url, rp_zone, view)
            if rpz_error:
                return self.error_result(rpz_error)

            rpz_rule_name = f"{ip.lower()}.{rp_zone}"

            # Step 2: Check if rule exists
            check_params: dict[str, Any] = {
                "name": rpz_rule_name,
                "zone": rp_zone,
                "view": view,
            }
            response = await self._infoblox_request(
                ENDPOINT_IP_RPZ, device_url, params=check_params
            )
            existing_rules = response.json()

            if not existing_rules:
                return self.success_result(
                    data={
                        "message": MSG_IP_ALREADY_UNBLOCKED,
                        "ip": ip,
                        "rp_zone": rp_zone,
                    },
                )

            # Check it's a block rule
            if (existing_rules[0].get("canonical") or "") != "":
                return self.error_result(ERR_IP_NOT_BLOCKED)

            # Step 3: Delete the rule
            ref = existing_rules[0].get("_ref")
            response = await self._infoblox_request(
                f"/{ref}", device_url, method="DELETE"
            )

            return self.success_result(
                data={
                    "message": MSG_IP_UNBLOCKED,
                    "ip": ip,
                    "rp_zone": rp_zone,
                    "reference_link": response.json() if response.text else None,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    not_found=True,
                    data={
                        "message": MSG_IP_ALREADY_UNBLOCKED,
                        "ip": ip,
                        "rp_zone": rp_zone,
                    },
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class BlockDomainAction(_InfobloxRpzBase):
    """Block a domain by adding an RPZ rule.

    Creates a 'Block Domain Name (No Such Domain)' RPZ rule with the
    specified domain in the given Response Policy Zone.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Block a domain via Infoblox RPZ."""
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                "Missing required parameter: domain",
                error_type=ERROR_TYPE_VALIDATION,
            )

        rp_zone = kwargs.get("rp_zone")
        if not rp_zone:
            return self.error_result(
                "Missing required parameter: rp_zone",
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = self._validate_credentials()
        if not creds:
            return self.error_result(
                ERR_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        device_url, _, _ = creds

        # Encode domain to IDNA
        domain = _encode_domain(domain)

        view = kwargs.get("network_view", DEFAULT_NETWORK_VIEW)
        comment = kwargs.get("comment")

        try:
            # Step 1: Validate RPZ
            rpz_error = await self._validate_rpz(device_url, rp_zone, view)
            if rpz_error:
                return self.error_result(rpz_error)

            rpz_rule_name = f"{domain}.{rp_zone}"

            # Step 2: Check if rule already exists
            check_params: dict[str, Any] = {
                "name": rpz_rule_name,
                "zone": rp_zone,
                "view": view,
            }
            response = await self._infoblox_request(
                ENDPOINT_DOMAIN_RPZ, device_url, params=check_params
            )
            existing_rules = response.json()

            if existing_rules:
                if (existing_rules[0].get("canonical") or "") != "":
                    return self.error_result(ERR_DOMAIN_EXISTS_NOT_BLOCKED)

                return self.success_result(
                    data={
                        "message": MSG_DOMAIN_ALREADY_BLOCKED,
                        "domain": domain,
                        "rp_zone": rp_zone,
                    },
                )

            # Step 3: Create block rule
            api_data: dict[str, Any] = {
                "name": rpz_rule_name,
                "rp_zone": rp_zone,
                "canonical": "",
                "view": view,
            }
            if comment:
                api_data["comment"] = comment

            response = await self._infoblox_request(
                ENDPOINT_DOMAIN_RPZ, device_url, method="POST", data=api_data
            )

            return self.success_result(
                data={
                    "message": MSG_DOMAIN_BLOCKED,
                    "domain": domain,
                    "rp_zone": rp_zone,
                    "reference_link": response.json() if response.text else None,
                },
            )

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class UnblockDomainAction(_InfobloxRpzBase):
    """Unblock a domain by removing the RPZ rule.

    Removes the 'Block Domain Name (No Such Domain)' RPZ rule for the
    specified domain from the given Response Policy Zone.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Unblock a domain via Infoblox RPZ."""
        domain = kwargs.get("domain")
        if not domain:
            return self.error_result(
                "Missing required parameter: domain",
                error_type=ERROR_TYPE_VALIDATION,
            )

        rp_zone = kwargs.get("rp_zone")
        if not rp_zone:
            return self.error_result(
                "Missing required parameter: rp_zone",
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = self._validate_credentials()
        if not creds:
            return self.error_result(
                ERR_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        device_url, _, _ = creds

        domain = _encode_domain(domain)
        view = kwargs.get("network_view", DEFAULT_NETWORK_VIEW)

        try:
            # Step 1: Validate RPZ
            rpz_error = await self._validate_rpz(device_url, rp_zone, view)
            if rpz_error:
                return self.error_result(rpz_error)

            rpz_rule_name = f"{domain}.{rp_zone}"

            # Step 2: Check if rule exists
            check_params: dict[str, Any] = {
                "name": rpz_rule_name,
                "zone": rp_zone,
                "view": view,
            }
            response = await self._infoblox_request(
                ENDPOINT_DOMAIN_RPZ, device_url, params=check_params
            )
            existing_rules = response.json()

            if not existing_rules:
                return self.success_result(
                    data={
                        "message": MSG_DOMAIN_ALREADY_UNBLOCKED,
                        "domain": domain,
                        "rp_zone": rp_zone,
                    },
                )

            if (existing_rules[0].get("canonical") or "") != "":
                return self.error_result(ERR_DOMAIN_NOT_BLOCKED)

            # Step 3: Delete the rule
            ref = existing_rules[0].get("_ref")
            response = await self._infoblox_request(
                f"/{ref}", device_url, method="DELETE"
            )

            return self.success_result(
                data={
                    "message": MSG_DOMAIN_UNBLOCKED,
                    "domain": domain,
                    "rp_zone": rp_zone,
                    "reference_link": response.json() if response.text else None,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    not_found=True,
                    data={
                        "message": MSG_DOMAIN_ALREADY_UNBLOCKED,
                        "domain": domain,
                        "rp_zone": rp_zone,
                    },
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class ListRpzAction(_InfobloxBase):
    """List details of Response Policy Zones.

    Returns all RPZ zones for the given network view with their
    policy settings, severity, priority, and last updated time.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List Response Policy Zones."""
        creds = self._validate_credentials()
        if not creds:
            return self.error_result(
                ERR_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        device_url, _, _ = creds
        view = kwargs.get("network_view", DEFAULT_NETWORK_VIEW)

        try:
            zone_params: dict[str, Any] = {
                "view": view,
                "_return_fields": LIST_RP_ZONE_RETURN_FIELDS,
            }
            rpz_list = await self._paged_request(
                ENDPOINT_RP_ZONE_DETAILS, device_url, params=zone_params
            )

            # Convert epoch timestamps to readable format
            for rpz in rpz_list:
                if rpz.get("rpz_last_updated_time"):
                    rpz["rpz_last_updated_time"] = _epoch_to_str(
                        rpz["rpz_last_updated_time"]
                    )

            return self.success_result(
                data={
                    "response_policy_zones": rpz_list,
                    "total_response_policy_zones": len(rpz_list),
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return self.success_result(
                    not_found=True,
                    data={
                        "response_policy_zones": [],
                        "total_response_policy_zones": 0,
                        "network_view": view,
                    },
                )
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class ListHostsAction(_InfobloxBase):
    """List available DNS host records (A and AAAA).

    Queries both IPv4 (record:a) and IPv6 (record:aaaa) endpoints
    and returns a combined list of hosts.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List DNS host records."""
        creds = self._validate_credentials()
        if not creds:
            return self.error_result(
                ERR_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        device_url, _, _ = creds

        try:
            # Get IPv4 hosts
            ipv4_params: dict[str, Any] = {
                "_return_fields": LIST_HOSTS_RETURN_FIELDS_V4
            }
            ipv4_hosts = await self._paged_request(
                ENDPOINT_RECORDS_IPV4, device_url, params=ipv4_params
            )

            # Post-process IPv4 hosts
            for host in ipv4_hosts:
                host["ip"] = host.pop("ipv4addr", "")
                zone = f".{host.get('zone', '')}"
                if host.get("name", "").endswith(zone):
                    host["name"] = host["name"][: -len(zone)]

            # Get IPv6 hosts
            ipv6_params: dict[str, Any] = {
                "_return_fields": LIST_HOSTS_RETURN_FIELDS_V6
            }
            ipv6_hosts = await self._paged_request(
                ENDPOINT_RECORDS_IPV6, device_url, params=ipv6_params
            )

            # Post-process IPv6 hosts
            for host in ipv6_hosts:
                host["ip"] = host.pop("ipv6addr", "")
                zone = f".{host.get('zone', '')}"
                if host.get("name", "").endswith(zone):
                    host["name"] = host["name"][: -len(zone)]

            all_hosts = ipv4_hosts + ipv6_hosts

            return self.success_result(
                data={
                    "hosts": all_hosts,
                    "total_hosts": len(all_hosts),
                },
            )

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class ListNetworkViewAction(_InfobloxBase):
    """List available network views from Infoblox.

    Returns all network views configured on the Grid Manager.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List network views."""
        creds = self._validate_credentials()
        if not creds:
            return self.error_result(
                ERR_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        device_url, _, _ = creds

        try:
            network_views = await self._paged_request(ENDPOINT_NETWORK_VIEW, device_url)

            return self.success_result(
                data={
                    "network_views": network_views,
                    "total_network_views": len(network_views),
                },
            )

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

class GetNetworkInfoAction(_InfobloxBase):
    """Get network information for an IP or IP range.

    Queries the network endpoint for matching networks. If an IP
    (not CIDR) is provided, filters results to networks containing
    that IP address.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get network information."""
        creds = self._validate_credentials()
        if not creds:
            return self.error_result(
                ERR_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        device_url, _, _ = creds

        ip = kwargs.get("ip")
        network_view = kwargs.get("network_view")

        params: dict[str, Any] = {}
        search_ip = None

        if ip:
            if "/" in ip:
                # CIDR notation - pass directly to API
                params["network"] = ip
            else:
                # Single IP - filter results after retrieval
                search_ip = ip

        if network_view:
            params["network_view"] = network_view

        try:
            networks = await self._paged_request(
                ENDPOINT_NETWORK, device_url, params=params
            )

            # Filter results if a single IP was provided
            if search_ip:
                try:
                    ip_obj = ipaddress.ip_address(search_ip)
                    networks = [
                        net
                        for net in networks
                        if net.get("network")
                        and ip_obj in ipaddress.ip_network(net["network"], strict=False)
                    ]
                except ValueError:
                    pass

            return self.success_result(
                data={
                    "networks": networks,
                    "number_of_matching_networks": len(networks),
                },
            )

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

_NOT_FOUND_MESSAGE = (
    "The host might not be available or could be using "
    "statically configured IP and belongs to non-default network view"
)

class GetSystemInfoAction(_InfobloxBase):
    """Get lease/host information for an IP or hostname.

    Queries the lease endpoint and optionally the DNS record endpoints
    to gather comprehensive system information.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get system information for IP/hostname."""
        ip_hostname = kwargs.get("ip_hostname")
        if not ip_hostname:
            return self.error_result(
                "Missing required parameter: ip_hostname",
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = self._validate_credentials()
        if not creds:
            return self.error_result(
                ERR_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        device_url, _, _ = creds
        network_view = kwargs.get("network_view", DEFAULT_NETWORK_VIEW)

        try:
            lease_list, host_list = await self._fetch_system_data(
                device_url, ip_hostname, network_view
            )

            if not lease_list and not host_list:
                return self.success_result(
                    not_found=True,
                    data={"ip_hostname": ip_hostname, "message": _NOT_FOUND_MESSAGE},
                )

            results, summary = self._process_system_data(
                lease_list, host_list, ip_hostname
            )

            if not results:
                return self.success_result(
                    not_found=True,
                    data={"ip_hostname": ip_hostname, "message": _NOT_FOUND_MESSAGE},
                )

            return self.success_result(
                data={
                    "system_info": results,
                    "summary": summary,
                },
            )

        except httpx.HTTPStatusError as e:
            return self.error_result(e)
        except Exception as e:
            return self.error_result(e)

    async def _fetch_system_data(
        self,
        device_url: str,
        ip_hostname: str,
        network_view: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
        """Fetch lease and host record data for the given IP/hostname."""
        lease_params: dict[str, Any] = {"_return_fields": LEASE_RETURN_FIELDS}
        if _is_ip(ip_hostname):
            lease_params["address"] = ip_hostname
        else:
            lease_params["client_hostname"] = ip_hostname
        lease_params["network_view"] = network_view

        response = await self._infoblox_request(
            ENDPOINT_LEASE, device_url, params=lease_params
        )
        lease_list = response.json()

        host_list = None
        if network_view == DEFAULT_NETWORK_VIEW:
            host_list = await self._get_host_records(device_url, ip_hostname)

        return lease_list, host_list

    def _process_system_data(
        self,
        lease_list: list[dict[str, Any]],
        host_list: list[dict[str, Any]] | None,
        ip_hostname: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Process lease and host record data into results and summary."""
        results: list[dict[str, Any]] = []
        summary: dict[str, Any] = {}

        # Process static IP hosts (no lease, but host record exists)
        if not lease_list and host_list:
            self._process_static_hosts(host_list, ip_hostname, results, summary)

        # Process lease records
        for data in lease_list:
            self._enrich_and_format_lease(data, host_list)
            summary["mac_address"] = data.get("hardware")
            summary["binding_state"] = data.get("binding_state")
            summary["never_ends"] = data.get("never_ends")
            summary["is_static_ip"] = False
            results.append(data)

        return results, summary

    @staticmethod
    def _process_static_hosts(
        host_list: list[dict[str, Any]],
        ip_hostname: str,
        results: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> None:
        """Process host records for static IP hosts (no leases)."""
        for host_data in host_list:
            client_hostname = host_data.get("name", "")
            zone = f".{host_data.get('zone', '')}"
            if client_hostname.endswith(zone):
                client_hostname = client_hostname[: -len(zone)]

            if not _is_ip(ip_hostname) and client_hostname != ip_hostname:
                continue

            data: dict[str, Any] = {
                "client_hostname": client_hostname,
                "hardware": host_data.get("discovered_data", {}).get("mac_address"),
                "os": host_data.get("discovered_data", {}).get("os"),
                "address": host_data.get("ipv4addr", host_data.get("ipv6addr")),
            }
            if _is_ipv4(str(host_data.get("ipv4addr", ""))):
                data["protocol"] = "IPV4"
            elif _is_ipv6(str(host_data.get("ipv6addr", ""))):
                data["protocol"] = "IPV6"

            summary["mac_address"] = data["hardware"]
            summary["is_static_ip"] = True
            results.append(data)

    @staticmethod
    def _enrich_and_format_lease(
        data: dict[str, Any],
        host_list: list[dict[str, Any]] | None,
    ) -> None:
        """Enrich lease data with host records and format timestamps."""
        if host_list:
            matching = [
                h
                for h in host_list
                if h.get("ipv4addr") == data.get("address")
                or h.get("ipv6addr") == data.get("address")
            ]
            if matching:
                data["os"] = matching[0].get("discovered_data", {}).get("os")

        for field in ("cltt", "starts", "ends"):
            if data.get(field):
                data[field] = _epoch_to_str(data[field])

    async def _get_host_records(
        self, device_url: str, ip_hostname: str
    ) -> list[dict[str, Any]]:
        """Get A/AAAA host records for a given IP or hostname."""
        if _is_ipv4(ip_hostname):
            params: dict[str, Any] = {
                "_return_fields": RECORD_A_RETURN_FIELDS,
                "ipv4addr": ip_hostname,
                "view": DEFAULT_NETWORK_VIEW,
            }
            response = await self._infoblox_request(
                ENDPOINT_RECORDS_IPV4, device_url, params=params
            )
            return response.json()

        if _is_ipv6(ip_hostname):
            params = {
                "_return_fields": RECORD_AAAA_RETURN_FIELDS,
                "ipv6addr": ip_hostname,
                "view": DEFAULT_NETWORK_VIEW,
            }
            response = await self._infoblox_request(
                ENDPOINT_RECORDS_IPV6, device_url, params=params
            )
            return response.json()

        # Hostname search - try A records first, then AAAA
        params = {
            "_return_fields": RECORD_A_RETURN_FIELDS,
            "name~": ip_hostname,
            "view": DEFAULT_NETWORK_VIEW,
        }
        response = await self._infoblox_request(
            ENDPOINT_RECORDS_IPV4, device_url, params=params
        )
        result = response.json()

        if not result:
            params = {
                "_return_fields": RECORD_AAAA_RETURN_FIELDS,
                "name~": ip_hostname,
                "view": DEFAULT_NETWORK_VIEW,
            }
            response = await self._infoblox_request(
                ENDPOINT_RECORDS_IPV6, device_url, params=params
            )
            result = response.json()

        return result
