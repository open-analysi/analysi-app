"""ZScaler integration actions for web security gateway management.

This module provides actions for managing ZScaler web security including:
- URL/IP blocking and allowing
- URL/IP lookups
- URL category management
- User and group management
- Sandbox file analysis
"""

import ipaddress
import time
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ACTION_ADD_TO_LIST,
    ACTION_REMOVE_FROM_LIST,
    CREDENTIAL_API_KEY,
    CREDENTIAL_PASSWORD,
    CREDENTIAL_USERNAME,
    DEFAULT_RETRY_COUNT,
    DEFAULT_TIMEOUT,
    ERR_MD5_UNKNOWN_MSG,
    ERROR_TYPE_AUTHENTICATION,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_HTTP,
    ERROR_TYPE_VALIDATION,
    MAX_URL_LENGTH,
    NON_NEGATIVE_INTEGER_MSG,
    POSITIVE_INTEGER_MSG,
    SANDBOX_GET_REPORT_MSG,
    SETTINGS_BASE_URL,
    SETTINGS_TIMEOUT,
    STATUS_ERROR,
    STATUS_SUCCESS,
    VALID_INTEGER_MSG,
)

logger = get_logger(__name__)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _validate_integer(
    value: Any, param_name: str, allow_zero: bool = False
) -> tuple[bool, str, int | None]:
    """Validate an integer parameter.

    Args:
        value: Value to validate
        param_name: Parameter name for error messages
        allow_zero: Whether zero should be considered valid

    Returns:
        Tuple of (is_valid, error_message, validated_value)
    """
    if value is None:
        return True, "", None

    try:
        if isinstance(value, str):
            if not value.replace(".", "").replace("-", "").isdigit():
                return False, VALID_INTEGER_MSG.format(param=param_name), None
            float_val = float(value)
            if not float_val.is_integer():
                return False, VALID_INTEGER_MSG.format(param=param_name), None
            value = int(float_val)
        else:
            value = int(value)

        if value < 0:
            return False, NON_NEGATIVE_INTEGER_MSG.format(param=param_name), None
        if not allow_zero and value == 0:
            return False, POSITIVE_INTEGER_MSG.format(param=param_name), None

        return True, "", value
    except (ValueError, TypeError):
        return False, VALID_INTEGER_MSG.format(param=param_name), None

def _is_ip_address(address: str) -> bool:
    """Check if string is a valid IP address.

    Args:
        address: String to check

    Returns:
        True if valid IPv4 or IPv6 address
    """
    try:
        ipaddress.ip_address(address)
        return True
    except ValueError:
        return False

def _truncate_protocol(endpoints: list[str]) -> list[str]:
    """Remove http:// or https:// protocol prefix from URLs.

    Args:
        endpoints: List of URLs

    Returns:
        List of URLs without protocol prefix
    """
    result = []
    for endpoint in endpoints:
        if endpoint.startswith("http://"):
            result.append(endpoint[len("http://") :])
        elif endpoint.startswith("https://"):
            result.append(endpoint[len("https://") :])
        else:
            result.append(endpoint)
    return result

def _check_url_length(
    endpoints: list[str], max_length: int = MAX_URL_LENGTH
) -> tuple[bool, str]:
    """Check if all URLs are within max length.

    Args:
        endpoints: List of URLs to check
        max_length: Maximum allowed length

    Returns:
        Tuple of (is_valid, error_message)
    """
    for url in endpoints:
        if len(url) > max_length:
            return (
                False,
                f"URL exceeds maximum length of {max_length} characters: {url[:50]}...",
            )
    return True, ""

# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

