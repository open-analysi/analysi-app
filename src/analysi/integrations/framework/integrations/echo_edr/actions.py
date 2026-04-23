"""Echo EDR integration actions.

Echo EDR is a simulated EDR for development, testing, and demos.
Response actions (isolate, release, scan) are stubbed.
"""

from datetime import UTC, datetime
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

logger = get_logger(__name__)

class HealthCheckAction(IntegrationAction):
    """Check health of Echo EDR server connection."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """
        Execute health check.

        Uses standard logging and error handling from base class.

        Returns:
            Standardized result with status, timestamp, integration metadata
        """
        # Get API URL from settings (includes /echo_edr prefix)
        api_url = self.settings.get("api_url", "http://echo-server:8000/echo_edr")

        # Extract base URL (remove /echo_edr suffix for health check)
        # Health check is at root (__health), not under /echo_edr
        if api_url.endswith("/echo_edr"):
            base_url = api_url[: -len("/echo_edr")]
        else:
            base_url = api_url

        self.log_info("Starting health check for Echo EDR", endpoint=base_url)

        try:
            # Prepare headers with credentials
            headers = {}
            if self.credentials and "api_key" in self.credentials:
                headers["Authorization"] = f"Bearer {self.credentials['api_key']}"

            # Call the health endpoint (http_request handles retry internally)
            await self.http_request(
                f"{base_url}/__health", headers=headers, timeout=10.0
            )

            self.log_info("Health check successful", endpoint=api_url)
            return {
                "healthy": True,
                **self.success_result(
                    data={
                        "healthy": True,
                        "message": "Echo EDR connection successful",
                        "api_version": "1.0",
                        "endpoint": api_url,
                    }
                ),
            }

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            self.log_warning(
                f"Health check failed with status {status_code}",
                endpoint=api_url,
                status_code=status_code,
            )
            return {
                "healthy": False,
                **self.error_result(
                    error=f"Health check failed with status {status_code}",
                    error_type="HealthCheckFailed",
                    data={"endpoint": api_url, "status_code": status_code},
                ),
            }

        except httpx.ConnectError as e:
            self.log_error("Connection refused", error=e, endpoint=api_url)
            return {
                "healthy": False,
                **self.error_result(
                    error="Failed to connect to Echo EDR: Connection refused",
                    error_type="ConnectionError",
                    data={"endpoint": api_url},
                ),
            }

        except Exception as e:
            self.log_error(
                "Unexpected error during health check", error=e, endpoint=api_url
            )
            return {
                "healthy": False,
                **self.error_result(
                    error=f"Failed to connect to Echo EDR: {e!s}",
                    data={"endpoint": api_url},
                ),
            }

class PullProcessesAction(IntegrationAction):
    """Pull process data from Echo EDR."""

    async def execute(
        self,
        ip: str,
        start_time: str | None = None,
        end_time: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Pull process data from Echo EDR for a specific IP.

        Args:
            ip: IP address of the endpoint
            start_time: Start time for filtering (ISO format)
            end_time: End time for filtering (ISO format)
            **kwargs: Additional parameters

        Returns:
            Dict with process records and count
        """
        # Get API URL from settings (includes /echo_edr prefix)
        api_url = self.settings.get("api_url", "http://echo-server:8000/echo_edr")

        self.log_info(
            f"Pulling process data for IP {ip} from Echo EDR", endpoint=api_url
        )

        try:
            # Prepare headers with credentials
            headers = {}
            if self.credentials and "api_key" in self.credentials:
                headers["Authorization"] = f"Bearer {self.credentials['api_key']}"

            # Construct URL: api_url already includes /echo_edr
            url = f"{api_url}/devices/ip/{ip}/processes"

            # Make the request (http_request handles retry internally)
            response = await self.http_request(url, headers=headers)
            data = response.json()

            # Filter by time if requested
            if start_time or end_time:
                data = self._filter_by_time(data, start_time, end_time)

            record_count = len(data) if isinstance(data, list) else 0
            self.log_info(f"Retrieved {record_count} process records for IP {ip}")

            return self.success_result(
                data={
                    "records": data,
                    "count": record_count,
                    "ip": ip,
                }
            )

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 404:
                self.log_warning(f"No process data found for IP {ip}")
                return self.success_result(
                    data={
                        "records": [],
                        "count": 0,
                        "ip": ip,
                        "message": f"No process data found for IP {ip}",
                    }
                )
            self.log_error(
                f"Failed to retrieve process data: HTTP {status_code}",
                status_code=status_code,
            )
            return self.error_result(
                error=f"HTTP {status_code}: {e.response.text}",
                error_type="HTTPError",
                data={"ip": ip, "status_code": status_code},
            )

        except httpx.TimeoutException as e:
            self.log_error(f"Timeout retrieving process data for IP {ip}", error=e)
            return self.error_result(
                error="Request timeout", error_type="TimeoutError", data={"ip": ip}
            )
        except httpx.ConnectError as e:
            self.log_error(f"Connection refused for IP {ip}", error=e)
            return self.error_result(
                error="Failed to connect to Echo EDR",
                error_type="ConnectionError",
                data={"ip": ip},
            )
        except Exception as e:
            self.log_error(f"Failed to retrieve process data for IP {ip}", error=e)
            return self.error_result(error=str(e), data={"ip": ip})

    def _filter_by_time(
        self,
        data: Any,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> Any:
        """
        Filter data by time range.

        Args:
            data: Data to filter (can be list or dict with timestamps)
            start_time: Start time for filtering (ISO format)
            end_time: End time for filtering (ISO format)

        Returns:
            Filtered data
        """
        # If no time constraints, return all data
        if not start_time and not end_time:
            return data

        # Parse time strings to datetime objects
        start_dt = None
        end_dt = None
        if start_time:
            try:
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except ValueError:
                logger.warning("invalid_starttime_format", start_time=start_time)

        if end_time:
            try:
                end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            except ValueError:
                logger.warning("invalid_endtime_format", end_time=end_time)

        # If data is a list, filter items with timestamp fields
        if isinstance(data, list):
            filtered = []
            for item in data:
                if isinstance(item, dict) and "timestamp" in item:
                    try:
                        item_dt = datetime.fromisoformat(
                            item["timestamp"].replace("Z", "+00:00")
                        )
                        if start_dt and item_dt < start_dt:
                            continue
                        if end_dt and item_dt > end_dt:
                            continue
                        filtered.append(item)
                    except (ValueError, TypeError):
                        # Include items with invalid timestamps
                        filtered.append(item)
                else:
                    # Include items without timestamp fields
                    filtered.append(item)
            return filtered

        # Return data as-is if we can't filter it
        return data

class PullBrowserHistoryAction(IntegrationAction):
    """Pull browser history data from Echo EDR."""

    async def execute(
        self,
        ip: str,
        start_time: str | None = None,
        end_time: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Pull browser history data from Echo EDR for a specific IP.

        Args:
            ip: IP address of the endpoint
            start_time: Start time for filtering (ISO format)
            end_time: End time for filtering (ISO format)
            **kwargs: Additional parameters

        Returns:
            Dict with browser history records and count
        """
        api_url = self.settings.get("api_url", "http://echo-server:8000/echo_edr")

        self.log_info(
            f"Pulling browser history for IP {ip} from Echo EDR", endpoint=api_url
        )

        try:
            headers = {}
            if self.credentials and "api_key" in self.credentials:
                headers["Authorization"] = f"Bearer {self.credentials['api_key']}"

            url = f"{api_url}/devices/ip/{ip}/browser_history"
            response = await self.http_request(url, headers=headers)
            data = response.json()

            # Filter by time if requested (use visit_time field for browser history)
            if start_time or end_time:
                data = self._filter_by_time(
                    data, start_time, end_time, time_field="visit_time"
                )

            record_count = len(data) if isinstance(data, list) else 0
            self.log_info(
                f"Retrieved {record_count} browser history records for IP {ip}"
            )

            return self.success_result(
                data={
                    "records": data,
                    "count": record_count,
                    "ip": ip,
                }
            )

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 404:
                self.log_warning(f"No browser history found for IP {ip}")
                return self.success_result(
                    data={
                        "records": [],
                        "count": 0,
                        "ip": ip,
                        "message": f"No browser history found for IP {ip}",
                    }
                )
            self.log_error(
                f"Failed to retrieve browser history: HTTP {status_code}",
                status_code=status_code,
            )
            return self.error_result(
                error=f"HTTP {status_code}: {e.response.text}",
                error_type="HTTPError",
                data={"ip": ip, "status_code": status_code},
            )

        except httpx.TimeoutException as e:
            self.log_error(f"Timeout retrieving browser history for IP {ip}", error=e)
            return self.error_result(
                error="Request timeout", error_type="TimeoutError", data={"ip": ip}
            )
        except httpx.ConnectError as e:
            self.log_error(f"Connection refused for IP {ip}", error=e)
            return self.error_result(
                error="Failed to connect to Echo EDR",
                error_type="ConnectionError",
                data={"ip": ip},
            )
        except Exception as e:
            self.log_error(f"Failed to retrieve browser history for IP {ip}", error=e)
            return self.error_result(error=str(e), data={"ip": ip})

    def _filter_by_time(
        self,
        data: Any,
        start_time: str | None = None,
        end_time: str | None = None,
        time_field: str = "timestamp",
    ) -> Any:
        """Filter data by time range using specified time field."""
        if not start_time and not end_time:
            return data

        start_dt = None
        end_dt = None
        if start_time:
            try:
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except ValueError:
                logger.warning("invalid_starttime_format", start_time=start_time)

        if end_time:
            try:
                end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            except ValueError:
                logger.warning("invalid_endtime_format", end_time=end_time)

        if isinstance(data, list):
            filtered = []
            for item in data:
                if isinstance(item, dict) and time_field in item:
                    try:
                        item_dt = datetime.fromisoformat(
                            item[time_field].replace("Z", "+00:00")
                        )
                        if start_dt and item_dt < start_dt:
                            continue
                        if end_dt and item_dt > end_dt:
                            continue
                        filtered.append(item)
                    except (ValueError, TypeError):
                        filtered.append(item)
                else:
                    filtered.append(item)
            return filtered

        return data

class PullNetworkConnectionsAction(IntegrationAction):
    """Pull network connection data from Echo EDR."""

    async def execute(
        self,
        ip: str,
        start_time: str | None = None,
        end_time: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Pull network connection data from Echo EDR for a specific IP.

        Args:
            ip: IP address of the endpoint
            start_time: Start time for filtering (ISO format)
            end_time: End time for filtering (ISO format)
            **kwargs: Additional parameters

        Returns:
            Dict with network connection records and count
        """
        api_url = self.settings.get("api_url", "http://echo-server:8000/echo_edr")

        self.log_info(
            f"Pulling network connections for IP {ip} from Echo EDR", endpoint=api_url
        )

        try:
            headers = {}
            if self.credentials and "api_key" in self.credentials:
                headers["Authorization"] = f"Bearer {self.credentials['api_key']}"

            url = f"{api_url}/devices/ip/{ip}/network_action"
            response = await self.http_request(url, headers=headers)
            data = response.json()

            # Filter by time if requested
            if start_time or end_time:
                data = self._filter_by_time(data, start_time, end_time)

            record_count = len(data) if isinstance(data, list) else 0
            self.log_info(
                f"Retrieved {record_count} network connection records for IP {ip}"
            )

            return self.success_result(
                data={
                    "records": data,
                    "count": record_count,
                    "ip": ip,
                }
            )

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 404:
                self.log_warning(f"No network connections found for IP {ip}")
                return self.success_result(
                    data={
                        "records": [],
                        "count": 0,
                        "ip": ip,
                        "message": f"No network connections found for IP {ip}",
                    }
                )
            self.log_error(
                f"Failed to retrieve network connections: HTTP {status_code}",
                status_code=status_code,
            )
            return self.error_result(
                error=f"HTTP {status_code}: {e.response.text}",
                error_type="HTTPError",
                data={"ip": ip, "status_code": status_code},
            )

        except httpx.TimeoutException as e:
            self.log_error(
                f"Timeout retrieving network connections for IP {ip}", error=e
            )
            return self.error_result(
                error="Request timeout", error_type="TimeoutError", data={"ip": ip}
            )
        except httpx.ConnectError as e:
            self.log_error(f"Connection refused for IP {ip}", error=e)
            return self.error_result(
                error="Failed to connect to Echo EDR",
                error_type="ConnectionError",
                data={"ip": ip},
            )
        except Exception as e:
            self.log_error(
                f"Failed to retrieve network connections for IP {ip}", error=e
            )
            return self.error_result(error=str(e), data={"ip": ip})

    def _filter_by_time(
        self,
        data: Any,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> Any:
        """Filter data by time range."""
        if not start_time and not end_time:
            return data

        start_dt = None
        end_dt = None
        if start_time:
            try:
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except ValueError:
                logger.warning("invalid_starttime_format", start_time=start_time)

        if end_time:
            try:
                end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            except ValueError:
                logger.warning("invalid_endtime_format", end_time=end_time)

        if isinstance(data, list):
            filtered = []
            for item in data:
                if isinstance(item, dict) and "timestamp" in item:
                    try:
                        item_dt = datetime.fromisoformat(
                            item["timestamp"].replace("Z", "+00:00")
                        )
                        if start_dt and item_dt < start_dt:
                            continue
                        if end_dt and item_dt > end_dt:
                            continue
                        filtered.append(item)
                    except (ValueError, TypeError):
                        filtered.append(item)
                else:
                    filtered.append(item)
            return filtered

        return data

class PullTerminalHistoryAction(IntegrationAction):
    """Pull terminal/command history data from Echo EDR."""

    async def execute(
        self,
        ip: str,
        start_time: str | None = None,
        end_time: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Pull terminal history data from Echo EDR for a specific IP.

        Args:
            ip: IP address of the endpoint
            start_time: Start time for filtering (ISO format)
            end_time: End time for filtering (ISO format)
            **kwargs: Additional parameters

        Returns:
            Dict with terminal history records and count
        """
        api_url = self.settings.get("api_url", "http://echo-server:8000/echo_edr")

        self.log_info(
            f"Pulling terminal history for IP {ip} from Echo EDR", endpoint=api_url
        )

        try:
            headers = {}
            if self.credentials and "api_key" in self.credentials:
                headers["Authorization"] = f"Bearer {self.credentials['api_key']}"

            url = f"{api_url}/devices/ip/{ip}/terminal_history"
            response = await self.http_request(url, headers=headers)
            data = response.json()

            # Filter by time if requested
            if start_time or end_time:
                data = self._filter_by_time(data, start_time, end_time)

            record_count = len(data) if isinstance(data, list) else 0
            self.log_info(
                f"Retrieved {record_count} terminal history records for IP {ip}"
            )

            return self.success_result(
                data={
                    "records": data,
                    "count": record_count,
                    "ip": ip,
                }
            )

        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            if status_code == 404:
                self.log_warning(f"No terminal history found for IP {ip}")
                return self.success_result(
                    data={
                        "records": [],
                        "count": 0,
                        "ip": ip,
                        "message": f"No terminal history found for IP {ip}",
                    }
                )
            self.log_error(
                f"Failed to retrieve terminal history: HTTP {status_code}",
                status_code=status_code,
            )
            return self.error_result(
                error=f"HTTP {status_code}: {e.response.text}",
                error_type="HTTPError",
                data={"ip": ip, "status_code": status_code},
            )

        except httpx.TimeoutException as e:
            self.log_error(f"Timeout retrieving terminal history for IP {ip}", error=e)
            return self.error_result(
                error="Request timeout", error_type="TimeoutError", data={"ip": ip}
            )
        except httpx.ConnectError as e:
            self.log_error(f"Connection refused for IP {ip}", error=e)
            return self.error_result(
                error="Failed to connect to Echo EDR",
                error_type="ConnectionError",
                data={"ip": ip},
            )
        except Exception as e:
            self.log_error(f"Failed to retrieve terminal history for IP {ip}", error=e)
            return self.error_result(error=str(e), data={"ip": ip})

    def _filter_by_time(
        self,
        data: Any,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> Any:
        """Filter data by time range."""
        if not start_time and not end_time:
            return data

        start_dt = None
        end_dt = None
        if start_time:
            try:
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except ValueError:
                logger.warning("invalid_starttime_format", start_time=start_time)

        if end_time:
            try:
                end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            except ValueError:
                logger.warning("invalid_endtime_format", end_time=end_time)

        if isinstance(data, list):
            filtered = []
            for item in data:
                if isinstance(item, dict) and "timestamp" in item:
                    try:
                        item_dt = datetime.fromisoformat(
                            item["timestamp"].replace("Z", "+00:00")
                        )
                        if start_dt and item_dt < start_dt:
                            continue
                        if end_dt and item_dt > end_dt:
                            continue
                        filtered.append(item)
                    except (ValueError, TypeError):
                        filtered.append(item)
                else:
                    filtered.append(item)
            return filtered

        return data

# Tool Actions (EDR Archetype) - Stubbed for now

class IsolateHostAction(IntegrationAction):
    """Isolate a host from the network."""

    async def execute(self, hostname: str, **kwargs) -> dict[str, Any]:
        """
        Isolate a host from the network.

        Args:
            hostname: Hostname or IP to isolate
            **kwargs: Additional parameters

        Returns:
            Result of isolation operation
        """
        # Stubbed — Echo EDR is a demo integration
        logger.info("isolating_host", hostname=hostname)
        return {
            "status": "success",
            "message": f"Host {hostname} isolated (mock implementation)",
            "hostname": hostname,
            "timestamp": datetime.now(UTC).isoformat(),
        }

class ReleaseHostAction(IntegrationAction):
    """Release a host from network isolation."""

    async def execute(self, hostname: str, **kwargs) -> dict[str, Any]:
        """
        Release a host from network isolation.

        Args:
            hostname: Hostname or IP to release
            **kwargs: Additional parameters

        Returns:
            Result of release operation
        """
        # Stubbed — Echo EDR is a demo integration
        logger.info("releasing_host", hostname=hostname)
        return {
            "status": "success",
            "message": f"Host {hostname} released (mock implementation)",
            "hostname": hostname,
            "timestamp": datetime.now(UTC).isoformat(),
        }

class ScanHostAction(IntegrationAction):
    """Initiate a security scan on a host."""

    async def execute(
        self, hostname: str, scan_type: str = "full", **kwargs
    ) -> dict[str, Any]:
        """
        Initiate a security scan on a host.

        Args:
            hostname: Hostname or IP to scan
            scan_type: Type of scan (quick, full, custom)
            **kwargs: Additional parameters

        Returns:
            Result of scan initiation
        """
        # Stubbed — Echo EDR is a demo integration
        logger.info("initiating_scan_on_host", scan_type=scan_type, hostname=hostname)
        return {
            "status": "success",
            "message": f"{scan_type.capitalize()} scan initiated on {hostname} (mock implementation)",
            "hostname": hostname,
            "scan_type": scan_type,
            "scan_id": f"scan-{datetime.now(UTC).timestamp()}",
            "timestamp": datetime.now(UTC).isoformat(),
        }

class GetHostDetailsAction(IntegrationAction):
    """Retrieve detailed information about a host."""

    async def execute(self, hostname: str, **kwargs) -> dict[str, Any]:
        """
        Retrieve detailed information about a host.

        Args:
            hostname: Hostname or IP to query
            **kwargs: Additional parameters

        Returns:
            Host details
        """
        # Stubbed — Echo EDR is a demo integration
        logger.info("fetching_details_for_host", hostname=hostname)
        return {
            "status": "success",
            "hostname": hostname,
            "ip_address": "192.168.1.100",
            "os": "Windows 10 Enterprise",
            "os_version": "10.0.19044",
            "agent_version": "1.2.3",
            "last_seen": datetime.now(UTC).isoformat(),
            "risk_level": "low",
            "timestamp": datetime.now(UTC).isoformat(),
        }
