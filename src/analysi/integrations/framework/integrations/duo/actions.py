"""Duo Security integration actions.

This module provides identity and MFA-related actions for Duo Security.
Duo uses custom HMAC-SHA1 authentication for API requests.
"""

import base64
import email.utils
import hashlib
import hmac
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

logger = get_logger(__name__)

# Constants
DEFAULT_TIMEOUT = 30

# ============================================================================
# AUTHENTICATION HELPER
# ============================================================================

def _create_duo_auth_headers(
    url: str,
    method: str,
    skey: str,
    ikey: str,
    body: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Create Duo authentication headers using HMAC-SHA1 signature.

    Args:
        url: Full URL of the request
        method: HTTP method (GET or POST)
        skey: Duo secret key
        ikey: Duo integration key
        body: Request body for POST requests

    Returns:
        Dict with Date, Authorization, and Content-Type headers
    """
    parsed_url = urlparse(url)
    host = parsed_url.netloc.lower()
    path = parsed_url.path

    # Parse parameters
    if method == "GET":
        params = parse_qs(parsed_url.query)
    elif method == "POST" and body:
        params = {k: [str(v)] for k, v in body.items()}
    else:
        params = {}

    # Create canonical string
    now = email.utils.formatdate()
    canon = [now, method.upper(), host, path]

    # Sort and encode parameters
    args = []
    for key in sorted(params.keys()):
        val = params[key][0] if isinstance(params[key], list) else str(params[key])
        args.append(f"{quote(key, safe='~')}={quote(val, safe='~')}")
    canon.append("&".join(args))

    canon_str = "\n".join(canon)

    # Sign canonical string with HMAC-SHA1
    sig = hmac.new(skey.encode(), canon_str.encode(), hashlib.sha1)
    auth = f"{ikey}:{sig.hexdigest()}"

    # Create headers
    headers = {
        "Date": now,
        "Authorization": f"Basic {base64.b64encode(auth.encode()).decode()}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    return headers

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for Duo API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check Duo API connectivity.

        Tests connectivity by calling the /auth/v2/check endpoint.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        # Extract credentials
        api_host = self.settings.get("api_host")
        ikey = self.credentials.get("ikey")
        skey = self.credentials.get("skey")

        if not api_host or not ikey or not skey:
            return {
                "status": "error",
                "error": "Missing required credentials: api_host, ikey, and skey are required",
                "error_type": "ConfigurationError",
                "healthy": False,
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            # Test connectivity with check endpoint
            url = f"https://{api_host}/auth/v2/check"
            headers = _create_duo_auth_headers(
                url=url,
                method="GET",
                skey=skey,
                ikey=ikey,
            )
            response = await self.http_request(
                url,
                headers=headers,
                timeout=timeout,
            )
            result = response.json()

            return {
                "status": "success",
                "message": "Duo API is accessible",
                "healthy": True,
                "data": result,
            }

        except Exception as e:
            logger.error("Duo health check failed", error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
                "healthy": False,
            }

class AuthorizeAction(IntegrationAction):
    """Authorize an action using Duo Push notification."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Send Duo Push notification to user for authorization.

        Args:
            **kwargs: Must contain:
                - user (str): Username or email who can authorize
                - type (str, optional): Type shown in notification (default: "Analysi request")
                - info (str, optional): Additional info to display

        Returns:
            Result with authorization status or error
        """
        # Extract and validate parameters
        user = kwargs.get("user")
        if not user:
            return {
                "status": "error",
                "error": "Missing required parameter 'user'",
                "error_type": "ValidationError",
            }

        request_type = kwargs.get("type", "Analysi request")
        info = kwargs.get("info")

        # Extract credentials
        api_host = self.settings.get("api_host")
        ikey = self.credentials.get("ikey")
        skey = self.credentials.get("skey")

        if not api_host or not ikey or not skey:
            return {
                "status": "error",
                "error": "Missing required credentials: api_host, ikey, and skey are required",
                "error_type": "ConfigurationError",
            }

        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            # Step 1: Pre-auth to check if user can authenticate
            preauth_url = f"https://{api_host}/auth/v2/preauth"
            preauth_data = {"username": user}
            preauth_headers = _create_duo_auth_headers(
                url=preauth_url,
                method="POST",
                skey=skey,
                ikey=ikey,
                body=preauth_data,
            )
            preauth_response_http = await self.http_request(
                preauth_url,
                method="POST",
                headers=preauth_headers,
                data=preauth_data,
                timeout=timeout,
            )
            preauth_result = preauth_response_http.json()

            preauth_response = preauth_result.get("response", {})
            if preauth_response.get("result") != "auth":
                return {
                    "status": "error",
                    "error": f"User is not permitted to authenticate: {preauth_response.get('status_msg', 'Unknown reason')}",
                    "error_type": "AuthorizationError",
                    "preauth_result": preauth_response.get("result"),
                }

            # Step 2: Send push notification for authorization
            auth_data = {
                "username": user,
                "factor": "push",
                "device": "auto",
                "type": request_type,
            }
            if info:
                auth_data["pushinfo"] = info

            auth_url = f"https://{api_host}/auth/v2/auth"
            auth_headers = _create_duo_auth_headers(
                url=auth_url,
                method="POST",
                skey=skey,
                ikey=ikey,
                body=auth_data,
            )
            auth_response_http = await self.http_request(
                auth_url,
                method="POST",
                headers=auth_headers,
                data=auth_data,
                timeout=timeout,
            )
            auth_result = auth_response_http.json()

            auth_response = auth_result.get("response", {})
            result_status = auth_response.get("result")

            if result_status == "allow":
                return {
                    "status": "success",
                    "result": "allow",
                    "message": "Action authorized",
                    "user": user,
                    "data": auth_response,
                }
            return {
                "status": "error",
                "result": result_status,
                "error": f"Action not authorized: {auth_response.get('status_msg', 'User denied or timeout')}",
                "error_type": "AuthorizationDenied",
                "user": user,
                "data": auth_response,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("duo_authorize_not_found", user=user)
                return {
                    "status": "success",
                    "not_found": True,
                    "user": user,
                }
            logger.error("Duo authorization failed", user=user, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
                "user": user,
            }
        except Exception as e:
            logger.error("Duo authorization failed", user=user, error=str(e))
            return {
                "status": "error",
                "error": str(e),
                "error_type": type(e).__name__,
                "user": user,
            }
