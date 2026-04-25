"""ThreatConnect integration actions.

ThreatConnect uses HMAC-SHA256 request signing instead of simple API key auth.
Each request is signed with: access_id + HMAC(secret_key, "{path}:{method}:{timestamp}")

upstream connector imports: requests, hmac, hashlib, base64 (REST API with HMAC signing)
Library type: REST API via self.http_request() with custom auth headers per request.
"""

import base64
import hashlib
import hmac
import ipaddress
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    API_VERSION,
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    ENDPOINT_INDICATORS,
    ENDPOINT_OWNERS,
    HASH_LENGTHS,
    INDICATOR_TYPE_ADDRESS,
    INDICATOR_TYPE_EMAIL,
    INDICATOR_TYPE_FILE,
    INDICATOR_TYPE_HOST,
    INDICATOR_TYPE_MAP,
    INDICATOR_TYPE_URL,
    MSG_MISSING_CREDENTIALS,
)

logger = get_logger(__name__)

# ============================================================================
# HMAC SIGNING HELPER
# ============================================================================

def _sign_request(
    secret_key: str,
    path: str,
    method: str,
    timestamp: int | None = None,
) -> tuple[str, int]:
    """Generate HMAC-SHA256 signature for ThreatConnect API request.

    The signing formula (from ThreatConnect docs):
      1. message = "{path}:{METHOD}:{timestamp}"
      2. signature = base64(hmac_sha256(secret_key, message))

    Args:
        secret_key: ThreatConnect API secret key
        path: URL path including query string (e.g., "/api/v3/indicators?tql=...")
        method: HTTP method in uppercase (GET, POST, PUT, DELETE)
        timestamp: Unix timestamp (defaults to current time if None)

    Returns:
        Tuple of (base64-encoded signature, timestamp used)
    """
    if timestamp is None:
        timestamp = int(time.time())

    method_upper = method.upper()
    message = f"{path}:{method_upper}:{timestamp}"

    signature_bytes = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()

    signature_b64 = base64.b64encode(signature_bytes).decode("utf-8")

    return signature_b64, timestamp

def _build_auth_headers(
    access_id: str,
    secret_key: str,
    path: str,
    method: str,
    timestamp: int | None = None,
) -> dict[str, str]:
    """Build ThreatConnect authentication headers.

    Args:
        access_id: ThreatConnect API access ID
        secret_key: ThreatConnect API secret key
        path: URL path including query string
        method: HTTP method (GET, POST, etc.)
        timestamp: Unix timestamp (defaults to current time)

    Returns:
        Dict with Authorization, Timestamp, and Content-Type headers
    """
    signature, ts = _sign_request(secret_key, path, method, timestamp)

    return {
        "Authorization": f"TC {access_id}:{signature}",
        "Timestamp": str(ts),
        "Content-Type": "application/json",
    }

# ============================================================================
# VALIDATION HELPERS
# ============================================================================

def _validate_ip(ip: str | None) -> tuple[bool, str]:
    """Validate IP address format (IPv4 or IPv6).

    Args:
        ip: IP address to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not ip or not isinstance(ip, str) or not ip.strip():
        return False, "IP address is required"
    try:
        ipaddress.ip_address(ip.strip())
        return True, ""
    except ValueError:
        return False, f"Invalid IP address format: {ip}"

def _validate_hash(file_hash: str | None) -> tuple[bool, str]:
    """Validate file hash format (MD5, SHA1, or SHA256).

    Args:
        file_hash: Hash string to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not file_hash or not isinstance(file_hash, str) or not file_hash.strip():
        return False, "File hash is required"

    file_hash = file_hash.strip()
    if len(file_hash) not in HASH_LENGTHS:
        return (
            False,
            f"Invalid hash length ({len(file_hash)}). Expected MD5 (32), SHA1 (40), or SHA256 (64)",
        )

    if not all(c in "0123456789abcdefABCDEF" for c in file_hash):
        return False, "Hash must contain only hexadecimal characters"

    return True, ""

