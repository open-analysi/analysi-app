"""Cybereason EDR integration actions.

Cybereason uses cookie-based session authentication: a POST to /login.html
returns a JSESSIONID cookie that is attached to all subsequent API requests.
Because ``self.http_request()`` creates a *new* ``httpx.AsyncClient`` per call
(with automatic retry, logging, and SSL handling), we perform the login as the
first call and then pass the resulting cookie header to every follow-up call.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    CUSTOM_REPUTATION_LIST,
    DEFAULT_CONTENT_TYPE,
    DEFAULT_PER_FEATURE_LIMIT,
    DEFAULT_PER_GROUP_LIMIT,
    DEFAULT_QUERY_TIMEOUT,
    DEFAULT_TIMEOUT,
    DEFAULT_TOTAL_RESULT_LIMIT,
    ENDPOINT_CLASSIFICATION_UPDATE,
    ENDPOINT_ISOLATE,
    ENDPOINT_REMEDIATE,
    ENDPOINT_SENSORS_QUERY,
    ENDPOINT_UNISOLATE,
    ENDPOINT_VISUAL_SEARCH,
    ERROR_TYPE_AUTHENTICATION,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    LOGIN_PATH,
    MSG_AUTH_FAILED,
    MSG_MISSING_CREDENTIALS,
    MSG_NO_SENSOR_IDS,
    USER_AGENT,
)

logger = get_logger(__name__)

# ============================================================================
# SHARED HELPERS
# ============================================================================

def _validate_credentials(
    credentials: dict[str, Any],
    settings: dict[str, Any],
) -> tuple[str, str, str] | None:
    """Extract and validate required credentials and settings.

    Returns (base_url, username, password) or None if invalid.
    ``base_url`` is read from *settings* (it is a configuration value, not a
    secret), while ``username`` and ``password`` come from *credentials*.
    """
    base_url = settings.get("base_url", "").rstrip("/")
    username = credentials.get("username")
    password = credentials.get("password")
    if not base_url or not username or not password:
        return None
    return base_url, username, password

async def _login(
    action: IntegrationAction,
    base_url: str,
    username: str,
    password: str,
    timeout: int,
) -> str | None:
    """Authenticate to Cybereason and return the JSESSIONID cookie value.

    Uses ``action.http_request()`` for automatic retry and logging.
    Returns the session ID string, or None on failure.
    """
    try:
        response = await action.http_request(
            url=f"{base_url}{LOGIN_PATH}",
            method="POST",
            data={"username": username, "password": password},
            timeout=timeout,
        )
        # Extract JSESSIONID from response cookies
        cookies = dict(response.cookies)
        session_id = cookies.get("JSESSIONID")
        return session_id
    except Exception as exc:
        logger.debug("cybereason_login_failed", error=str(exc))
        return None

def _build_headers(session_id: str) -> dict[str, str]:
    """Build headers with session cookie for authenticated API calls."""
    return {
        "Content-Type": DEFAULT_CONTENT_TYPE,
        "User-Agent": USER_AGENT,
        "Cookie": f"JSESSIONID={session_id}",
    }

def _build_visual_search_query(
    requested_types: list[dict[str, Any]],
    custom_fields: list[str],
    total_result_limit: int = DEFAULT_TOTAL_RESULT_LIMIT,
    per_group_limit: int = DEFAULT_PER_GROUP_LIMIT,
    per_feature_limit: int = DEFAULT_PER_FEATURE_LIMIT,
    query_timeout: int = DEFAULT_QUERY_TIMEOUT,
) -> dict[str, Any]:
    """Build a Cybereason visual search query payload."""
    return {
        "queryPath": requested_types,
        "totalResultLimit": total_result_limit,
        "perGroupLimit": per_group_limit,
        "perFeatureLimit": per_feature_limit,
        "templateContext": "SPECIFIC",
        "queryTimeout": query_timeout,
        "customFields": custom_fields,
    }

def _extract_simple_value(data: dict[str, Any], key: str) -> str | None:
    """Extract a simple value from Cybereason element data."""
    simple_values = data.get("simpleValues", {})
    entry = simple_values.get(key)
    if entry and entry.get("values"):
        return entry["values"][0]
    return None

def _extract_element_value(data: dict[str, Any], key: str, attr: str) -> str | None:
    """Extract an element value from Cybereason element data."""
    element_values = data.get("elementValues", {})
    entry = element_values.get(key)
    if entry and entry.get("elementValues"):
        return entry["elementValues"][0].get(attr)
    return None

async def _get_sensor_ids_by_name(
    action: IntegrationAction,
    base_url: str,
    headers: dict[str, str],
    machine_name: str,
    timeout: int,
) -> list[str]:
    """Get sensor (pylumId) IDs by machine name."""
    query = {
        "limit": 1000,
        "offset": 0,
        "filters": [
            {"fieldName": "machineName", "operator": "Equals", "values": [machine_name]}
        ],
    }
    try:
        response = await action.http_request(
            url=f"{base_url}{ENDPOINT_SENSORS_QUERY}",
            method="POST",
            headers=headers,
            json_data=query,
            timeout=timeout,
        )
        result = response.json()
        if result.get("totalResults", 0) > 0:
            return [sensor["pylumId"] for sensor in result.get("sensors", [])]
    except Exception as exc:
        logger.debug("cybereason_get_sensor_ids_by_name_failed", error=str(exc))
    return []

async def _get_sensor_ids_by_ip(
    action: IntegrationAction,
    base_url: str,
    headers: dict[str, str],
    machine_ip: str,
    timeout: int,
) -> list[str]:
    """Get sensor (pylumId) IDs by machine IP."""
    query = {
        "limit": 1000,
        "offset": 0,
        "filters": [
            {
                "fieldName": "externalIpAddress",
                "operator": "Equals",
                "values": [machine_ip],
            }
        ],
    }
    try:
        response = await action.http_request(
            url=f"{base_url}{ENDPOINT_SENSORS_QUERY}",
            method="POST",
            headers=headers,
            json_data=query,
            timeout=timeout,
        )
        result = response.json()
        if result.get("totalResults", 0) > 0:
            return [sensor["pylumId"] for sensor in result.get("sensors", [])]
    except Exception as exc:
        logger.debug("cybereason_get_sensor_ids_by_ip_failed", error=str(exc))
    return []

async def _get_machine_sensor_ids(
    action: IntegrationAction,
    base_url: str,
    headers: dict[str, str],
    machine_name_or_ip: str,
    timeout: int,
) -> list[str]:
    """Get sensor IDs by machine name or IP (tries both)."""
    sensor_ids: list[str] = []

    by_name = await _get_sensor_ids_by_name(
        action, base_url, headers, machine_name_or_ip, timeout
    )
    sensor_ids.extend(by_name)

    by_ip = await _get_sensor_ids_by_ip(
        action, base_url, headers, machine_name_or_ip, timeout
    )
    sensor_ids.extend(by_ip)

    return sensor_ids

async def _get_malop_sensor_ids(
    action: IntegrationAction,
    base_url: str,
    headers: dict[str, str],
    malop_id: str,
    timeout: int,
) -> list[str]:
    """Get sensor IDs for all machines in a malop."""
    query = _build_visual_search_query(
        requested_types=[
            {
                "requestedType": "MalopProcess",
                "filters": [],
                "guidList": [malop_id],
                "connectionFeature": {
                    "elementInstanceType": "MalopProcess",
                    "featureName": "suspects",
                },
            },
            {
                "requestedType": "Process",
                "filters": [],
                "connectionFeature": {
                    "elementInstanceType": "Process",
                    "featureName": "ownerMachine",
                },
            },
            {"requestedType": "Machine", "filters": [], "isResult": True},
        ],
        custom_fields=["pylumId", "elementDisplayName"],
        per_group_limit=1200,
        per_feature_limit=1200,
    )
    # Override queryTimeout to None as in the upstream connector
    query["queryTimeout"] = None

    try:
        response = await action.http_request(
            url=f"{base_url}{ENDPOINT_VISUAL_SEARCH}",
            method="POST",
            headers=headers,
            json_data=query,
            timeout=timeout,
        )
        result = response.json()
        machines = result.get("data", {}).get("resultIdToElementDataMap", {})
        sensor_ids = []
        for machine_details in machines.values():
            pylum_id = _extract_simple_value(machine_details, "pylumId")
            if pylum_id:
                sensor_ids.append(str(pylum_id))
        return sensor_ids
    except Exception as exc:
        logger.debug("cybereason_get_malop_sensor_ids_failed", error=str(exc))
        return []

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Test connectivity to the Cybereason console."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Authenticate to the Cybereason console and verify session cookie."""
        creds = _validate_credentials(self.credentials, self.settings)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
                data={"healthy": False},
            )

        base_url, username, password = creds
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        session_id = await _login(self, base_url, username, password, timeout)
        if not session_id:
            logger.error("cybereason_health_check_failed", error=MSG_AUTH_FAILED)
            return self.error_result(
                MSG_AUTH_FAILED,
                error_type=ERROR_TYPE_AUTHENTICATION,
                data={"healthy": False},
            )

        return self.success_result(
            data={"healthy": True, "session_established": True},
        )