class ZScalerSession:
    """Manages ZScaler API session with authentication and rate limiting."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        api_key: str,
        timeout: int = DEFAULT_TIMEOUT,
        retry_count: int = DEFAULT_RETRY_COUNT,
        http_request=None,
    ):
        """Initialize ZScaler session.

        Args:
            base_url: ZScaler API base URL
            username: ZScaler username
            password: ZScaler password
            api_key: ZScaler API key
            timeout: Request timeout in seconds
            retry_count: Number of retries for rate limiting
        """
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.api_key = api_key
        self.timeout = timeout
        self.retry_count = retry_count
        self.session_cookie = None
        self._http_request = http_request

    def _obfuscate_api_key(self) -> tuple[str, str]:
        """Obfuscate API key for authentication.

        Returns:
            Tuple of (timestamp, obfuscated_key)
        """
        now = str(int(time.time() * 1000))
        n = now[-6:]
        r = str(int(n) >> 1).zfill(6)
        key = ""
        for i in range(len(n)):
            key += self.api_key[int(n[i])]
        for j in range(len(r)):
            key += self.api_key[int(r[j]) + 2]
        return now, key

    async def authenticate(self) -> dict[str, Any]:
        """Authenticate and create ZScaler session.

        Returns:
            Result dict with status and session info
        """
        try:
            timestamp, obf_api_key = self._obfuscate_api_key()
        except Exception as e:
            logger.error("Failed to obfuscate API key", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": "Error obfuscating API key",
                "error_type": ERROR_TYPE_AUTHENTICATION,
            }

        body = {
            "apiKey": obf_api_key,
            "username": self.username,
            "password": self.password,
            "timestamp": timestamp,
        }

        try:
            if self._http_request:
                response = await self._http_request(
                    f"{self.base_url}/api/v1/authenticatedSession",
                    method="POST",
                    json_data=body,
                    timeout=self.timeout,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/api/v1/authenticatedSession",
                        json=body,
                    )
                    response.raise_for_status()

            # Extract session cookie
            set_cookie = response.headers.get("Set-Cookie", "")
            if set_cookie:
                self.session_cookie = set_cookie.split(";")[0].strip()
                logger.info("ZScaler session authenticated successfully")
                return {
                    "status": STATUS_SUCCESS,
                    "message": "Successfully started ZScaler session",
                }
            return {
                "status": STATUS_ERROR,
                "error": "No session cookie received",
                "error_type": ERROR_TYPE_AUTHENTICATION,
            }

        except httpx.HTTPStatusError as e:
            logger.error(
                "ZScaler authentication failed", status_code=e.response.status_code
            )
            return {
                "status": STATUS_ERROR,
                "error": f"Authentication failed: HTTP {e.response.status_code}",
                "error_type": ERROR_TYPE_AUTHENTICATION,
            }
        except Exception as e:
            logger.error("ZScaler authentication error", error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": f"Error starting ZScaler session: {e!s}",
                "error_type": ERROR_TYPE_AUTHENTICATION,
            }

    async def make_request(  # noqa: C901
        self,
        endpoint: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        use_json: bool = True,
        retry_on_rate_limit: bool = True,
        retries_left: int | None = None,
    ) -> dict[str, Any]:
        """Make authenticated request to ZScaler API.

        Args:
            endpoint: API endpoint path
            method: HTTP method
            params: Query parameters
            data: Request body data
            use_json: Whether to send data as JSON
            retry_on_rate_limit: Whether to retry on rate limit errors
            retries_left: Number of retries remaining (internal)

        Returns:
            Response data or error dict
        """
        if retries_left is None:
            retries_left = self.retry_count

        if not self.session_cookie:
            return {
                "status": STATUS_ERROR,
                "error": "Not authenticated - session cookie missing",
                "error_type": ERROR_TYPE_AUTHENTICATION,
            }

        url = f"{self.base_url}{endpoint}"
        headers = {"cookie": self.session_cookie}

        try:
            # http_request() calls raise_for_status() internally, which turns
            # 409/429 into HTTPStatusError.  We catch those here so the custom
            # Zscaler retry-with-backoff logic below remains reachable.
            try:
                if self._http_request:
                    kwargs = {
                        "method": method,
                        "headers": headers,
                        "params": params,
                        "timeout": self.timeout,
                    }
                    if use_json:
                        kwargs["json_data"] = data
                    else:
                        kwargs["data"] = data
                    response = await self._http_request(url, **kwargs)
                else:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        if use_json:
                            response = await client.request(
                                method, url, headers=headers, params=params, json=data
                            )
                        else:
                            response = await client.request(
                                method, url, headers=headers, params=params, data=data
                            )
            except httpx.HTTPStatusError as e:
                if (
                    e.response.status_code in (409, 429)
                    and retry_on_rate_limit
                    and retries_left > 0
                ):
                    # Let the 409/429 handling below process this response
                    response = e.response
                else:
                    raise

            # Handle rate limiting (409 and 429)
            if response.status_code == 409 and retry_on_rate_limit and retries_left > 0:
                logger.warning("Lock not available (409), retrying in 1 second")
                import asyncio

                await asyncio.sleep(1)
                return await self.make_request(
                    endpoint,
                    method,
                    params,
                    data,
                    use_json,
                    retry_on_rate_limit,
                    retries_left - 1,
                )

            if response.status_code == 429 and retry_on_rate_limit and retries_left > 0:
                try:
                    retry_after = response.json().get("Retry-After", "1 seconds")
                    wait_seconds = self._parse_retry_time(retry_after)
                    logger.warning("Rate limit exceeded", retry_after=retry_after)
                    import asyncio

                    await asyncio.sleep(wait_seconds)
                    return await self.make_request(
                        endpoint,
                        method,
                        params,
                        data,
                        use_json,
                        retry_on_rate_limit,
                        retries_left - 1,
                    )
                except Exception:
                    pass  # Fall through to normal error handling

            # Handle successful empty responses (204)
            if response.status_code == 204:
                return {"status": STATUS_SUCCESS, "data": {}}

            # Handle successful responses with content
            if 200 <= response.status_code < 300:
                if "json" in response.headers.get("Content-Type", ""):
                    return {"status": STATUS_SUCCESS, "data": response.json()}
                if response.text:
                    return {
                        "status": STATUS_SUCCESS,
                        "data": {"text": response.text},
                    }
                return {"status": STATUS_SUCCESS, "data": {}}

            # Handle error responses
            response.raise_for_status()

        except httpx.HTTPStatusError as e:
            logger.error(
                "ZScaler API HTTP error",
                endpoint=endpoint,
                status_code=e.response.status_code,
            )
            error_msg = f"HTTP {e.response.status_code}"
            try:
                error_data = e.response.json()
                if "message" in error_data:
                    error_msg = error_data["message"]
            except Exception:
                error_msg = f"{error_msg}: {e.response.text[:200]}"

            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_HTTP,
                "status_code": e.response.status_code,
            }
        except httpx.TimeoutException:
            logger.error("ZScaler API timeout", endpoint=endpoint)
            return {
                "status": STATUS_ERROR,
                "error": f"Request timed out after {self.timeout} seconds",
                "error_type": ERROR_TYPE_HTTP,
            }
        except Exception as e:
            logger.error("ZScaler API error", endpoint=endpoint, error=str(e))
            return {
                "status": STATUS_ERROR,
                "error": f"Error connecting to ZScaler: {e!s}",
                "error_type": ERROR_TYPE_HTTP,
            }

    @staticmethod
    def _parse_retry_time(retry_time: str) -> int:
        """Parse retry time string to seconds.

        Args:
            retry_time: Retry time string (e.g., "5 seconds", "2 minutes")

        Returns:
            Number of seconds to wait
        """
        parts = retry_time.split()
        if len(parts) >= 2:
            try:
                value = int(parts[0])
                unit = parts[1].lower()
                if unit.startswith("second"):
                    return value
                if unit.startswith("minute"):
                    return value * 60
            except ValueError:
                pass
        return 1  # Default to 1 second

    async def close(self) -> dict[str, Any]:
        """Close ZScaler session.

        Returns:
            Result dict
        """
        if not self.session_cookie:
            return {"status": STATUS_SUCCESS, "message": "No active session"}

        try:
            if self._http_request:
                await self._http_request(
                    f"{self.base_url}/api/v1/authenticatedSession",
                    method="DELETE",
                    headers={"cookie": self.session_cookie},
                    timeout=self.timeout,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    await client.delete(
                        f"{self.base_url}/api/v1/authenticatedSession",
                        headers={"cookie": self.session_cookie},
                    )
            self.session_cookie = None
            logger.info("ZScaler session closed successfully")
            return {"status": STATUS_SUCCESS, "message": "Session closed"}
        except Exception as e:
            logger.warning("Error closing ZScaler session", error=str(e))
            # Still mark as success since session is being cleaned up
            self.session_cookie = None
            return {"status": STATUS_SUCCESS, "message": "Session cleanup completed"}

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for ZScaler API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check ZScaler API connectivity by testing authentication.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        # Extract credentials
        base_url = self.settings.get(SETTINGS_BASE_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        api_key = self.credentials.get(CREDENTIAL_API_KEY)

        if not all([base_url, username, password, api_key]):
            return {
                "status": STATUS_ERROR,
                "error": "Missing required credentials (base_url, username, password, api_key)",
                "error_type": ERROR_TYPE_CONFIGURATION,
                "healthy": False,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        # Create session and test authentication
        session = ZScalerSession(
            base_url,
            username,
            password,
            api_key,
            timeout,
            http_request=self.http_request,
        )
        result = await session.authenticate()

        if result["status"] == STATUS_SUCCESS:
            await session.close()
            return {
                "status": STATUS_SUCCESS,
                "message": "ZScaler API is accessible",
                "healthy": True,
            }
        return {
            "status": STATUS_ERROR,
            "error": result.get("error", "Authentication failed"),
            "error_type": result.get("error_type", ERROR_TYPE_AUTHENTICATION),
            "healthy": False,
        }

class LookupUrlAction(IntegrationAction):
    """Look up URL categorization and blocklist status."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Look up URL information from ZScaler.

        Args:
            **kwargs: Must contain:
                - url (str): Comma-separated list of URLs to look up

        Returns:
            Result with URL lookup data or error
        """
        # Extract and validate URL parameter
        url_param = kwargs.get("url", "").strip()
        if not url_param:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'url'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Parse comma-separated URLs
        urls = [u.strip() for u in url_param.split(",") if u.strip()]
        if not urls:
            return {
                "status": STATUS_ERROR,
                "error": "Please provide valid list of URL(s)",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Truncate protocols
        urls = _truncate_protocol(urls)

        # Check URL lengths
        is_valid, error_msg = _check_url_length(urls)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Extract credentials and create session
        base_url = self.settings.get(SETTINGS_BASE_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        api_key = self.credentials.get(CREDENTIAL_API_KEY)

        if not all([base_url, username, password, api_key]):
            return {
                "status": STATUS_ERROR,
                "error": "Missing required credentials",
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        session = ZScalerSession(
            base_url,
            username,
            password,
            api_key,
            timeout,
            http_request=self.http_request,
        )

        # Authenticate
        auth_result = await session.authenticate()
        if auth_result["status"] != STATUS_SUCCESS:
            return auth_result

        try:
            # Look up URLs
            lookup_result = await session.make_request(
                "/api/v1/urlLookup",
                method="POST",
                data=urls,
            )

            if lookup_result["status"] != STATUS_SUCCESS:
                await session.close()
                if lookup_result.get("status_code") == 404:
                    logger.info("zscaler_url_not_found", urls=urls)
                    return {
                        "status": STATUS_SUCCESS,
                        "not_found": True,
                        "message": "URLs not found in ZScaler",
                        "total_urls": 0,
                        "urls": [],
                    }
                return lookup_result

            # Get blocklist to check if URLs are blocked
            blocklist_result = await session.make_request(
                "/api/v1/security/advanced",
                method="GET",
            )

            lookup_data = lookup_result.get("data", [])
            blocklist_urls = []
            if blocklist_result["status"] == STATUS_SUCCESS:
                blocklist_urls = blocklist_result.get("data", {}).get(
                    "blacklistUrls", []
                )

            # Annotate results with blocklist status
            for i, item in enumerate(lookup_data):
                url = item.get("url", "")
                lookup_data[i]["blocklisted"] = url in blocklist_urls

            await session.close()

            return {
                "status": STATUS_SUCCESS,
                "message": "Successfully completed lookup",
                "total_urls": len(lookup_data),
                "urls": lookup_data,
            }

        except Exception as e:
            logger.error("URL lookup failed", error=str(e))
            await session.close()
            return {
                "status": STATUS_ERROR,
                "error": f"URL lookup failed: {e!s}",
                "error_type": type(e).__name__,
            }

class LookupIpAction(IntegrationAction):
    """Look up IP address categorization and blocklist status."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Look up IP address information from ZScaler.

        Args:
            **kwargs: Must contain:
                - ip (str): Comma-separated list of IP addresses to look up

        Returns:
            Result with IP lookup data or error
        """
        # Extract and validate IP parameter
        ip_param = kwargs.get("ip", "").strip()
        if not ip_param:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'ip'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Parse comma-separated IPs
        ips = [ip.strip() for ip in ip_param.split(",") if ip.strip()]
        if not ips:
            return {
                "status": STATUS_ERROR,
                "error": "Please provide valid list of IP address(es)",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Extract credentials and create session
        base_url = self.settings.get(SETTINGS_BASE_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        api_key = self.credentials.get(CREDENTIAL_API_KEY)

        if not all([base_url, username, password, api_key]):
            return {
                "status": STATUS_ERROR,
                "error": "Missing required credentials",
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        session = ZScalerSession(
            base_url,
            username,
            password,
            api_key,
            timeout,
            http_request=self.http_request,
        )

        # Authenticate
        auth_result = await session.authenticate()
        if auth_result["status"] != STATUS_SUCCESS:
            return auth_result

        try:
            # Look up IPs
            lookup_result = await session.make_request(
                "/api/v1/urlLookup",
                method="POST",
                data=ips,
            )

            if lookup_result["status"] != STATUS_SUCCESS:
                await session.close()
                if lookup_result.get("status_code") == 404:
                    logger.info("zscaler_ip_not_found", ips=ips)
                    return {
                        "status": STATUS_SUCCESS,
                        "not_found": True,
                        "message": "IP addresses not found in ZScaler",
                        "total_ips": 0,
                        "ips": [],
                    }
                return lookup_result

            # Get blocklist to check if IPs are blocked
            blocklist_result = await session.make_request(
                "/api/v1/security/advanced",
                method="GET",
            )

            lookup_data = lookup_result.get("data", [])
            blocklist_urls = []
            if blocklist_result["status"] == STATUS_SUCCESS:
                blocklist_urls = blocklist_result.get("data", {}).get(
                    "blacklistUrls", []
                )

            # Annotate results with blocklist status
            for i, item in enumerate(lookup_data):
                url = item.get("url", "")
                lookup_data[i]["blocklisted"] = url in blocklist_urls

            await session.close()

            return {
                "status": STATUS_SUCCESS,
                "message": "Successfully completed lookup",
                "total_ips": len(lookup_data),
                "ips": lookup_data,
            }

        except Exception as e:
            logger.error("IP lookup failed", error=str(e))
            await session.close()
            return {
                "status": STATUS_ERROR,
                "error": f"IP lookup failed: {e!s}",
                "error_type": type(e).__name__,
            }

class BlockUrlAction(IntegrationAction):
    """Block URL by adding to blocklist or category."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Block URL in ZScaler.

        Args:
            **kwargs: Must contain:
                - url (str): Comma-separated list of URLs to block
                - url_category (str, optional): Category ID to add URLs to

        Returns:
            Result with blocked URLs or error
        """
        # Extract and validate URL parameter
        url_param = kwargs.get("url", "").strip()
        if not url_param:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'url'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Parse comma-separated URLs
        urls = [u.strip() for u in url_param.split(",") if u.strip()]
        if not urls:
            return {
                "status": STATUS_ERROR,
                "error": "Please provide valid list of URL(s)",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Truncate protocols
        urls = _truncate_protocol(urls)

        # Check URL lengths
        is_valid, error_msg = _check_url_length(urls)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        category = kwargs.get("url_category")

        # Extract credentials and create session
        base_url = self.settings.get(SETTINGS_BASE_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        api_key = self.credentials.get(CREDENTIAL_API_KEY)

        if not all([base_url, username, password, api_key]):
            return {
                "status": STATUS_ERROR,
                "error": "Missing required credentials",
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        session = ZScalerSession(
            base_url,
            username,
            password,
            api_key,
            timeout,
            http_request=self.http_request,
        )

        # Authenticate
        auth_result = await session.authenticate()
        if auth_result["status"] != STATUS_SUCCESS:
            return auth_result

        try:
            if category:
                # Add to category
                result = await self._amend_category(
                    session, urls, category, ACTION_ADD_TO_LIST
                )
            else:
                # Add to blocklist
                result = await self._amend_blocklist(session, urls, ACTION_ADD_TO_LIST)

            await session.close()
            return result

        except Exception as e:
            logger.error("Block URL failed", error=str(e))
            await session.close()
            return {
                "status": STATUS_ERROR,
                "error": f"Block URL failed: {e!s}",
                "error_type": type(e).__name__,
            }

    async def _amend_blocklist(
        self, session: ZScalerSession, urls: list[str], action: str
    ) -> dict[str, Any]:
        """Add or remove URLs from blocklist."""
        # Get current blocklist
        result = await session.make_request("/api/v1/security/advanced")
        if result["status"] != STATUS_SUCCESS:
            return result

        blocklist = result.get("data", {}).get("blacklistUrls", [])

        # Filter URLs based on action
        if action == ACTION_REMOVE_FROM_LIST:
            filtered_urls = list(set(blocklist).intersection(set(urls)))
            if not filtered_urls:
                return {
                    "status": STATUS_SUCCESS,
                    "message": "Blocklist contains none of these endpoints",
                    "updated": [],
                    "ignored": urls,
                }
        else:  # ADD_TO_LIST
            filtered_urls = list(set(urls) - set(blocklist))
            if not filtered_urls:
                return {
                    "status": STATUS_SUCCESS,
                    "message": "Blocklist contains all of these endpoints",
                    "updated": [],
                    "ignored": urls,
                }

        # Update blocklist
        update_result = await session.make_request(
            "/api/v1/security/advanced/blacklistUrls",
            method="POST",
            params={"action": action},
            data={"blacklistUrls": filtered_urls},
        )

        if update_result["status"] != STATUS_SUCCESS:
            return update_result

        return {
            "status": STATUS_SUCCESS,
            "message": "Successfully updated blocklist",
            "updated": filtered_urls,
            "ignored": list(set(urls) - set(filtered_urls)),
        }

    async def _amend_category(
        self, session: ZScalerSession, urls: list[str], category: str, action: str
    ) -> dict[str, Any]:
        """Add or remove URLs from category."""
        # Get category details
        cat_result = await self._get_category(session, category)
        if cat_result["status"] != STATUS_SUCCESS:
            return cat_result

        category_data = cat_result["data"]
        existing_urls = category_data.get("dbCategorizedUrls", [])

        # Filter URLs based on action
        if action == ACTION_REMOVE_FROM_LIST:
            filtered_urls = list(set(existing_urls).intersection(set(urls)))
            if not filtered_urls:
                return {
                    "status": STATUS_SUCCESS,
                    "message": "Category contains none of these endpoints",
                    "updated": [],
                    "ignored": urls,
                }
        else:  # ADD_TO_LIST
            filtered_urls = list(set(urls) - set(existing_urls))
            if not filtered_urls:
                return {
                    "status": STATUS_SUCCESS,
                    "message": "Category contains all of these endpoints",
                    "updated": [],
                    "ignored": urls,
                }

        # Update category
        update_data = {
            "configuredName": category_data.get("configuredName"),
            "keywordsRetainingParentCategory": category_data.get(
                "keywordsRetainingParentCategory", []
            ),
            "urls": [],
            "dbCategorizedUrls": filtered_urls,
        }

        update_result = await session.make_request(
            f"/api/v1/urlCategories/{category_data['id']}",
            method="PUT",
            params={"action": action},
            data=update_data,
        )

        if update_result["status"] != STATUS_SUCCESS:
            return update_result

        return {
            "status": STATUS_SUCCESS,
            "message": "Successfully updated category",
            "updated": filtered_urls,
            "ignored": list(set(urls) - set(filtered_urls)),
            "category_data": update_result.get("data"),
        }

    async def _get_category(
        self, session: ZScalerSession, category: str
    ) -> dict[str, Any]:
        """Get category by ID or name."""
        result = await session.make_request("/api/v1/urlCategories")
        if result["status"] != STATUS_SUCCESS:
            return result

        categories = result.get("data", [])

        # Try to find by configured name first
        for cat in categories:
            if cat.get("configuredName") == category:
                return {"status": STATUS_SUCCESS, "data": cat}

        # Try to find by ID
        for cat in categories:
            if cat.get("id") == category:
                return {"status": STATUS_SUCCESS, "data": cat}

        return {
            "status": STATUS_ERROR,
            "error": f"Unable to find category: {category}",
            "error_type": ERROR_TYPE_VALIDATION,
        }

class UnblockUrlAction(IntegrationAction):
    """Unblock URL by removing from blocklist or category."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Unblock URL in ZScaler.

        Args:
            **kwargs: Must contain:
                - url (str): Comma-separated list of URLs to unblock
                - url_category (str, optional): Category ID to remove URLs from

        Returns:
            Result with unblocked URLs or error
        """
        # Reuse BlockUrlAction logic with REMOVE action
        block_action = BlockUrlAction(
            self.integration_id, self.action_id, self.settings, self.credentials
        )

        # Extract and validate URL parameter
        url_param = kwargs.get("url", "").strip()
        if not url_param:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'url'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Parse comma-separated URLs
        urls = [u.strip() for u in url_param.split(",") if u.strip()]
        if not urls:
            return {
                "status": STATUS_ERROR,
                "error": "Please provide valid list of URL(s)",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Truncate protocols
        urls = _truncate_protocol(urls)

        # Check URL lengths
        is_valid, error_msg = _check_url_length(urls)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        category = kwargs.get("url_category")

        # Extract credentials and create session
        base_url = self.settings.get(SETTINGS_BASE_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        api_key = self.credentials.get(CREDENTIAL_API_KEY)

        if not all([base_url, username, password, api_key]):
            return {
                "status": STATUS_ERROR,
                "error": "Missing required credentials",
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        session = ZScalerSession(
            base_url,
            username,
            password,
            api_key,
            timeout,
            http_request=self.http_request,
        )

        # Authenticate
        auth_result = await session.authenticate()
        if auth_result["status"] != STATUS_SUCCESS:
            return auth_result

        try:
            if category:
                # Remove from category
                result = await block_action._amend_category(
                    session, urls, category, ACTION_REMOVE_FROM_LIST
                )
            else:
                # Remove from blocklist
                result = await block_action._amend_blocklist(
                    session, urls, ACTION_REMOVE_FROM_LIST
                )

            await session.close()
            return result

        except Exception as e:
            logger.error("Unblock URL failed", error=str(e))
            await session.close()
            return {
                "status": STATUS_ERROR,
                "error": f"Unblock URL failed: {e!s}",
                "error_type": type(e).__name__,
            }

class BlockIpAction(IntegrationAction):
    """Block IP address by adding to blocklist or category."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Block IP address in ZScaler.

        Args:
            **kwargs: Must contain:
                - ip (str): Comma-separated list of IP addresses to block
                - url_category (str, optional): Category ID to add IPs to

        Returns:
            Result with blocked IPs or error
        """
        # Reuse URL blocking logic (ZScaler treats IPs similar to URLs)
        block_url_action = BlockUrlAction(
            self.integration_id, "block_url", self.settings, self.credentials
        )

        # Replace 'ip' parameter with 'url' for internal processing
        modified_kwargs = dict(kwargs)
        modified_kwargs["url"] = modified_kwargs.pop("ip", "")

        return await block_url_action.execute(**modified_kwargs)

class UnblockIpAction(IntegrationAction):
    """Unblock IP address by removing from blocklist or category."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Unblock IP address in ZScaler.

        Args:
            **kwargs: Must contain:
                - ip (str): Comma-separated list of IP addresses to unblock
                - url_category (str, optional): Category ID to remove IPs from

        Returns:
            Result with unblocked IPs or error
        """
        # Reuse URL unblocking logic
        unblock_url_action = UnblockUrlAction(
            self.integration_id, "unblock_url", self.settings, self.credentials
        )

        # Replace 'ip' parameter with 'url' for internal processing
        modified_kwargs = dict(kwargs)
        modified_kwargs["url"] = modified_kwargs.pop("ip", "")

        return await unblock_url_action.execute(**modified_kwargs)

class ListUrlCategoriesAction(IntegrationAction):
    """List all URL categories in ZScaler."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List URL categories from ZScaler.

        Args:
            **kwargs: May contain:
                - get_ids_and_names_only (bool): Return only IDs and names

        Returns:
            Result with URL categories or error
        """
        ids_only = kwargs.get("get_ids_and_names_only", False)

        # Extract credentials and create session
        base_url = self.settings.get(SETTINGS_BASE_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        api_key = self.credentials.get(CREDENTIAL_API_KEY)

        if not all([base_url, username, password, api_key]):
            return {
                "status": STATUS_ERROR,
                "error": "Missing required credentials",
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        session = ZScalerSession(
            base_url,
            username,
            password,
            api_key,
            timeout,
            http_request=self.http_request,
        )

        # Authenticate
        auth_result = await session.authenticate()
        if auth_result["status"] != STATUS_SUCCESS:
            return auth_result

        try:
            # Get URL categories
            result = await session.make_request("/api/v1/urlCategories")

            if result["status"] != STATUS_SUCCESS:
                await session.close()
                return result

            categories = result.get("data", [])

            # Filter to IDs and names only if requested
            if ids_only:
                categories = [
                    {
                        "id": cat["id"],
                        **(
                            {"configuredName": cat["configuredName"]}
                            if "configuredName" in cat
                            else {}
                        ),
                    }
                    for cat in categories
                ]

            await session.close()

            return {
                "status": STATUS_SUCCESS,
                "total_url_categories": len(categories),
                "categories": categories,
            }

        except Exception as e:
            logger.error("List URL categories failed", error=str(e))
            await session.close()
            return {
                "status": STATUS_ERROR,
                "error": f"List URL categories failed: {e!s}",
                "error_type": type(e).__name__,
            }

class GetReportAction(IntegrationAction):
    """Get sandbox report for file hash."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get sandbox report from ZScaler.

        Args:
            **kwargs: Must contain:
                - file_hash (str): MD5 hash of file

        Returns:
            Result with sandbox report or error
        """
        file_hash = kwargs.get("file_hash", "").strip()
        if not file_hash:
            return {
                "status": STATUS_ERROR,
                "error": "Missing required parameter 'file_hash'",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Extract credentials and create session
        base_url = self.settings.get(SETTINGS_BASE_URL)
        username = self.credentials.get(CREDENTIAL_USERNAME)
        password = self.credentials.get(CREDENTIAL_PASSWORD)
        api_key = self.credentials.get(CREDENTIAL_API_KEY)

        if not all([base_url, username, password, api_key]):
            return {
                "status": STATUS_ERROR,
                "error": "Missing required credentials",
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)
        session = ZScalerSession(
            base_url,
            username,
            password,
            api_key,
            timeout,
            http_request=self.http_request,
        )

        # Authenticate
        auth_result = await session.authenticate()
        if auth_result["status"] != STATUS_SUCCESS:
            return auth_result

        try:
            # Get sandbox report
            result = await session.make_request(
                f"/api/v1/sandbox/report/{file_hash}", params={"details": "full"}
            )

            if result["status"] != STATUS_SUCCESS:
                await session.close()
                if result.get("status_code") == 404:
                    logger.info("zscaler_report_not_found", file_hash=file_hash)
                    return {
                        "status": STATUS_SUCCESS,
                        "not_found": True,
                        "message": "Sandbox report not found for the provided hash",
                        "file_hash": file_hash,
                    }
                return result

            report_data = result.get("data", {})

            # Check for unknown MD5 error
            full_details = report_data.get("Full Details", "")
            if ERR_MD5_UNKNOWN_MSG in full_details:
                await session.close()
                return {
                    "status": STATUS_ERROR,
                    "error": full_details,
                    "error_type": ERROR_TYPE_VALIDATION,
                }

            await session.close()

            return {
                "status": STATUS_SUCCESS,
                "message": SANDBOX_GET_REPORT_MSG,
                "file_hash": file_hash,
                "report": report_data,
            }

        except Exception as e:
            logger.error("Get sandbox report failed", file_hash=file_hash, error=str(e))
            await session.close()
            return {
                "status": STATUS_ERROR,
                "error": f"Get sandbox report failed: {e!s}",
                "error_type": type(e).__name__,
            }
