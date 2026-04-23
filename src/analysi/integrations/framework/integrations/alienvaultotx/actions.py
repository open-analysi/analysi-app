"""AlienVault OTX (Open Threat Exchange) integration actions.
"""

import ipaddress
from typing import Any

import httpx
import validators

from analysi.config.logging import get_logger
from analysi.integrations.framework.base import IntegrationAction

from .constants import (
    ALIENVAULT_BASE_URL,
    CREDENTIAL_API_KEY,
    DEFAULT_RESPONSE_TYPE,
    DEFAULT_TIMEOUT,
    ERROR_TYPE_CONFIGURATION,
    ERROR_TYPE_VALIDATION,
    MSG_INVALID_RESPONSE_TYPE,
    MSG_MALFORMED_DOMAIN,
    MSG_MALFORMED_IP,
    MSG_MISSING_API_KEY,
    RESPONSE_TYPES_DOMAIN,
    RESPONSE_TYPES_FILE,
    RESPONSE_TYPES_IPV4,
    RESPONSE_TYPES_IPV6,
    RESPONSE_TYPES_URL,
    SETTINGS_TIMEOUT,
    STATUS_ERROR,
    STATUS_SUCCESS,
)

logger = get_logger(__name__)

# ============================================================================
# VALIDATION UTILITIES
# ============================================================================

def _validate_ip_safe(ip_address: str) -> tuple[bool, str, str | None]:
    """Validate IP address and determine version (IPv4 or IPv6).

    Args:
        ip_address: IP address to validate

    Returns:
        Tuple of (is_valid, error_message, ip_version)
        ip_version is "ipv4" or "ipv6" if valid, None otherwise
    """
    if not ip_address or not isinstance(ip_address, str):
        return False, "IP address must be a non-empty string", None

    try:
        ip_obj = ipaddress.ip_address(ip_address)
        if isinstance(ip_obj, ipaddress.IPv4Address):
            return True, "", "ipv4"
        if isinstance(ip_obj, ipaddress.IPv6Address):
            return True, "", "ipv6"
    except ValueError:
        pass

    return False, MSG_MALFORMED_IP, None

def _validate_domain_safe(domain: str) -> tuple[bool, str]:
    """Validate domain format.

    Args:
        domain: Domain to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not domain or not isinstance(domain, str):
        return False, "Domain must be a non-empty string"
    if validators.domain(domain):
        return True, ""
    return False, MSG_MALFORMED_DOMAIN

def _validate_hash_safe(file_hash: str) -> tuple[bool, str]:
    """Validate file hash format (MD5, SHA1, or SHA256).

    Args:
        file_hash: File hash to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not file_hash or not isinstance(file_hash, str):
        return False, "File hash must be a non-empty string"

    hash_length = len(file_hash)
    if hash_length == 32:  # MD5
        hash_type = "MD5"
    elif hash_length == 40:  # SHA1
        hash_type = "SHA1"
    elif hash_length == 64:  # SHA256
        hash_type = "SHA256"
    else:
        return (
            False,
            "File hash must be MD5 (32 chars), SHA1 (40 chars), or SHA256 (64 chars)",
        )

    # Verify all characters are hexadecimal
    if not all(c in "0123456789abcdefABCDEF" for c in file_hash):
        return (
            False,
            f"Invalid {hash_type} hash format - must contain only hexadecimal characters",
        )

    return True, ""

