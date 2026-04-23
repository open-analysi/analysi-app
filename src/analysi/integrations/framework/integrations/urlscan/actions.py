"""urlscan.io integration actions for URL analysis and threat intelligence."""

import asyncio
import ipaddress
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.integrations.urlscan.constants import (
    BAD_REQUEST_CODE,
    DEFAULT_TIMEOUT,
    ENDPOINT_RESULT,
    ENDPOINT_SCAN,
    ENDPOINT_SCREENSHOT,
    ENDPOINT_SEARCH,
    ENDPOINT_USER_QUOTAS,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP_ERROR,
    ERROR_TYPE_REQUEST_ERROR,
    ERROR_TYPE_TIMEOUT,
    ERROR_TYPE_VALIDATION,
    MAX_POLLING_ATTEMPTS,
    MAX_TAGS,
    MSG_INVALID_IP,
    MSG_MISSING_API_KEY,
    MSG_MISSING_DOMAIN,
    MSG_MISSING_IP,
    MSG_MISSING_REPORT_ID,
    MSG_MISSING_URL,
    MSG_NO_DATA,
    MSG_REPORT_NOT_FOUND,
    MSG_REPORT_UUID_MISSING,
    MSG_TAGS_EXCEED_MAX,
    NOT_FOUND_CODE,
    POLLING_INTERVAL,
    STATUS_ERROR,
    STATUS_SUCCESS,
    URLSCAN_BASE_URL,
)

logger = get_logger(__name__)

# ============================================================================
# VALIDATION UTILITIES
# ============================================================================