class IsolateMachineAction(IntegrationAction):
    """Isolate machines in a malop from the network."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Block all communication for machines associated with a malop.

        Args:
            **kwargs: Must contain 'malop_id'
        """
        malop_id = kwargs.get("malop_id")
        if not malop_id:
            return self.error_result(
                "Missing required parameter: malop_id",
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = _validate_credentials(self.credentials, self.settings)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url, username, password = creds
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        session_id = await _login(self, base_url, username, password, timeout)
        if not session_id:
            return self.error_result(
                MSG_AUTH_FAILED,
                error_type=ERROR_TYPE_AUTHENTICATION,
            )

        headers = _build_headers(session_id)

        try:
            sensor_ids = await _get_malop_sensor_ids(
                self, base_url, headers, malop_id, timeout
            )
            if not sensor_ids:
                return self.error_result(
                    MSG_NO_SENSOR_IDS,
                    error_type=ERROR_TYPE_VALIDATION,
                )

            await self.http_request(
                url=f"{base_url}{ENDPOINT_ISOLATE}",
                method="POST",
                headers=headers,
                json_data={"pylumIds": sensor_ids, "malopId": malop_id},
                timeout=timeout,
            )

            return self.success_result(
                data={
                    "malop_id": malop_id,
                    "sensor_ids": sensor_ids,
                    "message": f"Isolation requested for {len(sensor_ids)} sensor(s)",
                },
            )
        except httpx.HTTPStatusError as e:
            logger.error("cybereason_isolate_machine_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            logger.error("cybereason_isolate_machine_failed", error=str(e))
            return self.error_result(e)

class UnisolateMachineAction(IntegrationAction):
    """Release machines in a malop from network isolation."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Unblock all communication for machines associated with a malop.

        Args:
            **kwargs: Must contain 'malop_id'
        """
        malop_id = kwargs.get("malop_id")
        if not malop_id:
            return self.error_result(
                "Missing required parameter: malop_id",
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = _validate_credentials(self.credentials, self.settings)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url, username, password = creds
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        session_id = await _login(self, base_url, username, password, timeout)
        if not session_id:
            return self.error_result(
                MSG_AUTH_FAILED,
                error_type=ERROR_TYPE_AUTHENTICATION,
            )

        headers = _build_headers(session_id)

        try:
            sensor_ids = await _get_malop_sensor_ids(
                self, base_url, headers, malop_id, timeout
            )
            if not sensor_ids:
                return self.error_result(
                    MSG_NO_SENSOR_IDS,
                    error_type=ERROR_TYPE_VALIDATION,
                )

            await self.http_request(
                url=f"{base_url}{ENDPOINT_UNISOLATE}",
                method="POST",
                headers=headers,
                json_data={"pylumIds": sensor_ids, "malopId": malop_id},
                timeout=timeout,
            )

            return self.success_result(
                data={
                    "malop_id": malop_id,
                    "sensor_ids": sensor_ids,
                    "message": f"Un-isolation requested for {len(sensor_ids)} sensor(s)",
                },
            )
        except httpx.HTTPStatusError as e:
            logger.error("cybereason_unisolate_machine_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            logger.error("cybereason_unisolate_machine_failed", error=str(e))
            return self.error_result(e)

class QuarantineDeviceAction(IntegrationAction):
    """Isolate a specific machine by name or IP from the network."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Block all communication for a machine identified by name or IP.

        Args:
            **kwargs: Must contain 'machine_name_or_ip'
        """
        machine_name_or_ip = kwargs.get("machine_name_or_ip")
        if not machine_name_or_ip:
            return self.error_result(
                "Missing required parameter: machine_name_or_ip",
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = _validate_credentials(self.credentials, self.settings)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url, username, password = creds
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        session_id = await _login(self, base_url, username, password, timeout)
        if not session_id:
            return self.error_result(
                MSG_AUTH_FAILED,
                error_type=ERROR_TYPE_AUTHENTICATION,
            )

        headers = _build_headers(session_id)

        try:
            sensor_ids = await _get_machine_sensor_ids(
                self, base_url, headers, machine_name_or_ip, timeout
            )
            if not sensor_ids:
                return self.error_result(
                    MSG_NO_SENSOR_IDS,
                    error_type=ERROR_TYPE_VALIDATION,
                )

            await self.http_request(
                url=f"{base_url}{ENDPOINT_ISOLATE}",
                method="POST",
                headers=headers,
                json_data={"pylumIds": sensor_ids},
                timeout=timeout,
            )

            return self.success_result(
                data={
                    "machine_name_or_ip": machine_name_or_ip,
                    "sensor_ids": sensor_ids,
                    "message": f"Isolation requested for {machine_name_or_ip}",
                },
            )
        except httpx.HTTPStatusError as e:
            logger.error("cybereason_quarantine_device_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            logger.error("cybereason_quarantine_device_failed", error=str(e))
            return self.error_result(e)

class UnquarantineDeviceAction(IntegrationAction):
    """Release a specific machine by name or IP from network isolation."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Unblock all communication for a machine identified by name or IP.

        Args:
            **kwargs: Must contain 'machine_name_or_ip'
        """
        machine_name_or_ip = kwargs.get("machine_name_or_ip")
        if not machine_name_or_ip:
            return self.error_result(
                "Missing required parameter: machine_name_or_ip",
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = _validate_credentials(self.credentials, self.settings)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url, username, password = creds
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        session_id = await _login(self, base_url, username, password, timeout)
        if not session_id:
            return self.error_result(
                MSG_AUTH_FAILED,
                error_type=ERROR_TYPE_AUTHENTICATION,
            )

        headers = _build_headers(session_id)

        try:
            sensor_ids = await _get_machine_sensor_ids(
                self, base_url, headers, machine_name_or_ip, timeout
            )
            if not sensor_ids:
                return self.error_result(
                    MSG_NO_SENSOR_IDS,
                    error_type=ERROR_TYPE_VALIDATION,
                )

            await self.http_request(
                url=f"{base_url}{ENDPOINT_UNISOLATE}",
                method="POST",
                headers=headers,
                json_data={"pylumIds": sensor_ids},
                timeout=timeout,
            )

            return self.success_result(
                data={
                    "machine_name_or_ip": machine_name_or_ip,
                    "sensor_ids": sensor_ids,
                    "message": f"Un-isolation requested for {machine_name_or_ip}",
                },
            )
        except httpx.HTTPStatusError as e:
            logger.error("cybereason_unquarantine_device_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            logger.error("cybereason_unquarantine_device_failed", error=str(e))
            return self.error_result(e)

class QueryProcessesAction(IntegrationAction):
    """Query processes associated with a malop."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Retrieve all processes for a given malop ID.

        Args:
            **kwargs: Must contain 'malop_id'
        """
        malop_id = kwargs.get("malop_id")
        if not malop_id:
            return self.error_result(
                "Missing required parameter: malop_id",
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = _validate_credentials(self.credentials, self.settings)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url, username, password = creds
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        session_id = await _login(self, base_url, username, password, timeout)
        if not session_id:
            return self.error_result(
                MSG_AUTH_FAILED,
                error_type=ERROR_TYPE_AUTHENTICATION,
            )

        headers = _build_headers(session_id)

        try:
            query = _build_visual_search_query(
                requested_types=[
                    {
                        "requestedType": "MalopProcess",
                        "filters": [],
                        "guidList": [malop_id],
                        "connectionFeature": {
                            "elementInstanceType": "MalopProcess",
                            "featureName": "suspects",
                        },
                    },
                    {"requestedType": "Process", "filters": [], "isResult": True},
                ],
                custom_fields=["ownerMachine", "elementDisplayName"],
            )

            response = await self.http_request(
                url=f"{base_url}{ENDPOINT_VISUAL_SEARCH}",
                method="POST",
                headers=headers,
                json_data=query,
                timeout=timeout,
            )

            result = response.json()
            processes_map = result.get("data", {}).get("resultIdToElementDataMap", {})

            processes = []
            for process_id, process_data in processes_map.items():
                entry: dict[str, Any] = {
                    "process_id": process_id,
                    "process_name": _extract_simple_value(
                        process_data, "elementDisplayName"
                    ),
                }
                owner_machine_id = _extract_element_value(
                    process_data, "ownerMachine", "guid"
                )
                if owner_machine_id:
                    entry["owner_machine_id"] = owner_machine_id
                owner_machine_name = _extract_element_value(
                    process_data, "ownerMachine", "name"
                )
                if owner_machine_name:
                    entry["owner_machine_name"] = owner_machine_name
                processes.append(entry)

            return self.success_result(
                data={
                    "malop_id": malop_id,
                    "total_processes": len(processes),
                    "processes": processes,
                },
            )

        except httpx.HTTPStatusError as e:
            logger.error("cybereason_query_processes_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            logger.error("cybereason_query_processes_failed", error=str(e))
            return self.error_result(e)

class QueryMachinesAction(IntegrationAction):
    """Query machine details by name."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Retrieve machine information by machine name.

        Args:
            **kwargs: Must contain 'name'
        """
        name = kwargs.get("name")
        if not name:
            return self.error_result(
                "Missing required parameter: name",
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = _validate_credentials(self.credentials, self.settings)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url, username, password = creds
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        session_id = await _login(self, base_url, username, password, timeout)
        if not session_id:
            return self.error_result(
                MSG_AUTH_FAILED,
                error_type=ERROR_TYPE_AUTHENTICATION,
            )

        headers = _build_headers(session_id)

        try:
            query = _build_visual_search_query(
                requested_types=[
                    {
                        "requestedType": "Machine",
                        "filters": [
                            {
                                "facetName": "elementDisplayName",
                                "values": [name],
                                "filterType": "MatchesWildcard",
                            }
                        ],
                        "isResult": True,
                    }
                ],
                custom_fields=[
                    "osVersionType",
                    "platformArchitecture",
                    "uptime",
                    "isActiveProbeConnected",
                    "lastSeenTimeStamp",
                    "timeStampSinceLastConnectionTime",
                    "activeUsers",
                    "mountPoints",
                    "processes",
                    "services",
                    "elementDisplayName",
                ],
            )

            response = await self.http_request(
                url=f"{base_url}{ENDPOINT_VISUAL_SEARCH}",
                method="POST",
                headers=headers,
                json_data=query,
                timeout=timeout,
            )

            result = response.json()
            machines_map = result.get("data", {}).get("resultIdToElementDataMap", {})

            machines = []
            for machine_id, machine_data in machines_map.items():
                entry: dict[str, Any] = {
                    "machine_id": machine_id,
                    "machine_name": _extract_simple_value(
                        machine_data, "elementDisplayName"
                    ),
                }
                os_version = _extract_simple_value(machine_data, "osVersionType")
                if os_version:
                    entry["os_version"] = os_version
                arch = _extract_simple_value(machine_data, "platformArchitecture")
                if arch:
                    entry["platform_architecture"] = arch
                connected = _extract_simple_value(
                    machine_data, "isActiveProbeConnected"
                )
                if connected is not None:
                    entry["is_connected_to_cybereason"] = connected
                machines.append(entry)

            return self.success_result(
                data={
                    "name": name,
                    "total_machines": len(machines),
                    "machines": machines,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("cybereason_machine_not_found", name=name)
                return self.success_result(
                    data={
                        "not_found": True,
                        "name": name,
                        "total_machines": 0,
                        "machines": [],
                    },
                )
            logger.error("cybereason_query_machines_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            logger.error("cybereason_query_machines_failed", error=str(e))
            return self.error_result(e)

class GetSensorStatusAction(IntegrationAction):
    """Get connectivity status for all machine sensors in a malop."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get sensor online/offline status for machines in a malop.

        Args:
            **kwargs: Must contain 'malop_id'
        """
        malop_id = kwargs.get("malop_id")
        if not malop_id:
            return self.error_result(
                "Missing required parameter: malop_id",
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = _validate_credentials(self.credentials, self.settings)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url, username, password = creds
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        session_id = await _login(self, base_url, username, password, timeout)
        if not session_id:
            return self.error_result(
                MSG_AUTH_FAILED,
                error_type=ERROR_TYPE_AUTHENTICATION,
            )

        headers = _build_headers(session_id)

        try:
            query = _build_visual_search_query(
                requested_types=[
                    {
                        "requestedType": "MalopProcess",
                        "filters": [],
                        "guidList": [malop_id],
                        "connectionFeature": {
                            "elementInstanceType": "MalopProcess",
                            "featureName": "suspects",
                        },
                    },
                    {
                        "requestedType": "Process",
                        "filters": [],
                        "connectionFeature": {
                            "elementInstanceType": "Process",
                            "featureName": "ownerMachine",
                        },
                    },
                    {"requestedType": "Machine", "filters": [], "isResult": True},
                ],
                custom_fields=["isConnected", "elementDisplayName"],
                per_group_limit=1200,
                per_feature_limit=1200,
            )
            # the upstream connector uses a short query timeout of 30 for this action
            query["queryTimeout"] = 30

            response = await self.http_request(
                url=f"{base_url}{ENDPOINT_VISUAL_SEARCH}",
                method="POST",
                headers=headers,
                json_data=query,
                timeout=timeout,
            )

            result = response.json()
            machines_map = result.get("data", {}).get("resultIdToElementDataMap", {})

            sensors = []
            for machine_id, machine_details in machines_map.items():
                is_connected = _extract_simple_value(machine_details, "isConnected")
                sensors.append(
                    {
                        "machine_id": machine_id,
                        "machine_name": _extract_simple_value(
                            machine_details, "elementDisplayName"
                        ),
                        "status": "Online" if is_connected == "true" else "Offline",
                    }
                )

            return self.success_result(
                data={
                    "malop_id": malop_id,
                    "total_sensors": len(sensors),
                    "sensors": sensors,
                },
            )

        except httpx.HTTPStatusError as e:
            logger.error("cybereason_get_sensor_status_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            logger.error("cybereason_get_sensor_status_failed", error=str(e))
            return self.error_result(e)

class KillProcessAction(IntegrationAction):
    """Kill an active process on a machine via remediation."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Request process termination through the Cybereason remediation API.

        Args:
            **kwargs: Must contain 'malop_id', 'machine_id', 'process_id', 'remediation_user'
        """
        malop_id = kwargs.get("malop_id")
        machine_id = kwargs.get("machine_id")
        process_id = kwargs.get("process_id")
        remediation_user = kwargs.get("remediation_user")

        missing = []
        if not malop_id:
            missing.append("malop_id")
        if not machine_id:
            missing.append("machine_id")
        if not process_id:
            missing.append("process_id")
        if not remediation_user:
            missing.append("remediation_user")

        if missing:
            return self.error_result(
                f"Missing required parameter(s): {', '.join(missing)}",
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = _validate_credentials(self.credentials, self.settings)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url, username, password = creds
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        session_id = await _login(self, base_url, username, password, timeout)
        if not session_id:
            return self.error_result(
                MSG_AUTH_FAILED,
                error_type=ERROR_TYPE_AUTHENTICATION,
            )

        headers = _build_headers(session_id)

        try:
            query = {
                "malopId": malop_id,
                "initiatorUserName": remediation_user,
                "actionsByMachine": {
                    machine_id: [{"targetId": process_id, "actionType": "KILL_PROCESS"}]
                },
            }

            response = await self.http_request(
                url=f"{base_url}{ENDPOINT_REMEDIATE}",
                method="POST",
                headers=headers,
                json_data=query,
                timeout=timeout,
            )

            result = response.json()
            data: dict[str, Any] = {"remediation_id": result.get("remediationId")}
            status_log = result.get("statusLog", [])
            if status_log:
                data["remediation_status"] = status_log[0].get("status")

            return self.success_result(data=data)

        except httpx.HTTPStatusError as e:
            logger.error("cybereason_kill_process_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            logger.error("cybereason_kill_process_failed", error=str(e))
            return self.error_result(e)

class SetReputationAction(IntegrationAction):
    """Set reputation (whitelist/blacklist/remove) for a file hash."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Update the custom reputation for a file hash.

        Args:
            **kwargs: Must contain 'reputation_item_hash' and 'custom_reputation'
        """
        reputation_item_hash = kwargs.get("reputation_item_hash")
        custom_reputation = kwargs.get("custom_reputation")

        if not reputation_item_hash:
            return self.error_result(
                "Missing required parameter: reputation_item_hash",
                error_type=ERROR_TYPE_VALIDATION,
            )

        if custom_reputation not in CUSTOM_REPUTATION_LIST:
            return self.error_result(
                f"Invalid custom_reputation. Must be one of: {', '.join(CUSTOM_REPUTATION_LIST)}",
                error_type=ERROR_TYPE_VALIDATION,
            )

        creds = _validate_credentials(self.credentials, self.settings)
        if not creds:
            return self.error_result(
                MSG_MISSING_CREDENTIALS,
                error_type=ERROR_TYPE_CONFIGURATION,
            )

        base_url, username, password = creds
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        session_id = await _login(self, base_url, username, password, timeout)
        if not session_id:
            return self.error_result(
                MSG_AUTH_FAILED,
                error_type=ERROR_TYPE_AUTHENTICATION,
            )

        headers = _build_headers(session_id)

        try:
            if custom_reputation == "remove":
                payload = [
                    {
                        "keys": [reputation_item_hash],
                        "maliciousType": None,
                        "prevent": False,
                        "remove": True,
                    }
                ]
            else:
                payload = [
                    {
                        "keys": [reputation_item_hash],
                        "maliciousType": custom_reputation,
                        "prevent": False,
                        "remove": False,
                    }
                ]

            await self.http_request(
                url=f"{base_url}{ENDPOINT_CLASSIFICATION_UPDATE}",
                method="POST",
                headers=headers,
                json_data=payload,
                timeout=timeout,
            )

            return self.success_result(
                data={
                    "reputation_item_hash": reputation_item_hash,
                    "custom_reputation": custom_reputation,
                    "message": f"Reputation '{custom_reputation}' set for hash",
                },
            )

        except httpx.HTTPStatusError as e:
            logger.error("cybereason_set_reputation_failed", error=str(e))
            return self.error_result(e)
        except Exception as e:
            logger.error("cybereason_set_reputation_failed", error=str(e))
            return self.error_result(e)
