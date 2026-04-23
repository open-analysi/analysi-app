"""Tor integration actions.

This module provides actions to check whether IP addresses are Tor exit nodes
by querying the Tor Project's public exit node lists. No authentication required.
"""

from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    DEFAULT_TIMEOUT,
    EXIT_ADDRESS_PREFIX,
    TOR_BULK_EXIT_LIST_URL,
    TOR_EXIT_ADDRESSES_URL,
)

logger = get_logger(__name__)

def _parse_exit_addresses(text: str) -> list[str]:
    """Parse IP addresses from the exit-addresses file.

    The file contains lines like:
        ExitAddress 195.154.251.25 2021-06-01 12:00:00

    Args:
        text: Raw text content of the exit-addresses file

    Returns:
        List of IP address strings
    """
    ip_list = []
    for line in text.splitlines():
        if line.startswith(EXIT_ADDRESS_PREFIX):
            parts = line.split()
            if len(parts) >= 2:
                ip_list.append(parts[1])
    return ip_list

def _parse_bulk_exit_list(text: str) -> list[str]:
    """Parse IP addresses from the TorBulkExitList response.

    The response contains one IP per line, with comment lines starting with '#'.

    Args:
        text: Raw text content of the bulk exit list response

    Returns:
        List of IP address strings
    """
    ip_list = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            ip_list.append(line)
    return ip_list

async def _fetch_exit_node_set(ips: list[str] | None, timeout: int) -> set[str]:
    """Fetch the current Tor exit node set from the Tor Project.

    Fetches the primary exit-addresses list and, if specific IPs are provided,
    also queries the TorBulkExitList endpoint for each IP to capture nodes
    that exited within the past 16 hours.

    Args:
        ips: Optional list of IPs to check against the bulk exit list endpoint
        timeout: HTTP request timeout in seconds

    Returns:
        Set of IP addresses that are Tor exit nodes

    Raises:
        httpx.HTTPStatusError: If the Tor Project returns a non-200 response
        httpx.RequestError: If there is a network/connection error
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        # Fetch the primary exit-addresses list
        response = await client.get(TOR_EXIT_ADDRESSES_URL)
        response.raise_for_status()
        exit_address_ips = _parse_exit_addresses(response.text)

        bulk_ips: list[str] = []
        if ips:
            for ip in ips:
                try:
                    bulk_response = await client.get(
                        TOR_BULK_EXIT_LIST_URL, params={"ip": ip}
                    )
                    if bulk_response.status_code == 200:
                        bulk_ips.extend(_parse_bulk_exit_list(bulk_response.text))
                except httpx.RequestError:
                    # If individual IP bulk lookup fails, continue with others
                    logger.warning("tor_bulk_exit_list_request_failed_for_ip", ip=ip)

    return set(exit_address_ips + bulk_ips)

class HealthCheckAction(IntegrationAction):
    """Health check for Tor Project connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity by fetching the Tor exit node list.

        Returns:
            Result with status=success if the exit node list is reachable
        """
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(TOR_EXIT_ADDRESSES_URL)
                response.raise_for_status()

            # Quick parse to count nodes as a sanity check
            exit_node_count = len(_parse_exit_addresses(response.text))

            logger.info("tor_health_check_success", exit_node_count=exit_node_count)
            return {
                "healthy": True,
                "status": "success",
                "message": "Successfully connected to Tor Project exit node list",
                "data": {
                    "healthy": True,
                    "exit_node_count": exit_node_count,
                    "source_url": TOR_EXIT_ADDRESSES_URL,
                },
            }

        except httpx.HTTPStatusError as e:
            logger.error(
                "tor_health_check_http_error",
                status_code=e.response.status_code,
                error=str(e),
            )
            return {
                "healthy": False,
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                "error_type": "HTTPStatusError",
                "data": {"healthy": False},
            }
        except httpx.TimeoutException as e:
            logger.error("tor_health_check_timeout", error=str(e))
            return {
                "healthy": False,
                "status": "error",
                "error": "Request timed out connecting to Tor Project",
                "error_type": "TimeoutError",
                "data": {"healthy": False},
            }
        except httpx.RequestError as e:
            logger.error("tor_health_check_connection_error", error=str(e))
            return {
                "healthy": False,
                "status": "error",
                "error": f"Connection error: {e!s}",
                "error_type": "ConnectionError",
                "data": {"healthy": False},
            }
        except Exception as e:
            logger.error("tor_health_check_unexpected_error", error=str(e))
            return {
                "healthy": False,
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
                "data": {"healthy": False},
            }

class LookupIpAction(IntegrationAction):
    """Check if one or more IP addresses are Tor exit nodes."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check if the given IP(s) are Tor exit nodes.

        Downloads the current Tor exit node list and checks each IP against it.
        Also queries the TorBulkExitList endpoint to catch nodes active in the
        past 16 hours.

        Args:
            **kwargs:
                ip (str): Single IP or comma-separated list of IPs (required)

        Returns:
            Result dict with:
                status (str): "success" or "error"
                results (list): Per-IP dicts with "ip" and "is_exit_node" keys
                num_exit_nodes (int): Count of IPs that are exit nodes
        """
        ip_param = kwargs.get("ip")
        if not ip_param:
            return {
                "status": "error",
                "error": "Missing required parameter: ip",
                "error_type": "ValidationError",
            }

        # Parse comma-separated IP list (matches the upstream behaviour)
        ips = [x.strip() for x in str(ip_param).split(",")]
        ips = [ip for ip in ips if ip]  # remove empty strings

        if not ips:
            return {
                "status": "error",
                "error": "No valid IPs provided",
                "error_type": "ValidationError",
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            exit_node_set = await _fetch_exit_node_set(ips, timeout)

            results = []
            num_exit_nodes = 0
            for ip in ips:
                is_exit_node = ip in exit_node_set
                if is_exit_node:
                    num_exit_nodes += 1
                results.append({"ip": ip, "is_exit_node": is_exit_node})

            logger.info(
                "tor_lookup_ip_success",
                ip_count=len(ips),
                num_exit_nodes=num_exit_nodes,
            )
            return {
                "status": "success",
                "results": results,
                "num_exit_nodes": num_exit_nodes,
            }

        except httpx.HTTPStatusError as e:
            logger.error(
                "tor_lookup_ip_http_error",
                status_code=e.response.status_code,
                error=str(e),
            )
            return {
                "status": "error",
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                "error_type": "HTTPStatusError",
            }
        except httpx.TimeoutException as e:
            logger.error("tor_lookup_ip_timeout", error=str(e))
            return {
                "status": "error",
                "error": "Request timed out fetching Tor exit node list",
                "error_type": "TimeoutError",
            }
        except httpx.RequestError as e:
            logger.error("tor_lookup_ip_connection_error", error=str(e))
            return {
                "status": "error",
                "error": f"Connection error: {e!s}",
                "error_type": "ConnectionError",
            }
        except Exception as e:
            logger.error("tor_lookup_ip_unexpected_error", error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
            }