def _validate_ip(ip_address: str) -> tuple[bool, str]:
    """Validate IP address format.

    Args:
        ip_address: IP address to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not ip_address or not isinstance(ip_address, str):
        return False, "IP address must be a non-empty string"
    try:
        ipaddress.ip_address(ip_address)
        return True, ""
    except ValueError:
        return False, MSG_INVALID_IP

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for urlscan.io API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check urlscan.io API connectivity.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        api_key = self.credentials.get("api_key", "")
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            url = f"{URLSCAN_BASE_URL}{ENDPOINT_USER_QUOTAS}"
            headers = {}
            if api_key:
                headers["API-Key"] = api_key

            await self.http_request(url, headers=headers, timeout=timeout)

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "urlscan.io API is accessible",
                "data": {"healthy": True},
            }

        except httpx.TimeoutException as e:
            logger.error("urlscanio_health_check_timeout", error=str(e))
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": f"Request timed out after {timeout} seconds",
                "error_type": ERROR_TYPE_TIMEOUT,
                "data": {"healthy": False},
            }
        except httpx.HTTPStatusError as e:
            logger.error(
                "urlscanio_health_check_http_error", status_code=e.response.status_code
            )
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
                "error_type": ERROR_TYPE_HTTP_ERROR,
                "data": {"healthy": False},
            }
        except httpx.RequestError as e:
            logger.error("urlscanio_health_check_request_error", error=str(e))
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_REQUEST_ERROR,
                "data": {"healthy": False},
            }

class GetReportAction(IntegrationAction):
    """Get analysis report for a submission."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get report for a urlscan.io submission.

        Args:
            **kwargs: Must contain 'id' (report UUID)

        Returns:
            Result with report data or error
        """
        report_id = kwargs.get("id")
        if not report_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_REPORT_ID,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        api_key = self.credentials.get("api_key", "")
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            url = f"{URLSCAN_BASE_URL}{ENDPOINT_RESULT.format(report_id)}"
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["API-Key"] = api_key

            # Poll for results
            for attempt in range(MAX_POLLING_ATTEMPTS):
                response = await self.http_request(
                    url, headers=headers, timeout=timeout
                )

                # Check if scan is complete
                if response.status_code == 200:
                    data = response.json()

                    # Check if still processing
                    if data.get("message") == "notdone":
                        if attempt < MAX_POLLING_ATTEMPTS - 1:
                            await asyncio.sleep(POLLING_INTERVAL)
                            continue
                        return {
                            "status": STATUS_SUCCESS,
                            "message": MSG_REPORT_NOT_FOUND,
                            "data": {"report_id": report_id, "processing": True},
                        }

                    # Report is ready
                    return {
                        "status": STATUS_SUCCESS,
                        "report_id": report_id,
                        "data": data,
                    }

                if response.status_code == NOT_FOUND_CODE:
                    # Still processing
                    if attempt < MAX_POLLING_ATTEMPTS - 1:
                        await asyncio.sleep(POLLING_INTERVAL)
                        continue
                    return {
                        "status": STATUS_SUCCESS,
                        "message": MSG_REPORT_NOT_FOUND,
                        "data": {"report_id": report_id, "processing": True},
                    }

                if response.status_code == BAD_REQUEST_CODE:
                    error_data = response.json()
                    return {
                        "status": STATUS_ERROR,
                        "error": error_data.get("message", "Bad request"),
                        "error_type": ERROR_TYPE_HTTP_ERROR,
                        "data": error_data,
                    }

                response.raise_for_status()

            # Max attempts reached
            return {
                "status": STATUS_SUCCESS,
                "message": MSG_REPORT_NOT_FOUND,
                "data": {"report_id": report_id, "processing": True},
            }

        except httpx.TimeoutException as e:
            logger.error("urlscanio_getreport_timeout", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out after {timeout} seconds",
                "error_type": ERROR_TYPE_TIMEOUT,
            }
        except httpx.HTTPStatusError as e:
            logger.error(
                "urlscanio_getreport_http_error", status_code=e.response.status_code
            )
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
                "error_type": ERROR_TYPE_HTTP_ERROR,
            }
        except httpx.RequestError as e:
            logger.error("urlscanio_getreport_request_error", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_REQUEST_ERROR,
            }

class HuntDomainAction(IntegrationAction):
    """Hunt for URLs associated with a domain."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search for domain in urlscan.io database.

        Args:
            **kwargs: Must contain 'domain'

        Returns:
            Result with search results or error
        """
        domain = kwargs.get("domain")
        if not domain:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_DOMAIN,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        api_key = self.credentials.get("api_key")
        if not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_API_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            url = f"{URLSCAN_BASE_URL}{ENDPOINT_SEARCH}?q=domain:{domain}"
            headers = {"API-Key": api_key}

            response = await self.http_request(url, headers=headers, timeout=timeout)
            data = response.json()

            results = data.get("results", [])
            if results:
                return {
                    "status": STATUS_SUCCESS,
                    "domain": domain,
                    "results_count": len(results),
                    "data": data,
                }
            return {
                "status": STATUS_SUCCESS,
                "message": MSG_NO_DATA,
                "domain": domain,
                "results_count": 0,
                "data": data,
            }

        except httpx.TimeoutException as e:
            logger.error("urlscanio_huntdomain_timeout", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out after {timeout} seconds",
                "error_type": ERROR_TYPE_TIMEOUT,
            }
        except httpx.HTTPStatusError as e:
            logger.error(
                "urlscanio_huntdomain_http_error", status_code=e.response.status_code
            )
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
                "error_type": ERROR_TYPE_HTTP_ERROR,
            }
        except httpx.RequestError as e:
            logger.error("urlscanio_huntdomain_request_error", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_REQUEST_ERROR,
            }

class HuntIpAction(IntegrationAction):
    """Hunt for URLs associated with an IP address."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search for IP in urlscan.io database.

        Args:
            **kwargs: Must contain 'ip'

        Returns:
            Result with search results or error
        """
        ip = kwargs.get("ip")
        if not ip:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_IP,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate IP format
        is_valid, error_msg = _validate_ip(ip)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        api_key = self.credentials.get("api_key")
        if not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_API_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            url = f'{URLSCAN_BASE_URL}{ENDPOINT_SEARCH}?q=ip:"{ip}"'
            headers = {"API-Key": api_key}

            response = await self.http_request(url, headers=headers, timeout=timeout)
            data = response.json()

            results = data.get("results", [])
            if results:
                return {
                    "status": STATUS_SUCCESS,
                    "ip": ip,
                    "results_count": len(results),
                    "data": data,
                }
            return {
                "status": STATUS_SUCCESS,
                "message": MSG_NO_DATA,
                "ip": ip,
                "results_count": 0,
                "data": data,
            }

        except httpx.TimeoutException as e:
            logger.error("urlscanio_huntip_timeout", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out after {timeout} seconds",
                "error_type": ERROR_TYPE_TIMEOUT,
            }
        except httpx.HTTPStatusError as e:
            logger.error(
                "urlscanio_huntip_http_error", status_code=e.response.status_code
            )
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
                "error_type": ERROR_TYPE_HTTP_ERROR,
            }
        except httpx.RequestError as e:
            logger.error("urlscanio_huntip_request_error", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_REQUEST_ERROR,
            }

class DetonateUrlAction(IntegrationAction):
    """Submit a URL for analysis (detonation)."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Submit URL for analysis to urlscan.io.

        Args:
            **kwargs: Must contain 'url'. Optional: 'private' (bool), 'tags' (str),
                     'custom_agent' (str), 'get_result' (bool)

        Returns:
            Result with submission UUID or error
        """
        url = kwargs.get("url")
        if not url:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_URL,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        api_key = self.credentials.get("api_key")
        if not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_API_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        # Parse optional parameters
        private = kwargs.get("private", False)
        tags_str = kwargs.get("tags", "")
        custom_agent = kwargs.get("custom_agent")
        get_result = kwargs.get("get_result", True)

        # Parse and validate tags
        tags = []
        if tags_str:
            tags = [tag.strip() for tag in tags_str.split(",") if tag.strip()]
            tags = list(set(tags))  # Remove duplicates
            if len(tags) > MAX_TAGS:
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_TAGS_EXCEED_MAX,
                    "error_type": ERROR_TYPE_VALIDATION,
                }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            api_url = f"{URLSCAN_BASE_URL}{ENDPOINT_SCAN}"
            headers = {
                "Content-Type": "application/json",
                "API-Key": api_key,
            }

            data = {
                "url": url,
                "public": "off" if private else "on",
                "tags": tags,
            }

            if custom_agent:
                data["customagent"] = custom_agent

            response = await self.http_request(
                api_url,
                method="POST",
                headers=headers,
                json_data=data,
                timeout=timeout,
            )

            # Handle bad request
            if response.status_code == BAD_REQUEST_CODE:
                error_data = response.json()
                return {
                    "status": STATUS_SUCCESS,
                    "message": f"Bad request: {error_data.get('message', 'Unknown')}",
                    "data": error_data,
                }

            result = response.json()

            report_uuid = result.get("uuid")
            if not report_uuid:
                return {
                    "status": STATUS_ERROR,
                    "error": MSG_REPORT_UUID_MISSING,
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            # If get_result is True, poll for the report
            if get_result:
                report_action = GetReportAction(
                    credentials=self.credentials,
                    settings=self.settings,
                    integration_id=self.integration_id,
                )
                report_result = await report_action.execute(id=report_uuid)

                # Merge submission info with report result
                if report_result.get("status") == STATUS_SUCCESS:
                    report_result["submission_info"] = result
                return report_result

            # Return submission info without waiting for results
            return {
                "status": STATUS_SUCCESS,
                "url": url,
                "uuid": report_uuid,
                "message": "URL submitted for analysis",
                "data": result,
            }

        except httpx.TimeoutException as e:
            logger.error("urlscanio_detonateurl_timeout", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out after {timeout} seconds",
                "error_type": ERROR_TYPE_TIMEOUT,
            }
        except httpx.HTTPStatusError as e:
            logger.error(
                "urlscanio_detonateurl_http_error", status_code=e.response.status_code
            )
            return {
                "status": STATUS_ERROR,
                "error": f"HTTP {e.response.status_code}: {e.response.text}",
                "error_type": ERROR_TYPE_HTTP_ERROR,
            }
        except httpx.RequestError as e:
            logger.error("urlscanio_detonateurl_request_error", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_REQUEST_ERROR,
            }

class GetScreenshotAction(IntegrationAction):
    """Get screenshot for a submission."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get screenshot for a urlscan.io submission.

        Args:
            **kwargs: Must contain 'report_id' (UUID of the report)

        Returns:
            Result with screenshot data (base64 encoded) or error
        """
        report_id = kwargs.get("report_id")
        if not report_id:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_REPORT_ID,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            url = f"{URLSCAN_BASE_URL}{ENDPOINT_SCREENSHOT.format(report_id)}"

            response = await self.http_request(url, timeout=timeout)

            if response.status_code == 200:
                # Screenshot available
                import base64

                screenshot_base64 = base64.b64encode(response.content).decode("utf-8")
                content_type = response.headers.get("content-type", "image/png")

                return {
                    "status": STATUS_SUCCESS,
                    "report_id": report_id,
                    "screenshot": screenshot_base64,
                    "content_type": content_type,
                    "size": len(response.content),
                }
            return {
                "status": STATUS_ERROR,
                "error": f"Screenshot not available (HTTP {response.status_code})",
                "error_type": ERROR_TYPE_HTTP_ERROR,
            }

        except httpx.TimeoutException as e:
            logger.error("urlscanio_getscreenshot_timeout", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out after {timeout} seconds",
                "error_type": ERROR_TYPE_TIMEOUT,
            }
        except httpx.RequestError as e:
            logger.error("urlscanio_getscreenshot_request_error", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": ERROR_TYPE_REQUEST_ERROR,
            }
