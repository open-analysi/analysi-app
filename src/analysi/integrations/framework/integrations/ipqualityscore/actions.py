"""IPQualityScore integration actions.

Provides fraud detection, IP/URL/email/phone reputation, and dark web leak lookups
via the IPQualityScore REST API.
"""

import re
import urllib.parse
from typing import Any

import httpx

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction
from analysi.integrations.framework.integrations.ipqualityscore.constants import (
    DARK_WEB_LEAK_TYPES,
    DEFAULT_TIMEOUT,
    EMAIL_REGEX,
    ENDPOINT_EMAIL,
    ENDPOINT_IP,
    ENDPOINT_LEAKED,
    ENDPOINT_PHONE,
    ENDPOINT_URL,
    IPQS_BASE_URL,
    MSG_API_FAILURE,
    MSG_INVALID_ABUSE_STRICTNESS,
    MSG_INVALID_EMAIL,
    MSG_INVALID_LEAK_TYPE,
    MSG_INVALID_STRICTNESS,
    MSG_INVALID_TIMEOUT,
    MSG_INVALID_TRANSACTION_STRICTNESS,
    MSG_MISSING_API_KEY,
    MSG_MISSING_PARAM,
    MSG_RATE_LIMITED,
    STRICTNESS_VALUES,
)

logger = get_logger(__name__)

# ============================================================================
# VALIDATION HELPERS
# ============================================================================

def _validate_strictness(value: Any) -> tuple[bool, str]:
    """Validate strictness parameter (0, 1, or 2).

    Args:
        value: Strictness value to validate (may be None, which is valid/optional)

    Returns:
        Tuple of (is_valid, error_message)
    """
    if value is None:
        return True, ""
    try:
        int_val = int(value)
        if int_val not in STRICTNESS_VALUES:
            return False, MSG_INVALID_STRICTNESS
        return True, ""
    except (ValueError, TypeError):
        return False, MSG_INVALID_STRICTNESS

def _validate_non_negative_int(value: Any, error_msg: str) -> tuple[bool, str]:
    """Validate a non-negative integer parameter.

    Args:
        value: Value to validate (may be None, which is valid/optional)
        error_msg: Error message to return on failure

    Returns:
        Tuple of (is_valid, error_message)
    """
    if value is None:
        return True, ""
    try:
        int_val = int(value)
        if not float(value).is_integer():
            return False, error_msg
        if int_val < 0:
            return False, error_msg
        return True, ""
    except (ValueError, TypeError):
        return False, error_msg