def _validate_non_empty(value: str | None, param_name: str) -> tuple[bool, str]:
    """Validate a string parameter is non-empty.

    Args:
        value: Parameter value
        param_name: Parameter name for error messages

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not value or not isinstance(value, str) or not value.strip():
        return False, f"{param_name} is required"
    return True, ""

# ============================================================================
# COMMON HELPERS
# ============================================================================

def _get_api_url(settings: dict[str, Any]) -> str:
    """Build the API base URL from settings.

    Handles both standard and sandbox ThreatConnect instances.

    Args:
        settings: Integration settings dict

    Returns:
        Full API URL (e.g., "https://api.threatconnect.com/v3")
    """
    base_url = settings.get("base_url", DEFAULT_BASE_URL).rstrip("/")

    # Sandbox instances use /api/v3 path
    if "sandbox.threatconnect.com" in base_url:
        return f"{base_url}/api/{API_VERSION}"

    return f"{base_url}/{API_VERSION}"

def _build_request_path(api_url: str, endpoint: str, params: dict | None = None) -> str:
    """Build the full path for signing, including query parameters.

    The HMAC signature must include the full path with query string, matching
    what the server sees in the request.

    Args:
        api_url: Full API URL (e.g., "https://api.threatconnect.com/v3")
        endpoint: Relative endpoint (e.g., "indicators")
        params: Query parameters dict

    Returns:
        Path portion of URL for signing (e.g., "/v3/indicators?tql=...")
    """
    # Extract path portion from full URL
    # e.g., "https://api.threatconnect.com/v3" -> "/v3"
    from urllib.parse import urlparse

    parsed = urlparse(f"{api_url}/{endpoint}")
    path = parsed.path

    if params:
        # Sort params for consistent signing
        query_string = urlencode(params, doseq=True)
        if query_string:
            path = f"{path}?{query_string}"

    return path

def _extract_credentials(credentials: dict[str, Any]) -> tuple[str | None, str | None]:
    """Extract access_id and secret_key from credentials dict.

    Args:
        credentials: Credentials dict from Vault

    Returns:
        Tuple of (access_id, secret_key)
    """
    return credentials.get("access_id"), credentials.get("secret_key")

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Verify API connectivity with ThreatConnect."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity by listing owners.

        Returns:
            Success result with owner count, or error on failure
        """
        access_id, secret_key = _extract_credentials(self.credentials)
        if not access_id or not secret_key:
            return {
                "status": "error",
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
                "healthy": False,
            }

        api_url = _get_api_url(self.settings)
        endpoint = ENDPOINT_OWNERS
        url = f"{api_url}/{endpoint}"
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        # Build signing path with no query params for health check
        sign_path = _build_request_path(api_url, endpoint)
        headers = _build_auth_headers(access_id, secret_key, sign_path, "GET")

        try:
            response = await self.http_request(
                url=url,
                headers=headers,
                timeout=timeout,
            )
            result = response.json()

            if result.get("status") != "Success":
                return {
                    "status": "error",
                    "error": f"API returned status: {result.get('status')}",
                    "error_type": "APIError",
                    "healthy": False,
                }

            return {
                "status": "success",
                "message": "ThreatConnect API is accessible",
                "healthy": True,
                "data": {
                    "healthy": True,
                    "owner_count": result.get("count", 0),
                },
            }

        except Exception as e:
            logger.error("threatconnect_health_check_failed", error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
                "healthy": False,
            }

