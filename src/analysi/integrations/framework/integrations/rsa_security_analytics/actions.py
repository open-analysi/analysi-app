"""RSA Security Analytics integration actions for the Naxos framework."""

import contextlib
import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from analysi.integrations.framework.base import IntegrationAction

from . import constants as consts

class HealthCheckAction(IntegrationAction):
    """Health check action for RSA Security Analytics."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute health check against RSA Security Analytics server.

        Returns:
            dict: Health check result with status and message
        """
        try:
            # Validate credentials
            url = self.settings.get(consts.SETTINGS_URL)
            username = self.credentials.get(consts.CREDENTIAL_USERNAME)
            password = self.credentials.get(consts.CREDENTIAL_PASSWORD)

            if not url or not username or not password:
                return {
                    "healthy": False,
                    "status": consts.STATUS_ERROR,
                    "error_type": consts.ERROR_TYPE_CONFIGURATION,
                    "error": consts.MSG_MISSING_CREDENTIALS,
                }

            # Validate settings
            incident_manager = self.settings.get(consts.SETTINGS_INCIDENT_MANAGER)
            if not incident_manager:
                return {
                    "healthy": False,
                    "status": consts.STATUS_ERROR,
                    "error_type": consts.ERROR_TYPE_CONFIGURATION,
                    "error": consts.MSG_MISSING_INCIDENT_MANAGER,
                }

            # Attempt to login and get incident manager device
            csrf_token, session_id = await self._login()

            # Verify incident manager device exists
            await self._get_incident_manager_id(csrf_token, session_id)

            # Logout
            await self._logout(session_id)

            return {
                "healthy": True,
                "status": consts.STATUS_SUCCESS,
                "message": "RSA Security Analytics connection successful",
            }

        except Exception as e:
            return {
                "healthy": False,
                "status": consts.STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

    async def _login(self) -> tuple[str, str]:
        """Perform login to RSA Security Analytics.

        Returns:
            tuple: (csrf_token, session_id)
        """
        url = self.settings.get(consts.SETTINGS_URL).rstrip("/")
        username = self.credentials.get(consts.CREDENTIAL_USERNAME)
        password = self.credentials.get(consts.CREDENTIAL_PASSWORD)
        verify_ssl = self.settings.get(consts.SETTINGS_VERIFY_SSL, False)

        login_url = f"{url}{consts.ENDPOINT_LOGIN}"
        login_data = {"j_username": username, "j_password": password}

        timeout = self.settings.get(consts.SETTINGS_TIMEOUT, consts.DEFAULT_TIMEOUT)

        response = await self.http_request(
            login_url,
            method="POST",
            data=login_data,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )

        # Extract CSRF token
        search_token = '"csrf-token" content="'
        if search_token not in response.text:
            raise ValueError(consts.MSG_CSRF_TOKEN_NOT_FOUND)

        csrf_index = re.search(search_token, response.text).end()
        csrf_token = response.text[csrf_index : csrf_index + 36]

        # Extract session ID
        session_id = response.cookies.get("JSESSIONID")
        if not session_id:
            raise ValueError(consts.MSG_SESSION_ID_MISSING)

        return csrf_token, session_id

    async def _get_incident_manager_id(self, csrf_token: str, session_id: str) -> str:
        """Get the incident manager device ID.

        Args:
            csrf_token: CSRF token from login
            session_id: Session ID cookie value

        Returns:
            str: Incident manager device ID
        """
        url = self.settings.get(consts.SETTINGS_URL).rstrip("/")
        incident_manager_name = self.settings.get(consts.SETTINGS_INCIDENT_MANAGER)
        verify_ssl = self.settings.get(consts.SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(consts.SETTINGS_TIMEOUT, consts.DEFAULT_TIMEOUT)

        endpoint = consts.ENDPOINT_DEVICES_TYPES.format(
            device_type="INCIDENT_MANAGEMENT"
        )
        query_params = {
            "page": 1,
            "start": 0,
            "limit": 100,
            "sort": [{"property": "displayType", "direction": "ASC"}],
        }

        cookie_header = {"Cookie": f"JSESSIONID={session_id}"}
        response = await self.http_request(
            f"{url}{endpoint}",
            params=query_params,
            headers=cookie_header,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )

        data = response.json()
        if not data.get("success"):
            raise ValueError(f"API call failed: {data.get('message', 'Unknown error')}")

        devices = data.get("data")
        if not devices:
            raise ValueError(consts.MSG_NO_DEVICES_FOUND)

        # Find matching device
        names = [device["displayName"] for device in devices]
        try:
            matched_index = names.index(incident_manager_name)
        except ValueError:
            raise ValueError(
                f"{consts.MSG_INCIDENT_MANAGER_NOT_FOUND}: '{incident_manager_name}'"
            )

        incident_manager_id = devices[matched_index].get("id")
        if not incident_manager_id:
            raise ValueError(f"Could not get ID for device '{incident_manager_name}'")

        return str(incident_manager_id)

    async def _logout(self, session_id: str) -> None:
        """Logout from RSA Security Analytics.

        Args:
            session_id: Session ID cookie value
        """
        url = self.settings.get(consts.SETTINGS_URL).rstrip("/")
        verify_ssl = self.settings.get(consts.SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(consts.SETTINGS_TIMEOUT, consts.DEFAULT_TIMEOUT)

        logout_url = f"{url}{consts.ENDPOINT_LOGOUT}"

        with contextlib.suppress(Exception):
            await self.http_request(
                logout_url,
                headers={"Cookie": f"JSESSIONID={session_id}"},
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

class ListIncidentsAction(IntegrationAction):
    """List incidents from RSA Security Analytics."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List incidents within a time frame.

        Args:
            start_time: Start time in format YYYY-MM-DD HH:MM:SS (UTC)
            end_time: End time in format YYYY-MM-DD HH:MM:SS (UTC)
            limit: Maximum number of incidents to list (default: 100)

        Returns:
            dict: Incidents list with count and data
        """
        try:
            # Extract parameters
            start_time = kwargs.get("start_time")
            end_time = kwargs.get("end_time")
            limit = kwargs.get("limit", consts.DEFAULT_INCIDENT_LIMIT)

            # Validate credentials
            url = self.settings.get(consts.SETTINGS_URL)
            username = self.credentials.get(consts.CREDENTIAL_USERNAME)
            password = self.credentials.get(consts.CREDENTIAL_PASSWORD)

            if not url or not username or not password:
                return {
                    "status": consts.STATUS_ERROR,
                    "error_type": consts.ERROR_TYPE_CONFIGURATION,
                    "error": consts.MSG_MISSING_CREDENTIALS,
                }

            # Parse time range
            start_epoch = 0
            end_epoch = 0
            if start_time or end_time:
                epoch = datetime.fromtimestamp(0, UTC)
                try:
                    if start_time:
                        start_epoch = int(
                            (
                                datetime.strptime(
                                    start_time, "%Y-%m-%d %H:%M:%S"
                                ).replace(tzinfo=UTC)
                                - epoch
                            ).total_seconds()
                            * 1000
                        )
                    else:
                        start_epoch = consts.DEFAULT_START_TIME

                    if end_time:
                        end_epoch = int(
                            (
                                datetime.strptime(
                                    end_time, "%Y-%m-%d %H:%M:%S"
                                ).replace(tzinfo=UTC)
                                - epoch
                            ).total_seconds()
                            * 1000
                        )
                    else:
                        end_epoch = int(time.time() * 1000)
                except ValueError as e:
                    return {
                        "status": consts.STATUS_ERROR,
                        "error_type": consts.ERROR_TYPE_VALIDATION,
                        "error": f"Invalid time format: {e!s}",
                    }

            # Login
            csrf_token, session_id = await self._login()

            try:
                # Get incident manager ID
                incident_manager_id = await self._get_incident_manager_id(
                    csrf_token, session_id
                )

                # Get incidents
                incidents = await self._get_incidents(
                    session_id, incident_manager_id, limit, start_epoch, end_epoch
                )

                return {
                    "status": consts.STATUS_SUCCESS,
                    "num_incidents": len(incidents),
                    "incidents": incidents,
                }

            finally:
                # Always logout
                await self._logout(session_id)

        except httpx.HTTPStatusError as e:
            return {
                "status": consts.STATUS_ERROR,
                "error_type": consts.ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": consts.STATUS_ERROR,
                "error_type": consts.ERROR_TYPE_CONNECTION,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": consts.STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

    async def _login(self) -> tuple[str, str]:
        """Login helper (same as HealthCheckAction)."""
        url = self.settings.get(consts.SETTINGS_URL).rstrip("/")
        username = self.credentials.get(consts.CREDENTIAL_USERNAME)
        password = self.credentials.get(consts.CREDENTIAL_PASSWORD)
        verify_ssl = self.settings.get(consts.SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(consts.SETTINGS_TIMEOUT, consts.DEFAULT_TIMEOUT)

        login_url = f"{url}{consts.ENDPOINT_LOGIN}"
        login_data = {"j_username": username, "j_password": password}

        response = await self.http_request(
            login_url,
            method="POST",
            data=login_data,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )

        search_token = '"csrf-token" content="'
        if search_token not in response.text:
            raise ValueError(consts.MSG_CSRF_TOKEN_NOT_FOUND)

        csrf_index = re.search(search_token, response.text).end()
        csrf_token = response.text[csrf_index : csrf_index + 36]

        session_id = response.cookies.get("JSESSIONID")
        if not session_id:
            raise ValueError(consts.MSG_SESSION_ID_MISSING)

        return csrf_token, session_id

    async def _get_incident_manager_id(self, csrf_token: str, session_id: str) -> str:
        """Get incident manager ID helper."""
        url = self.settings.get(consts.SETTINGS_URL).rstrip("/")
        incident_manager_name = self.settings.get(consts.SETTINGS_INCIDENT_MANAGER)
        verify_ssl = self.settings.get(consts.SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(consts.SETTINGS_TIMEOUT, consts.DEFAULT_TIMEOUT)

        endpoint = consts.ENDPOINT_DEVICES_TYPES.format(
            device_type="INCIDENT_MANAGEMENT"
        )
        query_params = {
            "page": 1,
            "start": 0,
            "limit": 100,
            "sort": [{"property": "displayType", "direction": "ASC"}],
        }

        cookie_header = {"Cookie": f"JSESSIONID={session_id}"}
        response = await self.http_request(
            f"{url}{endpoint}",
            params=query_params,
            headers=cookie_header,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )

        data = response.json()
        if not data.get("success"):
            raise ValueError(f"API call failed: {data.get('message', 'Unknown error')}")

        devices = data.get("data")
        if not devices:
            raise ValueError(consts.MSG_NO_DEVICES_FOUND)

        names = [device["displayName"] for device in devices]
        try:
            matched_index = names.index(incident_manager_name)
        except ValueError:
            raise ValueError(
                f"{consts.MSG_INCIDENT_MANAGER_NOT_FOUND}: '{incident_manager_name}'"
            )

        incident_manager_id = devices[matched_index].get("id")
        if not incident_manager_id:
            raise ValueError(f"Could not get ID for device '{incident_manager_name}'")

        return str(incident_manager_id)

    async def _logout(self, session_id: str) -> None:
        """Logout helper."""
        url = self.settings.get(consts.SETTINGS_URL).rstrip("/")
        verify_ssl = self.settings.get(consts.SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(consts.SETTINGS_TIMEOUT, consts.DEFAULT_TIMEOUT)

        logout_url = f"{url}{consts.ENDPOINT_LOGOUT}"

        with contextlib.suppress(Exception):
            await self.http_request(
                logout_url,
                headers={"Cookie": f"JSESSIONID={session_id}"},
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

    async def _get_incidents(
        self,
        session_id: str,
        incident_manager_id: str,
        limit: int,
        start_time: int,
        end_time: int,
    ) -> list[dict[str, Any]]:
        """Get incidents from RSA Security Analytics.

        Args:
            session_id: Session ID cookie value
            incident_manager_id: Incident manager device ID
            limit: Maximum incidents to retrieve
            start_time: Start time in milliseconds (0 for no filter)
            end_time: End time in milliseconds (0 for no filter)

        Returns:
            list: List of incident dictionaries
        """
        url = self.settings.get(consts.SETTINGS_URL).rstrip("/")
        verify_ssl = self.settings.get(consts.SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(consts.SETTINGS_TIMEOUT, consts.DEFAULT_TIMEOUT)

        endpoint = consts.ENDPOINT_INCIDENTS.format(
            incident_manager_id=incident_manager_id
        )
        query_params = {
            "limit": limit,
            "start": 0,
            "sort": '[{"property": "created", "direction": "DESC"}]',
        }

        if start_time and end_time:
            query_params["filter"] = (
                f'[{{"property": "created", "value": [{start_time}, {end_time}]}}]'
            )

        query_params["_dc"] = int(time.time() * 1000)

        cookie_header = {"Cookie": f"JSESSIONID={session_id}"}
        response = await self.http_request(
            f"{url}{endpoint}",
            params=query_params,
            headers=cookie_header,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )

        data = response.json()
        if not data.get("success"):
            raise ValueError(f"API call failed: {data.get('message', 'Unknown error')}")

        return data.get("data", [])

class ListAlertsAction(IntegrationAction):
    """List alerts for an incident from RSA Security Analytics."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List alerts for an incident.

        Args:
            id: Incident ID (optional - if not provided, lists all recent alerts)
            limit: Maximum number of alerts to list (default: 100)

        Returns:
            dict: Alerts list with count and data
        """
        try:
            # Extract parameters
            incident_id = kwargs.get("id")
            limit = kwargs.get("limit", consts.DEFAULT_ALERT_LIMIT)

            # Validate credentials
            url = self.settings.get(consts.SETTINGS_URL)
            username = self.credentials.get(consts.CREDENTIAL_USERNAME)
            password = self.credentials.get(consts.CREDENTIAL_PASSWORD)

            if not url or not username or not password:
                return {
                    "status": consts.STATUS_ERROR,
                    "error_type": consts.ERROR_TYPE_CONFIGURATION,
                    "error": consts.MSG_MISSING_CREDENTIALS,
                }

            # Login
            csrf_token, session_id = await self._login()

            try:
                # Get incident manager ID
                incident_manager_id = await self._get_incident_manager_id(
                    csrf_token, session_id
                )

                # Get alerts
                alerts = await self._get_alerts(
                    session_id, incident_manager_id, incident_id, limit
                )

                return {
                    "status": consts.STATUS_SUCCESS,
                    "num_alerts": len(alerts),
                    "alerts": alerts,
                }

            finally:
                # Always logout
                await self._logout(session_id)

        except httpx.HTTPStatusError as e:
            return {
                "status": consts.STATUS_ERROR,
                "error_type": consts.ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": consts.STATUS_ERROR,
                "error_type": consts.ERROR_TYPE_CONNECTION,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": consts.STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

    async def _login(self) -> tuple[str, str]:
        """Login helper."""
        url = self.settings.get(consts.SETTINGS_URL).rstrip("/")
        username = self.credentials.get(consts.CREDENTIAL_USERNAME)
        password = self.credentials.get(consts.CREDENTIAL_PASSWORD)
        verify_ssl = self.settings.get(consts.SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(consts.SETTINGS_TIMEOUT, consts.DEFAULT_TIMEOUT)

        login_url = f"{url}{consts.ENDPOINT_LOGIN}"
        login_data = {"j_username": username, "j_password": password}

        response = await self.http_request(
            login_url,
            method="POST",
            data=login_data,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )

        search_token = '"csrf-token" content="'
        if search_token not in response.text:
            raise ValueError(consts.MSG_CSRF_TOKEN_NOT_FOUND)

        csrf_index = re.search(search_token, response.text).end()
        csrf_token = response.text[csrf_index : csrf_index + 36]

        session_id = response.cookies.get("JSESSIONID")
        if not session_id:
            raise ValueError(consts.MSG_SESSION_ID_MISSING)

        return csrf_token, session_id

    async def _get_incident_manager_id(self, csrf_token: str, session_id: str) -> str:
        """Get incident manager ID helper."""
        url = self.settings.get(consts.SETTINGS_URL).rstrip("/")
        incident_manager_name = self.settings.get(consts.SETTINGS_INCIDENT_MANAGER)
        verify_ssl = self.settings.get(consts.SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(consts.SETTINGS_TIMEOUT, consts.DEFAULT_TIMEOUT)

        endpoint = consts.ENDPOINT_DEVICES_TYPES.format(
            device_type="INCIDENT_MANAGEMENT"
        )
        query_params = {
            "page": 1,
            "start": 0,
            "limit": 100,
            "sort": [{"property": "displayType", "direction": "ASC"}],
        }

        cookie_header = {"Cookie": f"JSESSIONID={session_id}"}
        response = await self.http_request(
            f"{url}{endpoint}",
            params=query_params,
            headers=cookie_header,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )

        data = response.json()
        if not data.get("success"):
            raise ValueError(f"API call failed: {data.get('message', 'Unknown error')}")

        devices = data.get("data")
        if not devices:
            raise ValueError(consts.MSG_NO_DEVICES_FOUND)

        names = [device["displayName"] for device in devices]
        try:
            matched_index = names.index(incident_manager_name)
        except ValueError:
            raise ValueError(
                f"{consts.MSG_INCIDENT_MANAGER_NOT_FOUND}: '{incident_manager_name}'"
            )

        incident_manager_id = devices[matched_index].get("id")
        if not incident_manager_id:
            raise ValueError(f"Could not get ID for device '{incident_manager_name}'")

        return str(incident_manager_id)

    async def _logout(self, session_id: str) -> None:
        """Logout helper."""
        url = self.settings.get(consts.SETTINGS_URL).rstrip("/")
        verify_ssl = self.settings.get(consts.SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(consts.SETTINGS_TIMEOUT, consts.DEFAULT_TIMEOUT)

        logout_url = f"{url}{consts.ENDPOINT_LOGOUT}"

        with contextlib.suppress(Exception):
            await self.http_request(
                logout_url,
                headers={"Cookie": f"JSESSIONID={session_id}"},
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

    async def _get_alerts(
        self,
        session_id: str,
        incident_manager_id: str,
        incident_id: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Get alerts from RSA Security Analytics.

        Args:
            session_id: Session ID cookie value
            incident_manager_id: Incident manager device ID
            incident_id: Incident ID (None for all alerts)
            limit: Maximum alerts to retrieve

        Returns:
            list: List of alert dictionaries
        """
        url = self.settings.get(consts.SETTINGS_URL).rstrip("/")
        verify_ssl = self.settings.get(consts.SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(consts.SETTINGS_TIMEOUT, consts.DEFAULT_TIMEOUT)

        endpoint = consts.ENDPOINT_ALERTS.format(
            incident_manager_id=incident_manager_id
        )
        query_params = {
            "start": 0,
            "limit": limit if limit is not None else consts.DEFAULT_PAGE_SIZE,
            "sort": '[{"property": "alert.timestamp", "direction": "DESC"}]',
        }

        if incident_id:
            query_params["filter"] = (
                f'[{{"property": "incidentId", "value": "{incident_id}"}}]'
            )
        else:
            query_params["filter"] = (
                f'[{{"property": "alert.timestamp", "value": [{consts.DEFAULT_START_TIME}, {int(time.time()) * 1000}]}}]'
            )

        query_params["_dc"] = int(time.time() * 1000)

        # Paginate through results
        alerts = []
        page = 1
        total = 0

        cookie_header = {"Cookie": f"JSESSIONID={session_id}"}
        while True:
            query_params["page"] = page

            response = await self.http_request(
                f"{url}{endpoint}",
                params=query_params,
                headers=cookie_header,
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

            data = response.json()
            if not data.get("success"):
                raise ValueError(
                    f"API call failed: {data.get('message', 'Unknown error')}"
                )

            if not total:
                total = data.get("total", 0)

            alerts.extend(data.get("data", []))

            len_alerts = len(alerts)
            if len_alerts == total or (limit and len_alerts >= limit):
                break

            page += 1

        return alerts

class ListEventsAction(IntegrationAction):
    """List events for an alert from RSA Security Analytics."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List events for an alert.

        Args:
            id: Alert ID (required)
            limit: Maximum number of events to list (default: 100)

        Returns:
            dict: Events list with count and data
        """
        try:
            # Extract parameters
            alert_id = kwargs.get("id")
            limit = kwargs.get("limit", consts.DEFAULT_EVENT_LIMIT)

            # Validate required parameter
            if not alert_id:
                return {
                    "status": consts.STATUS_ERROR,
                    "error_type": consts.ERROR_TYPE_VALIDATION,
                    "error": "Missing required parameter 'id' (alert ID)",
                }

            # Validate credentials
            url = self.settings.get(consts.SETTINGS_URL)
            username = self.credentials.get(consts.CREDENTIAL_USERNAME)
            password = self.credentials.get(consts.CREDENTIAL_PASSWORD)

            if not url or not username or not password:
                return {
                    "status": consts.STATUS_ERROR,
                    "error_type": consts.ERROR_TYPE_CONFIGURATION,
                    "error": consts.MSG_MISSING_CREDENTIALS,
                }

            # Login
            csrf_token, session_id = await self._login()

            try:
                # Get incident manager ID
                incident_manager_id = await self._get_incident_manager_id(
                    csrf_token, session_id
                )

                # Get events
                events = await self._get_events(
                    session_id, incident_manager_id, alert_id, limit
                )

                return {
                    "status": consts.STATUS_SUCCESS,
                    "num_events": len(events),
                    "events": events,
                }

            finally:
                # Always logout
                await self._logout(session_id)

        except httpx.HTTPStatusError as e:
            return {
                "status": consts.STATUS_ERROR,
                "error_type": consts.ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": consts.STATUS_ERROR,
                "error_type": consts.ERROR_TYPE_CONNECTION,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": consts.STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

    async def _login(self) -> tuple[str, str]:
        """Login helper."""
        url = self.settings.get(consts.SETTINGS_URL).rstrip("/")
        username = self.credentials.get(consts.CREDENTIAL_USERNAME)
        password = self.credentials.get(consts.CREDENTIAL_PASSWORD)
        verify_ssl = self.settings.get(consts.SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(consts.SETTINGS_TIMEOUT, consts.DEFAULT_TIMEOUT)

        login_url = f"{url}{consts.ENDPOINT_LOGIN}"
        login_data = {"j_username": username, "j_password": password}

        response = await self.http_request(
            login_url,
            method="POST",
            data=login_data,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )

        search_token = '"csrf-token" content="'
        if search_token not in response.text:
            raise ValueError(consts.MSG_CSRF_TOKEN_NOT_FOUND)

        csrf_index = re.search(search_token, response.text).end()
        csrf_token = response.text[csrf_index : csrf_index + 36]

        session_id = response.cookies.get("JSESSIONID")
        if not session_id:
            raise ValueError(consts.MSG_SESSION_ID_MISSING)

        return csrf_token, session_id

    async def _get_incident_manager_id(self, csrf_token: str, session_id: str) -> str:
        """Get incident manager ID helper."""
        url = self.settings.get(consts.SETTINGS_URL).rstrip("/")
        incident_manager_name = self.settings.get(consts.SETTINGS_INCIDENT_MANAGER)
        verify_ssl = self.settings.get(consts.SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(consts.SETTINGS_TIMEOUT, consts.DEFAULT_TIMEOUT)

        endpoint = consts.ENDPOINT_DEVICES_TYPES.format(
            device_type="INCIDENT_MANAGEMENT"
        )
        query_params = {
            "page": 1,
            "start": 0,
            "limit": 100,
            "sort": [{"property": "displayType", "direction": "ASC"}],
        }

        cookie_header = {"Cookie": f"JSESSIONID={session_id}"}
        response = await self.http_request(
            f"{url}{endpoint}",
            params=query_params,
            headers=cookie_header,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )

        data = response.json()
        if not data.get("success"):
            raise ValueError(f"API call failed: {data.get('message', 'Unknown error')}")

        devices = data.get("data")
        if not devices:
            raise ValueError(consts.MSG_NO_DEVICES_FOUND)

        names = [device["displayName"] for device in devices]
        try:
            matched_index = names.index(incident_manager_name)
        except ValueError:
            raise ValueError(
                f"{consts.MSG_INCIDENT_MANAGER_NOT_FOUND}: '{incident_manager_name}'"
            )

        incident_manager_id = devices[matched_index].get("id")
        if not incident_manager_id:
            raise ValueError(f"Could not get ID for device '{incident_manager_name}'")

        return str(incident_manager_id)

    async def _logout(self, session_id: str) -> None:
        """Logout helper."""
        url = self.settings.get(consts.SETTINGS_URL).rstrip("/")
        verify_ssl = self.settings.get(consts.SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(consts.SETTINGS_TIMEOUT, consts.DEFAULT_TIMEOUT)

        logout_url = f"{url}{consts.ENDPOINT_LOGOUT}"

        with contextlib.suppress(Exception):
            await self.http_request(
                logout_url,
                headers={"Cookie": f"JSESSIONID={session_id}"},
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

    async def _get_events(
        self, session_id: str, incident_manager_id: str, alert_id: str, limit: int
    ) -> list[dict[str, Any]]:
        """Get events from RSA Security Analytics.

        Args:
            session_id: Session ID cookie value
            incident_manager_id: Incident manager device ID
            alert_id: Alert ID
            limit: Maximum events to retrieve

        Returns:
            list: List of event dictionaries
        """
        url = self.settings.get(consts.SETTINGS_URL).rstrip("/")
        verify_ssl = self.settings.get(consts.SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(consts.SETTINGS_TIMEOUT, consts.DEFAULT_TIMEOUT)

        endpoint = consts.ENDPOINT_EVENTS.format(
            incident_manager_id=incident_manager_id, alert_id=alert_id
        )
        query_params = {
            "start": 0,
            "limit": limit if limit is not None else consts.DEFAULT_PAGE_SIZE,
            "sort": '[{"property": "timestamp", "direction": "DESC"}]',
        }

        query_params["_dc"] = int(time.time() * 1000)

        # Paginate through results
        events = []
        page = 1
        total = 0

        cookie_header = {"Cookie": f"JSESSIONID={session_id}"}
        while True:
            query_params["page"] = page

            response = await self.http_request(
                f"{url}{endpoint}",
                params=query_params,
                headers=cookie_header,
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

            data = response.json()
            if not data.get("success"):
                raise ValueError(
                    f"API call failed: {data.get('message', 'Unknown error')}"
                )

            if not total:
                total = data.get("total", 0)

            events.extend(data.get("data", []))

            len_events = len(events)
            if len_events == total or (limit and len_events >= limit):
                break

            page += 1

        return events

class ListDevicesAction(IntegrationAction):
    """List devices from RSA Security Analytics."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List devices connected to RSA Security Analytics.

        Returns:
            dict: Devices list with count and data
        """
        try:
            # Validate credentials
            url = self.settings.get(consts.SETTINGS_URL)
            username = self.credentials.get(consts.CREDENTIAL_USERNAME)
            password = self.credentials.get(consts.CREDENTIAL_PASSWORD)

            if not url or not username or not password:
                return {
                    "status": consts.STATUS_ERROR,
                    "error_type": consts.ERROR_TYPE_CONFIGURATION,
                    "error": consts.MSG_MISSING_CREDENTIALS,
                }

            # Login
            csrf_token, session_id = await self._login()

            try:
                # Get devices
                devices = await self._get_devices(session_id)

                return {
                    "status": consts.STATUS_SUCCESS,
                    "num_devices": len(devices),
                    "devices": devices,
                }

            finally:
                # Always logout
                await self._logout(session_id)

        except httpx.HTTPStatusError as e:
            return {
                "status": consts.STATUS_ERROR,
                "error_type": consts.ERROR_TYPE_HTTP,
                "error": f"HTTP {e.response.status_code}: {e!s}",
            }
        except httpx.RequestError as e:
            return {
                "status": consts.STATUS_ERROR,
                "error_type": consts.ERROR_TYPE_CONNECTION,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": consts.STATUS_ERROR,
                "error_type": type(e).__name__,
                "error": str(e),
            }

    async def _login(self) -> tuple[str, str]:
        """Login helper."""
        url = self.settings.get(consts.SETTINGS_URL).rstrip("/")
        username = self.credentials.get(consts.CREDENTIAL_USERNAME)
        password = self.credentials.get(consts.CREDENTIAL_PASSWORD)
        verify_ssl = self.settings.get(consts.SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(consts.SETTINGS_TIMEOUT, consts.DEFAULT_TIMEOUT)

        login_url = f"{url}{consts.ENDPOINT_LOGIN}"
        login_data = {"j_username": username, "j_password": password}

        response = await self.http_request(
            login_url,
            method="POST",
            data=login_data,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )

        search_token = '"csrf-token" content="'
        if search_token not in response.text:
            raise ValueError(consts.MSG_CSRF_TOKEN_NOT_FOUND)

        csrf_index = re.search(search_token, response.text).end()
        csrf_token = response.text[csrf_index : csrf_index + 36]

        session_id = response.cookies.get("JSESSIONID")
        if not session_id:
            raise ValueError(consts.MSG_SESSION_ID_MISSING)

        return csrf_token, session_id

    async def _logout(self, session_id: str) -> None:
        """Logout helper."""
        url = self.settings.get(consts.SETTINGS_URL).rstrip("/")
        verify_ssl = self.settings.get(consts.SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(consts.SETTINGS_TIMEOUT, consts.DEFAULT_TIMEOUT)

        logout_url = f"{url}{consts.ENDPOINT_LOGOUT}"

        with contextlib.suppress(Exception):
            await self.http_request(
                logout_url,
                headers={"Cookie": f"JSESSIONID={session_id}"},
                timeout=timeout,
                verify_ssl=verify_ssl,
            )

    async def _get_devices(self, session_id: str) -> list[dict[str, Any]]:
        """Get devices from RSA Security Analytics.

        Args:
            session_id: Session ID cookie value

        Returns:
            list: List of device dictionaries
        """
        url = self.settings.get(consts.SETTINGS_URL).rstrip("/")
        verify_ssl = self.settings.get(consts.SETTINGS_VERIFY_SSL, False)
        timeout = self.settings.get(consts.SETTINGS_TIMEOUT, consts.DEFAULT_TIMEOUT)

        endpoint = consts.ENDPOINT_DEVICES
        query_params = {"page": 1, "start": 0, "limit": 0}
        query_params["_dc"] = int(time.time() * 1000)

        cookie_header = {"Cookie": f"JSESSIONID={session_id}"}
        response = await self.http_request(
            f"{url}{endpoint}",
            params=query_params,
            headers=cookie_header,
            timeout=timeout,
            verify_ssl=verify_ssl,
        )

        data = response.json()
        if not data.get("success"):
            raise ValueError(f"API call failed: {data.get('message', 'Unknown error')}")

        devices = data.get("data", [])
        if not devices:
            raise ValueError(consts.MSG_NO_DEVICES_FOUND)

        return devices