def _validate_url_safe(url: str) -> tuple[bool, str]:
    """Validate URL format.

    Args:
        url: URL to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not url or not isinstance(url, str):
        return False, "URL must be a non-empty string"
    if validators.url(url):
        return True, ""
    return False, "Invalid URL format"

def _validate_response_type(
    response_type: str, valid_types: list[str]
) -> tuple[bool, str]:
    """Validate response type parameter.

    Args:
        response_type: Response type to validate
        valid_types: List of valid response types

    Returns:
        Tuple of (is_valid, error_message)
    """
    if response_type not in valid_types:
        return False, MSG_INVALID_RESPONSE_TYPE.format(
            valid_types=", ".join(valid_types)
        )
    return True, ""

# ============================================================================
# INTEGRATION ACTIONS
# ============================================================================

class HealthCheckAction(IntegrationAction):
    """Health check for AlienVault OTX API connectivity."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Check AlienVault OTX API connectivity.

        Returns:
            Result with status=success if healthy, status=error if unhealthy
        """
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": MSG_MISSING_API_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
                "data": {"healthy": False},
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Test connectivity by getting user info
            response = await self.http_request(
                f"{ALIENVAULT_BASE_URL}/api/v1/users/me",
                headers={
                    "X-OTX-API-KEY": api_key,
                    "Content-Type": "application/json",
                },
                timeout=timeout,
            )
            result = response.json()

            return {
                "healthy": True,
                "status": STATUS_SUCCESS,
                "message": "AlienVault OTX API is accessible",
                "data": {"healthy": True, "user_info": result},
            }

        except Exception as e:
            logger.error("alienvault_otx_health_check_failed", error=str(e))
            return {
                "healthy": False,
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
                "data": {"healthy": False},
            }

class DomainReputationAction(IntegrationAction):
    """Look up domain reputation."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get domain reputation from AlienVault OTX.

        Args:
            **kwargs: Must contain:
                - domain (str): Domain to query
                - response_type (str, optional): Type of response (default: "general")

        Returns:
            Result with domain reputation data or error
        """
        # Validate domain
        domain = kwargs.get("domain")
        is_valid, error_msg = _validate_domain_safe(domain)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate response type
        response_type = kwargs.get("response_type", DEFAULT_RESPONSE_TYPE)
        is_valid, error_msg = _validate_response_type(
            response_type, RESPONSE_TYPES_DOMAIN
        )
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Get credentials
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_API_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            response = await self.http_request(
                f"{ALIENVAULT_BASE_URL}/api/v1/indicators/domain/{domain}/{response_type}",
                headers={
                    "X-OTX-API-KEY": api_key,
                    "Content-Type": "application/json",
                },
                timeout=timeout,
            )
            result = response.json()

            # Extract pulse information
            pulse_info = result.get("pulse_info", {})
            pulses = pulse_info.get("pulses", [])

            return {
                "status": STATUS_SUCCESS,
                "domain": domain,
                "response_type": response_type,
                "num_pulses": len(pulses),
                "pulse_info": pulse_info,
                "full_data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("alienvault_otx_domain_not_found", domain=domain)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "domain": domain,
                    "response_type": response_type,
                    "num_pulses": 0,
                    "pulse_info": {},
                }
            logger.error(
                "alienvault_otx_domain_reputation_lookup_failed_for",
                domain=domain,
                error=str(e),
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error(
                "alienvault_otx_domain_reputation_lookup_failed_for",
                domain=domain,
                error=str(e),
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class IpReputationAction(IntegrationAction):
    """Look up IP address reputation."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get IP address reputation from AlienVault OTX.

        Args:
            **kwargs: Must contain:
                - ip (str): IP address to query (IPv4 or IPv6)
                - response_type (str, optional): Type of response (default: "general")

        Returns:
            Result with IP reputation data or error
        """
        # Validate IP address
        ip = kwargs.get("ip")
        is_valid, error_msg, ip_version = _validate_ip_safe(ip)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate response type based on IP version
        response_type = kwargs.get("response_type", DEFAULT_RESPONSE_TYPE)
        if ip_version == "ipv4":
            valid_types = RESPONSE_TYPES_IPV4
        else:  # ipv6
            valid_types = RESPONSE_TYPES_IPV6

        is_valid, error_msg = _validate_response_type(response_type, valid_types)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Get credentials
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_API_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            # Use appropriate endpoint based on IP version
            if ip_version == "ipv4":
                endpoint = f"/api/v1/indicators/IPv4/{ip}/{response_type}"
            else:
                endpoint = f"/api/v1/indicators/IPv6/{ip}/{response_type}"

            response = await self.http_request(
                f"{ALIENVAULT_BASE_URL}{endpoint}",
                headers={
                    "X-OTX-API-KEY": api_key,
                    "Content-Type": "application/json",
                },
                timeout=timeout,
            )
            result = response.json()

            # Extract pulse information
            pulse_info = result.get("pulse_info", {})
            pulses = pulse_info.get("pulses", [])

            return {
                "status": STATUS_SUCCESS,
                "ip": ip,
                "ip_version": ip_version,
                "response_type": response_type,
                "num_pulses": len(pulses),
                "pulse_info": pulse_info,
                "full_data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("alienvault_otx_ip_not_found", ip=ip)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "ip": ip,
                    "ip_version": ip_version,
                    "response_type": response_type,
                    "num_pulses": 0,
                    "pulse_info": {},
                }
            logger.error(
                "alienvault_otx_ip_reputation_lookup_failed_for", ip=ip, error=str(e)
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error(
                "alienvault_otx_ip_reputation_lookup_failed_for", ip=ip, error=str(e)
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class FileReputationAction(IntegrationAction):
    """Look up file hash reputation."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get file hash reputation from AlienVault OTX.

        Args:
            **kwargs: Must contain:
                - hash (str): File hash (MD5, SHA1, or SHA256)
                - response_type (str, optional): Type of response (default: "general")

        Returns:
            Result with file reputation data or error
        """
        # Validate file hash
        file_hash = kwargs.get("hash")
        is_valid, error_msg = _validate_hash_safe(file_hash)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate response type
        response_type = kwargs.get("response_type", DEFAULT_RESPONSE_TYPE)
        is_valid, error_msg = _validate_response_type(
            response_type, RESPONSE_TYPES_FILE
        )
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Get credentials
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_API_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            response = await self.http_request(
                f"{ALIENVAULT_BASE_URL}/api/v1/indicators/file/{file_hash}/{response_type}",
                headers={
                    "X-OTX-API-KEY": api_key,
                    "Content-Type": "application/json",
                },
                timeout=timeout,
            )
            result = response.json()

            # Extract pulse information
            pulse_info = result.get("pulse_info", {})
            pulses = pulse_info.get("pulses", [])

            return {
                "status": STATUS_SUCCESS,
                "file_hash": file_hash,
                "response_type": response_type,
                "num_pulses": len(pulses),
                "pulse_info": pulse_info,
                "full_data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("alienvault_otx_file_not_found", file_hash=file_hash)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "file_hash": file_hash,
                    "response_type": response_type,
                    "num_pulses": 0,
                    "pulse_info": {},
                }
            logger.error(
                "alienvault_otx_file_reputation_lookup_failed_for",
                file_hash=file_hash,
                error=str(e),
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error(
                "alienvault_otx_file_reputation_lookup_failed_for",
                file_hash=file_hash,
                error=str(e),
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class UrlReputationAction(IntegrationAction):
    """Look up URL reputation."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get URL reputation from AlienVault OTX.

        Args:
            **kwargs: Must contain:
                - url (str): URL to query
                - response_type (str, optional): Type of response (default: "general")

        Returns:
            Result with URL reputation data or error
        """
        # Validate URL
        url = kwargs.get("url")
        is_valid, error_msg = _validate_url_safe(url)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Validate response type
        response_type = kwargs.get("response_type", DEFAULT_RESPONSE_TYPE)
        is_valid, error_msg = _validate_response_type(response_type, RESPONSE_TYPES_URL)
        if not is_valid:
            return {
                "status": STATUS_ERROR,
                "error": error_msg,
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Get credentials
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_API_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            response = await self.http_request(
                f"{ALIENVAULT_BASE_URL}/api/v1/indicators/url/{url}/{response_type}",
                headers={
                    "X-OTX-API-KEY": api_key,
                    "Content-Type": "application/json",
                },
                timeout=timeout,
            )
            result = response.json()

            # Extract pulse information
            pulse_info = result.get("pulse_info", {})
            pulses = pulse_info.get("pulses", [])

            return {
                "status": STATUS_SUCCESS,
                "url": url,
                "response_type": response_type,
                "num_pulses": len(pulses),
                "pulse_info": pulse_info,
                "full_data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info("alienvault_otx_url_not_found", url=url)
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "url": url,
                    "response_type": response_type,
                    "num_pulses": 0,
                    "pulse_info": {},
                }
            logger.error(
                "alienvault_otx_url_reputation_lookup_failed_for", url=url, error=str(e)
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error(
                "alienvault_otx_url_reputation_lookup_failed_for", url=url, error=str(e)
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }

class GetPulseAction(IntegrationAction):
    """Get details of a specific pulse by ID."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Get pulse details from AlienVault OTX.

        Args:
            **kwargs: Must contain:
                - pulse_id (str): Pulse ID to retrieve

        Returns:
            Result with pulse details or error
        """
        # Validate pulse_id
        pulse_id = kwargs.get("pulse_id")
        if not pulse_id or not isinstance(pulse_id, str):
            return {
                "status": STATUS_ERROR,
                "error": "pulse_id must be a non-empty string",
                "error_type": ERROR_TYPE_VALIDATION,
            }

        # Get credentials
        api_key = self.credentials.get(CREDENTIAL_API_KEY)
        if not api_key:
            return {
                "status": STATUS_ERROR,
                "error": MSG_MISSING_API_KEY,
                "error_type": ERROR_TYPE_CONFIGURATION,
            }

        timeout = self.settings.get(SETTINGS_TIMEOUT, DEFAULT_TIMEOUT)

        try:
            response = await self.http_request(
                f"{ALIENVAULT_BASE_URL}/api/v1/pulses/{pulse_id}",
                headers={
                    "X-OTX-API-KEY": api_key,
                    "Content-Type": "application/json",
                },
                timeout=timeout,
            )
            result = response.json()

            # Extract indicator count
            indicators = result.get("indicators", [])

            return {
                "status": STATUS_SUCCESS,
                "pulse_id": pulse_id,
                "num_indicators": len(indicators),
                "pulse_name": result.get("name"),
                "pulse_description": result.get("description"),
                "full_data": result,
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {
                    "status": STATUS_SUCCESS,
                    "not_found": True,
                    "pulse_id": pulse_id,
                    "num_indicators": 0,
                    "pulse_info": {},
                }

            logger.error(
                "alienvault_otx_get_pulse_failed_for", pulse_id=pulse_id, error=str(e)
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
        except Exception as e:
            logger.error(
                "alienvault_otx_get_pulse_failed_for", pulse_id=pulse_id, error=str(e)
            )
            return {
                "status": STATUS_ERROR,
                "error": str(e),
                "error_type": type(e).__name__,
            }