class LookupIpAction(IntegrationAction):
    """Look up IP address indicator in ThreatConnect."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Look up IP indicator using TQL query.

        Args:
            **kwargs: Must contain 'ip' (IPv4 or IPv6 address)
                Optional: 'owner' (str) - filter by owner name

        Returns:
            Success result with indicator data, or error on failure
        """
        ip = kwargs.get("ip")
        is_valid, error_msg = _validate_ip(ip)
        if not is_valid:
            return {
                "status": "error",
                "error": error_msg,
                "error_type": "ValidationError",
            }

        access_id, secret_key = _extract_credentials(self.credentials)
        if not access_id or not secret_key:
            return {
                "status": "error",
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        return await self._lookup_indicator(
            access_id=access_id,
            secret_key=secret_key,
            indicator_type=INDICATOR_TYPE_ADDRESS,
            indicator_value=ip,
            owner=kwargs.get("owner"),
        )

    async def _lookup_indicator(
        self,
        access_id: str,
        secret_key: str,
        indicator_type: str,
        indicator_value: str,
        owner: str | None = None,
    ) -> dict[str, Any]:
        """Shared indicator lookup logic using TQL queries.

        Args:
            access_id: TC access ID
            secret_key: TC secret key
            indicator_type: TC indicator type name (e.g., "Address")
            indicator_value: Value to search for
            owner: Optional owner name to filter

        Returns:
            Result dict
        """
        api_url = _get_api_url(self.settings)
        endpoint = ENDPOINT_INDICATORS
        url = f"{api_url}/{endpoint}"
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        # Build TQL query matching upstream pattern
        tql = (
            f"typeName IN ('{indicator_type}') AND summary CONTAINS '{indicator_value}'"
        )
        if owner:
            owners_list = [
                o.strip() for o in owner.replace(";", ",").split(",") if o.strip()
            ]
            owners_str = ", ".join(repr(o) for o in owners_list)
            tql += f" and ownerName in ({owners_str})"

        params = {"tql": tql}
        sign_path = _build_request_path(api_url, endpoint, params)
        headers = _build_auth_headers(access_id, secret_key, sign_path, "GET")

        try:
            response = await self.http_request(
                url=url,
                params=params,
                headers=headers,
                timeout=timeout,
            )
            result = response.json()

            if result.get("status") == "Failure":
                return {
                    "status": "error",
                    "error": result.get("message", "Unknown error"),
                    "error_type": "APIError",
                }

            data = result.get("data", [])
            return {
                "status": "success",
                "total_objects": len(data),
                "data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(
                    "threatconnect_indicator_not_found", indicator=indicator_value
                )
                return {
                    "status": "success",
                    "not_found": True,
                    "total_objects": 0,
                    "data": {"data": [], "count": 0, "status": "Success"},
                }
            logger.error(
                "threatconnect_lookup_failed", indicator=indicator_value, error=str(e)
            )
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}
        except Exception as e:
            logger.error(
                "threatconnect_lookup_failed", indicator=indicator_value, error=str(e)
            )
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}

