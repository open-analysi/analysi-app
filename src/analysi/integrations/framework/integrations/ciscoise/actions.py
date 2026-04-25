"""Cisco ISE integration actions for network access control.

Cisco ISE exposes two API families:
- **MNT (Monitoring) API** -- XML by default, used for active sessions and
  Change of Authorization (CoA).  We request JSON via the ``Accept`` header
  where possible; for XML-only endpoints we parse with ``xml.etree``.
- **ERS (External RESTful Services) API** -- native JSON on port 9060, used
  for endpoint, resource, and ANC policy management.

Both APIs use HTTP Basic Auth.  The ERS API may use separate credentials
(``ers_username`` / ``ers_password``); when those are not configured the
primary credentials are used as a fallback.
"""

from typing import Any
from xml.etree.ElementTree import Element

import httpx
from defusedxml.ElementTree import fromstring as safe_xml_fromstring

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    CREDENTIAL_ERS_PASSWORD,
    CREDENTIAL_ERS_USERNAME,
    CREDENTIAL_PASSWORD,
    CREDENTIAL_USERNAME,
    ERROR_TYPE_API,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    ERS_ANC_APPLY,
    ERS_ANC_CLEAR,
    ERS_ENDPOINT,
    MNT_ACTIVE_LIST,
    MNT_IS_MAC_QUARANTINED,
    MSG_MISSING_CREDENTIALS,
    MSG_MISSING_ENDPOINT_ID,
    MSG_MISSING_ERS_CREDENTIALS,
    MSG_MISSING_IP_MAC_ADDRESS,
    MSG_MISSING_POLICY_NAME,
    MSG_MISSING_SERVER,
    SETTINGS_SERVER,
)

logger = get_logger(__name__)

# ============================================================================
# HELPERS
# ============================================================================

def _get_server(settings: dict[str, Any]) -> str | None:
    """Return the base URL (``https://<host>``) from settings, or None."""
    server = settings.get(SETTINGS_SERVER)
    if not server:
        return None
    server = server.strip()
    if not server.startswith("https://"):
        server = f"https://{server}"
    return server

def _get_ers_auth(credentials: dict[str, Any]) -> tuple[str, str] | None:
    """Return ERS (username, password) tuple, falling back to primary creds.

    Returns None when neither ERS nor primary credentials are available.
    """
    ers_user = credentials.get(CREDENTIAL_ERS_USERNAME)
    ers_pass = credentials.get(CREDENTIAL_ERS_PASSWORD)
    if ers_user and ers_pass:
        return (ers_user, ers_pass)
    # Fallback to primary credentials
    user = credentials.get(CREDENTIAL_USERNAME)
    password = credentials.get(CREDENTIAL_PASSWORD)
    if user and password:
        return (user, password)
    return None