def _validate_email(email: str | None) -> tuple[bool, str]:
    """Validate email address format.

    Args:
        email: Email address to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not email:
        return False, MSG_INVALID_EMAIL
    if not re.fullmatch(EMAIL_REGEX, str(email)):
        return False, MSG_INVALID_EMAIL
    return True, ""

def _build_api_url(endpoint: str, api_key: str, value: str) -> str:
    """Build IPQualityScore API URL.

    Args:
        endpoint: API endpoint type (ip, url, email, phone)
        api_key: API key for authentication
        value: The value to look up (URL-encoded if needed)

    Returns:
        Full API URL string
    """
    return f"{IPQS_BASE_URL}/{endpoint}/{api_key}/{value}"

def _build_optional_params(**kwargs) -> dict[str, Any]:
    """Build optional query parameters dict, filtering None values.

    Args:
        **kwargs: Optional parameter key-value pairs

    Returns:
        Dict of non-None parameters
    """
    params = {}
    for key, value in kwargs.items():
        if value is not None:
            # Convert booleans to lowercase strings per API spec
            if isinstance(value, bool):
                params[key] = str(value).lower()
            else:
                params[key] = value
    return params

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Verify IPQualityScore API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Test connectivity by querying a known IP (8.8.8.8).

        Returns:
            Success result if API is reachable and returns valid response.
        """
        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        url = _build_api_url(ENDPOINT_IP, api_key, "8.8.8.8")
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            response = await self.http_request(url=url, timeout=timeout)
            result = response.json()

            if result.get("success"):
                return self.success_result(
                    data={
                        "healthy": True,
                        "message": "IPQualityScore API is accessible",
                    },
                    healthy=True,
                )

            return self.error_result(
                MSG_API_FAILURE,
                error_type="APIError",
                healthy=False,
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 509:
                logger.warning("ipqs_health_check_rate_limited")
                return self.error_result(
                    MSG_RATE_LIMITED, error_type="RateLimitError", healthy=False
                )
            logger.error("ipqs_health_check_failed", error=str(e))
            return self.error_result(e, healthy=False)
        except Exception as e:
            logger.error("ipqs_health_check_failed", error=str(e))
            return self.error_result(e, healthy=False)

class IpReputationAction(IntegrationAction):
    """Query IPQualityScore Proxy/VPN detection API for an IP address."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Look up IP reputation including proxy, VPN, bot, and fraud detection.

        Args:
            **kwargs: Must contain:
                - ip (str): IP address to check
                - strictness (int, optional): Detection strictness (0, 1, or 2)
                - user_agent (str, optional): User agent for additional bot checks
                - user_language (str, optional): Language for risk evaluation
                - fast (bool, optional): Skip forensic checks
                - mobile (bool, optional): Treat as mobile device
                - allow_public_access_points (bool, optional): Allow public access points
                - lighter_penalties (bool, optional): Lower penalties for mixed-quality IPs
                - transaction_strictness (int, optional): Transaction irregularity weight

        Returns:
            Result with IP reputation data including fraud_score, proxy, VPN, tor flags.
        """
        ip = kwargs.get("ip")
        if not ip:
            return self.error_result(
                MSG_MISSING_PARAM.format("ip"), error_type="ValidationError"
            )

        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        # Validate optional integer parameters
        is_valid, err = _validate_strictness(kwargs.get("strictness"))
        if not is_valid:
            return self.error_result(err, error_type="ValidationError")

        is_valid, err = _validate_non_negative_int(
            kwargs.get("transaction_strictness"), MSG_INVALID_TRANSACTION_STRICTNESS
        )
        if not is_valid:
            return self.error_result(err, error_type="ValidationError")

        url = _build_api_url(ENDPOINT_IP, api_key, ip)
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        params = _build_optional_params(
            strictness=kwargs.get("strictness"),
            user_agent=kwargs.get("user_agent"),
            user_language=kwargs.get("user_language"),
            fast=kwargs.get("fast"),
            mobile=kwargs.get("mobile"),
            allow_public_access_points=kwargs.get("allow_public_access_points"),
            lighter_penalties=kwargs.get("lighter_penalties"),
            transaction_strictness=kwargs.get("transaction_strictness"),
        )

        try:
            response = await self.http_request(url=url, params=params, timeout=timeout)
            result = response.json()

            if not result.get("success"):
                return self.error_result(
                    result.get("message", MSG_API_FAILURE), error_type="APIError"
                )

            return self.success_result(data=result)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 509:
                return self.error_result(MSG_RATE_LIMITED, error_type="RateLimitError")
            if e.response.status_code == 404:
                logger.info("ipqs_ip_not_found", ip=ip)
                return self.success_result(
                    not_found=True, data={"ip": ip, "fraud_score": 0}
                )
            return self.error_result(e)
        except Exception as e:
            logger.error("ipqs_ip_reputation_failed", error=str(e), ip=ip)
            return self.error_result(e)

class EmailValidationAction(IntegrationAction):
    """Query IPQualityScore Email Validation API."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Validate an email address for deliverability, fraud risk, and disposability.

        Args:
            **kwargs: Must contain:
                - email (str): Email address to validate
                - fast (bool, optional): Skip SMTP check
                - suggest_domain (bool, optional): Check for domain typos
                - timeout (int, optional): SMTP check timeout in seconds
                - strictness (int, optional): Spam trap detection level (0, 1, or 2)
                - abuse_strictness (int, optional): ML abuse pattern recognition level

        Returns:
            Result with email validation data including validity, fraud score,
            deliverability, disposable flag, etc.
        """
        email = kwargs.get("email")
        if not email:
            return self.error_result(
                MSG_MISSING_PARAM.format("email"), error_type="ValidationError"
            )

        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        # Validate optional integer parameters
        is_valid, err = _validate_non_negative_int(
            kwargs.get("timeout"), MSG_INVALID_TIMEOUT
        )
        if not is_valid:
            return self.error_result(err, error_type="ValidationError")

        is_valid, err = _validate_strictness(kwargs.get("strictness"))
        if not is_valid:
            return self.error_result(err, error_type="ValidationError")

        is_valid, err = _validate_non_negative_int(
            kwargs.get("abuse_strictness"), MSG_INVALID_ABUSE_STRICTNESS
        )
        if not is_valid:
            return self.error_result(err, error_type="ValidationError")

        url = _build_api_url(ENDPOINT_EMAIL, api_key, email)
        http_timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        params = _build_optional_params(
            fast=kwargs.get("fast"),
            suggest_domain=kwargs.get("suggest_domain"),
            timeout=kwargs.get("timeout"),
            strictness=kwargs.get("strictness"),
            abuse_strictness=kwargs.get("abuse_strictness"),
        )

        try:
            response = await self.http_request(
                url=url, params=params, timeout=http_timeout
            )
            result = response.json()

            if not result.get("success"):
                return self.error_result(
                    result.get("message", MSG_API_FAILURE), error_type="APIError"
                )

            return self.success_result(data=result)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 509:
                return self.error_result(MSG_RATE_LIMITED, error_type="RateLimitError")
            if e.response.status_code == 404:
                logger.info("ipqs_email_not_found", email=email)
                return self.success_result(
                    not_found=True,
                    data={"email": email, "fraud_score": 0, "valid": False},
                )
            return self.error_result(e)
        except Exception as e:
            logger.error("ipqs_email_validation_failed", error=str(e), email=email)
            return self.error_result(e)

class UrlCheckerAction(IntegrationAction):
    """Query IPQualityScore malicious URL scanner API."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check a URL for malicious content, phishing, and risk scoring.

        Args:
            **kwargs: Must contain:
                - url (str): URL to check
                - strictness (int, optional): Scan strictness (0, 1, or 2)
                - fast (bool, optional): Use lighter checks for faster response

        Returns:
            Result with URL safety data including risk score, malware flag,
            phishing flag, suspicious flag, etc.
        """
        check_url = kwargs.get("url")
        if not check_url:
            return self.error_result(
                MSG_MISSING_PARAM.format("url"), error_type="ValidationError"
            )

        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        is_valid, err = _validate_strictness(kwargs.get("strictness"))
        if not is_valid:
            return self.error_result(err, error_type="ValidationError")

        # URL-encode the target URL as path parameter (per upstream pattern)
        encoded_url = urllib.parse.quote_plus(check_url)
        url = _build_api_url(ENDPOINT_URL, api_key, encoded_url)
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        params = _build_optional_params(
            strictness=kwargs.get("strictness"),
            fast=kwargs.get("fast"),
        )

        try:
            response = await self.http_request(url=url, params=params, timeout=timeout)
            result = response.json()

            if "status_code" in result and result["status_code"] != 200:
                return self.error_result(
                    result.get("message", MSG_API_FAILURE), error_type="APIError"
                )

            if not result.get("success"):
                return self.error_result(
                    result.get("message", MSG_API_FAILURE), error_type="APIError"
                )

            return self.success_result(data=result)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 509:
                return self.error_result(MSG_RATE_LIMITED, error_type="RateLimitError")
            if e.response.status_code == 404:
                logger.info("ipqs_url_not_found", url=check_url)
                return self.success_result(
                    not_found=True,
                    data={"url": check_url, "risk_score": 0, "unsafe": False},
                )
            return self.error_result(e)
        except Exception as e:
            logger.error("ipqs_url_checker_failed", error=str(e), url=check_url)
            return self.error_result(e)

class PhoneValidationAction(IntegrationAction):
    """Query IPQualityScore Phone Validation API."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Validate a phone number for fraud risk, carrier info, and validity.

        Args:
            **kwargs: Must contain:
                - phone (str): Phone number to validate
                - strictness (int, optional): Detection strictness (0, 1, or 2)
                - country (str, optional): Expected country code(s), comma-separated

        Returns:
            Result with phone validation data including validity, fraud score,
            carrier, line type, VOIP flag, etc.
        """
        phone = kwargs.get("phone")
        if not phone:
            return self.error_result(
                MSG_MISSING_PARAM.format("phone"), error_type="ValidationError"
            )

        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        is_valid, err = _validate_strictness(kwargs.get("strictness"))
        if not is_valid:
            return self.error_result(err, error_type="ValidationError")

        url = _build_api_url(ENDPOINT_PHONE, api_key, str(phone))
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        params = _build_optional_params(
            strictness=kwargs.get("strictness"),
            country=kwargs.get("country"),
        )

        try:
            response = await self.http_request(url=url, params=params, timeout=timeout)
            result = response.json()

            if not result.get("success"):
                return self.error_result(
                    result.get("message", MSG_API_FAILURE), error_type="APIError"
                )

            return self.success_result(data=result)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 509:
                return self.error_result(MSG_RATE_LIMITED, error_type="RateLimitError")
            if e.response.status_code == 404:
                logger.info("ipqs_phone_not_found", phone=str(phone))
                return self.success_result(
                    not_found=True,
                    data={"phone": str(phone), "fraud_score": 0, "valid": False},
                )
            return self.error_result(e)
        except Exception as e:
            logger.error("ipqs_phone_validation_failed", error=str(e), phone=str(phone))
            return self.error_result(e)

class DarkWebLeakLookupAction(IntegrationAction):
    """Query IPQualityScore Dark Web Leak API for exposed credentials."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Search dark web breach databases for leaked credentials.

        Args:
            **kwargs: Must contain:
                - type (str): Type of data to search: "email", "password", or "username"
                - value (str): The value to search for

        Returns:
            Result with leak data including exposed flag, source, first_seen, etc.
        """
        leak_type = kwargs.get("type")
        if not leak_type:
            return self.error_result(
                MSG_MISSING_PARAM.format("type"), error_type="ValidationError"
            )

        if leak_type not in DARK_WEB_LEAK_TYPES:
            return self.error_result(
                MSG_INVALID_LEAK_TYPE, error_type="ValidationError"
            )

        value = kwargs.get("value")
        if not value:
            return self.error_result(
                MSG_MISSING_PARAM.format("value"), error_type="ValidationError"
            )

        # Validate email format when searching for email type
        if leak_type == "email":
            is_valid, err = _validate_email(value)
            if not is_valid:
                return self.error_result(err, error_type="ValidationError")

        api_key = self.credentials.get("api_key")
        if not api_key:
            return self.error_result(
                MSG_MISSING_API_KEY, error_type="ConfigurationError"
            )

        # Dark web leak URL pattern: /leaked/{type}/{apikey}/{data}
        encoded_value = urllib.parse.quote_plus(value)
        url = f"{IPQS_BASE_URL}/{ENDPOINT_LEAKED}/{leak_type}/{api_key}/{encoded_value}"
        timeout = self.settings.get("timeout", DEFAULT_TIMEOUT)

        try:
            response = await self.http_request(url=url, timeout=timeout)
            result = response.json()

            if not result.get("success"):
                return self.error_result(
                    result.get("message", MSG_API_FAILURE), error_type="APIError"
                )

            return self.success_result(data=result)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 509:
                return self.error_result(MSG_RATE_LIMITED, error_type="RateLimitError")
            if e.response.status_code == 404:
                logger.info("ipqs_dark_web_leak_not_found", type=leak_type, value=value)
                return self.success_result(
                    not_found=True,
                    data={
                        "type": leak_type,
                        "value": value,
                        "exposed": False,
                        "found": [],
                    },
                )
            return self.error_result(e)
        except Exception as e:
            logger.error(
                "ipqs_dark_web_leak_lookup_failed",
                error=str(e),
                type=leak_type,
                value=value,
            )
            return self.error_result(e)