class LookupDomainAction(IntegrationAction):
    """Look up domain/host indicator in ThreatConnect."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Look up domain indicator using TQL query.

        Args:
            **kwargs: Must contain 'domain' (hostname)
                Optional: 'owner' (str) - filter by owner name

        Returns:
            Success result with indicator data, or error on failure
        """
        domain = kwargs.get("domain")
        is_valid, error_msg = _validate_non_empty(domain, "domain")
        if not is_valid:
            return {
                "status": "error",
                "error": error_msg,
                "error_type": "ValidationError",
            }

        access_id, secret_key = _extract_credentials(self.credentials)
        if not access_id or not secret_key:
            return {
                "status": "error",
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        # Reuse the lookup logic from LookupIpAction via composition
        lookup = LookupIpAction(
            integration_id=self.integration_id,
            action_id=self.action_id,
            settings=self.settings,
            credentials=self.credentials,
        )
        return await lookup._lookup_indicator(
            access_id=access_id,
            secret_key=secret_key,
            indicator_type=INDICATOR_TYPE_HOST,
            indicator_value=domain,
            owner=kwargs.get("owner"),
        )

class LookupHashAction(IntegrationAction):
    """Look up file hash indicator in ThreatConnect."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Look up file hash indicator using TQL query.

        Args:
            **kwargs: Must contain 'hash' (MD5, SHA1, or SHA256)
                Optional: 'owner' (str) - filter by owner name

        Returns:
            Success result with indicator data, or error on failure
        """
        file_hash = kwargs.get("hash")
        is_valid, error_msg = _validate_hash(file_hash)
        if not is_valid:
            return {
                "status": "error",
                "error": error_msg,
                "error_type": "ValidationError",
            }

        access_id, secret_key = _extract_credentials(self.credentials)
        if not access_id or not secret_key:
            return {
                "status": "error",
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        lookup = LookupIpAction(
            integration_id=self.integration_id,
            action_id=self.action_id,
            settings=self.settings,
            credentials=self.credentials,
        )
        return await lookup._lookup_indicator(
            access_id=access_id,
            secret_key=secret_key,
            indicator_type=INDICATOR_TYPE_FILE,
            indicator_value=file_hash,
            owner=kwargs.get("owner"),
        )

class LookupUrlAction(IntegrationAction):
    """Look up URL indicator in ThreatConnect."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Look up URL indicator using TQL query.

        Args:
            **kwargs: Must contain 'url'
                Optional: 'owner' (str) - filter by owner name

        Returns:
            Success result with indicator data, or error on failure
        """
        url = kwargs.get("url")
        is_valid, error_msg = _validate_non_empty(url, "url")
        if not is_valid:
            return {
                "status": "error",
                "error": error_msg,
                "error_type": "ValidationError",
            }

        access_id, secret_key = _extract_credentials(self.credentials)
        if not access_id or not secret_key:
            return {
                "status": "error",
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        lookup = LookupIpAction(
            integration_id=self.integration_id,
            action_id=self.action_id,
            settings=self.settings,
            credentials=self.credentials,
        )
        return await lookup._lookup_indicator(
            access_id=access_id,
            secret_key=secret_key,
            indicator_type=INDICATOR_TYPE_URL,
            indicator_value=url,
            owner=kwargs.get("owner"),
        )

class LookupEmailAction(IntegrationAction):
    """Look up email address indicator in ThreatConnect."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Look up email indicator using TQL query.

        Args:
            **kwargs: Must contain 'email'
                Optional: 'owner' (str) - filter by owner name

        Returns:
            Success result with indicator data, or error on failure
        """
        email = kwargs.get("email")
        is_valid, error_msg = _validate_non_empty(email, "email")
        if not is_valid:
            return {
                "status": "error",
                "error": error_msg,
                "error_type": "ValidationError",
            }

        access_id, secret_key = _extract_credentials(self.credentials)
        if not access_id or not secret_key:
            return {
                "status": "error",
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        lookup = LookupIpAction(
            integration_id=self.integration_id,
            action_id=self.action_id,
            settings=self.settings,
            credentials=self.credentials,
        )
        return await lookup._lookup_indicator(
            access_id=access_id,
            secret_key=secret_key,
            indicator_type=INDICATOR_TYPE_EMAIL,
            indicator_value=email,
            owner=kwargs.get("owner"),
        )

class CreateIndicatorAction(IntegrationAction):
    """Create a new indicator in ThreatConnect."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Create an indicator via POST to the indicators endpoint.

        Args:
            **kwargs: Must contain:
                - indicator_value (str): IP, domain, hash, URL, or email
                - indicator_type (str): One of: ip, domain, hash, url, email
                Optional:
                - rating (float): Indicator rating 0-5
                - confidence (int): Confidence 0-100

        Returns:
            Success result with created indicator data, or error on failure
        """
        indicator_value = kwargs.get("indicator_value")
        indicator_type = kwargs.get("indicator_type")

        is_valid, error_msg = _validate_non_empty(indicator_value, "indicator_value")
        if not is_valid:
            return {
                "status": "error",
                "error": error_msg,
                "error_type": "ValidationError",
            }

        is_valid, error_msg = _validate_non_empty(indicator_type, "indicator_type")
        if not is_valid:
            return {
                "status": "error",
                "error": error_msg,
                "error_type": "ValidationError",
            }

        # Map user-friendly type names to TC API type names
        tc_type = INDICATOR_TYPE_MAP.get(indicator_type)
        if not tc_type:
            return {
                "status": "error",
                "error": f"Invalid indicator_type: {indicator_type}. Must be one of: {', '.join(INDICATOR_TYPE_MAP.keys())}",
                "error_type": "ValidationError",
            }

        access_id, secret_key = _extract_credentials(self.credentials)
        if not access_id or not secret_key:
            return {
                "status": "error",
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        api_url = _get_api_url(self.settings)
        endpoint = ENDPOINT_INDICATORS
        url = f"{api_url}/{endpoint}"
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        # Build request body matching upstream _create_payload_for_post_data
        body: dict[str, Any] = {"type": tc_type}

        # Set the correct field name for the indicator value based on type
        if tc_type == INDICATOR_TYPE_ADDRESS:
            body["ip"] = indicator_value
        elif tc_type == INDICATOR_TYPE_HOST:
            body["hostName"] = indicator_value
        elif tc_type == INDICATOR_TYPE_URL:
            body["text"] = indicator_value
        elif tc_type == INDICATOR_TYPE_EMAIL:
            body["address"] = indicator_value
        elif tc_type == INDICATOR_TYPE_FILE:
            # Determine hash type by length
            hash_type = HASH_LENGTHS.get(len(indicator_value))
            if hash_type:
                body[hash_type] = indicator_value
            else:
                body["md5"] = indicator_value

        # Add optional fields
        if kwargs.get("rating") is not None:
            body["rating"] = kwargs["rating"]
        if kwargs.get("confidence") is not None:
            body["confidence"] = kwargs["confidence"]

        sign_path = _build_request_path(api_url, endpoint)
        headers = _build_auth_headers(access_id, secret_key, sign_path, "POST")

        try:
            response = await self.http_request(
                url=url,
                method="POST",
                headers=headers,
                json=body,
                timeout=timeout,
            )
            result = response.json()

            return {
                "status": "success",
                "message": "Indicator created in ThreatConnect",
                "data": result,
            }

        except httpx.HTTPStatusError as e:
            logger.error(
                "threatconnect_create_indicator_failed",
                indicator=indicator_value,
                error=str(e),
            )
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}
        except Exception as e:
            logger.error(
                "threatconnect_create_indicator_failed",
                indicator=indicator_value,
                error=str(e),
            )
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}

class ListOwnersAction(IntegrationAction):
    """List ThreatConnect owners/organizations visible to the user."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """List all owners visible with the configured credentials.

        Returns:
            Success result with owner data, or error on failure
        """
        access_id, secret_key = _extract_credentials(self.credentials)
        if not access_id or not secret_key:
            return {
                "status": "error",
                "error": MSG_MISSING_CREDENTIALS,
                "error_type": "ConfigurationError",
            }

        api_url = _get_api_url(self.settings)
        endpoint = ENDPOINT_OWNERS
        url = f"{api_url}/{endpoint}"
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        sign_path = _build_request_path(api_url, endpoint)
        headers = _build_auth_headers(access_id, secret_key, sign_path, "GET")

        try:
            response = await self.http_request(
                url=url,
                headers=headers,
                timeout=timeout,
            )
            result = response.json()

            if result.get("status") != "Success":
                return {
                    "status": "error",
                    "error": f"API returned status: {result.get('status')}",
                    "error_type": "APIError",
                }

            owners = result.get("data", [])
            return {
                "status": "success",
                "num_owners": len(owners),
                "data": result,
            }

        except Exception as e:
            logger.error("threatconnect_list_owners_failed", error=str(e))
            return {"status": "error", "error": str(e), "error_type": type(e).__name__}