def _xml_to_dict(xml_text: str) -> dict[str, Any]:
    """Convert an XML string to a nested dict.

    A lightweight replacement for ``xmltodict`` using only the stdlib.  This
    handles the simple XML structures returned by the ISE MNT API (flat or
    one-level nesting).
    """

    def _element_to_dict(element: Element) -> dict[str, Any] | str:
        children = list(element)
        if not children:
            return element.text or ""
        result: dict[str, Any] = {}
        for child in children:
            child_data = _element_to_dict(child)
            tag = child.tag
            # Handle repeated tags by converting to list
            if tag in result:
                existing = result[tag]
                if isinstance(existing, list):
                    existing.append(child_data)
                else:
                    result[tag] = [existing, child_data]
            else:
                result[tag] = child_data
        return result

    root = safe_xml_fromstring(xml_text)
    return {root.tag: _element_to_dict(root)}

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Validate connectivity to the Cisco ISE MNT API."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity by fetching the active session list.

        Returns:
            Success result with ``healthy: True`` or error result.
        """
        base_url = _get_server(self.settings)
        if not base_url:
            return self.error_result(
                MSG_MISSING_SERVER, error_type=ERROR_TYPE_CONFIGURATION
            )

        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        if not username or not password:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        try:
            response = await self.http_request(
                url=f"{base_url}{MNT_ACTIVE_LIST}",
                auth=(username, password),
            )
            return self.success_result(
                data={"healthy": True, "status_code": response.status_code},
                healthy=True,
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(
                f"ISE health check failed with status {e.response.status_code}",
                error_type=ERROR_TYPE_API,
            )
        except Exception as e:
            return self.error_result(e)

class GetActiveSessionsAction(IntegrationAction):
    """List active sessions on the Cisco ISE appliance (MNT API)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Fetch the list of currently active sessions.

        Returns:
            Success result containing session list and a quarantine flag per
            session.
        """
        base_url = _get_server(self.settings)
        if not base_url:
            return self.error_result(
                MSG_MISSING_SERVER, error_type=ERROR_TYPE_CONFIGURATION
            )

        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        if not username or not password:
            return self.error_result(
                MSG_MISSING_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        try:
            # Fetch active session list (MNT API returns XML)
            response = await self.http_request(
                url=f"{base_url}{MNT_ACTIVE_LIST}",
                auth=(username, password),
            )
            data = _xml_to_dict(response.text)

            active_list = data.get("activeList", {})
            if not isinstance(active_list, dict):
                # Empty <activeList/> parses as empty string
                active_list = {}
            sessions_raw = active_list.get("activeSession", [])

            # Normalise to list (single session comes as dict)
            if isinstance(sessions_raw, dict):
                sessions_raw = [sessions_raw]

            sessions: list[dict[str, Any]] = []
            for session in sessions_raw:
                mac = session.get("calling_station_id", "")
                quarantine_status = "Unknown"

                # Try to get quarantine status for each MAC
                if mac:
                    try:
                        q_response = await self.http_request(
                            url=f"{base_url}{MNT_IS_MAC_QUARANTINED}/{mac}",
                            auth=(username, password),
                        )
                        q_data = _xml_to_dict(q_response.text)
                        user_data = q_data.get("EPS_RESULT", {}).get("userData", "")
                        quarantine_status = "Yes" if user_data == "true" else "No"
                    except Exception:
                        # Non-fatal: keep Unknown for this session
                        pass

                session["is_quarantined"] = quarantine_status
                sessions.append(session)

            return self.success_result(
                data={"sessions": sessions, "sessions_found": len(sessions)},
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(
                f"Failed to list sessions: HTTP {e.response.status_code}",
                error_type=ERROR_TYPE_API,
            )
        except Exception as e:
            return self.error_result(e)

class ListEndpointsAction(IntegrationAction):
    """List endpoints configured on ISE via the ERS API."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List all endpoints, optionally filtered by MAC address.

        Keyword Args:
            mac_address: Optional MAC address filter.

        Returns:
            Success result with endpoints and total count.
        """
        base_url = _get_server(self.settings)
        if not base_url:
            return self.error_result(
                MSG_MISSING_SERVER, error_type=ERROR_TYPE_CONFIGURATION
            )

        auth = _get_ers_auth(self.credentials)
        if not auth:
            return self.error_result(
                MSG_MISSING_ERS_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        mac_address = kwargs.get("mac_address")
        url = f"{base_url}{ERS_ENDPOINT}"
        if mac_address:
            url += f"?filter=mac.EQ.{mac_address}"

        try:
            response = await self.http_request(
                url=url,
                auth=auth,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            result = response.json()
            total = result.get("SearchResult", {}).get("total", 0)

            return self.success_result(
                data={
                    "search_result": result.get("SearchResult", {}),
                    "endpoints_found": total,
                },
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(
                f"Failed to list endpoints: HTTP {e.response.status_code}",
                error_type=ERROR_TYPE_API,
            )
        except Exception as e:
            return self.error_result(e)

class GetEndpointByMacAction(IntegrationAction):
    """Get detailed information about a specific endpoint by its ISE ID.

    Despite the name (which reflects the common use-case of looking up by
    MAC), the upstream connector actually queries by ISE endpoint ID.  If callers
    need to search by MAC first they can use ``list_endpoints`` with a MAC
    filter and then call this action with the returned ``endpoint_id``.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get endpoint details by ISE endpoint ID.

        Keyword Args:
            endpoint_id: The ISE endpoint UUID.

        Returns:
            Success result with endpoint data, or not_found on 404.
        """
        base_url = _get_server(self.settings)
        if not base_url:
            return self.error_result(
                MSG_MISSING_SERVER, error_type=ERROR_TYPE_CONFIGURATION
            )

        auth = _get_ers_auth(self.credentials)
        if not auth:
            return self.error_result(
                MSG_MISSING_ERS_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        endpoint_id = kwargs.get("endpoint_id")
        if not endpoint_id:
            return self.error_result(
                MSG_MISSING_ENDPOINT_ID, error_type=ERROR_TYPE_VALIDATION
            )

        try:
            response = await self.http_request(
                url=f"{base_url}{ERS_ENDPOINT}/{endpoint_id}",
                auth=auth,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            result = response.json()

            return self.success_result(data=result)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self.log_info("ciscoise_endpoint_not_found", endpoint_id=endpoint_id)
                return self.success_result(
                    not_found=True,
                    data={"endpoint_id": endpoint_id},
                )
            return self.error_result(
                f"Failed to get endpoint: HTTP {e.response.status_code}",
                error_type=ERROR_TYPE_API,
            )
        except Exception as e:
            return self.error_result(e)

class QuarantineEndpointAction(IntegrationAction):
    """Apply an ANC (Adaptive Network Control) policy to quarantine an endpoint.

    Wraps the ISE ERS ``ancendpoint/apply`` operation.  Accepts either a MAC
    address or an IP address for the target endpoint.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Apply ANC policy to an endpoint (quarantine).

        Keyword Args:
            ip_mac_address: MAC address or IP address of the endpoint.
            policy_name: ANC policy name to apply (e.g. "quarantine").

        Returns:
            Success result on successful policy application.
        """
        base_url = _get_server(self.settings)
        if not base_url:
            return self.error_result(
                MSG_MISSING_SERVER, error_type=ERROR_TYPE_CONFIGURATION
            )

        auth = _get_ers_auth(self.credentials)
        if not auth:
            return self.error_result(
                MSG_MISSING_ERS_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        ip_mac_address = kwargs.get("ip_mac_address")
        policy_name = kwargs.get("policy_name")

        if not ip_mac_address:
            return self.error_result(
                MSG_MISSING_IP_MAC_ADDRESS, error_type=ERROR_TYPE_VALIDATION
            )
        if not policy_name:
            return self.error_result(
                MSG_MISSING_POLICY_NAME, error_type=ERROR_TYPE_VALIDATION
            )

        # Detect whether the value is a MAC or IP address
        addr_name = _detect_address_type(ip_mac_address)

        payload = {
            "OperationAdditionalData": {
                "additionalData": [
                    {"name": addr_name, "value": ip_mac_address},
                    {"name": "policyName", "value": policy_name},
                ]
            }
        }

        try:
            await self.http_request(
                url=f"{base_url}{ERS_ANC_APPLY}",
                method="PUT",
                auth=auth,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json_data=payload,
            )
            return self.success_result(
                data={
                    "ip_mac_address": ip_mac_address,
                    "policy_name": policy_name,
                    "message": "Policy applied",
                },
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(
                f"Failed to apply ANC policy: HTTP {e.response.status_code}",
                error_type=ERROR_TYPE_API,
            )
        except Exception as e:
            return self.error_result(e)

class ReleaseEndpointAction(IntegrationAction):
    """Clear an ANC policy from an endpoint (un-quarantine).

    Wraps the ISE ERS ``ancendpoint/clear`` operation.
    """

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Clear ANC policy from an endpoint (release from quarantine).

        Keyword Args:
            ip_mac_address: MAC address or IP address of the endpoint.
            policy_name: ANC policy name to clear.

        Returns:
            Success result on successful policy removal.
        """
        base_url = _get_server(self.settings)
        if not base_url:
            return self.error_result(
                MSG_MISSING_SERVER, error_type=ERROR_TYPE_CONFIGURATION
            )

        auth = _get_ers_auth(self.credentials)
        if not auth:
            return self.error_result(
                MSG_MISSING_ERS_CREDENTIALS, error_type=ERROR_TYPE_CONFIGURATION
            )

        ip_mac_address = kwargs.get("ip_mac_address")
        policy_name = kwargs.get("policy_name")

        if not ip_mac_address:
            return self.error_result(
                MSG_MISSING_IP_MAC_ADDRESS, error_type=ERROR_TYPE_VALIDATION
            )
        if not policy_name:
            return self.error_result(
                MSG_MISSING_POLICY_NAME, error_type=ERROR_TYPE_VALIDATION
            )

        addr_name = _detect_address_type(ip_mac_address)

        payload = {
            "OperationAdditionalData": {
                "additionalData": [
                    {"name": addr_name, "value": ip_mac_address},
                    {"name": "policyName", "value": policy_name},
                ]
            }
        }

        try:
            await self.http_request(
                url=f"{base_url}{ERS_ANC_CLEAR}",
                method="PUT",
                auth=auth,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json_data=payload,
            )
            return self.success_result(
                data={
                    "ip_mac_address": ip_mac_address,
                    "policy_name": policy_name,
                    "message": "Policy cleared",
                },
            )
        except httpx.HTTPStatusError as e:
            return self.error_result(
                f"Failed to clear ANC policy: HTTP {e.response.status_code}",
                error_type=ERROR_TYPE_API,
            )
        except Exception as e:
            return self.error_result(e)

# ============================================================================
# ADDRESS DETECTION HELPER
# ============================================================================

def _detect_address_type(address: str) -> str:
    """Detect whether an address string is a MAC or IP address.

    Returns ``"macAddress"`` or ``"ipAddress"`` for the ISE API payload.
    Defaults to ``"macAddress"`` when the format is ambiguous.
    """
    # Simple heuristic: MACs contain colons or dashes and are 17 chars
    stripped = address.strip()
    if ":" in stripped or "-" in stripped:
        # Looks like a MAC (e.g. AA:BB:CC:DD:EE:FF)
        return "macAddress"
    if "." in stripped and stripped.replace(".", "").replace(":", "").isdigit():
        # Looks like an IPv4 address
        return "ipAddress"
    # Default to MAC for other formats
    return "macAddress"
